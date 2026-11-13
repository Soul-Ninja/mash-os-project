"""Track only children owned by this shell; waitpid is the event source."""
from collections import deque
from dataclasses import dataclass
import contextlib
import os
import signal
import time

if os.name == "posix":
    import termios


@dataclass
class Process:
    argv: list[str]
    state: str = "Running"
    code: int | None = None


@dataclass
class Job:
    number: int
    pgid: int
    processes: dict[int, Process]
    source: str
    modes: list | None = None
    reported: str = "Running"

    @property
    def state(self):
        live = [p for p in self.processes.values() if p.code is None]
        if not live:
            return "Done"
        return "Stopped" if all(p.state == "Stopped" for p in live) else "Running"

    @property
    def status(self):
        if self.state == "Stopped":
            return 128 + signal.SIGTSTP
        code = list(self.processes.values())[-1].code
        return code if code is not None else 128 + signal.SIGTSTP


class JobManager:
    def __init__(self, interactive=False):
        self.interactive = interactive
        self.jobs = {}
        self.events = deque(maxlen=100)
        self.next_number = 1
        self.shell_pgid = os.getpgrp()
        self.shell_modes = None
        self.old_signals = {}
        self.reaping = False
        self.reap_pending = False
        self.foreground_pgid = None
        if interactive:
            while os.tcgetpgrp(0) != os.getpgrp():
                os.killpg(os.getpgrp(), signal.SIGTTIN)
            for sig in (signal.SIGTTOU, signal.SIGTTIN, signal.SIGTSTP):
                self.old_signals[sig] = signal.signal(sig, signal.SIG_IGN)
            if os.getpgrp() != os.getpid():
                os.setpgid(0, 0)
            self.shell_pgid = os.getpgrp()
            os.tcsetpgrp(0, self.shell_pgid)
            self.shell_modes = termios.tcgetattr(0)

    def record(self, text):
        self.events.append(f"{time.strftime('%H:%M:%S')} {text}")

    def add(self, pgid, processes, source):
        job = Job(self.next_number, pgid, processes, source)
        self.jobs[job.number] = job
        self.next_number += 1
        for pid in processes:
            self.record(f"job %{job.number}: launched PID {pid}, PGID {pgid}")
        return job

    def update(self, pid, status):
        for job in self.jobs.values():
            if pid not in job.processes:
                continue
            process = job.processes[pid]
            if os.WIFSTOPPED(status):
                process.state = "Stopped"
            elif os.WIFCONTINUED(status):
                process.state = "Running"
            else:
                process.code = os.waitstatus_to_exitcode(status)
                if process.code < 0:
                    process.code = 128 - process.code
                process.state = f"Exited({process.code})"
            self.record(f"PID {pid}: {process.state}")
            return

    def reap(self):
        if self.reaping:
            self.reap_pending = True
            return
        self.reaping = True
        try:
            while True:
                self.reap_pending = False
                for job in list(self.jobs.values()):
                    if job.pgid == self.foreground_pgid:
                        continue
                    for pid, process in job.processes.items():
                        while process.code is None:
                            try:
                                observed, status = os.waitpid(pid, os.WNOHANG | os.WUNTRACED | os.WCONTINUED)
                            except ChildProcessError:
                                break
                            if observed == 0:
                                break
                            self.update(observed, status)
                if not self.reap_pending:
                    break
        finally:
            self.reaping = False

    def notify(self):
        self.reap()
        for number, job in list(self.jobs.items()):
            if job.state != job.reported:
                print(f"[{number}] {job.state}\t{job.source}")
                job.reported = job.state
            if job.state == "Done":
                del self.jobs[number]

    def select(self, spec=None):
        self.reap()
        active = {n: job for n, job in self.jobs.items() if job.state != "Done"}
        if spec is None and active:
            return active[max(active)]
        try:
            return active[int(spec.removeprefix("%"))]
        except (ValueError, KeyError, AttributeError):
            raise ValueError("no such active job") from None

    def resume(self, job):
        os.killpg(job.pgid, signal.SIGCONT)
        for process in job.processes.values():
            if process.code is None:
                process.state = "Running"
        job.reported = "Running"
        self.record(f"job %{job.number}: sent SIGCONT")

    def foreground(self, job, resume=False, release_fd=None):
        self.foreground_pgid = job.pgid
        try:
            if self.interactive:
                os.tcsetpgrp(0, job.pgid)
                if job.modes:
                    termios.tcsetattr(0, termios.TCSADRAIN, job.modes)
            if release_fd is not None:
                os.close(release_fd)
                release_fd = None
            if resume:
                self.resume(job)
            while job.state == "Running":
                try:
                    pid, status = os.waitpid(-job.pgid, os.WUNTRACED | os.WCONTINUED)
                    self.update(pid, status)
                except KeyboardInterrupt:
                    # Noninteractive callers have no terminal to deliver SIGINT to the job.
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(job.pgid, signal.SIGINT)
                except ChildProcessError:
                    # A job may have completed between selection and terminal handoff.
                    if job.state == "Running":
                        raise
                    break
        finally:
            self.foreground_pgid = None
            if release_fd is not None:
                os.close(release_fd)
            if self.interactive:
                try:
                    if job.state == "Stopped":
                        job.modes = termios.tcgetattr(0)
                finally:
                    os.tcsetpgrp(0, self.shell_pgid)
                    termios.tcsetattr(0, termios.TCSADRAIN, self.shell_modes)
        if job.state == "Done":
            self.jobs.pop(job.number, None)
        else:
            print(f"[{job.number}] Stopped\t{job.source}")
            job.reported = "Stopped"
        return job.status

    def close(self):
        self.reap()
        active = [job for job in self.jobs.values() if job.state != "Done"]
        for job in active:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(job.pgid, signal.SIGHUP)
                os.killpg(job.pgid, signal.SIGCONT)
        deadline = time.monotonic() + 0.5
        while active and time.monotonic() < deadline:
            self.reap()
            active = [job for job in active if job.state != "Done"]
            if active:
                time.sleep(0.01)
        for job in active:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(job.pgid, signal.SIGKILL)
            for pid, process in job.processes.items():
                if process.code is None:
                    with contextlib.suppress(ChildProcessError):
                        os.waitpid(pid, 0)
        for sig, handler in self.old_signals.items():
            signal.signal(sig, handler)
