# Assessment Report Standard

## Objective

Generate a Markdown report in American English for the analyzed namespace.

The reference report should be inspected by the agent to reproduce its organization, tone, tables, and depth.

It is a structural and methodological reference, not a source of data for other namespaces.

## Minimum structure

```markdown
# Workload Assessment

## 1. Executive Summary

## 2. Scope of Analysis

## 3. Data Sources

## 4. Namespace Overview

## 5. Identified Workloads

## 6. CPU Analysis

## 7. Memory Analysis

## 8. QoS Analysis

## 9. Replica Analysis

## 10. Probe Analysis

## 11. Scheduling Analysis

## 12. Storage Analysis

## 13. Events

## 14. Operator Update (OLM)

## 15. Workload × Worknode Correlation

## 16. Identified Anomalies

## 17. Findings

## 18. Optimization Opportunities

## 19. Risks

## 20. Recommendations

## 21. Conclusion

## 22. Analysis Limitations
```

The structure may be adapted after inspection of the reference report.

## Writing rules

- Write in English (US).
- Be technical and objective.
- Do not use alarmist language.
- Do not present inferences as facts.
- Clearly distinguish evidence, analysis, and recommendation.
- State missing data explicitly.
- Avoid generic recommendations.
- Prioritize actionable recommendations.

## Finding model

```markdown
### RES-CPU-001 — Elevated CPU request

**Severity:** HIGH

**Confidence:** HIGH

**Workload:** example

**Evidence:**

- CPU request: `2000m`
- CPU limit: `4000m`
- Replicas: `3`
- Source: `file.yaml`

**Analysis:**

The workload requires 6000m of CPU across three replicas.

**Potential impact:**

This configuration may reserve a significant share of available cluster capacity.

**Recommendation:**

Evaluate the CPU request sizing based on real usage metrics.

**Limitation:**

No CPU usage data is available in the analyzed inputs.
```

## Number rules

- CPU values should preserve units like `m` when appropriate.
- Memory values should preserve units such as `Mi` and `Gi`.
- Do not round values in a way that changes the interpretation.
- Derived totals should indicate that they are calculated values.
- Never invent missing values.

## Runtime metrics

If runtime data is not available, do not create:

- CPU usage;
- memory usage;
- throttling;
- OOMKilled;
- restart count;
- latency;
- throughput.

In that case, explicitly state the limitation.

## Source traceability

Relevant findings should point to the data origin whenever possible.

The implementation must preserve source metadata throughout parsing and normalization.

## File name

The report should be saved as:

`<namespace>.md`

Example:

`my-namespace-prd.md`
