# CI/CD pilot: Core AI only

## Scope and observed baseline

Pilot repository: `ShiftWise-AI/kubeoptix-core-ai`. Operator repository, confirmed
by its Git remote: `ShiftWise-AI/kubeoptix-operator`, default branch `main`.
No other component is changed. Existing local deletions of `branch-limits.yml`,
`publish-quay.yml` and `.github/CI-CD.md` are intentional inputs to this change;
the replacement files must be delivered together with those deletions. Do not
retain the old workflows remotely alongside their replacements.

On 2026-10-19 the repository was public, Actions was disabled, and a disabled
ruleset named `develop` also mentioned `stage`. Classic protections on `main`
and `develop` required `check-flow` and `ci-required`, up-to-date branches and
enforcement for administrators, but zero approvals. The new workflows retain
the two required check names. Merge queues are not supported by this pilot;
do not enable them without adding trusted validation for every queued PR.

## Flow and security boundaries

`governance.yml` uses `pull_request_target`, reads the current PR from the API,
and does not check out or execute PR code. Both head and base must belong to
this repository, not merely have matching branch names. Allowed routes:

| Target | Allowed local source |
| --- | --- |
| `develop` | `feature/<name>`, `fix/<name>` |
| `main` | `develop`, `fix/<name>` |

Fork PRs are deliberately rejected, even with a valid-looking source name.
The target branch supplies the trusted gate. Install this workflow on both
protected branches; a workflow file present only in a PR cannot provide a
trusted `pull_request_target` check for its own bootstrap.

Applied remotely during implementation: Actions enabled; rebase merges
disabled; both protected branches retain strict checks/admin enforcement and
now require both checks from GitHub Actions app 15368, one approval, CODEOWNER
review, last-push approval and stale-review dismissal. Verified through the
GitHub API. No source commits, branches, releases or Operator PRs were pushed.

`ci-release.yml` tests every PR and push to `main`, validates workflow syntax,
scans source/secrets, builds the existing `Containerfile`, enforces non-root
runtime and scans the built image. `ci-required` fails if validation fails or
is skipped/cancelled. Actions are pinned to full commit SHAs. No PR job has
publishing credentials or write permissions. These checks complement review;
reviewers must reject changes that bypass CI, change check names or expose
credentials. CODEOWNERS protects workflows and release logic.

After validation on `main`, the release job requires environment approval,
checks secrets and verifies that its source SHA is the actual merge commit of
a merged, allowed, same-repository PR to `main`. A direct push or a spoofed
branch name is not accepted as a release. Squash and merge-commit merges are
supported; keep rebase merging disabled for unambiguous merge provenance.

## Version and retry contract

`[project].version` in `pyproject.toml` is the existing application version.
It is not replaced with a VERSION file, workflow variable or second manifest.
Existing tags reach `v1.0.5`, while the source declares `1.0.0`; therefore the
first reservation is `1.0.6`, not an overwrite of an existing release.
The allocator preserves the source major/minor and increments the greatest
patch of that line, considering both project metadata and existing SemVer
tags. If source major/minor is behind an existing release, it fails explicitly.

A release commit has the merge commit as its parent and changes only
`pyproject.toml`. It is retained by an annotated `vMAJOR.MINOR.PATCH` tag whose
message records `Release-Source: <full source SHA>`. The tagged commit is the
versioned source used for the second test run and image build. There is no push
to protected `main`; its development version is not rewritten by the bot.
To inspect a published version, read `pyproject.toml` at its release tag.
Planned major/minor changes belong in normal reviewed source PRs.

The tag is a durable reservation created BEFORE image publication. A failed
attempt may therefore leave a reserved tag without an image; that is not a
successful release. Retry the same source instead of deleting or reusing tags.
Fresh runners find the reservation and do not increment again. The build uses
the same reserved commit. A preexisting Quay image is reused only when its OCI
version and source labels agree; authentication/network errors fail closed.
Enable immutable version tags on Quay and protect release tags from human
updates/deletions. Do not create manual release tags while this pilot runs.

Published tags: `MAJOR.MINOR.PATCH`, `sha-<full merge SHA>` and existing `latest`.
The remote digest is checked after push. Only a release whose source is still
the head of `main` and whose version is the highest reserved version updates
`latest` or proposes an Operator update; older retries cannot move production
references backwards. Older releases can finish image publication only.

The production job has one concurrency group, `queue: max`, and cancellation
disabled for the active job. GitHub queues up to 100 pending releases instead
of replacing older pending jobs. Ordering follows arrival at the concurrency
group, not commit order. Monitor the queue; runs above its capacity are cancelled
and require recovery via `workflow_dispatch` with the full original merge SHA.
An older release/recovery publishes its immutable image but intentionally does
not downgrade the Operator/latest. During pilot acceptance, also serialize the
Operator PR reviews so an old pin cannot be merged after a newer one.
The queue field is documented in GitHub's current concurrency reference but
not yet recognized by actionlint 1.7.12. Only that exact unknown-key diagnostic
is excluded; a local configuration test asserts `queue: max`. Confirm parser
acceptance in the actual GitHub run before accepting the pilot.

## Operator update

The effective reference is `CoreAIImage` in
`internal/operands/settings.go`, resolved by `FromCR`. The shared
`constants.ImageTag` controls unrelated operands and must not be changed.
The automation replaces only the `CoreAIImage` initializer with
`quay.io/parraes/kubeoptix-core-ai:<version>@sha256:<digest>`.
It preserves Operator version, bundle/CSV versions and all other components.
There is no separate Core AI version entry in the current bundles to update.

Before committing, the job runs gofmt, the existing operands suite, and a
temporary test asserting the exact resolved image. It fails if unexpected
tracked files change or the initializer contract is no longer recognized.
It pushes only `fix/core-ai-<version>` and opens a PR to Operator `main`, never
pushes to its protected branch and never merges automatically. Retries reuse
that branch and the open PR, including recovery after a push but before PR
creation. An already matching base produces no commit or PR. Do not manually
edit the bot-owned update branch; create a separate fix PR instead.

This source change does NOT rebuild/publish the Operator or its OLM bundle.
Deployment still requires reviewing/merging the Operator PR and following
its existing release process. Close obsolete Core AI update PRs before
merging a newer one; never merge an older pin after a newer release.

## Required configuration

Create environment `quay-release`, restrict deployment branches to protected
`main`, and configure a required reviewer with self-approval prevention.
Do not make its credentials available to PR jobs. Configure these environment
secrets, entering values directly through GitHub, never in commands or files:

| Secret | Minimum scope |
| --- | --- |
| `QUAY_USERNAME` | Quay robot account with write on `parraes/kubeoptix-core-ai` only |
| `QUAY_PASSWORD` | That robot account's token |
| `OPERATOR_TOKEN` | Fine-grained token: Operator only, Contents read/write and Pull requests read/write; metadata read; expiration and organization approval as needed |

A GitHub App installation token with the same narrow scopes can replace the
fine-grained token via a separately configured token-generation step. No
Operator credential may have bypass permission for protected branches.

The default `GITHUB_TOKEN` is read-only. Only the release job has Contents
write (tag reservation) and Pull requests read (merge provenance). It does
not request Actions write, administration or permission to approve PRs.

GitHub administrator checklist:

1. Enable GitHub Actions on THIS repository. Keep default token read-only.
2. Preserve existing protections; require `check-flow` and `ci-required`
   from GitHub Actions (app id 15368), strict up-to-date status checks,
   PRs, at least one approval, stale-review dismissal, CODEOWNER review,
   last-push approval and enforcement for admins. Disable force pushes and
   deletions on `main` and `develop`; do not configure bypass actors.
3. CODEOWNERS lists `@pedroarraes` (admin) and `@darioajr` (write), with
   repository permissions verified through the GitHub API. Keep at least two
   eligible owners so one can review the other's PR; nobody can approve their
   own PR. Adjust ownership by review if team membership changes.
4. Keep rebase merges and merge queues disabled. Add tag rules restricting
   update/deletion of `v*` and limiting creation to the release authority;
   ensure the release job can create its tags without branch bypass.
5. Bootstrap the two workflows on both protected branches using existing
   required checks and reviewed PRs. The old trusted gate does not allow
   `fix/*`; use `feature/* -> develop -> main` for initial delivery. Do not
   disable required checks merely to merge this change. If old CI cannot run,
   an administrator must explicitly coordinate the protected bootstrap.
6. Configure the environment, secrets, Quay robot/immutable tags, and Operator
   protection before approving the first release. Verify the Operator has
   its own functioning CI and required checks; its local deleted workflows
   are outside this pilot and were not restored or modified.

## Acceptance test runbook

1. Open local `feature/test -> develop`, `fix/test -> develop`,
   `develop -> main`, `fix/test -> main`: both required checks must run and
   pass when tests/build/scans pass. Use real disposable changes, not empty PRs.
2. Try `feature/test -> main`, `main -> develop`, arbitrary branch names,
   empty prefixes, fork `develop -> main`, fork `fix/test -> main`, fork
   `feature/test -> develop`, and an unexpected target. Confirm governance
   failure for every invalid route and disabled merge on protected targets.
3. Change a PR target, then push a new commit; verify checks reflect current
   API data, previous approvals are dismissed and stale results cannot merge.
4. Break a test and then a container build in separate allowed PRs. Verify
   `ci-required` fails and no release secrets or image publication are used.
5. Merge a valid PR to `main`. Approve the release environment. Verify the
   tagged commit's project version, source marker, successful second test run,
   version/sha/latest tags, matching digest, and non-root/scanned image.
6. Rerun the job (including from a new runner). Verify the same reserved tag,
   no new patch, unchanged version-image digest and no duplicate Operator PR.
7. Simulate missing Quay credentials/push denial using a test environment;
   verify explicit failure and absence of subsequent Operator update. Recover
   the same source SHA after correcting the credential.
8. Interrupt after tag push, image push, and Operator branch push in separate
   trials; resume each and inspect the single version and single PR. Attempt
   closely spaced merges in a controlled test; confirm all jobs are queued
   rather than replaced, without downgrading moving refs.
9. Verify Operator PR diff contains ONLY the Core AI initializer; confirm its
   reference equals the version/digest on Quay, its CI passes and no global
   component/Operator/CSV versions change. Review and merge manually, then
   follow the Operator's own release/deployment process.

## Recovery and rollback

Use Re-run failed jobs or dispatch `CI and Quay release` from `main` with
`source=<full original merge SHA>`. Never dispatch from a feature branch.
Do not delete reservations, force-move release tags, overwrite immutable
version tags or reuse a patch for different source code.

For deployment rollback, open a normal Operator `fix/*` PR restoring the
previous known-good Core AI version AND digest; run operands tests and its CI.
Release/deploy the Operator through its existing process. If consumers use
`latest`, an authorized Quay operator may retarget it to the known-good digest
as a separately approved incident action; immutable release tags stay intact.
Revert application changes through a normal allowed PR, producing a new patch
for the corrective release rather than rewriting history. Revoke compromised
tokens and rotate environment secrets before retrying.

## Validation evidence and remaining gates

Local verification: actionlint 1.7.12 with verified archive checksum; seven
pipeline tests (including Git clone/reservation/retry) and full pytest suite:
238 passed, 4 skipped on Python 3.14.7. CI targets Python 3.12. The unchanged
Containerfile built successfully with Podman; a network-disabled container
imported the API successfully as UID 1001 and reported installed version 1.0.0.
The build emitted a preexisting KubeDiagrams/pygraphviz dependency warning;
dependencies were not changed in this pilot.
These tests do not prove real Actions, Quay authentication/push, Trivy/SAST,
environment approval, Operator Go execution, protected merge behavior or
deployment. Those require the real acceptance run above. The pilot is NOT
validated for replication.