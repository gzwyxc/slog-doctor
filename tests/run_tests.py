#!/usr/bin/env python3
"""Slog Doctor self-checks (standard library only).

Run:  python3 tests/run_tests.py
Exits non-zero on the first failing check.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from slogdoctor import analyze as az          # noqa: E402
from slogdoctor import parsers                # noqa: E402

PASSED = []


def check(name, cond, detail=""):
    if not cond:
        print(f"FAIL: {name} {detail}")
        raise SystemExit(1)
    PASSED.append(name)
    print(f"ok:   {name}")


def load(name):
    with open(os.path.join(ROOT, "samples", name), encoding="utf-8") as fh:
        return fh.read()


def main():
    # --- slog2 fixture -------------------------------------------------
    events, stats = parsers.parse_text(load("qnx-crashloop-slog2.txt"))
    check("slog2 format auto-detected", stats["format"] == "slog2", stats)
    check("slog2 fixture parses >= 90 events", stats["parsed"] >= 90, stats)
    check("slog2 fixture skips 0 lines", stats["skipped"] == 0, stats)

    a = az.analyze(events)
    check("analysis sees >= 14 problem events", a.problem_total >= 14,
          a.problem_total)
    kinds = {f.kind for f in a.findings}
    check("restart-loop finding present", "restart-loop" in kinds, kinds)
    check("burst finding present", "burst" in kinds, kinds)
    titles = " | ".join(f.title for f in a.findings)
    check("ESRCH pattern finding present", "ESRCH" in titles, titles)
    check("storage pattern finding present",
          "storage" in titles.lower() or "CAM" in titles, titles)
    bursts = [t for t in a.timeline if t["burst"]]
    check("burst minute is 08:06",
          len(bursts) == 1 and bursts[0]["minute"].strftime("%H:%M") == "08:06",
          bursts)
    top = a.clusters[0]
    check("top cluster is a problem cluster", top.problem_count >= 4, top)

    # --- trace fixture ---------------------------------------------------
    tevents, tstats = parsers.parse_text(load("qnx-kernel-trace.txt"))
    check("trace format auto-detected", tstats["format"] == "trace", tstats)
    check("trace fixture parses >= 25 events", tstats["parsed"] >= 25, tstats)
    ta = az.analyze(tevents)
    destroyed = [e for e in tevents if "DESTROYED" in e.message]
    check("trace process-destroy events flagged as problems",
          len(destroyed) == 2 and all(e.is_problem for e in destroyed),
          len(destroyed))

    # --- unit-level checks -------------------------------------------------
    check("signature normalizes numbers",
          az.signature("connection 12 failed at 0x8000")
          == az.signature("connection 87 failed at 0x9abc"))
    ev, _ = parsers.parse_text(
        "Nov 25 08:00:01.5 host proc[42]: 2: something broke\n")
    check("single slog2 line parses with pid+severity",
          len(ev) == 1 and ev[0].pid == 42 and ev[0].severity == 2, ev)

    print(f"\nALL {len(PASSED)} CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
