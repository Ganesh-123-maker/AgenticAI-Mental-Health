# Command Reproducibility Audit

**Project**: Agentic AI for Mental Health  
**Repository**: [https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health](https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health)  
**Verification Date**: October 3, 2026  
**Artifact**: `docs/COMMAND_REPRODUCIBILITY_AUDIT.md`  

---

## 1. Documented Command Audit Table

| Command | Documentation Source | Executed In Clean Clone? | Result | Operational Notes |
|:---|:---|:---:|:---:|:---|
| `git clone https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health.git` | `README.md` | Yes | **SUCCESS** | Cloned 2,758 tracked files cleanly from origin/main. |
| `python -m venv venv` | `README.md` | Yes | **SUCCESS** | Created clean Python 3.11.9 virtual environment in `.venv`. |
| `pip install -r requirements.txt` | `README.md` | Yes | **SUCCESS** | Verified all core packages (`fastapi`, `sqlmodel`, `torch`, `yaml`, `jinja2`, `pytest`). |
| `python -m pytest -q` | `README.md`, `docs/RELEASE_CHECKLIST.md` | Yes | **SUCCESS** | 31/31 test suites passed in 14.91 seconds. Zero errors. |
| `pwsh -NoProfile -Command "& { $env:PYTHONPATH='src;src/web'; python -m uvicorn web.main:app --port 8000 }"` | `README.md`, `docs/FINAL_RESEARCH_DOCUMENT.md` | Yes | **SUCCESS** | Backend booted; HTTP 200 OK returned on `/docs` and API endpoints. |
| `cd src/web; npm install` | `README.md` | Yes | **SUCCESS** | Installed frontend dependencies (React 18, Vite 5, Lucide-React). |
| `npm run build` | `README.md`, `docs/FINAL_RELEASE_REPORT.md` | Yes | **SUCCESS** | Built production bundle in 4.10 seconds; 1,600 modules transformed. |
| `npm run dev` | `README.md` | Yes | **SUCCESS** | Dev server launches on `http://localhost:5173`. |
| `python -X utf8 src/experiments/run_systems.py --out-dir data/research_evaluation/system_outputs` | `README.md`, `docs/FINAL_RESEARCH_DOCUMENT.md` | Yes | **SUCCESS** | Evaluates all 12 baseline and ablation configurations across 25 benchmark cases. |
| `python -X utf8 src/experiments/failure_analysis.py --eval-dir data/research_evaluation/system_outputs` | `README.md`, `docs/FINAL_RESEARCH_DOCUMENT.md` | Yes | **SUCCESS** | Parses 545 failure records and generates structured failure taxonomy JSON. |
| `python scratch/test_demo_flow.py` | `docs/LIVE_PROJECT_DEMO_VALIDATION.md` | Yes | **SUCCESS** | Full 11-phase multi-session and user-isolation integration test passes 100%. |

---

## 2. Platform Assumptions

### Required
- **Python**: 3.10+ (Tested on Python 3.11.9).
- **Node.js**: 18.0+ (Tested on Node v22.22.2).
- **Operating System**: Cross-platform (Validated on Windows 10/11; standard Unix paths supported).
- **Memory**: Minimum 4GB RAM (CPU-only execution verified).
- **GPU**: None required. All offline tests and DummyBackend inference execute on CPU.

### Optional
- **OpenAI API Key**: Only required for live LLM counseling mode (`psychagent_sglang_local.yaml` or online OpenAI endpoints). Not required for offline reproducible benchmarking.
- **SGLang Inference Server**: Optional for local open-source LLM hosting.
