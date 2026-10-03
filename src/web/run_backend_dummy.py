import os
import uvicorn

if __name__ == "__main__":
    os.environ["PSYCHAGENT_WEB_BASELINE_CONFIG"] = "configs/baselines/psychagent_dummy_local.yaml"
    os.environ["PSYCHAGENT_WEB_RUNTIME_CONFIG"] = "configs/runtime/psychagent_dummy_local.yaml"
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
