"""Real Unix processes; automatically skipped on native Windows."""
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = str(ROOT / 'mash.py')
POSIX = os.name == 'posix' and hasattr(os, 'fork')


@unittest.skipUnless(POSIX, 'requires Unix fork/exec and process groups')
class IntegrationTests(unittest.TestCase):
    def run_shell(self, command=None, script=None, cwd=None):
        argv = [sys.executable, ENTRY]
        if command is not None:
            argv += ['-c', command]
        return subprocess.run(argv, input=script, text=True, capture_output=True, cwd=cwd,
                              env={**os.environ, 'MASH_HISTORY': ''}, timeout=10)

    def test_quoted_arguments(self):
        result = self.run_shell('printf "%s\\n" "hello world" "|" ""')
        self.assertEqual(result.stdout, 'hello world\n|\n\n')
        self.assertEqual(result.returncode, 0)

    def test_three_stage_pipeline_and_large_payload(self):
        result = self.run_shell('seq 1 20000 | cat | wc -l')
        self.assertEqual(result.stdout.strip(), '20000')
        self.assertEqual(result.returncode, 0)

    def test_early_reader_exit_does_not_hang(self):
        result = self.run_shell('yes | head -n 1')
        self.assertEqual(result.stdout, 'y\n')
        self.assertEqual(result.returncode, 0)

    def test_redirection_append_and_input(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_shell(script='printf "one\\n" > "a file"\nprintf "two\\n" >> "a file"\ncat < "a file"\n', cwd=directory)
            self.assertEqual(result.stdout, 'one\ntwo\n')
            self.assertEqual(Path(directory, 'a file').read_text(), 'one\ntwo\n')

    def test_stderr_redirection(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_shell('sh -c "echo problem >&2" 2>err', cwd=directory)
            self.assertEqual(result.stderr, '')
            self.assertEqual(Path(directory, 'err').read_text(), 'problem\n')

    def test_builtin_redirection_is_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_shell(script='help > help.txt\nprintf ok\ncd missing 2>err\nprintf done\n', cwd=directory)
            self.assertEqual(result.stdout, 'okdone')
            self.assertIn('Built-ins', Path(directory, 'help.txt').read_text())
            self.assertIn('mash:', Path(directory, 'err').read_text())

    def test_cd_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_shell(script=f'cd {shlex.quote(directory)}\npwd\n')
            self.assertEqual(os.path.realpath(result.stdout.strip()), os.path.realpath(directory))

    def test_command_errors_and_last_pipeline_status(self):
        self.assertEqual(self.run_shell('mash-no-such-executable-12345').returncode, 127)
        self.assertEqual(self.run_shell('true | false').returncode, 1)
        self.assertEqual(self.run_shell('false | true').returncode, 0)
        self.assertEqual(self.run_shell('echo >').returncode, 2)

    def test_unexecutable_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'blocked')
            path.write_text('no execute permission')
            path.chmod(0o600)
            self.assertEqual(self.run_shell(shlex.quote(str(path))).returncode, 126)

    def test_redirection_failure_does_not_poison_next_command(self):
        result = self.run_shell(script='echo bad > /mash-nonexistent-dir-12345/out\nprintf good\n')
        self.assertEqual(result.stdout, 'good')
        self.assertIn('mash:', result.stderr)

    def test_background_jobs_and_foreground_wait(self):
        result = self.run_shell(script='sleep 0.2 &\njobs\nfg %1\nprintf finished\n')
        self.assertIn('Running', result.stdout)
        self.assertTrue(result.stdout.endswith('finished'))

    def test_background_noninteractive_stdin_is_devnull(self):
        result = self.run_shell(script='cat &\nprintf intact\n')
        self.assertIn('intact', result.stdout)

    def test_dashboard_events_and_sysinfo(self):
        result = self.run_shell(script='sleep 1 &\nmonitor\nfg\nsysinfo\n')
        self.assertIn('MASH PROCESS DASHBOARD', result.stdout)
        self.assertIn('launched PID', result.stdout)
        self.assertIn('CPU:', result.stdout)

    def test_external_command_can_consume_script_stdin(self):
        result = self.run_shell(script='dd bs=1 count=11 status=none\nchild data\nprintf after\n')
        self.assertEqual(result.stdout, 'child data\nafter')

    def test_force_exit_reaps_owned_children(self):
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory, 'pid')
            result = self.run_shell(script=f'sh -c "echo $$ > {pidfile}; exec sleep 60" &\nsleep 0.1\nexit --force\n')
            self.assertEqual(result.returncode, 0)
            pid = int(pidfile.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_repeated_pipeline_execution_does_not_leak_descriptors(self):
        code = ('import os; from mash.shell import Shell; s=Shell(); '
                'before=len(os.listdir("/proc/self/fd")); '
                '[s.execute("true | true") for _ in range(50)]; '
                'assert len(os.listdir("/proc/self/fd")) == before; s.close()')
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(POSIX, 'requires a Unix pseudo-terminal')
class TerminalTests(unittest.TestCase):
    def setUp(self):
        import pty
        self.directory = tempfile.TemporaryDirectory()
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            os.environ['MASH_HISTORY'] = str(Path(self.directory.name, 'history'))
            os.chdir(self.directory.name)
            os.execv(sys.executable, [sys.executable, ENTRY])
        self.read_until(b'mash> ')

    def tearDown(self):
        try:
            os.write(self.fd, b'\x03exit --force\n')
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                done, _ = os.waitpid(self.pid, os.WNOHANG)
                if done:
                    break
                time.sleep(0.02)
            else:
                os.kill(self.pid, signal.SIGKILL)
                os.waitpid(self.pid, 0)
        except (OSError, ChildProcessError):
            pass
        os.close(self.fd)
        self.directory.cleanup()

    def read_until(self, needle, timeout=5):
        import select
        output = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if select.select([self.fd], [], [], 0.1)[0]:
                try:
                    data = os.read(self.fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                output.extend(data)
                if needle in output:
                    return bytes(output)
        self.fail(f'terminal did not produce {needle!r}: {bytes(output)!r}')

    def send(self, text):
        os.write(self.fd, text.encode() + b'\n')
        return self.read_until(b'mash> ')

    def test_ctrl_c_interrupts_child_and_shell_survives(self):
        os.write(self.fd, b'sleep 60\n')
        time.sleep(0.15)
        os.write(self.fd, b'\x03')
        self.read_until(b'mash> ')
        self.assertIn(b'survived', self.send('printf survived'))

    def test_stop_resume_and_foreground(self):
        os.write(self.fd, b'sleep 60\n')
        time.sleep(0.15)
        os.write(self.fd, b'\x1a')
        self.assertIn(b'Stopped', self.read_until(b'mash> '))
        self.assertIn(b'Running', self.send('bg %1'))
        os.write(self.fd, b'fg %1\n')
        time.sleep(0.15)
        os.write(self.fd, b'\x03')
        self.read_until(b'mash> ')

    def test_terminal_reader_gets_foreground_ownership(self):
        os.write(self.fd, b'cat\n')
        time.sleep(0.1)
        os.write(self.fd, b'hello-terminal\n')
        self.read_until(b'hello-terminal')
        os.write(self.fd, b'\x04')
        self.read_until(b'mash> ')

    def test_monitor_watch_returns_on_ctrl_c(self):
        os.write(self.fd, b'monitor --watch\n')
        self.read_until(b'Refresh:')
        os.write(self.fd, b'\x03')
        self.read_until(b'mash> ')

    def test_background_children_are_reaped_while_prompt_is_idle(self):
        self.send('sleep 0.1 &')
        time.sleep(0.3)
        children = Path(f'/proc/{self.pid}/task/{self.pid}/children').read_text().strip()
        self.assertEqual(children, '')

    def test_completion_and_history_keys(self):
        self.send('printf history-marker')
        os.write(self.fd, b'\x1b[A\n')
        self.assertIn(b'history-marker', self.read_until(b'mash> '))
        os.write(self.fd, b'sysin\t\n')
        self.assertIn(b'CPU:', self.read_until(b'mash> '))


if __name__ == '__main__':
    unittest.main()
