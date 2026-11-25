"""QNX-specific diagnostic knowledge base.

Each rule maps a log pattern to a plain-language explanation of what is
happening on the QNX system and a concrete suggested next step.  This is
the part of Slog Doctor that a generic log tool cannot do: the patterns
are the failure modes of QNX's microkernel architecture -- native
message passing, resource managers, the High Availability Manager (HAM),
``procnto``, ``io-pkt`` networking and ``devb-*`` storage drivers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Rule:
    id: str
    title: str
    pattern: re.Pattern
    explanation: str
    action: str
    weight: int          # higher = more diagnostically important


def _r(id_, title, pat, expl, act, weight):
    return Rule(id_, title, re.compile(pat, re.IGNORECASE), expl, act, weight)


RULES: list[Rule] = [
    _r("crash-segv", "Process crashed with a segmentation fault",
       r"sigsegv|segmentation fault|signal 11\b",
       "A process tried to access memory it does not own and the kernel "
       "killed it. On QNX this is a bug in that process (bad pointer, "
       "use-after-free, stack corruption) -- the microkernel and other "
       "processes are unaffected, which is exactly the fault isolation "
       "QNX is designed for.",
       "Get a core dump (dumper) for the process and open it in the "
       "debugger; check the faulting address and the last release's "
       "changes in that component.",
       100),
    _r("crash-abort", "Process aborted (SIGABRT)",
       r"sigabrt|signal 6\b|abort\(\)",
       "The process called abort(), usually because an assertion failed "
       "or the C library detected heap corruption. The message just "
       "before the abort usually names the failed check.",
       "Read the log lines immediately before the abort from the same "
       "process; fix the failed assertion or the heap corruption it "
       "detected, and capture a core dump.",
       95),
    _r("ham-restart", "HAM restarted a failed process",
       r"\bham\b.*(restart|recover|died)|restarting .* (process|service)",
       "The High Availability Manager noticed a process died (its "
       "heartbeat/entity condition fired) and restarted it, as "
       "configured. One restart is HA working as designed; repeated "
       "restarts of the same process mean the underlying fault is "
       "still present and HAM is masking it.",
       "Treat the *first* crash of the process as the real bug and fix "
       "that crash; do not just tune the supervisor's restart policy -- "
       "that only hides the fault.",
       90),
    _r("msgsend-esrch", "Message sent to a process that no longer exists (ESRCH)",
       r"msgsend.*esrch|esrch.*msgsend|no such process",
       "In QNX native message passing, MsgSend() returned ESRCH: the "
       "destination process (or its channel) was gone when the client "
       "tried to send. Typically the server crashed or restarted and "
       "the client kept a stale connection id (coid).",
       "Check whether the destination process crashed just before "
       "these errors (look for a crash cluster at the same timestamp). "
       "Clients should re-attach (name_open/ConnectAttach) when a "
       "server restarts instead of caching the coid forever.",
       85),
    _r("resmgr-error", "Resource manager reported an error",
       r"resmgr|resource manager",
       "A resource manager (QNX's pluggable server that owns a "
       "pathname-space resource such as /dev/... ) reported a problem. "
       "Because most QNX drivers and services are resource managers, "
       "this often means a driver-level fault rather than an "
       "application bug.",
       "Identify which resource manager emitted the line and check "
       "its device (disk, serial, network) for hardware errors around "
       "the same time.",
       70),
    _r("watchdog", "Watchdog timeout / system inactivity",
       r"watchdog",
       "The watchdog was not kicked in time, or a watchdog event "
       "fired. On a real-time system this usually means a high-priority "
       "thread starved the kicker, a driver blocked with interrupts "
       "off, or the system genuinely hung.",
       "Look for a CPU-hogging thread or a blocked driver in the "
       "minutes before the timeout; check priorities of the watchdog "
       "kicker thread against the real-time workload.",
       90),
    _r("storage-cam", "Storage (CAM/devb) error",
       r"\bdevb|cam .* (error|timeout|reset)|scsi.*error|ata.*error",
       "The block driver stack (devb-* / CAM) reported a storage "
       "error: command timeouts, resets or media errors. Repeated "
       "errors point at failing media or a cabling/power problem "
       "rather than software.",
       "Check the same device for escalating error counts, run the "
       "drive's SMART/health check, and plan media replacement if "
       "errors cluster on one device.",
       80),
    _r("enospc", "Filesystem out of space (ENOSPC)",
       r"enospc|no space left",
       "A write failed because the filesystem is full. On embedded "
       "QNX targets this is frequently log files (slog2 buffers are "
       "RAM-backed, but persistent logs are not) or core dumps "
       "filling a small flash partition.",
       "Find the largest consumers on the partition (cores in "
       "/var/dumps are the usual suspect) and add rotation/quotas.",
       75),
    _r("iopkt-link", "Network link state change (io-pkt)",
       r"io-pkt|link (is )?(down|up)|media .* (down|up)|nic .*down",
       "The io-pkt networking stack reported a link change. A single "
       "down/up pair is a cable or switch event; flapping (many pairs "
       "per minute) breaks TCP sessions and makes network services "
       "look randomly broken.",
       "If the link flaps, check the physical layer first (cable, "
       "switch port, PHY negotiation) before debugging applications.",
       60),
    _r("oom", "Memory allocation failure",
       r"out of memory|malloc.*fail|cannot allocate|enomem",
       "A process could not allocate memory. On QNX, check whether one "
       "process is leaking (its heap grows in pidin mem output) or the "
       "target is simply undersized for the workload.",
       "Watch the suspect process's memory over time; a steady climb "
       "is a leak, a step jump is a legitimate peak that needs a "
       "bigger budget.",
       80),
    _r("priority-inversion", "Possible priority inversion / deadline miss",
       r"deadline (miss|overrun)|priority inversion|latency.*exceed",
       "A real-time deadline was missed. QNX's priority-inheritance "
       "in message passing prevents classic unbounded inversion, so a "
       "miss usually means overload or a lower-priority thread holding "
       "a shared resource too long.",
       "Use a kernel trace (tracelogger) around the miss and look at "
       "the scheduling of the involved threads; check for long "
       "critical sections in shared resource managers.",
       65),
]


def match(message: str) -> Rule | None:
    """Return the highest-weight knowledge rule matching a message."""
    best = None
    for rule in RULES:
        if rule.pattern.search(message):
            if best is None or rule.weight > best.weight:
                best = rule
    return best
