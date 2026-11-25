"""Report rendering: terminal text summary and a self-contained HTML report."""

from __future__ import annotations

import html
import json
from datetime import datetime

from .analyze import Analysis, severity_label
from .parsers import SEVERITY_NAMES


def text_summary(a: Analysis, sources: list[dict]) -> str:
    out = []
    out.append("=" * 68)
    out.append("SLOG DOCTOR -- QNX log health report")
    out.append("=" * 68)
    for s in sources:
        out.append(f"  input: {s['name']}  [{s['format']}]  "
                   f"{s['parsed']} events parsed, {s['skipped']} lines skipped")
    out.append(f"  total events: {a.total}   "
               f"problems (severity <= ERROR): {a.problem_total}")
    if a.start and a.end:
        out.append(f"  window: {a.start:%Y-%m-%d %H:%M:%S} .. "
                   f"{a.end:%H:%M:%S}")
    out.append("")
    out.append("Severity distribution:")
    for sev in sorted(a.severity_counts):
        out.append(f"  {severity_label(sev):<9} {a.severity_counts[sev]}")
    if a.problem_sources:
        out.append("\nNoisiest problem sources:")
        for src, n in a.problem_sources.most_common(5):
            out.append(f"  {src:<24} {n} problem events")
    if a.findings:
        out.append("\nFindings (most important first):")
        for i, f in enumerate(a.findings, 1):
            out.append(f"  {i}. [{f.kind}] {f.title}")
            out.append(f"     {f.detail}")
            if f.rule:
                out.append(f"     -> Next step: {f.rule.action}")
    if a.clusters:
        out.append("\nTop error clusters (normalized signatures):")
        shown = 0
        for c in a.clusters:
            if c.problem_count == 0:
                continue
            out.append(f"  x{c.problem_count:<4} [{severity_label(c.worst_severity)}] "
                       f"{c.signature[:90]}")
            if c.rule:
                out.append(f"        {c.rule.title}")
            shown += 1
            if shown >= 8:
                break
    return "\n".join(out)


def to_json(a: Analysis, sources: list[dict]) -> str:
    data = {
        "inputs": sources,
        "total_events": a.total,
        "problem_events": a.problem_total,
        "severities": {severity_label(k): v
                       for k, v in sorted(a.severity_counts.items())},
        "findings": [{"kind": f.kind, "title": f.title,
                      "detail": f.detail,
                      "action": f.rule.action if f.rule else None}
                     for f in a.findings],
        "clusters": [{"signature": c.signature, "count": c.count,
                      "problems": c.problem_count,
                      "worst_severity": severity_label(c.worst_severity),
                      "sources": dict(c.sources),
                      "explanation": c.rule.title if c.rule else None}
                     for c in a.clusters[:25]],
        "timeline": [{"minute": t["minute"].isoformat(),
                      "total": t["total"], "problems": t["problems"],
                      "burst": t["burst"]} for t in a.timeline],
    }
    return json.dumps(data, indent=2)


def _timeline_svg(a: Analysis, width: int = 760, height: int = 120) -> str:
    if not a.timeline:
        return "<p class='muted'>No timestamps available for a timeline.</p>"
    peak = max(t["total"] for t in a.timeline) or 1
    n = len(a.timeline)
    bw = width / n
    bars = []
    for i, t in enumerate(a.timeline):
        h = (t["total"] / peak) * (height - 18)
        ph = (t["problems"] / peak) * (height - 18) if t["total"] else 0
        x = i * bw
        cls = "burst" if t["burst"] else ""
        bars.append(
            f"<rect class='bar {cls}' x='{x:.1f}' y='{height - h:.1f}' "
            f"width='{max(bw - 1, 1):.1f}' height='{h:.1f}'>"
            f"<title>{t['minute']:%H:%M} — {t['total']} events, "
            f"{t['problems']} problems</title></rect>")
        if t["problems"]:
            bars.append(
                f"<rect class='pbar' x='{x:.1f}' y='{height - ph:.1f}' "
                f"width='{max(bw - 1, 1):.1f}' height='{ph:.1f}'/>")
    return (f"<svg viewBox='0 0 {width} {height}' class='chart' "
            f"role='img' aria-label='Events per minute'>"
            + "".join(bars) + "</svg>")


_CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
 margin:2rem auto;max-width:900px;padding:0 1rem;color:#1c2430;background:#f7f8fa}
h1{font-size:1.6rem;margin-bottom:.2rem} h2{margin-top:2rem;font-size:1.15rem}
.muted{color:#667} .cards{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}
.card{background:#fff;border:1px solid #dde3ea;border-radius:10px;
 padding:1rem 1.2rem;min-width:150px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.card .n{font-size:1.7rem;font-weight:700} .card .l{color:#667;font-size:.85rem}
.finding{background:#fff;border-left:5px solid #d97706;border-radius:6px;
 padding:.8rem 1rem;margin:.6rem 0}
.finding.restart-loop,.finding.crash{border-left-color:#dc2626}
.finding .act{color:#14532d} table{border-collapse:collapse;width:100%;
 background:#fff;border:1px solid #dde3ea;border-radius:8px;overflow:hidden}
td,th{padding:.5rem .7rem;border-bottom:1px solid #eef1f5;text-align:left;
 font-size:.92rem;vertical-align:top} th{background:#eef2f7}
.chart{width:100%;background:#fff;border:1px solid #dde3ea;border-radius:8px}
.bar{fill:#7aa2d6}.bar.burst{fill:#d97706}.pbar{fill:#dc2626;opacity:.75}
code{background:#eef1f5;padding:.05rem .3rem;border-radius:4px}
details{margin:.3rem 0} summary{cursor:pointer;color:#345}
"""


def html_report(a: Analysis, sources: list[dict],
                generated: datetime | None = None) -> str:
    generated = generated or datetime.now()
    esc = html.escape
    sev_rows = "".join(
        f"<tr><td>{esc(severity_label(s))}</td><td>{n}</td></tr>"
        for s, n in sorted(a.severity_counts.items()))
    findings = "".join(
        f"<div class='finding {esc(f.kind)}'><strong>{esc(f.title)}</strong>"
        f"<p>{esc(f.detail)}</p>"
        + (f"<p class='act'><strong>Next step:</strong> {esc(f.rule.action)}</p>"
           if f.rule else "")
        + "</div>" for f in a.findings) or \
        "<p class='muted'>No significant findings.</p>"
    cluster_rows = []
    for c in a.clusters[:20]:
        expl = ""
        if c.rule:
            expl = (f"<details><summary>{esc(c.rule.title)}</summary>"
                    f"<p>{esc(c.rule.explanation)}</p>"
                    f"<p><strong>Next step:</strong> {esc(c.rule.action)}</p>"
                    f"</details>")
        cluster_rows.append(
            f"<tr><td>{c.problem_count}</td><td>{c.count}</td>"
            f"<td>{esc(severity_label(c.worst_severity))}</td>"
            f"<td>{esc(', '.join(c.sources))}</td>"
            f"<td><code>{esc(c.signature[:110])}</code>{expl}</td></tr>")
    inputs = "".join(
        f"<li><code>{esc(s['name'])}</code> — {esc(s['format'])}, "
        f"{s['parsed']} events parsed, {s['skipped']} lines skipped</li>"
        for s in sources)
    window = (f"{a.start:%Y-%m-%d %H:%M:%S} .. {a.end:%H:%M:%S}"
              if a.start and a.end else "n/a")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Slog Doctor — QNX log health report</title><style>{_CSS}</style></head>
<body>
<h1>Slog Doctor — QNX log health report</h1>
<p class="muted">Generated {generated:%Y-%m-%d %H:%M} · Log window: {esc(window)}</p>
<ul>{inputs}</ul>
<div class="cards">
 <div class="card"><div class="n">{a.total}</div><div class="l">total events</div></div>
 <div class="card"><div class="n">{a.problem_total}</div><div class="l">problem events (severity ≤ ERROR)</div></div>
 <div class="card"><div class="n">{len(a.clusters)}</div><div class="l">distinct message clusters</div></div>
 <div class="card"><div class="n">{len(a.findings)}</div><div class="l">findings</div></div>
</div>
<h2>Findings</h2>{findings}
<h2>Timeline — events per minute (red overlay = problems, orange = burst)</h2>
{_timeline_svg(a)}
<h2>Severity distribution</h2>
<table><tr><th>Severity</th><th>Events</th></tr>{sev_rows}</table>
<h2>Top message clusters</h2>
<table><tr><th>Problems</th><th>Total</th><th>Worst severity</th>
<th>Sources</th><th>Signature / explanation</th></tr>
{''.join(cluster_rows)}</table>
<p class="muted">Slog Doctor analyzes text exports from QNX 8.0 targets
(slog2info, traceprinter). It runs on the developer's host — no agent on the target.</p>
</body></html>"""
