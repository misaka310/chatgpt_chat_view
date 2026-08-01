# Privacy

This tool is designed for local analysis.

## What stays local

- Raw conversation exports
- Personal JSON, CSV, and HTML analysis output
- Conversation titles, text, identifiers, source paths, and input file names
- Intermediate files and logs

## Optional private Sites dashboard

`start_sites.bat` builds a separate frontend under `sites/usage-dashboard`. Its generated `public/usage-data.json` contains only allowlisted aggregate values such as month, date, sent-message counts, active-day counts, conversation counts, estimated token counts, and generation time.

The real Sites aggregate file and build output are ignored by Git. Before saving or deploying a Sites version, run the repository's public-artifact verifier against both the source public directory and the built `dist` directory.

A private Sites deployment still sends the allowlisted aggregate values to ChatGPT Sites so that the owner can view them remotely. Raw exports and personal detailed analysis remain local and are not included in the deployment artifact.

## Before making the repository public

Run:

```powershell
git status --ignored
git ls-files input output sites/usage-dashboard/public/usage-data.json sites/usage-dashboard/dist
```

Confirm that private files are ignored and not staged.

Do not commit files such as:

- `chat.html`
- `conversations.json`
- `conversations-*.json`
- files under `input/`
- files under `output/`
- `sites/usage-dashboard/public/usage-data.json`
- files under `sites/usage-dashboard/dist/`

## Important limitation

The usage reports are local estimates from exported user messages. They are not official model-specific usage data.
