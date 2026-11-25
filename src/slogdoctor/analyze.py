"""Analysis over parsed log events: clustering, timeline, anomalies."""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from . import knowledge
from .parsers import LogEvent, SEVERITY_NAMES

_HEX = re.compile(r"0x[0-9a-fA-F]+")
_NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_WS = re.compile(r"\s+")


def signature(message: str) -> str:
    """Normalize a message into a cluster signature.

    Numbers, hex addresses and pointer-like values are replaced with
    ``#`` so that 'connection 12 failed' and 'connection 87 failed'
    cluster together.
    """
    s = _HEX.sub("#", message)
    s = _NUM.sub("#", s)
    return _WS.sub(" ", s).strip()


@dataclass
class Cluster:
    signature: str
    count: int
    sources: Counter
    severities: Counter
    first: datetime | None
    last: datetime | None
    sample: str
    rule: knowledge.Rule | None = None

    @property
    def worst_severity(self) -> int | None:
        return min(self.severities) if self.severities else None

    @property
    def problem_count(self) -> int:
        return sum(c for sev, c in self.severities.items()
                   if sev is not None and sev <= 2)


@dataclass
class Finding:
    kind: str            # 'restart-loop' | 'burst' | 'crash' | 'pattern'
    title: str
    detail: str
    rule: knowledge.Rule | None = None


@dataclass
class Analysis:
    total: int = 0
    severity_counts: Counter = field(default_factory=Counter)
    source_counts: Counter = field(default_factory=Counter)
    problem_sources: Counter = field(default_factory=Counter)
    clusters: list[Cluster] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)   # per-minute buckets
    start: datetime | None = None
    end: datetime | None = None

    @property
    def problem_total(self) -> int:
        return sum(c for sev, c in self.severity_counts.items()
                   if sev is not None and sev <= 2)


def analyze(events: list[LogEvent]) -> Analysis:
    a = Analysis(total=len(events))
    by_sig: dict[str, list[LogEvent]] = defaultdict(list)
    crashes: Counter = Counter()          # process -> crash count
    timed: list[LogEvent] = []

    for ev in events:
        if ev.severity is not None:
            a.severity_counts[ev.severity] += 1
        a.source_counts[ev.source] += 1
        if ev.is_problem:
            a.problem_sources[ev.source] += 1
        by_sig[signature(ev.message)].append(ev)
        rule = knowledge.match(ev.message)
        if rule and rule.id.startswith("crash-"):
            crashes[ev.source] += 1
        if ev.ts is not None:
            timed.append(ev)

    # --- clusters -----------------------------------------------------
    for sig, evs in by_sig.items():
        ts_list = [e.ts for e in evs if e.ts is not None]
        sample = evs[0].message
        a.clusters.append(Cluster(
            signature=sig,
            count=len(evs),
            sources=Counter(e.source for e in evs),
            severities=Counter(e.severity for e in evs
                               if e.severity is not None),
            first=min(ts_list) if ts_list else None,
            last=max(ts_list) if ts_list else None,
            sample=sample,
            rule=knowledge.match(sample),
        ))
    # Problems first, then explained patterns, then volume.
    a.clusters.sort(key=lambda c: (
        -c.problem_count,
        -(c.rule.weight if c.rule else 0),
        -c.count))

    # --- findings -----------------------------------------------------
    for proc, n in crashes.items():
        if n >= 3:
            a.findings.append(Finding(
                kind="restart-loop",
                title=f"Restart loop: {proc} crashed {n} times",
                detail=(f"{proc} crashed {n} times in this log window. "
                        "A supervisor such as the High Availability "
                        "Manager (HAM) is restarting it, but the root "
                        "cause is unfixed -- the system is running "
                        "without this service for part of every cycle."),
                rule=knowledge.match("ham restart")))
        elif n >= 1:
            a.findings.append(Finding(
                kind="crash",
                title=f"{proc} crashed {n} time(s)",
                detail=(f"{proc} terminated abnormally {n} time(s). "
                        "QNX's microkernel isolates the fault, but the "
                        "service is down until restarted."),
                rule=knowledge.match("sigsegv")))
    for c in a.clusters:
        if c.rule and c.problem_count >= 2 and c.rule.id not in (
                "crash-segv", "crash-abort"):
            a.findings.append(Finding(
                kind="pattern",
                title=f"{c.rule.title} (x{c.problem_count})",
                detail=c.rule.explanation, rule=c.rule))

    # --- timeline + burst anomalies -----------------------------------
    if timed:
        a.start = min(e.ts for e in timed)
        a.end = max(e.ts for e in timed)
        buckets: dict[datetime, list[int]] = {}
        for e in timed:
            key = e.ts.replace(second=0, microsecond=0)
            b = buckets.setdefault(key, [0, 0])
            b[0] += 1
            if e.is_problem:
                b[1] += 1
        keys = sorted(buckets)
        totals = [buckets[k][0] for k in keys]
        mean = statistics.mean(totals) if totals else 0
        stdev = statistics.pstdev(totals) if len(totals) > 1 else 0
        for k in keys:
            total, problems = buckets[k]
            burst = stdev > 0 and total > mean + 2 * stdev
            a.timeline.append({"minute": k, "total": total,
                               "problems": problems, "burst": burst})
            if burst:
                a.findings.append(Finding(
                    kind="burst",
                    title=f"Event burst at {k:%H:%M}",
                    detail=(f"{total} events in one minute vs an average "
                            f"of {mean:.1f}/min ({problems} of them "
                            "errors). Bursts like this usually mark the "
                            "moment a failure cascaded -- start the "
                            "investigation at this timestamp.")))
    a.findings.sort(key=lambda f: (
        {"restart-loop": 0, "crash": 1, "burst": 2, "pattern": 3}[f.kind]))
    return a


def severity_label(sev: int | None) -> str:
    if sev is None:
        return "—"
    return SEVERITY_NAMES.get(sev, str(sev))
