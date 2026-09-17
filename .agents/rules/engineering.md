---
trigger: always_on
description: Engineering discipline for this repository - definition of done, evidence, docs sync, git safety
---

# Engineering rules (always on)

## Definition of done
- A feature or fix is DONE only when one of these holds: (a) it changes the output of `sentinel-diff analyze` and the regenerated artifacts are committed, or (b) a test imports and calls the real function in `src/sentinel_diff/` and would fail without the change.
- For every bug fix, prove the test detects the bug: temporarily revert the fix, run the test and capture the FAIL; restore it, run again and capture the PASS. Paste both outputs in the final report. No proof, not done.
- Never write a test that reimplements or simulates the behavior with numpy instead of calling the module under test. Offline is not an excuse: use pytest `tmp_path` GeoTIFFs, `rasterio.io.MemoryFile`, or stub STAC items.

## Evidence over claims
- Every number, date or scene ID in README.md, PLAN.md, docs/ and reports/ is copied from a generated artifact (`reports/*_metrics.json`, CLI output). Never type results from memory. When the pipeline is re-run, update every place the numbers appear (README table and prose, HTML report, PLAN.md).
- PLAN.md is the ground truth. Update it before README.md. README claims only `[x]` items. A Known Issue is marked resolved only with the name of the test or artifact that proves it.
- Never silently change a parameter or default (thresholds, cloud limits, date windows, resampling). Name the change and its effect in the commit message and the docs.

## Scope and git
- One logical change per commit; Conventional Commits; code, comments, docs and commit messages in English.
- Before each commit run `make check` and `make test` and include their output in the report. Never use `--no-verify`, never amend pushed commits, never force push. Never push without explicit user approval in the current conversation.
- Never commit data, rasters, secrets or files over 2 MB. Never read or write files outside this workspace.
- If you notice a problem outside the current task, do not fix it; add it to PLAN.md Known Issues.

## Reporting
- End every task with: what changed, what proves it (test names + outputs), what was intentionally left out.
- State uncertainty explicitly. "Verified" means you ran it and saw the output in this conversation.
