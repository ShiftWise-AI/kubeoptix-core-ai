import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib


REPOSITORY = "ShiftWise-AI/kubeoptix-core-ai"
OPERATOR = "ShiftWise-AI/kubeoptix-operator"
IMAGE = "quay.io/parraes/kubeoptix-core-ai"
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def api(path, method="GET", payload=None):
    command = ["gh", "api", path, "--method", method]
    if payload is not None:
        command += ["--input", "-"]
    return json.loads(subprocess.check_output(
        command, input=None if payload is None else json.dumps(payload), text=True
    ))


def allowed_pr(pr, repository=REPOSITORY):
    base = pr.get("base", {})
    head = pr.get("head", {})
    if (base.get("repo") or {}).get("full_name") != repository:
        return False
    if (head.get("repo") or {}).get("full_name") != repository:
        return False
    source = head.get("ref", "")
    if base.get("ref") == "develop":
        return bool(re.fullmatch(r"(?:feature|fix)/[^\s]+", source))
    if base.get("ref") == "main":
        return source == "develop" or bool(re.fullmatch(r"fix/[^\s]+", source))
    return False


def version_tuple(value):
    if not SEMVER.fullmatch(value):
        raise ValueError(f"Invalid MAJOR.MINOR.PATCH: {value}")
    return tuple(map(int, value.split(".")))


def next_version(current, released):
    baseline = version_tuple(current)
    versions = [version_tuple(value) for value in released]
    if any(value[:2] > baseline[:2] for value in versions):
        raise ValueError("Source major/minor is older than an existing release")
    patch = max([baseline[2]] + [value[2] for value in versions if value[:2] == baseline[:2]])
    return f"{baseline[0]}.{baseline[1]}.{patch + 1}"


def replace_version(text, version):
    document = tomllib.loads(text)
    old = document["project"]["version"]
    version_tuple(old)
    updated, count = re.subn(
        rf'(?m)^version = "{re.escape(old)}"$', f'version = "{version}"', text
    )
    if count != 1 or tomllib.loads(updated)["project"]["version"] != version:
        raise ValueError("Expected exactly one project version assignment")
    return updated


def operator_image(text, reference):
    updated, count = re.subn(
        r'(?m)^(\s*CoreAIImage:\s+)(?:registryImage\(constants.CoreAIName\)|"[^"\n]+"),$',
        lambda match: f'{match[1]}"{reference}",', text,
    )
    if count != 1:
        raise ValueError("Operator CoreAIImage contract changed; refusing broad edits")
    return updated


def verify_source(source):
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("Expected full source commit SHA")
    run("git", "merge-base", "--is-ancestor", source, "origin/main")
    prs = api(f"repos/{REPOSITORY}/commits/{source}/pulls?per_page=100")
    if not any(pr.get("merged_at") and pr.get("merge_commit_sha") == source
               and pr["base"]["ref"] == "main" and allowed_pr(pr) for pr in prs):
        raise ValueError("Release source must be the merge commit of an allowed same-repository PR to main")


def output(**values):
    with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")


def reserve(source):
    verify_source(source)
    tags = run("git", "tag", "--list", "v*").splitlines()
    releases = [tag[1:] for tag in tags if SEMVER.fullmatch(tag[1:])]
    marker = f"Release-Source: {source}"
    matches = [tag for tag in tags if SEMVER.fullmatch(tag[1:]) and
               marker in run("git", "for-each-ref", "--format=%(contents)", f"refs/tags/{tag}").splitlines()]
    if len(matches) > 1:
        raise ValueError("Multiple releases reserved for the same source")
    if matches:
        tag = matches[0]
        document = tomllib.loads(run("git", "show", f"{tag}:pyproject.toml"))
        if document["project"]["version"] != tag[1:]:
            raise ValueError("Reserved release version does not match pyproject.toml")
        if run("git", "rev-parse", f"{tag}^1") != source:
            raise ValueError("Reserved release has an unexpected source parent")
    else:
        run("git", "checkout", "--detach", source)
        path = Path("pyproject.toml")
        version = next_version(tomllib.loads(path.read_text())["project"]["version"], releases)
        path.write_text(replace_version(path.read_text(), version))
        run("git", "add", "pyproject.toml")
        run("git", "commit", "-m", f"Release {version}\n\n{marker}")
        tag = f"v{version}"
        run("git", "tag", "-a", tag, "-m", marker)
        run("git", "push", "origin", f"refs/tags/{tag}")
    run("git", "checkout", "--detach", tag)
    output(version=tag[1:], tag=tag, source=source,
           commit=run("git", "rev-parse", "HEAD"))


def update_operator(version, digest, directory):
    version_tuple(version)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Invalid registry digest")
    reference = f"{IMAGE}:{version}@{digest}"
    root = Path(directory).resolve()
    branch = f"fix/core-ai-{version}"
    remote_branches = run("git", "ls-remote", "--heads", "origin", branch, cwd=root)
    if remote_branches:
        run("git", "fetch", "origin", branch, cwd=root)
        run("git", "checkout", "--detach", "FETCH_HEAD", cwd=root)
    path = root / "internal/operands/settings.go"
    before = path.read_text()
    after = operator_image(before, reference)
    if after != before:
        path.write_text(after)
        run("gofmt", "-w", str(path))
    probe = root / "internal/operands/ci_release_test.go"
    if probe.exists():
        raise ValueError("Refusing to overwrite an existing Operator test")
    probe.write_text('package operands\nimport "testing"\n'
                     'func TestCIReleaseImage(t *testing.T) {\n'
                     f'if got := FromCR(newShiftWise()).CoreAIImage; got != "{reference}" {{\n'
                     't.Fatalf("unexpected CoreAI image: %s", got)\n}\n}\n')
    try:
        run("go", "test", "./internal/operands", cwd=root)
    finally:
        probe.unlink()
    changed = run("git", "diff", "--name-only", cwd=root).splitlines()
    if changed not in ([], ["internal/operands/settings.go"]):
        raise ValueError("Unexpected Operator changes")
    if changed:
        run("git", "checkout", "-B", branch, cwd=root)
        run("git", "add", "internal/operands/settings.go", cwd=root)
        run("git", "commit", "-m", f"fix: pin Core AI to {version}", cwd=root)
        run("git", "push", "origin", f"HEAD:refs/heads/{branch}", cwd=root)
    elif not remote_branches:
        return
    existing = api(f"repos/{OPERATOR}/pulls?state=open&head=ShiftWise-AI:{branch}&base=main")
    if not existing:
        api(f"repos/{OPERATOR}/pulls", "POST", {
            "title": f"fix: update Core AI to {version}", "head": branch, "base": "main",
            "body": f"Published and verified image: `{reference}`.\n\nOnly the Core AI default changes; Operator and other component versions remain unchanged.",
        })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["reserve", "operator"])
    parser.add_argument("--source")
    parser.add_argument("--version")
    parser.add_argument("--digest")
    parser.add_argument("--directory", default="operator")
    args = parser.parse_args()
    if args.command == "reserve":
        reserve(args.source)
    else:
        update_operator(args.version, args.digest, args.directory)


if __name__ == "__main__":
    main()