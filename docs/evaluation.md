# Validation and evaluation

## What is automated

| Area | Evidence |
|---|---|
| Lexer/parser | Quotes, escapes, empty arguments, literal operators, comments, malformed syntax, redirection ordering |
| Descriptor management | Target descriptors, append/truncate flags, restoration after built-in failures, pipeline allocation/partial-fork cleanup |
| Job model | Pipeline state aggregation, statuses, job selection, event bounds, notification cleanup |
| Monitoring | Fixture-based Linux stat parsing, CPU/RSS calculation, disappearing processes |
| Built-ins | Persistent directory changes, invalid arguments, safe exit, rejected pipeline/background usage |
| Real Unix execution | Concurrent/large pipelines, early reader exit, redirection, command errors, background/foreground jobs, descriptor leak checks |
| Pseudo-terminal behavior | Ctrl+C, Ctrl+Z, bg/fg, foreground readers, dashboard cancellation, idle child reaping, history and completion keys |
| Benchmark statistics | Known median and nearest-rank p95 fixture |

Run `python3 -m unittest discover -s tests -v`. Unix integration and pseudo-terminal tests skip on native Windows, so a green Windows result alone does not validate Unix process behavior. Linux tests expect standard coreutils programs, `/proc`, a usable PTY, and Python with GNU readline for the keyboard test. CI uses Ubuntu with Python 3.10 and 3.12.

Tests isolate redirected files and interactive history in temporary directories. Real-process tests have timeouts. The forced-exit test checks that a known direct child no longer exists; the repeated-pipeline test checks the shell's own `/proc/self/fd` count. Mocked failure tests deliberately make fork or pipe allocation fail.

## Local validation status

The implementation was prepared on native Windows, without WSL or Docker available. Cross-platform unit tests and syntax checks can run here; Linux-only execution and terminal tests cannot. Their skipped status is a validation gap, not evidence that those behaviors passed. The Linux workflow is supplied but has not been dispatched from this checkout. Run the full suite on Linux before treating job control as validated for submission.

On 2026-11-13, 40 unit tests passed locally and 22 Unix integration/terminal tests were skipped (62 discovered). Syntax compilation and `git diff --check` also passed. The local sandbox's temporary-directory restriction required setting Python's test temporary directory to the repository; tests still cleaned up their own temporary files.

No performance numbers are claimed in this document. The benchmark must be run on the target Linux environment before writing conclusions.

## Performance study

```sh
python3 scripts/benchmark.py --runs 30 --warmups 3 --output benchmark-results.json
```

Three workloads are measured:

1. Startup: create the shell and execute its `exit` built-in.
2. External command: create the shell and execute `/bin/true`.
3. Pipeline: create the shell and execute `printf 'one\ntwo\n' | wc -l`.

Each measurement includes the complete runner process, pipe capture, and exit. MASH includes Python interpreter/import overhead. Bash is launched with `--noprofile --norc`, and `BASH_ENV`/`ENV` are removed from the measurement environment. The pipeline uses Bash's built-in `printf` versus MASH's external `printf`, so it is an implementation comparison, not equivalent process counts. Both runners receive the same workload; execution order is interleaved using a fixed random seed. Warmups are discarded. Raw sample milliseconds, median, nearest-rank p95, minimum, timestamp, Python/Bash versions, platform, and logical CPU count are saved as JSON.

Record CPU model, memory, distribution/kernel, power mode, VM/container/WSL status, and background load alongside results. Run on the same machine and environment, avoid interpreting a warm-cache experiment as cold startup, and repeat experiments if contention changes. For cold-cache results or syscall attribution, design a separate experiment rather than changing the meaning of these measurements.

Suggested report table (fill from measured JSON):

| Workload | MASH median/p95 ms | Bash median/p95 ms | Explanation |
|---|---|---|---|
| Startup | pending | pending | Interpreter/import and initialization cost |
| External command | pending | pending | Startup plus one command and waiting |
| Pipeline | pending | pending | Pipes, process count, launch and synchronization |

## Submission checklist

- Run all tests on the Linux presentation machine; investigate skips and failures.
- Attach benchmark JSON and the machine/environment details; report limitations honestly.
- Include the architecture diagram, supported grammar, state model, and process launch protocol.
- Demonstrate terminal job control and dashboard lifecycle events live.
- Explain why Python was chosen and which OS mechanisms the application coordinates.
- Distinguish implemented functionality from full shell/POSIX compatibility.
