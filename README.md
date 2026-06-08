# claude-warmth

Do you treat Claude like a person? **claude-warmth** measures how warmly you write to your AI compared with how you text the actual people in your life — on a 0–100 warmth scale calibrated entirely from your own iMessage history.

It produces two things:

1. **A warmth trend chart** — your warmth toward Claude across your conversation history, plotted against three personal reference lines: how warmly you text your *Acquaintances*, *Friends*, and *Closest* people.
2. **A local HTML report** — the chart, a full plain-language methodology (how the warmth index is defined, how the conversation index works, how the three thresholds are computed), and a clustering view of your contacts by warmth bucket.

Everything runs locally with stdlib Python. No network calls, no uploads, contact numbers masked. Because the scale is calibrated to *your* texting habits, scores aren't comparable between people — by design.

## Requirements

- **macOS with iMessage history** — at least 6 contacts you've sent 100+ messages. You'll copy `~/Library/Messages/chat.db` into your project folder when prompted (the skill walks you through it).
- **Claude usage** — Cowork sessions and/or Claude Code history (`~/.claude/projects`), with at least 16 "deliberative" messages (moments where you think out loud rather than issue commands).
- Claude Cowork or Claude Code.

## Install

**Claude Code:**

```
/plugin marketplace add akestur/claude_warmth
/plugin install claude-warmth@kestur-plugins
```

**Claude Cowork:** Customize menu → Plugins → **+** → Add marketplace → enter `akestur/claude_warmth` → install **claude-warmth**.

## Use

Say:

> analyze my warmth with Claude

or

> do I treat Claude like a person?

## How it works (short version)

Your sent iMessages build a personal warmth scale from ten style markers — laughter, emoji, profanity, slang, self-disclosure, hedging, lowercase habits, minus period-endings and formal politeness — z-scored against your own contacts and anchored so 0 = no warmth markers at all and 100 = your warmest contact. Your deliberative messages to Claude are then scored on that same ruler in a rolling window across your conversation history. The full methodology, including honest limitations, is in every generated report.

## Privacy

Your messages never leave your machine. The analysis scripts are ~400 lines of dependency-free Python you can read in [`plugins/claude-warmth/skills/analyze-warmth/scripts/warmth.py`](plugins/claude-warmth/skills/analyze-warmth/scripts/warmth.py). Reports mask contact identifiers.

## License

MIT
