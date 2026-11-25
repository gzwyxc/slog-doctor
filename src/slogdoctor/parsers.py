"""Parsers for QNX 8.0 log/trace text exports.

Supported input formats (auto-detected per file):

* ``slog2``  -- text output of QNX's ``slog2info`` utility, e.g.::

      Nov 25 08:00:01.123 qnx-target procnto[1]: 5: System startup complete

  The canonical slog2info line carries a timestamp with milliseconds, the
  host name, the emitting process (optionally with ``[pid]``), a numeric
  severity (0-7) and the message.  Column layouts vary with slog2info
  flags, so extraction is regex-based and tolerant: the process and
  severity fields are optional.

* ``trace``  -- text output of QNX's ``traceprinter`` utility over a
  kernel trace (``tracelogger`` .kev file), e.g.::

      0.000123456  0  THREAD          1/2  RUNNING

  Header lines (TRACEPRINTER/TRACEPARSER banners, column titles) are
  skipped; event rows carry a seconds-with-nanoseconds timestamp, a CPU
  id, an event class, an owner (pid/tid) and event data.

* ``syslog`` -- generic syslog-style fallback so the tool still does
  something useful on plain ``slogger``/syslog text.

All parsers normalize to :class:`LogEvent`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# QNX slog severity levels (from <sys/slog.h>): lower is worse.
SEVERITY_NAMES = {
    0: "SHUTDOWN",
    1: "CRITICAL",
    2: "ERROR",
    3: "WARNING",
    4: "NOTICE",
    5: "INFO",
    6: "DEBUG",
    7: "DEBUG2",
}

# Severities we count as "problems" for error-rate / burst analysis.
PROBLEM_SEVERITIES = {0, 1, 2}


@dataclass
class LogEvent:
    ts: datetime | None          # wall-clock time when known
    rel_ts: float | None         # seconds since trace start (trace format)
    host: str
    source: str                  # process / event class that emitted the line
    pid: int | None
    severity: int | None         # slog severity 0-7, None when unknown
    message: str
    raw: str
    fmt: str                     # 'slog2' | 'trace' | 'syslog'
    line_no: int = 0

    @property
    def severity_name(self) -> str:
        if self.severity is None:
            return "—"
        return SEVERITY_NAMES.get(self.severity, str(self.severity))

    @property
    def is_problem(self) -> bool:
        return self.severity in PROBLEM_SEVERITIES


_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

_TS = r"(?P<mon>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+" \
      r"(?P<h>\d{2}):(?P<mi>\d{2}):(?P<s>\d{2})(?:\.(?P<ms>\d{1,6}))?"

_SLOG2_RE = re.compile(
    r"^" + _TS + r"\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<src>[A-Za-z0-9_.\-/]+)(?:\[(?P<pid>\d+)\])?:\s*"
    r"(?:(?P<sev>[0-7])\s*:\s*)?"
    r"(?P<msg>.*)$"
)

_SYSLOG_RE = re.compile(
    r"^" + _TS + r"\s+(?P<host>\S+)\s+(?P<msg>.*)$"
)

_TRACE_RE = re.compile(
    r"^\s*(?P<rel>\d+\.\d+)\s+(?P<cpu>\d+)\s+"
    r"(?P<cls>[A-Z][A-Z_ ]*?)\s{2,}(?P<owner>\S+)\s*(?P<data>.*)$"
)

_TRACE_SKIP = ("TRACEPRINTER", "TRACEPARSER", "HEADER FILE", "TRACE FILE",
               "TRACE DATE", "TRACE KERNEL", "TIMESTAMP", "---")


def _make_ts(m: re.Match, year: int) -> datetime | None:
    try:
        ms = (m.group("ms") or "0").ljust(6, "0")[:6]
        return datetime(year, _MONTHS[m.group("mon")], int(m.group("day")),
                        int(m.group("h")), int(m.group("mi")),
                        int(m.group("s")), int(ms))
    except (KeyError, ValueError):
        return None


def parse_slog2_line(line: str, year: int, line_no: int) -> LogEvent | None:
    m = _SLOG2_RE.match(line)
    if not m:
        return None
    sev = m.group("sev")
    return LogEvent(
        ts=_make_ts(m, year), rel_ts=None, host=m.group("host"),
        source=m.group("src"),
        pid=int(m.group("pid")) if m.group("pid") else None,
        severity=int(sev) if sev is not None else None,
        message=m.group("msg").strip(), raw=line, fmt="slog2",
        line_no=line_no)


def parse_trace_line(line: str, line_no: int) -> LogEvent | None:
    if any(line.lstrip().startswith(s) for s in _TRACE_SKIP):
        return None
    m = _TRACE_RE.match(line)
    if not m:
        return None
    cls = m.group("cls").strip()
    data = m.group("data").strip()
    # Kernel-trace event classes of diagnostic interest get a severity so
    # they flow into the same clustering / problem analysis as log lines.
    sev = None
    upper = (cls + " " + data).upper()
    if "DIE" in upper or "DESTROY" in upper and "PROCESS" in upper:
        sev = 2
    owner = m.group("owner")
    pid = None
    pm = re.match(r"(\d+)", owner)
    if pm:
        pid = int(pm.group(1))
    source = cls
    if cls == "PROCESS":
        # Name the process, not the event class: data looks like
        # "CREATE telemetryd pid 6010" or "telemetryd DESTROYED ...".
        nm = re.search(r"(?:CREATE\s+)?([A-Za-z][\w.\-]*)\s+"
                       r"(?:pid\s+\d+|DESTROYED)", data)
        if nm:
            source = nm.group(1)
    return LogEvent(
        ts=None, rel_ts=float(m.group("rel")), host="(trace)",
        source=source, pid=pid, severity=sev,
        message=(cls + " " + data).strip(), raw=line, fmt="trace",
        line_no=line_no)


def parse_syslog_line(line: str, year: int, line_no: int) -> LogEvent | None:
    m = _SYSLOG_RE.match(line)
    if not m:
        return None
    return LogEvent(
        ts=_make_ts(m, year), rel_ts=None, host=m.group("host"),
        source="(syslog)", pid=None, severity=None,
        message=m.group("msg").strip(), raw=line, fmt="syslog",
        line_no=line_no)


def detect_format(lines: list[str]) -> str:
    """Sniff the format of a file from its first recognizable lines."""
    slog = trace = 0
    for line in lines[:200]:
        if parse_trace_line(line, 0):
            trace += 1
        elif _SLOG2_RE.match(line):
            slog += 1
        if slog >= 3 or trace >= 3:
            break
    if trace > slog:
        return "trace"
    if slog:
        return "slog2"
    return "syslog"


def parse_text(text: str, fmt: str = "auto",
               year: int = 2026) -> tuple[list[LogEvent], dict]:
    """Parse a whole file's text. Returns (events, stats)."""
    lines = text.splitlines()
    if fmt == "auto":
        fmt = detect_format(lines)
    parser = {"slog2": lambda ln, n: parse_slog2_line(ln, year, n),
              "trace": lambda ln, n: parse_trace_line(ln, n),
              "syslog": lambda ln, n: parse_syslog_line(ln, year, n)}[fmt]
    events: list[LogEvent] = []
    skipped = 0
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        ev = parser(line, n)
        if ev is None:
            skipped += 1
        else:
            events.append(ev)
    return events, {"format": fmt, "lines": len(lines),
                    "parsed": len(events), "skipped": skipped}
