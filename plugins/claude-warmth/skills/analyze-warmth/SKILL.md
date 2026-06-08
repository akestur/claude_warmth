---
name: analyze-warmth
description: Measures how warmly the user writes to Claude compared with their human iMessage contacts, producing an inline warmth-trend chart and a local HTML report. Trigger when the user says "analyze my warmth with Claude", "run claude-warmth", "how warm am I with Claude", "warmth index", "do I treat Claude like a person", "compare how I talk to Claude vs people", or similar. Requires macOS with an iMessage chat.db copy; analyzes Cowork and/or Claude Code conversation history. All processing is local.
---

# Analyze warmth with Claude

Measure how warmly the user writes to Claude versus their human iMessage contacts. Produce two outputs: an inline warmth-trend chart and `claude-warmth-report.html` in the user's working folder.

All math lives in `scripts/warmth.py` — run it, never reimplement it. The script is stdlib-only Python 3 and makes no network calls. Tell the user up front: everything runs locally, nothing is uploaded, contact numbers are masked.

## Step 1 — Locate the iMessage database (required)

The personal warmth scale is calibrated from the user's own texting history; without it there is nothing to compare against.

1. Look for `chat.db` in the working folder and any connected folders.
2. If absent, explain that a copy of their iMessage database is needed and how to provide it: open Finder → Go → Go to Folder → `~/Library/Messages`, copy `chat.db` into the project folder. (Direct access usually requires Full Disk Access; a manual copy is simplest.) If they're not on macOS or don't use iMessage, stop: this analysis can't run without it.
3. Wait for the file before proceeding.

## Step 2 — Calibrate the personal scale

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/analyze-warmth/scripts/warmth.py" calibrate --db <path-to-chat.db> --out warmth_state.json
```

This builds the user's 0–100 warmth scale from contacts with 100+ sent messages and computes the Acquaintances / Friends / Closest thresholds. If it errors with fewer than 6 qualifying contacts, relay the error plainly and stop.

## Step 3 — Gather Claude conversations (use every source available)

**Claude Code** (if the user uses Claude Code):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/analyze-warmth/scripts/warmth.py" extract-claude-code --out claude_messages.json
```

In Cowork the shell is sandboxed and cannot see `~/.claude` by default — if the command finds 0 sessions but the user says they use Claude Code, request folder access to `~/.claude/projects`, then re-run with `--root <the granted folder's shell path>`.

**Cowork sessions** (when session-inspection tools are available). `cowork_messages.json` is a persistent, append-only cache — sessions already in it are frozen forever so the trend history never reshuffles between runs. Protocol:

1. If `cowork_messages.json` exists in the working folder, read its `id` fields. Those sessions are cached: do not re-read, re-extract, or reorder them.
2. List local sessions. New sessions = not in the cache, AND not the currently-running session (the analysis must not include the conversation it is part of), AND not automated/scheduled runs (repeated identical titles fired on a schedule).
3. Extract only the new sessions' user-typed messages from their transcripts — skip system content; for large sets fan out to parallel subagents. Write `cowork_new.json` ordered oldest session first:

```json
[{"id": "...", "first_ts": "", "messages": ["msg1", "msg2"]}]
```

4. Append to the cache deterministically (never hand-merge):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/analyze-warmth/scripts/warmth.py" merge-cowork --cache cowork_messages.json --new cowork_new.json
```

Only if the user explicitly asks for a rebuild ("refresh", "re-extract from scratch") delete `cowork_messages.json` first and treat every session as new.

If neither source yields anything, tell the user and stop.

## Step 4 — Score and build the report

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/analyze-warmth/scripts/warmth.py" score --state warmth_state.json \
  --claude-code claude_messages.json --cowork cowork_messages.json \
  --out warmth_result.json --report claude-warmth-report.html
```

The script prints a JSON summary and writes three files: the result JSON, the HTML report, and `warmth_inline.html` — a ready-made inline chart fragment. If it exits with `NOT_ENOUGH_DATA`, tell the user how many deliberative messages they have, that 16+ are needed, and to re-run after more Claude usage — do not fabricate a chart.

## Step 5 — Present results

1. **Inline chart** (if a visualization/widget tool is available): read `warmth_inline.html` and render its contents verbatim as the widget code. Do not redesign, restyle, or rebuild the chart — the fragment is the single source of truth so every run looks identical. If no visualization tool exists, skip this.
2. **HTML report**: present `claude-warmth-report.html` to the user (it contains the chart, full methodology, and the contact clustering view).
3. **Narrate honestly, in 2–4 sentences**: where their warmth with Claude sits relative to their three human lines, the direction of the trend, and one caveat (e.g., small window size if the script chose < 15). Read the arc, not single wiggles. Never claim the user is "cold" or "warm" as a person — this measures writing style toward an AI, nothing more.

## Notes

- `report_template.html` and `inline_chart_template.html` live next to the script and are consumed automatically; don't edit them per-run.
- Window size, thresholds, and all numbers come from script output — never estimate or adjust them.
- If the user asks how a number is computed, the methodology section of the report has the authoritative explanation; summarize from it.
