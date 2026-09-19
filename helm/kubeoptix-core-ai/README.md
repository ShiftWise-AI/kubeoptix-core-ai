# Helm chart — kubeoptix-core-ai

This Helm chart installs KubeOptix Core AI on OpenShift as a **single-instance StatefulSet** (`scalePolicy.maxReplicas: 1`).

## Architecture

| Resource | Configuration |
|----------|---------------|
| Workload | `StatefulSet`; replicas controlled by `scalePolicy.maxReplicas` |
| API service | `ClusterIP` (`service.api`) |
| External exposure | None (no Route/Ingress) |
| Persistence | Existing PVC `harvester-app-data` mounted at `/app/data` |
| Build | `BuildConfig` + `ImageStream` when `build.enabled=true` |

## Prerequisites

1. OpenShift 4.x with the default `restricted` SCC.
2. PVC `harvester-app-data` already exists in the target namespace.
3. Git secret for the BuildConfig (never keep this in `values.example.yaml`):

```bash
oc create secret generic github-auth   --from-literal=username=<user>   --from-literal=password=<token>   --type=kubernetes.io/basic-auth   -n shiftwise-ai
```

## Installation

```bash
cp ./helm/kubeoptix-core-ai/values.example.yaml ./my-values.yaml
# adjust build.git.uri, build.git.ref, image.repository, and namespace.name

helm lint ./helm/kubeoptix-core-ai -f ./my-values.yaml
helm template kubeoptix-core-ai ./helm/kubeoptix-core-ai -f ./my-values.yaml

./install.sh -f ./my-values.yaml
```

`install.sh` always installs into the `shiftwise-ai` namespace and triggers `oc start-build` when the chart creates a BuildConfig. After installation, the script also performs cleanup of orphaned resources from the same release (for example, ConfigMaps, Secrets, certificates, and routes that are no longer part of the current manifest). A successful installation also removes completed builds (`status=Complete`) from the BuildConfig of the release.

To disable orphan cleanup for a specific run, use `-x`:

```bash
./install.sh -f ./my-values.yaml -x
```

## Image build (OpenShift)

The project uses a **Containerfile** (UBI 10). With `build.enabled=true`, the chart creates `BuildConfig` + `ImageStream`, and `install.sh` runs the build automatically:

```bash
./install.sh -f ./my-values.yaml
```

After `oc start-build --wait`, the script waits for the `ImageStreamTag` from the BuildConfig before restarting the StatefulSet, which reduces pull failures such as `manifest unknown`. When `image.useBuildOutput=true`, the pod template also watches that `ImageStreamTag`, so later successful builds trigger a rollout automatically.

Manual rebuild:

```bash
oc start-build kubeoptix-core-ai --wait -n shiftwise-ai
oc rollout restart statefulset/kubeoptix-core-ai -n shiftwise-ai
```

## Environment variables (`podEnv`)

| Variable | Default value |
|----------|---------------|
| `TZ` | `America/Sao_Paulo` |
| `LOG_LEVEL` | `INFO` |
| `PORT` | `8000` |
| `HOME` | `/tmp` |
| `KUBECONFIG` | `/tmp/.kube/config` |
| `KUBEOPTIX_METADATA_DIR` | `/app/data/assessment` |
| `KUBEOPTIX_OUTPUT_DIR` | `/app/data/reports` |

The container uses the image `CMD` (`python api.py`).

## Analysis API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/analysis` | Analyzes one or more namespaces and writes reports to `KUBEOPTIX_OUTPUT_DIR` |

Example:

```bash
oc exec -n shiftwise-ai statefulset/kubeoptix-core-ai --   curl -sS -X POST "http://127.0.0.1:8000/analysis"   -H "Content-Type: application/json"   -d '{"namespaces": ["example-ns-prd"]}'
```

Full API documentation: [`docs/api.md`](../../docs/api.md).

## Health checks

| Probe | Endpoint |
|-------|----------|
| `startupProbe` | `GET /health/live` |
| `livenessProbe` | `GET /health/live` |
| `readinessProbe` | `GET /health/ready` |

## Single-instance deployment

This application **does not support multiple replicas**. Keep `scalePolicy.maxReplicas: 1` and do not create HPA, KEDA, or any autoscaling configuration.

## Security

- Compatible with OpenShift `restricted` SCC (do not force `runAsUser` or `fsGroup` in the chart values).
- `readOnlyRootFilesystem` is not enforced in the chart (PVC and `/tmp` require write access).
- `automountServiceAccountToken: false` (no cluster API access).
