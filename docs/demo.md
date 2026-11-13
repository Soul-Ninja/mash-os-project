# Presentation demo

Run on Linux in a real terminal, from the repository root. Use a disposable directory for redirected output. Start with `python3 mash.py`, then `help`.

## 1. Parsing and file descriptors

```sh
printf "%s\n" "hello world" "literal | operator"
printf "warning\ninfo\nwarning\n" > demo.txt
printf "warning again\n" >> demo.txt
cat < demo.txt | grep warning | wc -l
ls /mash-no-such-path 2> errors.txt
cat errors.txt
```

Expected: quoted arguments stay intact, the pipeline prints 3, output appends correctly, and the `ls` error appears in the file. Explain the three concurrent processes, pipe endpoints, descriptor 0/1/2, and why unused pipe ends must close.

## 2. Background jobs and process observation

```sh
sleep 60 | cat &
jobs
monitor
monitor --watch
```

Expected: two tracked PIDs share one PGID. The dashboard shows real kernel states, lifetime CPU average, resident memory, pipeline membership, and observed lifecycle records. Ctrl+C leaves the watch without killing the background job.

Use the actual job number shown by `jobs`:

```sh
fg
```

Press Ctrl+Z. Run `jobs`, `bg`, and `fg`, then Ctrl+C. Explain why foreground terminal ownership matters and why one signal can reach every stage in the group.

## 3. Recovery and usability

```sh
no-such-mash-command
printf recovered
echo >
printf still-running
cd /tmp
pwd
history
```

Expected: failures report clear errors and the shell remains usable. Show arrow-up history, then type `sysin` and press Tab to complete `sysinfo`. Use `exit` once no active jobs remain.

## 4. Evidence

In the host shell, show:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/benchmark.py --runs 30 --warmups 3
```

Present actual measurements from the machine used for the demo. Explain the difference between whole-process overhead, CPU time, and wall time. Do not describe Python interpreter startup as an isolated fork/exec cost. Do not claim POSIX compliance or kernel implementation.
