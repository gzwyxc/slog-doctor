# QNX Global Hackathon — Entry Plan ("Slog Doctor")

Devpost account: **gzwyxc** (registered solo). Category target: **Developer Tooling & Host Tools** ($4,000).
Stacking target: **Best Codelab / Tutorial** bonus ($3,500). A project may win one Overall prize + one Bonus prize + Community Choice.

Source of truth: Official Rules snapshot `~/workspace/devpost-sweep-2026-11-25/qnx-global-hackathon-rules.txt`
(event page https://qnx.devpost.com/ · rules https://qnx.devpost.com/rules).

---

## 1. Hard deadlines

| Item | When |
|---|---|
| Submission period | Nov 2, 2026 11:00 AM ET – **Dec 15, 2026 2:00 PM ET** |
| **Our internal freeze** | **Dec 14, 2026** (repo, video, form all done a day early) |
| Judging + public voting | Jan 15–29, 2027 |
| Winners announced | On or around Feb 4, 2027, 2:00 PM ET |

Eligibility (verified from rules §3): individuals 18+; US residents fully eligible; exclusions are only
Brazil/Russia/Crimea/Cuba/Iran/North Korea + OFAC-sanctioned. No student/employee restriction. Fully online.
Project must be **newly created between Nov 2 and Dec 15, 2026**, or significantly updated in that window — ours is new.

## 2. Judging criteria (§6, Stage Two — four criteria, EQUALLY weighted)

1. **Technological Implementation** — "How well is the project built, and how effectively does it use QNX 8.0?
   Does the code reflect real engineering effort and a working, non-trivial implementation that genuinely
   builds for or runs on QNX?"
2. **Design** — "Does the project deliver a complete, coherent product experience, not just a technical proof of concept?"
3. **Potential Impact** — "Does the project make a credible, specific case for solving a real problem in a market
   QNX serves or wants to serve, and does it show why a real-time foundation like QNX is the right choice for it?"
4. **Innovation & AI Creativity** — "Is this a creative, non-obvious use of QNX and does the team show genuine
   understanding of the problem space?" (No AI/LLM ban anywhere in the rules; AI is an explicit scored theme.)

Bonus prizes judged separately:
- **Best Codelab/Tutorial ($3,500)** — a codelab/tutorial authored during the Submission Period that teaches the
  reader how to perform a task on or for QNX 8.0 (does NOT have to relate to our Project — ours will).
- **Best Use of QNX-specific Technologies ($3,500)** — native message passing, resource managers, microkernel
  architecture, startup/boot customization, real-time services, security policies. (Stretch goal only; our
  host-tool route touches resmgr/message-passing *diagnostics*, which is adjacent but weaker — do not overclaim.)

Prize math for our route: category win $4,000 (runner-up $2,000; honorable mention $1,000) + codelab bonus $3,500
= up to **$7,500** from one entry. Grand Prize $10,000 is open to all submissions.

## 3. Submission checklist (§4 — every item is REQUIRED unless noted)

- [ ] **Public code repository** (GitHub/GitLab/Bitbucket), public, with a **detectable open-source license file**
      (we ship MIT `LICENSE` at repo root).
- [ ] Repo must **genuinely evidence QNX 8.0** — "not merely that QNX 8.0 is named in the README."
      For a host-based tool the rules' evidence test is: *"output or functionality specifically intended to build,
      analyze, test, deploy, debug, or manage software for QNX 8.0."*
      Our evidence: real parsers for QNX **slog2** (`slog2info`) text exports and QNX **kernel trace**
      (`tracelogger`/`traceprinter`) text exports; a QNX-specific diagnostic knowledge base (resource managers,
      native message passing, HAM restarts, `procnto`, `io-pkt`, `devb-*` drivers); sample QNX log fixtures;
      a sample QNX **.build** image file parsed by the tool (phase 2); README naming QNX 8.0 throughout the docs.
      Host tools are expressly eligible: *"a host-based tool running on Windows, macOS, or Linux that builds,
      tests, analyzes, or otherwise supports software targeting QNX 8.0."*
- [ ] **Build and run instructions** in the repo specifying: QNX version (**QNX 8.0 / QNX Everywhere**),
      the target (host tool — runs on Linux/macOS/Windows; analyzes artifacts produced on QNX 8.0 targets incl. QEMU),
      and the toolchain (Python 3.10+, standard library only — no third-party packages).
- [ ] **Text description** of features and functionality (Devpost form field; draft lives in `docs/devpost-description.md`, phase 2).
- [ ] **Demo video < 3 minutes**, uploaded to YouTube and **publicly visible**. Screen recording only —
      no person or voice required by the rules. Must show (our shot list):
      1. A raw QNX slog2 log full of errors (the "before" pain — scrolling noise).
      2. One command: `slogdoctor analyze` on the sample crash-loop log.
      3. The HTML report: summary cards → error clusters ranked → the crash-loop finding with its
         plain-language explanation ("telemetryd crashed with SIGSEGV and HAM restarted it 4 times…").
      4. The timeline view showing the error burst/anomaly highlight.
      5. A kernel-trace file analyzed the same way (second format, same workflow).
      6. Closing frame: repo URL + "works on logs from any QNX 8.0 target, including QEMU".
- [ ] **All submission materials in English** (or with English translation). Our repo/docs are English.
- [ ] Category selected on the form: **Developer Tooling & Host Tools**; bonus opt-in: **Best Codelab/Tutorial**
      (codelab lives in `codelab/` in the same repo).
- [ ] (If we win) Winner affidavit + required forms; US residents may need a **W-9** (ITIN works).
      Prizes delivered within 60 days of Devpost/Sponsor receiving completed forms. PayPal/Payoneer/Wise per Devpost flow.

## 4. The tool — "Slog Doctor" (design)

**One-liner:** A host-side diagnostic tool that turns raw QNX 8.0 system logs (slog2) and kernel traces into a
ranked, plain-language health report — so an embedded developer finds the crash, the restart loop, and the
error burst in minutes instead of grepping ten thousand lines.

**Why it fits QNX's markets (Potential Impact):** QNX ships in automotive, medical, robotics and industrial
systems where a field failure is a log file shipped back from a device you cannot attach a debugger to.
Triage of slog2 output is a daily, manual, expert-only task. A tool that clusters, timelines and *explains*
QNX-specific failure patterns (resmgr errors, MsgSend to a dead process, HAM restart loops, watchdog bites)
directly serves the developers QNX wants to attract.

**Form factor:** Python 3 CLI (stdlib only, zero install friction) + a self-contained single-file HTML report
(inline CSS/SVG, no external assets — opens offline, easy to demo on video). Terminal text summary for CLI users.

**Pipeline:**
1. **Ingest** — auto-detect format per file: `slog2` (slog2info text export), `trace` (traceprinter text export),
   `syslog` (generic fallback). Tolerant regex field extraction (slog2info column layouts vary by flags).
2. **Parse** — normalize to events: timestamp, host, process, pid, severity (slog severities 0–7 mapped to
   names), message, raw line.
3. **Analyze**
   - Severity & source distribution.
   - **Error clustering**: messages normalized (numbers, hex, pids, addresses stripped) into signatures;
     ranked by count with first/last seen and a sample line.
   - **QNX knowledge base**: pattern → plain-language explanation + suggested next step
     (SIGSEGV/SIGABRT crashes, HAM restart loops, MsgSend `ESRCH` to a dead process, resmgr attach/detach
     errors, `io-pkt` link events, `devb-*`/CAM storage errors, watchdog timeouts, ENOSPC, malloc failures…).
   - **Restart-loop detection**: same process crashing ≥ 3 times in the window.
   - **Timeline & anomalies**: per-minute event/error buckets; bursts flagged at mean + 2σ.
4. **Report** — text summary (stdout) + HTML report (summary cards, SVG timeline, ranked clusters with
   explanations, anomaly list) + optional JSON for tooling.

**Repo layout (public-repo-ready):**
```
PLAN.md  README.md  LICENSE  .gitignore
src/slogdoctor/   __init__.py __main__.py parsers.py analyze.py knowledge.py report.py
samples/          qnx-crashloop-slog2.txt  qnx-kernel-trace.txt  README.md
tests/            run_tests.py
docs/             test-run.log  sample-report.html  (generated proof it works)
codelab/          README.md  (phase-2: full step-by-step codelab for the $3,500 bonus)
```

## 5. QNX SDP / toolchain note

- The host-tool route **does not need the QNX SDP at all** — Slog Doctor runs on the developer's host and
  analyzes log/trace text exported from a target. Nothing to install, nothing to license. ✅ No blocker.
- QNX SDP 8.0 is offered **free for non-commercial use via "QNX Everywhere"**, but getting it requires
  creating a BlackBerry/QNX account and accepting a license agreement **in the user's own name**.
  Per instructions we will **NOT** sign up for it in this phase.
  ⚠️ **Flagged (phase-2 optional enhancement, needs the user):** if the user creates a free QNX Everywhere
  account, we could additionally cross-compile a tiny QNX 8.0 target demo (a small C program that emits slog2
  logs and crashes on purpose under QEMU) to generate *real* target logs and strengthen the
  Technological Implementation score. The entry stands without it.

## 6. Phase plan

- **Phase 1 (this run):** PLAN.md, scaffold, working core (parsers + clustering + knowledge base + HTML/text
  report), sample fixtures, test run with log saved in `docs/test-run.log`, sample report in `docs/sample-report.html`.
- **Phase 2:** push to a public GitHub repo (account gzwyxc) with the MIT LICENSE; write the full codelab in
  `codelab/`; optional .build-file parsing; Devpost description draft.
- **Phase 3:** record the < 3 min demo video (shot list in §3), upload public to YouTube, complete the Devpost
  submission form (category + codelab bonus), submit **before Dec 14**.
