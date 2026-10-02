# `prompts/`

This directory provides the prompt assets utilized by the project models. Refer to this directory when understanding model inputs, modifying prompts, investigating behavioral changes, adjusting counseling styles, updating evaluation standards, or tuning skill retrieval prompts.

## Directory Overview

`prompts/` stores the prompt assets currently in use. This includes Jinja2 templates as well as plain-text scoring prompts provided to judge models. These assets are loaded by several key modules:

- `src/sample/core/prompt_manager.py`
- `src/sample/prompt_manager.py`
- `src/sample/skill_manager.py`
- `src/eval/utils.py`

These prompts represent essential operational logic rather than optional supplementary documentation.

## Functional Roles Across the Pipeline

Conceptually, `prompts/` is divided into three tiers:

- **Generation Tier**: Drives client simulation, counselor dialogue generation, longitudinal session summaries, and profile updates.
- **Skill Tier**: Provides prompts for coarse skill filtering and turn-level skill rewriting when the external skill library is active.
- **Evaluation Tier**: Supplies standardized scoring rubrics and prompts for various psychometric scales and counseling dimensions.

The `sample` and `rft` pipelines primarily consume the generation and skill tiers, while `eval` consumes the evaluation tier.

## Key Files and Subdirectories

### `public/`

Common prompts shared by `src/sample/core/prompt_manager.py`:

- `counselor_system.jinja2`
- `session_opening.jinja2`
- `public_recap.jinja2`

These templates define cross-modality shared context, including public client background, longitudinal history recap, homework review, and opening remarks.

### `client/`

- `dialogue.jinja2`

The core input template for the client simulator, invoked by `ClientSimulator.generate_client_utterance()`. It incorporates:

- `intake_profile`
- Longitudinal session history summaries
- Previous session homework
- The counselor's most recent utterance

To adjust client simulation dynamics, begin here.

### `psychagent/`

Modality-specific prompts directly utilized by `sample` and `rft`. Currently supports:

- `bt/` (Behavior Therapy)
- `cbt/` (Cognitive Behavioral Therapy)
- `het/` (Humanistic-Existential Therapy)
- `pdt/` (Psychodynamic Therapy)
- `pmt/` (Postmodern Therapy)
- `skill/`

Each modality directory adheres to a structured template hierarchy:

```text
<modality>/
  counsel/system.jinja2
  summary/system.jinja2
  summary/user.jinja2
  profile/system.jinja2
  profile/user.jinja2
```

This layout represents the path contract loaded by `src/sample/prompt_manager.py`.

Key details:
- `counsel/system.jinja2` typically instructs the model to structure internal reasoning within `<think>` and dialogue within `<response>`.
- `src/sample/runner.py` in `_chat_with_retry()` extracts `<response>` as the natural language dialogue written to transcripts.
- `skill/select_skill/` and `skill/rewrite/` are loaded by `src/sample/skill_manager.py` for coarse filtering and turn-level retrieval.

### `eval/`

Scoring prompts for `src.eval`. Most evaluation methods use the convention:

```text
prompts/eval/<method_name>/<prompt_name>.txt
```

Examples:
- `ctrs/collaboration.txt`
- `miti/empathy.txt`
- `psc/transference.txt`
- `tes/warmth.txt`

A few evaluation prompts reside at the root of `prompts/eval/`, such as:
- `human_vs_llm_eval.txt`

The loader in `src/eval/utils.py::load_prompt()` supports both subdirectory and direct-file layouts.

## Relationships to Other Directories

- **Coupled with [`../src/`](../src/)**: Template locations and file paths are loaded directly in code.
- **Configured by [`../configs/`](../configs/)**: Skill prompt paths and model parameters can be overridden via runtime configs.
- **Supplied by [`../data/`](../data/)**: Benchmark and profile data provide context injected during prompt rendering.

## Important Notes

- Templates include both `.jinja2` files and `.txt` plain-text prompts; treat them according to their specific execution requirements.
- The directory layout under `psychagent/<modality>/...` follows the contractual expectations of `src/sample/prompt_manager.py`.
- Evaluation prompt discovery follows `src/eval/utils.py::load_prompt()`.
