# Local AI / statistical layer

This is an **optional** and **secondary** analysis layer compared with the deterministic rules. It runs **100% offline**, on CPU, without an external LLM or paid API.

## Dependencies and rationale

| Library | Used for | Why |
|---------|----------|-----|
| `statistics` | robust z-score (MAD), IQR, quantiles | standard library; robust to extreme outliers |
| `numpy` | feature matrices | lightweight vector operations |
| `scikit-learn` | Isolation Forest, K-Means, scaler | mature algorithms with reproducible `random_state` |

**Not added** (evaluated and rejected for this phase):

- **pandas** — namespace-scale data is small; lists and NumPy are sufficient.
- **sentence-transformers / FAISS** — features are structured numeric values; semantic similarity on names is not operational proof.
- **TF-IDF over YAML** — no value against resource-based feature vectors.

## Execution order

1. **Statistics** (`ml/statistics.py`) — robust z-score (median/MAD) and IQR per feature.
2. **Comparison** (`ml/comparison.py`) — centroid distance and divergent pairs.
3. **Anomalies** (`ml/anomalies.py`) — multivariate Isolation Forest.
4. **Clustering** (`ml/clustering.py`) — K-Means by resource profile.
5. **Similarity** (`ml/similarity.py`) — cosine similarity between standardized vectors.

## Features (`ml/features.py`)

Each workload becomes a fixed 14-dimensional vector (requests, limits, replicas, probes, scheduling flags, usage/request ratios when PodMetrics exist). See `FEATURE_NAMES` and `FEATURE_DESCRIPTIONS` in the code.

## Reproducibility

- `MLConfig.random_seed` (default `42`, environment variable `KUBEOPTIX_ML_SEED`).
- `KUBEOPTIX_ML_ENABLED=false` or CLI `--no-ml` disables the layer.
- ML findings use IDs `ML-<CATEGORY>-NNN` and MEDIUM/LOW confidence.

## Principle

> A statistical outlier is not a defect. Use it as an investigation signal, not as a substitute for deterministic rules such as “missing request” or “usage > limit”.

Finding categories: `MLSTAT`, `MLCOMP`, `MLANOM`, `MLCLUST`, `MLSIM`.
