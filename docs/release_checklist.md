# Public Release Checklist

Use this before merging or publishing a release.

## Repository state

- [ ] Default branch is `main`.
- [ ] Unneeded remote branches are deleted.
- [ ] No nested `.git` directory exists below the repository root.
- [ ] Repository name and description are public-facing.
- [ ] License is present.
- [ ] README starts with a quick start.
- [ ] Root files are limited to the two user entry points and essential repository documents/configuration.

## Data safety

- [ ] `git status --ignored` shows raw exports as ignored.
- [ ] No raw export, generated private output, or real `usage-data.json` is staged or committed.
- [ ] Screenshots use fake sample data or are fully redacted.
- [ ] `scripts/verify_sites_public.py` passes for the Sites source and built artifact.
- [ ] The Sites artifact contains no conversation text, title, ID, input filename, local path, email address, or secret.

## First-run UX

- [ ] First-run setup through `start.bat` succeeds on Windows.
- [ ] An interrupted setup is retried automatically on the next launch.
- [ ] `start.bat` analyzes changed `input/`, reuses unchanged results, and opens the dashboard.
- [ ] The browser opens `output/dashboard.html` through the loopback-only local server.
- [ ] `dashboard.html` links to the 3-hour usage report.
- [ ] `start_sites.bat --no-open` builds, scans, and reuses the Sites artifact correctly.

## Sites access

- [ ] The final Share/publishing screen shows the intended restrictive audience.
- [ ] The published URL is denied in a signed-out/private browser window.
- [ ] Publishing is cancelled if owner-only or equivalent private access is unavailable.

## Verification

- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] `npm test` passes in `sites/usage-dashboard`.
- [ ] `npm run lint` passes in `sites/usage-dashboard`.
- [ ] `git diff --check` passes.
- [ ] GitHub Actions passes.
