# ChatGPT Usage Dashboard Site

This directory is the only ChatGPT Sites deployment root in this repository.

It contains the tracked frontend source and hosting metadata only. The real aggregate file is generated locally at `public/usage-data.json`, is ignored by Git, and must pass `scripts/verify_sites_public.py` before a build or deployment is accepted.

## Published data boundary

The frontend reads only this allowlisted schema:

- month and date
- total, non-voice, and voice-only sent-message counts
- total, non-voice, and voice active-day counts
- conversation counts
- estimated token counts
- aggregate generation time and fixed methodology text

Raw exports, private analysis output, titles, identifiers, local paths, input names, logs, and per-conversation details do not belong in this directory or its deployment artifact.

## Local flow

From the repository root, run `start_sites.bat`. It:

1. prepares or reuses the local Python environment;
2. analyzes changed ChatGPT export input;
3. writes only the allowlisted aggregate data;
4. scans the source and built artifact for private markers and secrets;
5. installs exact Node dependencies only when needed;
6. builds or reuses the Sites artifact and opens a local preview.

Node.js 22.13 or later is required.

## Access control after deployment

Repository files and `.openai/hosting.json` do not decide who can open a published Site. In the ChatGPT Sites publishing or Share screen, explicitly choose the most restrictive audience available—owner/workspace administrators only, or only your own account where selectable.

Before treating the Site as private:

1. inspect the final audience shown in the Share screen;
2. open the published URL in a signed-out/private browser window and confirm access is denied;
3. do not publish if the required private audience is unavailable on the current workspace or plan.

The aggregate deliberately excludes message content, but dates and usage counts are still personal data and should not be published accidentally.
