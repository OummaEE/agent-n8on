"""
Skill: boostcamp_crm
Description: Simple CRM for managing startups, accelerator programs, and investor contacts.
Data stored locally in JSON files in the memory/ directory.
Author: Jane's Agent Builder
"""

import json
import os
import datetime

SKILL_NAME = "boostcamp_crm"
SKILL_VERSION = "1.0"
SKILL_DESCRIPTION = "CRM for BoostCamp — manage startups, programs, investors, and contacts"
SKILL_TOOLS = {
    "crm_add_startup": {
        "description": "Add a startup to the CRM",
        "args": {
            "name": "Startup name",
            "stage": "Stage: idea/mvp/growth/scale",
            "country": "Country",
            "contact": "Contact person name",
            "email": "Contact email",
            "notes": "Additional notes"
        },
        "example": '{"tool": "crm_add_startup", "args": {"name": "TechCo", "stage": "mvp", "country": "Sweden", "contact": "Erik", "email": "erik@techco.se"}}'
    },
    "crm_list_startups": {
        "description": "List all startups in CRM, optionally filtered by stage or country",
        "args": {"filter": "Optional filter: stage name or country"},
        "example": '{"tool": "crm_list_startups", "args": {"filter": "Sweden"}}'
    },
    "crm_add_investor": {
        "description": "Add an investor contact",
        "args": {
            "name": "Investor/fund name",
            "type": "Type: angel/vc/corporate/government",
            "focus": "Investment focus areas",
            "contact": "Contact person",
            "email": "Email",
            "notes": "Notes"
        },
        "example": '{"tool": "crm_add_investor", "args": {"name": "Nordic Fund", "type": "vc", "focus": "SaaS, AI", "contact": "Anna", "email": "anna@nordicfund.se"}}'
    },
    "crm_list_investors": {
        "description": "List all investors, optionally filtered",
        "args": {"filter": "Optional filter"},
        "example": '{"tool": "crm_list_investors", "args": {}}'
    },
    "crm_add_program": {
        "description": "Add an accelerator program",
        "args": {
            "name": "Program name",
            "partner": "Partner organization",
            "startups_count": "Number of startups",
            "status": "Status: planning/active/completed",
            "start_date": "Start date YYYY-MM-DD",
            "notes": "Notes"
        },
        "example": '{"tool": "crm_add_program", "args": {"name": "BoostCamp Nordic Q1", "partner": "Stockholm Innovation", "startups_count": 12, "status": "active"}}'
    },
    "crm_list_programs": {
        "description": "List all accelerator programs",
        "args": {},
        "example": '{"tool": "crm_list_programs", "args": {}}'
    },
    "crm_search": {
        "description": "Search across all CRM data (startups, investors, programs)",
        "args": {"query": "Search text"},
        "example": '{"tool": "crm_search", "args": {"query": "AI"}}'
    },
    "crm_stats": {
        "description": "Show CRM statistics — counts, stages, countries",
        "args": {},
        "example": '{"tool": "crm_stats", "args": {}}'
    }
}

# CRM data file
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRM_FILE = os.path.join(AGENT_DIR, "memory", "crm_data.json")


def _load_crm() -> dict:
    """Load CRM data"""
    try:
        if os.path.exists(CRM_FILE):
            with open(CRM_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {"startups": [], "investors": [], "programs": []}


def _save_crm(data: dict):
    """Save CRM data"""
    os.makedirs(os.path.dirname(CRM_FILE), exist_ok=True)
    with open(CRM_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def crm_add_startup(**kwargs) -> str:
    crm = _load_crm()
    entry = {
        "id": len(crm["startups"]) + 1,
        "name": kwargs.get("name", ""),
        "stage": kwargs.get("stage", "idea"),
        "country": kwargs.get("country", ""),
        "contact": kwargs.get("contact", ""),
        "email": kwargs.get("email", ""),
        "notes": kwargs.get("notes", ""),
        "added": datetime.datetime.now().isoformat()[:19]
    }
    crm["startups"].append(entry)
    _save_crm(crm)
    return f"Startup '{entry['name']}' added (ID: {entry['id']}, stage: {entry['stage']})"


def crm_list_startups(filter_str: str = "") -> str:
    crm = _load_crm()
    startups = crm.get("startups", [])
    
    if filter_str:
        fl = filter_str.lower()
        startups = [s for s in startups if fl in json.dumps(s, ensure_ascii=False).lower()]
    
    if not startups:
        return "No startups found." + (f" (filter: '{filter_str}')" if filter_str else "")
    
    lines = [f"=== Startups ({len(startups)}) ==="]
    for s in startups:
        lines.append(f"  [{s.get('id', '?')}] {s['name']} | {s.get('stage', '?')} | {s.get('country', '?')}")
        if s.get('contact'):
            lines.append(f"      Contact: {s['contact']} <{s.get('email', '')}>")
        if s.get('notes'):
            lines.append(f"      Notes: {s['notes'][:100]}")
    return "\n".join(lines)


def crm_add_investor(**kwargs) -> str:
    crm = _load_crm()
    entry = {
        "id": len(crm["investors"]) + 1,
        "name": kwargs.get("name", ""),
        "type": kwargs.get("type", ""),
        "focus": kwargs.get("focus", ""),
        "contact": kwargs.get("contact", ""),
        "email": kwargs.get("email", ""),
        "notes": kwargs.get("notes", ""),
        "added": datetime.datetime.now().isoformat()[:19]
    }
    crm["investors"].append(entry)
    _save_crm(crm)
    return f"Investor '{entry['name']}' added (ID: {entry['id']}, type: {entry['type']})"


def crm_list_investors(filter_str: str = "") -> str:
    crm = _load_crm()
    investors = crm.get("investors", [])
    
    if filter_str:
        fl = filter_str.lower()
        investors = [i for i in investors if fl in json.dumps(i, ensure_ascii=False).lower()]
    
    if not investors:
        return "No investors found."
    
    lines = [f"=== Investors ({len(investors)}) ==="]
    for inv in investors:
        lines.append(f"  [{inv.get('id', '?')}] {inv['name']} | {inv.get('type', '?')} | Focus: {inv.get('focus', '?')}")
        if inv.get('contact'):
            lines.append(f"      Contact: {inv['contact']} <{inv.get('email', '')}>")
    return "\n".join(lines)


def crm_add_program(**kwargs) -> str:
    crm = _load_crm()
    entry = {
        "id": len(crm["programs"]) + 1,
        "name": kwargs.get("name", ""),
        "partner": kwargs.get("partner", ""),
        "startups_count": kwargs.get("startups_count", 0),
        "status": kwargs.get("status", "planning"),
        "start_date": kwargs.get("start_date", ""),
        "notes": kwargs.get("notes", ""),
        "added": datetime.datetime.now().isoformat()[:19]
    }
    crm["programs"].append(entry)
    _save_crm(crm)
    return f"Program '{entry['name']}' added (ID: {entry['id']}, status: {entry['status']})"


def crm_list_programs() -> str:
    crm = _load_crm()
    programs = crm.get("programs", [])
    
    if not programs:
        return "No programs found."
    
    lines = [f"=== Programs ({len(programs)}) ==="]
    for p in programs:
        lines.append(f"  [{p.get('id', '?')}] {p['name']} | {p.get('status', '?')} | "
                     f"Partner: {p.get('partner', '?')} | Startups: {p.get('startups_count', 0)}")
    return "\n".join(lines)


def crm_search(query: str) -> str:
    crm = _load_crm()
    q = query.lower()
    results = []
    
    for s in crm.get("startups", []):
        if q in json.dumps(s, ensure_ascii=False).lower():
            results.append(f"  [Startup] {s['name']} | {s.get('stage', '')} | {s.get('country', '')}")
    
    for i in crm.get("investors", []):
        if q in json.dumps(i, ensure_ascii=False).lower():
            results.append(f"  [Investor] {i['name']} | {i.get('type', '')} | {i.get('focus', '')}")
    
    for p in crm.get("programs", []):
        if q in json.dumps(p, ensure_ascii=False).lower():
            results.append(f"  [Program] {p['name']} | {p.get('status', '')} | {p.get('partner', '')}")
    
    if not results:
        return f"No results for '{query}'."
    
    return f"=== Search: '{query}' ({len(results)} results) ===\n" + "\n".join(results)


def crm_stats() -> str:
    crm = _load_crm()
    startups = crm.get("startups", [])
    investors = crm.get("investors", [])
    programs = crm.get("programs", [])
    
    lines = ["=== CRM Statistics ==="]
    lines.append(f"Startups: {len(startups)}")
    lines.append(f"Investors: {len(investors)}")
    lines.append(f"Programs: {len(programs)}")
    
    if startups:
        stages = {}
        countries = {}
        for s in startups:
            stages[s.get('stage', 'unknown')] = stages.get(s.get('stage', 'unknown'), 0) + 1
            countries[s.get('country', 'unknown')] = countries.get(s.get('country', 'unknown'), 0) + 1
        lines.append(f"\nStartup stages: {', '.join(f'{k}:{v}' for k, v in stages.items())}")
        lines.append(f"Countries: {', '.join(f'{k}:{v}' for k, v in countries.items())}")
    
    if programs:
        statuses = {}
        for p in programs:
            statuses[p.get('status', 'unknown')] = statuses.get(p.get('status', 'unknown'), 0) + 1
        lines.append(f"\nProgram statuses: {', '.join(f'{k}:{v}' for k, v in statuses.items())}")
    
    return "\n".join(lines)


TOOLS = {
    "crm_add_startup": lambda args: crm_add_startup(**args),
    "crm_list_startups": lambda args: crm_list_startups(args.get("filter", "")),
    "crm_add_investor": lambda args: crm_add_investor(**args),
    "crm_list_investors": lambda args: crm_list_investors(args.get("filter", "")),
    "crm_add_program": lambda args: crm_add_program(**args),
    "crm_list_programs": lambda args: crm_list_programs(),
    "crm_search": lambda args: crm_search(args.get("query", "")),
    "crm_stats": lambda args: crm_stats(),
}
