"""TemplateAdapter — substitutes {{PARAM}} placeholders into an n8n template.

Usage::

    from skills.template_registry import TemplateRegistry
    from skills.template_adapter import TemplateAdapter

    registry = TemplateRegistry()
    template = registry.load("content_factory")

    adapter = TemplateAdapter()
    # Check required params before adapting:
    missing = adapter.get_missing_required(template, {"WORKFLOW_NAME": "My Factory"})
    # → ["FEED_URL"]   ← required but not supplied

    workflow_json = adapter.adapt(template, {
        "FEED_URL":       "https://example.com/rss",
        "WORKFLOW_NAME":  "My Content Factory",
        "REWRITE_PROMPT": "Summarise this article in 3 sentences:",
        "OUTPUT_FILE":    "/tmp/output.jsonl",
    })
    # workflow_json is ready to POST to n8n.

The adapter:
  1. Deep-copies the template dict.
  2. Strips the ``_meta`` key (n8n doesn't accept extra top-level keys).
  3. Serialises to JSON string, performs {{KEY}} → value substitution.
  4. Deserialises back to dict and returns it.

Required params (listed in ``_meta.required_params``) are NOT defaulted.
Optional params get sensible defaults (see ``_OPTIONAL_DEFAULTS``).
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, List, Optional

# Only optional params get defaults.  Required params must be supplied by the user.
# These defaults apply across ALL templates; per-template naming is handled in controller.py.
_OPTIONAL_DEFAULTS: Dict[str, str] = {
    "WORKFLOW_NAME":       "Workflow",
    "REWRITE_PROMPT":      "Summarise this article concisely:",
    "OUTPUT_FILE":         "events.csv",
    "OUTPUT":              "none",
    "OPENAI_API_KEY":      "YOUR_OPENAI_API_KEY",
    "SCHEDULE_INTERVAL":   "0 * * * *",
}


class TemplateAdapter:
    """Replace ``{{PARAM}}`` placeholders in a template with real values."""

    def adapt(self, template: dict, params: Dict[str, Any]) -> dict:
        """Return a new workflow dict ready to POST to n8n.

        Args:
            template: Full template dict (including ``_meta``).
            params:   Substitution values.  Required params MUST be present.
        """
        # 1. Deep-copy so we never mutate the cached template.
        tpl = copy.deepcopy(template)

        # 2. Strip non-n8n keys.
        tpl.pop("_meta", None)

        # 3. Build substitution map: optional defaults first, user params override.
        subs = dict(_OPTIONAL_DEFAULTS)
        subs.update({k: str(v) for k, v in params.items() if v is not None})

        # 4. Serialise → substitute → deserialise.
        raw = json.dumps(tpl, ensure_ascii=False)
        raw = self._substitute(raw, subs)
        return json.loads(raw)

    def get_missing_required(
        self, template: dict, params: Dict[str, Any]
    ) -> List[str]:
        """Return list of required param names that are missing or empty in *params*."""
        required: List[str] = (
            template.get("_meta", {}).get("required_params", [])
        )
        return [
            key for key in required
            if not (params.get(key) or "").strip()
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _substitute(text: str, subs: Dict[str, str]) -> str:
        """Replace every ``{{KEY}}`` occurrence with the corresponding value."""
        def _replacer(m: re.Match) -> str:
            key = m.group(1)
            return subs.get(key, m.group(0))  # leave unresolved placeholders as-is

        return re.sub(r"\{\{([A-Z0-9_]+)\}\}", _replacer, text)

    @staticmethod
    def extract_placeholders(template: dict) -> List[str]:
        """Return sorted list of all ``{{PARAM}}`` keys found in the template."""
        raw = json.dumps(template)
        return sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", raw)))
