from typing import Any, Callable, Dict, List, Optional


def _manual_trigger() -> Dict[str, Any]:
    return {
        "id": "node-trigger",
        "name": "Manual Trigger",
        "type": "n8n-nodes-base.manualTrigger",
        "typeVersion": 1,
        "position": [240, 300],
        "parameters": {},
    }


def _schedule_trigger(cadence: str) -> Dict[str, Any]:
    return {
        "id": "node-trigger",
        "name": "Schedule Trigger",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [240, 300],
        "parameters": {"rule": {"interval": [{"field": cadence or "day"}]}},
    }


def _webhook_trigger(path_hint: str) -> Dict[str, Any]:
    safe = (path_hint or "workflow").lower().replace(" ", "-")
    return {
        "id": "node-trigger",
        "name": "Webhook Trigger",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 1,
        "position": [240, 300],
        "parameters": {"httpMethod": "POST", "path": f"{safe}-hook"},
    }


def _pick_trigger(params: Dict[str, Any], workflow_name: str) -> Dict[str, Any]:
    trigger_type = str(params.get("trigger_type", "manual")).lower()
    if trigger_type == "schedule":
        return _schedule_trigger(str(params.get("cadence", "day")).lower())
    if trigger_type == "webhook":
        return _webhook_trigger(workflow_name)
    return _manual_trigger()


def _linear_workflow(workflow_name: str, trigger: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    full_nodes: List[Dict[str, Any]] = [trigger]
    x = 520
    idx = 1
    for n in nodes:
        node = dict(n)
        node["id"] = node.get("id", f"node-{idx}")
        node["position"] = [x, 300]
        full_nodes.append(node)
        x += 250
        idx += 1

    connections: Dict[str, Any] = {}
    prev = trigger["name"]
    for n in full_nodes[1:]:
        connections[prev] = {"main": [[{"node": n["name"], "type": "main", "index": 0}]]}
        prev = n["name"]

    return {
        "name": workflow_name,
        "nodes": full_nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }


def _credential(name: str) -> Dict[str, Any]:
    return {"name": name}


def _build_content_factory(workflow_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    trigger = _pick_trigger(params, workflow_name)
    nodes = [
        {
            "name": "Fetch Topics",
            "type": "n8n-nodes-base.googleSheets",
            "typeVersion": 4.5,
            "parameters": {
                "documentId": params["sheet_id"],
                "range": params["sheet_range"],
            },
            "credentials": {"googleSheetsOAuth2Api": _credential(params["google_sheets_credential"])},
        },
        {
            "name": "Generate Text",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "parameters": {
                "url": params.get("generation_endpoint", "http://localhost:5000/api/generate"),
                "method": "POST",
            },
        },
        {
            "name": "Optional Image",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "parameters": {
                "url": params.get("image_endpoint", "http://localhost:5000/api/image"),
                "method": "POST",
            },
        },
        {
            "name": "Save To Notion",
            "type": "n8n-nodes-base.notion",
            "typeVersion": 2,
            "parameters": {"databaseId": params["notion_db_id"]},
            "credentials": {"notionApi": _credential(params["notion_credential"])},
        },
        {
            "name": "Notify Telegram",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "parameters": {
                "text": f"Content factory done ({params.get('language', 'en')})",
                "chatId": params.get("telegram_chat_id", ""),
            },
            "credentials": {"telegramApi": _credential(params["telegram_credential"])},
        },
    ]
    return _linear_workflow(workflow_name, trigger, nodes)


def _build_web_parser(workflow_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    trigger = _pick_trigger(params, workflow_name)
    nodes = [
        {"name": "Fetch Page", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "parameters": {"url": params["source_url"], "method": "GET"}},
        {"name": "Extract HTML", "type": "n8n-nodes-base.htmlExtract", "typeVersion": 1.1, "parameters": {}},
        {"name": "Transform", "type": "n8n-nodes-base.set", "typeVersion": 3.4, "parameters": {"assignments": {"assignments": []}}},
        {
            "name": "Save Result",
            "type": "n8n-nodes-base.googleSheets",
            "typeVersion": 4.5,
            "parameters": {"documentId": params["sheet_id"], "range": params.get("sheet_range", "A:C")},
            "credentials": {"googleSheetsOAuth2Api": _credential(params["google_sheets_credential"])},
        },
        {
            "name": "Notify Telegram",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "parameters": {"text": "Parser pipeline completed", "chatId": params.get("telegram_chat_id", "")},
            "credentials": {"telegramApi": _credential(params["telegram_credential"])},
        },
    ]
    return _linear_workflow(workflow_name, trigger, nodes)


def _build_inbox_organizer(workflow_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    trigger = _pick_trigger(params, workflow_name)
    nodes = [
        {
            "name": "Search Unread",
            "type": "n8n-nodes-base.gmail",
            "typeVersion": 2.1,
            "parameters": {"operation": "getAll"},
            "credentials": {"gmailOAuth2": _credential(params["gmail_credential"])},
        },
        {"name": "Classify Mail", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "parameters": {"url": params.get("classification_endpoint", "http://localhost:5000/api/classify"), "method": "POST"}},
        {
            "name": "Apply Label",
            "type": "n8n-nodes-base.gmail",
            "typeVersion": 2.1,
            "parameters": {"operation": "addLabel", "labelIds": params.get("label_name", "AI-Processed")},
            "credentials": {"gmailOAuth2": _credential(params["gmail_credential"])},
        },
        {
            "name": "Notify Telegram",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "parameters": {"text": "Inbox organizer done", "chatId": params.get("telegram_chat_id", "")},
            "credentials": {"telegramApi": _credential(params["telegram_credential"])},
        },
    ]
    return _linear_workflow(workflow_name, trigger, nodes)


def _build_comment_responder(workflow_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    trigger = _pick_trigger(params, workflow_name)
    nodes = [
        {"name": "Fetch Comments", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "parameters": {"url": params["post_url"], "method": "GET"}},
        {"name": "Keyword Filter", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "parameters": {"conditions": {"string": [{"value1": "={{$json.text}}", "operation": "contains", "value2": params["keyword"]}]}}},
        {"name": "Reply Comment", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "parameters": {"url": params["reply_endpoint"], "method": "POST"}},
        {
            "name": "Log Sheet",
            "type": "n8n-nodes-base.googleSheets",
            "typeVersion": 4.5,
            "parameters": {"documentId": params["sheet_id"], "range": params.get("sheet_range", "A:D")},
            "credentials": {"googleSheetsOAuth2Api": _credential(params["google_sheets_credential"])},
        },
        {
            "name": "Notify Telegram",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "parameters": {"text": "Comment responder done", "chatId": params.get("telegram_chat_id", "")},
            "credentials": {"telegramApi": _credential(params["telegram_credential"])},
        },
    ]
    return _linear_workflow(workflow_name, trigger, nodes)


def _build_lead_capture(workflow_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    trigger = _pick_trigger(params, workflow_name)
    nodes = [
        {"name": "Validate Payload", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "parameters": {}},
        {
            "name": "Store CRM",
            "type": "n8n-nodes-base.googleSheets",
            "typeVersion": 4.5,
            "parameters": {"documentId": params["crm_sheet_id"], "range": params.get("sheet_range", "A:F")},
            "credentials": {"googleSheetsOAuth2Api": _credential(params["google_sheets_credential"])},
        },
        {
            "name": "Followup Email",
            "type": "n8n-nodes-base.gmail",
            "typeVersion": 2.1,
            "parameters": {"operation": "send", "fromEmail": params["followup_email_from"]},
            "credentials": {"gmailOAuth2": _credential(params["gmail_credential"])},
        },
        {
            "name": "Notify Telegram",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "parameters": {"text": "Lead captured", "chatId": params.get("telegram_chat_id", "")},
            "credentials": {"telegramApi": _credential(params["telegram_credential"])},
        },
    ]
    return _linear_workflow(workflow_name, trigger, nodes)


def _build_file_cleanup(workflow_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    trigger = _pick_trigger(params, workflow_name)
    nodes = [
        {"name": "Cleanup Endpoint", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "parameters": {"url": params.get("cleanup_endpoint", "http://localhost:5000/api/clean_duplicates"), "method": "POST"}},
        {"name": "Format Log", "type": "n8n-nodes-base.set", "typeVersion": 3.4, "parameters": {"assignments": {"assignments": []}}},
        {
            "name": "Notify Telegram",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "parameters": {"text": "Cleanup pipeline done", "chatId": params.get("telegram_chat_id", "")},
            "credentials": {"telegramApi": _credential(params["telegram_credential"])},
        },
    ]
    return _linear_workflow(workflow_name, trigger, nodes)


def _build_pdf_analyzer(workflow_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    trigger = _pick_trigger(params, workflow_name)
    nodes = [
        {
            "name": "Download PDF",
            "type": "n8n-nodes-base.googleDrive",
            "typeVersion": 3,
            "parameters": {"resource": "file", "operation": "download", "fileId": params["drive_folder_id"]},
            "credentials": {"googleDriveOAuth2Api": _credential(params["google_drive_credential"])},
        },
        {"name": "Extract Text", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "parameters": {"url": params.get("extract_endpoint", "http://localhost:5000/api/pdf/extract"), "method": "POST"}},
        {"name": "Summarize", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "parameters": {"url": params.get("summary_endpoint", "http://localhost:5000/api/summarize"), "method": "POST"}},
        {
            "name": "Save Summary",
            "type": "n8n-nodes-base.googleDrive",
            "typeVersion": 3,
            "parameters": {"resource": "file", "operation": "upload"},
            "credentials": {"googleDriveOAuth2Api": _credential(params["google_drive_credential"])},
        },
    ]
    return _linear_workflow(workflow_name, trigger, nodes)


def _build_municipality_scraper(workflow_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    trigger = _pick_trigger(params, workflow_name)
    nodes = [
        {"name": "Fetch Kommun Site", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "parameters": {"url": params["source_url"], "method": "GET"}},
        {"name": "Extract Contacts", "type": "n8n-nodes-base.htmlExtract", "typeVersion": 1.1, "parameters": {}},
        {
            "name": "Save Contacts",
            "type": "n8n-nodes-base.googleSheets",
            "typeVersion": 4.5,
            "parameters": {"documentId": params["sheet_id"], "range": params.get("sheet_range", "A:E")},
            "credentials": {"googleSheetsOAuth2Api": _credential(params["google_sheets_credential"])},
        },
        {
            "name": "Notify Telegram",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "parameters": {"text": "Municipality scrape done", "chatId": params.get("telegram_chat_id", "")},
            "credentials": {"telegramApi": _credential(params["telegram_credential"])},
        },
    ]
    return _linear_workflow(workflow_name, trigger, nodes)


RECIPE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "content_factory": {
        "name": "Content Factory",
        "keywords": ["content factory", "content-zavod", "контент-завод", "контент завод", "innehall", "innehåll", "content producer"],
        "required_params": ["sheet_id", "sheet_range", "notion_db_id", "notion_credential"],
        "optional_params": {
            "trigger_type": "schedule",
            "cadence": "day",
            "language": "en",
            "target_platforms": "instagram,facebook",
            "google_sheets_credential": "google_sheets_default",
            "telegram_credential": "telegram_default",
        },
        "builder": _build_content_factory,
        "missing_questions": {
            "sheet_id": "Какой Google Sheet ID использовать?",
            "sheet_range": "Какой диапазон Google Sheet (например A:A)?",
            "notion_db_id": "Укажи Notion database ID.",
            "notion_credential": "Как называется credential для Notion в n8n?",
        },
    },
    "web_page_parser": {
        "name": "Web Page Parser",
        "keywords": ["web page parser", "page parser", "парсер страницы", "парсер", "skrapa sida", "scrape page"],
        "required_params": ["source_url", "sheet_id", "google_sheets_credential", "telegram_credential"],
        "optional_params": {"trigger_type": "webhook", "sheet_range": "A:C"},
        "builder": _build_web_parser,
        "missing_questions": {
            "source_url": "Какой URL нужно парсить?",
            "sheet_id": "Куда сохранять результаты: Google Sheet ID?",
            "google_sheets_credential": "Как называется credential для Google Sheets в n8n?",
            "telegram_credential": "Как называется Telegram credential в n8n?",
        },
    },
    "inbox_organizer": {
        "name": "Inbox Organizer",
        "keywords": ["inbox organizer", "organize inbox", "organize gmail", "организуй почту", "inkorg", "gmail organizer"],
        "required_params": ["gmail_credential", "telegram_credential"],
        "optional_params": {"trigger_type": "schedule", "cadence": "day", "label_name": "AI-Processed"},
        "builder": _build_inbox_organizer,
        "missing_questions": {
            "gmail_credential": "Какой Gmail credential использовать?",
            "telegram_credential": "Как называется Telegram credential в n8n?",
        },
    },
    "comment_keyword_responder": {
        "name": "Comment Keyword Responder",
        "keywords": ["comment responder", "keyword responder", "ответ на комментарии", "комментар", "kommentar", "keyword comment"],
        "required_params": ["post_url", "keyword", "reply_endpoint", "sheet_id", "google_sheets_credential", "telegram_credential"],
        "optional_params": {"trigger_type": "schedule", "sheet_range": "A:D"},
        "builder": _build_comment_responder,
        "missing_questions": {
            "post_url": "Какой URL/ID поста нужно отслеживать?",
            "keyword": "Какое ключевое слово искать в комментариях?",
            "reply_endpoint": "Какой endpoint использовать для ответа на комментарий?",
            "sheet_id": "Куда логировать ответы: Google Sheet ID?",
            "google_sheets_credential": "Как называется credential для Google Sheets в n8n?",
            "telegram_credential": "Как называется Telegram credential в n8n?",
        },
    },
    "lead_capture_crm": {
        "name": "Lead Capture + CRM",
        "keywords": ["lead capture", "crm", "лиды", "lead form", "lead pipeline"],
        "required_params": ["crm_sheet_id", "google_sheets_credential", "followup_email_from", "gmail_credential", "telegram_credential"],
        "optional_params": {"trigger_type": "webhook", "sheet_range": "A:F"},
        "builder": _build_lead_capture,
        "missing_questions": {
            "crm_sheet_id": "Какой Google Sheet ID использовать как CRM?",
            "google_sheets_credential": "Как называется credential для Google Sheets в n8n?",
            "followup_email_from": "С какого email отправлять follow-up?",
            "gmail_credential": "Какой Gmail credential использовать?",
            "telegram_credential": "Как называется Telegram credential в n8n?",
        },
    },
    "file_cleanup_pipeline": {
        "name": "File Cleanup Pipeline",
        "keywords": ["file cleanup", "clean duplicates", "очистка файлов", "дубликаты файлов", "stada filer"],
        "required_params": ["target_path", "telegram_credential"],
        "optional_params": {"trigger_type": "schedule", "cadence": "day", "cleanup_endpoint": "http://localhost:5000/api/clean_duplicates"},
        "builder": _build_file_cleanup,
        "missing_questions": {
            "target_path": "Какой путь нужно очищать от дублей?",
            "telegram_credential": "Как называется Telegram credential в n8n?",
        },
    },
    "pdf_analyzer_pipeline": {
        "name": "PDF Analyzer Pipeline",
        "keywords": ["pdf analyzer", "pdf pipeline", "анализ pdf", "pdf analys"],
        "required_params": ["drive_folder_id", "google_drive_credential"],
        "optional_params": {"trigger_type": "schedule", "cadence": "day"},
        "builder": _build_pdf_analyzer,
        "missing_questions": {
            "drive_folder_id": "Какой Drive folder/file ID использовать как источник?",
            "google_drive_credential": "Как называется credential для Google Drive в n8n?",
        },
    },
    "municipality_scraping_pipeline": {
        "name": "Municipality Scraping Pipeline",
        "keywords": ["municipality scraping", "kommun scraping", "kommun", "муниципал", "kommun kontakt"],
        "required_params": ["source_url", "sheet_id", "google_sheets_credential", "telegram_credential"],
        "optional_params": {"trigger_type": "schedule", "cadence": "week", "sheet_range": "A:E"},
        "builder": _build_municipality_scraper,
        "missing_questions": {
            "source_url": "Какой сайт kommun/municipality нужно парсить?",
            "sheet_id": "Куда сохранять контакты: Google Sheet ID?",
            "google_sheets_credential": "Как называется credential для Google Sheets в n8n?",
            "telegram_credential": "Как называется Telegram credential в n8n?",
        },
    },
}


def select_recipe(user_text: str) -> Optional[str]:
    text = (user_text or "").lower()
    for key, recipe in RECIPE_REGISTRY.items():
        for kw in recipe.get("keywords", []):
            if kw in text:
                return key
    return None


def resolve_recipe(recipe_key: str) -> Optional[Dict[str, Any]]:
    return RECIPE_REGISTRY.get(recipe_key)


def apply_recipe_defaults(recipe_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
    recipe = resolve_recipe(recipe_key)
    if not recipe:
        return dict(params or {})
    out = dict(recipe.get("optional_params", {}))
    out.update(params or {})
    return out


def validate_recipe_params(recipe_key: str, params: Dict[str, Any]) -> List[str]:
    recipe = resolve_recipe(recipe_key)
    if not recipe:
        return ["recipe_key"]
    required = recipe.get("required_params", [])
    return [k for k in required if not params.get(k)]


def get_missing_param_questions(recipe_key: str, missing_keys: List[str]) -> List[str]:
    recipe = resolve_recipe(recipe_key) or {}
    questions = recipe.get("missing_questions", {})
    return [questions.get(k, f"Please provide: {k}") for k in missing_keys]


def build_recipe_workflow(recipe_key: str, workflow_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    recipe = resolve_recipe(recipe_key)
    if not recipe:
        raise ValueError(f"Unknown recipe: {recipe_key}")
    builder: Callable[[str, Dict[str, Any]], Dict[str, Any]] = recipe["builder"]
    return builder(workflow_name, params or {})
