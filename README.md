# kubeoptix-core-ai

Local OpenShift/Kubernetes workload assessment agent. It ingests YAML metadata
collected from a cluster, normalizes workloads and related resources, applies
deterministic rules, and optionally runs a local statistical/ML layer to flag
atypical profiles inside a namespace.

Assessment output is a structured Markdown report with findings,
visualizations, recommendations, and explicit confidence levels for each item.

## Requirements

- Python 3.12+
- CPU only — no GPU, no external LLM, no paid APIs, no network at runtime
- **matplotlib** — numeric and composition charts (included in dependencies)
- **KubeDiagrams + Graphviz** — architecture diagrams (CLI `kube-diagrams`; installed in the container; see below for local development)

### Architecture diagrams

The report invokes the [KubeDiagrams](https://github.com/philippemerle/KubeDiagrams) CLI (`kube-diagrams`).
It requires Graphviz `dot` in PATH.

```bash
# Fedora/RHEL
sudo dnf install graphviz

# KubeDiagrams CLI (pygraphviz 2.0.1 has a wheel; KubeDiagrams pins 1.14 in metadata)
pip install pygraphviz==2.0.1
pip install --no-deps KubeDiagrams==0.8.0
pip install diagrams graphviz2drawio
```

In the **container** (Containerfile), the CLI is installed automatically with this workaround.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

The CLI reads a metadata directory containing one directory per namespace and a
`worknodes/` directory. A namespace directory may contain workload controllers,
pods, PodMetrics, services, routes, ConfigMaps, PVCs, autoscalers, PDBs, events,
pod logs, and OLM resources in the layout produced by the cluster collection
process. Files that are absent are reported as unavailable; the analyzer does
not invent runtime data.

```bash
# List available namespaces
kubeoptix-core-ai list-namespaces

# Inspect parsed workloads and worknodes
kubeoptix-core-ai load-workloads --namespace my-namespace-prd
kubeoptix-core-ai load-worknodes

# Ingestion diagnostics (no operational findings)
kubeoptix-core-ai diagnose --namespace my-namespace-prd

# Full analysis (deterministic + local ML)
kubeoptix-core-ai analyze --namespace my-namespace-prd

# Deterministic rules only
kubeoptix-core-ai analyze --namespace my-namespace-prd --no-ml

# Reproducible seed for K-Means and Isolation Forest
kubeoptix-core-ai analyze --namespace my-namespace-prd --ml-seed 42

# JSON output
kubeoptix-core-ai analyze --namespace my-namespace-prd --json

# Markdown assessment report
kubeoptix-core-ai report --namespace my-namespace-prd --output output/

# Batch: all namespaces under a metadata directory
./run.sh /path/to/metadata /path/to/output
```

The `load-workloads`, `load-worknodes`, `diagnose`, and `analyze` commands
support `--json` for machine-readable output. Use `--metadata-dir
/path/to/metadata` to configure a metadata tree in one option, or use
`--workloads-base` and `--worknodes-path` separately. The `run` command requires
`--metadata-dir` and `--output`; `run.sh` is a convenience wrapper for that
command.

### Operational log benchmark

The project includes a deterministic benchmark for operational failure patterns in
pod logs, such as DNS/service lookup errors (`ENOTFOUND`, `fetch failed`), HTTP
5xx responses, and PostgreSQL local `trust` authentication. This is intentional
and local-only; it does not depend on any external LLM or API.

```bash
python3 scripts/benchmark_log_signals.py
```

The benchmark reads the assessment corpus under `../base-treinamento/assessment/shiftwise-ai`
and reports precision, recall, and F1 for the expected operational signals.

The deterministic layer also correlates runtime DNS failures with service names declared in
ConfigMaps and workload env values, such as `ANALYZER_API_URL=http://analyzer-api:8000`,
which helps distinguish a genuine missing backend from a transient startup-order problem.

### Structural report parity benchmark

To compare the generated report with the analyzer reference and verify that the
report keeps the same section flow, architecture block and action plan structure,
run:

```bash
python3 scripts/benchmark_report_structure.py
```

This check is deterministic and local-only: it measures how close the generated
Markdown is to the structural reference without relying on any external LLM or
generative model.

### Environment variables

| Variable | Description |
|----------|-------------|
| `KUBEOPTIX_WORKLOADS_BASE` | Base directory for namespace metadata |
| `KUBEOPTIX_WORKNODES_PATH` | Directory of worknode YAML files |
| `KUBEOPTIX_ML_ENABLED` | `true`/`false` — enable the ML layer (default: `true`) |
| `KUBEOPTIX_ML_SEED` | Random seed for stochastic algorithms (default: `42`) |

The HTTP API uses `KUBEOPTIX_METADATA_DIR` and `KUBEOPTIX_OUTPUT_DIR` instead of
the CLI's relative defaults. In the container these default to
`/app/data/assessment` and `/app/data/reports`.

## Architecture

```
YAML → parsers → Pydantic models
                    ↓
         ┌──────────┴──────────┐
         ↓                     ↓
  Deterministic analysis   Local ML layer (optional)
  (absolute rules)         (statistical signals)
         └──────────┬──────────┘
                    ↓
              AnalysisReport
                    ↓
         Markdown report + visualizations
```

The deterministic layer handles verifiable facts such as missing requests,
usage above request, and missing probes. The ML layer adds relative comparisons
within the namespace; it **never replaces** simple rules when those are more
reliable.

## AI techniques

> **Important:** this project does **not** use generative AI or external LLMs.
> All “AI” runs locally on CPU, offline, on structured numeric features extracted
> from ingested YAML and PodMetrics.

The optional ML layer (`src/kubeoptix_core_ai/ml/`) complements deterministic
rules. It is disabled with `--no-ml` or `KUBEOPTIX_ML_ENABLED=false`.

| Technique | Module | Purpose |
|-----------|--------|---------|
| Robust z-score (median/MAD) and IQR | `ml/statistics.py` | Univariate outliers resistant to extremes (Tukey fences) |
| Euclidean distance to centroid | `ml/comparison.py` | Workloads farthest from the namespace profile; divergent pairs |
| Isolation Forest | `ml/anomalies.py` | Multivariate anomalies (unusual feature combinations) |
| K-Means | `ml/clustering.py` | Natural resource-profile groups for right-sizing comparison |
| Cosine similarity | `ml/similarity.py` | Similar numeric profiles for in-namespace benchmarking |

**Feature vector:** each workload is encoded as a fixed 14-dimensional vector
(requests, limits, replicas, probes, scheduling flags, usage/request ratios when
PodMetrics exist). See `FEATURE_NAMES` in `ml/features.py`.

**Execution order:** statistics → comparison → anomalies → clustering →
similarity.

**Explicitly not used** (evaluated and rejected for this use case):

- Text embeddings and semantic similarity over YAML
- TF-IDF on manifest text
- pandas (namespace-scale data fits lists/NumPy)
- External model APIs or cloud inference

ML findings use IDs `ML-<CATEGORY>-NNN`, categories `MLSTAT`, `MLCOMP`,
`MLANOM`, `MLCLUST`, `MLSIM`, and are tagged with the standard limitation:
*statistical outlier ≠ operational defect*.

Further detail: [`src/kubeoptix_core_ai/ml/README.md`](src/kubeoptix_core_ai/ml/README.md).

## Report confidence model

Every finding in the assessment report carries a **confidence** grade. The report
as a whole is designed so readers can separate **evidence**, **analysis**,
**recommendation**, and **limitations** — and judge how much to trust each item.

### Per-finding confidence

| Level | Meaning | Typical source |
|-------|---------|----------------|
| **HIGH** | Direct evidence in ingested artifacts (Deployment YAML, Pod status, PodMetrics snapshot) | Deterministic rules: missing probes, request/limit values, usage vs request in a single metrics snapshot |
| **MEDIUM** | Supported inference with partial or contextual data | Scheduling heuristics, inventory checks, ML statistics/comparison/anomaly signals |
| **LOW** | Hypothesis with limited evidence | Some clustering outliers, sparse namespace comparisons |

Deterministic findings (`RES-<CATEGORY>-NNN`) usually score **HIGH** when the
checked field is present in collected YAML or metrics. ML findings (`ML-*`) are
capped at **MEDIUM** or **LOW** and use lower severities (INFO/LOW) by design.

### What the report guarantees

- **Traceability:** findings link to source files and field paths when available.
- **No invented data:** missing metrics, events, or secret content are stated
  explicitly in the limitations section rather than inferred.
- **Terminology discipline:** configured *request/limit* is never labeled as
  measured *usage*; PodMetrics usage is labeled as a point-in-time snapshot.
- **Actionable vs exploratory:** recommendations in §19 link back to detailed
  findings; ML signals in §16 are indexed as investigation hints, not confirmed
  defects.

### Overall trust boundaries

The produced report is **high confidence for configuration facts** present in
the dump and **moderate confidence for sizing and optimization advice** that
depends on a single PodMetrics snapshot without historical series. Validation
with 7–30 days of metrics before production changes is recommended in the
report conclusion when runtime data exists.

Disable the ML layer (`--no-ml`) for a **fully rule-based report** with the
highest per-item confidence — at the cost of missing relative/statistical signals
within the namespace.

## Tests

```bash
pytest
```

## HTTP API

REST endpoints for health checks and namespace analysis are documented in
[`docs/api.md`](docs/api.md). Interactive OpenAPI docs are available at `/docs`
and `/redoc` when running `python api.py`.

Start the API locally with:

```bash
KUBEOPTIX_METADATA_DIR=/path/to/metadata \
KUBEOPTIX_OUTPUT_DIR=/path/to/output \
python api.py
```

The container exposes port `8000`; `KUBEOPTIX_API_HOST` and
`KUBEOPTIX_API_PORT` control the bind address and port. For OpenShift, use
`run-ocp.sh` to generate reports from the configured data directories. The
application runs without an external LLM, cloud inference service, or network
access at runtime.

## Agent specification

Methodology and report format:
[`kubeoptix-core-ai-agent-spec/`](kubeoptix-core-ai-agent-spec/).
