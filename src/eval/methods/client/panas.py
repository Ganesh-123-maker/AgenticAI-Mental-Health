from typing import Any, Dict
import re


from ...core.base import EvaluationMethod
from ...utils import load_prompt
from jinja2 import Template
import json

from typing import List
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    # extra="ignore" tolerates unexpected LLM fields (e.g. "rating");
    # strict=False allows float JSON scores (e.g. 2.0) to be coerced to int.
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
        # Convert list to lookup dictionary for quick score retrieval
        def _norm(s: str) -> str:
            return re.sub(r"\s+", "", str(s or "")).lower()

        data_lookup = {_norm(entry.get("item")): entry.get("score") for entry in data if isinstance(entry, dict)}
        
        scores = {}
        
        # Original emotion list as baseline
        emotions = ['Interested', 'Excited', 'Strong', 'Enthusiastic', 'Proud', 'Alert', 'Inspired', 'Determined', 'Attentive', 'Active','Distressed', 'Upset', 'Guilty', 'Scared', 'Hostile', 'Irritable', 'Ashamed', 'Nervous', 'Jittery', 'Afraid']

        for emotion in emotions:
            # Retrieve raw score from lookup dict
            original_score = data_lookup.get(_norm(emotion))
            
            if original_score is not None:
                # Score calculation logic: (raw_score - 1) * 2.5
                scores[f'panas_{emotion.lower()}'] = (original_score - 1) * 2.5

        # Compute total scores for positive and negative emotions
        positive_emotions = ['interested', 'excited', 'strong', 'enthusiastic', 'proud', 'alert', 'inspired', 'determined', 'attentive', 'active'] 
        negative_emotions = ['distressed', 'upset', 'guilty', 'scared', 'hostile', 'irritable', 'ashamed', 'nervous', 'jittery','afraid']
        
        positive_total = sum(scores.get(f'panas_{emotion}', 0) for emotion in positive_emotions)
        negative_total = sum(scores.get(f'panas_{emotion}', 0) for emotion in negative_emotions)
        
        final_scores = {}
        
        num_positive = len(positive_emotions)
        num_negative = len(negative_emotions)

        final_scores['positive'] = positive_total / num_positive if num_positive > 0 else 0
        final_scores['negative'] = negative_total / num_negative if num_negative > 0 else 0
        
        # Convert to 0-10 scale
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

        # Convert data (list) to the required format string
        # score = {'items': [
        #     {'item': 'Interested', 'score': 2}, {'item': 'Excited', 'score': 1}, {'item': 'Strong', 'score': 3}, {'item': 'Enthusiastic', 'score': 2}, {'item': 'Proud', 'score': 3}, {'item': 'Alert', 'score': 2}, {'item': 'Inspired', 'score': 2}, {'item': 'Determined', 'score': 3}, {'item': 'Attentive', 'score': 3}, {'item': 'Active', 'score': 2}, 
        # {'item': 'Distressed', 'score': 4}, 
        # {'item': 'Upset', 'score': 4}, 
        # {'item': 'Guilty', 'score': 4}, 
        # {'item': 'Scared', 'score': 3}, 
        # {'item': 'Hostile', 'score': 2}, 
        # {'item': 'Irritable', 'score': 3}, 
        # {'item': 'Ashamed', 'score': 4}, 
        # {'item': 'Nervous', 'score': 4}, 
        # {'item': 'Jittery', 'score': 3}, 
        # {'item': 'Afraid', 'score': 4}]}
        final_score = self._parse_panas_response([it.model_dump() for it in validated.items])
        return {"client": final_score}


    def get_name(self) -> str:
        return "PANAS"
