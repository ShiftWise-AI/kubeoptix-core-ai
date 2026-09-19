# OpenShift Workload Analysis Methodology

## 1. Principles

The analysis should combine four layers:

1. Observed data
2. Deterministic analysis
3. Statistical / local machine learning analysis
4. Recommendations

The output should clearly distinguish facts, inferences, and recommendations.

## 2. Data discovery

Before implementing any parser:

- list directory structure;
- identify namespaces;
- identify file formats;
- review representative samples;
- identify available fields;
- identify missing fields;
- analyze the reference report.

The real files are the authority on data format.

## 3. Normalization

Convert discovered data into standardized internal models.

A workload should be able to represent, when available:

- namespace;
- name;
- kind;
- replicas;
- containers;
- CPU request;
- CPU limit;
- memory request;
- memory limit;
- probes;
- QoS;
- scheduling;
- volumes;
- labels;
- metadata;
- data source.

A worknode should be able to represent:

- name;
- CPU capacity;
- CPU allocatable;
- memory capacity;
- memory allocatable;
- labels;
- taints;
- architecture;
- any other relevant attributes.

## 4. Resource analysis

### CPU

Evaluate:

- requests;
- limits;
- total per workload;
- total per namespace;
- request/limit ratio;
- share of worker allocatable capacity;
- potential over-allocation or under-sizing.

Never call a request a "usage" value.

### Memory

Evaluate:

- requests;
- limits;
- total per workload;
- total per namespace;
- request/limit ratio;
- proportion of worker allocatable capacity.

Do not infer OOMKilled without evidence from events or metrics.

## 5. QoS

When data allows, classify:

- Guaranteed;
- Burstable;
- BestEffort.

Explain classification impact without overstating conclusions.

## 6. Replicas

Evaluate:

- replica count;
- workloads with a single replica;
- replica concentration by workload;
- potential resilience concerns.

A single replica may be a risk signal, but it must not be described as effective unavailability without evidence.

## 7. Probes

Evaluate:

- readinessProbe;
- livenessProbe;
- startupProbe.

Identify missing or unusual patterns when supported by the data.

## 8. Scheduling

Evaluate:

- nodeSelector;
- nodeAffinity;
- podAffinity;
- podAntiAffinity;
- tolerations;
- topologySpreadConstraints;
- any other relevant configuration.

Correlate scheduling constraints with worknode characteristics when sufficient data exists.

## 9. Workload × Worknode

Correlate:

- workload requests;
- replica counts;
- scheduling characteristics;
- worker capacity;
- allocatable capacity.

Possible findings:

- requests incompatible with capacity;
- concentration;
- uneven distribution;
- potentially over-reserved capacity;
- potential placement difficulty.

Always distinguish reserved capacity from actual consumption.

## 10. Anomaly detection

This may use:

- z-score;
- IQR;
- Isolation Forest;
- clustering;
- similarity;
- other suitable local techniques.

Features and thresholds must be documented.

A statistical outlier is not automatically a problem. It should be presented as an investigation signal.

## 11. Similarity

When sufficient data exists, compare similar workloads using:

- structured features;
- TF-IDF;
- local embeddings;
- statistical distance.

Embeddings should be optional and executable on CPU.

Do not use semantic similarity as proof of operational equivalence.

## 12. Scoring

Each finding may contain:

- ID;
- category;
- severity;
- evidence;
- impact;
- recommendation;
- confidence;
- source.

Suggested severities:

- CRITICAL
- HIGH
- MEDIUM
- LOW
- INFO

Confidence levels:

- HIGH
- MEDIUM
- LOW

## 13. Evidence

Whenever possible, record:

- namespace;
- workload;
- container;
- field;
- value;
- source file/path;
- observation timestamp when available.

Findings must be traceable to artifacts or metadata.

## 14. Limitations

The assessment must declare missing data explicitly.

Do not fabricate fields, runtime metrics, or operational events that are not present in the input corpus.

When a fact cannot be proved, call it an inference or a limitation.
