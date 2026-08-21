"""Parâmetros da camada de ML local."""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_ML_ENABLED = "KUBEOPTIX_ML_ENABLED"
ENV_ML_SEED = "KUBEOPTIX_ML_SEED"


@dataclass(frozen=True)
class MLConfig:
    """Configuração reproduzível da análise estatística / ML local.

    Algoritmos estocásticos (K-Means, Isolation Forest) usam ``random_seed``.
    """

    enabled: bool = True
    random_seed: int = 42
    # z-score robusto (mediana/MAD): limiar típico 3.5; valores menores = mais sensível
    zscore_threshold: float = 3.5
    # IQR: multiplicador clássico de Tukey para limites inferior/superior
    iqr_multiplier: float = 1.5
    # Fração esperada de outliers no Isolation Forest (auto quando None)
    isolation_contamination: float | str = "auto"
    # Similaridade de cosseno mínima para reportar par de workloads
    similarity_threshold: float = 0.90
    # Mínimos de workloads para cada técnica (abaixo disso, técnica é omitida)
    min_workloads_stat: int = 3
    min_workloads_anom: int = 5
    min_workloads_cluster: int = 3
    min_workloads_similarity: int = 2
    min_fleet_namespaces: int = 2
    min_fleet_workloads: int = 8

    @classmethod
    def from_env(cls) -> MLConfig:
        enabled_raw = os.environ.get(ENV_ML_ENABLED, "true").lower()
        enabled = enabled_raw in ("1", "true", "yes", "on")
        seed_raw = os.environ.get(ENV_ML_SEED, "42")
        return cls(
            enabled=enabled,
            random_seed=int(seed_raw),
        )
