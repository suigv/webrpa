from typing import Dict


class LLMClient:
    def evaluate(self, prompt: str) -> Dict[str, object]:
        return {"ok": True, "prompt": prompt, "result": "stub"}
