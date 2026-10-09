# Security backport

This vendored package is based on `braces@3.0.3` and applies the complete fix from `FSDevelop/braces` commit `28d440b5dd449dbf1fe6f3506cf94ecca4d02660`, the head of micromatch/braces PR #72 for CVE-2026-93687 / GHSA-vfj7-8cjw-p6xm.

The local package version is `3.0.4` so dependency scanners do not mistake the patched backport for the vulnerable upstream `3.0.3` release. Replace this vendor copy with an official upstream release as soon as one containing the fix is published.

The upstream package remains MIT licensed; see `LICENSE` in this directory.
