# API REST — KubeOptix Core AI

A API HTTP é servida pelo `api.py` (FastAPI + Uvicorn). A documentação interativa
está disponível em `/docs` (Swagger UI) e `/redoc` quando o servidor está em execução.

## Endpoints de saúde

| Método | Caminho | Descrição |
|--------|---------|-----------|
| `GET` | `/health/live` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe |
| `GET` | `/health` | Status geral da aplicação |

## Análise de namespaces

| Método | Caminho | Descrição |
|--------|---------|-----------|
| `POST` | `/analysis` | Executa análise e gera relatórios Markdown |

### Diretórios de dados

| Variável | Padrão | Uso |
|----------|--------|-----|
| `KUBEOPTIX_METADATA_DIR` | `/app/data/assessment` | Metadados de namespaces e worknodes |
| `KUBEOPTIX_OUTPUT_DIR` | `/app/data/reports` | Destino dos relatórios `.md` gerados |

### `POST /analysis`

Executa a análise de **um ou mais namespaces** informados na requisição. Para cada
namespace válido, gera um relatório Markdown em `KUBEOPTIX_OUTPUT_DIR`. O diretório de
saída é criado automaticamente se não existir.

#### Request body

```json
{
  "namespaces": ["example-ns-prd"],
  "enable_ml": false
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `namespaces` | `string[]` | Sim | Lista com pelo menos um namespace |
| `enable_ml` | `boolean` | Não | Ativa/desativa a camada ML local (padrão: variável de ambiente) |

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

#### Múltiplos namespaces

```json
{
  "namespaces": ["example-ns-prd", "other-ns-prd"]
}
```

Resposta com um relatório por namespace. O nome do arquivo é `<namespace>.md`
(por exemplo, `example-ns-prd.md`).

#### Erros

| HTTP | Situação | Exemplo de corpo |
|------|----------|------------------|
| `422` | Lista ausente, vazia ou com strings em branco | Validação Pydantic |
| `400` | Nome de namespace inválido | `{"detail": {"message": "Nome de namespace inválido: ..."}}` |
| `404` | Namespace inexistente em assessment | `{"detail": {"message": "...", "missing_namespaces": ["foo"]}}` |
| `500` | Falha durante a análise | `{"detail": {"message": "..."}}` |

#### Exemplo com `curl`

```bash
curl -sS -X POST "http://localhost:8000/analysis" \
  -H "Content-Type: application/json" \
  -d '{"namespaces": ["example-ns-prd", "other-ns-prd"], "enable_ml": false}'
```

## Geração assíncrona com progresso

O `POST /analysis` continua síncrono (a resposta só volta quando o `.md` está pronto).
Para o frontend acompanhar uma barra de 0 a 100%, use o fluxo assíncrono:

| Método | Caminho | Descrição |
|--------|---------|-----------|
| `POST` | `/api/reports` | Inicia a análise em background e devolve `execution_id` |
| `GET` | `/api/reports/{execution_id}/status` | Consulta progresso, estado e caminho do relatório |

O estado fica em memória no processo da API (adequado a uma única instância).

### `POST /api/reports`

Mesmo corpo do `POST /analysis`. A validação de namespaces ocorre na requisição
inicial (404/400 iguais ao endpoint síncrono). A análise pesada corre em background.

#### Response `202 Accepted`

```json
{
  "execution_id": "a1b2c3d4e5f6...",
  "status": "pending",
  "progress": 0
}
```

### `GET /api/reports/{execution_id}/status`

O frontend pode fazer polling a cada 1 ou 2 segundos. O campo `progress` é um
inteiro `0 <= progress <= 100`. O valor `100` só aparece depois que o `.md`
foi gravado.

#### Em execução

```json
{
  "execution_id": "a1b2c3d4e5f6...",
  "status": "running",
  "progress": 45,
  "message": "Analisando YAMLs",
  "processed": 45,
  "total": 100,
  "report": null
}
```

#### Concluído

```json
{
  "execution_id": "a1b2c3d4e5f6...",
  "status": "completed",
  "progress": 100,
  "message": "Relatório gerado com sucesso",
  "processed": 100,
  "total": 100,
  "report": "/app/data/reports/example-ns-prd.md"
}
```

#### Erro

```json
{
  "execution_id": "a1b2c3d4e5f6...",
  "status": "error",
  "progress": 67,
  "message": "Erro durante a análise dos YAMLs",
  "processed": 40,
  "total": 60,
  "report": null,
  "error": "mensagem do erro"
}
```

Estados possíveis: `pending`, `running`, `completed`, `error`.

#### Como o progresso é calculado

Marcos por namespace, sobre o pipeline real (sem valores artificiais):

| Progresso local | Etapa |
|-----------------|-------|
| 0% | execução iniciada |
| 10% | YAMLs identificados (`scan_namespace_files`) |
| 20%–70% | leitura/parse de cada YAML (`(processados / total) * 50`) |
| 70%–80% | análise determinística (e ML, se ativa) |
| 90% | geração do Markdown |
| 100% | arquivo `.md` gravado |

Com vários namespaces, cada um ocupa uma fatia igual de 0–100.

#### Exemplo com `curl`

```bash
EXEC_ID=$(curl -sS -X POST "http://localhost:8000/api/reports" \
  -H "Content-Type: application/json" \
  -d '{"namespaces": ["example-ns-prd"], "enable_ml": false}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["execution_id"])')

curl -sS "http://localhost:8000/api/reports/${EXEC_ID}/status"
```
