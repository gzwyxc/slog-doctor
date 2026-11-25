# Slog Doctor

**A host-side diagnostic tool for QNX 8.0 system logs and kernel traces.**

Your QNX target in the field crashed at 3 a.m. All you got back is a
10,000-line `slog2` dump. Slog Doctor reads that dump (and kernel traces)
on your development host and tells you, in plain language:

* **what crashed** — and whether a supervisor (HAM) is hiding a restart loop,
* **what cascaded** — e.g. clients failing with `ESRCH` because they kept
  sending messages to a process that no longer exists,
* **when it happened** — a per-minute timeline with error bursts flagged,
* **what to do next** — every finding comes with a concrete suggested action.

No agent on the target. No cloud upload. One Python file set, standard
library only.

## Why this exists

QNX 8.0 powers cars, medical devices, robots and industrial controllers —
systems you usually *cannot* attach a debugger to once they ship. When a
field unit misbehaves, the evidence is a log file. Triage today means an
expert greps slog2 output by hand and holds the QNX failure patterns
(resource-manager errors, message-passing failures, HAM restarts,
`io-pkt` link flaps, `devb-*` storage errors) in their head. Slog Doctor
encodes that expertise into a knowledge base and applies it in seconds.

## Quick start

Requirements: Python 3.10+ (standard library only — nothing to install).
Slog Doctor is a **host-based tool**: it runs on Linux, macOS or Windows
and analyzes artifacts produced on a **QNX 8.0** target (including QEMU).

```sh
# Analyze the bundled sample: a QNX 8.0 boot log with a crash loop in it
PYTHONPATH=src python3 -m slogdoctor analyze samples/qnx-crashloop-slog2.txt \
    --out report.html --json report.json

# Or use the wrapper
./slogdoctor analyze samples/qnx-kernel-trace.txt
```

Open `report.html` in any browser — it is a single self-contained file
(inline CSS/SVG, works offline).

## Inputs

| Format | Produced by | Notes |
|---|---|---|
| `slog2` | `slog2info` text export from a QNX 8.0 target | Auto-detected. Severities 0–7 per `<sys/slog.h>`. |
| `trace` | `traceprinter` text export of a `tracelogger` `.kev` capture | Process/thread/kernel-call events, normalized into the same pipeline. |
| `syslog` | generic syslog-style text | Fallback so mixed exports still parse. |

On the target, produce an export with e.g. `slog2info > system-log.txt`
or `traceprinter trace.kev > trace.txt`, copy it to your host, analyze.

## What the analysis does

1. **Clustering** — messages are normalized (numbers, hex addresses, pids
   stripped) into signatures and ranked, so 400 repeats of one fault are
   one row, not 400 lines.
2. **QNX knowledge base** — patterns map to explanations and next steps:
   SIGSEGV/SIGABRT crashes, HAM restart loops, `MsgSend` → `ESRCH`
   (message sent to a dead process), resource-manager errors, watchdog
   events, CAM/`devb-*` storage errors, `io-pkt` link flapping, ENOSPC,
   allocation failures, deadline misses.
3. **Restart-loop detection** — the same process crashing ≥ 3 times is
   called out as its own finding: the supervisor is masking a bug.
4. **Timeline + burst detection** — events per minute with problem
   overlay; minutes above mean + 2σ are flagged as cascade points.

## Repository layout

```
src/slogdoctor/   the tool (parsers, analysis, knowledge base, reports)
samples/          realistic QNX 8.0 log/trace fixtures with a failure story
tests/            self-checks:  python3 tests/run_tests.py
codelab/          step-by-step tutorial: triage a QNX crash loop with Slog Doctor
docs/             sample report + test-run log (proof the tool works)
PLAN.md           design notes and hackathon submission checklist
```

## QNX connection

Slog Doctor targets **QNX 8.0 (QNX Everywhere)** development workflows:
its parsers implement the `slog2info` and `traceprinter` text formats,
its severity model is QNX's slog severity scale, and its knowledge base
is written specifically for QNX's microkernel architecture — native
message passing, resource managers, the High Availability Manager,
`procnto`, `io-pkt` and `devb-*` drivers.

## License

MIT — see [LICENSE](LICENSE).
