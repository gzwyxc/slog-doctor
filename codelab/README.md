# Codelab: Triage a QNX 8.0 Crash Loop in 10 Minutes with Slog Doctor

**Time:** ~10 minutes · **Level:** Beginner-friendly (no QNX experience assumed) ·
**You need:** a computer with Python 3.10+ — that's all. No QNX target, no
SDK, no installation.

This codelab teaches a real task *for* QNX 8.0 development: taking a raw
`slog2` system log from a misbehaving target and turning it into a
root-cause shortlist — the crash, the restart loop hiding it, and the
cascade it caused — using **Slog Doctor**, a host-side diagnostic tool.

Everything runs against sample logs bundled in this repository, so the
codelab works identically on any machine. At the end you'll also learn
how to run the exact same workflow on logs from a real QNX 8.0 target
(board or QEMU).

## What you will learn

- How QNX 8.0 systems report trouble: `slogger2`/`slog2`, slog severities,
  and the `slog2info` text export format.
- Why a process can crash for ten minutes without anyone noticing — the
  High Availability Manager (HAM) restart loop.
- How QNX native message passing fails after a server restart
  (`MsgSend` → `ESRCH`, stale connection ids), and the standard fix.
- How to read a diagnostic report like a triage nurse: findings first,
  clusters second, raw log last.
- How to confirm a fix by re-running the analysis on a post-fix log.

## The scenario

A QNX 8.0 target — think vehicle telematics unit or industrial
controller — came back from the field with a complaint: *"the dashboard
freezes for a few seconds every couple of minutes, and the network
dropped out once."* All you received is one file:
`samples/qnx-crashloop-slog2.txt`, a `slog2info` export covering
08:00–08:10 on the morning of Nov 25. Your job: find out what is wrong,
in what order it happened, and what to fix first.

---

## Step 0 — Get the tool and prove it works (1 minute)

Clone the repository and run the built-in self-checks:

```sh
git clone https://github.com/gzwyxc/slog-doctor.git
cd slog-doctor
python3 tests/run_tests.py
```

> **You should see:** `ALL 15 CHECKS PASSED`.
> Slog Doctor is pure Python 3 standard library — there is nothing to
> install, which is deliberate: triage tools must run on whatever
> machine the log lands on.

If you already have the repo, just `cd` into it; every command below is
run from the repository root.

## Step 1 — Feel the pain: the raw log (1 minute)

Look at what an engineer gets today:

```sh
wc -l samples/qnx-crashloop-slog2.txt
grep -c "SIGSEGV" samples/qnx-crashloop-slog2.txt
grep "ESRCH" samples/qnx-crashloop-slog2.txt | wc -l
```

> **You should see:** `93` lines, `4` SIGSEGV crashes, `6` ESRCH errors.

93 lines is a *kind* sample — field logs are usually 10,000+. Even here,
notice what grep can't tell you: whether the 4 crashes are one bug or
four, what the ESRCH errors have to do with them, and which of the three
noisy processes matters. Keep the numbers `4` and `6` in mind; you'll
meet them again as *findings*, with explanations attached.

A slog2 line, decoded:

```
Nov 25 08:03:26.540 qnx-target telemetryd[6010]: 1: telemetryd terminated: SIGSEGV (signal 11), fault address 0x00000000
└── timestamp ──┘ └── host ──┘ └ process[pid] ┘ └┬┘ └──────────── message ────────────┘
                                              severity
```

QNX slog severities run 0–7 (from `<sys/slog.h>`): 0 = emergency,
1 = alert, 2 = critical, 3 = error, 4 = warning, then notice/info/debug.
Slog Doctor treats the top bands (shown as CRITICAL/ERROR) as *problems*.

## Step 2 — Run Slog Doctor (1 minute)

```sh
./slogdoctor analyze samples/qnx-crashloop-slog2.txt
```

(The `./slogdoctor` wrapper just sets `PYTHONPATH`; equivalently:
`PYTHONPATH=src python3 -m slogdoctor analyze <file>`.)

> **You should see** the report header:
>
> ```
>   input: qnx-crashloop-slog2.txt  [slog2]  93 events parsed, 0 lines skipped
>   total events: 93   problems (severity <= ERROR): 15
>   window: 2026-11-25 08:00:01 .. 08:10:59
> ```
>
> and a severity distribution of **CRITICAL 4 · ERROR 11 · WARNING 26 ·
> INFO 46 · DEBUG 6**.

Triage rule #1: **start from the findings, not the log.** The tool has
already clustered repeated messages into signatures (numbers, pids and
addresses normalized away), so 15 problem events collapse into a short
ranked list. Read them top-down in the next steps.

## Step 3 — Finding #1: the restart loop (2 minutes)

```
1. [restart-loop] Restart loop: telemetryd crashed 4 times
```

`telemetryd`, the sensor service, crashed with SIGSEGV **four times** —
at 08:03:26, 08:05:31, 08:08:09 and 08:10:06 — and each time the High
Availability Manager restarted it within a second. HAM is doing its job
(keeping the service available), but it is also *hiding the bug*: from
the outside the system "mostly works", which matches the field
complaint of brief dashboard freezes.

Spot the pid changing at every restart — that detail matters in Step 4:

```sh
grep "telemetryd 2.4.1 started" samples/qnx-crashloop-slog2.txt
```

> **You should see** four starts with pids **6010 → 6112 → 6230 → 6311**
> (plus a fifth, 6405, after the last crash at 08:10:06).

Now find the *precursor*. Slog Doctor ranks by importance, but a good
triager also looks for the warning that precedes each crash:

```sh
grep -n "channel 17" samples/qnx-crashloop-slog2.txt
```

> **You should see** `Sensor channel 17 slow to respond` warnings with
> latencies of 240–310 ms — 240, 310, 285, 260, 295 ms — each one
> shortly **before** a crash, and every crash reports
> `fault address 0x00000000` (a null-pointer dereference).

**Working hypothesis:** telemetryd's channel-17 read path mishandles a
slow/timeout response and dereferences a null pointer. That is the bug
to fix first — *not* the HAM restart policy, which is only the
messenger. The report's "Next step" says exactly this.

## Step 4 — Finding #3: the ESRCH cascade (2 minutes)

```
3. [pattern] Message sent to a process that no longer exists (ESRCH) (x6)
```

This is the most QNX-specific finding in the report, so let's unpack it.

QNX is a microkernel OS: services like `telemetryd` run as ordinary
processes and clients talk to them with **native message passing** —
`MsgSend()` over a connection id (*coid*) obtained from `name_open()` /
`ConnectAttach()`. When `telemetryd` crashes and HAM restarts it, the
new process is a *different process* — but `dashd` (the dashboard)
cached the old coid and keeps sending to it. The kernel answers
**ESRCH** ("no such process"): the dashboard is talking to a ghost.

Check the timestamps against Step 3:

```sh
grep "ESRCH" samples/qnx-crashloop-slog2.txt
```

> **You should see** the 6 ESRCH errors clustered *immediately after
> restarts* (08:04, 08:06, 08:08), each naming a stale coid
> (…825, …826, …827 — a new one after every restart, because dashd
> re-attached late or partially). Between them, `dashd` logs
> `Telemetry data stale` — those are the visible dashboard freezes.

**The fix pattern** (the report's "Next step"): a client that gets ESRCH
must drop the coid and re-attach (`name_open` again) instead of caching
the connection forever. Root cause is still the crash — but this is a
real second bug: a well-behaved client degrades gracefully when a
server restarts.

## Step 5 — The HTML report and the 08:06 burst (2 minutes)

Generate the shareable report (single self-contained HTML file, plus a
JSON summary for tooling):

```sh
./slogdoctor analyze samples/qnx-crashloop-slog2.txt \
    --out report.html --json report.json
```

Open `report.html` in any browser. Walk it top-down:

1. **Summary cards** — totals, problems, window: the 10-second answer.
2. **Findings** — the same ranked list as the terminal, with the
   knowledge-base explanation and next step for each.
3. **Timeline** — events per minute with problems overlaid. One minute
   glows: **08:06, flagged as a burst** (25 events vs an 8.5/min
   average). Finding #2 points you there.
4. **Top error clusters** — the ranked signatures: ESRCH ×6, SIGSEGV ×4,
   CAM timeouts ×2…

Now the judgment call. What happened at 08:06?

```sh
grep "08:06" samples/qnx-crashloop-slog2.txt | grep "io-pkt"
```

> **You should see** `io-pkt` (QNX's networking stack) reporting
> `link down on emac0` / `link up` **seven times in 16 seconds**
> (14 link lines), finally renegotiating at **100 Mbps** instead of
> 1000 Mbps.

That's a *separate* incident — a flapping physical link (cable, PHY or
connector), which also explains the field report's "network dropped
out once" and the sensor-read timeouts in the same minute. Teaching
point: **the burst marks a cascade point, not necessarily the root
cause.** The crash loop started at 08:03, three minutes before the
burst — the network flap did not cause the crashes, and fixing the
cable will not fix telemetryd.

Don't skip finding #4 either: the `devb-eide`/CAM storage timeouts at
08:05 (×2 plus a device reset) are a watch item — if they recur on the
same device, suspect media, not software.

## Step 6 — Same workflow, kernel side: a trace (1 minute)

`slog2` is the application-level view. QNX can also record a **kernel
trace** with `tracelogger`, exported to text with `traceprinter`. Same
incident, kernel's perspective:

```sh
./slogdoctor analyze samples/qnx-kernel-trace.txt
```

> **You should see:** `[trace] 32 events parsed`, and one finding —
> `[crash] telemetryd crashed 2 time(s)` — from the cluster
> `PROCESS telemetryd DESTROYED (signal #)` ×2.

Two independent evidence sources agree: the process really was
destroyed by signal 11 twice inside the capture window. In real
investigations this cross-check is how you distinguish "the application
logged a crash" from "the kernel killed it".

## Step 7 — Verify the fix (1 minute)

Fast-forward to Nov 26. The team shipped `telemetryd 2.4.2` (channel-17
timeout path fixed) and patched `dashd` to re-attach on ESRCH. The new
morning's log is `samples/qnx-healthy-slog2.txt`:

```sh
./slogdoctor analyze samples/qnx-healthy-slog2.txt
```

> **You should see:**
>
> ```
>   total events: 35   problems (severity <= ERROR): 0
> ```
>
> **No restart-loop finding. No ESRCH finding.** Channel 17 now answers
> in ~12 ms. The only remaining finding is a "burst" at 08:00 — the
> boot minute, 10 events with **0 errors**; that's normal startup
> noise, and the report tells you the error count so you can judge
> that in one glance.

This is the workflow's closing habit: **the same command that found the
bug proves the fix.** Keep the before/after reports with the bug
ticket.

## Doing it on a real QNX 8.0 target

On the target (board or QEMU), export the system log and copy it to
your host — the analysis itself never runs on the target:

```sh
# on the QNX 8.0 target
slog2info > field-log.txt
# optional: kernel trace (run as root, stop with Ctrl-C)
tracelogger -n 1 -f trace.kev
traceprinter trace.kev > trace.txt

# on your host
./slogdoctor analyze field-log.txt --out field-report.html
./slogdoctor analyze trace.txt
```

Notes: `slog2info` column layouts vary with flags; Slog Doctor's parser
is deliberately tolerant of layout variation. Mixed exports (some
syslog-style lines) still parse via the fallback format.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python3: command not found` / version < 3.10 | Install Python 3.10+; Slog Doctor has no other dependencies. |
| `No module named slogdoctor` | Use the `./slogdoctor` wrapper, or set `PYTHONPATH=src` when calling `python3 -m slogdoctor`. |
| `./slogdoctor`: Permission denied | The executable bit was lost in a download/copy: run `chmod +x slogdoctor`, or call it as `sh slogdoctor analyze …`. |
| Format shown as `[syslog]` for a slog2 export | Your `slog2info` flags changed the layout; the analysis still runs, but check the parse counts (`lines skipped` should be low). |
| A burst finding on a healthy log | Check its error count: boot/shutdown minutes burst with 0 errors and are benign (see Step 7). |

## Summary

You triaged a field failure in about ten minutes:

1. **Root cause (fix first):** `telemetryd` null-pointer crash on the
   slow channel-17 path — proven by 4 SIGSEGVs at fault address
   `0x00000000`, each preceded by channel-17 slowness warnings.
2. **Masking factor:** HAM restarted the service 4 times, turning a
   crash into intermittent freezes.
3. **Cascade bug:** `dashd` cached a stale coid → 6 `MsgSend` ESRCH
   errors after each restart; fix is re-attach on ESRCH.
4. **Separate incident:** `io-pkt` link flapping at 08:06 (the burst) —
   physical layer, not software.
5. **Watch item:** CAM storage timeouts at 08:05.
6. **Closure:** post-fix log analyzes clean — 0 problems, findings gone.

## Self-check

1. A service crashes every few minutes but users only report
   "slowness". What QNX component is probably masking the crash, and
   what log pattern proves it?
2. A client logs `MsgSend ... ESRCH` right after its server restarts.
   What is stale, and what should the client do on ESRCH?
3. The timeline flags a burst at minute X. Why is "the root cause is
   at minute X" the wrong first conclusion?
4. Two findings remain after your fix ships: a boot-minute burst with
   0 errors, and CAM timeouts on one device. Which one do you act on,
   and why?
5. Why run the analysis on a kernel trace as well as the slog2 log?

**Answer key:** 1) HAM — repeated crash lines for the same process,
each followed within ~1 s by a HAM restart line and a new pid.
2) The connection id (coid); drop it and re-attach with `name_open` /
`ConnectAttach` instead of caching it forever.
3) A burst marks where a failure *cascaded* (or an unrelated incident
happened); here the crashes began 3 minutes before the burst.
Correlation is a starting point, not a verdict.
4) The CAM timeouts — recurring storage errors on one device point to
failing media; a 0-error boot burst is normal startup noise.
5) Independent evidence: the trace shows the kernel destroying the
process (signal 11), confirming the crash outside the application's
own logging.

## Next steps

- Run Slog Doctor on your own target's `slog2info` export and compare
  its findings with your manual read.
- Browse `src/slogdoctor/knowledge.py` — every pattern in the knowledge
  base is a small, readable entry; adding your own product's failure
  signatures is the intended way to extend the tool.
- Read the sample HTML report in `docs/sample-report.html` for the full
  report layout used in Step 5.
