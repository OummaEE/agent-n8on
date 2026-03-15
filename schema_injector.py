"""
schema_injector.py

Utilities for injecting real API response schemas into LLM prompts, so the
agent can reference actual field paths instead of guessing them.

Functions
---------
fetch_api_schema(url, method, headers)
    Makes a test HTTP request and returns a list of field paths found in the
    response body.

extract_field_paths(json_response, prefix, max_depth)
    Recursively walks a parsed JSON value and returns every dot-path / index-
    path it finds (e.g. "email", "profile.email", "items[0].id").

inject_schema_to_prompt(schema)
    Formats a list of field paths into a human-readable block suitable for
    insertion into an LLM prompt.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

MAX_FIELDS = 60          # cap to keep prompts from growing unboundedly
_DEFAULT_TIMEOUT = 10    # seconds


def fetch_api_schema(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> list[str]:
    """
    Perform a lightweight HTTP request to *url* and return all field paths
    found in the JSON response body.

    Parameters
    ----------
    url:      Full URL to request.
    method:   HTTP method ("GET", "POST", …).
    headers:  Optional request headers dict.
    body:     Optional request body bytes (for POST/PUT).
    timeout:  Socket timeout in seconds.

    Returns
    -------
    List of field path strings (may be empty on error or non-JSON response).

    Raises
    ------
    urllib.error.URLError  if the network request fails.
    ValueError             if the response is not valid JSON.
    """
    req = urllib.request.Request(url, data=body, method=method.upper())

    if headers:
        for key, value in headers.items():
            req.add_header(key, value)

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Response is not valid JSON: {exc}") from exc

    return extract_field_paths(parsed)


def extract_field_paths(
    json_response: Any,
    prefix: str = "",
    max_depth: int = 5,
) -> list[str]:
    """
    Recursively extract every accessible field path from a parsed JSON value.

    Examples
    --------
    >>> extract_field_paths({"a": {"b": 1}, "c": [{"d": 2}]})
    ['a', 'a.b', 'c', 'c[0]', 'c[0].d']

    Parameters
    ----------
    json_response: Parsed JSON value (dict, list, scalar).
    prefix:        Dot-path prefix accumulated during recursion.
    max_depth:     Maximum recursion depth (prevents huge output on deep trees).

    Returns
    -------
    Sorted, deduplicated list of path strings (at most MAX_FIELDS entries).
    """
    paths: list[str] = []
    _collect_paths(json_response, prefix, max_depth, 0, paths)
    # Deduplicate preserving order, then cap
    seen: set[str] = set()
    result: list[str] = []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            result.append(p)
        if len(result) >= MAX_FIELDS:
            break
    return result


def inject_schema_to_prompt(schema: list[str]) -> str:
    """
    Format a list of field paths into a prompt-ready text block.

    Parameters
    ----------
    schema: List of field path strings as returned by ``extract_field_paths``.

    Returns
    -------
    A formatted string to append to the LLM prompt.
    """
    if not schema:
        return (
            "Схема API недоступна. Используй только очевидные поля "
            "(id, name, email, status, …) и избегай глубоких путей.\n"
        )

    lines = ["Доступные поля в ответе API (используй точные пути):"]
    for path in schema[:MAX_FIELDS]:
        lines.append(f"  - {path}")

    lines.append(
        "\nПример доступа в n8n: {{ $('NodeName').item.json.<path> }}\n"
        "Используй ТОЛЬКО поля из списка выше."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_paths(
    value: Any,
    prefix: str,
    max_depth: int,
    depth: int,
    out: list[str],
) -> None:
    """Recursive worker for extract_field_paths."""
    if depth > max_depth:
        return

    if isinstance(value, dict):
        if prefix:
            out.append(prefix)
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            _collect_paths(child, child_prefix, max_depth, depth + 1, out)

    elif isinstance(value, list):
        if prefix:
            out.append(prefix)
        if value:
            # Only inspect the first element to infer schema
            item_prefix = f"{prefix}[0]" if prefix else "[0]"
            _collect_paths(value[0], item_prefix, max_depth, depth + 1, out)

    else:
        # Scalar leaf — add the prefix (field name) if non-empty
        if prefix:
            out.append(prefix)
