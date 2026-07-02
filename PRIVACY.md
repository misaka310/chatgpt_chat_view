# Privacy

This tool is designed for local analysis.

## What stays local

- Raw conversation exports
- Generated JSON, CSV, and HTML output
- Token estimates and usage summaries

## Before making the repository public

Run:

```powershell
git status --ignored
```

Confirm that private files are ignored and not staged.

Do not commit files such as:

- `chat.html`
- `conversations.json`
- `conversations-*.json`
- files under `input/`
- files under `output/`

## Important limitation

The 3-hour limit report is a local estimate from exported user messages. It is not official model-specific usage data.
