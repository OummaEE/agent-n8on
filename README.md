# Jane's AI Agent v4.0 - Local AI Assistant with Skills, Telegram & CRM

## What Is This
A personal AI assistant that runs **100% locally** on your Windows PC.
Uses Ollama for LLM, has a beautiful chat interface in the browser, and can actually **execute** code, manage files, parse websites, create documents, manage CRM, control n8n workflows, and receive tasks from Telegram.

No cloud. No subscriptions. Your data stays on your machine.

## Quick Start

### Prerequisites
- **Python 3.10+**
- **Ollama** running with model `qwen2.5-coder:14b`
- **Playwright** + **playwright-stealth**

### Install Dependencies (one time)
```powershell
pip install requests playwright playwright-stealth python-docx reportlab openpyxl python-pptx psutil PyPDF2
playwright install chromium
```

### Optional Dependencies (for specific skills)
```powershell
# Voice input (Whisper STT)
pip install openai-whisper sounddevice numpy

# Telegram bot
# No extra packages needed (uses requests)
```

### Run
```powershell
python agent_v3.py
```

Opens `http://localhost:5000` in your browser automatically.

## Architecture

```
jane_agent/
  agent_v3.py          # Main agent: Web UI + 29 built-in tools + skills loader
  skills/              # Plugin directory (auto-loaded on startup)
    skills_enabled.json  # Whitelist: only listed skills are loaded
    kommun_parser.py     # Swedish municipality parser
    google_calendar.py   # Google Calendar integration
    telegram_bot.py      # Telegram bot (receive tasks)
    excel_reports.py     # Advanced Excel reports
    boostcamp_crm.py     # CRM for accelerator programs
    pdf_analyzer.py      # PDF text extraction and search
    n8n_templates.py     # Ready-made n8n workflow templates
    voice_input.py       # Voice input via Whisper STT
    __init__.py
  memory/              # Persistent storage (auto-created)
    chat_history.json    # Last 200 messages
    user_profile.json    # User preferences and facts
    tasks.json           # Task tracking
    crm_data.json        # CRM data (startups, investors, programs)
  .env                 # Secrets: API keys, tokens (not tracked in git)
  agent_v2.py          # Previous CLI version (archive)
  install.bat          # Legacy installer
  README.md            # This file
```

## Tools Summary

### 29 Built-in Tools
| Tool | Description |
|------|-------------|
| `run_python` | Execute Python code |
| `run_powershell` | Execute PowerShell commands |
| `create_file` | Create text files |
| `read_file` | Read file contents |
| `list_files` | List directory contents |
| `organize_folder` | Auto-sort files by type |
| `find_duplicates` | Find duplicate files |
| `disk_usage` | Show disk space info |
| `open_app` | Open apps or URLs |
| `create_document` | Create Word/PDF/Excel/PowerPoint |
| `web_search` | Search via DuckDuckGo |
| `parse_webpage` | Extract text (Playwright+stealth) |
| `stealth_browse` | Browse with visible stealth browser |
| `take_screenshot` | Screenshot any webpage |
| `system_info` | CPU, RAM, disk info |
| `clean_temp` | Clean temp files |
| `send_email` | Send via Gmail |
| `n8n_list_workflows` | List n8n workflows |
| `n8n_get_workflow` | Get workflow details |
| `n8n_create_workflow` | Create n8n workflow |
| `n8n_activate_workflow` | Activate/deactivate workflow |
| `n8n_delete_workflow` | Delete n8n workflow |
| `delete_files` | Delete files by paths |
| `move_files` | Move/rename files |
| `memory_add_fact` | Remember a fact about user |
| `memory_add_task` | Add a task |
| `memory_complete_task` | Mark task as done |
| `memory_show` | Show memory contents |
| `chat` | Just talk |

### 26 Skill Tools (from 8 skills)

| Skill | Tools | Description |
|-------|-------|-------------|
| **kommun_parser** | `parse_kommun`, `search_kommuns` | Parse Swedish municipality websites for contacts |
| **google_calendar** | `calendar_today`, `calendar_week`, `calendar_create` | Google Calendar integration |
| **telegram_bot** | `telegram_send`, `telegram_status` | Send/receive messages from Telegram |
| **excel_reports** | `excel_create_report`, `excel_read`, `excel_analyze` | Advanced Excel with charts |
| **boostcamp_crm** | `crm_add_startup`, `crm_list_startups`, `crm_add_investor`, `crm_list_investors`, `crm_add_program`, `crm_list_programs`, `crm_search`, `crm_stats` | CRM for accelerator programs |
| **pdf_analyzer** | `pdf_read`, `pdf_info`, `pdf_search` | PDF text extraction and search |
| **n8n_templates** | `n8n_template_list`, `n8n_template_get` | Ready-made n8n workflow templates |
| **voice_input** | `voice_listen`, `voice_transcribe`, `voice_status` | Voice input via Whisper STT |

**Total: 55 tools (29 built-in + 26 from skills)**

## Skills System

### How It Works
1. On startup, agent scans `skills/` directory
2. Only skills listed in `skills_enabled.json` are loaded
3. Each skill is a standalone `.py` file with `TOOLS` dict
4. Skill tools are merged into the main tool router

### Security (3 levels)
1. **Local only**: Skills run on your machine, no data leaves
2. **Transparent code**: Each skill is a readable `.py` file
3. **Whitelist**: New skills don't load until added to `skills_enabled.json`

### Adding a New Skill
1. Create `skills/my_skill.py` with `SKILL_NAME`, `SKILL_TOOLS`, `TOOLS` exports
2. Add `"my_skill"` to `skills/skills_enabled.json` -> `enabled` array
3. Restart agent

### Disabling a Skill
Remove its name from `skills/skills_enabled.json` -> `enabled` array.

## Telegram Integration

### Setup
1. Open Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow steps, copy the token
3. Add to `.env` file:
   ```
   TELEGRAM_BOT_TOKEN=your-token-here
   ```
4. Restart agent - Telegram bot starts automatically

### How It Works
- Send a message to your bot in Telegram
- Agent processes it through Ollama (same as web UI)
- Result is sent back to Telegram
- All 55 tools available from Telegram too

## n8n Integration

### Setup
1. Start n8n locally: `npx n8n start`
2. Get API key from n8n Settings -> API
3. Add to `.env`:
   ```
   N8N_API_KEY=your-n8n-api-key
   N8N_URL=http://localhost:5678
   ```

### Built-in n8n Tools
- List, create, activate, delete workflows
- 5 ready-made workflow templates (daily monitor, email digest, RSS, kommun parser, backup)

## API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI |
| GET | `/api/status` | Ollama status + skills + tool count |
| GET | `/api/tools` | List all available tools (55) |
| GET | `/api/skills` | List loaded skills with their tools |
| GET | `/api/history` | Conversation history (last 50) |
| GET | `/api/memory` | User profile, tasks, history length |
| POST | `/api/chat` | Send message `{"message": "..."}` |
| POST | `/api/clear` | Clear conversation history |

## Configuration

Edit the top of `agent_v3.py`:
```python
OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5-coder:14b"
WEB_PORT = 5000
```

### .env File (secrets)
```
# Gmail
GMAIL_ADDRESS=your.email@gmail.com
GMAIL_APP_PASSWORD=your_app_password

# Telegram
TELEGRAM_BOT_TOKEN=your-telegram-bot-token

# n8n
N8N_API_KEY=your-n8n-api-key
N8N_URL=http://localhost:5678

# Google Calendar (optional)
GOOGLE_CALENDAR_ID=your-calendar-id@gmail.com
GOOGLE_API_KEY=your-google-api-key
```

## Version History

| Version | Changes |
|---------|---------|
| **v4.0** | Skills system (8 skills, 26 tools), Telegram bot, CRM, kommun parser, voice input |
| v3.3 | Added `delete_files`, `move_files` (29 built-in tools) |
| v3.2 | Persistent memory (chat_history, user_profile, tasks) |
| v3.1 | n8n integration (5 workflow tools) |
| v3.0 | Web UI, 18 tools, Playwright+stealth |
| v2.0 | CLI version, basic tools |

## Tech Stack
- Python 3 (stdlib `http.server` - zero web frameworks)
- Ollama (local LLM, qwen2.5-coder:14b)
- Playwright + stealth (web automation)
- HTML/CSS/JS (inline, single file)
- Everything runs locally, no cloud dependencies

## URLs
- **Web UI**: http://localhost:5000
- **Ollama**: http://localhost:11434
- **n8n**: http://localhost:5678

Last updated: 2026-02-11
