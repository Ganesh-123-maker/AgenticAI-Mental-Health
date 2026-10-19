import json
import re
from typing import Any, List, Literal

from jinja2 import Template
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...core.base import EvaluationMethod
from ...utils import load_prompt

PANASItemName = Literal[
    "Interested",
    "Excited",
    "Strong",
    "Enthusiastic",
    "Proud",
    "Alert",
    "Inspired",
    "Determined",
    "Attentive",
    "Active",
    "Distressed",
    "Upset",
    "Guilty",
    "Scared",
    "Hostile",
    "Irritable",
    "Ashamed",
    "Nervous",
    "Jittery",
    "Afraid",
]

_PANAS_ORDER: list[str] = [
    "Interested",
    "Excited",
    "Strong",
    "Enthusiastic",
    "Proud",
    "Alert",
    "Inspired",
    "Determined",
    "Attentive",
    "Active",
    "Distressed",
    "Upset",
    "Guilty",
    "Scared",
    "Hostile",
    "Irritable",
    "Ashamed",
    "Nervous",
    "Jittery",
    "Afraid",
]


class Item(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=False)

    item: PANASItemName
    score: int = Field(ge=1, le=5)


class Items(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)

    items: List[Item] = Field(min_length=20, max_length=20)

    @model_validator(mode="after")
    def _validate_order(self) -> "Items":
        names = [it.item for it in self.items]
        if names != _PANAS_ORDER:
            raise ValueError("PANAS items must be in the exact required order")
        return self

class PANAS(EvaluationMethod):

    def _parse_panas_response(self, data: list) -> float:
        """Parse PANAS scale response."""
        def _norm(s: str) -> str:
            return re.sub(r"\s+", "", str(s or "")).lower()

        data_lookup = {_norm(entry.get("item")): entry.get("score") for entry in data if isinstance(entry, dict)}
        
        scores = {}
        
        emotions = ['Interested', 'Excited', 'Strong', 'Enthusiastic', 'Proud', 'Alert', 'Inspired', 'Determined', 'Attentive', 'Active','Distressed', 'Upset', 'Guilty', 'Scared', 'Hostile', 'Irritable', 'Ashamed', 'Nervous', 'Jittery', 'Afraid']

        for emotion in emotions:
            original_score = data_lookup.get(_norm(emotion))
            
            if original_score is not None:
                scores[f'panas_{emotion.lower()}'] = (original_score - 1) * 2.5

        positive_emotions = ['interested', 'excited', 'strong', 'enthusiastic', 'proud', 'alert', 'inspired', 'determined', 'attentive', 'active'] 
        negative_emotions = ['distressed', 'upset', 'guilty', 'scared', 'hostile', 'irritable', 'ashamed', 'nervous', 'jittery','afraid']
        
        positive_total = sum(scores.get(f'panas_{emotion}', 0) for emotion in positive_emotions)
        negative_total = sum(scores.get(f'panas_{emotion}', 0) for emotion in negative_emotions)
        
        final_scores = {}
        
        num_positive = len(positive_emotions)
        num_negative = len(negative_emotions)

        final_scores['positive'] = positive_total / num_positive if num_positive > 0 else 0
        final_scores['negative'] = negative_total / num_negative if num_negative > 0 else 0
        
        final_score = (final_scores['positive'] - final_scores['negative'] + 10) / 2
        
        return final_score

    async def evaluate(self, gpt_api, dialogue: Any, profile: dict = None) -> dict[str, float]:
        """Evaluate dialogue quality."""
        prompt = load_prompt("panas", "panas","cn")
        
        template = Template(prompt)
        prompt = template.render(intake_form=profile, diag=dialogue)

        messages=[{"role": "user", "content": prompt}]

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                criteria_output = await self.chat_api(gpt_api, messages=messages)
                validated = Items.model_validate(json.loads(criteria_output))
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt >= 2:
                    raise
                messages = messages + [
                    {
                        "role": "user",
                        "content": "The previous output failed schema validation. Please strictly output a single JSON object containing only the key 'items'; items length must be 20; each containing only item (fixed emotion name) and score (integer 1-5), in the exact required order.",
                    }
                ]
        else:  # pragma: no cover
            raise RuntimeError(f"Failed to get valid PANAS output: {last_err}")

        final_score = self._parse_panas_response([it.model_dump() for it in validated.items])
        return {"client": final_score}


    def get_name(self) -> str:
        return "PANAS"
