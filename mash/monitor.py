"""Linux /proc snapshots; CPU is a lifetime average, not a sampled percentage."""
import os
from pathlib import Path
import platform
import shlex
import time


def process_stats(pid, proc=Path("/proc")):
    stat = (proc / str(pid) / "stat").read_text().rpartition(") ")[2].split()
    ticks = os.sysconf("SC_CLK_TCK")
    uptime = float((proc / "uptime").read_text().split()[0])
    age = max(uptime - int(stat[19]) / ticks, 0.01)
    cpu = 100 * (int(stat[11]) + int(stat[12])) / ticks / age
    memory = int(stat[21]) * os.sysconf("SC_PAGE_SIZE") / 1024**2
    return stat[0], cpu, memory


def sysinfo():
    memory = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    cpu = next((line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")), platform.machine())
    print(f"CPU: {cpu}\nKernel: {platform.system()} {platform.release()}")
    print(f"Memory total: {memory['MemTotal'].strip()}")
    print(f"Memory available: {memory.get('MemAvailable', memory['MemFree']).strip()}")


def snapshot(manager):
    manager.reap()
    print(f"MASH PROCESS DASHBOARD | shell PID {os.getpid()} | {time.strftime('%H:%M:%S')}")
    print("CPU avg% = lifetime CPU time / elapsed time; RSS = resident memory.")
    print("JOB  PGID     PID      STATE         CPU avg%  RSS MiB  COMMAND")
    for job in manager.jobs.values():
        print(f"[%{job.number}] {job.state}: {job.source}")
        for pid, process in job.processes.items():
            try:
                state, cpu, memory = process_stats(pid)
                metrics = f"{state:<13} {cpu:8.1f} {memory:8.1f}"
            except (OSError, ValueError, IndexError):
                metrics = f"{process.state:<13} {'n/a':>8} {'n/a':>8}"
            print(f"{job.number:<4} {job.pgid:<8} {pid:<8} {metrics}  {shlex.join(process.argv)}")
        print("  pipeline: " + " -> ".join(f"PID {pid}" for pid in job.processes))
    if not manager.jobs:
        print("No tracked jobs. Start one with: sleep 30 &")
    print("Recent lifecycle events (launch recorded by parent; states observed with waitpid):")
    for event in list(manager.events)[-12:]:
        print(f"  {event}")


def monitor(manager, watch=False):
    try:
        while True:
            if watch:
                print("\033[H\033[2J", end="")
            snapshot(manager)
            if not watch:
                return 0
            print("\nRefresh: 1 second. Ctrl+C returns to the shell.", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        return 130
