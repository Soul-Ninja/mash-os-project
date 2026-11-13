import contextlib
import io
import unittest
from unittest.mock import patch

from mash.jobs import Job, JobManager, Process


class JobTests(unittest.TestCase):
    def manager(self):
        with patch('mash.jobs.os.getpgrp', return_value=50, create=True):
            return JobManager()

    def test_pipeline_stops_only_when_all_live_members_stop(self):
        first, last = Process(['cat']), Process(['wc'])
        job = Job(1, 70, {70: first, 71: last}, 'cat | wc')
        first.state = 'Stopped'
        self.assertEqual(job.state, 'Running')
        last.state = 'Stopped'
        self.assertEqual(job.state, 'Stopped')
        first.code = 0
        self.assertEqual(job.state, 'Stopped')
        last.code = 7
        self.assertEqual(job.state, 'Done')
        self.assertEqual(job.status, 7)

    def test_job_numbers_do_not_reuse_completed_numbers(self):
        manager = self.manager()
        manager.add(70, {70: Process(['true'])}, 'true')
        manager.jobs.clear()
        self.assertEqual(manager.add(71, {71: Process(['true'])}, 'true').number, 2)

    def test_select_validates_job_id(self):
        manager = self.manager()
        job = manager.add(70, {70: Process(['sleep'])}, 'sleep')
        with patch.object(manager, 'reap'):
            self.assertIs(manager.select(), job)
            self.assertIs(manager.select('%1'), job)
            for spec in ('%0', 'bad', '%999'):
                with self.assertRaises(ValueError):
                    manager.select(spec)

    def test_signal_exit_code(self):
        manager = self.manager()
        job = manager.add(70, {70: Process(['sleep'])}, 'sleep')
        with patch('mash.jobs.os.WIFSTOPPED', return_value=False, create=True), \
             patch('mash.jobs.os.WIFCONTINUED', return_value=False, create=True), \
             patch('mash.jobs.os.waitstatus_to_exitcode', return_value=-2, create=True):
            manager.update(70, 2)
        self.assertEqual(job.status, 130)
        self.assertIn('Exited(130)', manager.events[-1])

    def test_notify_removes_finished_jobs(self):
        manager = self.manager()
        job = manager.add(70, {70: Process(['true'], code=0)}, 'true')
        with patch.object(manager, 'reap'), contextlib.redirect_stdout(io.StringIO()) as output:
            manager.notify()
        self.assertIn('Done', output.getvalue())
        self.assertNotIn(job.number, manager.jobs)

    def test_event_history_is_bounded(self):
        manager = self.manager()
        for number in range(120):
            manager.record(str(number))
        self.assertEqual(len(manager.events), 100)

    def test_reap_is_reentrant_safe(self):
        manager = self.manager()
        manager.reaping = True
        with patch('mash.jobs.os.waitpid', create=True) as wait:
            manager.reap()
        wait.assert_not_called()

    def test_reaper_does_not_steal_foreground_wait_events(self):
        manager = self.manager()
        manager.add(70, {70: Process(['sleep'])}, 'sleep')
        manager.foreground_pgid = 70
        with patch('mash.jobs.os.waitpid', create=True) as wait:
            manager.reap()
        wait.assert_not_called()

    def test_stopped_pipeline_status_when_final_stage_already_exited(self):
        job = Job(1, 70, {70: Process(['sleep'], state='Stopped'),
                         71: Process(['true'], code=0)}, 'sleep | true')
        with patch('mash.jobs.signal.SIGTSTP', 20, create=True):
            self.assertEqual(job.status, 148)

    def test_foreground_hands_over_terminal_before_releasing_children(self):
        manager = self.manager()
        manager.interactive = True
        manager.shell_modes = ['shell modes']
        job = manager.add(70, {70: Process(['true'])}, 'true')
        order = []

        def wait(*args):
            order.append('wait')
            return 70, 0

        def update(*args):
            job.processes[70].code = 0

        with patch('mash.jobs.os.tcsetpgrp', side_effect=lambda fd, group: order.append(group), create=True), \
             patch('mash.jobs.os.close', side_effect=lambda fd: order.append('release')), \
             patch('mash.jobs.os.waitpid', side_effect=wait, create=True), \
             patch.multiple('mash.jobs.os', WUNTRACED=2, WCONTINUED=8, create=True), \
             patch('mash.jobs.termios', create=True) as terminal, patch.object(manager, 'update', side_effect=update):
            self.assertEqual(manager.foreground(job, release_fd=99), 0)
            terminal.tcsetattr.assert_called_once_with(0, terminal.TCSADRAIN, ['shell modes'])
        self.assertEqual(order, [70, 'release', 'wait', 50])
        self.assertNotIn(job.number, manager.jobs)
        self.assertIsNone(manager.foreground_pgid)

    def test_terminal_is_restored_even_when_wait_fails(self):
        manager = self.manager()
        manager.interactive = True
        job = manager.add(70, {70: Process(['true'])}, 'true')
        with patch('mash.jobs.os.tcsetpgrp', create=True) as ownership, \
             patch('mash.jobs.os.waitpid', side_effect=OSError('failed'), create=True), \
             patch.multiple('mash.jobs.os', WUNTRACED=2, WCONTINUED=8, create=True), \
             patch('mash.jobs.termios', create=True) as terminal:
            with self.assertRaises(OSError):
                manager.foreground(job)
        self.assertEqual(ownership.call_args.args, (0, 50))
        terminal.tcsetattr.assert_called_once()

    def test_resume_signals_entire_group(self):
        manager = self.manager()
        job = manager.add(70, {70: Process(['sleep'], state='Stopped'),
                               71: Process(['cat'], state='Stopped')}, 'sleep | cat')
        with patch('mash.jobs.os.killpg', create=True) as kill, \
             patch('mash.jobs.signal.SIGCONT', 18, create=True):
            manager.resume(job)
        kill.assert_called_once_with(70, 18)
        self.assertEqual(job.state, 'Running')


if __name__ == '__main__':
    unittest.main()
