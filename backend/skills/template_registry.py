"""TemplateRegistry — discovers and loads n8n workflow templates.

Templates live in skills/n8n_templates/*.json.
Each file contains a top-level ``_meta`` object:

    {
      "_meta": {
        "id":          "content_factory",
        "name":        "Content Factory",
        "description": "...",
        "keywords":    ["rss", "content", "factory", ...],
        "required_params": ["FEED_URL"],
        "optional_params": ["REWRITE_PROMPT", ...]
      },
      ... normal n8n workflow JSON ...
    }
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

_DEFAULT_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "n8n_templates")


class TemplateRegistry:
    """Load and search n8n workflow templates from the templates directory."""

    def __init__(self, templates_dir: Optional[str] = None) -> None:
        self.templates_dir = templates_dir or _DEFAULT_TEMPLATES_DIR
        self._cache: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_all(self) -> List[dict]:
        """Return metadata dicts for every template file found."""
        metas = []
        for fname in self._json_files():
            tpl = self._load_file(fname)
            if tpl:
                metas.append(tpl.get("_meta", {"id": fname, "name": fname}))
        return metas

    def load(self, template_id: str) -> Optional[dict]:
        """Load a template by its ``_meta.id``.  Returns the full dict or None."""
        if template_id in self._cache:
            return self._cache[template_id]
        for fname in self._json_files():
            tpl = self._load_file(fname)
            if tpl and tpl.get("_meta", {}).get("id") == template_id:
                self._cache[template_id] = tpl
                return tpl
        return None

    def find(self, query: str) -> Optional[str]:
        """Return the template id whose keywords best match *query*, or None."""
        query_low = query.lower()
        best_id: Optional[str] = None
        best_score = 0
        for fname in self._json_files():
            tpl = self._load_file(fname)
            if not tpl:
                continue
            meta = tpl.get("_meta", {})
            keywords: List[str] = meta.get("keywords", [])
            score = sum(1 for kw in keywords if kw.lower() in query_low)
            if score > best_score:
                best_score = score
                best_id = meta.get("id")
        return best_id if best_score > 0 else None

    def find_and_load(self, query: str) -> Optional[dict]:
        """Convenience: find + load in one call."""
        tid = self.find(query)
        return self.load(tid) if tid else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _json_files(self) -> List[str]:
        if not os.path.isdir(self.templates_dir):
            return []
        return [
            f for f in os.listdir(self.templates_dir)
            if f.endswith(".json")
        ]

    def _load_file(self, filename: str) -> Optional[dict]:
        path = os.path.join(self.templates_dir, filename)
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None
