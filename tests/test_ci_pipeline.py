import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml


spec = importlib.util.spec_from_file_location(
    "ci_pipeline", Path(__file__).resolve().parents[1] / "scripts/ci_pipeline.py"
)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


class PipelineTests(unittest.TestCase):
    def test_workflow_dependency_and_queue_contract(self):
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / ".github/workflows/ci-release.yml").read_text())
        jobs = workflow["jobs"]
        self.assertEqual(jobs["release"]["concurrency"]["queue"], "max")
        self.assertFalse(jobs["release"]["concurrency"]["cancel-in-progress"])
        self.assertEqual(jobs["ci-required"]["needs"], ["validate"])
        self.assertEqual(jobs["release"]["needs"], ["ci-required"])
        self.assertEqual(jobs["release"]["environment"], "quay-release")
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        gate = yaml.safe_load((root / ".github/workflows/governance.yml").read_text())
        for step in gate["jobs"]["check-flow"]["steps"]:
            self.assertNotIn("run", step)
            self.assertTrue(step["uses"].startswith("actions/github-script@"))

    def test_branch_matrix_and_repository_identity(self):
        for base in ("develop", "main", "stage"):
            for source in ("feature/a", "fix/a", "develop", "main", "feature/", "fix/", "other/a"):
                for fork in (False, True):
                    with self.subTest(base=base, source=source, fork=fork):
                        pr = {
                            "base": {"ref": base, "repo": {"full_name": pipeline.REPOSITORY}},
                            "head": {"ref": source, "repo": {"full_name": "attacker/fork" if fork else pipeline.REPOSITORY}},
                        }
                        expected = not fork and (
                            base == "develop" and source in ("feature/a", "fix/a") or
                            base == "main" and source in ("develop", "fix/a")
                        )
                        self.assertEqual(pipeline.allowed_pr(pr), expected)
                        pr["base"]["repo"]["full_name"] = "attacker/fork"
                        self.assertFalse(pipeline.allowed_pr(pr))

    def test_patch_uses_existing_release_history(self):
        self.assertEqual(pipeline.next_version("1.0.0", ["1.0.2", "1.0.5"]), "1.0.6")
        self.assertEqual(pipeline.next_version("1.4.7", []), "1.4.8")
        with self.assertRaises(ValueError):
            pipeline.next_version("1.0.0", ["2.0.0"])

    def test_only_project_version_changes(self):
        text = '[project]\nname = "test"\nversion = "1.0.0"\n'
        self.assertEqual(pipeline.replace_version(text, "1.0.6"), text.replace("1.0.0", "1.0.6"))

    def test_operator_update_is_scoped_and_idempotent(self):
        original = ('CoreAIImage: registryImage(constants.CoreAIName),\n'
                    'ReporterImage: registryImage(constants.ReporterName),\n')
        reference = pipeline.IMAGE + ":1.0.6@sha256:" + "a" * 64
        result = pipeline.operator_image(original, reference)
        self.assertIn('ReporterImage: registryImage(constants.ReporterName),', result)
        self.assertIn(reference, result)
        self.assertEqual(pipeline.operator_image(result, reference), result)
        with self.assertRaises(ValueError):
            pipeline.operator_image("unexpected contract", reference)

    def test_release_reservation_survives_a_fresh_checkout(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            first = root / "first"
            second = root / "second"
            subprocess.check_call(["git", "init", "--bare", str(remote)], stdout=subprocess.DEVNULL)
            subprocess.check_call(["git", "clone", str(remote), str(first)], stdout=subprocess.DEVNULL)
            try:
                os.chdir(first)
                pipeline.run("git", "config", "user.name", "CI Test")
                pipeline.run("git", "config", "user.email", "ci@example.invalid")
                Path("pyproject.toml").write_text('[project]\nname = "test"\nversion = "1.0.0"\n')
                pipeline.run("git", "add", "pyproject.toml")
                pipeline.run("git", "commit", "-m", "Initial source")
                pipeline.run("git", "tag", "v1.0.5")
                pipeline.run("git", "push", "origin", "HEAD:refs/heads/main", "--tags")
                source = pipeline.run("git", "rev-parse", "HEAD")
                with patch.object(pipeline, "verify_source"), patch.object(pipeline, "output") as first_output:
                    pipeline.reserve(source)
                self.assertEqual(first_output.call_args.kwargs["version"], "1.0.6")
                subprocess.check_call(["git", "clone", "--branch", "main", str(remote), str(second)], stdout=subprocess.DEVNULL)
                os.chdir(second)
                with patch.object(pipeline, "verify_source"), patch.object(pipeline, "output") as second_output:
                    pipeline.reserve(source)
                self.assertEqual(first_output.call_args, second_output.call_args)
                self.assertEqual(pipeline.run("git", "tag", "--list"), "v1.0.5\nv1.0.6")
                self.assertIn('version = "1.0.6"', Path("pyproject.toml").read_text())
            finally:
                os.chdir(previous)

    def test_release_requires_merged_pr_identity(self):
        source = "a" * 40
        pr = {
            "merged_at": "2026-10-19T00:00:00Z", "merge_commit_sha": source,
            "base": {"ref": "main", "repo": {"full_name": pipeline.REPOSITORY}},
            "head": {"ref": "fix/test", "repo": {"full_name": pipeline.REPOSITORY}},
        }
        with patch.object(pipeline, "run"), patch.object(pipeline, "api", return_value=[pr]):
            pipeline.verify_source(source)
            pr["head"]["repo"]["full_name"] = "attacker/fork"
            with self.assertRaises(ValueError):
                pipeline.verify_source(source)