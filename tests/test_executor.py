import errno
import unittest
from unittest.mock import MagicMock, call, patch

from mash.executor import apply_redirects, launch, redirected
from mash.parser import parse


class ExecutorTests(unittest.TestCase):
    def test_redirection_targets_and_flags(self):
        with patch('mash.executor.os.open', return_value=9) as opened, \
             patch('mash.executor.os.dup2') as dup, patch('mash.executor.os.close') as close:
            apply_redirects([('<', 'in'), ('>', 'out'), ('>>', 'out'), ('2>', 'err'), ('2>>', 'err')])
        self.assertEqual([c.args[1] for c in dup.call_args_list], [0, 1, 1, 2, 2])
        import os
        self.assertTrue(opened.call_args_list[2].args[1] & os.O_APPEND)
        self.assertTrue(opened.call_args_list[1].args[1] & os.O_TRUNC)
        self.assertEqual(close.call_count, 5)

    def test_open_target_descriptor_is_not_closed(self):
        with patch('mash.executor.os.open', return_value=1), \
             patch('mash.executor.os.set_inheritable') as inherit, patch('mash.executor.os.close') as close:
            apply_redirects([('>', 'out')])
        close.assert_not_called()
        inherit.assert_called_once_with(1, True)

    def test_builtin_descriptors_restored_after_error(self):
        with patch('mash.executor.os.dup', side_effect=[10, 11, 12]), \
             patch('mash.executor.os.dup2') as dup, patch('mash.executor.os.close') as close, \
             patch('mash.executor.apply_redirects', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError), redirected([('>', 'out')]):
                self.fail('must not enter the body')
        self.assertEqual(dup.call_args_list, [call(10, 0), call(11, 1), call(12, 2)])
        self.assertEqual(close.call_count, 3)

    def test_partial_pipeline_failure_kills_and_reaps_started_children(self):
        manager = MagicMock()
        with patch('mash.executor.os.pipe', side_effect=[(10, 11), (12, 13)]), \
             patch('mash.executor.os.fork', side_effect=[90, OSError(errno.EAGAIN, 'fork failed')], create=True), \
             patch('mash.executor.os.setpgid', create=True), \
             patch('mash.executor.signal.SIGKILL', 9, create=True), \
             patch('mash.executor.os.kill') as kill, \
             patch('mash.executor.os.waitpid', create=True) as wait, \
             patch('mash.executor.os.close') as close:
            with self.assertRaises(OSError):
                launch(parse('echo x | cat'), manager)
        kill.assert_called_once()
        wait.assert_called_once_with(90, 0)
        self.assertEqual({c.args[0] for c in close.call_args_list}, {10, 11, 12, 13})
        manager.add.assert_not_called()

    def test_pipe_allocation_failure_closes_previously_allocated_pipes(self):
        with patch('mash.executor.os.pipe', side_effect=[(10, 11), OSError('no descriptors')]), \
             patch('mash.executor.os.close') as close:
            with self.assertRaises(OSError):
                launch(parse('a | b | c'), MagicMock())
        self.assertEqual(close.call_args_list, [call(10), call(11)])


if __name__ == '__main__':
    unittest.main()
