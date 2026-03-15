import re
import json

# Expected typeVersion for each known node type.
# Nodes outside this dict skip typeVersion validation.
_KNOWN_TYPE_VERSIONS: dict[str, list[float]] = {
    "n8n-nodes-base.httpRequest":    [4.0, 4.1, 4.2],
    "n8n-nodes-base.code":           [1, 2],
    "n8n-nodes-base.set":            [1, 2, 3, 3.1, 3.2, 3.3, 3.4],
    "n8n-nodes-base.if":             [1, 2],
    "n8n-nodes-base.switch":         [1, 2, 3],
    "n8n-nodes-base.webhook":        [1, 2],
    "n8n-nodes-base.scheduleTrigger": [1, 1.1, 1.2],
    "n8n-nodes-base.merge":          [1, 2, 3],
    "n8n-nodes-base.manualTrigger":  [1],
}

# Required parameter keys per typeVersion (node_type → {typeVersion → required_keys}).
# Only enforced when typeVersion is in the map.
_REQUIRED_PARAMS: dict[str, dict[float, list[str]]] = {
    "n8n-nodes-base.code": {
        2: ["jsCode"],
    },
    "n8n-nodes-base.httpRequest": {
        4.1: ["url"],
        4.2: ["url"],
    },
}


class N8nValidationException(Exception):
    pass


class N8nValidator:
    @staticmethod
    def validate_workflow(workflow_json: dict) -> bool:
        nodes = workflow_json.get("nodes", [])
        connections = workflow_json.get("connections", {})

        node_names = {node["name"] for node in nodes}

        N8nValidator._validate_schema(workflow_json)
        N8nValidator._validate_type_versions(nodes)
        N8nValidator._validate_connections(connections, node_names)
        N8nValidator._validate_data_references(nodes, node_names)

        return True

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_schema(workflow_json: dict):
        if "nodes" not in workflow_json or "connections" not in workflow_json:
            raise N8nValidationException(
                "Workflow должен содержать ключи 'nodes' и 'connections'."
            )

    # ------------------------------------------------------------------
    # typeVersion
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_type_versions(nodes: list):
        for node in nodes:
            node_type = node.get("type", "")
            if node_type not in _KNOWN_TYPE_VERSIONS:
                continue  # unknown type — skip

            type_version = node.get("typeVersion")
            allowed = _KNOWN_TYPE_VERSIONS[node_type]

            if type_version not in allowed:
                raise N8nValidationException(
                    f"Узел '{node.get('name', '?')}' (type={node_type}) "
                    f"имеет неподдерживаемый typeVersion={type_version}. "
                    f"Допустимые: {allowed}."
                )

            # Check required parameters for this typeVersion
            required_map = _REQUIRED_PARAMS.get(node_type, {})
            required_keys = required_map.get(type_version, [])
            params = node.get("parameters", {})
            for key in required_keys:
                if key not in params:
                    raise N8nValidationException(
                        f"Узел '{node.get('name', '?')}' (type={node_type}, "
                        f"typeVersion={type_version}) отсутствует обязательный "
                        f"параметр '{key}'."
                    )

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_connections(connections: dict, node_names: set):
        """
        connections structure:
          {
            "NodeName": {
              "main": [
                [  // output index 0
                  {"node": "Target", "type": "main", "index": 0},
                  ...
                ],
                [  // output index 1
                  ...
                ]
              ]
            }
          }
        routing["main"] is a LIST of lists (one per output port), NOT a dict.
        """
        for source_node, routing in connections.items():
            if source_node not in node_names:
                raise N8nValidationException(
                    f"Connection source '{source_node}' не существует."
                )

            main_outputs = routing.get("main", [])  # list of lists
            for output_connections in main_outputs:
                if not isinstance(output_connections, list):
                    continue
                for connection in output_connections:
                    target_node = connection.get("node")
                    if target_node not in node_names:
                        raise N8nValidationException(
                            f"Connection target '{target_node}' не существует."
                        )

    # ------------------------------------------------------------------
    # Data references ($('NodeName'))
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_data_references(nodes: list, node_names: set):
        pattern = re.compile(r"\$\('([^']+)'\)")

        for node in nodes:
            params_str = json.dumps(node.get("parameters", {}))
            matches = pattern.findall(params_str)

            for referenced_node in matches:
                if referenced_node not in node_names:
                    raise N8nValidationException(
                        f"Узел '{node['name']}' ссылается на несуществующий "
                        f"узел '{referenced_node}'."
                    )
