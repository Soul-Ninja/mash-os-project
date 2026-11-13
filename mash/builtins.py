"""Built-ins run in the parent so directory and job changes persist."""
import os

from .monitor import monitor, sysinfo

NAMES = {"cd", "exit", "help", "history", "jobs", "fg", "bg", "sysinfo", "monitor"}


def run(command, shell):
    name, *args = command.argv
    if name == "cd":
        if len(args) > 1:
            raise ValueError("usage: cd [directory]")
        os.chdir(args[0] if args else os.path.expanduser("~"))
    elif name == "exit":
        if args not in ([], ["--force"]):
            raise ValueError("usage: exit [--force]")
        shell.manager.reap()
        if args != ["--force"] and any(job.state != "Done" for job in shell.manager.jobs.values()):
            raise ValueError("active jobs remain; use fg/bg, or exit --force to terminate them")
        shell.exiting = True
        return shell.status
    elif name in ("fg", "bg"):
        if len(args) > 1:
            raise ValueError(f"usage: {name} [%job]")
        if name == "fg" and command.redirects:
            raise ValueError("fg cannot be redirected: it requires the shell terminal")
        job = shell.manager.select(args[0] if args else None)
        if name == "fg":
            return shell.manager.foreground(job, resume=True)
        shell.manager.resume(job)
        print(f"[{job.number}] Running\t{job.source}")
    elif name == "monitor":
        if args not in ([], ["--watch"]):
            raise ValueError("usage: monitor [--watch]")
        if args and (not shell.interactive or command.redirects):
            raise ValueError("monitor --watch requires an interactive, unredirected terminal")
        return monitor(shell.manager, watch=bool(args))
    else:
        if args:
            raise ValueError(f"{name} does not accept arguments")
        if name == "sysinfo":
            sysinfo()
        elif name == "history":
            for number, line in enumerate(shell.history, 1):
                print(f"{number:5}  {line}")
        elif name == "jobs":
            shell.manager.reap()
            for job in shell.manager.jobs.values():
                print(f"[{job.number}] {job.state}\tPGID {job.pgid}\t{job.source}")
        elif name == "help":
            print("MASH: Unix shell with pipelines and job control\n"
                  "Built-ins: cd [dir], exit [--force], help, history, jobs,\n"
                  "          fg [%job], bg [%job], sysinfo, monitor [--watch]\n"
                  "Syntax: command [args] [< file] [> file] [>> file] [2> file]\n"
                  "        command | command [&]  (also supports 2>>)\n"
                  "Quotes and backslash escapes preserve arguments.\n"
                  "Ctrl+C interrupts foreground jobs; Ctrl+Z suspends them.\n"
                  "Built-ins must be standalone foreground commands.\n"
                  "No variable/glob expansion, command substitution, ;, &&, or ||.")
    return 0
