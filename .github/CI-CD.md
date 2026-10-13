# CI/CD Audit and Operations

## Findings (2026-10-09)

The original workflow already ran on main push, and its latest run succeeded.
The confirmed gaps were missing tests/security gates, mutable Action tags,
publication independent of GitFlow validation, and cancellable main runs.
All 21 GitFlow branches across seven repositories required only `check-flow`,
zero approvals, and no up-to-date branch. Repository secrets were empty;
organization secret configuration could not be audited (403).

## Pipeline Contract

PRs to develop/stage/main, pushes to those branches, and merge queues run GitFlow,
pytest, workflow syntax validation, dependency/secret scans, image build,
non-root inspection, and final-image vulnerability/configuration/secret scans.
`ci-required` rejects failed, cancelled, or skipped dependencies. Trivy v0.69.3
blocks HIGH/CRITICAL including unfixed findings. Actions use full SHAs and
actionlint v1.7.7 is checksum-verified. Token permissions are `contents: read`;
checkout does not persist credentials.

Only main pushes or valid `vMAJOR.MINOR.PATCH` tags authenticate and push the
already-scanned image to `quay.io/parraes/kubeoptix-core-ai`. Main keeps `latest`
and `sha-<commit>`, releases version and SHA tags; tags must point into main
history. PRs, stage, develop, and merge queues never access Quay secrets. Main
runs are not actively cancelled; GitHub can coalesce pending concurrent runs.

## GitHub and Quay Configuration

Applied and verified on all three branches: `check-flow` and `ci-required` from
GitHub Actions, up-to-date branch, at least one approval, dismissal of stale
reviews, approval of the last push, enforcement for admins, no force pushes,
and no branch deletion. Existing checks remain. GitHub allows APPROVE reviews
on failing PRs, but protected branches prevent integration.

Publish these workflows on the existing feature branch and open a PR to develop.
Require a green gate and independent review, then promote develop -> stage ->
main. PRs remain blocked until the updated workflows produce `ci-required`.
Permit the pinned Actions in organization policy and protect `v*` tags with a
ruleset limiting creation to maintainers and prohibiting update/deletion.
`GITHUB_TOKEN`-generated pushes do not trigger another workflow; use an approved
GitHub App for automated tag creation when a push-triggered release is needed.

Create a Quay robot with Write only on this destination. Set `QUAY_USERNAME`
(full `namespace+robot`) and `QUAY_PASSWORD` (token) in repository secrets or
restricted organization secrets including this repository. Never print tokens,
enable tracing, or store credentials in code/command arguments. Rotate through
secure prompts and enable Quay vulnerability notifications.

## Validation and Blockers

All 14 workflows passed actionlint, aggregate failure cases and 63 GitFlow cases
passed, and all 21 remote protections were verified. Source scans passed with
no HIGH/CRITICAL findings or secrets. Local Python 3.14 tests: 221 passed,
4 skipped by existing conditions, 2 failed:

- `test_report_finding_groups.py::test_markdown_groups_res_findings_in_sections`
  expected grouped-report wording not present in generated Markdown.
- `test_visualization_architecture.py::test_architecture_section_in_namespace_overview`
  expected architecture/fallback wording not present in generated Markdown.

No application code or assertions were changed or skipped to make CI green.
These failures must be resolved before merging; confirm them in the clean Python
3.12 CI environment. The final image was not rebuilt/scanned locally. No changed
workflows were committed, pushed, or executed remotely, and no image was
published. Acceptance is pending a genuinely green reviewed promotion and a
main run publishing the exact scanned image. Never bypass `ci-required`.

## PR Failure Remediation (2026-10-09)

PR #34 confirmed that resource findings were omitted from generated Markdown
despite being grouped correctly in memory. The report now renders these groups
after Visualizations, outside the declared-resource suggestion block, and retains
textual architecture relationships when a diagram succeeds. The Spanish test
now asserts the expected impact label: "Impacto potencial" is valid in both
Spanish and Portuguese and must not be rejected as untranslated Portuguese.
The original grouping assertion and every application test remain enabled.

The complete suite passed on Python 3.12: 223 passed, 4 pre-existing skips.
The container now uses the same fixed UBI 10 base as the other Python services;
Trivy could not scan Fedora OS packages, so a green Fedora image scan did not
provide adequate OS coverage. The UBI image passed OS/application, configuration,
and secret scans. Only the two historical build inventories in pip/virtualenv
are excluded, as documented for Analyzer; installed packages are still scanned.
The old blockers above describe the initial audit, not the corrected revision.
Remote checks and independent review are still required before promotion.