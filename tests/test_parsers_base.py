"""Testes do carregamento base de YAML."""

from __future__ import annotations

from pathlib import Path

import pytest

from kubeoptix_core_ai.parsers.base import load_yaml_file
from kubeoptix_core_ai.parsers.csv import parse_packagemanifest


def test_load_yaml_file_quotes_sanitized_bracket_scalars(tmp_path: Path) -> None:
    yaml_file = tmp_path / "broken.yaml"
    yaml_file.write_text(
        "metadata:\n  name: example\nstatus:\n  crd:\n    name: [TOKEN_REMOVIDO].io\n",
        encoding="utf-8",
    )

    document = load_yaml_file(yaml_file)

    assert document["status"]["crd"]["name"] == "[TOKEN_REMOVIDO].io"


def test_parse_packagemanifest_with_sanitized_crd_names(tmp_path: Path) -> None:
    yaml_file = tmp_path / "operator.yaml"
    yaml_file.write_text(
        """apiVersion: packages.operators.coreos.com/v1
kind: PackageManifest
metadata:
  name: compliance-operator
status:
  defaultChannel: stable
  channels:
  - name: stable
    currentCSV: compliance-operator.v1.0.0
  packageName: compliance-operator
  customresourcedefinitions:
    owned:
    - description: ComplianceCheckResult
      kind: ComplianceCheckResult
      name: [TOKEN_REMOVIDO].io
      version: v1alpha1
""",
        encoding="utf-8",
    )

    package_name, default_channel, channel_csv = parse_packagemanifest(yaml_file)

    assert package_name == "compliance-operator"
    assert default_channel == "stable"
    assert channel_csv == "compliance-operator.v1.0.0"


@pytest.mark.parametrize(
    "yaml_text",
    [
        "items:\n- name: [a, b, c]\n",
        'url: https://example.com[TOKEN_REMOVIDO]/\n',
    ],
)
def test_load_yaml_file_preserves_valid_bracket_forms(
    tmp_path: Path, yaml_text: str
) -> None:
    yaml_file = tmp_path / "valid.yaml"
    yaml_file.write_text(yaml_text, encoding="utf-8")

    document = load_yaml_file(yaml_file)

    if "items" in document:
        assert document["items"] == [{"name": ["a", "b", "c"]}]
    else:
        assert document["url"] == "https://example.com[TOKEN_REMOVIDO]/"
