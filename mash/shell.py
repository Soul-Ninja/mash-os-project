"""Entry points, line editing, and the read/parse/execute loop."""
import argparse
import glob
import os
from pathlib import Path
import shlex
import signal
import sys

from . import builtins
from .executor import launch, redirected
from .jobs import JobManager
from .parser import parse


class Shell:
    def __init__(self, interactive=False):
        self.interactive = interactive
        self.manager = JobManager(interactive)
        self.history = []
        self.status = 0
        self.exiting = False
        self.readline = None
        self.history_path = None
        self.session_history = []

    def setup_editor(self):
        try:
            import readline
        except ImportError:
            print("mash: readline unavailable; history/Tab keys disabled", file=sys.stderr)
            return
        self.readline = readline
        readline.set_auto_history(False)
        readline.set_history_length(1000)
        setting = os.environ.get("MASH_HISTORY", str(Path.home() / ".mash_history"))
        self.history_path = Path(setting).expanduser() if setting else None
        if self.history_path:
            try:
                readline.read_history_file(self.history_path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                print(f"mash: history: {exc}", file=sys.stderr)
        self.history = [readline.get_history_item(i)
                        for i in range(1, readline.get_current_history_length() + 1)][-1000:]
        readline.set_completer_delims(" \t\n|&<>;")
        readline.set_completer(self.complete)
        readline.parse_and_bind("tab: complete")

    def complete(self, text, state):
        if state == 0:
            matches = {path + ("/" if os.path.isdir(path) else "")
                       for path in glob.glob(glob.escape(text) + "*")}
            if self.readline.get_begidx() == 0:
                matches.update(name for name in builtins.NAMES if name.startswith(text))
                for directory in os.get_exec_path():
                    try:
                        for item in Path(directory or ".").iterdir():
                            if item.name.startswith(text) and item.is_file() and os.access(item, os.X_OK):
                                matches.add(item.name)
                    except OSError:
                        continue
            # Completion targets unquoted words; escape spaces and shell operators.
            self.completions = [shlex.quote(match) for match in sorted(matches)]
        return self.completions[state] if state < len(self.completions) else None

    def execute(self, line):
        try:
            pipeline = parse(line)
            if pipeline is None:
                return self.status
            self.history.append(line)
            self.history = self.history[-1000:]
            if self.readline:
                self.readline.add_history(line)
                self.session_history.append(line)
            has_builtin = any(command.argv[0] in builtins.NAMES for command in pipeline.commands)
            if has_builtin:
                if len(pipeline.commands) != 1 or pipeline.background:
                    raise ValueError("built-ins must be standalone foreground commands")
                command = pipeline.commands[0]
                if command.argv[0] == "fg" and command.redirects:
                    raise ValueError("fg cannot be redirected")
                with redirected(command.redirects):
                    try:
                        self.status = builtins.run(command, self)
                    except (ValueError, OSError) as exc:
                        print(f"mash: {exc}", file=sys.stderr)
                        self.status = 2 if isinstance(exc, ValueError) else 1
            else:
                self.status = launch(pipeline, self.manager)
        except ValueError as exc:
            print(f"mash: {exc}", file=sys.stderr)
            self.status = 2
        except OSError as exc:
            print(f"mash: {exc}", file=sys.stderr)
            self.status = 1
        return self.status

    def close(self):
        try:
            self.manager.close()
        finally:
            if self.readline and self.history_path and self.session_history:
                try:
                    fd = os.open(self.history_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                    os.close(fd)
                    self.readline.append_history_file(len(self.session_history), self.history_path)
                except OSError as exc:
                    print(f"mash: cannot save history: {exc}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description="MASH: educational Unix shell")
    parser.add_argument("-c", dest="command", help="execute one pipeline and exit")
    options = parser.parse_args(argv)
    if os.name != "posix" or not hasattr(os, "fork"):
        print("mash requires Linux/Unix. On Windows, run it inside WSL or a Linux container.", file=sys.stderr)
        return 1
    interactive = options.command is None and sys.stdin.isatty()
    shell = Shell(interactive)
    old_sigquit = signal.signal(signal.SIGQUIT, signal.SIG_IGN)
    old_sigchld = signal.signal(signal.SIGCHLD, lambda *_: shell.manager.reap())
    try:
        if options.command is not None:
            return shell.execute(options.command)
        if interactive:
            shell.setup_editor()
            print("MASH | Unix shell and process laboratory. Type help for commands.")
        while not shell.exiting:
            try:
                shell.manager.notify()
                if interactive:
                    line = input("mash> ")
                else:
                    # Avoid buffered read-ahead consuming input intended for child commands.
                    data = bytearray()
                    while True:
                        char = os.read(0, 1)
                        if not char or char == b"\n":
                            break
                        data.extend(char)
                    if not char and not data:
                        break
                    line = data.decode(sys.stdin.encoding or "utf-8", errors="surrogateescape")
                shell.execute(line)
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                shell.status = 130
        return shell.status
    finally:
        shell.close()
        signal.signal(signal.SIGCHLD, old_sigchld)
        signal.signal(signal.SIGQUIT, old_sigquit)
