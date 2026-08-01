# Public Release Checklist

Use this before switching the repository visibility to public.

## Repository state

- [ ] Default branch is `main`.
- [ ] Unneeded remote branches are deleted.
- [ ] Repository name and description are public-facing.
- [ ] License is present.
- [ ] README starts with a quick start.

## Data safety

- [ ] `git status --ignored` shows raw exports as ignored.
- [ ] No raw export is staged or committed.
- [ ] Generated outputs are ignored unless they are sample-only.
- [ ] Screenshots use fake sample data or are fully redacted.

## First-run UX

- [ ] First-run setup through `start.bat` succeeds on Windows.
- [ ] `start.bat` analyzes changed `input/`, reuses unchanged results, and opens the dashboard.
- [ ] The browser opens `output/dashboard.html` through the loopback-only local server.
- [ ] `dashboard.html` links to the 3-hour usage report.

## Verification

- [ ] `python -m unittest` passes.
- [ ] GitHub Actions test passes.
