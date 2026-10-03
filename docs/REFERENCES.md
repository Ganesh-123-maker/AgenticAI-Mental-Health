# Research References & Source Attribution

**Project**: Agentic AI for Mental Health  
**Repository**: [https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health](https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health)  
**Artifact**: `docs/REFERENCES.md`  
**Purpose**: Document all research literature, software repositories, datasets, and models genuinely used in this project.

---

### Research Literature

1. **PsychAgent Framework**:
   - **Title**: *PsychAgent: A Multi-Agent Framework for Dynamic Psychological Counseling via Modular Clinical Expertise*
   - **Authors**: Zheng, et al.
   - **Year**: 2024
   - **Venue**: arXiv preprint
   - **Role in Project**: Foundational architecture providing hierarchical meta-skill and micro-skill taxonomies and clinical prompt structures.

2. **Working Alliance Inventory (WAI)**:
   - **Title**: *Development and Validation of the Working Alliance Inventory*
   - **Authors**: Horvath, A. O., & Greenberg, L. S.
   - **Year**: 1989
   - **Venue**: Journal of Counseling Psychology, 36(2), 223–233.
   - **Role in Project**: Layer 1 clinical evaluation metric measuring Goal, Task, and Bond dimensions (`src/eval/methods/counselor/human_eval.py`).

3. **Session Rating Scale (SRS)**:
   - **Title**: *The Session Rating Scale: Preliminary Psychometric Properties of a "Working" Alliance Measure*
   - **Authors**: Duncan, B. L., Miller, S. D., Sparks, J. A., Claud, D. A., Reynolds, L. R., Brown, J., & Johnson, L. D.
   - **Year**: 2003
   - **Venue**: Journal of Brief Therapy, 3(1), 3–12.
   - **Role in Project**: Working alliance and relational satisfaction evaluation instrument (`src/eval/methods/client/srs.py`).

4. **Positive and Negative Affect Schedule (PANAS)**:
   - **Title**: *Development and Validation of Brief Measures of Positive and Negative Affect: The PANAS Scales*
   - **Authors**: Watson, D., Clark, L. A., & Tellegen, A.
   - **Year**: 1988
   - **Venue**: Journal of Personality and Social Psychology, 54(6), 1063–1070.
   - **Role in Project**: Affective state assessment for client evaluation (`src/eval/methods/client/panas.py`).

5. **Patient Health Questionnaire (PHQ-9)**:
   - **Title**: *The PHQ-9: Validity of a Brief Depression Severity Measure*
   - **Authors**: Kroenke, K., Spitzer, R. L., & Williams, J. B.
   - **Year**: 2001
   - **Venue**: Journal of General Internal Medicine, 16(9), 606–613.
   - **Role in Project**: Standardized depression symptom severity assessment instrument (`src/eval/methods/client/phq_9.py`).

6. **State-Trait Anxiety Inventory (STAI)**:
   - **Title**: *State-Trait Anxiety Inventory for Adults: Manual and Sample Form*
   - **Authors**: Spielberger, C. D.
   - **Year**: 1983
   - **Venue**: Consulting Psychologists Press
   - **Role in Project**: Anxiety assessment method (`src/eval/methods/client/stai.py`).

7. **Cognitive Therapy Rating Scale (CTRS)**:
   - **Title**: *Cognitive Therapy Rating Scale Manual*
   - **Authors**: Young, J. E., & Beck, A. T.
   - **Year**: 1980
   - **Venue**: Unpublished manuscript, University of Pennsylvania
   - **Role in Project**: Clinical counselor competency scoring (`src/eval/methods/counselor/ctrs.py`).

8. **Motivational Interviewing Treatment Integrity (MITI)**:
   - **Title**: *Motivational Interviewing Treatment Integrity: Manual Version 3.1.1*
   - **Authors**: Moyers, T. B., Martin, T., Manuel, J. K., Miller, W. R., & Ernst, D.
   - **Year**: 2005
   - **Venue**: University of New Mexico Center on Alcoholism, Substance Abuse, and Addictions
   - **Role in Project**: Counselor empathy and relational score validation (`src/eval/methods/counselor/miti.py`).

---

### Software & Repositories

1. **AgenticAI-Mental-Health**:
   - **Repository**: [https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health](https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health)
   - **Description**: The primary academic repository hosting the 11-agent pipeline, FastAPI backend, Vite React frontend, and evaluation harness.

2. **FastAPI**:
   - **Repository**: [https://github.com/fastapi/fastapi](https://github.com/fastapi/fastapi)
   - **Authors**: Sebastián Ramírez
   - **Description**: High-performance Python web framework used for the backend REST API (`src/web/backend/`).

3. **SQLModel**:
   - **Repository**: [https://github.com/fastapi/sqlmodel](https://github.com/fastapi/sqlmodel)
   - **Authors**: Sebastián Ramírez
   - **Description**: Relational SQLite database modeling and schema management (`src/web/backend/models.py`).

4. **React & Vite**:
   - **Repositories**: [https://github.com/facebook/react](https://github.com/facebook/react), [https://github.com/vitejs/vite](https://github.com/vitejs/vite)
   - **Description**: Frontend library and bundling tool powering the user interface (`src/web/src/`).

5. **Pytest**:
   - **Repository**: [https://github.com/pytest-dev/pytest](https://github.com/pytest-dev/pytest)
   - **Description**: Testing framework running the 31-suite automated test harness (`tests/`).

---

### Datasets & Clinical Benchmarks

1. **Ambiguous Cases Clinical Benchmark**:
   - **Source Directory**: `data/benchmark/ambiguous_cases/`
   - **Scope**: 25 curated clinical vignettes across five psychotherapy modalities (`bt`, `cbt`, `het`, `pdt`, `pmt`), split into Ordinary Distress (ambiguity, missing data, contradictions) and Safety tracks (crisis, passive suicidal ideation, negated risk).

2. **Psychotherapy Meta-Skills Knowledge Base**:
   - **Source File**: `assets/skills/meta_skills.json`
   - **Scope**: Hierarchical clinical taxonomy of therapeutic interventions across therapeutic stages 1, 2, and 3.

3. **Psychotherapy Micro-Skill Embeddings**:
   - **Source File**: `assets/skills/micro_skills.pt`
   - **Scope**: Pre-computed tensor trigger embeddings for fine-grained semantic RAG retrieval by `SkillManager`.

---

### APIs & Model Backends

1. **OpenAI API**:
   - **Provider**: OpenAI
   - **Endpoint**: `https://api.openai.com/v1`
   - **Models Used/Referenced**: `gpt-4o`, `text-embedding-3-small` for generative counseling and semantic skill retrieval.

2. **Local Dummy / Offline Engine**:
   - **Implementation**: `src/sample/backends/dummy_backend.py`
   - **Description**: Deterministic offline execution engine enabling 100% reproducible benchmarking and automated testing without external API dependencies.
