"""
test_validator.py

Unit tests for N8nValidator (n8n_validator.py).
"""

import pytest
from n8n_validator import N8nValidator, N8nValidationException


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_workflow():
    return {
        "nodes": [
            {"name": "Webhook", "parameters": {}},
            {
                "name": "Set Data",
                "parameters": {
                    "value": "={{ $('Webhook').item.json.query }}"
                },
            },
        ],
        "connections": {
            "Webhook": {
                "main": [
                    [{"node": "Set Data", "type": "main", "index": 0}]
                ]
            }
        },
    }


# ---------------------------------------------------------------------------
# Tests from instructions
# ---------------------------------------------------------------------------


def test_valid_workflow(valid_workflow):
    assert N8nValidator.validate_workflow(valid_workflow) is True


def test_invalid_connection_target(valid_workflow):
    valid_workflow["connections"]["Webhook"]["main"][0][0]["node"] = "GhostNode"
    with pytest.raises(
        N8nValidationException, match="Connection target 'GhostNode' не существует"
    ):
        N8nValidator.validate_workflow(valid_workflow)


def test_invalid_data_reference(valid_workflow):
    valid_workflow["nodes"][1]["parameters"]["value"] = (
        "={{ $('OldWebhook').item.json.query }}"
    )
    with pytest.raises(
        N8nValidationException,
        match="ссылается на несуществующий узел 'OldWebhook'",
    ):
        N8nValidator.validate_workflow(valid_workflow)


def test_missing_schema_keys():
    bad_json = {"nodes": []}
    with pytest.raises(
        N8nValidationException,
        match="должен содержать ключи 'nodes' и 'connections'",
    ):
        N8nValidator.validate_workflow(bad_json)


# ---------------------------------------------------------------------------
# Additional tests for connection structure (list-of-lists fix)
# ---------------------------------------------------------------------------


def test_multiple_outputs_list_of_lists():
    """IF node has two output ports (true / false) — both should be validated."""
    workflow = {
        "nodes": [
            {"name": "IF", "parameters": {}},
            {"name": "True Branch", "parameters": {}},
            {"name": "False Branch", "parameters": {}},
        ],
        "connections": {
            "IF": {
                "main": [
                    [{"node": "True Branch", "type": "main", "index": 0}],
                    [{"node": "False Branch", "type": "main", "index": 0}],
                ]
            }
        },
    }
    assert N8nValidator.validate_workflow(workflow) is True


def test_invalid_second_output_target():
    """Bad target in output index 1 should be caught."""
    workflow = {
        "nodes": [
            {"name": "IF", "parameters": {}},
            {"name": "True Branch", "parameters": {}},
        ],
        "connections": {
            "IF": {
                "main": [
                    [{"node": "True Branch", "type": "main", "index": 0}],
                    [{"node": "NonExistent", "type": "main", "index": 0}],
                ]
            }
        },
    }
    with pytest.raises(
        N8nValidationException, match="Connection target 'NonExistent' не существует"
    ):
        N8nValidator.validate_workflow(workflow)


def test_invalid_connection_source():
    """Source node that does not exist in nodes list should be caught."""
    workflow = {
        "nodes": [{"name": "A", "parameters": {}}, {"name": "B", "parameters": {}}],
        "connections": {
            "GhostSource": {
                "main": [[{"node": "B", "type": "main", "index": 0}]]
            }
        },
    }
    with pytest.raises(
        N8nValidationException, match="Connection source 'GhostSource' не существует"
    ):
        N8nValidator.validate_workflow(workflow)


# ---------------------------------------------------------------------------
# typeVersion validation tests
# ---------------------------------------------------------------------------


def test_valid_type_version_passes():
    """Known node type with valid typeVersion should pass."""
    workflow = {
        "nodes": [
            {
                "name": "My Code",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "parameters": {"jsCode": "return $input.all();"},
            }
        ],
        "connections": {},
    }
    assert N8nValidator.validate_workflow(workflow) is True


def test_invalid_type_version_rejected():
    """Known node type with wrong typeVersion should raise."""
    workflow = {
        "nodes": [
            {
                "name": "My Code",
                "type": "n8n-nodes-base.code",
                "typeVersion": 99,
                "parameters": {"jsCode": "return [];"},
            }
        ],
        "connections": {},
    }
    with pytest.raises(N8nValidationException, match="неподдерживаемый typeVersion=99"):
        N8nValidator.validate_workflow(workflow)


def test_missing_required_param_for_typeversion():
    """httpRequest v4.1 requires 'url' — missing should raise."""
    workflow = {
        "nodes": [
            {
                "name": "Fetch",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.1,
                "parameters": {},          # 'url' missing
            }
        ],
        "connections": {},
    }
    with pytest.raises(
        N8nValidationException, match="отсутствует обязательный параметр 'url'"
    ):
        N8nValidator.validate_workflow(workflow)


def test_unknown_node_type_skips_version_check():
    """Custom / third-party node types are not validated for typeVersion."""
    workflow = {
        "nodes": [
            {
                "name": "Custom",
                "type": "n8n-nodes-custom.myPlugin",
                "typeVersion": 999,
                "parameters": {},
            }
        ],
        "connections": {},
    }
    assert N8nValidator.validate_workflow(workflow) is True


def test_empty_connections_valid():
    """Single node with no connections is valid."""
    workflow = {
        "nodes": [{"name": "Solo", "parameters": {}}],
        "connections": {},
    }
    assert N8nValidator.validate_workflow(workflow) is True
