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
