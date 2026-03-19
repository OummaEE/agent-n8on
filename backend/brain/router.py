"""Router — classifies a user message into one of three paths.

FAST    — single, well-defined action; controller can handle it directly.
SLOW    — complex / multi-step task; needs a plan → execute → verify cycle.
CLARIFY — too ambiguous to act on; must ask the user for more information.
"""

from __future__ import annotations

import re
from typing import Literal

Path = Literal["FAST", "SLOW", "CLARIFY"]

# ---------------------------------------------------------------------------
# Keywords that signal a multi-step / complex request.
# ---------------------------------------------------------------------------
_SLOW_CONNECTORS = [
    # English
    r"\band then\b", r"\bafter that\b", r"\bthen\b", r"\bfollowed by\b",
    r"\bonce .{0,30} done\b", r"\buntil .{0,60} works?\b",
    r"\bautomatically\b", r"\bend[-\s]to[-\s]end\b", r"\bfull pipeline\b",
    r"\bmulti[-\s]step\b", r"\bsequentially\b", r"\bstep by step\b",
    # Russian
    r"\bа затем\b", r"\bпосле чего\b", r"\bзатем\b", r"\bпосле того как\b",
    r"\bпока не заработает\b", r"\bдо тех пор пока\b", r"\bпоэтапно\b",
    r"\bпо шагам\b", r"\bполный цикл\b", r"\bавтоматически\b",
]
_SLOW_PATTERN = re.compile("|".join(_SLOW_CONNECTORS), re.IGNORECASE)

# Words that signal multiple distinct high-level actions in one message.
# NOTE: "test" removed — it often appears as a noun (e.g. "final test", "test message")
# and causes false SLOW classification for single-action requests.
_ACTION_WORDS_EN = {"create", "build", "run", "debug", "fix", "deploy",
                    "scan", "clean", "delete", "move", "send", "analyze", "update"}
_ACTION_WORDS_RU = {"создай", "создать", "запусти", "запустить", "отладь",
                    "исправь", "исправить", "удали", "удалить", "очисти",
                    "сканируй", "проверь", "обнови", "обновить"}

# ---------------------------------------------------------------------------
# Clarify triggers — messages too vague to act on.
# ---------------------------------------------------------------------------
_CLARIFY_TRIGGERS = [
    r"^(fix|исправь|сделай|help|помоги|do it|сделай это)[\s.!?]*$",
    r"^(debug|отладь|запусти|run|start)[\s.!?]*$",
    r"^(what|как|что|зачем|почему)[\s.!?]*$",
]
_CLARIFY_PATTERN = re.compile("|".join(_CLARIFY_TRIGGERS), re.IGNORECASE)


class Router:
    """Classify a user message into FAST / SLOW / CLARIFY."""

    def route(self, message: str, controller_handled: bool) -> Path:
        """
        Args:
            message:            raw user message
            controller_handled: True if controller.handle_request returned handled=True
        """
        route, _ = self.route_with_reason(message, controller_handled)
        return route

    def route_with_reason(self, message: str, controller_handled: bool) -> tuple:
        """Like route(), but returns (path, reason) for logging."""
        msg = message.strip()

        if controller_handled:
            return "FAST", "controller already handled"

        if self._is_clarify(msg):
            return "CLARIFY", f"too vague ({len(msg.split())} words, matches clarify pattern)"

        match = _SLOW_PATTERN.search(msg)
        if match:
            return "SLOW", f"multi-step connector detected: '{match.group()}'"

        verb_count = self._count_action_verbs(msg)
        if verb_count >= 2:
            return "SLOW", f"{verb_count} action verbs found"

        return "FAST", "default (single action, no slow signals)"

    # ------------------------------------------------------------------
    def _is_clarify(self, msg: str) -> bool:
        return bool(_CLARIFY_PATTERN.match(msg)) and len(msg.split()) <= 4

    def _count_action_verbs(self, msg: str) -> int:
        # Strip quoted substrings (workflow names) so e.g. "Test" isn't a verb.
        stripped = re.sub(r'["\'][^"\']{1,120}["\']', " ", msg)
        words = set(re.findall(r"[a-zа-яёА-ЯЁA-Z]{3,}", stripped.lower()))
        en_hits = words & _ACTION_WORDS_EN
        ru_hits = words & _ACTION_WORDS_RU
        return len(en_hits) + len(ru_hits)
