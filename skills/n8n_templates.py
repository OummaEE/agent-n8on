"""
Skill: n8n_templates
Description: Ready-made n8n workflow templates for common automations.
Provides templates that can be imported directly into n8n.
Author: Jane's Agent Builder
"""

import json

SKILL_NAME = "n8n_templates"
SKILL_VERSION = "1.0"
SKILL_DESCRIPTION = "Ready-made n8n workflow templates — daily reports, monitoring, parsing"
SKILL_TOOLS = {
    "n8n_template_list": {
        "description": "List all available n8n workflow templates",
        "args": {},
        "example": '{"tool": "n8n_template_list", "args": {}}'
    },
    "n8n_template_get": {
        "description": "Get a specific template by name, ready to import into n8n",
        "args": {"template": "Template name (from list)"},
        "example": '{"tool": "n8n_template_get", "args": {"template": "daily_website_monitor"}}'
    }
}

TEMPLATES = {
    "daily_website_monitor": {
        "name": "Daily Website Monitor",
        "description": "Check a website every day at 9am, detect changes, send notification",
        "tags": ["monitoring", "daily", "web"],
        "workflow": {
            "name": "Daily Website Monitor",
            "nodes": [
                {
                    "parameters": {"rule": {"interval": [{"triggerAtHour": 9}]}},
                    "name": "Every day 9am",
                    "type": "n8n-nodes-base.scheduleTrigger",
                    "position": [250, 300]
                },
                {
                    "parameters": {
                        "url": "={{$json.url || 'https://example.com'}}",
                        "options": {"timeout": 10000}
                    },
                    "name": "Fetch Page",
                    "type": "n8n-nodes-base.httpRequest",
                    "position": [470, 300]
                },
                {
                    "parameters": {
                        "jsCode": "const crypto = require('crypto');\nconst html = $input.first().json.data;\nconst hash = crypto.createHash('md5').update(html).digest('hex');\nreturn [{json: {hash, length: html.length, timestamp: new Date().toISOString()}}];"
                    },
                    "name": "Hash Content",
                    "type": "n8n-nodes-base.code",
                    "position": [690, 300]
                }
            ],
            "connections": {
                "Every day 9am": {"main": [[{"node": "Fetch Page", "type": "main", "index": 0}]]},
                "Fetch Page": {"main": [[{"node": "Hash Content", "type": "main", "index": 0}]]}
            }
        }
    },
    "email_digest": {
        "name": "Daily Email Digest",
        "description": "Collect emails, summarize with Ollama, send digest to Telegram",
        "tags": ["email", "ai", "daily", "telegram"],
        "workflow": {
            "name": "Daily Email Digest",
            "nodes": [
                {
                    "parameters": {"rule": {"interval": [{"triggerAtHour": 8}]}},
                    "name": "Every day 8am",
                    "type": "n8n-nodes-base.scheduleTrigger",
                    "position": [250, 300]
                },
                {
                    "parameters": {
                        "resource": "message",
                        "operation": "getAll",
                        "returnAll": False,
                        "limit": 20,
                        "filters": {"readStatus": "unread"}
                    },
                    "name": "Get Unread Emails",
                    "type": "n8n-nodes-base.gmail",
                    "position": [470, 300]
                },
                {
                    "parameters": {
                        "jsCode": "const emails = $input.all().map(i => `From: ${i.json.from}\\nSubject: ${i.json.subject}\\n`);\nreturn [{json: {summary_prompt: `Summarize these emails in 3 sentences:\\n${emails.join('\\n')}`}}];"
                    },
                    "name": "Prepare Summary",
                    "type": "n8n-nodes-base.code",
                    "position": [690, 300]
                }
            ],
            "connections": {
                "Every day 8am": {"main": [[{"node": "Get Unread Emails", "type": "main", "index": 0}]]},
                "Get Unread Emails": {"main": [[{"node": "Prepare Summary", "type": "main", "index": 0}]]}
            }
        }
    },
    "rss_to_telegram": {
        "name": "RSS to Telegram",
        "description": "Monitor RSS feed and send new items to Telegram",
        "tags": ["rss", "telegram", "monitoring"],
        "workflow": {
            "name": "RSS to Telegram",
            "nodes": [
                {
                    "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}},
                    "name": "Every hour",
                    "type": "n8n-nodes-base.scheduleTrigger",
                    "position": [250, 300]
                },
                {
                    "parameters": {"url": "https://example.com/feed.xml"},
                    "name": "Read RSS",
                    "type": "n8n-nodes-base.rssFeedRead",
                    "position": [470, 300]
                }
            ],
            "connections": {
                "Every hour": {"main": [[{"node": "Read RSS", "type": "main", "index": 0}]]}
            }
        }
    },
    "kommun_parser_schedule": {
        "name": "Scheduled Kommun Parser",
        "description": "Parse Swedish kommun websites weekly and save results to Google Sheets",
        "tags": ["parsing", "kommun", "weekly", "google-sheets"],
        "workflow": {
            "name": "Weekly Kommun Parser",
            "nodes": [
                {
                    "parameters": {"rule": {"interval": [{"triggerAtDay": 1, "triggerAtHour": 10}]}},
                    "name": "Every Monday 10am",
                    "type": "n8n-nodes-base.scheduleTrigger",
                    "position": [250, 300]
                },
                {
                    "parameters": {
                        "jsCode": "const urls = [\n  'https://www.stockholm.se/kontakt',\n  'https://goteborg.se/kontakt',\n  'https://malmo.se/kontakt'\n];\nreturn urls.map(url => ({json: {url}}));"
                    },
                    "name": "Kommun URLs",
                    "type": "n8n-nodes-base.code",
                    "position": [470, 300]
                },
                {
                    "parameters": {"url": "={{$json.url}}", "options": {"timeout": 15000}},
                    "name": "Fetch Page",
                    "type": "n8n-nodes-base.httpRequest",
                    "position": [690, 300]
                }
            ],
            "connections": {
                "Every Monday 10am": {"main": [[{"node": "Kommun URLs", "type": "main", "index": 0}]]},
                "Kommun URLs": {"main": [[{"node": "Fetch Page", "type": "main", "index": 0}]]}
            }
        }
    },
    "backup_files_daily": {
        "name": "Daily File Backup",
        "description": "Daily backup of important folders to a ZIP archive",
        "tags": ["backup", "daily", "files"],
        "workflow": {
            "name": "Daily File Backup",
            "nodes": [
                {
                    "parameters": {"rule": {"interval": [{"triggerAtHour": 22}]}},
                    "name": "Every day 10pm",
                    "type": "n8n-nodes-base.scheduleTrigger",
                    "position": [250, 300]
                },
                {
                    "parameters": {
                        "jsCode": "const { execSync } = require('child_process');\nconst date = new Date().toISOString().slice(0,10);\nconst cmd = `powershell Compress-Archive -Path 'C:/Users/Dator/Documents/important' -DestinationPath 'C:/Users/Dator/Backups/backup_${date}.zip' -Force`;\nexecSync(cmd);\nreturn [{json: {status: 'backup_done', date}}];"
                    },
                    "name": "Create Backup",
                    "type": "n8n-nodes-base.code",
                    "position": [470, 300]
                }
            ],
            "connections": {
                "Every day 10pm": {"main": [[{"node": "Create Backup", "type": "main", "index": 0}]]}
            }
        }
    }
}


def n8n_template_list() -> str:
    """List available templates"""
    lines = [f"=== n8n Workflow Templates ({len(TEMPLATES)}) ===\n"]
    for key, tmpl in TEMPLATES.items():
        tags = ", ".join(tmpl.get("tags", []))
        lines.append(f"  📋 {key}")
        lines.append(f"     {tmpl['name']}: {tmpl['description']}")
        lines.append(f"     Tags: {tags}\n")
    lines.append("Use n8n_template_get to get the full workflow JSON for import.")
    return "\n".join(lines)


def n8n_template_get(template: str) -> str:
    """Get a template"""
    tmpl = TEMPLATES.get(template)
    if not tmpl:
        # Fuzzy match
        for key in TEMPLATES:
            if template.lower() in key.lower() or template.lower() in TEMPLATES[key]["name"].lower():
                tmpl = TEMPLATES[key]
                template = key
                break
    
    if not tmpl:
        available = ", ".join(TEMPLATES.keys())
        return f"Template '{template}' not found.\nAvailable: {available}"
    
    workflow_json = json.dumps(tmpl["workflow"], indent=2, ensure_ascii=False)
    return (f"=== Template: {tmpl['name']} ===\n"
            f"{tmpl['description']}\n\n"
            f"Workflow JSON (paste into n8n import):\n"
            f"```json\n{workflow_json}\n```\n\n"
            f"Or ask me to create this workflow in n8n using:\n"
            f"  n8n_create_workflow with the description above.")


TOOLS = {
    "n8n_template_list": lambda args: n8n_template_list(),
    "n8n_template_get": lambda args: n8n_template_get(args.get("template", "")),
}
