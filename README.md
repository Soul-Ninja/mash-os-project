# MASH — Micro-Architecture Shell

An educational Unix shell and process laboratory in Python. MASH launches real processes using `fork` and `execvp`, connects pipelines with `pipe`/`dup2`, and controls foreground/background process groups. Its dashboard shows owned jobs and actual process information from Linux `/proc`.

This is a deliberately limited shell, not a POSIX-compliance claim or a new operating system. The kernel owns PCBs and scheduling; MASH requests process operations through Python's OS interfaces. The previous simulated kernel boot has been removed.

## Run

Use Linux with Python **3.10+**. No third-party Python packages are required. On Windows, run inside WSL or a Linux container; native Windows has no `os.fork`.

```sh
python3 mash.py
# Equivalent entry point:
python3 -m mash
# One pipeline, with its exit status:
python3 mash.py -c 'printf "hello world\n" | wc -w'
# One pipeline per line, from standard input:
python3 mash.py < commands.txt
```

For a fresh Ubuntu/WSL environment:

```sh
sudo apt-get update
sudo apt-get install python3 bash coreutils procps
python3 -m unittest discover -s tests -v
python3 mash.py
```

`readline` supplies arrow-key history and Tab completion in interactive mode. Without it, commands still work, with a warning that those keys are unavailable. Commands such as `cat`, `grep`, `wc`, and `sleep` are programs provided by your OS.

## Try it

```sh
printf "%s\n" "hello world" "quoted | operator"
printf "one\ntwo\n" > "a file.txt"
printf "three\n" >> "a file.txt"
cat < "a file.txt" | grep three | wc -l
ls /no-such-directory 2> errors.txt
sleep 60 &
jobs
monitor
monitor --watch
fg %6
```

Use the job number printed by your own session for `fg`/`bg`; numbers count every launched pipeline, including completed foreground commands. While `sleep 60` is in the foreground, Ctrl+Z stops it, `bg` resumes it in the background, and `fg` returns it to the terminal. Ctrl+C interrupts the foreground job. Ctrl+C exits the dashboard watch and returns to the prompt.

## Supported features

- Single/double quotes, empty quoted arguments, adjacent quoted/unquoted fragments, backslash escaping, and comments starting with `#` at a word boundary.
- Concurrent multi-stage pipelines: `command | command | command`.
- Ordered file redirection: `<`, `>`, `>>`, `2>`, and `2>>`. Operators can touch words. `>` truncates existing files, as in conventional shells.
- Background pipelines with trailing `&`; one process group per pipeline.
- `jobs`, `fg [%job]`, `bg [%job]`, Ctrl+C, and Ctrl+Z. Without a job number, `fg`/`bg` select the most recently created active job.
- Parent built-ins: `cd [directory]`, `exit [--force]`, `help`, `history`, `sysinfo`, and `monitor [--watch]`, plus job commands. Built-ins can redirect files, except `fg`; they cannot be piped or backgrounded.
- Interactive arrow-key history and Tab completion for executable names and paths from unquoted prefixes. History is appended to `~/.mash_history`; set `MASH_HISTORY=/path/to/file` to change it or `MASH_HISTORY=` to disable persistence. Commands may contain sensitive arguments: do not store secrets in history. The in-memory listing keeps the last 1,000 commands; the disk log is append-only.
- A Linux dashboard with PID, PGID, kernel state, resident memory, lifetime-average CPU percentage, pipeline membership, and the last 12 lifecycle events. Up to 100 events are retained in memory. `monitor --watch` refreshes once a second.

## Process and exit behavior

The pipeline status is the last command's status. Errors use 2 for syntax/usage, 1 for redirection/OS operation failures, 126 for an executable that cannot run, and 127 for a missing executable. Signal termination reports `128 + signal number`.

Child exit/stop/continue events are reaped through `waitpid`; `SIGCHLD` also reaps background children while the prompt is idle. Status notifications print on the next prompt iteration. Closing the shell sends SIGHUP and SIGCONT to remaining owned groups, waits up to 0.5 seconds, then kills and reaps remaining direct children. `exit` refuses to close with active jobs; `exit --force` explicitly permits this cleanup. EOF and the end of a `-c` invocation also clean up jobs: background jobs are not detached services.

The dashboard records parent-side launch events and kernel wait events; it does not pretend to observe every instruction or scheduler transition. CPU avg% is total process CPU time divided by elapsed lifetime, not a one-second CPU sample. Exited or inaccessible processes show `n/a` for metrics. Only jobs launched by this MASH session are tracked.

## Scope limits

No variable or tilde expansion in ordinary arguments, glob expansion, substitutions, aliases, `;`, `&&`, `||`, here-documents, descriptor duplication (`2>&1`), arbitrary descriptor numbers, multiline grammar, or full shell scripting. `$`, `~`, `*`, and backticks are literal argument characters; `cd` without an argument still resolves the home directory. Quoted operators remain literal. Unsupported control operators produce errors before launching anything.

Script input is shared with child commands, as in a conventional shell: a command that reads stdin can consume subsequent script lines. Noninteractive background jobs receive `/dev/null` as stdin unless explicitly redirected. Completion targets unquoted prefixes; it is not a full shell-aware completion parser. The `/proc` dashboard and test suite target Linux; other Unix systems are not validated.

## Structure

```text
mash.py                 Compatibility launcher
mash/
  shell.py              CLI, history/completion, read/parse/execute loop
  parser.py             Lexer, command/pipeline model, syntax validation
  executor.py           Pipes, descriptors, fork/exec, partial-launch cleanup
  jobs.py               Process groups, terminal ownership, waitpid events
  builtins.py           Parent-side built-ins
  monitor.py            Linux process metrics and dashboard
scripts/benchmark.py    MASH/Bash comparison with raw JSON samples
tests/                  Unit, Unix integration, and pseudo-terminal tests
docs/                   Architecture, demo, and evaluation notes
.github/workflows/      Linux test and benchmark workflow
```

## Validate and evaluate

```sh
python3 -m unittest discover -s tests -v
python3 scripts/benchmark.py --runs 30 --warmups 3
```

The benchmark reports whole-process median and p95 times for startup, one external command, and a pipeline, comparing MASH with Bash without startup files. It saves raw samples and environment metadata to `benchmark-results.json`. This includes Python interpreter startup and is not an isolated syscall or command-launch measurement. Bash's `printf` is a built-in; MASH launches the external program, so the pipeline comparison measures that implementation difference too.

See [architecture](docs/architecture.md), [presentation demo](docs/demo.md), and [validation and evaluation](docs/evaluation.md). The checked-in GitHub Actions workflow runs the real Unix and terminal tests on Linux when pushed or manually dispatched; adding a workflow does not mean CI has already run.
