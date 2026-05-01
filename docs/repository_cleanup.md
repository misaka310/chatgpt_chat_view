# Repository Cleanup Notes

## What Was Organized
- Added `.gitignore` to block chat content and generated artifacts.
- Standardized documentation under `docs/`.

## Files Intended for Git
- `analyze_chat_export.py`
- `docs/README_ja.md`
- `docs/repository_cleanup.md`
- `.gitignore`

## Files Intentionally Excluded
- Raw exports: `chat.html`, `conversations-*.json`
- Generated artifacts: `dashboard.html`, `parsed_summary.json`, `daily_*.csv`, `monthly_*.csv`, `monthly_summary.md`

## Push Checklist
1. Confirm current branch is not `main` or `master`.
2. Run basic verification command(s).
3. Ensure `git status` does not include raw chat files.
4. Commit and push the working branch.
