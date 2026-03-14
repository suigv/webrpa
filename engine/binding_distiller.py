from __future__ import annotations

import json
import logging
from typing import Any

from ai_services.llm_client import LLMClient, LLMRequest
from engine.actions._state_detection_support import preprocess_xml

logger = logging.getLogger(__name__)

class BindingDistiller:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client or LLMClient()

    def analyze_ui_state(
        self,
        xml: str,
        app_name: str,
        known_states: list[str],
        xml_filter: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Analyzes a UI state using LLM and returns suggested state_id and features."""
        flt = xml_filter or {}
        node_text = preprocess_xml(xml, **flt)
        known_str = ", ".join(known_states) if known_states else "None"
        
        prompt = f"""You are a mobile UI analysis expert. Below is a compressed node list of the current screen for the app '{app_name}':

{node_text}

Already recorded states: {known_str}

Tasks:
1. Determine the status/state name for this screen (use lowercase snake_case, e.g., home_feed, login_screen).
2. Identify 2-3 most stable identification features:
   - Use 'text=xxx' for static UI text.
   - Use 'resource-id=com.package:id/element' for static IDs.
   - DO NOT use 'bounds' coordinates.
   - DO NOT use dynamic content (names, counts, times).

Return EXACTLY a JSON object:
{{
  "state_id": "string",
  "features": ["feature1", "feature2"],
  "reason": "short explanation"
}}"""

        request = LLMRequest(
            prompt=prompt,
            response_format={"type": "json_object"},
        )
        
        try:
            response = self._llm_client.evaluate(request)
            if not response.ok:
                return {"state_id": "unknown", "features": [], "reason": f"LLM error: {response.error}"}
            
            if response.structured_state and isinstance(response.structured_state, dict):
                return response.structured_state
            
            output = response.output_text.strip()
            # Clean markdown if present
            if output.startswith("```"):
                lines = output.splitlines()
                output = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                
            return json.loads(output)
        except Exception as exc:
            logger.exception("AI UI state analysis failed")
            return {"state_id": "unknown", "features": [], "reason": f"Exception: {exc}"}

    def generate_binding_code(self, app_name: str, records: list[dict[str, Any]]) -> str:
        """Generates Python code for detect_stage function based on multiple records."""
        # Sanitize records for prompt
        slim = [{"state_id": r["state_id"], "features": r["features"]} for r in records]
        records_str = json.dumps(slim, ensure_ascii=False, indent=2)
        
        prompt = f"""Based on the following UI state records for the app '{app_name}', generate a Python function 'detect_{app_name}_stage(rpc)'.

Records:
{records_str}

Requirements:
1. Signature: def detect_{app_name}_stage(rpc: Any) -> str
2. Use 'query_any_text_contains(rpc, ["text1", "text2"])' for text-based matching.
3. Order from most specific to most general.
4. Return 'unknown' as fallback.
5. Output ONLY the Python code, no explanation.

Imports available:
from engine.actions._state_detection_support import query_any_text_contains
"""

        request = LLMRequest(prompt=prompt)
        try:
            response = self._llm_client.evaluate(request)
            return response.output_text
        except Exception as exc:
            logger.exception("AI binding code generation failed")
            return f"# LLM generation failed: {exc}"
