"""KnowledgeSelector — retrieves relevant local context before LLM calls.

This is a minimal keyword-based retrieval layer. No vector DB.
It searches local knowledge sources and returns relevant fragments
to inject into the LLM prompt, reducing hallucination and token waste.

STATUS: SCAFFOLDED — basic file loading works; smart retrieval is future work.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# Base directory for knowledge assets
_KNOWLEDGE_DIR = Path(__file__).parent
_REPAIR_MEMORY_DIR = _KNOWLEDGE_DIR / "repair_memory"
_INSTRUCTION_PACKS_DIR = _KNOWLEDGE_DIR / "instruction_packs"
_TEMPLATES_DIR = _KNOWLEDGE_DIR / "templates"
_DOCS_CACHE_DIR = _KNOWLEDGE_DIR / "docs_cache"


# Explicit keyword-to-pack mapping.
# Maps task keywords to instruction pack filenames (stems).
# Used when filename-based matching would miss relevant packs.
_KEYWORD_INDEX: Dict[str, List[str]] = {
    # n8n_terminology — retrieved for any workflow generation or naming task
    "workflow": ["n8n_terminology"],
    "node": ["n8n_terminology"],
    "trigger": ["n8n_terminology"],
    "credential": ["n8n_terminology"],
    "create": ["n8n_terminology"],
    "generate": ["n8n_terminology"],
    "build": ["n8n_terminology"],
    "name": ["n8n_terminology"],
    "naming": ["n8n_terminology"],
    # error_message_patterns — retrieved for error/repair contexts
    "error": ["error_message_patterns"],
    "fail": ["error_message_patterns"],
    "failed": ["error_message_patterns"],
    "broken": ["error_message_patterns"],
    "repair": ["error_message_patterns", "debug_routing_confidence"],
    "fix": ["error_message_patterns", "debug_routing_confidence"],
    # debug_routing_confidence — retrieved for debug/repair tasks
    "debug": ["debug_routing_confidence"],
    "execution": ["debug_routing_confidence"],
    "inspect": ["debug_routing_confidence"],
    "diagnose": ["debug_routing_confidence"],
    "bailout": ["debug_routing_confidence"],
    "confidence": ["debug_routing_confidence"],
    "timeout": ["debug_routing_confidence", "error_message_patterns"],
    "401": ["debug_routing_confidence", "error_message_patterns"],
    "403": ["debug_routing_confidence", "error_message_patterns"],
    "429": ["debug_routing_confidence", "error_message_patterns"],
    "404": ["debug_routing_confidence", "error_message_patterns"],
}


class KnowledgeSelector:
    """Retrieve relevant context fragments for a given task."""

    def __init__(self, extra_skills_dir: Optional[Path] = None):
        """
        Args:
            extra_skills_dir: path to skills/instructions/ for backward compat
                              with existing skill loading in brain_layer.py
        """
        self._extra_skills_dir = extra_skills_dir

    def retrieve_context(
        self,
        task: str,
        node_types: Optional[List[str]] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Gather relevant knowledge for a task.

        Returns dict with keys:
          - repair_hints: list of relevant past error fixes
          - instruction_fragments: list of relevant instruction text
          - template_matches: list of matching template filenames
          - sources_used: list of source names for logging
        """
        result: Dict[str, Any] = {
            "repair_hints": [],
            "instruction_fragments": [],
            "template_matches": [],
            "sources_used": [],
        }

        # 1. Search repair memory
        if error_message:
            hints = self._search_repair_memory(error_message)
            if hints:
                result["repair_hints"] = hints
                result["sources_used"].append("repair_memory")

        # 2. Search instruction packs by node type or task keywords
        instructions = self._search_instructions(task, node_types)
        if instructions:
            result["instruction_fragments"] = instructions
            result["sources_used"].append("instruction_packs")

        # 3. Search templates by task description
        templates = self._search_templates(task)
        if templates:
            result["template_matches"] = templates
            result["sources_used"].append("templates")

        return result

    # -- internal search methods -------------------------------------------

    def _search_repair_memory(self, error_message: str) -> List[Dict[str, str]]:
        """Find past fixes matching the error pattern."""
        results = []
        memory_file = _REPAIR_MEMORY_DIR / "error_corrections.json"
        if not memory_file.exists():
            return results

        try:
            corrections = json.loads(memory_file.read_text(encoding="utf-8"))
            error_lower = error_message.lower()
            for entry in corrections:
                pattern = entry.get("error_pattern", "").lower()
                if pattern and pattern in error_lower:
                    results.append(entry)
        except (json.JSONDecodeError, OSError):
            pass
        return results

    def _search_instructions(
        self, task: str, node_types: Optional[List[str]] = None
    ) -> List[str]:
        """Find instruction fragments relevant to the task or node types."""
        results = []
        matched_stems: set = set()
        task_lower = task.lower()
        task_words = [w for w in task_lower.split() if len(w) > 2]

        # Phase 1: keyword index lookup (explicit mapping, catches short words like "fix")
        for word in task_words:
            for stem in _KEYWORD_INDEX.get(word, []):
                if stem not in matched_stems:
                    pack_file = _INSTRUCTION_PACKS_DIR / f"{stem}.md"
                    if pack_file.exists():
                        results.append(pack_file.read_text(encoding="utf-8")[:2000])
                        matched_stems.add(stem)

        # Phase 2: node-type matching (e.g. "httpRequest" -> http_request_patterns.md)
        if node_types:
            for md_file in _INSTRUCTION_PACKS_DIR.glob("*.md"):
                if md_file.stem in matched_stems:
                    continue
                name = md_file.stem.lower().replace("_", " ").replace("-", " ")
                for nt in node_types:
                    if nt.lower().replace("n8n-nodes-base.", "") in name:
                        results.append(md_file.read_text(encoding="utf-8")[:2000])
                        matched_stems.add(md_file.stem)
                        break

        # Phase 3: filename word matching (fallback for packs not in keyword index)
        for md_file in _INSTRUCTION_PACKS_DIR.glob("*.md"):
            if md_file.stem in matched_stems:
                continue
            name = md_file.stem.lower().replace("_", " ").replace("-", " ")
            if any(word in name for word in task_words if len(word) > 3):
                results.append(md_file.read_text(encoding="utf-8")[:2000])
                matched_stems.add(md_file.stem)

        # Phase 4: legacy skills/instructions/ (backward compat)
        if self._extra_skills_dir and self._extra_skills_dir.exists():
            for md_file in self._extra_skills_dir.glob("*.md"):
                name = md_file.stem.lower()
                if any(word in name for word in task_words if len(word) > 3):
                    results.append(md_file.read_text(encoding="utf-8")[:2000])

        return results[:5]  # limit to avoid prompt bloat

    def _search_templates(self, task: str) -> List[str]:
        """Find template files matching the task description."""
        results = []
        task_lower = task.lower()

        for json_file in _TEMPLATES_DIR.glob("*.json"):
            name = json_file.stem.lower().replace("_", " ")
            if any(word in name for word in task_lower.split() if len(word) > 3):
                results.append(str(json_file))

        return results[:5]
