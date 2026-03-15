"""
dry_run_validator.py

Simulate n8n workflow execution with synthetic mock data to detect
logic problems that structural validation cannot catch:

  - Dead branches in IF nodes (conditions that never evaluate True or False
    for any of the test items → one output port never receives data).
  - Dead branches in Switch nodes (rules that never match → output never used,
    or no rules defined → all outputs dead).
  - Hardcoded comparisons that always resolve the same way.

Usage
-----
    from dry_run_validator import DryRunValidator

    result = DryRunValidator.run(workflow_json)
    if not result.passed:
        for warning in result.warnings:
            print(warning)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BranchCoverage:
    """Tracks which output ports of a branching node fired during simulation."""

    node_name: str
    total_outputs: int          # expected number of output ports
    fired_outputs: set[int] = field(default_factory=set)

    @property
    def dead_outputs(self) -> list[int]:
        return [i for i in range(self.total_outputs) if i not in self.fired_outputs]


@dataclass
class DryRunResult:
    """Result returned by DryRunValidator.run()."""

    warnings: list[str] = field(default_factory=list)
    branch_coverage: list[BranchCoverage] = field(default_factory=list)

    @property
    def dead_branches(self) -> list[tuple[str, int]]:
        """List of (node_name, output_index) for every dead branch."""
        return [
            (cov.node_name, idx)
            for cov in self.branch_coverage
            for idx in cov.dead_outputs
        ]

    @property
    def passed(self) -> bool:
        """True when no dead branches and no warnings were found."""
        return len(self.dead_branches) == 0 and len(self.warnings) == 0


# ---------------------------------------------------------------------------
# Default synthetic test items
# ---------------------------------------------------------------------------

_DEFAULT_MOCK_ITEMS: list[dict] = [
    # Item that satisfies common "is active / has value" conditions
    {"id": 1, "status": "active",   "value": "hello", "count": 5,
     "email": "user@example.com",   "flag": True,     "name": "Alice"},
    # Item that fails those same conditions (inactive, empty, zero)
    {"id": 2, "status": "inactive", "value": "",      "count": 0,
     "email": "",                   "flag": False,    "name": ""},
    # Extra variation
    {"id": 3, "status": "pending",  "value": "world", "count": -1,
     "email": "other@example.com",  "flag": True,     "name": "Bob"},
]

# ---------------------------------------------------------------------------
# Operator evaluation
# ---------------------------------------------------------------------------

_TRUTHY_OPERATORS = {"notEmpty", "isNotEmpty", "exists"}
_FALSY_OPERATORS  = {"empty",    "isEmpty",    "notExists"}


def _eval_operator(left: Any, right: Any, operator: dict) -> bool:
    """Evaluate a single n8n condition operator."""
    op = operator.get("operation", "equals")

    if op in _TRUTHY_OPERATORS:
        return bool(left)
    if op in _FALSY_OPERATORS:
        return not bool(left)

    # Normalise for comparison
    left_s  = "" if left  is None else str(left)
    right_s = "" if right is None else str(right)

    if op in ("equals", "eq", "=="):
        return left_s == right_s
    if op in ("notEquals", "ne", "!="):
        return left_s != right_s
    if op in ("contains",):
        return right_s in left_s
    if op in ("notContains",):
        return right_s not in left_s
    if op in ("startsWith",):
        return left_s.startswith(right_s)
    if op in ("endsWith",):
        return left_s.endswith(right_s)
    if op in ("gt", ">"):
        try:
            return float(left) > float(right)
        except (TypeError, ValueError):
            return False
    if op in ("lt", "<"):
        try:
            return float(left) < float(right)
        except (TypeError, ValueError):
            return False
    if op in ("gte", ">="):
        try:
            return float(left) >= float(right)
        except (TypeError, ValueError):
            return False
    if op in ("lte", "<="):
        try:
            return float(left) <= float(right)
        except (TypeError, ValueError):
            return False
    if op in ("regex", "matches"):
        try:
            return bool(re.search(right_s, left_s))
        except re.error:
            return False

    # Unknown operator — assume True to avoid false positives
    return True


# ---------------------------------------------------------------------------
# Expression resolver
# ---------------------------------------------------------------------------

# Matches: ={{ $json.field.subfield }}  or  ={{ $json["key"] }}
_JSON_EXPR_RE = re.compile(
    r"^=\{\{[^}]*\$json\.([A-Za-z0-9_.]+)[^}]*\}\}$"
)
# Matches literal (non-expression) values like "active", "42"
_LITERAL_RE = re.compile(r"^(?!=\{\{)(.*)$")


def _resolve_left_value(expr: str, item: dict) -> tuple[Any, bool]:
    """
    Resolve a leftValue expression against a mock item.

    Returns
    -------
    (value, resolved) — resolved=False when the expression can't be parsed
    (e.g. uses $('NodeName'), complex logic, etc.).
    """
    expr = (expr or "").strip()
    m = _JSON_EXPR_RE.match(expr)
    if not m:
        # Not a simple $json.path expression → treat as unresolvable
        return None, False

    path = m.group(1).strip().rstrip(".")
    parts = path.split(".")
    value: Any = item
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list):
            try:
                value = value[int(part)]
            except (ValueError, IndexError):
                return None, False
        else:
            return None, False  # field not found in mock data
    return value, True


def _resolve_right_value(expr: str) -> Any:
    """Parse a rightValue — usually a literal string or number."""
    if expr is None:
        return None
    expr_s = str(expr).strip()
    # Try numeric
    try:
        return int(expr_s)
    except ValueError:
        pass
    try:
        return float(expr_s)
    except ValueError:
        pass
    return expr_s


# ---------------------------------------------------------------------------
# IF node evaluation
# ---------------------------------------------------------------------------

def _evaluate_if_conditions(conditions_cfg: dict, item: dict) -> bool | None:
    """
    Evaluate IF node conditions against *item*.

    Returns
    -------
    True  → item goes to output 0 (true branch)
    False → item goes to output 1 (false branch)
    None  → condition cannot be evaluated (unresolvable expressions)
    """
    conditions = conditions_cfg.get("conditions", [])
    combinator = conditions_cfg.get("combinator", "and").lower()

    if not conditions:
        # No conditions configured → always False (n8n behaviour)
        return False

    results: list[bool] = []
    for cond in conditions:
        left_expr  = cond.get("leftValue",  "")
        right_expr = cond.get("rightValue", "")
        operator   = cond.get("operator",   {})

        left, resolved = _resolve_left_value(left_expr, item)
        if not resolved:
            # Could not resolve — skip this condition
            continue

        right = _resolve_right_value(right_expr)
        results.append(_eval_operator(left, right, operator))

    if not results:
        return None  # all conditions unresolvable

    if combinator == "or":
        return any(results)
    return all(results)


# ---------------------------------------------------------------------------
# Switch node evaluation
# ---------------------------------------------------------------------------

def _evaluate_switch_rules(parameters: dict, item: dict) -> int | None:
    """
    Evaluate Switch node rules against *item*.

    Returns
    -------
    int   → output port index that matches (0-based)
    None  → no rule matched (goes to fallback / no output)
    """
    rules = parameters.get("rules", {}).get("rules", [])
    for idx, rule in enumerate(rules):
        conditions_cfg = rule.get("conditions", {})
        result = _evaluate_if_conditions(conditions_cfg, item)
        if result is True:
            return idx
    return None  # no rule matched


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------

_IF_TYPE     = "n8n-nodes-base.if"
_SWITCH_TYPE = "n8n-nodes-base.switch"
_BRANCH_TYPES = {_IF_TYPE, _SWITCH_TYPE}


class DryRunValidator:
    """
    Simulate n8n workflow execution with mock data and detect dead branches.

    The validator does **not** perform full graph traversal.  Instead it
    evaluates every IF/Switch node independently against all mock items,
    tracks which output ports fired, and reports ports that never fired.

    This catches:
    - IF with empty conditions (true branch is always dead)
    - IF with hardcoded comparisons that always resolve the same way
    - Switch with no rules (all outputs dead)
    - Conditions that reference fields absent from all test items
    """

    @classmethod
    def run(
        cls,
        workflow: dict,
        mock_items: list[dict] | None = None,
    ) -> DryRunResult:
        """
        Parameters
        ----------
        workflow:   n8n workflow JSON dict (must have "nodes" key).
        mock_items: Synthetic data items to test against.
                    Defaults to DryRunValidator._DEFAULT_MOCK_ITEMS.

        Returns
        -------
        DryRunResult with warnings and dead_branches populated.
        """
        if mock_items is None:
            mock_items = _DEFAULT_MOCK_ITEMS

        result = DryRunResult()
        nodes = workflow.get("nodes", [])

        for node in nodes:
            node_type = node.get("type", "")
            if node_type not in _BRANCH_TYPES:
                continue

            if node_type == _IF_TYPE:
                cls._analyse_if_node(node, mock_items, result)
            elif node_type == _SWITCH_TYPE:
                cls._analyse_switch_node(node, mock_items, result)

        return result

    # ------------------------------------------------------------------
    # IF analysis
    # ------------------------------------------------------------------

    @classmethod
    def _analyse_if_node(
        cls,
        node: dict,
        mock_items: list[dict],
        result: DryRunResult,
    ) -> None:
        name = node.get("name", "?")
        params = node.get("parameters", {})
        conditions_cfg = params.get("conditions", {})

        coverage = BranchCoverage(node_name=name, total_outputs=2)
        unresolvable_count = 0

        for item in mock_items:
            outcome = _evaluate_if_conditions(conditions_cfg, item)
            if outcome is True:
                coverage.fired_outputs.add(0)
            elif outcome is False:
                coverage.fired_outputs.add(1)
            else:
                unresolvable_count += 1

        result.branch_coverage.append(coverage)

        dead = coverage.dead_outputs
        if dead:
            branch_names = {0: "true (output 0)", 1: "false (output 1)"}
            for port in dead:
                branch_label = branch_names.get(port, f"output {port}")
                result.warnings.append(
                    f"[IF '{name}'] Ветка {branch_label} никогда не срабатывает "
                    f"ни с одним из {len(mock_items)} тестовых элементов."
                )

        if unresolvable_count == len(mock_items):
            result.warnings.append(
                f"[IF '{name}'] Условия содержат сложные выражения "
                f"($('NodeName'), вычисляемые поля), которые не могут быть "
                f"оценены статически. Проверь вручную."
            )

    # ------------------------------------------------------------------
    # Switch analysis
    # ------------------------------------------------------------------

    @classmethod
    def _analyse_switch_node(
        cls,
        node: dict,
        mock_items: list[dict],
        result: DryRunResult,
    ) -> None:
        name = node.get("name", "?")
        params = node.get("parameters", {})
        rules = params.get("rules", {}).get("rules", [])

        if not rules:
            coverage = BranchCoverage(node_name=name, total_outputs=0)
            result.branch_coverage.append(coverage)
            result.warnings.append(
                f"[Switch '{name}'] Нет правил — все выходы мертвы. "
                f"Добавь хотя бы одно правило."
            )
            return

        coverage = BranchCoverage(node_name=name, total_outputs=len(rules))

        for item in mock_items:
            matched = _evaluate_switch_rules(params, item)
            if matched is not None:
                coverage.fired_outputs.add(matched)

        result.branch_coverage.append(coverage)

        dead = coverage.dead_outputs
        for port in dead:
            result.warnings.append(
                f"[Switch '{name}'] Правило {port} (output {port}) никогда не "
                f"срабатывает ни с одним из {len(mock_items)} тестовых элементов."
            )
