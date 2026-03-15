"""
workflow_generator.py

N8nAgent: generates n8n workflow JSON by filling parameters into a base template,
then validates the result with N8nValidator. Retries up to MAX_RETRIES times on
validation errors, passing the error text back to the LLM for correction.
Falls back to the raw base template if all attempts fail.

Sub-workflow splitting
----------------------
Large workflows (> MAX_NODES_PER_WORKFLOW nodes) are automatically split into
smaller sub-workflows connected via "Execute Workflow" nodes.

Use ``N8nAgent.build_workflows()`` (plural) to get a list of sub-workflow dicts
when the generated workflow exceeds the node limit.  ``build_workflow()`` (singular)
stays unchanged for backward compatibility — it returns a single dict.
"""

import copy
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from n8n_validator import N8nValidator, N8nValidationException

MAX_RETRIES = 3
MAX_NODES_PER_WORKFLOW = 10   # trigger split when exceeded
_DEFAULT_CHUNK_SIZE = 7       # nodes per sub-workflow (≤ MAX_NODES_PER_WORKFLOW)

_BLOCKS_DIR = Path(__file__).parent / "skills" / "n8n_blocks"


# ---------------------------------------------------------------------------
# BlockLibrary
# ---------------------------------------------------------------------------

class BlockLibrary:
    """Loads and returns node skeleton JSON from skills/n8n_blocks/."""

    _cache: dict[str, dict] = {}

    @classmethod
    def get_block(cls, block_name: str) -> dict:
        """
        Return a deep copy of the block skeleton for *block_name*
        (e.g. "http_request", "code", "set", "webhook").
        Raises FileNotFoundError if the block JSON does not exist.
        """
        if block_name not in cls._cache:
            path = _BLOCKS_DIR / f"{block_name}.json"
            if not path.exists():
                raise FileNotFoundError(
                    f"Block '{block_name}' not found in {_BLOCKS_DIR}"
                )
            with open(path, encoding="utf-8") as fh:
                cls._cache[block_name] = json.load(fh)
        block = copy.deepcopy(cls._cache[block_name])
        # Replace placeholder UUIDs
        block_str = json.dumps(block).replace("{uuid}", str(uuid.uuid4()))
        return json.loads(block_str)

    @classmethod
    def list_blocks(cls) -> list[str]:
        return [p.stem for p in _BLOCKS_DIR.glob("*.json")]


# ---------------------------------------------------------------------------
# TemplateManager
# ---------------------------------------------------------------------------

class TemplateManager:
    """Loads base workflow templates (full workflow JSON files)."""

    def __init__(self, templates_dir: str | Path | None = None):
        if templates_dir is None:
            templates_dir = Path(__file__).parent / "skills" / "n8n_templates"
        self._dir = Path(templates_dir)

    def get_template(self, name: str) -> dict:
        """Load a template by name (without .json extension)."""
        path = self._dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Template '{name}' not found in {self._dir}")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)


# ---------------------------------------------------------------------------
# Sub-workflow splitter
# ---------------------------------------------------------------------------

def split_workflow(workflow: dict, chunk_size: int = _DEFAULT_CHUNK_SIZE) -> list[dict]:
    """
    Split a large workflow into multiple smaller sub-workflows.

    Nodes are ordered by their x-position (left→right), then grouped into
    chunks of at most *chunk_size*.  All chunks except the last get an
    "Execute Workflow" node appended that links to the next part.
    Connections that cross chunk boundaries are replaced by this bridge node.

    Parameters
    ----------
    workflow:   Full n8n workflow JSON dict.
    chunk_size: Maximum number of nodes per sub-workflow (default 7).
                Must be ≥ 1.

    Returns
    -------
    List of workflow dicts (len == 1 when no split was needed).
    Each sub-workflow has ``name``, ``nodes``, ``connections``, ``settings``.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")

    nodes = workflow.get("nodes", [])
    connections = workflow.get("connections", {})
    base_name = workflow.get("name", "Workflow")
    settings = workflow.get("settings", {})

    if len(nodes) <= chunk_size:
        return [workflow]

    # Sort by x-position so chunks follow visual left-to-right execution order
    sorted_nodes = sorted(nodes, key=lambda n: n.get("position", [0, 0])[0])

    # Build chunks
    chunks: list[list[dict]] = [
        sorted_nodes[i : i + chunk_size]
        for i in range(0, len(sorted_nodes), chunk_size)
    ]

    sub_workflows: list[dict] = []

    for part_idx, chunk in enumerate(chunks):
        chunk_node_names: set[str] = {n["name"] for n in chunk}
        is_last_chunk = part_idx == len(chunks) - 1

        # ---- Filter connections to only intra-chunk ones ----
        chunk_connections: dict = {}
        for src, routing in connections.items():
            if src not in chunk_node_names:
                continue
            filtered_main: list[list] = []
            for output_list in routing.get("main", []):
                filtered = [
                    c for c in output_list
                    if isinstance(c, dict) and c.get("node") in chunk_node_names
                ]
                filtered_main.append(filtered)
            chunk_connections[src] = {"main": filtered_main}

        chunk_nodes: list[dict] = list(chunk)

        # ---- Add Execute Workflow bridge (all chunks except the last) ----
        if not is_last_chunk:
            next_part_num = part_idx + 2  # 1-based
            bridge_name = f"Continue to Part {next_part_num}"
            bridge_node = {
                "id": str(uuid.uuid4()),
                "name": bridge_name,
                "type": "n8n-nodes-base.executeWorkflow",
                "typeVersion": 1.1,
                "parameters": {
                    "source": "parameter",
                    "workflowId": {
                        "__rl": True,
                        "value": f"__PART_{next_part_num}__",
                        "mode": "id",
                    },
                    "options": {},
                },
                "position": [
                    (chunk[-1].get("position", [0, 0])[0] + 250),
                    (chunk[-1].get("position", [0, 0])[1]),
                ],
            }

            # Wire the last node of this chunk → bridge
            last_node_name = chunk[-1]["name"]
            existing = chunk_connections.get(last_node_name, {})
            existing_main = existing.get("main", [])
            # Append bridge as output 0 of the last node (don't overwrite existing)
            if not existing_main:
                existing_main = []
            existing_main.append(
                [{"node": bridge_name, "type": "main", "index": 0}]
            )
            chunk_connections[last_node_name] = {"main": existing_main}

            chunk_nodes.append(bridge_node)

        sub_wf = {
            "name": f"{base_name} - Part {part_idx + 1}",
            "nodes": chunk_nodes,
            "connections": chunk_connections,
            "settings": settings,
        }
        sub_workflows.append(sub_wf)

    logging.info(
        f"split_workflow: {len(nodes)} nodes → {len(sub_workflows)} sub-workflows "
        f"(chunk_size={chunk_size})"
    )
    return sub_workflows


# ---------------------------------------------------------------------------
# N8nAgent
# ---------------------------------------------------------------------------

class N8nAgent:
    """
    Generates an n8n workflow JSON from a base template and a user intent.

    Parameters
    ----------
    llm_client:
        Any object with a ``complete(prompt: str) -> str`` method.
    template_manager:
        TemplateManager instance with ``get_template(name) -> dict``.
    """

    # System prompt injected into every generation request.
    # Instructs the LLM to keep individual workflows small.
    SYSTEM_PROMPT = (
        "ПРАВИЛА ГЕНЕРАЦИИ n8n WORKFLOW:\n"
        "1. Максимум 7–10 узлов в одном workflow.\n"
        "2. Если задача сложнее — предусматривай разбивку на sub-workflows.\n"
        "3. Для связи между sub-workflows используй узел Execute Workflow.\n"
        "4. Используй ТОЛЬКО поля, которые реально существуют в ответах API.\n"
        "5. Возвращай ТОЛЬКО валидный JSON без пояснений.\n"
    )

    def __init__(self, llm_client: Any, template_manager: TemplateManager):
        self.llm = llm_client
        self.templates = template_manager

    # ------------------------------------------------------------------
    # Public: single workflow (backward compatible)
    # ------------------------------------------------------------------

    def build_workflow(self, user_intent: str, base_template_name: str) -> dict:
        """
        Build a single workflow dict.

        If the generated workflow has > MAX_NODES_PER_WORKFLOW nodes it is
        *not* automatically split — use ``build_workflows()`` for that.

        Tries up to MAX_RETRIES times; on validation failure the error is
        fed back to the LLM.  Falls back to the unmodified base template
        when all retries are exhausted.
        """
        base_workflow = self.templates.get_template(base_template_name)
        attempts = 0
        current_workflow = copy.deepcopy(base_workflow)
        last_error = ""

        while attempts < MAX_RETRIES:
            try:
                current_workflow = self._generate_parameters(
                    current_workflow, user_intent, last_error
                )
                N8nValidator.validate_workflow(current_workflow)
                logging.info("Workflow успешно прошел валидацию.")
                return current_workflow

            except N8nValidationException as e:
                attempts += 1
                last_error = str(e)
                logging.warning(
                    f"Попытка {attempts}/{MAX_RETRIES} провалена: {last_error}"
                )
            except Exception as e:  # LLM or JSON parse errors
                attempts += 1
                last_error = f"Unexpected error: {e}"
                logging.warning(
                    f"Попытка {attempts}/{MAX_RETRIES} ошибка LLM/parse: {last_error}"
                )

        logging.error("Превышен лимит попыток. Откат к базовому шаблону.")
        return copy.deepcopy(base_workflow)

    # ------------------------------------------------------------------
    # Public: auto-split into sub-workflows
    # ------------------------------------------------------------------

    def build_workflows(
        self,
        user_intent: str,
        base_template_name: str,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
    ) -> list[dict]:
        """
        Build one or more sub-workflows for *user_intent*.

        Calls ``build_workflow`` then checks node count.  If the result
        exceeds MAX_NODES_PER_WORKFLOW, ``split_workflow`` is called to
        produce a list of smaller connected sub-workflows.

        Parameters
        ----------
        user_intent:        Natural-language description of the desired flow.
        base_template_name: Template name passed to TemplateManager.
        chunk_size:         Max nodes per sub-workflow (default 7).

        Returns
        -------
        List of workflow dicts — usually a single element, multiple when split.
        """
        workflow = self.build_workflow(user_intent, base_template_name)
        node_count = len(workflow.get("nodes", []))

        if node_count > MAX_NODES_PER_WORKFLOW:
            logging.info(
                f"build_workflows: {node_count} nodes > {MAX_NODES_PER_WORKFLOW} "
                f"— splitting into sub-workflows (chunk_size={chunk_size})"
            )
            return split_workflow(workflow, chunk_size=chunk_size)

        return [workflow]

    # ------------------------------------------------------------------
    # Internal: LLM interaction
    # ------------------------------------------------------------------

    def _generate_parameters(
        self, workflow: dict, intent: str, error_feedback: str
    ) -> dict:
        prompt = self._build_prompt(workflow, intent, error_feedback)
        raw = self.llm.complete(prompt)
        return self._parse_llm_response(raw)

    def _build_prompt(self, workflow: dict, intent: str, error_feedback: str) -> str:
        feedback_section = ""
        if error_feedback:
            feedback_section = (
                f"\n\nПредыдущая попытка вернула ошибку валидации:\n{error_feedback}\n"
                "Исправь workflow так, чтобы эта ошибка больше не возникала."
            )

        return (
            f"{self.SYSTEM_PROMPT}\n"
            "Заполни поля `parameters` и `name` каждого узла в следующем JSON, "
            "реализуя описанный сценарий.\n\n"
            f"Сценарий: {intent}\n\n"
            f"Базовый workflow:\n"
            f"{json.dumps(workflow, ensure_ascii=False, indent=2)}"
            f"{feedback_section}"
        )

    @staticmethod
    def _parse_llm_response(raw: str) -> dict:
        """Extract JSON from the LLM response string (strips markdown fences)."""
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            raw = "\n".join(inner)
        return json.loads(raw)
