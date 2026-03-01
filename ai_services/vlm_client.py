from typing import Dict


class VLMClient:
    def evaluate(self, image_ref: str, prompt: str) -> Dict[str, object]:
        return {"ok": True, "image_ref": image_ref, "prompt": prompt, "result": "stub"}
