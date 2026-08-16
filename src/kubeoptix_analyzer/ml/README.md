# Camada de IA / estatística local

Análise **opcional** e **secundária** às regras determinísticas. Executa
100% offline, em CPU, sem LLM externo nem APIs pagas.

## Dependências e justificativa

| Biblioteca        | Usada para                         | Por quê                                      |
|-------------------|------------------------------------|----------------------------------------------|
| `statistics`      | z-score robusto (MAD), IQR, quantis | stdlib; outliers univariados resistentes a extremos |
| `numpy`           | matrizes de features               | operações vetoriais leves                    |
| `scikit-learn`    | Isolation Forest, K-Means, scaler  | algoritmos maduros, `random_state` reproduzível |

**Não adicionadas** (avaliadas e descartadas nesta fase):

- **pandas** — volume de dados por namespace é pequeno; listas/numpy bastam.
- **sentence-transformers / FAISS** — features são numéricas estruturadas;
  similaridade semântica de nomes não prova equivalência operacional.
- **TF-IDF sobre YAML** — não agrega valor frente a vetores de recursos.

## Ordem de execução

1. **Estatística** (`ml/statistics.py`) — z-score robusto (mediana/MAD) e IQR por feature.
2. **Comparação** (`ml/comparison.py`) — distância ao centroide e pares divergentes.
3. **Anomalias** (`ml/anomalies.py`) — Isolation Forest multivariado.
4. **Clustering** (`ml/clustering.py`) — K-Means por perfil de recursos.
5. **Similaridade** (`ml/similarity.py`) — cosseno entre vetores padronizados.

## Features (`ml/features.py`)

Cada workload vira um vetor fixo de 14 dimensões (requests, limits, réplicas,
probes, flags de scheduling, ratios usage/request quando há PodMetrics).
Ver `FEATURE_NAMES` e `FEATURE_DESCRIPTIONS` no código.

## Reprodutibilidade

- `MLConfig.random_seed` (padrão `42`, env `KUBEOPTIX_ML_SEED`).
- `KUBEOPTIX_ML_ENABLED=false` ou CLI `--no-ml` desativa a camada.
- Findings ML usam IDs `ML-<CATEGORIA>-NNN` e confiança MEDIUM/LOW.

## Princípio

> Outlier estatístico ≠ defeito. Use como sinal de investigação, não como
> substituto de regras como “request ausente” ou “usage > limit”.

Categorias de finding: `MLSTAT`, `MLCOMP`, `MLANOM`, `MLCLUST`, `MLSIM`.
