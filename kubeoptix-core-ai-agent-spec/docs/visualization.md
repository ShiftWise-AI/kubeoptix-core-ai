# Visualization Guide

## Intent

The agent must generate visual evidence that is traceable to the ingested manifests, workload definitions, and runtime metrics. Visualizations are a complement to evidence, not a substitute for it.

## Required visual outputs

The report should include, when supported by the available data:

- namespace-level architecture diagram;
- service-to-workload dependency diagram;
- namespace partition proposal;
- resource profile charts (CPU, memory, replicas, QoS coverage);
- event or log anomaly summary, if present;
- visual note for missing data.

## Architecture diagram rules

- Prefer KubeDiagrams with Graphviz when available.
- Use a diagram that reflects actual selectors, `spec.to`, `envFrom`, `volumes`, and `scaleTargetRef` relationships.
- If KubeDiagrams fails, fall back to a textual architecture summary in the markdown report.
- Do not invent relationships not present in the YAML corpus.

## Visualization constraints

- Keep diagrams readable for a single namespace.
- Use a deterministic layout whenever possible.
- Maintain consistent naming with report assets.
- Include a short textual explanation below every diagram when needed.

## Reporting expectations

Every visual should be attached to a section that explains:

- what the diagram represents;
- which source files support it;
- what evidence it confirms;
- what remains unknown.

## Output naming conventions

Use a stable asset prefix so the Markdown output references the correct generated files.

For example:

- `ml-<namespace>_assets/...`
- `.../topology.png`
- `.../resource_usage.png`

This keeps the report self-contained and reproducible.
