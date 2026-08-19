"""Testes da leitura tolerante de YAML de inventário."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.visualization.kubediagrams.yamlutil import (
    load_diagram_documents,
    sanitize_inventory_yaml,
)


def test_sanitize_inventory_yaml_quotes_placeholders() -> None:
    raw = (
        "uid: [RG_REMOVIDO]-0a35-4eff-90af-458990df5b00\n"
        "runAsUser: [TELEFONE_REMOVIDO]\n"
        "mixed: 1e6b5947-[TELEFONE_REMOVIDO]-9626\n"
        "groups:\n"
        "  - [TELEFONE_REMOVIDO]\n"
    )
    sanitized = sanitize_inventory_yaml(raw)
    assert 'uid: "[RG_REMOVIDO]-0a35-4eff-90af-458990df5b00"' in sanitized
    assert 'runAsUser: "[TELEFONE_REMOVIDO]"' in sanitized
    assert 'mixed: "1e6b5947-[TELEFONE_REMOVIDO]-9626"' in sanitized
    assert '- "[TELEFONE_REMOVIDO]"' in sanitized


def test_load_diagram_documents_recovers_projected_token_placeholder(
    tmp_path: Path,
) -> None:
    path = tmp_path / "kubeoptix-harvester-0.yaml"
    path.write_text(
        "apiVersion: v1\n"
        "kind: Pod\n"
        "metadata:\n"
        "  name: kubeoptix-harvester-0\n"
        "  labels:\n"
        "    app.kubernetes.io/name: kubeoptix-harvester\n"
        "  ownerReferences:\n"
        "  - apiVersion: apps/v1\n"
        "    controller: true\n"
        "    kind: StatefulSet\n"
        "    name: kubeoptix-harvester\n"
        "  uid: [RG_REMOVIDO]-0a35-4eff-90af-458990df5b00\n"
        "spec:\n"
        "  serviceAccountName: shiftwisea-ai-user\n"
        "  volumes:\n"
        "  - name: app-data\n"
        "    persistentVolumeClaim:\n"
        "      claimName: harvester-app-data\n"
        "  - name: kube-api-access\n"
        "    projected:\n"
        "      sources:\n"
        "      - [TOKEN_EXPLICITO_REMOVIDO]: 3607\n"
        "          path: token\n",
        encoding="utf-8",
    )
    documents = load_diagram_documents(path)
    assert len(documents) == 1
    document = documents[0]
    assert document["kind"] == "Pod"
    assert document["metadata"]["name"] == "kubeoptix-harvester-0"
    assert document["metadata"]["labels"]["app.kubernetes.io/name"] == "kubeoptix-harvester"
    owners = document["metadata"]["ownerReferences"]
    assert owners[0]["kind"] == "StatefulSet"
    assert owners[0]["name"] == "kubeoptix-harvester"
