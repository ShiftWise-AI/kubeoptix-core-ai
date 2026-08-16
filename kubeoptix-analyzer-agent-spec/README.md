# Especificação do Agente de Análise de Workloads OpenShift

Este diretório contém as regras e a metodologia que devem orientar o desenvolvimento do agente.

## Estrutura

- `.cursor/rules/workload-agent.mdc` — regras permanentes para o Cursor.
- `docs/methodology.md` — metodologia de análise.
- `docs/report-format.md` — padrão do relatório Markdown.

## Como utilizar no Cursor

Abra o projeto no Cursor e permita que as regras em `.cursor/rules` sejam carregadas.

Antes de implementar, peça ao Agent para:

1. analisar os arquivos reais de workloads;
2. analisar os arquivos de worknodes;
3. analisar o relatório de referência;
4. identificar os formatos reais;
5. propor a arquitetura;
6. somente depois iniciar a implementação.

Exemplo de primeira solicitação:

> Leia as regras do projeto e analise as fontes de dados configuradas. Não implemente ainda. Inspecione os arquivos reais, identifique seus formatos e campos disponíveis, analise o relatório de referência e proponha uma arquitetura para o agente. Não faça suposições sobre os dados que não estejam confirmadas nos arquivos.

## Princípio central

A solução deve priorizar:

**Confiabilidade → Rastreabilidade → Precisão → Qualidade → IA**

A IA deve complementar a análise, e não substituir evidências.
