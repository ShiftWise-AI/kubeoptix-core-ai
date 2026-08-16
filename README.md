# kubeoptix-analyzer

Agente local de análise de workloads OpenShift/Kubernetes. Lê metadados YAML
coletados do cluster, aplica regras determinísticas e, opcionalmente, uma
camada estatística / ML local para sinalizar perfis atípicos no namespace.

## Requisitos

- Python 3.11+
- CPU only — sem GPU, sem LLM externo, sem APIs pagas, sem internet em runtime

## Instalação

```bash
pip install -e ".[dev]"
```

## Uso

```bash
# Listar namespaces disponíveis
kubeoptix-analyzer list-namespaces

# Diagnóstico de ingestão (sem findings operacionais)
kubeoptix-analyzer diagnose --namespace meu-namespace-prd

# Análise completa (determinística + ML local)
kubeoptix-analyzer analyze --namespace meu-namespace-prd

# Apenas regras determinísticas
kubeoptix-analyzer analyze --namespace meu-namespace-prd --no-ml

# Seed reproduzível para K-Means e Isolation Forest
kubeoptix-analyzer analyze --namespace meu-namespace-prd --ml-seed 42

# Saída JSON
kubeoptix-analyzer analyze --namespace meu-namespace-prd --json

# Relatório Markdown de assessment
kubeoptix-analyzer report --namespace meu-namespace-prd --output output/
```

### Variáveis de ambiente

| Variável | Descrição |
|----------|-----------|
| `KUBEOPTIX_WORKLOADS_BASE` | Diretório base dos metadados de namespaces |
| `KUBEOPTIX_WORKNODES_PATH` | Diretório dos YAMLs de worknodes |
| `KUBEOPTIX_ML_ENABLED` | `true`/`false` — ativa camada ML (padrão: `true`) |
| `KUBEOPTIX_ML_SEED` | Seed para algoritmos estocásticos (padrão: `42`) |

## Arquitetura

```
YAML → parsers → modelos Pydantic
                    ↓
         ┌──────────┴──────────┐
         ↓                     ↓
  Análise determinística   Camada ML local (opcional)
  (regras absolutas)       (sinais estatísticos)
         └──────────┬──────────┘
                    ↓
              AnalysisReport
```

A camada determinística trata fatos verificáveis (request ausente, usage > request,
probes faltando). A camada ML complementa com comparações relativas dentro do
namespace — **nunca substitui** regras simples quando estas são mais confiáveis.

## Camada ML local

Documentação detalhada em [`src/kubeoptix_analyzer/ml/README.md`](src/kubeoptix_analyzer/ml/README.md).

| Técnica | Módulo | Problema que resolve |
|---------|--------|----------------------|
| z-score robusto / IQR | `ml/statistics.py` | Outliers univariados resistentes a valores extremos (mediana/MAD + Tukey) |
| Distância euclidiana | `ml/comparison.py` | Workload mais distante do perfil típico; pares mais divergentes |
| Isolation Forest | `ml/anomalies.py` | Anomalias multivariadas (combinação atípica de features) |
| K-Means | `ml/clustering.py` | Grupos naturais de perfis para comparar right-sizing |
| Similaridade de cosseno | `ml/similarity.py` | Pares com perfil numérico parecido para benchmarking interno |

**Não implementado (avaliado e descartado):** embeddings textuais, TF-IDF sobre
YAML, pandas — features estruturadas numéricas são suficientes e mais confiáveis
para right-sizing.

Findings ML usam IDs `ML-<CATEGORIA>-NNN`, severidade INFO/LOW e a limitação
padrão de que outlier estatístico ≠ defeito operacional.

## Testes

```bash
pytest
```

## Especificação do agente

Metodologia e formato de relatório em [`kubeoptix-analyzer-agent-spec/`](kubeoptix-analyzer-agent-spec/).
