# REST API — KubeOptix Core AI

The HTTP API is served by `api.py` (FastAPI + Uvicorn). The interactive documentation is available under `/docs` (Swagger UI) and `/redoc` while the server is running.

## Running the service

```bash
KUBEOPTIX_METADATA_DIR=/path/to/metadata KUBEOPTIX_OUTPUT_DIR=/path/to/reports python api.py
```

The server binds to `0.0.0.0:8000` by default. `KUBEOPTIX_API_HOST` and `KUBEOPTIX_API_PORT` override the address and port. In containers or OpenShift, the defaults are `/app/data/assessment` for metadata and `/app/data/reports` for generated reports.

## Data layout

`KUBEOPTIX_METADATA_DIR` must contain one folder per namespace and a `worknodes/` folder either under the same directory or in the parent directory. Each namespace is validated against the Kubernetes naming convention (`[a-z0-9.-]`) and may include YAMLs from controllers, pods, PodMetrics, services, routes, ConfigMaps, PVCs, autoscalers, PDBs, events, logs, and OLM resources. The loader correlates these resources before analysis. Missing categories are recorded as limitations rather than being fabricated.

## Health endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health/live` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe |
| `GET` | `/health` | Overall status |

`/health/ready` checks whether the working directory and `/tmp` are usable and, when configured, whether the file pointed to by `MARK_DOWN_FILE` is available. It returns `200` when all checks are `UP` and `503` otherwise.

## Namespace analysis

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/analysis` | Runs the analysis and writes Markdown reports |

### Data directories

| Variable | Default | Usage |
|----------|---------|-------|
| `KUBEOPTIX_METADATA_DIR` | `/app/data/assessment` | Namespace and worknode metadata |
| `KUBEOPTIX_OUTPUT_DIR` | `/app/data/reports` | Destination for generated `.md` reports |
| `SYSTEM_SETTINGS_URL` | `http://localhost:8000/system-settings` | Full endpoint used to resolve the report locale; use `http://configurations-api:8000/system-settings` in OpenShift |

Before analysis starts, the service reads `language` from `SYSTEM_SETTINGS_URL`.
Markdown
reports accept only the exact BCP 47 locales `pt-BR`, `en-US`, `es-ES`, and `it-IT`.
Missing, empty, unsupported, or unavailable settings stop report generation with an
explicit configuration error; no language fallback is applied.

### `POST /analysis`

Runs analysis for one or more namespaces provided in the request. For each valid namespace, it writes a Markdown report to `KUBEOPTIX_OUTPUT_DIR`. The output directory is created automatically if it does not exist.

#### Request body

```json
{
  "namespaces": ["example-ns-prd"],
  "enable_ml": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `namespaces` | `string[]` | Yes | At least one namespace |
| `enable_ml` | `boolean` | No | Enables or disables the local ML layer (default: environment variable) |

#### Response `201 Created`

```json
{
  "status": "SUCCESS",
  "reports": [
    {
      "namespace": "example-ns-prd",
      "report_path": "/app/data/reports/example-ns-prd.md",
      "workloads_analyzed": 3,
      "finding_count": 12
    }
  ]
}
```

#### Multiple namespaces

```json
{
  "namespaces": ["example-ns-prd", "other-ns-prd"]
}
```

The response includes one report per namespace. Report filenames are `<namespace>.md` (for example, `example-ns-prd.md`).

#### Errors

| HTTP | Situation | Example body |
|------|-----------|--------------|
| `422` | Missing, empty, or blank namespace list | Pydantic validation |
| `400` | Invalid namespace name | `{"detail": {"message": "Invalid namespace name: ..."}}` |
| `404` | Namespace is not present in the assessment metadata | `{"detail": {"message": "...", "missing_namespaces": ["foo"]}}` |
| `500` | Analysis failure | `{"detail": {"message": "..."}}` |

#### Example with `curl`

```bash
curl -sS -X POST "http://localhost:8000/analysis"   -H "Content-Type: application/json"   -d '{"namespaces": ["example-ns-prd", "other-ns-prd"], "enable_ml": false}'
```

## Asynchronous generation with progress

`POST /analysis` is synchronous: the response returns only after the `.md` file is written. To let a frontend display a 0–100% progress bar, use the asynchronous flow:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/reports` | Starts background analysis and returns `execution_id` |
| `GET` | `/api/reports/{execution_id}/status` | Retrieves progress, status, and report path |

The state lives in the API process memory (appropriate for a single-instance deployment).

### `POST /api/reports`

Uses the same body as `POST /analysis`. Namespace validation occurs in the initial request (same `404`/`400` behavior). The heavy analysis runs in the background. When `enable_ml` is omitted, it defaults to `true`.

#### Response `202 Accepted`

```json
{
  "execution_id": "a1b2c3d4e5f6...",
  "status": "pending",
  "progress": 0,
  "current_stage": "",
  "current_file": null,
  "phase": "",
  "running": false,
  "files_processed": 0,
  "files_total": 0
}
```

`phase`, `running`, `files_processed`, and `files_total` are aliases of `current_stage`,
`status`, `processed`, and `total` respectively, matching the payload shape used by the
kubeoptix-analyzer `/analysis/status` endpoint so frontend polling code can share the
same field names across both backends.

### `GET /api/reports/{execution_id}/status`

The frontend can poll every 1–2 seconds. The `progress` field is an integer `0 <= progress <= 100`. A value of `100` appears only after the `.md` file has been written.

#### In progress

```json
{
  "execution_id": "a1b2c3d4e5f6...",
  "status": "running",
  "progress": 45,
  "message": "Analyzing YAML files",
  "processed": 45,
  "total": 100,
  "report": null,
  "current_stage": "Data collection",
  "current_file": "deployment-prod.yaml",
  "phase": "Data collection",
  "running": true,
  "files_processed": 45,
  "files_total": 100
}
```

#### Completed

```json
{
  "execution_id": "a1b2c3d4e5f6...",
  "status": "completed",
  "progress": 100,
  "message": "Report generated successfully",
  "processed": 100,
  "total": 100,
  "report": "/app/data/reports/example-ns-prd.md",
  "current_stage": "Finalization",
  "current_file": "deployment-prod.yaml",
  "phase": "Finalization",
  "running": false,
  "files_processed": 100,
  "files_total": 100
}
```

#### Error

```json
{
  "execution_id": "a1b2c3d4e5f6...",
  "status": "error",
  "progress": 67,
  "message": "Error during YAML analysis",
  "processed": 40,
  "total": 60,
  "report": null,
  "error": "error message",
  "current_stage": "Data collection",
  "current_file": "deployment-prod.yaml",
  "phase": "Data collection",
  "running": false,
  "files_processed": 40,
  "files_total": 60
}
```

Possible states: `pending`, `running`, `completed`, `error`.

#### How progress is calculated

Breakpoints by namespace, over the real pipeline (without synthetic values):

| Local progress | Stage |
|---------------|-------|
| 0% | execution started |
| 10% | YAML files identified (`scan_namespace_files`) |
| 20%–70% | read/parse of each YAML (`(processed / total) * 50`) |
| 70%–80% | deterministic analysis (and ML, if enabled) |
| 90% | Markdown generation |
| 100% | `.md` file written |

With multiple namespaces, each namespace receives an equal slice of the overall 0–100 range.
The `current_file` field contains only the basename of the file currently being parsed,
or `null` when no file has started. The `current_stage` field identifies the last
published pipeline stage. On errors, the last known stage and file are retained.

#### Example with `curl`

```bash
EXEC_ID=$(curl -sS -X POST "http://localhost:8000/api/reports"   -H "Content-Type: application/json"   -d '{"namespaces": ["example-ns-prd"], "enable_ml": false}'   | python -c 'import json,sys; print(json.load(sys.stdin)["execution_id"])')

curl -sS "http://localhost:8000/api/reports/${EXEC_ID}/status"
```
