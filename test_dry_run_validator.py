"""
test_dry_run_validator.py

Unit tests for:
  - dry_run_validator.DryRunValidator  (dead branch detection)
  - workflow_generator.split_workflow  (sub-workflow splitting)
  - workflow_generator.N8nAgent.build_workflows (auto-split on > 10 nodes)
"""

import unittest
from unittest.mock import MagicMock

from dry_run_validator import DryRunValidator, DryRunResult, _evaluate_if_conditions
from workflow_generator import split_workflow, N8nAgent, MAX_NODES_PER_WORKFLOW


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_if_node(name: str, conditions: list, combinator: str = "and") -> dict:
    return {
        "name": name,
        "type": "n8n-nodes-base.if",
        "parameters": {
            "conditions": {
                "conditions": conditions,
                "combinator": combinator,
            }
        },
    }


def _make_switch_node(name: str, rules: list) -> dict:
    return {
        "name": name,
        "type": "n8n-nodes-base.switch",
        "parameters": {
            "rules": {"rules": rules}
        },
    }


def _cond(left: str, right: str, op: str = "equals") -> dict:
    return {
        "leftValue": left,
        "rightValue": right,
        "operator": {"type": "string", "operation": op},
    }


def _minimal_workflow(nodes: list) -> dict:
    return {"nodes": nodes, "connections": {}}


# ---------------------------------------------------------------------------
# DryRunValidator — no branching nodes
# ---------------------------------------------------------------------------

class NoBranchingTests(unittest.TestCase):

    def test_linear_workflow_no_warnings(self):
        wf = _minimal_workflow([
            {"name": "Webhook", "type": "n8n-nodes-base.webhook", "parameters": {}},
            {"name": "Set", "type": "n8n-nodes-base.set", "parameters": {}},
        ])
        result = DryRunValidator.run(wf)
        self.assertTrue(result.passed)
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.dead_branches, [])

    def test_empty_nodes_passes(self):
        result = DryRunValidator.run({"nodes": [], "connections": {}})
        self.assertTrue(result.passed)

    def test_no_nodes_key_passes(self):
        result = DryRunValidator.run({"connections": {}})
        self.assertTrue(result.passed)


# ---------------------------------------------------------------------------
# IF node — both branches fire
# ---------------------------------------------------------------------------

class IfBothBranchesTests(unittest.TestCase):

    def test_status_equals_condition_both_branches(self):
        """Default mock data has status='active' and status='inactive' → both fire."""
        node = _make_if_node(
            "Filter Active",
            [_cond("={{ $json.status }}", "active")],
        )
        result = DryRunValidator.run(_minimal_workflow([node]))
        self.assertTrue(result.passed, msg=f"Warnings: {result.warnings}")

    def test_flag_truthy_condition_both_branches(self):
        """flag=True and flag=False in defaults → both branches fire."""
        node = _make_if_node(
            "Flag Check",
            [_cond("={{ $json.flag }}", "True")],
        )
        result = DryRunValidator.run(_minimal_workflow([node]))
        self.assertTrue(result.passed)


# ---------------------------------------------------------------------------
# IF node — dead true branch
# ---------------------------------------------------------------------------

class IfDeadTrueBranchTests(unittest.TestCase):

    def test_empty_conditions_true_branch_dead(self):
        """IF with no conditions always sends to false (output 1)."""
        node = _make_if_node("Empty IF", [])
        result = DryRunValidator.run(_minimal_workflow([node]))
        self.assertFalse(result.passed)
        self.assertIn(("Empty IF", 0), result.dead_branches)

    def test_impossible_condition_true_branch_dead(self):
        """Condition 'status == NEVER_MATCHES' always False with default data."""
        node = _make_if_node(
            "Impossible IF",
            [_cond("={{ $json.status }}", "__impossible_value__")],
        )
        result = DryRunValidator.run(_minimal_workflow([node]))
        self.assertFalse(result.passed)
        self.assertIn(("Impossible IF", 0), result.dead_branches)

    def test_warning_text_mentions_node_name(self):
        node = _make_if_node("My IF Node", [])
        result = DryRunValidator.run(_minimal_workflow([node]))
        self.assertTrue(any("My IF Node" in w for w in result.warnings))


# ---------------------------------------------------------------------------
# IF node — dead false branch
# ---------------------------------------------------------------------------

class IfDeadFalseBranchTests(unittest.TestCase):

    def test_always_true_condition_false_branch_dead(self):
        """
        With custom mock where all items have status='active',
        the false branch (output 1) never fires.
        """
        node = _make_if_node(
            "Always True IF",
            [_cond("={{ $json.status }}", "active")],
        )
        # All items have status='active' → condition always True → false branch dead
        mock_items = [
            {"status": "active", "id": 1},
            {"status": "active", "id": 2},
        ]
        result = DryRunValidator.run(_minimal_workflow([node]), mock_items=mock_items)
        self.assertFalse(result.passed)
        self.assertIn(("Always True IF", 1), result.dead_branches)


# ---------------------------------------------------------------------------
# IF node — unresolvable expressions
# ---------------------------------------------------------------------------

class IfUnresolvableTests(unittest.TestCase):

    def test_complex_expression_generates_warning(self):
        """$('OtherNode').item.json.field cannot be resolved statically."""
        node = _make_if_node(
            "Complex IF",
            [_cond("={{ $('PrevNode').item.json.status }}", "active")],
        )
        result = DryRunValidator.run(_minimal_workflow([node]))
        # Both branches appear dead (unresolvable → no routing happened)
        self.assertTrue(
            any("Complex IF" in w for w in result.warnings),
            msg=f"Expected warning about Complex IF, got: {result.warnings}",
        )

    def test_field_not_in_mock_data_warns(self):
        """Field 'nonexistent_field' not in any mock item → unresolvable."""
        node = _make_if_node(
            "Missing Field IF",
            [_cond("={{ $json.nonexistent_field }}", "value")],
        )
        # Use minimal mock with no 'nonexistent_field'
        mock_items = [{"id": 1, "name": "test"}]
        result = DryRunValidator.run(_minimal_workflow([node]), mock_items=mock_items)
        # The true branch never fires (field unresolvable → counted as dead)
        self.assertIn(("Missing Field IF", 0), result.dead_branches)


# ---------------------------------------------------------------------------
# Switch node
# ---------------------------------------------------------------------------

class SwitchTests(unittest.TestCase):

    def test_switch_no_rules_warns(self):
        node = _make_switch_node("Empty Switch", [])
        result = DryRunValidator.run(_minimal_workflow([node]))
        self.assertFalse(result.passed)
        self.assertTrue(any("Switch" in w for w in result.warnings))

    def test_switch_one_rule_fires(self):
        """Switch rule that matches 'active' fires with default mock data."""
        rule = {
            "conditions": {
                "conditions": [_cond("={{ $json.status }}", "active")],
                "combinator": "and",
            }
        }
        node = _make_switch_node("Status Switch", [rule])
        result = DryRunValidator.run(_minimal_workflow([node]))
        # Output 0 fires (at least one item has status='active')
        coverage = next(c for c in result.branch_coverage if c.node_name == "Status Switch")
        self.assertIn(0, coverage.fired_outputs)

    def test_switch_impossible_rule_is_dead(self):
        """Rule that never matches → output 0 dead."""
        rule = {
            "conditions": {
                "conditions": [_cond("={{ $json.status }}", "__never__")],
                "combinator": "and",
            }
        }
        node = _make_switch_node("Dead Switch", [rule])
        result = DryRunValidator.run(_minimal_workflow([node]))
        self.assertIn(("Dead Switch", 0), result.dead_branches)


# ---------------------------------------------------------------------------
# DryRunResult properties
# ---------------------------------------------------------------------------

class DryRunResultPropertiesTests(unittest.TestCase):

    def test_passed_true_when_no_dead_branches(self):
        result = DryRunResult()
        self.assertTrue(result.passed)

    def test_dead_branches_aggregates_coverage(self):
        from dry_run_validator import BranchCoverage
        cov = BranchCoverage(node_name="IF1", total_outputs=2, fired_outputs={0})
        result = DryRunResult(branch_coverage=[cov])
        self.assertIn(("IF1", 1), result.dead_branches)
        self.assertFalse(result.passed)


# ---------------------------------------------------------------------------
# split_workflow
# ---------------------------------------------------------------------------

def _make_nodes(count: int) -> list[dict]:
    """Create *count* simple nodes with increasing x positions."""
    return [
        {
            "name": f"Node{i}",
            "type": "n8n-nodes-base.set",
            "parameters": {},
            "position": [i * 200, 0],
        }
        for i in range(count)
    ]


class SplitWorkflowTests(unittest.TestCase):

    def test_small_workflow_not_split(self):
        wf = {"name": "Small", "nodes": _make_nodes(5), "connections": {}}
        result = split_workflow(wf, chunk_size=7)
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], wf)  # same object — no copy

    def test_exactly_chunk_size_not_split(self):
        wf = {"name": "Exact", "nodes": _make_nodes(7), "connections": {}}
        result = split_workflow(wf, chunk_size=7)
        self.assertEqual(len(result), 1)

    def test_large_workflow_produces_multiple_parts(self):
        wf = {"name": "Big Flow", "nodes": _make_nodes(15), "connections": {}}
        parts = split_workflow(wf, chunk_size=7)
        self.assertGreater(len(parts), 1)
        # 15 nodes / chunk 7 → 3 parts (7 + 7 + 1, but bridge nodes are added)
        self.assertGreaterEqual(len(parts), 2)

    def test_internal_connections_preserved(self):
        """Connections between nodes in the same chunk survive the split."""
        nodes = _make_nodes(10)
        connections = {
            "Node0": {"main": [[{"node": "Node1", "type": "main", "index": 0}]]},
            "Node1": {"main": [[{"node": "Node2", "type": "main", "index": 0}]]},
        }
        wf = {"name": "Connected", "nodes": nodes, "connections": connections}
        parts = split_workflow(wf, chunk_size=5)
        # Node0→Node1 should be in part 1 connections
        part1_conns = parts[0]["connections"]
        self.assertIn("Node0", part1_conns)

    def test_execute_workflow_node_added_between_chunks(self):
        wf = {"name": "Flow", "nodes": _make_nodes(14), "connections": {}}
        parts = split_workflow(wf, chunk_size=7)
        # All parts except last should have an Execute Workflow bridge node
        for part in parts[:-1]:
            node_types = [n["type"] for n in part["nodes"]]
            self.assertIn("n8n-nodes-base.executeWorkflow", node_types)

    def test_last_chunk_has_no_execute_workflow_node(self):
        wf = {"name": "Flow", "nodes": _make_nodes(14), "connections": {}}
        parts = split_workflow(wf, chunk_size=7)
        last_types = [n["type"] for n in parts[-1]["nodes"]]
        self.assertNotIn("n8n-nodes-base.executeWorkflow", last_types)

    def test_sub_workflow_names_contain_part_number(self):
        wf = {"name": "My Flow", "nodes": _make_nodes(14), "connections": {}}
        parts = split_workflow(wf, chunk_size=7)
        for idx, part in enumerate(parts):
            self.assertIn(f"Part {idx + 1}", part["name"])
            self.assertIn("My Flow", part["name"])

    def test_invalid_chunk_size_raises(self):
        wf = {"name": "X", "nodes": _make_nodes(5), "connections": {}}
        with self.assertRaises(ValueError):
            split_workflow(wf, chunk_size=0)


# ---------------------------------------------------------------------------
# N8nAgent.build_workflows — auto split
# ---------------------------------------------------------------------------

class BuildWorkflowsTests(unittest.TestCase):

    def _make_agent_with_workflow(self, node_count: int) -> "N8nAgent":
        """Return an N8nAgent whose LLM returns a workflow with *node_count* nodes."""
        generated_wf = {
            "name": "Generated",
            "nodes": _make_nodes(node_count),
            "connections": {},
        }
        llm = MagicMock()
        llm.complete.return_value = f"```json\n{__import__('json').dumps(generated_wf)}\n```"

        tm = MagicMock()
        tm.get_template.return_value = copy.deepcopy(generated_wf)

        agent = N8nAgent(llm, tm)
        return agent

    def test_small_workflow_returns_single_element_list(self):
        agent = self._make_agent_with_workflow(5)
        parts = agent.build_workflows("intent", "template")
        self.assertEqual(len(parts), 1)

    def test_large_workflow_returns_multiple_parts(self):
        agent = self._make_agent_with_workflow(MAX_NODES_PER_WORKFLOW + 5)
        parts = agent.build_workflows("intent", "template")
        self.assertGreater(len(parts), 1)

    def test_build_workflow_singular_still_works(self):
        """build_workflow (singular) must not be broken."""
        agent = self._make_agent_with_workflow(5)
        wf = agent.build_workflow("intent", "template")
        self.assertIsInstance(wf, dict)
        self.assertIn("nodes", wf)


import copy  # needed for BuildWorkflowsTests helper


if __name__ == "__main__":
    unittest.main()
