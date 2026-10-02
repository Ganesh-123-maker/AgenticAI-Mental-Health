# `configs/`

This directory provides configuration files for the execution workflows of PsychAgent, including:

- Which configuration files are required for `sample`, `eval`, and `rft`
- Where to adjust parameters across `baseline`, `runtime`, `dataset`, and `rft-config`
- How to switch model endpoints, control data scale, modify evaluation metrics, or configure reward evaluation endpoints

## Workflow Configuration Requirements

```text
sample: baseline + runtime + dataset
eval:   runtime
rft:    baseline + runtime + dataset + rft runtime
```

For basic execution, the commands in the root [`../README.md`](../README.md) are sufficient. Consult this guide when modifying parameters, changing inference endpoints, adjusting dataset splits, or tuning multi-agent toggles.

## Requirements for `sample`

A standard generation run loads three configuration categories simultaneously:

- [`baselines/psychagent_sglang_local.yaml`](baselines/psychagent_sglang_local.yaml)
- [`runtime/psychagent_sglang_local.yaml`](runtime/psychagent_sglang_local.yaml)
- [`datasets/profiles_sample.yaml`](datasets/profiles_sample.yaml) (or another dataset YAML)

Responsibilities:

- **`baseline`**: Controls counselor model endpoint and generation hyperparameters (`backend`, `model`, `base_url`, `api_key_env`, `temperature`, `max_tokens`, `max_sessions`, `max_counselor_turns`, `end_token`).
- **`runtime`**: Controls execution mechanics (`concurrency`, `resume`, `overwrite`, `save_dir`, `output_language`), client simulator parameters (`client_*`), session/skill parameters (`psychagent_*`), embedding settings (`psychagent_embedding_*`), and multi-agent pipeline toggles (`multi_agent_enabled`, `uncertainty_enabled`, `risk_enabled`, `clarification_enabled`, `safety_supervisor_enabled`, `longitudinal_enabled`, `multi_agent_routing_enabled`).
- **`dataset`**: Controls case selection and paths (`root_data_path`, `supported_modalities`, `split`, `max_cases`, `max_cases_per_modality`, `case_selection_strategy`, `filename_sort_policy`).

Common adjustments:
- Switch counselor LLM service: edit `baselines/*.yaml`
- Modify concurrency, resume behavior, language, or multi-agent toggles: edit `runtime/psychagent_sglang_local.yaml`
- Change dataset sample sizes or paths: edit `datasets/*.yaml`

## Requirements for `eval`

Evaluation runs depend exclusively on a runtime configuration:

- [`runtime/eval_default.yaml`](runtime/eval_default.yaml)

Responsibilities:
- Input/output paths: `data_root`, `output_root`
- Input format: `input_format`
- Evaluation judge endpoints: `api_key`, `api_base_url`, `api_model`
- Concurrency control: `method_concurrency`, `file_concurrency`, `api_concurrency`, `api_rps`
- Execution behavior: `resume`, `overwrite`, `case_limit`
- Metric selection: `supported_modalities`, `method_by_modality`

CLI arguments can temporarily override YAML defaults (e.g., `--input-format`, `--data-root`, `--output-root`, `--modalities`).

## Requirements for `rft`

RFT reuses the three configurations from `sample` and adds a dedicated rollout/reward configuration:

- [`baselines/psychagent_sglang_local.yaml`](baselines/psychagent_sglang_local.yaml)
- [`runtime/psychagent_sglang_local.yaml`](runtime/psychagent_sglang_local.yaml)
- [`datasets/profiles_rft.yaml`](datasets/profiles_rft.yaml)
- [`runtime/rft_default.yaml`](runtime/rft_default.yaml)

The RFT runtime controls:
- Rollout scale: `rollout_n`, `rollout_concurrency`
- Reward concurrency: `reward_method_concurrency`, `reward_api_concurrency`, `reward_api_rps`
- Reward endpoint: `reward_api_key`, `reward_api_base_url`, `reward_api_model`
- Artifact retention: `keep_all_rollout_transcripts`
- Reward method mapping: `method_by_modality`

## Example Files in this Directory

- [`baselines/psychagent_sglang_local.yaml`](baselines/psychagent_sglang_local.yaml): Default counselor model connection config.
- [`datasets/profiles_sample.yaml`](datasets/profiles_sample.yaml): Default `sample` dataset using bundled profile assets.
- [`datasets/profiles_rft.yaml`](datasets/profiles_rft.yaml): Default `rft` dataset using bundled profile assets.
- [`datasets/psycheval.yaml`](datasets/psycheval.yaml): Multi-modality dataset config.
- [`datasets/psycheval_bt_cbt_het_pdt_pmt.yaml`](datasets/psycheval_bt_cbt_het_pdt_pmt.yaml): Five-modality dataset configuration with per-modality sample caps.
- [`runtime/psychagent_sglang_local.yaml`](runtime/psychagent_sglang_local.yaml): Main runtime configuration shared by `sample` and `rft`.
- [`runtime/eval_default.yaml`](runtime/eval_default.yaml): Default `eval` execution config.
- [`runtime/rft_default.yaml`](runtime/rft_default.yaml): RFT rollout and reward evaluation config.

## Resolution Rules

- Relative paths in `datasets/*.yaml` resolve relative to the configuration file's directory.
- Dataset YAMLs are parsed into `DatasetConfig` by [`../src/sample/io/config_loader.py`](../src/sample/io/config_loader.py) and validated by [`../src/sample/io/dataset_loader.py`](../src/sample/io/dataset_loader.py).
- Evaluation YAMLs are validated via Pydantic schemas in [`../src/eval/core/schemas.py`](../src/eval/core/schemas.py).
