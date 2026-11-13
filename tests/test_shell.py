import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from mash import builtins
from mash.parser import Command
from mash.shell import Shell, main


class ShellTests(unittest.TestCase):
    def shell(self):
        with patch('mash.shell.JobManager'):
            return Shell()

    def test_builtin_in_pipeline_or_background_is_rejected_before_launch(self):
        shell = self.shell()
        with patch('mash.shell.launch') as launch, contextlib.redirect_stderr(io.StringIO()):
            for line in ('cd / | cat', 'sleep 1 | jobs', 'cd / &'):
                self.assertEqual(shell.execute(line), 2)
        launch.assert_not_called()

    def test_bad_parse_does_not_launch(self):
        shell = self.shell()
        with patch('mash.shell.launch') as launch, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(shell.execute('echo >'), 2)
        launch.assert_not_called()

    def test_external_pipeline_status(self):
        shell = self.shell()
        with patch('mash.shell.launch', return_value=7):
            self.assertEqual(shell.execute('false'), 7)
            self.assertEqual(shell.execute('  '), 7)

    def test_cd_changes_directory_and_reports_missing_directory(self):
        shell = self.shell()
        original = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                builtins.run(Command(['cd', directory]), shell)
                self.assertEqual(os.path.realpath(os.getcwd()), os.path.realpath(directory))
                with self.assertRaises(OSError):
                    builtins.run(Command(['cd', 'no-such-mash-directory']), shell)
                os.chdir(original)
        finally:
            os.chdir(original)

    def test_exit_refuses_active_jobs_without_force(self):
        shell = self.shell()
        shell.manager.jobs = {1: MagicMock(state='Running')}
        with self.assertRaisesRegex(ValueError, 'active jobs'):
            builtins.run(Command(['exit']), shell)
        self.assertFalse(shell.exiting)
        builtins.run(Command(['exit', '--force']), shell)
        self.assertTrue(shell.exiting)

    def test_builtin_argument_validation(self):
        shell = self.shell()
        for argv in (['cd', 'a', 'b'], ['jobs', 'oops'], ['fg', '1', '2'],
                     ['exit', 'oops'], ['monitor', '--bad'], ['monitor', '--watch']):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                builtins.run(Command(argv), shell)

    def test_fg_rejects_redirection_before_opening_files(self):
        shell = self.shell()
        with patch('mash.shell.redirected') as redirect, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(shell.execute('fg > out'), 2)
        redirect.assert_not_called()

    def test_non_posix_entrypoint_gives_actionable_error(self):
        with patch('mash.shell.os.name', 'nt'), contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(['-c', 'echo hello']), 1)
        self.assertIn('WSL', error.getvalue())

    def test_completion_quotes_paths_with_spaces(self):
        shell = self.shell()
        shell.readline = MagicMock()
        shell.readline.get_begidx.return_value = 5
        with patch('mash.shell.glob.glob', return_value=['a file']), patch('mash.shell.os.path.isdir', return_value=False):
            self.assertEqual(shell.complete('a', 0), "'a file'")
            self.assertIsNone(shell.complete('a', 1))

    def test_history_persistence_appends_only_this_session(self):
        shell = self.shell()
        shell.readline = MagicMock()
        shell.history_path = 'history-file'
        shell.session_history = ['echo one', 'echo two']
        with patch('mash.shell.os.open', return_value=9), patch('mash.shell.os.close'):
            shell.close()
        shell.readline.append_history_file.assert_called_once_with(2, 'history-file')

    def test_disabled_history_does_not_write(self):
        shell = self.shell()
        shell.readline = MagicMock()
        shell.session_history = ['echo hello']
        shell.close()
        shell.readline.append_history_file.assert_not_called()


if __name__ == '__main__':
    unittest.main()
