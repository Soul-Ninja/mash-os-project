import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mash.jobs import JobManager, Process
from mash.monitor import process_stats, snapshot


class MonitorTests(unittest.TestCase):
    def test_proc_stat_handles_spaces_and_parentheses_in_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '42').mkdir()
            fields = ['0'] * 22
            fields[0], fields[11], fields[12], fields[19], fields[21] = 'S', '100', '100', '1000', '256'
            (root / '42' / 'stat').write_text('42 (a tricky ) name) ' + ' '.join(fields))
            (root / 'uptime').write_text('20.0 0.0')
            with patch('mash.monitor.os.sysconf', side_effect=[100, 4096], create=True):
                state, cpu, memory = process_stats(42, root)
        self.assertEqual((state, cpu, memory), ('S', 20.0, 1.0))

    def test_disappearing_process_does_not_break_dashboard(self):
        with patch('mash.jobs.os.getpgrp', return_value=50, create=True):
            manager = JobManager()
        manager.add(70, {70: Process(['sleep', '30'])}, 'sleep 30 &')
        with patch.object(manager, 'reap'), patch('mash.monitor.process_stats', side_effect=FileNotFoundError), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            snapshot(manager)
        self.assertIn('n/a', output.getvalue())
        self.assertIn('PID 70', output.getvalue())
        self.assertIn('sleep 30', output.getvalue())


if __name__ == '__main__':
    unittest.main()
