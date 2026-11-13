"""Launch pipelines using fork/exec, with a gate before terminal access."""
import contextlib
import os
import signal
import sys

from .jobs import Process


def apply_redirects(redirects):
    for operator, path in redirects:
        target = 0 if operator == "<" else 2 if operator.startswith("2") else 1
        flags = os.O_RDONLY if target == 0 else os.O_WRONLY | os.O_CREAT
        if target != 0:
            flags |= os.O_APPEND if operator.endswith(">>") else os.O_TRUNC
        fd = os.open(path, flags, 0o644)
        try:
            if fd == target:
                os.set_inheritable(fd, True)
            else:
                os.dup2(fd, target, inheritable=True)
        finally:
            if fd != target:
                os.close(fd)


@contextlib.contextmanager
def redirected(redirects):
    saved = {}
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        for target in (0, 1, 2):
            saved[target] = os.dup(target)
        apply_redirects(redirects)
        yield
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        finally:
            for target, fd in saved.items():
                os.dup2(fd, target)
                os.close(fd)


def launch(pipeline, manager):
    pipes, processes, pgid = [], {}, 0
    gate_read = gate_write = None
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        for _ in pipeline.commands[:-1]:
            pipes.append(os.pipe())
        gate_read, gate_write = os.pipe()
        for index, command in enumerate(pipeline.commands):
            pid = os.fork()
            if pid == 0:
                phase = "setup"
                try:
                    os.setpgid(0, pgid)
                    for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTSTP,
                                signal.SIGTTIN, signal.SIGTTOU, signal.SIGPIPE, signal.SIGCHLD):
                        signal.signal(sig, signal.SIG_DFL)
                    os.close(gate_write)
                    os.read(gate_read, 1)
                    os.close(gate_read)
                    if index:
                        os.dup2(pipes[index - 1][0], 0)
                    if index < len(pipeline.commands) - 1:
                        os.dup2(pipes[index][1], 1)
                    for pair in pipes:
                        for fd in pair:
                            os.close(fd)
                    phase = "redirection"
                    if pipeline.background and index == 0 and not manager.interactive:
                        apply_redirects([("<", os.devnull)])
                    apply_redirects(command.redirects)
                    phase = "exec"
                    os.execvp(command.argv[0], command.argv)
                except BaseException as exc:
                    message = f"mash: {command.argv[0]}: {exc}\n"
                    with contextlib.suppress(OSError):
                        os.write(2, message.encode(errors="replace"))
                    code = 127 if phase == "exec" and isinstance(exc, FileNotFoundError) else 126
                    os._exit(1 if phase == "redirection" else code)
            processes[pid] = Process(command.argv)
            pgid = pgid or pid
            os.setpgid(pid, pgid)
        job = manager.add(pgid, processes, pipeline.source)
    except BaseException:
        # A partial pipeline must not leave blocked children or open pipe ends behind.
        for pid in processes:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        for pid in processes:
            with contextlib.suppress(ChildProcessError):
                os.waitpid(pid, 0)
        if gate_write is not None:
            os.close(gate_write)
        raise
    finally:
        for pair in pipes:
            for fd in pair:
                os.close(fd)
        if gate_read is not None:
            os.close(gate_read)
    if pipeline.background:
        os.close(gate_write)
        print(f"[{job.number}] {job.pgid}")
        return 0
    return manager.foreground(job, release_fd=gate_write)
