#!/usr/bin/env python3
"""
Jane Agent Controller Layer v1.0
================================
Ð¦ÐµÐ½Ñ‚Ñ€Ð°Ð»Ð¸Ð·Ð¾Ð²Ð°Ð½Ð½Ð°Ñ ÑÐ¸ÑÑ‚ÐµÐ¼Ð° ÑƒÐ¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ñ Ð°Ð³ÐµÐ½Ñ‚Ð¾Ð¼ Ð¿Ð¾Ð²ÐµÑ€Ñ… agent_v3.py

ÐÑ€Ñ…Ð¸Ñ‚ÐµÐºÑ‚ÑƒÑ€Ð°:
    User Request
         â†“
    Intent Classifier
         â†“
    State Manager
         â†“
    Policy Engine
         â†“
    Workflow Planner
         â†“
    Tool Executor
         â†“
    Result Validator

Ð ÐµÑˆÐ°ÐµÑ‚ Ð¿Ñ€Ð¾Ð±Ð»ÐµÐ¼Ñ‹:
    âœ“ LLM Ð²Ñ‹Ð´ÑƒÐ¼Ñ‹Ð²Ð°ÐµÑ‚ Ñ„Ð°Ð¹Ð»Ñ‹ â†’ State Manager Ð·Ð½Ð°ÐµÑ‚ Ñ€ÐµÐ°Ð»ÑŒÐ½Ð¾Ðµ ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ
    âœ“ LLM Ð½Ðµ Ð¿Ð¾Ð½Ð¸Ð¼Ð°ÐµÑ‚ follow-up â†’ Intent Classifier Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ñ‘Ñ‚ ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚
    âœ“ LLM Ð»Ð¾Ð¼Ð°ÐµÑ‚ workflow â†’ Workflow Planner ÑÑ‚Ñ€Ð¾Ð¸Ñ‚ Ð´ÐµÑ‚ÐµÑ€Ð¼Ð¸Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ñ‹Ðµ Ñ†ÐµÐ¿Ð¾Ñ‡ÐºÐ¸
    âœ“ LLM Ð¸Ð³Ð½Ð¾Ñ€Ð¸Ñ€ÑƒÐµÑ‚ Ð¾ÑˆÐ¸Ð±ÐºÐ¸ â†’ Result Validator Ð¿Ñ€Ð¾Ð²ÐµÑ€ÑÐµÑ‚ ÐºÐ°Ð¶Ð´Ñ‹Ð¹ ÑˆÐ°Ð³
    âœ“ ÐÐµÑ‚ Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾ÑÑ‚Ð¸ â†’ Policy Engine ÐºÐ¾Ð½Ñ‚Ñ€Ð¾Ð»Ð¸Ñ€ÑƒÐµÑ‚ Ð´Ð¾ÑÑ‚ÑƒÐ¿
"""

import os
import json
import re
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from n8n_recipes import (
    apply_recipe_defaults,
    build_recipe_workflow,
    get_missing_param_questions,
    resolve_recipe,
    select_recipe,
    validate_recipe_params,
)

# Ollama / local LLM settings (used by IntentClassifier for semantic routing).
_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")

# Duplicate cleanup confirmation thresholds (P1)
_DUP_CONFIRM_FILES = int(os.environ.get("DUP_CONFIRM_FILES", "20"))   # files
_DUP_CONFIRM_MB    = float(os.environ.get("DUP_CONFIRM_MB", "500"))   # megabytes


# ============================================================
# SESSION STATE MANAGER
# ============================================================

@dataclass
class SessionState:
    """Ð¡Ð¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ Ñ‚ÐµÐºÑƒÑ‰ÐµÐ¹ ÑÐµÑÑÐ¸Ð¸ Ð´Ð¸Ð°Ð»Ð¾Ð³Ð°"""
    
    # ÐŸÐ¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ ÑÐºÐ°Ð½Ñ‹/Ð¾Ð¿ÐµÑ€Ð°Ñ†Ð¸Ð¸
    last_duplicates_path: Optional[str] = None
    last_duplicates_map: Optional[Dict] = None
    last_scan_results: Optional[Dict] = None
    last_tool_call: Optional[str] = None
    last_tool_result: Any = None
    
    # ÐžÐ¶Ð¸Ð´Ð°ÐµÐ¼Ð¾Ðµ Ð½Ð°Ð¼ÐµÑ€ÐµÐ½Ð¸Ðµ (pending intent)
    pending_intent: Optional[str] = None
    pending_params: Dict = field(default_factory=dict)
    
    # Ð˜ÑÑ‚Ð¾Ñ€Ð¸Ñ Ð¾Ð¿ÐµÑ€Ð°Ñ†Ð¸Ð¹ Ð² Ñ€Ð°Ð¼ÐºÐ°Ñ… Ñ‚ÐµÐºÑƒÑ‰ÐµÐ¹ Ð·Ð°Ð´Ð°Ñ‡Ð¸
    task_history: List[Dict] = field(default_factory=list)
    
    # ÐšÐ¾Ð½Ñ‚ÐµÐºÑÑ‚ Ð´Ð»Ñ follow-up ÐºÐ¾Ð¼Ð°Ð½Ð´
    context: Dict = field(default_factory=dict)
    pending_delete: Optional[Dict[str, Any]] = None

    # n8n debug context - last known execution/workflow for follow-up
    last_n8n_execution_id: Optional[str] = None
    last_n8n_workflow_id: Optional[str] = None

    def __post_init__(self):
        """Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ñ Ð¿Ñ€Ð¸ ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ð¸"""
        if self.context is None:
            self.context = {}
        if self.task_history is None:
            self.task_history = []
    
    def clear_task(self):
        """ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚ Ñ‚ÐµÐºÑƒÑ‰ÐµÐ¹ Ð·Ð°Ð´Ð°Ñ‡Ð¸"""
        self.pending_intent = None
        self.pending_params = {}
        self.task_history = []
    
    def add_step(self, tool: str, args: Dict, result: Any):
        """Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ ÑˆÐ°Ð³ Ð²Ñ‹Ð¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ"""
        self.task_history.append({
            "tool": tool,
            "args": args,
            "result": str(result)[:500],
            "timestamp": datetime.now().isoformat()
        })
        self.last_tool_call = tool
        self.last_tool_result = result


class StateManager:
    """Ð£Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸ÐµÐ¼ Ð´Ð¸Ð°Ð»Ð¾Ð³Ð° Ð¸ Ð´Ð°Ð½Ð½Ñ‹Ð¼Ð¸ Ð°Ð³ÐµÐ½Ñ‚Ð°"""
    PENDING_DELETE_TTL_SECONDS = 300
    
    def __init__(self, memory_dir: str):
        self.memory_dir = memory_dir
        self.session = SessionState()
        self.state_file = os.path.join(memory_dir, "session_state.json")
        self.load()
    
    def save(self):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ Ð½Ð° Ð´Ð¸ÑÐº"""
        try:
            data = {
                "last_duplicates_path": self.session.last_duplicates_path,
                "last_scan_results": self.session.last_scan_results,
                "pending_intent": self.session.pending_intent,
                "pending_params": self.session.pending_params,
                "context": self.session.context,
                "pending_delete": self.session.pending_delete,
                "last_n8n_execution_id": self.session.last_n8n_execution_id,
                "last_n8n_workflow_id": self.session.last_n8n_workflow_id,
            }
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"âš ï¸  Failed to save state: {e}")
    
    def load(self):
        """Ð—Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ Ñ Ð´Ð¸ÑÐºÐ°"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.session.last_duplicates_path = data.get("last_duplicates_path")
                    self.session.last_scan_results = data.get("last_scan_results")
                    self.session.pending_intent = data.get("pending_intent")
                    self.session.pending_params = data.get("pending_params", {})
                    self.session.context = data.get("context", {})
                    self.session.pending_delete = data.get("pending_delete")
                    self.session.last_n8n_execution_id = data.get("last_n8n_execution_id")
                    self.session.last_n8n_workflow_id = data.get("last_n8n_workflow_id")
        except Exception as e:
            print(f"âš ï¸  Failed to load state: {e}")
    
    def update_n8n_context(self, execution_id: str = "", workflow_id: str = "") -> None:
        """Persist last n8n execution/workflow IDs for follow-up debug commands."""
        if execution_id:
            self.session.last_n8n_execution_id = execution_id
        if workflow_id:
            self.session.last_n8n_workflow_id = workflow_id
        self.save()

    def update_duplicates_scan(self, path: str, duplicates_map: Dict):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ñ‹ ÑÐºÐ°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ð¾Ð²"""
        self.session.last_duplicates_path = path
        self.session.last_duplicates_map = duplicates_map
        self.session.pending_intent = "CLEAN_DUPLICATES_AVAILABLE"
        self.session.context["duplicates_count"] = len(duplicates_map)
        self.save()
    
    def get_duplicates_context(self) -> Optional[Dict]:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÐºÐ¾Ð½Ñ‚ÐµÐºÑÑ‚ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÐµÐ³Ð¾ ÑÐºÐ°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ð¾Ð²"""
        if self.session.last_duplicates_path:
            return {
                "path": self.session.last_duplicates_path,
                "duplicates_map": self.session.last_duplicates_map,
                "count": self.session.context.get("duplicates_count", 0)
            }
        return None

    def set_pending_delete(self, full_path: str, folder: str, requested_mode: str):
        self.session.pending_delete = {
            "full_path": full_path,
            "folder": folder,
            "filename": os.path.basename(full_path),
            "requested_mode": requested_mode,
            "timestamp": time.time(),
        }
        self.save()

    def get_pending_delete(self) -> Optional[Dict[str, Any]]:
        pending = self.session.pending_delete
        if not pending:
            return None
        ts = pending.get("timestamp")
        if not isinstance(ts, (int, float)):
            self.clear_pending_delete()
            return None
        if (time.time() - ts) > self.PENDING_DELETE_TTL_SECONDS:
            self.clear_pending_delete()
            return None
        return pending

    def clear_pending_delete(self):
        self.session.pending_delete = None
        self.save()


# ============================================================
# INTENT CLASSIFIER
# ============================================================

class IntentClassifier:
    """Ð Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð²Ð°Ð½Ð¸Ðµ Ð½Ð°Ð¼ÐµÑ€ÐµÐ½Ð¸Ð¹ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ"""
    
    # Ð¡Ð»Ð¾Ð²Ð°Ñ€ÑŒ Ð½Ð°Ð¼ÐµÑ€ÐµÐ½Ð¸Ð¹ (Intent Dictionary)
    INTENTS = {
        # === Ð¤ÐÐ™Ð›Ð« ===
        "CLEAN_DUPLICATES_KEEP_NEWEST": {
            "keywords": {
                "ru": ["Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚", "Ð´ÑƒÐ±Ð»Ð¸", "Ð¾Ð´Ð¸Ð½Ð°ÐºÐ¾Ð²", "ÐºÐ¾Ð¿Ð¸", "Ð¿Ð¾Ð²Ñ‚Ð¾Ñ€"],
                "actions": ["ÑƒÐ´Ð°Ð»", "ÑƒÐ±ÐµÑ€", "Ð¾Ñ‡Ð¸ÑÑ‚", "Ð¿Ð¾Ñ‡Ð¸ÑÑ‚", "clean", "remove", "delete"]
            },
            "requires": ["path"],
            "workflow": "duplicates_cleanup"
        },
        "FIND_DUPLICATES_ONLY": {
            "keywords": {
                "ru": ["Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚", "Ð´ÑƒÐ±Ð»Ð¸", "Ð¾Ð´Ð¸Ð½Ð°ÐºÐ¾Ð²", "ÐºÐ¾Ð¿Ð¸", "Ð¿Ð¾Ð²Ñ‚Ð¾Ñ€", "Ð½Ð°Ð¹Ð´", "Ð¿Ð¾ÐºÐ°Ð¶", "ÑÐºÐ°Ð½Ð¸Ñ€"],
            },
            "requires": ["path"],
            "workflow": "duplicates_scan"
        },
        "DELETE_OLD_DUPLICATES_FOLLOWUP": {
            "keywords": {
                "ru": ["ÑƒÐ´Ð°Ð» ÑÑ‚Ð°Ñ€", "ÑƒÐ±ÐµÑ€ ÑÑ‚Ð°Ñ€", "Ð¿Ð¾Ñ‡Ð¸ÑÑ‚", "ÑƒÐ´Ð°Ð» Ð¸Ñ…", "ÑƒÐ±ÐµÑ€ Ð¸Ñ…", "Ð¾Ñ‡Ð¸ÑÑ‚"],
                "en": ["delete old", "remove old", "clean", "delete them", "remove them"]
            },
            "requires_context": "CLEAN_DUPLICATES_AVAILABLE",
            "workflow": "duplicates_cleanup_followup"
        },
        "ORGANIZE_FOLDER_BY_TYPE": {
            "keywords": {
                "ru": ["Ð¾Ñ€Ð³Ð°Ð½Ð¸Ð·", "Ñ€Ð°Ð·Ð»Ð¾Ð¶Ð¸", "ÑÐ¾Ñ€Ñ‚Ð¸Ñ€", "Ð¿Ð¾ Ñ‚Ð¸Ð¿", "Ð¿Ð¾ Ñ€Ð°ÑÑˆÐ¸Ñ€ÐµÐ½Ð¸"],
                "en": ["organize", "sort by type", "sort by extension"]
            },
            "requires": ["path"],
            "workflow": "organize_files"
        },
        "DISK_USAGE_REPORT": {
            "keywords": {
                "ru": ["Ð´Ð¸ÑÐº", "Ð¼ÐµÑÑ‚Ð¾", "Ð·Ð°Ð½ÑÑ‚Ð¾", "ÑÐºÐ¾Ð»ÑŒÐºÐ¾", "ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸Ðº"],
                "en": ["disk usage", "disk space", "how much space"]
            },
            "requires": ["path"],
            "workflow": "disk_usage"
        },
        
        # === Ð”ÐžÐšÐ£ÐœÐ•ÐÐ¢Ð« ===
        "CREATE_DOCUMENT_FROM_TEMPLATE": {
            "keywords": {
                "ru": ["ÑÐ¾Ð·Ð´", "ÑÐ³ÐµÐ½ÐµÑ€", "Ð´Ð¾ÐºÑƒÐ¼ÐµÐ½Ñ‚", "word", "docx", "Ð¾Ñ‚Ñ‡Ñ‘Ñ‚", "Ð¿Ð¸ÑÑŒÐ¼Ð¾"],
                "en": ["create document", "generate doc", "word doc", "report"]
            },
            "requires": ["template_type"],
            "workflow": "create_document"
        },
        
        # === EMAIL ===
        "SEND_EMAIL_SIMPLE": {
            "keywords": {
                "ru": ["Ð¾Ñ‚Ð¿Ñ€Ð°Ð² Ð¿Ð¸ÑÑŒÐ¼", "email", "mail", "Ð½Ð°Ð¿Ð¸Ñˆ Ð¿Ð¸ÑÑŒÐ¼"],
                "en": ["send email", "send mail", "email to"]
            },
            "requires": ["recipient", "subject"],
            "workflow": "send_email"
        },
        
        # === BROWSING ===
        "BROWSE_WITH_LOGIN": {
            "keywords": {
                "ru": ["Ð¾Ñ‚ÐºÑ€Ð¾Ð¹", "Ð·Ð°Ð¹Ð´Ð¸", "Ð·Ð°Ð»Ð¾Ð³Ð¸Ð½", "browse", "gmail", "Ð¾Ñ‚ÐºÑ€ ÑÐ°Ð¹Ñ‚"],
                "en": ["browse", "open", "login to", "go to"]
            },
            "requires": ["url"],
            "workflow": "browse_authenticated"
        },
    }
    
    def __init__(self, state_manager: StateManager):
        self.state = state_manager
    
    def classify(self, user_message: str) -> Optional[Tuple[str, Dict]]:
        """
        ÐšÐ»Ð°ÑÑÐ¸Ñ„Ð¸Ñ†Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ Ð½Ð°Ð¼ÐµÑ€ÐµÐ½Ð¸Ðµ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ.
        
        Returns:
            (intent_name, extracted_params) Ð¸Ð»Ð¸ None
        """
        msg = user_message.lower().strip()
        pending_delete = self.state.get_pending_delete()

        # Pending decision for existing workflow create/update.
        if self.state.session.pending_intent == "N8N_CREATE_WORKFLOW_CONFIRM_UPDATE":
            pending = dict(self.state.session.pending_params or {})
            if self._is_yes_phrase(msg):
                pending["decision"] = "update"
                return ("N8N_CREATE_WORKFLOW_DECISION", pending)
            if self._is_create_another_phrase(msg):
                pending["decision"] = "create_another"
                return ("N8N_CREATE_WORKFLOW_DECISION", pending)
            if self._is_no_phrase(msg):
                pending["decision"] = "cancel"
                return ("N8N_CREATE_WORKFLOW_DECISION", pending)

        # Pending missing params for recipe-driven n8n builder.
        if self.state.session.pending_intent == "N8N_BUILD_WORKFLOW_MISSING_PARAMS":
            pending = dict(self.state.session.pending_params or {})
            extracted = self._extract_n8n_build_params(user_message)
            merged = dict(pending.get("params", {}))
            merged.update(extracted.get("params", {}))
            return (
                "N8N_BUILD_WORKFLOW",
                {
                    "recipe_key": pending.get("recipe_key", extracted.get("recipe_key")),
                    "workflow_name": pending.get("workflow_name") or extracted.get("workflow_name"),
                    "params": merged,
                    "raw_user_message": user_message,
                },
            )

        # Pending activation decision after successful build.
        if self.state.session.pending_intent == "N8N_ACTIVATE_WORKFLOW_CONFIRM":
            pending = dict(self.state.session.pending_params or {})
            if self._is_yes_phrase(msg):
                pending["activate"] = True
                return ("N8N_ACTIVATE_WORKFLOW_DECISION", pending)
            if self._is_no_phrase(msg):
                pending["activate"] = False
                return ("N8N_ACTIVATE_WORKFLOW_DECISION", pending)

        # Pending cleanup confirmation (threshold exceeded).
        if self.state.session.pending_intent == "CLEAN_DUPLICATES_CONFIRM":
            pending = dict(self.state.session.pending_params or {})
            self.state.session.pending_intent = None
            self.state.session.pending_params = {}
            self.state.save()
            if self._is_yes_phrase(msg):
                # Resume with confirmed=True so threshold is bypassed
                pending["_confirmed"] = True
                return ("CLEAN_DUPLICATES_KEEP_NEWEST", pending) if pending.get("_origin") == "CLEAN" else ("DELETE_OLD_DUPLICATES_FOLLOWUP", pending)
            return ("CLEAN_DUPLICATES_CANCELLED", {})

        # Pending purge-trash confirmation.
        if self.state.session.pending_intent == "PURGE_TRASH_CONFIRM":
            pending = dict(self.state.session.pending_params or {})
            self.state.session.pending_intent = None
            self.state.session.pending_params = {}
            self.state.save()
            if self._is_yes_phrase(msg):
                pending["confirm"] = True
                return ("PURGE_TRASH", pending)
            # Any non-yes reply cancels purge
            return ("PURGE_TRASH_CANCELLED", {})

        # Pending missing required params for template workflow creation.
        if self.state.session.pending_intent == "N8N_TEMPLATE_AWAIT_PARAMS":
            pending = dict(self.state.session.pending_params or {})
            missing_key = pending.pop("_missing_param", "FEED_URL")
            low_msg = user_message.lower()
            if missing_key == "FEED_URL":
                m_url = re.search(r'https?://\S+', user_message)
                if m_url:
                    pending[missing_key] = m_url.group(0).rstrip(".,;)")
                else:
                    stripped = user_message.strip()
                    if stripped and len(stripped) < 300:
                        pending[missing_key] = stripped
            elif missing_key == "PLATFORM":
                # Normalize platform name from user answer.
                if any(k in low_msg for k in ["telegram", "телеграм", "тг", " тг "]):
                    pending[missing_key] = "telegram"
                elif any(k in low_msg for k in ["instagram", "инстаграм"]):
                    pending[missing_key] = "instagram"
                elif any(k in low_msg for k in ["twitter", "твиттер", "x.com"]):
                    pending[missing_key] = "twitter"
                elif any(k in low_msg for k in ["reddit", "реддит"]):
                    pending[missing_key] = "reddit"
                else:
                    word = user_message.strip().split()[0].lower() if user_message.strip() else ""
                    if word and len(word) < 50:
                        pending[missing_key] = word
            elif missing_key == "TARGET":
                # Collect ALL @handles / #hashtags (comma-separated input supported).
                m_handles = re.findall(r'[@#][\w]+', user_message)
                if m_handles:
                    pending[missing_key] = ", ".join(m_handles)
                else:
                    stripped = user_message.strip().rstrip(".,;)")
                    if stripped and len(stripped) < 200:
                        pending[missing_key] = stripped
            else:
                # Generic param: use whole message.
                stripped = user_message.strip()
                if stripped and len(stripped) < 300:
                    pending[missing_key] = stripped
            self.state.session.pending_intent = None
            self.state.session.pending_params = {}
            self.state.save()
            return ("N8N_CREATE_FROM_TEMPLATE", pending)

        # === FOLLOW-UP INTENTS (Ð²Ñ‹ÑÐ¾ÐºÐ¸Ð¹ Ð¿Ñ€Ð¸Ð¾Ñ€Ð¸Ñ‚ÐµÑ‚) ===
        if pending_delete and self._is_trash_followup_phrase(msg):
            return ("DELETE_WITH_PENDING_CONTEXT_TRASH", {
                "path": pending_delete["full_path"],
                "folder": pending_delete["folder"],
                "pending_context_used": True,
            })

        # Проверяем контекст диалога
        if self.state.session.pending_intent == "CLEAN_DUPLICATES_AVAILABLE":
            # Пользователь сказал "удали старые" после find_duplicates
            if self._matches_keywords(msg, ["удал", "убер", "очист", "clean", "remove", "delete"]):
                # Особый случай: если есть уточнение "старые/новые/oldest/newest"
                # "удали старые"/"delete old" → keep newest (default)
                # "удали новые"/"delete new" → keep oldest (rare)
                keep = "newest"
                if any(w in msg for w in ["нов", "new"]) and not any(w in msg for w in ["стар", "old"]):
                    keep = "oldest"
                
                return ("DELETE_OLD_DUPLICATES_FOLLOWUP", {
                    "path": self.state.session.last_duplicates_path,
                    "keep": keep
                })

        # N8N create workflow intent (RU/EN).
        if self._is_n8n_build_request(msg):
            parsed = self._extract_n8n_build_params(user_message)
            return ("N8N_BUILD_WORKFLOW", parsed)

        # N8N fix workflow intent (alias to debug loop).
        if self._is_n8n_fix_request(msg):
            workflow_name = self._extract_workflow_name(user_message)
            execution_id = self._extract_execution_id_from_message(user_message)
            if not workflow_name and not execution_id:
                execution_id = self.state.session.last_n8n_execution_id or ""
            if workflow_name or execution_id:
                return ("N8N_FIX_WORKFLOW", {
                    "workflow_name": workflow_name,
                    "execution_id": execution_id,
                    "max_iterations": self._extract_max_iterations(msg),
                    "dry_run": self._is_dry_run(msg),
                    "confirm_sensitive_patch": self._has_confirmation_token(msg),
                })

        # N8N list workflows intent — show all workflows in n8n instance.
        if self._is_n8n_list_workflows_request(msg):
            return ("N8N_LIST_WORKFLOWS", {})

        # N8N activate/deactivate workflow intent.
        if self._is_n8n_activate_request(msg):
            workflow_name = self._extract_workflow_name(user_message)
            deactivate = any(k in msg for k in ["деактивир", "выключ", "остановить", "deactivate", "disable", "stop"])
            return ("N8N_ACTIVATE_WORKFLOW", {
                "workflow_name": workflow_name,
                "active": not deactivate,
            })

        # N8N list templates intent — must check BEFORE LLM template classifier to avoid "GOOD" fallback.
        if self._is_n8n_list_templates_request(msg):
            return ("N8N_LIST_TEMPLATES", {})

        # Template-based multi-node workflow creation — LLM classifier with regex fallback.
        llm_tpl = self._llm_classify_template(user_message)
        if llm_tpl.get("is_template"):
            parsed = self._extract_template_params(user_message)
            parsed["template_id"] = (
                llm_tpl.get("template_id") or parsed.get("template_id", "content_factory")
            )
            return ("N8N_CREATE_FROM_TEMPLATE", parsed)

        # Legacy generic n8n create workflow intent (kept for compatibility).
        if self._is_n8n_create_request(msg):
            parsed = self._extract_n8n_create_params(user_message)
            return ("N8N_CREATE_WORKFLOW", parsed)

        # N8N debug and repair loop intent (RU/EN).
        if self._is_n8n_debug_request(msg):
            workflow_name = self._extract_workflow_name(user_message)
            execution_id = self._extract_execution_id_from_message(user_message)
            # Fall back to session context when no explicit target given.
            if not workflow_name and not execution_id:
                execution_id = self.state.session.last_n8n_execution_id or ""
                workflow_name = ""
            if workflow_name or execution_id:
                return ("N8N_DEBUG_WORKFLOW", {
                    "workflow_name": workflow_name,
                    "execution_id": execution_id,
                    "max_iterations": self._extract_max_iterations(msg),
                    "dry_run": self._is_dry_run(msg),
                    "confirm_sensitive_patch": self._has_confirmation_token(msg),
                })
        
        # === PRIMARY INTENTS ===
        # Проверяем основные намерения
        
        # 1. CLEAN_DUPLICATES_KEEP_NEWEST (найти И удалить)
        has_dup_keywords = self._matches_keywords(msg, 
            ["дублика", "дубли", "одинаков", "копи", "повтор", "duplicate"])
        has_action_keywords = self._matches_keywords(msg,
            ["удал", "убер", "очист", "почист", "clean", "remove", "delete"])
        
        if has_dup_keywords and has_action_keywords:
            path = self._extract_path(user_message)
            if path:
                return ("CLEAN_DUPLICATES_KEEP_NEWEST", {"path": path})
        
        # 2. FIND_DUPLICATES_ONLY (только найти, без удаления)
        if has_dup_keywords and not has_action_keywords:
            if self._matches_keywords(msg, ["найд", "покаж", "scan", "find", "show", "сканир"]):
                path = self._extract_path(user_message)
                if path:
                    return ("FIND_DUPLICATES_ONLY", {"path": path})
        
        # 3. ORGANIZE_FOLDER_BY_TYPE
        if self._matches_keywords(msg, ["органи", "разложи", "сортир", "по тип", "organize", "sort"]):
            path = self._extract_path(user_message)
            if path:
                return ("ORGANIZE_FOLDER_BY_TYPE", {"path": path})
        
        # 4. DISK_USAGE_REPORT
        if self._matches_keywords(msg, ["диск", "место", "занято", "disk usage", "space"]):
            path = self._extract_path(user_message) or "C:/"
            return ("DISK_USAGE_REPORT", {"path": path})
        
        # 5. BROWSE_WITH_LOGIN
        if self._matches_keywords(msg, ["открой", "зайди", "browse", "login", "откр"]):
            url = self._extract_url(user_message)
            if url:
                return ("BROWSE_WITH_LOGIN", {"url": url})

        # 6. TRASH OPERATIONS (restore / list / purge)
        has_trash_word = any(w in msg for w in ["корзин", "trash", "_trash"])

        if has_trash_word and any(w in msg for w in ["восстанов", "верни", "restore", "вернуть"]):
            path = self._extract_path(user_message)
            if path:
                return ("RESTORE_FROM_TRASH", {"path": path})

        if has_trash_word and any(w in msg for w in ["покаж", "список", "list", "что в", "show"]):
            drive = None
            m = re.search(r'\b([A-Za-z]):\b', user_message)
            if m:
                drive = m.group(1).upper() + ":"
            return ("LIST_TRASH", {"drive": drive})

        if has_trash_word and any(w in msg for w in ["очисти", "purge", "очист", "удали всё", "удали все"]):
            drive = None
            m = re.search(r'\b([A-Za-z]):\b', user_message)
            if m:
                drive = m.group(1).upper() + ":"
            return ("PURGE_TRASH", {"drive": drive, "confirm": False})

        # 7. DELETE FILE/FOLDER
        delete_keywords = [
            "удали", "удалить", "delete", "remove", "стереть",
        ]
        if self._matches_keywords(msg, delete_keywords):
            path = self._extract_path(user_message)
            if path:
                requested_mode = "permanent" if self._is_permanent_delete_phrase(msg) else "trash"
                return ("DELETE_FILE_REQUEST", {
                    "path": path,
                    "folder": os.path.dirname(path),
                    "requested_mode": requested_mode,
                })

        return None

    def _is_n8n_create_request(self, msg: str) -> bool:
        has_n8n = "n8n" in msg
        has_workflow = "workflow" in msg or "воркфлоу" in msg
        has_create = any(k in msg for k in ["создай", "создать", "create", "make", "new workflow", "новый workflow"])
        return has_n8n and has_workflow and has_create

    def _is_n8n_build_request(self, msg: str) -> bool:
        if "n8n" not in msg:
            return False
        build_markers = [
            "automation",
            "автоматиза",
            "контент-завод",
            "контент завод",
            "content factory",
            "bygg",
            "workflow:",
            "workflow в n8n:",
            "workflow i n8n:",
        ]
        if any(m in msg for m in build_markers):
            return True
        # Explicit recipe keyword match still counts as build intent.
        return select_recipe(msg) is not None

    def _is_n8n_fix_request(self, msg: str) -> bool:
        has_workflow = "workflow" in msg or "воркфлоу" in msg
        fix_markers = [
            "почини",
            "исправ",
            "fix my workflow",
            "fix workflow",
            "workflow errors",
            "ошибк",
            "не работает",
        ]
        return has_workflow and any(m in msg for m in fix_markers)

    def _extract_n8n_build_params(self, original_msg: str) -> Dict[str, Any]:
        msg = original_msg.strip()
        low = msg.lower()
        recipe_key = select_recipe(low)
        workflow_name = self._extract_workflow_name(msg) or ""
        quoted = re.search(r'"([^"]{2,120})"|\'([^\']{2,120})\'', msg)
        if quoted and ("workflow" in low or "воркфлоу" in low):
            workflow_name = (quoted.group(1) or quoted.group(2)).strip()

        trigger_type = "manual"
        if any(k in low for k in ["schedule", "cron", "по расписанию", "каждый", "dag", "daily", "weekly"]):
            trigger_type = "schedule"
        if any(k in low for k in ["webhook", "вебхук"]):
            trigger_type = "webhook"

        cadence = "day"
        if any(k in low for k in ["week", "weekly", "еженед", "varje vecka"]):
            cadence = "week"

        params: Dict[str, Any] = {
            "trigger_type": trigger_type,
            "cadence": cadence,
        }
        if "swedish" in low or "швед" in low or "svenska" in low:
            params["language"] = "sv"
        elif "russian" in low or "русск" in low:
            params["language"] = "ru"
        elif "english" in low or "англ" in low:
            params["language"] = "en"

        url = self._extract_url(msg)
        if url:
            params.setdefault("source_url", url)
            params.setdefault("post_url", url)

        patterns = {
            "sheet_id": [
                r"(?:google\s*sheet|sheet)\s*(?:id)?\s*[:=]?\s*([A-Za-z0-9_\-]{8,})",
            ],
            "sheet_range": [r"\b([A-Z]{1,3}:[A-Z]{1,3})\b"],
            "notion_db_id": [r"(?:notion(?:\s*db|\s*database)?\s*(?:id)?)\s*[:=]?\s*([A-Za-z0-9_\-]{8,})"],
            "telegram_chat_id": [r"(?:telegram\s*(?:chat)?\s*id)\s*[:=]?\s*([A-Za-z0-9_\-]+)"],
            "gmail_credential": [r"(?:gmail\s*cred(?:ential)?(?:\s*name)?)\s*[:=]?\s*([A-Za-z0-9_\- ]{2,80})"],
            "google_sheets_credential": [r"(?:google\s*sheets?\s*cred(?:ential)?(?:\s*name)?)\s*[:=]?\s*([A-Za-z0-9_\- ]{2,80})"],
            "notion_credential": [r"(?:notion\s*cred(?:ential)?(?:\s*name)?)\s*[:=]?\s*([A-Za-z0-9_\- ]{2,80})"],
            "telegram_credential": [r"(?:telegram\s*cred(?:ential)?(?:\s*name)?)\s*[:=]?\s*([A-Za-z0-9_\- ]{2,80})"],
            "google_drive_credential": [r"(?:google\s*drive\s*cred(?:ential)?(?:\s*name)?)\s*[:=]?\s*([A-Za-z0-9_\- ]{2,80})"],
            "crm_sheet_id": [r"(?:crm\s*sheet\s*id)\s*[:=]?\s*([A-Za-z0-9_\-]{8,})"],
            "followup_email_from": [r"(?:follow[\s-]?up\s*email(?:\s*from)?)\s*[:=]?\s*([A-Za-z0-9@\.\-_]+)"],
            "drive_folder_id": [r"(?:drive\s*(?:folder|file)?\s*id)\s*[:=]?\s*([A-Za-z0-9_\-]{8,})"],
            "keyword": [r"(?:keyword|ключев(?:ое|ой)\s+слово)\s*[:=]?\s*[\"']?([^\"'\n,]{2,80})"],
            "reply_endpoint": [r"(?:reply\s*endpoint)\s*[:=]?\s*([^\s,]+)"],
            "target_path": [r"([A-Za-z]:[/\\][^\s,\"'>]+)"],
        }

        for key, regs in patterns.items():
            for pat in regs:
                m = re.search(pat, msg, flags=re.IGNORECASE)
                if m:
                    val = (m.group(1) or "").strip().strip(",.")
                    if val:
                        params[key] = val.replace("\\", "/")
                        break

        if "google sheet" in low and "sheet_id" not in params:
            m = re.search(r"<([^>]+)>", msg)
            if m:
                params["sheet_id"] = m.group(1).strip()
        if "notion" in low and "notion_db_id" not in params:
            m = re.findall(r"<([^>]+)>", msg)
            if len(m) >= 2:
                params["notion_db_id"] = m[1].strip()

        return {
            "recipe_key": recipe_key,
            "workflow_name": workflow_name,
            "params": params,
            "raw_user_message": original_msg,
        }

    def _is_n8n_list_workflows_request(self, msg: str) -> bool:
        """Detect 'show/list all n8n workflows' intent (not templates, not create)."""
        has_n8n = "n8n" in msg
        has_list = any(k in msg for k in [
            "show", "list", "display", "what", "which", "all workflows", "my workflows",
            "покаж", "список", "какие", "мои workflow", "мои wf", "все workflow",
        ])
        has_workflow = any(k in msg for k in ["workflow", "flows", "wf"])
        has_create = any(k in msg for k in [
            "create", "build", "make", "создай", "создать", "сделай", "собери",
        ])
        # Exclude "show templates" requests — handled by N8N_LIST_TEMPLATES
        has_template = any(k in msg for k in ["template", "шаблон"])
        return has_n8n and has_list and has_workflow and not has_create and not has_template

    def _is_n8n_activate_request(self, msg: str) -> bool:
        """Detect standalone activate/deactivate workflow intent."""
        has_n8n = "n8n" in msg or "workflow" in msg
        has_activate = any(k in msg for k in [
            "активируй", "активировать", "включ", "активн",
            "деактивир", "выключ", "остановить",
            "activate", "deactivate", "enable", "disable",
        ])
        # Avoid matching build workflow requests that end with "activate"
        has_create = any(k in msg for k in ["создай", "создать", "сделай", "собери", "build", "create"])
        return has_n8n and has_activate and not has_create

    def _is_n8n_list_templates_request(self, msg: str) -> bool:
        """Detect 'show/list available n8n templates' without a creation intent."""
        has_list = any(k in msg for k in [
            "show", "list", "display", "what", "which", "available", "all templates",
            "покаж", "список", "какие", "доступн",
        ])
        has_template = any(k in msg for k in ["template", "шаблон"])
        has_create = any(k in msg for k in [
            "create", "build", "make", "создай", "создать", "сделай",
        ])
        return has_list and has_template and not has_create

    def _llm_classify_template(self, user_message: str) -> Dict[str, Any]:
        """Ask the local LLM whether the message is a template workflow request.

        Returns a dict: {"is_template": bool, "template_id": str|None}.
        Falls back to regex heuristic when Ollama is unreachable or returns garbage.
        """
        from skills.template_registry import TemplateRegistry
        registry = TemplateRegistry()
        metas = registry.list_all()
        templates_info = "\n".join(
            f'- {m["id"]}: {m.get("description", "")}  keywords: {", ".join(m.get("keywords", [])[:6])}'
            for m in metas
        )
        prompt = (
            "Classify the user request below.\n"
            "Question 1: Does the user want to create a multi-node automation workflow "
            "(content pipeline, RSS processor, autoposting, blog automation, parsing + posting)?\n"
            "Question 2: If yes, which template best matches?\n\n"
            f"Available templates:\n{templates_info}\n\n"
            'Respond ONLY with valid JSON, nothing else:\n'
            '{"is_template": true/false, "template_id": "<id or null>"}\n\n'
            f"User: {user_message}"
        )
        try:
            import requests as _req
            resp = _req.post(
                f"{_OLLAMA_URL}/api/chat",
                json={
                    "model": _OLLAMA_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a JSON intent classifier. "
                                "Respond ONLY with a single JSON object, no markdown, no explanation."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 128},
                },
                timeout=15,
            )
            raw = resp.json()["message"]["content"].strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(raw[start:end])
                # OR with regex: if LLM missed it but regex catches it, trust regex.
                regex_says = self._is_n8n_template_request_regex(user_message.lower())
                if not result.get("is_template") and regex_says:
                    result["is_template"] = True
                    if not result.get("template_id"):
                        result["template_id"] = self._detect_template_id_from_message(user_message.lower())
                return result
        except Exception:
            pass
        # Fallback: regex heuristic.
        regex_says = self._is_n8n_template_request_regex(user_message.lower())
        tid = self._detect_template_id_from_message(user_message.lower()) if regex_says else None
        return {
            "is_template": regex_says,
            "template_id": tid,
        }

    def _detect_template_id_from_message(self, low: str) -> str:
        """Heuristic: pick the best-matching template id from the message."""
        is_facebook = any(k in low for k in [
            "facebook", "фейсбук", " fb ", "fb groups", "fb события",
        ]) and any(k in low for k in [
            "парс", "scrape", "собир", "collect", "группы", "groups", "события", "events",
        ])
        if is_facebook:
            return "facebook_scraper"
        is_social = (
            any(k in low for k in [
                "telegram", "телеграм", "instagram", "инстаграм",
                "twitter", "твиттер", "reddit", "реддит",
                "соцсет", "social media", "social",
            ]) and any(k in low for k in [
                "парс", "собир", "collect", "harvest", "посты", "posts", "канал", "channel",
            ])
        ) or any(k in low for k in ["social parser", "парсер соцсет", "парсинг соцсет"])
        return "social_parser" if is_social else "content_factory"

    def _is_n8n_template_request_regex(self, low: str) -> bool:
        """Regex fallback for template detection (used when LLM unavailable)."""
        has_create = any(k in low for k in [
            "создай", "создать", "create", "build", "make", "собери",
            "хочу", "нужен", "нужно", "сделай", "настрой", "хочу автомат",
        ])
        # content_factory keywords
        has_template_kw = any(k in low for k in [
            "контент-завод", "content factory", "content-factory",
            "фабрик", "factory", "pipeline", "пайплайн",
            "автопостинг", "autoposting", "auto-posting",
            "парсить блог", "парсить новости",
        ])
        has_rss_automation = any(k in low for k in [
            "rss", "фид", "feed", "блог", "blog",
        ]) and has_create
        # social_parser keywords
        has_collect_verb = any(k in low for k in [
            "парс", "собирать", "collect", "harvest", "мониторить", "monitor",
        ])
        has_social_network = any(k in low for k in [
            "telegram", "телеграм", "instagram", "инстаграм",
            "twitter", "твиттер", "reddit", "реддит",
            "соцсет", "social media",
        ])
        has_social_parser_kw = any(k in low for k in [
            "social parser", "парсер соцсетей", "парсинг соцсетей",
            "парсер постов",
        ])
        has_social_automation = (has_collect_verb and has_social_network) or has_social_parser_kw
        # facebook_scraper keywords
        has_facebook = any(k in low for k in [
            "facebook", "фейсбук", "fb groups", "facebook groups", "facebook events",
        ])
        has_facebook_automation = has_facebook and any(k in low for k in [
            "парс", "scrape", "собир", "collect", "группы", "groups", "события",
        ])
        # For social automation, collect verbs alone (without explicit "create") are sufficient.
        has_action = has_create or has_collect_verb
        return (
            (has_create and (has_template_kw or has_rss_automation))
            or (has_action and has_social_automation)
            or (has_action and has_facebook_automation)
        )

    def _is_n8n_template_request(self, msg: str) -> bool:
        """LLM-based template request detection with regex fallback."""
        result = self._llm_classify_template(msg)
        return bool(result.get("is_template", False))

    def _extract_template_params(self, original_msg: str) -> Dict[str, Any]:
        """Extract substitution params for a template-based workflow creation."""
        msg = original_msg.strip()
        low = msg.lower()

        # Feed URL.
        feed_url = ""
        m_url = re.search(r'https?://\S+', msg)
        if m_url:
            feed_url = m_url.group(0).rstrip(".,;)")

        # Workflow name — quoted string or explicit marker first.
        name = ""
        quoted = re.search(r'"([^"]{2,80})"|\'([^\']{2,80})\'', msg)
        if quoted:
            name = (quoted.group(1) or quoted.group(2)).strip()
        if not name:
            m_ru = re.search(
                r'под\s+названием\s+(.+?)(?:\s+с\s+|\s+для\s+|\s+от\s+|\n|$)',
                msg, re.IGNORECASE | re.DOTALL)
            m_en = re.search(
                r'named?\s+(.+?)(?:\s+with\s+|\s+for\s+|\n|$)',
                msg, re.IGNORECASE | re.DOTALL)
            if m_ru:
                name = m_ru.group(1).strip(" .,-\"'")
            elif m_en:
                name = m_en.group(1).strip(" .,-\"'")
        # (name is left empty here; each template branch below auto-generates it)

        # Rewrite prompt.
        rewrite_prompt = "Summarise this article concisely:"
        m_prompt = re.search(
            r'(?:промпт|prompt|rewrite\s+as|перепиши\s+как)\s*[:\-]?\s*["\']?(.{5,200}?)["\']?\s*(?:$|\n)',
            msg, re.IGNORECASE | re.DOTALL)
        if m_prompt:
            rewrite_prompt = m_prompt.group(1).strip()

        # Max debug iterations.
        max_iter = 3
        m_iter = re.search(r'(?:max[_ ]?iter|итерац)\s*[:=]?\s*(\d+)', msg, re.IGNORECASE)
        if m_iter:
            max_iter = max(1, min(int(m_iter.group(1)), 10))

        # Determine template id from keywords (also set by LLM classifier upstream).
        template_id = self._detect_template_id_from_message(low)

        # --- facebook_scraper: extract GROUP_URLS and SCRIPT_DIR ---
        if template_id == "facebook_scraper":
            # Group URLs — any https:// URL or comma-separated list.
            group_urls = ""
            m_url = re.search(r'https?://\S+', msg)
            if m_url:
                group_urls = m_url.group(0).rstrip(".,;)")
            # Multiple URLs: capture full comma-separated list.
            m_multi = re.search(r'(https?://[^\s,]+(?:\s*,\s*https?://[^\s,]+)+)', msg)
            if m_multi:
                group_urls = m_multi.group(1).strip()

            # SCRIPT_DIR — explicit path or leave empty (handler will ask).
            script_dir = ""
            m_dir = re.search(
                r'(?:путь|path|dir|directory|папка|folder)\s*[=:]?\s*["\']?([A-Za-z]:[^\s"\']{3,200}|/[^\s"\']{3,200})["\']?',
                msg, re.IGNORECASE)
            if m_dir:
                script_dir = m_dir.group(1).strip()

            if not name:
                name = "Facebook Group Scraper"

            return {
                "template_id": template_id,
                "WORKFLOW_NAME": name,
                "GROUP_URLS": group_urls,   # Empty → handler will ask.
                "SCRIPT_DIR": script_dir,   # Empty → handler will ask.
                "OUTPUT_FILE": "events.csv",
                "max_iterations": max_iter,
            }

        # --- social_parser: extract PLATFORM and TARGET ---
        if template_id == "social_parser":
            platform = ""
            if any(k in low for k in ["telegram", "телеграм", "тг"]):
                platform = "telegram"
            elif any(k in low for k in ["instagram", "инстаграм"]):
                platform = "instagram"
            elif any(k in low for k in ["twitter", "твиттер"]):
                platform = "twitter"
            elif any(k in low for k in ["reddit", "реддит"]):
                platform = "reddit"

            target = ""
            # Collect ALL @handles / #hashtags — supports comma/space-separated lists.
            m_handles = re.findall(r'[@#][\w]+', msg)
            if m_handles:
                target = ", ".join(m_handles)
            else:
                m_chan = re.search(
                    r'(?:канал|channel|аккаунт|account|хэштег|hashtag)\s+["\']?([\w@#_\-\.]+(?:\s*,\s*[\w@#_\-\.]+)*)["\']?',
                    msg, re.IGNORECASE)
                if m_chan:
                    target = m_chan.group(1)

            # Auto-generate workflow name.
            if not name:
                if target:
                    name = target.lstrip("@#").capitalize() + " Social Parser"
                elif platform:
                    name = platform.capitalize() + " Social Parser"
                else:
                    name = "Social Parser"

            return {
                "template_id": template_id,
                "WORKFLOW_NAME": name,
                "PLATFORM": platform,   # Empty → handler will ask.
                "TARGET": target,       # Empty → handler will ask.
                "OUTPUT": "none",
                "max_iterations": max_iter,
            }

        # --- content_factory (default) ---
        if not name:
            if feed_url:
                from urllib.parse import urlparse
                host = urlparse(feed_url).netloc.lstrip("www.").split(".")[0]
                name = host.capitalize() + " Content Factory" if host else "Content Factory"
            else:
                name = "Content Factory"

        return {
            "template_id": template_id,
            "WORKFLOW_NAME": name,
            "FEED_URL": feed_url,        # Empty string when not provided — handler will ask.
            "REWRITE_PROMPT": rewrite_prompt,
            "OUTPUT_FILE": "none",
            "max_iterations": max_iter,
        }

    def _extract_n8n_create_params(self, original_msg: str) -> Dict[str, Any]:
        msg = original_msg.strip()
        low = msg.lower()

        # Name extraction.
        name = ""
        quoted = re.search(r'"([^"]{2,120})"|\'([^\']{2,120})\'', msg)
        if quoted:
            name = (quoted.group(1) or quoted.group(2)).strip()
        if not name:
            ru_q = re.search(r'под\s+названием\s*["\']([^"\']{2,120})["\']', msg, flags=re.IGNORECASE | re.DOTALL)
            en_q = re.search(r'named\s*["\']([^"\']{2,120})["\']', msg, flags=re.IGNORECASE | re.DOTALL)
            ru = re.search(r'под\s+названием\s+(.+?)(?:\s+с\s+|\s+и\s+|\n|$)', msg, flags=re.IGNORECASE | re.DOTALL)
            en = re.search(r'named\s+(.+?)(?:\s+with\s+|\s+and\s+|\n|$)', msg, flags=re.IGNORECASE | re.DOTALL)
            if ru_q:
                name = ru_q.group(1).strip(" .,-")
            elif en_q:
                name = en_q.group(1).strip(" .,-")
            elif ru:
                name = ru.group(1).strip(" .,-\"'")
            elif en:
                name = en.group(1).strip(" .,-\"'")

        # Trigger type.
        trigger = "manual"
        if any(k in low for k in ["webhook", "вебхук"]):
            trigger = "webhook"
        elif any(k in low for k in ["schedule", "cron", "по расписанию", "расписан"]):
            trigger = "schedule"
        elif any(k in low for k in ["manual", "manual trigger", "ручной"]):
            trigger = "manual"

        node_types: List[str] = []
        if "set" in low:
            node_types.append("set")
        if "http request" in low or "http" in low:
            node_types.append("http_request")
        if "telegram" in low:
            node_types.append("telegram")
        if "google drive" in low or "гугл диск" in low:
            node_types.append("google_drive")
        if "gmail" in low:
            node_types.append("gmail")

        set_message = None
        m1 = re.search(r'(?:set|node set).{0,50}(?:outputs?|выводит|message)\s+["\']?([A-Za-zА-Яа-я0-9 _-]{1,120})["\']?', msg, flags=re.IGNORECASE)
        if m1:
            set_message = m1.group(1).strip()
        elif "hello" in low and "set" in low:
            set_message = "hello"

        # Extract log message from descriptive patterns: "логирует X" / "logs X" etc.
        if not set_message:
            m_log = re.search(
                r'(?:логирует|выводит|logs?|prints?|outputs?)\s+["\']?([^"\']{1,120}?)["\']?\s*$',
                msg, flags=re.IGNORECASE)
            if m_log:
                set_message = m_log.group(1).strip().rstrip(".,!?")

        # Ensure "set" node is included when a log message is present.
        if set_message and "set" not in node_types:
            node_types.append("set")

        # Auto-generate a workflow name from the log message when name is still empty.
        if not name and set_message:
            words = set_message.split()[:4]
            name = " ".join(w.capitalize() for w in words) + " Logger"

        return {
            "workflow_name": name,
            "trigger_type": trigger,
            "node_types": node_types,
            "set_message": set_message,
        }

    def _is_yes_phrase(self, msg: str) -> bool:
        return any(k in msg for k in ["да", "yes", "update it", "обнови", "activate", "активируй"])

    def _is_no_phrase(self, msg: str) -> bool:
        return any(k in msg for k in ["нет", "no", "cancel", "не надо"])

    def _is_create_another_phrase(self, msg: str) -> bool:
        return any(k in msg for k in ["create another", "создай еще", "создай ещё", "another one", "другой"])

    def _is_n8n_debug_request(self, msg: str) -> bool:
        has_n8n = "n8n" in msg
        has_execution = "execution" in msg or "выполнени" in msg
        has_workflow = "workflow" in msg or "воркфлоу" in msg or has_execution
        has_debug = any(k in msg for k in [
            "debug", "fix", "исправ", "проверь", "ошибка", "error", "не работает", "until it runs",
            "пока не заработает", "почему ошибка", "протестируй",
            "почему упало", "почему слетело", "why did it fail", "why failed", "analyze execution",
            "анализ выполнения", "отладь", "отладит",
        ])
        return has_n8n and has_workflow and has_debug

    def _extract_execution_id_from_message(self, msg: str) -> str:
        """Extract n8n execution ID from user message.

        Matches patterns like:
          execution 12345 / execution: exec-007 / execution_id=abc
          exec abc123 / run_id=xyz / выполнение exec-999
        """
        patterns = [
            r'execution[_\s-]?id[\s]*[=:][\s]*(\S+)',
            r'execution[:\s]+([a-zA-Z0-9_\-]{2,})',
            r'(?<![a-zA-Z])exec[\s]+([a-zA-Z0-9_\-]{3,})',
            r'выполнени[еяи][\s]+([a-zA-Z0-9_\-]{2,})',
            r'run[_\s]id[\s]*[=:][\s]*(\S+)',
        ]
        for pat in patterns:
            try:
                m = re.search(pat, msg, flags=re.IGNORECASE)
            except re.error:
                continue
            if m:
                val = m.group(1).strip()
                if len(val) >= 2:
                    return val
        return ""

    def _extract_workflow_name(self, original_msg: str) -> Optional[str]:
        msg = original_msg.strip()

        # Quoted workflow name has top priority.
        quoted = re.search(r'"([^"]{2,120})"|\'([^\']{2,120})\'', msg)
        if quoted:
            return (quoted.group(1) or quoted.group(2)).strip()

        # English: "... workflow My Name ..."
        en = re.search(r'workflow\s+([A-Za-z0-9 _\-/\.]{2,120})', msg, flags=re.IGNORECASE)
        if en:
            tail = en.group(1)
            for stopper in [" in n8n", " why ", " error", " until ", ",", ".", " исправ", " fix", " run "]:
                pos = tail.lower().find(stopper.strip().lower())
                if pos > 0:
                    tail = tail[:pos]
                    break
            return tail.strip(" -")

        # Russian: "... workflow NAME в n8n ..."
        ru = re.search(r'workflow\s+(.+?)(?:\s+в\s+n8n|\s+in\s+n8n|$)', msg, flags=re.IGNORECASE)
        if ru:
            return ru.group(1).strip(" -.,")

        return None

    def _extract_max_iterations(self, msg: str) -> int:
        m = re.search(r'(?:max[_ ]?iterations?|итерац[ий]{1,2})\s*[:=]?\s*(\d+)', msg, flags=re.IGNORECASE)
        if not m:
            return 3
        try:
            return max(1, min(int(m.group(1)), 10))
        except Exception:
            return 3

    def _is_dry_run(self, msg: str) -> bool:
        return any(k in msg for k in ["dry run", "dry-run", "без применения", "только предложи", "preview only"])

    def _has_confirmation_token(self, msg: str) -> bool:
        return any(k in msg for k in ["confirm", "подтверждаю", "подтверждено", "разрешаю patch"])
    
    def _matches_keywords(self, msg: str, keywords: List[str]) -> bool:
        """ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð½Ð°Ð»Ð¸Ñ‡Ð¸Ñ Ñ…Ð¾Ñ‚Ñ Ð±Ñ‹ Ð¾Ð´Ð½Ð¾Ð³Ð¾ ÐºÐ»ÑŽÑ‡ÐµÐ²Ð¾Ð³Ð¾ ÑÐ»Ð¾Ð²Ð°"""
        return any(kw in msg for kw in keywords)
    
    def _extract_path(self, msg: str) -> Optional[str]:
        """Ð˜Ð·Ð²Ð»ÐµÑ‡ÑŒ Ð¿ÑƒÑ‚ÑŒ Ð¸Ð· ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ"""
        # Windows paths: C:/..., D:/..., Downloads, Desktop
        patterns = [
            r'([A-Za-z]:[/\\][^\s,"\'>]+)',
            r'([A-Za-z]:\\[^\s,"\'>]+)',
        ]
        for pat in patterns:
            match = re.search(pat, msg)
            if match:
                return match.group(1).replace('\\', '/')
        
        # ÐšÐ¾Ñ€Ð¾Ñ‚ÐºÐ¸Ðµ Ð°Ð»Ð¸Ð°ÑÑ‹
        msg_lower = msg.lower()
        if "downloads" in msg_lower or "Ð·Ð°Ð³Ñ€ÑƒÐ·Ðº" in msg_lower:
            return os.path.join(os.environ.get('USERPROFILE', '~'), 'Downloads')
        if "desktop" in msg_lower or "Ñ€Ð°Ð±Ð¾Ñ‡Ð¸Ð¹ ÑÑ‚Ð¾Ð»" in msg_lower:
            return os.path.join(os.environ.get('USERPROFILE', '~'), 'Desktop')
        if "documents" in msg_lower or "Ð´Ð¾ÐºÑƒÐ¼ÐµÐ½Ñ‚Ñ‹" in msg_lower:
            return os.path.join(os.environ.get('USERPROFILE', '~'), 'Documents')
        
        return None
    
    def _extract_url(self, msg: str) -> Optional[str]:
        """Ð˜Ð·Ð²Ð»ÐµÑ‡ÑŒ URL Ð¸Ð· ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ"""
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        match = re.search(url_pattern, msg)
        if match:
            return match.group(0)
        
        # ÐŸÐ¾Ð´Ð´ÐµÑ€Ð¶ÐºÐ° Ð½ÐµÐ¿Ð¾Ð»Ð½Ñ‹Ñ… URL (gmail.com â†’ https://gmail.com)
        domain_pattern = r'\b([a-z0-9-]+\.)+[a-z]{2,}\b'
        match = re.search(domain_pattern, msg.lower())
        if match:
            domain = match.group(0)
            if not domain.startswith('http'):
                return f"https://{domain}"
            return domain
        
        return None

    def _is_permanent_delete_phrase(self, msg: str) -> bool:
        permanent_phrases = [
            "навсегда", "permanent", "permanently", "без корзины",
        ]
        return any(p in msg for p in permanent_phrases)

    def _is_trash_followup_phrase(self, msg: str) -> bool:
        phrases = [
            "перемести в корзину",
            "в корзину",
            "не навсегда",
            "удали в корзину",
            "отмени permanent",
            "move to trash",
            "not permanent",
            "trash it",
            "cancel permanent",
        ]
        return any(p in msg for p in phrases)


# ============================================================
# POLICY ENGINE
# ============================================================

class PolicyEngine:
    """Control of safety and access policy"""

    SAFE_OPERATIONS = {
        "find_duplicates",
        "clean_duplicates",
        "organize_folder",
        "disk_usage",
        "list_files",
        "create_file",
        "read_file",
        "browse_as_me",
        "web_search",
        "send_email",
        "create_document",
        # Trash management
        "list_trash",
        "restore_from_trash",
        "purge_trash",
    }

    CONFIRM_REQUIRED = {
        "delete_files",
        "run_powershell",
        "clean_duplicates",  # if mode != dry_run
    }

    FORBIDDEN_PATHS = [
        "C:/Windows/System32",
        "C:/Program Files",
        "C:/ProgramData",
    ]

    def __init__(self):
        self.requested_folder: Optional[str] = None
        self.last_scanned_folder: Optional[str] = None

    def set_requested_folder(self, path: Optional[str]):
        self.requested_folder = os.path.normpath(os.path.abspath(path)) if path else None

    def set_last_scanned_folder(self, path: Optional[str]):
        self.last_scanned_folder = os.path.normpath(os.path.abspath(path)) if path else None

    @staticmethod
    def _is_within_folder(path: str, folder: str) -> bool:
        try:
            norm_path = os.path.normpath(os.path.abspath(path))
            norm_folder = os.path.normpath(os.path.abspath(folder))
            if os.name == "nt":
                norm_path = os.path.normcase(norm_path)
                norm_folder = os.path.normcase(norm_folder)
            return os.path.commonpath([norm_path, norm_folder]) == norm_folder
        except Exception:
            return False

    def check_operation(self, tool_name: str, args: Dict) -> Tuple[bool, Optional[str]]:
        """
        Check if operation is allowed.

        Returns:
            (allowed: bool, reason: Optional[str])
        """
        if tool_name not in self.SAFE_OPERATIONS and tool_name not in self.CONFIRM_REQUIRED:
            return False, f"Операция '{tool_name}' не разрешена политикой безопасности"

        if "path" in args:
            path = args["path"]
            for forbidden in self.FORBIDDEN_PATHS:
                if path.startswith(forbidden):
                    return False, f"Путь '{path}' находится в защищённой области"

        if "paths" in args:  # for delete_files
            for path in args["paths"]:
                for forbidden in self.FORBIDDEN_PATHS:
                    if path.startswith(forbidden):
                        return False, f"Путь '{path}' находится в защищённой области"

        if tool_name == "delete_files":
            missing = []
            for path in args.get("paths", []):
                if not os.path.exists(path):
                    missing.append(path)
            if missing:
                return False, f"Файлы не существуют: {', '.join(missing[:3])}"

        # Any deletion must stay within requested folder or last scanned folder.
        if tool_name in {"delete_files", "clean_duplicates"}:
            allowed_roots = [p for p in [self.requested_folder, self.last_scanned_folder] if p]
            if not allowed_roots:
                return False, "Удаление заблокировано: нет allowed folder (requested_folder/last_scanned_folder)"

            if tool_name == "delete_files":
                delete_paths = args.get("paths", [])
            else:
                target = args.get("path")
                delete_paths = [target] if target else []

            for delete_path in delete_paths:
                if not any(self._is_within_folder(delete_path, root) for root in allowed_roots):
                    return False, f"Удаление заблокировано: '{delete_path}' вне allowed folder"

        return True, None

    def needs_confirmation(self, tool_name: str, args: Dict) -> bool:
        """Requires user confirmation?"""
        if tool_name in self.CONFIRM_REQUIRED:
            if tool_name == "delete_files":
                return bool(args.get("permanent")) and not bool(args.get("confirm"))
            if tool_name == "clean_duplicates":
                return args.get("mode", "trash") != "dry_run"
            return True
        return False

# ============================================================
# WORKFLOW PLANNER
# ============================================================

@dataclass
class WorkflowStep:
    """ÐžÐ´Ð¸Ð½ ÑˆÐ°Ð³ Ð² workflow"""
    tool: str
    args: Dict
    description: str
    validate: Optional[callable] = None


class WorkflowPlanner:
    """ÐŸÐ»Ð°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð¿Ð¾ÑÐ»ÐµÐ´Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒÐ½Ð¾ÑÑ‚Ð¸ Ð´ÐµÐ¹ÑÑ‚Ð²Ð¸Ð¹ (Ð´ÐµÑ‚ÐµÑ€Ð¼Ð¸Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ð¾Ðµ)"""
    
    def __init__(self, state_manager: StateManager):
        self.state = state_manager
    
    def plan(self, intent: str, params: Dict) -> List[WorkflowStep]:
        """
        ÐŸÐ¾ÑÑ‚Ñ€Ð¾Ð¸Ñ‚ÑŒ workflow Ð´Ð»Ñ Ð½Ð°Ð¼ÐµÑ€ÐµÐ½Ð¸Ñ.
        
        Returns:
            List[WorkflowStep] â€” Ð¿Ð¾ÑÐ»ÐµÐ´Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒÐ½Ð¾ÑÑ‚ÑŒ ÑˆÐ°Ð³Ð¾Ð²
        """
        if intent == "CLEAN_DUPLICATES_KEEP_NEWEST":
            return self._plan_duplicates_cleanup(params)
        
        elif intent == "FIND_DUPLICATES_ONLY":
            return self._plan_duplicates_scan(params)
        
        elif intent == "DELETE_OLD_DUPLICATES_FOLLOWUP":
            return self._plan_duplicates_cleanup_followup(params)
        
        elif intent == "ORGANIZE_FOLDER_BY_TYPE":
            return self._plan_organize_files(params)
        
        elif intent == "DISK_USAGE_REPORT":
            return self._plan_disk_usage(params)
        
        elif intent == "BROWSE_WITH_LOGIN":
            return self._plan_browse_authenticated(params)

        elif intent == "DELETE_FILE_REQUEST":
            return self._plan_delete_file_request(params)

        elif intent == "DELETE_WITH_PENDING_CONTEXT_TRASH":
            return self._plan_delete_with_pending_context_trash(params)

        elif intent == "N8N_DEBUG_WORKFLOW":
            return self._plan_n8n_debug_workflow(params)

        elif intent == "RESTORE_FROM_TRASH":
            return [WorkflowStep(
                tool="restore_from_trash",
                args={"path": params["path"]},
                description=f"Restore {params['path']} from _TRASH to original location",
            )]

        elif intent == "LIST_TRASH":
            return [WorkflowStep(
                tool="list_trash",
                args={"drive": params.get("drive")},
                description="List all items in _TRASH",
            )]

        elif intent == "PURGE_TRASH":
            return [WorkflowStep(
                tool="purge_trash",
                args={"drive": params.get("drive"), "confirm": params.get("confirm", False)},
                description="Permanently purge all items from _TRASH",
            )]

        return []
    
    def _plan_duplicates_cleanup(self, params: Dict) -> List[WorkflowStep]:
        """Workflow: Ð½Ð°Ð¹Ñ‚Ð¸ Ð¸ ÑƒÐ´Ð°Ð»Ð¸Ñ‚ÑŒ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹"""
        path = params["path"]
        keep = params.get("keep", "newest")
        
        return [
            WorkflowStep(
                tool="clean_duplicates",
                args={"path": path, "mode": "trash", "keep": keep},
                description=f"Ð¡ÐºÐ°Ð½Ð¸Ñ€ÑƒÑŽ {path}, Ð½Ð°Ñ…Ð¾Ð¶Ñƒ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹, Ð¿ÐµÑ€ÐµÐ¼ÐµÑ‰Ð°ÑŽ ÑÑ‚Ð°Ñ€Ñ‹Ðµ Ð² ÐºÐ¾Ñ€Ð·Ð¸Ð½Ñƒ"
            )
        ]
    
    def _plan_duplicates_scan(self, params: Dict) -> List[WorkflowStep]:
        """Workflow: Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð½Ð°Ð¹Ñ‚Ð¸ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹"""
        path = params["path"]
        
        return [
            WorkflowStep(
                tool="find_duplicates",
                args={"path": path},
                description=f"Ð¡ÐºÐ°Ð½Ð¸Ñ€ÑƒÑŽ {path} Ð¸ Ð¿Ð¾ÐºÐ°Ð·Ñ‹Ð²Ð°ÑŽ Ð½Ð°Ð¹Ð´ÐµÐ½Ð½Ñ‹Ðµ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹"
            )
        ]
    
    def _plan_duplicates_cleanup_followup(self, params: Dict) -> List[WorkflowStep]:
        """Workflow: ÑƒÐ´Ð°Ð»Ð¸Ñ‚ÑŒ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹ (follow-up Ð¿Ð¾ÑÐ»Ðµ find_duplicates)"""
        path = params["path"]
        keep = params.get("keep", "newest")
        
        return [
            WorkflowStep(
                tool="clean_duplicates",
                args={"path": path, "mode": "trash", "keep": keep},
                description=f"Ð£Ð´Ð°Ð»ÑÑŽ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹ Ð¸Ð· Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÐµÐ³Ð¾ ÑÐºÐ°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ ({path})"
            )
        ]
    
    def _plan_organize_files(self, params: Dict) -> List[WorkflowStep]:
        """Workflow: Ð¾Ñ€Ð³Ð°Ð½Ð¸Ð·Ð¾Ð²Ð°Ñ‚ÑŒ Ñ„Ð°Ð¹Ð»Ñ‹ Ð¿Ð¾ Ñ‚Ð¸Ð¿Ð°Ð¼"""
        path = params["path"]
        
        return [
            WorkflowStep(
                tool="organize_folder",
                args={"path": path},
                description=f"ÐžÑ€Ð³Ð°Ð½Ð¸Ð·ÑƒÑŽ Ñ„Ð°Ð¹Ð»Ñ‹ Ð² {path} Ð¿Ð¾ Ñ‚Ð¸Ð¿Ð°Ð¼"
            )
        ]
    
    def _plan_disk_usage(self, params: Dict) -> List[WorkflowStep]:
        """Workflow: Ð¾Ñ‚Ñ‡Ñ‘Ñ‚ Ð¿Ð¾ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ð½Ð¸ÑŽ Ð´Ð¸ÑÐºÐ°"""
        path = params["path"]
        
        return [
            WorkflowStep(
                tool="disk_usage",
                args={"path": path},
                description=f"ÐÐ½Ð°Ð»Ð¸Ð·Ð¸Ñ€ÑƒÑŽ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð´Ð¸ÑÐºÐ° Ð² {path}"
            )
        ]
    
    def _plan_browse_authenticated(self, params: Dict) -> List[WorkflowStep]:
        """Workflow: Ð¾Ñ‚ÐºÑ€Ñ‹Ñ‚ÑŒ ÑÐ°Ð¹Ñ‚ Ñ Ð°Ð²Ñ‚Ð¾Ñ€Ð¸Ð·Ð°Ñ†Ð¸ÐµÐ¹"""
        url = params["url"]
        
        return [
            WorkflowStep(
                tool="browse_as_me",
                args={"url": url},
                description=f"ÐžÑ‚ÐºÑ€Ñ‹Ð²Ð°ÑŽ {url} Ñ Ñ‚Ð²Ð¾Ð¸Ð¼Ð¸ cookies/ÑÐµÑÑÐ¸ÐµÐ¹"
            )
        ]

    def _plan_delete_file_request(self, params: Dict) -> List[WorkflowStep]:
        path = params["path"]
        requested_mode = params.get("requested_mode", "trash")
        permanent = requested_mode == "permanent"
        return [
            WorkflowStep(
                tool="delete_files",
                args={"paths": [path], "permanent": permanent, "confirm": False},
                description=f"Delete request for {path} (mode={requested_mode})"
            )
        ]

    def _plan_delete_with_pending_context_trash(self, params: Dict) -> List[WorkflowStep]:
        path = params["path"]
        return [
            WorkflowStep(
                tool="delete_files",
                args={"paths": [path], "permanent": False, "confirm": False},
                description=f"Follow-up delete to trash for {path}"
            )
        ]

    def _plan_n8n_debug_workflow(self, params: Dict) -> List[WorkflowStep]:
        name = params.get("workflow_name", "")
        return [
            WorkflowStep(
                tool="n8n_debug_workflow",
                args=params,
                description=f"Deterministic n8n debug loop for workflow '{name}'"
            )
        ]


# ============================================================
# RESULT VALIDATOR
# ============================================================

class ResultValidator:
    """Ð’Ð°Ð»Ð¸Ð´Ð°Ñ†Ð¸Ñ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ð¾Ð² Ð²Ñ‹Ð¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ"""
    
    @staticmethod
    def validate_duplicates_scan(result: str) -> Tuple[bool, Optional[str]]:
        """ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚ ÑÐºÐ°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ð¾Ð²"""
        if "Error" in result or "error" in result:
            return False, "Ð¡ÐºÐ°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð·Ð°Ð²ÐµÑ€ÑˆÐ¸Ð»Ð¾ÑÑŒ Ñ Ð¾ÑˆÐ¸Ð±ÐºÐ¾Ð¹"
        
        if "No duplicates found" in result:
            return True, None  # Ð­Ñ‚Ð¾ Ð²Ð°Ð»Ð¸Ð´Ð½Ñ‹Ð¹ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚
        
        if "Found" in result and "groups" in result:
            return True, None
        
        return False, "ÐÐµÐ¾Ð¶Ð¸Ð´Ð°Ð½Ð½Ñ‹Ð¹ Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ð°"
    
    @staticmethod
    def validate_cleanup(result: str) -> Tuple[bool, Optional[str]]:
        """ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚ Ð¾Ñ‡Ð¸ÑÑ‚ÐºÐ¸"""
        if "Error" in result:
            return False, "ÐžÑ‡Ð¸ÑÑ‚ÐºÐ° Ð·Ð°Ð²ÐµÑ€ÑˆÐ¸Ð»Ð°ÑÑŒ Ñ Ð¾ÑˆÐ¸Ð±ÐºÐ¾Ð¹"
        
        if "Cleaned" in result or "moved to _trash" in result:
            return True, None

        if "No duplicates found" in result:
            return True, None  # valid no-op

        return False, "Неожиданный формат результата"
    @staticmethod
    def validate_file_exists(path: str) -> Tuple[bool, Optional[str]]:
        """ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ ÑÑƒÑ‰ÐµÑÑ‚Ð²Ð¾Ð²Ð°Ð½Ð¸Ðµ Ñ„Ð°Ð¹Ð»Ð°"""
        if os.path.exists(path):
            return True, None
        return False, f"Ð¤Ð°Ð¹Ð» Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½: {path}"


# ============================================================
# MAIN CONTROLLER
# ============================================================

class AgentController:
    """Ð“Ð»Ð°Ð²Ð½Ñ‹Ð¹ ÐºÐ¾Ð½Ñ‚Ñ€Ð¾Ð»Ð»ÐµÑ€ Ð°Ð³ÐµÐ½Ñ‚Ð°"""
    
    def __init__(self, memory_dir: str, tools_dict: Dict):
        """
        Args:
            memory_dir: Ð¿ÑƒÑ‚ÑŒ Ðº Ð¿Ð°Ð¿ÐºÐµ memory/
            tools_dict: ÑÐ»Ð¾Ð²Ð°Ñ€ÑŒ Ð¸Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚Ð¾Ð² Ð¸Ð· agent_v3.py (TOOLS)
        """
        self.state = StateManager(memory_dir)
        self.intent_classifier = IntentClassifier(self.state)
        self.policy = PolicyEngine()
        self.planner = WorkflowPlanner(self.state)
        self.validator = ResultValidator()
        self.tools = tools_dict
        self.memory_dir = memory_dir
        self.n8n_backup_dir = os.path.join(memory_dir, "n8n_backups")
        os.makedirs(self.n8n_backup_dir, exist_ok=True)

    def _call_tool_json(self, tool_name: str, args: Dict) -> Dict[str, Any]:
        if tool_name not in self.tools:
            return {"error": f"Tool not available: {tool_name}"}
        result = self.tools[tool_name](args)
        if isinstance(result, dict):
            return result
        if not isinstance(result, str):
            return {"value": result}
        try:
            return json.loads(result)
        except Exception:
            return {"text": result}

    @staticmethod
    def _extract_execution_error(execution: Dict[str, Any]) -> Dict[str, Any]:
        data = execution.get("data", {}) if isinstance(execution, dict) else {}
        result_data = data.get("resultData", {}) if isinstance(data, dict) else {}
        run_data = result_data.get("runData", {}) if isinstance(result_data, dict) else {}
        top_error = result_data.get("error", {}) if isinstance(result_data, dict) else {}

        failing_node_name = ""
        failing_node_id = ""
        error_message = ""
        error_stack = ""

        if isinstance(top_error, dict):
            error_message = top_error.get("message", "") or ""
            error_stack = top_error.get("stack", "") or ""
            failing_node_name = top_error.get("node", {}).get("name", "") if isinstance(top_error.get("node"), dict) else ""

        if not failing_node_name:
            failing_node_name = result_data.get("lastNodeExecuted", "") if isinstance(result_data, dict) else ""

        if isinstance(run_data, dict):
            for node_name, entries in run_data.items():
                if not isinstance(entries, list) or not entries:
                    continue
                last = entries[-1]
                node_error = last.get("error", {}) if isinstance(last, dict) else {}
                if isinstance(node_error, dict) and node_error:
                    if not error_message:
                        error_message = node_error.get("message", "") or str(node_error)
                    if not error_stack:
                        error_stack = node_error.get("stack", "") or ""
                    failing_node_name = failing_node_name or node_name
                    break

        return {
            "node_name": failing_node_name or "",
            "node_id": failing_node_id or "",
            "message": error_message or "",
            "stack": error_stack or "",
        }

    @staticmethod
    def _find_workflow_node(workflow: Dict[str, Any], node_name: str) -> Optional[Dict[str, Any]]:
        for node in workflow.get("nodes", []):
            if node.get("name") == node_name:
                return node
        return None

    def _backup_workflow_json(self, workflow_id: str, workflow_json: Dict[str, Any]) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(self.n8n_backup_dir, f"{workflow_id}_{ts}.json")
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(workflow_json, f, ensure_ascii=False, indent=2)
        return backup_path

    def _has_path_to_terminal(self, workflow: Dict[str, Any]) -> bool:
        nodes = workflow.get("nodes", [])
        if not nodes:
            return False
        node_names = {n.get("name") for n in nodes if n.get("name")}
        outgoing = {name: 0 for name in node_names}
        for src, conn in workflow.get("connections", {}).items():
            if not isinstance(conn, dict):
                continue
            for buckets in conn.values():
                if not isinstance(buckets, list):
                    continue
                for bucket in buckets:
                    if not isinstance(bucket, list):
                        continue
                    for edge in bucket:
                        if isinstance(edge, dict) and edge.get("node") in node_names and src in outgoing:
                            outgoing[src] += 1
        return any(v == 0 for v in outgoing.values())

    def _propose_patch(self, workflow: Dict[str, Any], error_info: Dict[str, Any]) -> Dict[str, Any]:
        patched = json.loads(json.dumps(workflow))
        summary = []
        touches_sensitive = False
        changed = False

        # Ensure node ids are present.
        for idx, node in enumerate(patched.get("nodes", []), start=1):
            if not node.get("id"):
                node["id"] = f"node-{idx}"
                changed = True
                summary.append(f"added missing node id for '{node.get('name', idx)}'")

        msg = (error_info.get("message") or "").lower()
        failing_node_name = error_info.get("node_name") or ""
        failing_node = self._find_workflow_node(patched, failing_node_name) if failing_node_name else None

        if failing_node:
            params = failing_node.setdefault("parameters", {})
            # Fix bad webhook method/path values.
            if "webhook" in str(failing_node.get("type", "")).lower():
                method = str(params.get("httpMethod", "")).upper() if params.get("httpMethod") else ""
                valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
                if ("method" in msg or "httpmethod" in msg or method not in valid_methods) and method and method not in valid_methods:
                    params["httpMethod"] = "GET"
                    changed = True
                    touches_sensitive = True
                    summary.append(f"set webhook httpMethod=GET on '{failing_node_name}'")
                if not params.get("path"):
                    params["path"] = f"autofix-{str(failing_node_name).lower().replace(' ', '-') or 'webhook'}"
                    changed = True
                    touches_sensitive = True
                    summary.append(f"set missing webhook path on '{failing_node_name}'")

            # Fix invalid expression with unbalanced braces.
            for k, v in list(params.items()):
                if isinstance(v, str) and "{{" in v and "}}" not in v:
                    params[k] = v + "}}"
                    changed = True
                    summary.append(f"closed expression braces in '{failing_node_name}.{k}'")

            # Fix basic numeric type mismatch patterns.
            if "must be of type number" in msg or "expected number" in msg:
                for k, v in list(params.items()):
                    if isinstance(v, str) and v.isdigit():
                        params[k] = int(v)
                        changed = True
                        summary.append(f"converted '{failing_node_name}.{k}' to number")

            if "credential" in msg or "credentials" in msg:
                touches_sensitive = True
                summary.append("credentials issue detected (requires user-provided credential values)")

        # Fix broken connections (dangling node links).
        node_names = {n.get("name") for n in patched.get("nodes", []) if n.get("name")}
        connections = patched.get("connections", {})
        if isinstance(connections, dict):
            for src, conn in list(connections.items()):
                if src not in node_names:
                    connections.pop(src, None)
                    changed = True
                    summary.append(f"removed connections for missing source node '{src}'")
                    continue
                if not isinstance(conn, dict):
                    continue
                for channel, buckets in list(conn.items()):
                    if not isinstance(buckets, list):
                        continue
                    new_buckets = []
                    for bucket in buckets:
                        if not isinstance(bucket, list):
                            continue
                        valid_edges = [e for e in bucket if isinstance(e, dict) and e.get("node") in node_names]
                        if valid_edges:
                            new_buckets.append(valid_edges)
                    if new_buckets != buckets:
                        conn[channel] = new_buckets
                        changed = True
                        summary.append(f"removed dangling connection targets from '{src}'")

        # If graph has no terminal path, do not auto-wire; report only.
        if not self._has_path_to_terminal(patched):
            summary.append("connection graph may have no path to a terminal node")

        return {
            "changed": changed,
            "workflow_json": patched,
            "summary": "; ".join(summary) if summary else "no safe automatic patch found",
            "touches_sensitive": touches_sensitive,
        }

    def _build_n8n_workflow_json(
        self,
        name: str,
        trigger_type: str = "manual",
        node_types: Optional[List[str]] = None,
        set_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        node_types = list(node_types or [])
        nodes: List[Dict[str, Any]] = []

        if trigger_type == "webhook":
            trigger_node = {
                "id": "node-trigger",
                "name": "Webhook Trigger",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 1,
                "position": [240, 300],
                "parameters": {"httpMethod": "GET", "path": f"{name.lower().replace(' ', '-')}-hook"},
            }
        elif trigger_type == "schedule":
            trigger_node = {
                "id": "node-trigger",
                "name": "Schedule Trigger",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [240, 300],
                "parameters": {},
            }
        else:
            trigger_node = {
                "id": "node-trigger",
                "name": "Manual Trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [240, 300],
                "parameters": {},
            }
        nodes.append(trigger_node)

        ordered_nodes: List[Dict[str, Any]] = []
        if "set" in node_types or set_message is not None:
            ordered_nodes.append({
                "id": "node-set",
                "name": "Set",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3.4,
                "position": [480, 300],
                "parameters": {
                    "assignments": {
                        "assignments": [
                            {
                                "id": "assign-message",
                                "name": "message",
                                "value": set_message or "hello",
                                "type": "string",
                            }
                        ]
                    }
                },
            })

        if "http_request" in node_types:
            ordered_nodes.append({
                "id": "node-http",
                "name": "HTTP Request",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [720, 300],
                "parameters": {"url": "https://example.com", "method": "GET"},
            })
        if "telegram" in node_types:
            ordered_nodes.append({
                "id": "node-telegram",
                "name": "Telegram",
                "type": "n8n-nodes-base.telegram",
                "typeVersion": 1.2,
                "position": [960, 300],
                "parameters": {},
            })
        if "google_drive" in node_types:
            ordered_nodes.append({
                "id": "node-gdrive",
                "name": "Google Drive",
                "type": "n8n-nodes-base.googleDrive",
                "typeVersion": 3,
                "position": [1200, 300],
                "parameters": {},
            })
        if "gmail" in node_types:
            ordered_nodes.append({
                "id": "node-gmail",
                "name": "Gmail",
                "type": "n8n-nodes-base.gmail",
                "typeVersion": 2.1,
                "position": [1440, 300],
                "parameters": {},
            })

        nodes.extend(ordered_nodes)

        connections: Dict[str, Any] = {}
        prev_name = trigger_node["name"]
        for node in ordered_nodes:
            connections.setdefault(prev_name, {"main": [[]]})
            connections[prev_name]["main"][0].append({"node": node["name"], "type": "main", "index": 0})
            prev_name = node["name"]

        return {
            "name": name,
            "nodes": nodes,
            "connections": connections,
            "settings": {"executionOrder": "v1"},
        }

    def _handle_n8n_create_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = (params.get("workflow_name") or "").strip()
        if not name:
            return {
                "handled": True,
                "response": "Укажи, пожалуйста, имя workflow в n8n.",
                "tool_name": "chat",
                "tool_result": None,
                "steps": [],
                "thinking": "Need one required field: workflow name",
            }

        trigger_type = params.get("trigger_type", "manual")
        node_types = params.get("node_types", []) or []
        set_message = params.get("set_message")
        decision = params.get("decision", "")

        listing = self._call_tool_json("n8n_list_workflows", {"query": name, "raw": True})
        if "error" in listing:
            return {
                "handled": True,
                "response": f"Ошибка n8n: {listing['error']}",
                "tool_name": "n8n_create_workflow",
                "tool_result": listing,
                "steps": [],
                "thinking": "Failed to list workflows",
            }

        existing = [
            w for w in listing.get("data", [])
            if str(w.get("name", "")).strip().lower() == name.lower()
        ]
        target_name = name
        workflow_id = ""
        should_update = False

        if existing:
            workflow_id = str(existing[0].get("id", ""))
            if decision == "update":
                should_update = True
            elif decision == "create_another":
                base = name
                idx = 2
                names = {str(w.get("name", "")).strip().lower() for w in listing.get("data", [])}
                while f"{base} ({idx})".lower() in names:
                    idx += 1
                target_name = f"{base} ({idx})"
            elif decision == "cancel":
                self.state.session.pending_intent = None
                self.state.session.pending_params = {}
                self.state.save()
                return {
                    "handled": True,
                    "response": "Ок, не обновляю.",
                    "tool_name": "chat",
                    "tool_result": None,
                    "steps": [],
                    "thinking": "User canceled update",
                }
            else:
                self.state.session.pending_intent = "N8N_CREATE_WORKFLOW_CONFIRM_UPDATE"
                self.state.session.pending_params = {
                    "workflow_name": name,
                    "trigger_type": trigger_type,
                    "node_types": node_types,
                    "set_message": set_message,
                }
                self.state.save()
                return {
                    "handled": True,
                    "response": "Workflow already exists. Update it? да/нет",
                    "tool_name": "chat",
                    "tool_result": None,
                    "steps": [],
                    "thinking": "Idempotency check requires confirmation",
                }

        workflow_json = self._build_n8n_workflow_json(
            name=target_name,
            trigger_type=trigger_type,
            node_types=node_types,
            set_message=set_message,
        )

        if should_update and workflow_id:
            write_res = self._call_tool_json(
                "n8n_update_workflow",
                {"id": workflow_id, "workflow_json": workflow_json, "raw": True},
            )
            action = "updated"
        else:
            write_res = self._call_tool_json(
                "n8n_create_workflow",
                {"workflow_json": workflow_json, "name": target_name, "raw": True},
            )
            action = "created"

        if "error" in write_res:
            return {
                "handled": True,
                "response": f"Ошибка n8n при создании workflow: {write_res['error']}",
                "tool_name": "n8n_create_workflow",
                "tool_result": write_res,
                "steps": [],
                "thinking": "n8n create/update call failed",
            }

        workflow_id = str(write_res.get("id") or workflow_id or "")
        if workflow_id:
            confirm = self._call_tool_json("n8n_get_workflow", {"id": workflow_id, "raw": True})
            if "error" not in confirm:
                workflow_id = str(confirm.get("id", workflow_id))

        # Clear pending state for this workflow flow.
        self.state.session.pending_intent = None
        self.state.session.pending_params = {}
        self.state.save()

        nodes_count = len(workflow_json.get("nodes", []))
        verb = "Updated" if action == "updated" else "Created"
        return {
            "handled": True,
            "response": f"{verb} workflow '{target_name}' in n8n (id={workflow_id or '?'}). Trigger={trigger_type}, nodes={nodes_count}.",
            "tool_name": "n8n_create_workflow" if action == "created" else "n8n_update_workflow",
            "tool_result": {
                "status": action.upper(),
                "id": workflow_id,
                "name": target_name,
                "trigger": trigger_type,
                "nodes": nodes_count,
            },
            "steps": [{"action": action, "workflow_id": workflow_id, "name": target_name}],
            "thinking": "Deterministic n8n workflow creation via tools",
        }

    def _handle_n8n_activate_workflow_decision(self, params: Dict[str, Any]) -> Dict[str, Any]:
        workflow_id = str(params.get("workflow_id", "")).strip()
        workflow_name = str(params.get("workflow_name", "")).strip() or workflow_id
        activate = bool(params.get("activate", False))
        self.state.session.pending_intent = None
        self.state.session.pending_params = {}
        self.state.save()
        if not activate:
            return {
                "handled": True,
                "response": f"Ок, workflow '{workflow_name}' оставлен неактивным.",
                "tool_name": "chat",
                "tool_result": {"status": "INACTIVE", "workflow_id": workflow_id},
                "steps": [],
                "thinking": "User declined activation",
            }
        res = self._call_tool_json("n8n_activate_workflow", {"id": workflow_id, "active": True})
        if isinstance(res, dict) and "error" in res:
            return {
                "handled": True,
                "response": f"Workflow собран, но не активирован: {res['error']}",
                "tool_name": "n8n_activate_workflow",
                "tool_result": res,
                "steps": [],
                "thinking": "Activation failed",
            }
        return {
            "handled": True,
            "response": f"Workflow '{workflow_name}' активирован.",
            "tool_name": "n8n_activate_workflow",
            "tool_result": res,
            "steps": [{"action": "activate", "workflow_id": workflow_id}],
            "thinking": "Workflow activated after confirmation",
        }

    def _handle_n8n_build_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        raw_user_message = str(params.get("raw_user_message", ""))
        recipe_key = params.get("recipe_key") or select_recipe(raw_user_message.lower())
        if not recipe_key:
            return {
                "handled": True,
                "response": (
                    "Не понял тип workflow. Выбери recipe: "
                    "Content Factory, Web Page Parser, Inbox Organizer, Comment Keyword Responder, "
                    "Lead Capture + CRM, File Cleanup Pipeline, PDF Analyzer Pipeline, Municipality Scraping Pipeline."
                ),
                "tool_name": "chat",
                "tool_result": None,
                "steps": [],
                "thinking": "Recipe key required",
            }

        recipe = resolve_recipe(recipe_key) or {}
        explicit_name = str(params.get("workflow_name", "")).strip()
        if explicit_name:
            workflow_name = explicit_name
        else:
            workflow_name = f"{recipe.get('name', 'Workflow')} {datetime.now().strftime('%Y%m%d_%H%M')}"

        merged_params = apply_recipe_defaults(recipe_key, params.get("params", {}) or {})
        missing = validate_recipe_params(recipe_key, merged_params)
        if missing:
            self.state.session.pending_intent = "N8N_BUILD_WORKFLOW_MISSING_PARAMS"
            self.state.session.pending_params = {
                "recipe_key": recipe_key,
                "workflow_name": workflow_name,
                "params": merged_params,
            }
            self.state.save()
            questions = get_missing_param_questions(recipe_key, missing)
            return {
                "handled": True,
                "response": "\n".join(questions),
                "tool_name": "chat",
                "tool_result": {"missing": missing, "recipe": recipe_key},
                "steps": [],
                "thinking": "Missing required recipe params",
            }

        try:
            workflow_json = build_recipe_workflow(recipe_key, workflow_name, merged_params)
        except Exception as e:
            return {
                "handled": True,
                "response": f"Не удалось собрать workflow из recipe: {e}",
                "tool_name": "chat",
                "tool_result": {"error": str(e)},
                "steps": [],
                "thinking": "Recipe build failure",
            }

        validation = self._call_tool_json("n8n_validate_workflow", {"workflow_json": workflow_json, "raw": True})
        if "error" in validation:
            return {
                "handled": True,
                "response": f"Ошибка валидации workflow: {validation['error']}",
                "tool_name": "n8n_validate_workflow",
                "tool_result": validation,
                "steps": [],
                "thinking": "n8n validation tool failed",
            }
        if not validation.get("valid", False):
            return {
                "handled": True,
                "response": f"Workflow не прошел валидацию: {'; '.join(validation.get('errors', [])[:5])}",
                "tool_name": "n8n_validate_workflow",
                "tool_result": validation,
                "steps": [],
                "thinking": "Workflow JSON invalid",
            }

        listing = self._call_tool_json("n8n_list_workflows", {"query": workflow_name, "raw": True})
        if "error" in listing:
            return {
                "handled": True,
                "response": f"Ошибка n8n при поиске workflow: {listing['error']}",
                "tool_name": "n8n_list_workflows",
                "tool_result": listing,
                "steps": [],
                "thinking": "Could not list workflows",
            }
        items = listing.get("data", []) if isinstance(listing, dict) else []
        exact = [w for w in items if str(w.get("name", "")).strip().lower() == workflow_name.lower()]
        if explicit_name and len(exact) > 1:
            return {
                "handled": True,
                "response": f"Найдено несколько workflow с именем '{workflow_name}'. Уточни точное имя.",
                "tool_name": "n8n_list_workflows",
                "tool_result": {"matches": [{"id": w.get("id"), "name": w.get("name")} for w in exact[:10]]},
                "steps": [],
                "thinking": "Ambiguous exact match; refusing to touch multiple workflows",
            }
        should_update = bool(explicit_name and exact)
        workflow_id = str(exact[0].get("id", "")) if should_update else ""
        backup_path = ""

        if should_update:
            current = self._call_tool_json("n8n_get_workflow", {"id": workflow_id, "raw": True})
            if "error" in current:
                return {
                    "handled": True,
                    "response": f"Не удалось загрузить текущий workflow для backup: {current['error']}",
                    "tool_name": "n8n_get_workflow",
                    "tool_result": current,
                    "steps": [],
                    "thinking": "Cannot backup before update",
                }
            backup_path = self._backup_workflow_json(workflow_id, current)
            write_res = self._call_tool_json("n8n_update_workflow", {"id": workflow_id, "workflow_json": workflow_json, "raw": True})
            action = "updated"
        else:
            write_res = self._call_tool_json("n8n_create_workflow", {"name": workflow_name, "workflow_json": workflow_json, "raw": True})
            action = "created"
            workflow_id = str(write_res.get("id", ""))

        if "error" in write_res:
            return {
                "handled": True,
                "response": f"n8n {action} failed: {write_res['error']}",
                "tool_name": "n8n_update_workflow" if should_update else "n8n_create_workflow",
                "tool_result": write_res,
                "steps": [],
                "thinking": "Write workflow failed",
            }

        workflow_id = str(write_res.get("id") or workflow_id)
        execution_ids: List[str] = []
        final_status = "STOPPED"
        next_needed = ""
        debug_report = None

        run_res = self._call_tool_json("n8n_run_workflow", {"workflow_id": workflow_id, "wait": True, "raw": True})
        run_error = run_res.get("error") if isinstance(run_res, dict) else "run returned non-json"

        run_execution_id = str(run_res.get("execution_id", "")) if isinstance(run_res, dict) else ""
        if run_execution_id:
            execution_ids.append(run_execution_id)

        if not run_error and run_execution_id:
            exec_obj = self._call_tool_json("n8n_get_execution", {"execution_id": run_execution_id, "raw": True})
            if isinstance(exec_obj, dict) and str(exec_obj.get("status", "")).lower() in {"success", "succeeded"}:
                final_status = "SUCCESS"

        if final_status != "SUCCESS":
            debug_res = self._handle_n8n_debug_workflow({
                "workflow_id": workflow_id,   # pass id — avoids name-lookup failure when name was truncated
                "workflow_name": workflow_name,
                "max_iterations": 3,
                "dry_run": False,
                "confirm_sensitive_patch": self.intent_classifier._has_confirmation_token(raw_user_message.lower()),
            })
            debug_report = debug_res.get("tool_result", {}) if isinstance(debug_res, dict) else {}
            execution_ids.extend(debug_report.get("execution_ids", []) if isinstance(debug_report, dict) else [])
            final_status = debug_report.get("status", "STOPPED") if isinstance(debug_report, dict) else "STOPPED"
            if final_status != "SUCCESS":
                reason = debug_report.get("reason", "debug loop stopped") if isinstance(debug_report, dict) else "debug loop stopped"
                if "confirmation" in str(reason).lower() or "confirm" in str(reason).lower():
                    next_needed = "Для патча credentials/webhook нужен токен CONFIRM."
                else:
                    next_needed = f"Нужно проверить credentials/ids. Причина: {reason}"

        self.state.session.pending_intent = None
        self.state.session.pending_params = {}
        self.state.save()

        recipe_name = recipe.get("name", recipe_key)
        nodes_count = len(workflow_json.get("nodes", []))
        report_lines = [
            f"recipe: {recipe_name}",
            f"workflow id: {workflow_id or '-'}",
            f"nodes {action}: {nodes_count}",
            f"execution ids: {', '.join([e for e in execution_ids if e]) or '-'}",
            f"final status: {final_status}",
        ]
        if backup_path:
            report_lines.append(f"backup: {backup_path}")
        if next_needed:
            report_lines.append(f"next: {next_needed}")

        if final_status == "SUCCESS":
            self.state.session.pending_intent = "N8N_ACTIVATE_WORKFLOW_CONFIRM"
            self.state.session.pending_params = {"workflow_id": workflow_id, "workflow_name": workflow_name}
            self.state.save()
            report_lines.append("Активировать workflow сейчас? yes/no")

        return {
            "handled": True,
            "response": "\n".join(report_lines),
            "tool_name": "n8n_update_workflow" if should_update else "n8n_create_workflow",
            "tool_result": {
                "recipe": recipe_key,
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "nodes": nodes_count,
                "execution_ids": execution_ids,
                "status": final_status,
                "backup_path": backup_path,
                "debug_report": debug_report,
            },
            "steps": [{"action": action, "workflow_id": workflow_id}],
            "thinking": "Recipe-based n8n build pipeline completed",
        }

    def _resolve_workflow(self, workflow_name: str) -> Dict[str, Any]:
        # n8n truncates workflow names to 128 chars on PUT/POST (via _sanitize_workflow_payload).
        # Strategy:
        #   - Pass only the first 60 chars to tool_n8n_list_workflows as a filter query;
        #     this safely falls within any truncated stored name and the original name.
        #   - Then do exact / prefix-based matching locally.
        _SAFE_PREFIX_LEN = 60  # safely below 128 and avoids truncation artifacts at the end
        from agent_v3 import _N8N_MAX_NAME_LEN  # noqa: PLC0415
        is_long = len(workflow_name) > _N8N_MAX_NAME_LEN
        query_name = workflow_name[:_SAFE_PREFIX_LEN] if is_long else workflow_name
        listing = self._call_tool_json("n8n_list_workflows", {"query": query_name, "raw": True})
        if "error" in listing:
            return listing
        items = listing.get("data", []) if isinstance(listing, dict) else []
        if not items:
            return {"error": f"Workflow '{workflow_name}' not found"}

        wn_lower = workflow_name.strip().lower()
        # 1. Exact match (works for short names or names not truncated by n8n)
        exact = [w for w in items if str(w.get("name", "")).strip().lower() == wn_lower]
        if exact:
            return exact[0]

        # 2. Prefix match: stored name starts with the first _SAFE_PREFIX_LEN chars of the
        #    original name.  Covers long names whose tails differ due to truncation/ellipsis.
        prefix_lower = workflow_name[:_SAFE_PREFIX_LEN].lower()
        prefix_match = [
            w for w in items
            if str(w.get("name", "")).strip().lower().startswith(prefix_lower)
        ]
        if len(prefix_match) == 1:
            return prefix_match[0]
        if len(prefix_match) > 1:
            return {
                "error": f"Multiple workflows matched '{workflow_name}'",
                "matches": [{"id": w.get("id"), "name": w.get("name"), "active": w.get("active")} for w in prefix_match[:10]],
            }

        # 3. Classic fuzzy (substring) match for short names
        fuzzy = [w for w in items if wn_lower in str(w.get("name", "")).strip().lower()]
        if len(fuzzy) == 1:
            return fuzzy[0]
        if len(fuzzy) > 1:
            return {
                "error": f"Multiple workflows matched '{workflow_name}'",
                "matches": [{"id": w.get("id"), "name": w.get("name"), "active": w.get("active")} for w in fuzzy[:10]],
            }
        return {"error": f"Workflow '{workflow_name}' not found"}

    def _handle_n8n_debug_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        workflow_name = (params.get("workflow_name") or "").strip()
        execution_id_hint = (params.get("execution_id") or "").strip()
        # Callers that already know the id (e.g. just created the workflow) pass it
        # directly to skip name-resolution (which breaks when name was truncated to 128 chars).
        workflow_id_hint = (params.get("workflow_id") or "").strip()
        max_iterations = int(params.get("max_iterations", 3) or 3)
        max_iterations = max(1, min(max_iterations, 10))
        dry_run = bool(params.get("dry_run", False))
        confirm_sensitive_patch = bool(params.get("confirm_sensitive_patch", False))

        # ------------------------------------------------------------------
        # Resolve workflow: by id (fastest), by execution, or by name.
        # ------------------------------------------------------------------
        workflow_id: Optional[str] = None
        seed_execution_obj: Optional[Dict[str, Any]] = None  # pre-fetched starting execution

        if workflow_id_hint:
            # Fastest path: id already known (e.g. freshly created workflow).
            # Fetch workflow to get its actual name for logging / display.
            workflow_id = workflow_id_hint
            if not workflow_name:
                wf_meta = self._call_tool_json("n8n_get_workflow", {"id": workflow_id, "raw": True})
                workflow_name = str(wf_meta.get("name", workflow_id)) if "error" not in wf_meta else workflow_id
        elif execution_id_hint:
            exec_meta = self._call_tool_json("n8n_get_execution", {"execution_id": execution_id_hint, "raw": True})
            if "error" in exec_meta:
                return {
                    "handled": True,
                    "response": f"Cannot fetch execution {execution_id_hint}: {exec_meta['error']}",
                    "tool_name": "n8n_debug_workflow",
                    "tool_result": exec_meta,
                    "steps": [],
                    "thinking": "Execution not found",
                }
            workflow_id = str(exec_meta.get("workflowId") or "")
            if not workflow_id:
                return {
                    "handled": True,
                    "response": f"Execution {execution_id_hint} has no workflowId in response.",
                    "tool_name": "n8n_debug_workflow",
                    "tool_result": exec_meta,
                    "steps": [],
                    "thinking": "No workflowId on execution",
                }
            seed_execution_obj = exec_meta
            if not workflow_name:
                workflow_name = str(exec_meta.get("workflowData", {}).get("name", "") or workflow_id)
        else:
            resolved = self._resolve_workflow(workflow_name)
            if "error" in resolved:
                return {
                    "handled": True,
                    "response": f"Stopped: {resolved['error']}",
                    "tool_name": "n8n_debug_workflow",
                    "tool_result": resolved,
                    "steps": [],
                    "thinking": "Could not resolve target workflow safely",
                }
            workflow_id = resolved.get("id")

        print(f"Handled by Controller: N8N_DEBUG_WORKFLOW name={workflow_name} id={workflow_id} seed_exec={execution_id_hint or '-'}")

        wf_full = self._call_tool_json("n8n_get_workflow", {"id": workflow_id, "raw": True})
        if "error" in wf_full:
            return {
                "handled": True,
                "response": f"Stopped: {wf_full['error']}",
                "tool_name": "n8n_debug_workflow",
                "tool_result": wf_full,
                "steps": [],
                "thinking": "Failed to load workflow JSON",
            }

        report = {
            "workflow_id": workflow_id,
            "workflow_name": wf_full.get("name", workflow_name),
            "max_iterations": max_iterations,
            "dry_run": dry_run,
            "iterations": [],
            "execution_ids": [],
            "status": "STOPPED",
            "reason": "",
        }
        last_error_signature = None
        repeated_same_error = 0

        for idx in range(1, max_iterations + 1):
            print(f"Iteration {idx}/{max_iterations}")

            # On the very first iteration, use the caller-provided execution if given.
            if idx == 1 and seed_execution_obj is not None:
                execution_obj = seed_execution_obj
                seed_eid = str(seed_execution_obj.get("id", ""))
                if seed_eid:
                    report["execution_ids"].append(seed_eid)
            else:
                executions = self._call_tool_json("n8n_get_executions", {"workflow_id": workflow_id, "limit": 5, "raw": True})
                if "error" in executions:
                    report["reason"] = executions["error"]
                    break

                execution_list = executions.get("data", [])
                if not execution_list:
                    run_once = self._call_tool_json("n8n_run_workflow", {"workflow_id": workflow_id, "wait": True, "raw": True})
                    run_id = run_once.get("execution_id", "")
                    if run_id:
                        report["execution_ids"].append(run_id)
                    if "error" in run_once:
                        report["reason"] = run_once["error"]
                        break
                    else:
                        execution_obj = self._call_tool_json("n8n_get_execution", {"execution_id": run_id, "raw": True}) if run_id else {}
                else:
                    latest_id = execution_list[0].get("id")
                    execution_obj = self._call_tool_json("n8n_get_execution", {"execution_id": latest_id, "raw": True})

            if "error" in execution_obj:
                report["reason"] = execution_obj["error"]
                break

            status = str(execution_obj.get("status", "")).lower()
            if status in {"success", "succeeded"}:
                report["status"] = "SUCCESS"
                report["reason"] = "workflow execution is successful"
                eid = execution_obj.get("id")
                if eid:
                    report["execution_ids"].append(str(eid))
                print(f"n8n workflow fixed: execution={eid}")
                break

            error_info = self._extract_execution_error(execution_obj)
            err_sig = f"{error_info.get('node_name')}|{error_info.get('message')}".strip()
            if err_sig and err_sig == last_error_signature:
                repeated_same_error += 1
            else:
                repeated_same_error = 0
            last_error_signature = err_sig

            print(f"Error node={error_info.get('node_name', '?')} msg={error_info.get('message', '')[:200]}")

            current_wf = self._call_tool_json("n8n_get_workflow", {"id": workflow_id, "raw": True})
            if "error" in current_wf:
                report["reason"] = current_wf["error"]
                break

            patch = self._propose_patch(current_wf, error_info)
            iter_info = {
                "iteration": idx,
                "status": "ERROR",
                "error_node": error_info.get("node_name"),
                "error_message": error_info.get("message"),
                "patch_summary": patch["summary"],
            }

            if repeated_same_error >= 1:
                report["reason"] = "same error repeated twice with no progress"
                report["iterations"].append(iter_info)
                break

            if not patch["changed"]:
                report["reason"] = "cannot fix automatically"
                report["iterations"].append(iter_info)
                break

            if patch["touches_sensitive"] and not confirm_sensitive_patch:
                report["reason"] = "needs user confirmation for credentials/webhook patch"
                report["iterations"].append(iter_info)
                print(f"🟡 Stopped: reason ({report['reason']})")
                break

            backup_path = self._backup_workflow_json(workflow_id, current_wf)
            iter_info["backup_path"] = backup_path

            if dry_run:
                iter_info["status"] = "DRY_RUN"
                report["iterations"].append(iter_info)
                report["reason"] = "dry-run mode, patch not applied"
                print(f"🛠 Patch applied: {patch['summary']} (dry-run)")
                break

            update_res = self._call_tool_json(
                "n8n_update_workflow",
                {"id": workflow_id, "workflow_json": patch["workflow_json"], "raw": True},
            )
            if "error" in update_res:
                iter_info["status"] = "UPDATE_ERROR"
                iter_info["update_error"] = update_res["error"]
                report["iterations"].append(iter_info)
                report["reason"] = update_res["error"]
                break

            print(f"🛠 Patch applied: {patch['summary']}")
            run_res = self._call_tool_json("n8n_run_workflow", {"workflow_id": workflow_id, "wait": True, "raw": True})
            run_id = run_res.get("execution_id", "")
            if run_id:
                report["execution_ids"].append(run_id)
            iter_info["run_execution_id"] = run_id
            report["iterations"].append(iter_info)
            if "error" in run_res:
                report["reason"] = run_res["error"]
                break

        if report["status"] != "SUCCESS":
            if not report["reason"]:
                report["reason"] = f"max iterations reached ({max_iterations})"
            print(f"Stopped: reason ({report['reason']})")

        # Persist context for follow-up debug commands.
        last_eid = report["execution_ids"][-1] if report["execution_ids"] else ""
        self.state.update_n8n_context(execution_id=last_eid, workflow_id=str(workflow_id or ""))

        lines = [
            f"n8n debug report: workflow={report['workflow_name']} ({report['workflow_id']})",
            f"status={report['status']}",
            f"iterations={len(report['iterations'])}/{max_iterations}",
            f"reason={report['reason']}",
            f"execution_ids={', '.join(report['execution_ids']) if report['execution_ids'] else '-'}",
        ]
        for it in report["iterations"]:
            lines.append(
                f"- i{it['iteration']}: node={it.get('error_node') or '-'} msg={str(it.get('error_message') or '')[:120]} patch={it.get('patch_summary')}"
            )

        return {
            "handled": True,
            "response": "\n".join(lines),
            "tool_name": "n8n_debug_workflow",
            "tool_result": report,
            "steps": report["iterations"],
            "thinking": "Deterministic n8n debug loop completed",
        }

    # ------------------------------------------------------------------
    # Template-based workflow creation
    # ------------------------------------------------------------------

    def _handle_n8n_create_from_template(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a multi-node n8n workflow from a template, then run+debug it."""
        from skills.template_registry import TemplateRegistry
        from skills.template_adapter import TemplateAdapter

        template_id = params.get("template_id", "content_factory")
        registry = TemplateRegistry()
        template = registry.load(template_id)
        if not template:
            return {
                "handled": True,
                "response": f"Template '{template_id}' not found in skills/n8n_templates/.",
                "tool_name": "n8n_create_from_template",
                "tool_result": None,
                "steps": [],
                "thinking": "Template not found",
            }

        # --- Check for missing required params and ask before proceeding ---
        adapter = TemplateAdapter()
        missing = adapter.get_missing_required(template, params)
        if missing:
            # Build a targeted question for the first missing param.
            key = missing[0]
            questions = {
                "FEED_URL":   "Укажи URL RSS-ленты (например, https://example.com/feed):",
                "PLATFORM":   "Укажи платформу (telegram, instagram, twitter, reddit):",
                "TARGET":     "Укажи канал, аккаунт или хэштег (например, @channel, @username или #hashtag):",
                "GROUP_URLS": "Укажи URL Facebook-группы (или несколько через запятую):",
                "SCRIPT_DIR": (
                    "Укажи полный путь к папке facebook-scrapper "
                    "(например, C:\\Agent\\skills\\n8n_templates\\Facebook-scrapper\\Facebook-scrapper-genspark_ai_developer):"
                ),
            }
            question = questions.get(key, f"Укажи значение для параметра {key}:")
            # Save pending state so the next user message completes the params.
            self.state.session.pending_intent = "N8N_TEMPLATE_AWAIT_PARAMS"
            self.state.session.pending_params = {**params, "_missing_param": key}
            self.state.save()
            return {
                "handled": True,
                "response": question,
                "tool_name": "clarify",
                "tool_result": {"missing_param": key},
                "steps": [],
                "thinking": f"Required param {key} missing — asking user",
            }

        workflow_json = adapter.adapt(template, params)
        name = workflow_json.get("name") or params.get("WORKFLOW_NAME") or "Content Factory"

        steps = []

        # --- Check for existing workflow with same name ---
        listing = self._call_tool_json("n8n_list_workflows", {"query": name, "raw": True})
        if "error" in listing:
            return {
                "handled": True,
                "response": f"n8n error while checking existing workflows: {listing['error']}",
                "tool_name": "n8n_create_from_template",
                "tool_result": listing,
                "steps": steps,
                "thinking": "Failed to list workflows",
            }

        existing = [
            w for w in listing.get("data", [])
            if str(w.get("name", "")).strip().lower() == name.lower()
        ]

        workflow_id = ""
        if existing:
            workflow_id = str(existing[0].get("id", ""))
            update_res = self._call_tool_json(
                "n8n_update_workflow",
                {"id": workflow_id, "workflow_json": workflow_json, "raw": True},
            )
            steps.append({"action": "update_workflow", "result": update_res})
            op = "updated"
        else:
            create_res = self._call_tool_json(
                "n8n_create_workflow",
                {"name": name, "workflow_json": workflow_json, "raw": True},
            )
            if "error" in create_res:
                return {
                    "handled": True,
                    "response": f"Failed to create workflow: {create_res['error']}",
                    "tool_name": "n8n_create_from_template",
                    "tool_result": create_res,
                    "steps": steps,
                    "thinking": "n8n create failed",
                }
            workflow_id = str(create_res.get("id", ""))
            steps.append({"action": "create_workflow", "result": create_res})
            op = "created"

        if not workflow_id:
            return {
                "handled": True,
                "response": f"Workflow {op} but no id returned.",
                "tool_name": "n8n_create_from_template",
                "tool_result": None,
                "steps": steps,
                "thinking": "Missing workflow_id after create/update",
            }

        # --- Run → check → fix loop ---
        max_iterations = int(params.get("max_iterations", 3))
        debug_res = self._handle_n8n_debug_workflow({
            "workflow_id": workflow_id,   # pass id — avoids name-lookup failure when name was truncated
            "workflow_name": name,
            "max_iterations": max_iterations,
            "dry_run": False,
            "confirm_sensitive_patch": False,
        })
        steps.extend(debug_res.get("steps", []))

        debug_ok = debug_res.get("tool_result", {}).get("success", False) if debug_res.get("tool_result") else False
        debug_reason = ""
        if isinstance(debug_res.get("tool_result"), dict):
            debug_reason = debug_res["tool_result"].get("reason", "")

        status_line = "SUCCESS" if debug_ok else "NEEDS_ATTENTION"
        response_lines = [
            f"Template workflow '{name}' {op} (id={workflow_id}).",
            f"Template: {template_id}  |  Feed: {params.get('FEED_URL', '')}",
            f"Run+debug loop: {status_line}",
            debug_res.get("response", ""),
        ]

        return {
            "handled": True,
            "response": "\n".join(line for line in response_lines if line),
            "tool_name": "n8n_create_from_template",
            "tool_result": {
                "workflow_id": workflow_id,
                "workflow_name": name,
                "template_id": template_id,
                "operation": op,
                "debug": debug_res.get("tool_result"),
                "success": debug_ok,
            },
            "steps": steps,
            "thinking": f"Template workflow {op}, debug loop done ({status_line})",
        }

    def _handle_n8n_list_templates(self) -> Dict[str, Any]:
        """Return the list of available n8n skill templates."""
        result = self._call_tool_json("n8n_template_list", {})
        text = result.get("text") or str(result)
        return {
            "handled": True,
            "response": text,
            "tool_name": "n8n_template_list",
            "tool_result": result,
            "steps": [],
            "thinking": "User wants to see available n8n templates",
        }

    def _handle_n8n_list_workflows(self) -> Dict[str, Any]:
        """List all workflows in the n8n instance."""
        result = self._call_tool_json("n8n_list_workflows", {"query": "", "raw": True})
        if "error" in result:
            return {
                "handled": True,
                "response": f"Ошибка n8n: {result['error']}",
                "tool_name": "n8n_list_workflows",
                "tool_result": result,
                "steps": [],
                "thinking": "Failed to list n8n workflows",
            }
        items = result.get("data", [])
        if not items:
            return {
                "handled": True,
                "response": "В n8n нет ни одного workflow.",
                "tool_name": "n8n_list_workflows",
                "tool_result": result,
                "steps": [],
                "thinking": "No workflows found",
            }
        lines = ["=== n8n Workflows ===\n"]
        for wf in items:
            status = "✅ активен" if wf.get("active") else "⏸ неактивен"
            lines.append(f"  [{wf.get('id')}] {wf.get('name', '?')}  — {status}")
        lines.append(f"\nИтого: {len(items)} workflow(s).")
        return {
            "handled": True,
            "response": "\n".join(lines),
            "tool_name": "n8n_list_workflows",
            "tool_result": result,
            "steps": [],
            "thinking": "Listed all n8n workflows",
        }

    def _handle_n8n_activate_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Activate or deactivate a named n8n workflow."""
        workflow_name = (params.get("workflow_name") or "").strip()
        active = bool(params.get("active", True))
        action_word = "активировать" if active else "деактивировать"
        if not workflow_name:
            return {
                "handled": True,
                "response": f"Укажи имя workflow, который нужно {action_word}.",
                "tool_name": "n8n_activate_workflow",
                "tool_result": None,
                "steps": [],
                "thinking": "Workflow name missing",
            }
        resolved = self._resolve_workflow(workflow_name)
        if "error" in resolved:
            return {
                "handled": True,
                "response": resolved["error"],
                "tool_name": "n8n_activate_workflow",
                "tool_result": resolved,
                "steps": [],
                "thinking": "Could not resolve workflow name",
            }
        workflow_id = resolved["id"]
        found_name = resolved.get("name", workflow_name)
        res = self._call_tool_json("n8n_activate_workflow", {"id": workflow_id, "active": active})
        if "error" in res:
            return {
                "handled": True,
                "response": f"Ошибка при изменении статуса '{found_name}': {res['error']}",
                "tool_name": "n8n_activate_workflow",
                "tool_result": res,
                "steps": [],
                "thinking": "Activation failed",
            }
        status_word = "активирован" if active else "деактивирован"
        return {
            "handled": True,
            "response": f"Workflow '{found_name}' {status_word}.",
            "tool_name": "n8n_activate_workflow",
            "tool_result": res,
            "steps": [{"action": "activate", "workflow_id": workflow_id, "active": active}],
            "thinking": f"Workflow {status_word} successfully",
        }

    def handle_request(self, user_message: str) -> Dict[str, Any]:
        """
        ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ‚ÑŒ Ð·Ð°Ð¿Ñ€Ð¾Ñ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ Ñ‡ÐµÑ€ÐµÐ· Controller Layer.
        
        Returns:
            {
                "handled": bool,  # Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ð½ Ð»Ð¸ Ñ‡ÐµÑ€ÐµÐ· controller
                "response": str,
                "tool_name": str,
                "tool_result": Any,
                "steps": List[Dict],
                "thinking": str
            }
        """
        # 1. INTENT CLASSIFICATION
        intent_result = self.intent_classifier.classify(user_message)
        
        if not intent_result:
            # ÐÐ°Ð¼ÐµÑ€ÐµÐ½Ð¸Ðµ Ð½Ðµ Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð½Ð¾ â†’ Ð¿ÐµÑ€ÐµÐ´Ð°Ñ‚ÑŒ LLM
            return {"handled": False}
        
        intent, params = intent_result
        print(f"ðŸŽ¯ Intent: {intent}")
        print(f"ðŸ“‹ Params: {params}")
        if intent == "N8N_LIST_WORKFLOWS":
            return self._handle_n8n_list_workflows()
        if intent == "N8N_ACTIVATE_WORKFLOW":
            return self._handle_n8n_activate_workflow(params)
        if intent == "N8N_LIST_TEMPLATES":
            return self._handle_n8n_list_templates()
        if intent == "N8N_CREATE_FROM_TEMPLATE":
            return self._handle_n8n_create_from_template(params)
        if intent in {"N8N_CREATE_WORKFLOW", "N8N_CREATE_WORKFLOW_DECISION"}:
            return self._handle_n8n_create_workflow(params)
        if intent == "N8N_BUILD_WORKFLOW":
            return self._handle_n8n_build_workflow(params)
        if intent == "N8N_ACTIVATE_WORKFLOW_DECISION":
            return self._handle_n8n_activate_workflow_decision(params)
        if intent in {"N8N_DEBUG_WORKFLOW", "N8N_FIX_WORKFLOW"}:
            return self._handle_n8n_debug_workflow(params)

        requested_folder = params.get("folder") or params.get("path")
        self.policy.set_requested_folder(requested_folder)
        if intent == "DELETE_FILE_REQUEST":
            self.state.set_pending_delete(
                full_path=params["path"],
                folder=params.get("folder") or os.path.dirname(params["path"]),
                requested_mode=params.get("requested_mode", "trash"),
            )
        elif intent == "DELETE_WITH_PENDING_CONTEXT_TRASH":
            print(f"Using pending delete context: {params['path']}")

        elif intent == "PURGE_TRASH" and not params.get("confirm"):
            # Ask user to confirm purge before executing
            self.state.session.pending_intent = "PURGE_TRASH_CONFIRM"
            self.state.session.pending_params = dict(params)
            self.state.save()
            return {
                "handled": True,
                "response": (
                    "Вы уверены, что хотите НАВСЕГДА удалить все файлы из корзины (_TRASH)? "
                    "Это необратимо. Напиши 'да' для подтверждения или 'нет' для отмены."
                ),
                "tool_name": "purge_trash",
                "tool_result": None,
                "steps": [],
                "thinking": "Waiting for purge confirmation",
            }
        
        # Short-circuit cancelled cleanup
        if intent == "CLEAN_DUPLICATES_CANCELLED":
            return {
                "handled": True,
                "response": "Очистка дубликатов отменена.",
                "tool_name": None,
                "tool_result": None,
                "steps": [],
                "thinking": "Cleanup cancelled by user",
            }

        # Short-circuit cancelled purge
        if intent == "PURGE_TRASH_CANCELLED":
            return {
                "handled": True,
                "response": "Очистка корзины отменена.",
                "tool_name": None,
                "tool_result": None,
                "steps": [],
                "thinking": "Purge cancelled by user",
            }

        # 2. WORKFLOW PLANNING
        workflow = self.planner.plan(intent, params)
        
        if not workflow:
            return {"handled": False, "error": "ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¿Ð¾ÑÑ‚Ñ€Ð¾Ð¸Ñ‚ÑŒ workflow"}
        
        print(f"ðŸ“ Workflow: {len(workflow)} steps")
        
        # 3. EXECUTION + VALIDATION
        steps = []
        final_result = None
        
        for step in workflow:
            print(f"  âš™ï¸  {step.description}")

            # Always propagate allowed_folder for delete operations.
            if step.tool in {"delete_files", "clean_duplicates"}:
                allowed_folder = (
                    step.args.get("allowed_folder")
                    or params.get("folder")
                    or self.policy.requested_folder
                    or self.policy.last_scanned_folder
                )
                if allowed_folder:
                    step.args["allowed_folder"] = allowed_folder
            
            # Policy check
            allowed, reason = self.policy.check_operation(step.tool, step.args)
            if not allowed:
                return {
                    "handled": True,
                    "response": f"âŒ ÐžÐ¿ÐµÑ€Ð°Ñ†Ð¸Ñ Ð·Ð°Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ð½Ð°: {reason}",
                    "tool_name": step.tool,
                    "tool_result": None,
                    "steps": steps,
                    "thinking": f"Policy denied: {reason}"
                }
            
            # Duplicate cleanup threshold check (P1)
            if step.tool == "clean_duplicates" and not params.get("_confirmed"):
                dry_args = dict(step.args)
                dry_args["mode"] = "dry_run"
                if "clean_duplicates" in self.tools:
                    dry_result = self.tools["clean_duplicates"](dry_args)
                    # Parse counts/size from dry_run output
                    import re as _re
                    m_files = _re.search(r"Would move (\d+) file", dry_result)
                    m_mb = _re.search(r"\(([0-9.]+) MB\)", dry_result)
                    n_files = int(m_files.group(1)) if m_files else 0
                    n_mb = float(m_mb.group(1)) if m_mb else 0.0
                    if n_files >= _DUP_CONFIRM_FILES or n_mb >= _DUP_CONFIRM_MB:
                        origin = "CLEAN" if intent == "CLEAN_DUPLICATES_KEEP_NEWEST" else "FOLLOWUP"
                        self.state.session.pending_intent = "CLEAN_DUPLICATES_CONFIRM"
                        self.state.session.pending_params = dict(params)
                        self.state.session.pending_params["_origin"] = origin
                        self.state.save()
                        return {
                            "handled": True,
                            "response": (
                                f"Будет перемещено {n_files} файл(ов) ({n_mb:.1f} MB) в корзину. "
                                f"Подтверди: 'да' для продолжения или 'нет' для отмены."
                            ),
                            "tool_name": "clean_duplicates",
                            "tool_result": dry_result,
                            "steps": steps,
                            "thinking": f"Threshold exceeded: {n_files} files / {n_mb} MB",
                        }

            # Confirmation check
            if self.policy.needs_confirmation(step.tool, step.args):
                if step.tool == "delete_files":
                    return {
                        "handled": True,
                        "response": "Blocked: permanent delete requires permanent=true and confirm=true.",
                        "tool_name": step.tool,
                        "tool_result": None,
                        "steps": steps,
                        "thinking": "Confirmation required for permanent delete"
                    }
            
            # Execute tool
            try:
                if step.tool not in self.tools:
                    return {
                        "handled": True,
                        "response": f"âŒ Ð˜Ð½ÑÑ‚Ñ€ÑƒÐ¼ÐµÐ½Ñ‚ '{step.tool}' Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½",
                        "tool_name": step.tool,
                        "tool_result": None,
                        "steps": steps,
                        "thinking": f"Tool not found: {step.tool}"
                    }
                
                result = self.tools[step.tool](step.args)
                final_result = result
                
                # Validation
                if step.tool == "find_duplicates":
                    valid, error = self.validator.validate_duplicates_scan(result)
                    if not valid:
                        return {
                            "handled": True,
                            "response": f"âŒ {error}",
                            "tool_name": step.tool,
                            "tool_result": result,
                            "steps": steps,
                            "thinking": error
                        }
                    
                    # Update state after successful scan
                    # TODO: extract duplicates_map from result
                    self.state.session.last_duplicates_path = step.args["path"]
                    self.state.session.pending_intent = "CLEAN_DUPLICATES_AVAILABLE"
                    self.policy.set_last_scanned_folder(step.args["path"])
                    self.state.save()
                
                elif step.tool == "clean_duplicates":
                    valid, error = self.validator.validate_cleanup(result)
                    if not valid:
                        return {
                            "handled": True,
                            "response": f"âŒ {error}",
                            "tool_name": step.tool,
                            "tool_result": result,
                            "steps": steps,
                            "thinking": error
                        }
                    
                    # Clear pending intent after cleanup
                    self.state.session.clear_task()
                    self.state.save()
                elif step.tool == "delete_files":
                    if "Blocked" not in str(result) and "Error" not in str(result):
                        self.state.clear_pending_delete()
                
                steps.append({
                    "tool": step.tool,
                    "args": step.args,
                    "result": str(result)[:1000],
                    "description": step.description
                })
                
                self.state.session.add_step(step.tool, step.args, result)
                
            except Exception as e:
                return {
                    "handled": True,
                    "response": f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ°: {e}",
                    "tool_name": step.tool,
                    "tool_result": None,
                    "steps": steps,
                    "thinking": f"Exception: {e}"
                }
        
        # 4. RETURN SUCCESS
        return {
            "handled": True,
            "response": final_result,
            "tool_name": workflow[-1].tool if workflow else None,
            "tool_result": final_result,
            "steps": steps,
            "thinking": f"Executed workflow '{intent}' with {len(steps)} steps"
        }


# ============================================================
# INTEGRATION HELPER
# ============================================================

def create_controller(memory_dir: str, tools_dict: Dict) -> AgentController:
    """
    Ð¤Ð°Ð±Ñ€Ð¸ÐºÐ° Ð´Ð»Ñ ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ñ ÐºÐ¾Ð½Ñ‚Ñ€Ð¾Ð»Ð»ÐµÑ€Ð°.
    
    Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð² agent_v3.py:
    
        from controller import create_controller
        
        # Ð’ Ð½Ð°Ñ‡Ð°Ð»Ðµ Ñ„Ð°Ð¹Ð»Ð° Ð¿Ð¾ÑÐ»Ðµ Ð¾Ð¿Ñ€ÐµÐ´ÐµÐ»ÐµÐ½Ð¸Ñ TOOLS
        CONTROLLER = create_controller(MEMORY_DIR, TOOLS)
        
        # Ð’ process_message() Ð¿ÐµÑ€ÐµÐ´ agentic loop:
        controller_result = CONTROLLER.handle_request(user_message)
        if controller_result.get("handled"):
            return controller_result
    """
    return AgentController(memory_dir, tools_dict)

