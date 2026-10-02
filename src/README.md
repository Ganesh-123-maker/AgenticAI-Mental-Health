# `src/`

This directory provides the architectural foundation, module boundaries, and entry points for the PsychAgent codebase. It is designed for researchers and developers seeking to understand execution flow, debug runs, or extend the system with new agents and evaluation methods.

## Overview

`src/` contains the primary implementation of the PsychAgent framework. The codebase is organized into key top-level modules:

- `sample/`: Multi-session counseling dialogue generation and agent pipeline execution
- `eval/`: Quantitative metrics, clinical scales, and multi-agent coordination/safety evaluators
- `rft/`: Best-of-N trajectory selection and reinforcement fine-tuning based on rollout + reward
- `experiments/`: Comparative benchmark runners and ablation evaluation harness
- `shared/`: Cross-module utilities for file paths, serialization, and YAML configuration

The root [`../README.md`](../README.md) provides a high-level research summary; this document details codebase architecture and control flow.

## System Architecture and Execution Flow

The overall execution pipeline operates as follows:

1. `sample` ingests case profiles from `assets/profiles/` or benchmark suites and generates `course.json` and `session_*.json` dialogue artifacts.
2. `eval` evaluates benchmark cases or generated dialogues using standardized clinical scales and multi-agent supervisory metrics.
3. `rft` leverages `sample` to produce multiple rollouts and uses `eval.reward` to compute multi-dimensional rewards for trajectory optimization.
4. `experiments` orchestrates full system configurations (Systems A–F) and component ablations across multi-modal benchmark datasets.
5. `shared` provides hardened infrastructure and file utilities across all modules.

## Key Modules and Components

### `sample/`

The core generation pipeline. Entry points:

- `sample/__main__.py`
- `sample/main.py`

Key components:

- `sample/main.py`: Command-line interface, configuration loading, and runner initialization.
- `sample/runner.py`: Central orchestration loop managing concurrent case rollouts, multi-turn session dialogues, recap/profile updates, and checkpoint recovery.
- `sample/agents/`: Multi-agent architecture comprising `MemoryAgent`, `StateAgent`, `UncertaintyAgent`, `RiskAgent`, `ClarificationAgent`, `ReassessmentAgent`, `Orchestrator`, `CounselingAgent`, `SafetySupervisor`, `OutcomeAgent`, and `MemoryUpdateAgent`.
- `sample/agents/pipeline.py`: Pipeline execution controller managing turn-level message passing, routing loops, safety checks, and ablation bypass toggles.
- `sample/skill_manager.py`: Theoretical skill retrieval and embedding index management.
- `sample/client/simulator.py`: Simulated client persona dialogue generator.

### `eval/`

Evaluation and assessment framework. Entry points:

- `eval/__main__.py`
- `eval/main.py`

Key components:

- `eval/main.py`: CLI configuration parser and execution dispatcher.
- `eval/manager/evaluation_orchestrator.py`: Case discovery, session orchestration, concurrent method execution, and score aggregation.
- `eval/methods/`: Registry and implementations of evaluation methods:
  - `client/`: Standardized psychological scales (e.g., `PANAS`, `SRS`, `PHQ_9`, `BDI_II`)
  - `counselor/`: Counselor competency scales (e.g., `WAI`, `CTRS`, `MITI`)
  - `multi_agent/`: Architectural supervisory metrics (`coordination`, `uncertainty`, `safety`, `longitudinal`)

### `experiments/`

Benchmarking and ablation harness:

- `experiments/run_systems.py`: Automated benchmarking harness comparing baseline models, PsychAgent, and multi-agent configurations across 100-case ambiguous evaluation tracks.

### `shared/`

Shared utilities providing robust common abstractions:

- `shared/file_utils.py`: Safe path resolution (`project_root()`), atomic JSON writes, and sanitized naming.
- `shared/config_utils.py`: YAML loading with fallback parsing.

## Directory Relationships

- [`../configs/`](../configs/): Runtime, baseline, dataset, and ablation toggle configurations.
- [`../prompts/`](../prompts/): Prompt catalogs for counseling agents, skill retrieval, and evaluation judges.
- [`../data/`](../data/): Benchmark suites (`data/benchmark/ambiguous_cases/`) and evaluation outputs (`data/eval_outputs_multi_agent/`).
- [`../assets/`](../assets/): Profile definitions and counseling skill libraries.
- [`../tests/`](../tests/): Automated test suites for agents (`tests/agents/`) and evaluation methods (`tests/eval/`).
