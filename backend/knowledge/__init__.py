"""Knowledge layer — local-first context retrieval for workflow generation.

Provides relevant context to the LLM before generating or repairing workflows.
Sources (in priority order):
  1. repair_memory   — previously solved errors
  2. instruction_packs — n8n node-specific rules and patterns
  3. templates       — saved workflow templates (golden + user-generated)
  4. docs_cache      — cached n8n documentation fragments

No vector DB. Plain file-based lookup with keyword matching.
"""
from knowledge.knowledge_selector import KnowledgeSelector

__all__ = ["KnowledgeSelector"]
