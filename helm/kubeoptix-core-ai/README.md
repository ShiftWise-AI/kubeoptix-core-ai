# Helm Chart — kubeoptix-core-ai

Chart Helm para instalar o KubeOptix Core AI em OpenShift como **StatefulSet single-instance** (`scalePolicy.maxReplicas: 1`).

## Arquitetura

| Recurso | Configuração |
|---------|--------------|
| Workload | `StatefulSet`, réplicas via `scalePolicy.maxReplicas` |
| Service API | `ClusterIP` (`service.api`) |
| Exposição externa | Nenhuma (sem Route/Ingress) |
| Persistência | PVC existente `harvester-app-data` em `/app/data` |
| Build | `BuildConfig` + `ImageStream` quando `build.enabled=true` |

## Pré-requisitos

1. OpenShift 4.x com SCC padrão (restricted).
2. PVC `harvester-app-data` já criado no namespace de destino.
3. Secret Git para o BuildConfig (nunca em `values.example.yaml`):

```bash
oc create secret generic github-auth \
  --from-literal=username=<user> \
  --from-literal=password=<TOKEN_GIT> \
  --type=kubernetes.io/basic-auth \
  -n shiftwise-ai
```

## Instalação

```bash
cp ./helm/kubeoptix-core-ai/values.example.yaml ./my-values.yaml
# ajuste build.git.uri, build.git.ref, image.repository e namespace.name

helm lint ./helm/kubeoptix-core-ai -f ./my-values.yaml
helm template kubeoptix-core-ai ./helm/kubeoptix-core-ai -f ./my-values.yaml

./install.sh -f ./my-values.yaml
```

O `install.sh` instala sempre no namespace `shiftwise-ai` e dispara `oc start-build` quando o chart cria um BuildConfig.
Após a instalação, o script também executa cleanup de recursos órfãos do mesmo release (ex.: ConfigMaps, Secrets, certificados e rotas que ficaram fora do manifest atual).
Após uma instalação bem-sucedida, o script remove automaticamente builds concluídos (`status=Complete`) do BuildConfig do release.
Após o término, o script também remove os secrets de histórico Helm (`sh.helm.release.v1.<release>.*`) do namespace.
Para desabilitar apenas o cleanup de recursos órfãos em uma execução específica, use `-x`:

```bash
./install.sh -f ./my-values.yaml -x
```

## Build da imagem (OpenShift)

O projeto usa **Containerfile** (UBI 10). Com `build.enabled=true`, o chart cria `BuildConfig` + `ImageStream` e o `install.sh` executa o build automaticamente:

```bash
./install.sh -f ./my-values.yaml
```

Após o `oc start-build --wait`, o script aguarda a publicação da `ImageStreamTag` de saída do BuildConfig antes de reiniciar o StatefulSet, reduzindo falhas de pull com `manifest unknown`.

Para rebuild manual:

```bash
oc start-build kubeoptix-core-ai --wait -n shiftwise-ai
oc rollout restart statefulset/kubeoptix-core-ai -n shiftwise-ai
```

## Variáveis de ambiente (`podEnv`)

| Variável | Valor padrão |
|----------|--------------|
| `TZ` | `America/Sao_Paulo` |
| `LOG_LEVEL` | `INFO` |
| `PORT` | `8000` |
| `HOME` | `/tmp` |
| `KUBECONFIG` | `/tmp/.kube/config` |
| `KUBEOPTIX_METADATA_DIR` | `/app/data/assessment` |
| `KUBEOPTIX_OUTPUT_DIR` | `/app/data/reports` |

O container usa o `CMD` da imagem (`python api.py`).

## API de análise

| Método | Caminho | Descrição |
|--------|---------|-----------|
| `POST` | `/analysis` | Analisa um ou mais namespaces e grava relatórios em `KUBEOPTIX_OUTPUT_DIR` |

Exemplo:

```bash
oc exec -n shiftwise-ai statefulset/kubeoptix-core-ai -- \
  curl -sS -X POST "http://127.0.0.1:8000/analysis" \
  -H "Content-Type: application/json" \
  -d '{"namespaces": ["meu-namespace-prd"]}'
```

Documentação completa: [`docs/api.md`](../../docs/api.md).

## Health checks

| Probe | Endpoint |
|-------|----------|
| `startupProbe` | `GET /health/live` |
| `livenessProbe` | `GET /health/live` |
| `readinessProbe` | `GET /health/ready` |

## Single-instance

Esta aplicação **não suporta múltiplas réplicas**. Mantenha `scalePolicy.maxReplicas: 1` e não crie HPA, KEDA ou qualquer autoscaling.

## Segurança

- Compatível com SCC `restricted` do OpenShift (não fixar `runAsUser`/`fsGroup` no values).
- `readOnlyRootFilesystem` não é forçado no chart (PVC e `/tmp` precisam de escrita).
- `automountServiceAccountToken: false` (sem acesso à API do cluster).
