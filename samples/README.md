# Sample fixtures

Synthetic but format-faithful exports, written to the documented output
formats of QNX 8.0's `slog2info` and `traceprinter` utilities. Each file
tells a failure story so you can see what Slog Doctor extracts.

## `qnx-crashloop-slog2.txt` — slog2info export, 10 minutes of a bad morning

Story: the target boots cleanly at 08:00. A sensor process,
`telemetryd`, starts faulting on channel 17, then crashes with SIGSEGV.
The High Availability Manager (HAM) restarts it — four times. Between
crashes, the dashboard process `dashd` keeps a stale connection id and
spams `MsgSend ... ESRCH` errors. At 08:05 the disk stack (`devb-eide` /
CAM) reports command timeouts, and at 08:06 the network link flaps for a
minute, producing an event burst.

Expected analysis: a **restart-loop finding** for telemetryd (4 crashes),
an **ESRCH pattern finding**, a **storage-error finding**, and a
**burst flagged at 08:06**.

## `qnx-kernel-trace.txt` — traceprinter export of a kernel trace

Story: the same incident seen from the kernel side — process/thread
scheduling, message sends, and `telemetryd` being destroyed (signal 11)
and recreated twice inside the capture window.

## `qnx-healthy-slog2.txt` — slog2info export, the morning after the fix

Story: same system, next day. `telemetryd 2.4.2` (channel-17 timeout
path fixed) runs clean, channel 17 answers in ~12 ms, `dashd` behaves,
the link is stable. Expected analysis: **0 problems**, no restart-loop
or ESRCH findings — the "verify the fix" counterpart to the crash-loop
log, used in the codelab's final step.

Run any of them with:

```sh
./slogdoctor analyze samples/qnx-crashloop-slog2.txt --out report.html
./slogdoctor analyze samples/qnx-kernel-trace.txt
./slogdoctor analyze samples/qnx-healthy-slog2.txt
```
