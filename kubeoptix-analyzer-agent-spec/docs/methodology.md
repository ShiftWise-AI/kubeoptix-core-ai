# Metodologia de Análise de Workloads OpenShift

## 1. Princípios

A análise deve combinar quatro camadas:

1. Dados observados
2. Análise determinística
3. Análise estatística / Machine Learning local
4. Recomendações

A saída deve permitir distinguir claramente fatos, inferências e recomendações.

## 2. Descoberta dos dados

Antes da implementação de qualquer parser:

- listar a estrutura dos diretórios;
- identificar namespaces;
- identificar formatos de arquivos;
- examinar amostras representativas;
- identificar campos disponíveis;
- identificar campos ausentes;
- analisar o relatório de referência.

Os arquivos reais são a autoridade sobre o formato dos dados.

## 3. Normalização

Converter os dados encontrados para modelos internos padronizados.

Um workload deve poder representar, quando disponíveis:

- namespace;
- name;
- kind;
- replicas;
- containers;
- CPU request;
- CPU limit;
- memória request;
- memória limit;
- probes;
- QoS;
- scheduling;
- volumes;
- labels;
- metadados;
- origem dos dados.

Um worknode deve poder representar:

- nome;
- CPU capacity;
- CPU allocatable;
- memória capacity;
- memória allocatable;
- labels;
- taints;
- arquitetura;
- demais atributos disponíveis.

## 4. Análise de recursos

### CPU

Avaliar:

- requests;
- limits;
- soma por workload;
- soma por namespace;
- relação request/limit;
- proporção em relação ao allocatable dos workers;
- potenciais excessos ou insuficiências de configuração.

Nunca chamar request de "uso".

### Memória

Avaliar:

- requests;
- limits;
- soma por workload;
- soma por namespace;
- relação request/limit;
- proporção em relação ao allocatable.

Não inferir OOMKilled sem evidência de eventos ou métricas.

## 5. QoS

Quando os dados permitirem, classificar:

- Guaranteed;
- Burstable;
- BestEffort.

Explicar o impacto da classificação sem exagerar conclusões.

## 6. Réplicas

Avaliar:

- número de réplicas;
- workloads com uma réplica;
- quantidade de réplicas por workload;
- concentração potencial.

Uma única réplica pode ser um risco potencial, mas não deve ser descrita como indisponibilidade efetiva sem evidência.

## 7. Probes

Avaliar:

- readinessProbe;
- livenessProbe;
- startupProbe.

Identificar ausência ou padrões incomuns quando os dados permitirem.

## 8. Scheduling

Avaliar:

- nodeSelector;
- nodeAffinity;
- podAffinity;
- podAntiAffinity;
- tolerations;
- topologySpreadConstraints;
- outras configurações relevantes.

Correlacionar restrições de scheduling com características dos worknodes quando houver dados suficientes.

## 9. Workload × Worknode

Correlacionar:

- requests dos workloads;
- número de réplicas;
- características de scheduling;
- capacidade dos workers;
- capacidade allocatable.

Possíveis findings:

- requests incompatíveis com capacidade;
- concentração;
- distribuição desequilibrada;
- capacidade potencialmente reservada em excesso;
- dificuldade potencial de scheduling.

Distinguir sempre capacidade reservada de consumo real.

## 10. Detecção de anomalias

Pode utilizar:

- z-score;
- IQR;
- Isolation Forest;
- clustering;
- similaridade;
- outras técnicas locais adequadas.

As features e thresholds devem ser documentados.

Um outlier estatístico não é automaticamente um problema. Ele deve ser apresentado como sinal para investigação.

## 11. Similaridade

Quando houver dados suficientes, comparar workloads semelhantes usando:

- features estruturadas;
- TF-IDF;
- embeddings locais;
- distância estatística.

Embeddings devem ser opcionais e executáveis em CPU.

Não utilizar similaridade semântica como prova de equivalência operacional.

## 12. Scoring

Cada finding pode possuir:

- ID;
- categoria;
- severidade;
- evidência;
- impacto;
- recomendação;
- confiança;
- fonte.

Severidades sugeridas:

- CRITICAL
- HIGH
- MEDIUM
- LOW
- INFO

Confiança:

- HIGH
- MEDIUM
- LOW

## 13. Evidência

Sempre que possível registrar:

- namespace;
- workload;
- container;
- campo;
- valor;
- arquivo de origem.

Exemplo:

> CPU request configurado em 2000m, 3 réplicas, totalizando 6000m de CPU solicitada.

## 14. Dados ausentes

Quando não houver informação:

> Informação não disponível nos dados coletados.

Para métricas de runtime ausentes:

> A análise de utilização real não foi realizada devido à ausência de métricas de runtime nos dados disponíveis.

## 15. IA local

A IA deve ser opcional.

Prioridade:

1. regras determinísticas;
2. estatística;
3. detecção de anomalias;
4. clustering;
5. similaridade;
6. embeddings locais.

### Implementação (`src/kubeoptix_analyzer/ml/`)

| Prioridade | Técnica | Módulo | Dependência |
|------------|---------|--------|-------------|
| 2 | z-score, IQR | `statistics.py` | stdlib (`statistics`) |
| 3 | Isolation Forest | `anomalies.py` | scikit-learn |
| 4 | K-Means | `clustering.py` | scikit-learn |
| 5 | Similaridade de cosseno | `similarity.py` | numpy |
| — | Comparação multivariada | `comparison.py` | numpy |
| — | Extração de features | `features.py` | numpy |

**Embeddings locais não implementados:** features são numéricas estruturadas
(requests, limits, réplicas, probes, ratios usage/request). Similaridade
semântica de nomes não prova equivalência operacional.

**Bibliotecas adotadas e justificativa:**

- `numpy` — matrizes de features e operações vetoriais leves
- `scikit-learn` — Isolation Forest, K-Means, StandardScaler (CPU, `random_state`)

**Bibliotecas avaliadas e descartadas:**

- `pandas` — volume por namespace é pequeno; listas/numpy bastam
- `sentence-transformers` / `FAISS` — não agregam valor frente a vetores de recursos
- `TF-IDF` sobre YAML — não substitui comparação numérica de dimensionamento

Reprodutibilidade: `KUBEOPTIX_ML_SEED` (padrão `42`); CLI `--ml-seed` e `--no-ml`.

Não adicionar dependências sem justificar sua necessidade.

## 16. Reprodutibilidade

A mesma entrada deve produzir resultados consistentes.

Algoritmos estocásticos devem possuir seed configurável.

## 17. Limitações

O relatório deve declarar claramente:

- dados ausentes;
- métricas não coletadas;
- inferências;
- limitações dos modelos;
- limitações da correlação workload × worker.
