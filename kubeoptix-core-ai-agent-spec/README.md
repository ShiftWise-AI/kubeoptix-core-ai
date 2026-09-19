# OpenShift Workload Analysis Agent Specification

This directory defines the rules and methodology that should guide agent development.

## Structure

- `.cursor/rules/workload-agent.mdc` — permanent rules for Cursor.
- `docs/methodology.md` — analysis methodology.
- `docs/report-format.md` — Markdown report standard.

## How to use it in Cursor

Open the project in Cursor and allow the rules in `.cursor/rules` to load.

Before implementation, ask the agent to:

1. inspect the real workload files;
2. inspect the worknode files;
3. inspect the reference report;
4. identify the actual formats;
5. propose the architecture;
6. only then start the implementation.

Example first prompt:

> Read the project rules and inspect the configured data sources. Do not implement anything yet. Inspect the real files, identify their formats and fields, analyze the reference report, and propose an architecture for the agent. Do not make assumptions about the data unless they are confirmed by the files.

## Core principle

The solution should prioritize:

**Reliability → Traceability → Accuracy → Quality → AI**

AI should complement the analysis, not replace evidence.
