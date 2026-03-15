"""
Skill: telegram_bot
Description: Telegram bot integration — receive tasks, send messages, files, photos.
Requires: TELEGRAM_BOT_TOKEN in .env
Optional: TELEGRAM_ALLOWED_IDS in .env (comma-separated chat IDs for security)
Setup: 1) Message @BotFather on Telegram, /newbot, get token
       2) Add TELEGRAM_BOT_TOKEN=your-token to .env
       3) (Optional) Add TELEGRAM_ALLOWED_IDS=123456789 to .env for security
       4) Start agent — it will auto-start polling Telegram
Author: Jane's Agent Builder
Version: 2.0 — added file/photo sending, security, allowed_ids
"""

import threading
import time
import json
import requests
import os
import sys
import io

# FIX: Force UTF-8 for console output on Windows (prevents 'charmap' codec errors)
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except:
            pass

SKILL_NAME = "telegram_bot"
SKILL_VERSION = "2.0"
SKILL_DESCRIPTION = "Telegram bot — send messages/files/photos, receive tasks from Telegram"
SKILL_TOOLS = {
    "telegram_send": {
        "description": "Send a text message to a Telegram chat",
        "args": {
            "chat_id": "Telegram chat ID (optional if you already chatted with the bot)",
            "message": "Text message to send"
        },
        "example": '{"tool": "telegram_send", "args": {"message": "Report is ready!"}}'
    },
    "telegram_send_file": {
        "description": "Send a file (document) to Telegram — PDF, Excel, Word, ZIP, any file",
        "args": {
            "chat_id": "Telegram chat ID (optional)",
            "path": "Path to the file on disk",
            "caption": "Optional caption/description for the file"
        },
        "example": '{"tool": "telegram_send_file", "args": {"path": "C:/Users/Dator/Desktop/report.xlsx", "caption": "Monthly report"}}'
    },
    "telegram_send_photo": {
        "description": "Send a photo/screenshot to Telegram",
        "args": {
            "chat_id": "Telegram chat ID (optional)",
            "path": "Path to image file (PNG, JPG, etc.)",
            "caption": "Optional caption"
        },
        "example": '{"tool": "telegram_send_photo", "args": {"path": "C:/Users/Dator/Desktop/screenshot.png", "caption": "Screenshot of the page"}}'
    },
    "telegram_status": {
        "description": "Show Telegram bot status, connection info, and recent messages",
        "args": {},
        "example": '{"tool": "telegram_status", "args": {}}'
    }
}

# Global state for Telegram bot
_tg_state = {
    "running": False,
    "bot_name": None,
    "last_update_id": 0,
    "messages_received": 0,
    "messages_sent": 0,
    "files_sent": 0,
    "last_chat_id": None,
    "recent_messages": [],
    "process_callback": None,
    "history_callback": None,
    "allowed_ids": None,  # Security: only these chat IDs can use the bot
}


def _load_tg_config():
    """Load Telegram config from .env"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    config = {}
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, val = line.split('=', 1)
                    config[key.strip()] = val.strip().strip('"').strip("'")
    return config


def _tg_api(method: str, data: dict = None, files: dict = None) -> dict:
    """Call Telegram Bot API (supports file uploads via multipart)"""
    config = _load_tg_config()
    token = config.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"error": "TELEGRAM_BOT_TOKEN not set in .env"}

    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        if files:
            # Multipart upload for files/photos
            resp = requests.post(url, data=data or {}, files=files, timeout=120)
        elif data:
            resp = requests.post(url, json=data, timeout=30)
        else:
            resp = requests.get(url, timeout=30)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _is_allowed(chat_id) -> bool:
    """Check if chat_id is in the allowed list (security)"""
    if _tg_state["allowed_ids"] is None:
        return True  # No restrictions
    return str(chat_id) in _tg_state["allowed_ids"]


def _poll_loop():
    """Long-polling loop for incoming Telegram messages"""
    global _tg_state

    # Get bot info
    me = _tg_api("getMe")
    if me.get("ok"):
        _tg_state["bot_name"] = me["result"].get("username", "unknown")
        print(f"  Telegram: bot @{_tg_state['bot_name']} connected.")
    else:
        print(f"  Telegram: failed to connect — {me.get('error', me.get('description', 'unknown error'))}")
        _tg_state["running"] = False
        return

    while _tg_state["running"]:
        try:
            result = _tg_api("getUpdates", {
                "offset": _tg_state["last_update_id"] + 1,
                "timeout": 20,
                "allowed_updates": ["message"]
            })

            if not result.get("ok"):
                time.sleep(5)
                continue

            for update in result.get("result", []):
                _tg_state["last_update_id"] = update["update_id"]

                msg = update.get("message", {})
                text = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")
                user_name = msg.get("from", {}).get("first_name", "Unknown")

                if not text or not chat_id:
                    continue

                # Security check
                if not _is_allowed(chat_id):
                    _tg_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": "Access denied. Your chat ID is not in TELEGRAM_ALLOWED_IDS."
                    })
                    continue

                _tg_state["messages_received"] += 1
                _tg_state["last_chat_id"] = chat_id
                _tg_state["recent_messages"].append({
                    "from": user_name,
                    "text": text[:200],
                    "chat_id": chat_id,
                    "time": time.strftime("%H:%M:%S")
                })
                _tg_state["recent_messages"] = _tg_state["recent_messages"][-20:]

                # Send "typing" indicator
                _tg_api("sendChatAction", {"chat_id": chat_id, "action": "typing"})

                # Process message through agent
                if _tg_state["process_callback"]:
                    try:
                        agent_result = _tg_state["process_callback"](
                            text,
                            _tg_state.get("history_callback", [])
                        )

                        # Extract response text
                        response_text = ""
                        file_path = None

                        if isinstance(agent_result, dict):
                            tool_name = agent_result.get("tool_name", "")
                            tool_result = agent_result.get("tool_result", "")
                            response = agent_result.get("response", "")

                            if tool_name == "chat":
                                # FIX: "chat" tool puts text in "response", not "tool_result"
                                response_text = str(response or tool_result or "")
                            elif tool_result:
                                result_str = str(tool_result)
                                response_text = f"[{tool_name}]\n{result_str[:3000]}"

                                # Auto-detect if a file was created — send it
                                if any(kw in result_str.lower() for kw in
                                       ['created:', 'saved:', 'screenshot saved:', 'report created:']):
                                    # Try to extract file path from result
                                    for line in result_str.split('\n'):
                                        for kw in ['created:', 'saved:', 'Screenshot saved:',
                                                    'Report created:', 'Excel report created:']:
                                            if kw.lower() in line.lower():
                                                path_part = line.split(kw, 1)[-1] if kw in line else \
                                                    line.split(kw.lower(), 1)[-1]
                                                path_part = path_part.strip()
                                                if os.path.exists(path_part):
                                                    file_path = path_part
                                                    break
                                        if file_path:
                                            break

                            elif response:
                                # FIX: Also check "response" field (used when no tool detected)
                                response_text = str(response)[:3000]
                            elif agent_result.get("answer"):
                                response_text = str(agent_result["answer"])[:3000]
                            elif agent_result.get("raw"):
                                # Last resort: use the raw Ollama output
                                raw = str(agent_result["raw"])
                                # Strip <think>...</think> tags
                                if "<think>" in raw:
                                    idx = raw.rfind("</think>")
                                    if idx != -1:
                                        raw = raw[idx + 8:].strip()
                                response_text = raw[:3000] if raw else ""
                            else:
                                response_text = json.dumps(agent_result, ensure_ascii=False)[:3000]
                        else:
                            response_text = str(agent_result)[:3000]

                        # FIX: Never send empty or "None" to user
                        if not response_text or response_text == "None":
                            response_text = "(Agent processed the request but returned no text output)"

                        if response_text:
                            telegram_send(str(chat_id), response_text)

                        # Auto-send file if detected
                        if file_path:
                            ext = os.path.splitext(file_path)[1].lower()
                            if ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
                                telegram_send_photo(str(chat_id), file_path, "Auto-attached file")
                            else:
                                telegram_send_file(str(chat_id), file_path, "Auto-attached file")

                    except Exception as e:
                        telegram_send(str(chat_id), f"Error: {str(e)[:500]}")

        except Exception as e:
            print(f"  Telegram poll error: {e}")
            time.sleep(5)


def start_telegram_bot(process_callback=None, history_callback=None):
    """Start the Telegram bot polling in a background thread"""
    global _tg_state

    config = _load_tg_config()
    if not config.get("TELEGRAM_BOT_TOKEN"):
        print("  Telegram: no TELEGRAM_BOT_TOKEN in .env — bot disabled.")
        return False

    if _tg_state["running"]:
        return True

    _tg_state["running"] = True
    _tg_state["process_callback"] = process_callback
    _tg_state["history_callback"] = history_callback

    # Load allowed IDs (security)
    allowed = config.get("TELEGRAM_ALLOWED_IDS", "")
    if allowed:
        _tg_state["allowed_ids"] = set(
            aid.strip() for aid in allowed.split(",") if aid.strip()
        )
        print(f"  Telegram: security ON — only {len(_tg_state['allowed_ids'])} allowed chat(s)")
    else:
        _tg_state["allowed_ids"] = None
        print("  Telegram: security OFF — anyone can message the bot")
        print("  Tip: add TELEGRAM_ALLOWED_IDS=your_chat_id to .env for security")

    thread = threading.Thread(target=_poll_loop, daemon=True, name="telegram-bot")
    thread.start()
    return True


def stop_telegram_bot():
    """Stop the Telegram bot"""
    global _tg_state
    _tg_state["running"] = False


def telegram_send(chat_id: str, message: str) -> str:
    """Send a text message to Telegram"""
    if not chat_id:
        chat_id = str(_tg_state.get("last_chat_id", ""))
    if not chat_id:
        return ("No chat_id specified and no previous chat found.\n"
                "First send a message TO the bot from Telegram, then the agent can reply.")

    chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]

    for chunk in chunks:
        result = _tg_api("sendMessage", {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML"
        })
        if not result.get("ok"):
            result = _tg_api("sendMessage", {
                "chat_id": chat_id,
                "text": chunk
            })
        if result.get("ok"):
            _tg_state["messages_sent"] += 1
        else:
            return f"Error sending message: {result.get('description', 'unknown error')}"

    return f"Message sent to chat {chat_id} ({len(message)} chars)"


def telegram_send_file(chat_id: str, path: str, caption: str = "") -> str:
    """Send a file (document) to Telegram — PDF, Excel, Word, ZIP, any file up to 50MB"""
    if not chat_id:
        chat_id = str(_tg_state.get("last_chat_id", ""))
    if not chat_id:
        return "No chat_id. Send a message to the bot first."

    if not os.path.exists(path):
        return f"File not found: {path}"

    file_size = os.path.getsize(path)
    if file_size > 50 * 1024 * 1024:
        return f"File too large ({file_size / 1024 / 1024:.1f} MB). Telegram limit is 50 MB."

    file_name = os.path.basename(path)

    try:
        with open(path, 'rb') as f:
            result = _tg_api(
                "sendDocument",
                data={"chat_id": chat_id, "caption": caption[:1024] if caption else ""},
                files={"document": (file_name, f)}
            )

        if result.get("ok"):
            _tg_state["files_sent"] += 1
            return f"File sent: {file_name} ({file_size / 1024:.1f} KB) to chat {chat_id}"
        else:
            return f"Error sending file: {result.get('description', 'unknown error')}"
    except Exception as e:
        return f"Error sending file: {e}"


def telegram_send_photo(chat_id: str, path: str, caption: str = "") -> str:
    """Send a photo/screenshot to Telegram"""
    if not chat_id:
        chat_id = str(_tg_state.get("last_chat_id", ""))
    if not chat_id:
        return "No chat_id. Send a message to the bot first."

    if not os.path.exists(path):
        return f"Image not found: {path}"

    file_name = os.path.basename(path)

    try:
        with open(path, 'rb') as f:
            result = _tg_api(
                "sendPhoto",
                data={"chat_id": chat_id, "caption": caption[:1024] if caption else ""},
                files={"photo": (file_name, f)}
            )

        if result.get("ok"):
            _tg_state["files_sent"] += 1
            return f"Photo sent: {file_name} to chat {chat_id}"
        else:
            return f"Error sending photo: {result.get('description', 'unknown error')}"
    except Exception as e:
        return f"Error sending photo: {e}"


def telegram_status() -> str:
    """Show Telegram bot status"""
    lines = ["=== Telegram Bot Status ==="]

    if _tg_state["running"]:
        lines.append(f"Status: Running")
        lines.append(f"Bot: @{_tg_state['bot_name']}")
    else:
        config = _load_tg_config()
        if config.get("TELEGRAM_BOT_TOKEN"):
            lines.append(f"Status: Stopped (token found but bot not running)")
        else:
            lines.append(f"Status: Not configured")
            lines.append(f"\nSetup:")
            lines.append(f"1. Open Telegram, message @BotFather")
            lines.append(f"2. Send /newbot, follow steps, get token")
            lines.append(f"3. Add to .env: TELEGRAM_BOT_TOKEN=your-token")
            lines.append(f"4. Restart agent")
            return "\n".join(lines)

    lines.append(f"Messages received: {_tg_state['messages_received']}")
    lines.append(f"Messages sent: {_tg_state['messages_sent']}")
    lines.append(f"Files sent: {_tg_state['files_sent']}")

    if _tg_state["allowed_ids"]:
        lines.append(f"Security: ON ({len(_tg_state['allowed_ids'])} allowed chat(s))")
    else:
        lines.append(f"Security: OFF (anyone can message)")

    if _tg_state["last_chat_id"]:
        lines.append(f"Last chat ID: {_tg_state['last_chat_id']}")

    recent = _tg_state["recent_messages"]
    if recent:
        lines.append(f"\nRecent messages ({len(recent)}):")
        for m in recent[-5:]:
            lines.append(f"  [{m['time']}] {m['from']}: {m['text'][:80]}")

    return "\n".join(lines)


TOOLS = {
    "telegram_send": lambda args: telegram_send(args.get("chat_id", ""), args.get("message", "")),
    "telegram_send_file": lambda args: telegram_send_file(
        args.get("chat_id", ""), args.get("path", ""), args.get("caption", "")
    ),
    "telegram_send_photo": lambda args: telegram_send_photo(
        args.get("chat_id", ""), args.get("path", ""), args.get("caption", "")
    ),
    "telegram_status": lambda args: telegram_status(),
}
