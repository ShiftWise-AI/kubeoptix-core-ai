# Padrão do Relatório de Assessment

## Objetivo

Gerar um relatório Markdown em português do Brasil para o namespace analisado.

O relatório de referência deve ser inspecionado pelo agente para reproduzir seu nível de organização, linguagem, tabelas e profundidade.

Ele é referência estrutural e metodológica, não fonte de dados para outros namespaces.

## Estrutura mínima

```markdown
# Assessment de Workload

## 1. Sumário Executivo

## 2. Escopo da Análise

## 3. Fontes de Dados

## 4. Visão Geral do Namespace

## 5. Workloads Identificados

## 6. Análise de CPU

## 7. Análise de Memória

## 8. Análise de QoS

## 9. Análise de Réplicas

## 10. Análise de Probes

## 11. Análise de Scheduling

## 12. Análise de Storage

## 13. Events

## 14. Atualização de Operators (OLM)

## 15. Correlação Workload × Worknode

## 16. Anomalias Identificadas

## 17. Findings

## 18. Oportunidades de Otimização

## 19. Riscos

## 20. Recomendações

## 21. Conclusão

## 22. Limitações da Análise
```

A estrutura pode ser adaptada após inspeção do relatório de referência.

## Regras de redação

- Escrever em pt-BR.
- Ser técnico e objetivo.
- Não utilizar linguagem alarmista.
- Não apresentar inferências como fatos.
- Diferenciar claramente evidência, análise e recomendação.
- Informar ausência de dados.
- Evitar recomendações genéricas.
- Priorizar recomendações acionáveis.

## Modelo de finding

```markdown
### RES-CPU-001 — Request de CPU elevado

**Severidade:** HIGH

**Confiança:** HIGH

**Workload:** exemplo

**Evidências:**

- CPU request: `2000m`
- CPU limit: `4000m`
- Réplicas: `3`
- Origem: `arquivo.yaml`

**Análise:**

O workload possui 6000m de CPU solicitada considerando as três réplicas.

**Impacto potencial:**

A configuração pode reservar parcela significativa da capacidade disponível.

**Recomendação:**

Avaliar o dimensionamento do CPU request com base em métricas reais de utilização.

**Limitação:**

Não há métrica de CPU usage disponível nos dados analisados.
```

## Regras de números

- CPU deve preservar unidades como `m` quando apropriado.
- Memória deve preservar unidades como `Mi`/`Gi`.
- Não arredondar valores de forma que altere a interpretação.
- Totais calculados devem indicar que são derivados.
- Nunca inventar valores ausentes.

## Métricas de runtime

Se não existirem dados de runtime, não criar:

- CPU usage;
- memory usage;
- throttling;
- OOMKilled;
- restart count;
- latência;
- throughput.

Nesse caso, declarar a limitação.

## Rastreamento da origem

Findings relevantes devem apontar a origem do dado sempre que possível.

A implementação deve preservar metadados de origem durante parsing e normalização.

## Nome do arquivo

O relatório deve ser salvo como:

`<namespace>.md`

Exemplo:

`meu-namespace-prd.md`
