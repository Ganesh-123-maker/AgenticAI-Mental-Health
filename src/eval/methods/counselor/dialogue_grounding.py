from typing import Any

from ...core.base import EvaluationMethod
from ...utils import load_prompt
from jinja2 import Template
import json

from typing import Annotated, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DialogueGroundingItemName = Literal["No Fabrication or Misremembering", "Bounded Inference with Confirmation", "Accurate Quotation and Internal Consistency"]
EvidenceStr = Annotated[str, Field(pattern=r"^DIALOGUE: counselor:")]


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    item: DialogueGroundingItemName
    score: int = Field(ge=0, le=4)
    evidence_pos: List[EvidenceStr] = Field(max_length=2)
    evidence_neg: List[EvidenceStr] = Field(max_length=2)
    thought: str = Field(max_length=24, pattern=r"^[^\n\r]{0,24}$")

    @field_validator("evidence_pos", "evidence_neg")
    @classmethod
    def _validate_evidence(cls, v: List[str]) -> List[str]:
        for s in v:
            if "DIALOGUE: client:" in s or "PROFILE:" in s:
                raise ValueError("evidence must not contain client/profile prefixes")
        return v


class Items(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: List[Item] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _validate_order(self) -> "Items":
        expected: list[str] = ["No Fabrication or Misremembering", "Bounded Inference with Confirmation", "Accurate Quotation and Internal Consistency"]
        actual = [it.item for it in self.items]
        if actual != expected:
            raise ValueError("Dialogue_Grounding items must be in the exact required order")
        return self


class Dialogue_Grounding(EvaluationMethod):
    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> dict[str, float]:
        prompt = load_prompt("dialogue_grounding", "dialogue_grounding", "cn")
        profile_obj = profile or {}
        try:
            profile_text = json.dumps(profile_obj, ensure_ascii=False, indent=2)
        except Exception:
            profile_text = str(profile_obj)
        prompt = Template(prompt).render(diag=dialogue, profile=profile_text)
        messages = [{"role": "user", "content": prompt}]
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                out = await self.chat_api(gpt_api, messages=messages)
                validated = Items.model_validate(json.loads(out))
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt >= 2:
                    raise
                messages = messages + [
                    {
                        "role": "user",
                        "content": "The previous output failed schema validation. Please strictly output JSON: containing only key 'items' with length 3; each item contains item/evidence_pos/evidence_neg/thought/score, and evidence must start with `DIALOGUE: counselor:`.",
                    }
                ]
        else:  # pragma: no cover
            raise RuntimeError(f"Failed to get valid Dialogue_Grounding output: {last_err}")

        if not validated.items:
            return {"counselor": 0.0}

        mean_score = 0.0
        for it in validated.items:
            mean_score += float(it.score) * 10.0 / 4.0  # 0-4 -> 0-10
        mean_score /= len(validated.items)
        return {"counselor": mean_score}

    def get_name(self) -> str:
        return "Dialogue_Grounding"
