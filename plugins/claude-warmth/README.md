# claude-warmth

Do you treat Claude like a person? This plugin measures how warmly you write to Claude compared with how you text the people in your life — on a 0–100 warmth scale calibrated entirely from your own iMessage history.

## What you get

1. **An inline chart**: your warmth toward Claude across your conversation history, plotted against three personal reference lines — how warmly you text your Acquaintances, Friends, and Closest people.
2. **A local HTML report** (`claude-warmth-report.html`): the chart, a full plain-language methodology (how the warmth index is defined, how the conversation index works, how the three thresholds are computed), and a clustering view of your contacts by warmth bucket.

## What it needs

- **macOS with iMessage history.** Copy `~/Library/Messages/chat.db` into your project folder — this calibrates your personal scale. Required.
- **Claude conversations**, from either or both: Claude Code session files (`~/.claude/projects`, read automatically) and Cowork session transcripts (read via session tools).

## Privacy

Everything runs locally with stdlib Python. No network calls, no uploads. Contact identifiers are masked in all outputs. Your scale is calibrated to your own habits, so scores aren't comparable between people — by design.

## Trigger

Say "analyze my warmth with Claude", "run claude-warmth", or "do I treat Claude like a person?"
