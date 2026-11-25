"""Slog Doctor CLI.

Usage:
    python3 -m slogdoctor analyze LOG [LOG ...] [--out report.html]
                                  [--json summary.json]
                                  [--format auto|slog2|trace|syslog]

Runs on the developer's host (Linux/macOS/Windows). Inputs are text
exports produced on a QNX 8.0 target with slog2info / traceprinter.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slogdoctor import analyze as _analyze          # noqa: E402
from slogdoctor import parsers, report              # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="slogdoctor",
        description="Diagnose QNX 8.0 slog2 logs and kernel traces.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    an = sub.add_parser("analyze", help="analyze one or more log files")
    an.add_argument("files", nargs="+", help="log/trace text files")
    an.add_argument("--format", default="auto",
                    choices=["auto", "slog2", "trace", "syslog"],
                    help="input format (default: auto-detect per file)")
    an.add_argument("--out", metavar="HTML",
                    help="also write a self-contained HTML report")
    an.add_argument("--json", metavar="JSON",
                    help="also write a machine-readable JSON summary")
    args = ap.parse_args(argv)

    events = []
    sources = []
    for path in args.files:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        evs, stats = parsers.parse_text(text, fmt=args.format)
        events.extend(evs)
        stats["name"] = os.path.basename(path)
        sources.append(stats)

    events.sort(key=lambda e: (e.ts is None, e.ts or e.rel_ts or 0))
    result = _analyze.analyze(events)
    print(report.text_summary(result, sources))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report.html_report(result, sources))
        print(f"\nHTML report written to {args.out}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(report.to_json(result, sources))
        print(f"JSON summary written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
