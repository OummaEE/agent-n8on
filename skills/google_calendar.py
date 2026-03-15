"""
Skill: google_calendar
Description: Manage Google Calendar — list, create, delete events.
Requires: GOOGLE_CALENDAR_ID and GOOGLE_API_KEY in .env
Note: For full write access, requires OAuth2 setup (service account or user token).
      For read-only with API key, only public calendars work.
      Best approach: use Google Apps Script webhook + n8n for full integration.
Author: Jane's Agent Builder
"""

SKILL_NAME = "google_calendar"
SKILL_VERSION = "1.0"
SKILL_DESCRIPTION = "Manage Google Calendar - list events, create events, check schedule"
SKILL_TOOLS = {
    "calendar_today": {
        "description": "Show today's events from Google Calendar",
        "args": {},
        "example": '{"tool": "calendar_today", "args": {}}'
    },
    "calendar_week": {
        "description": "Show this week's events",
        "args": {},
        "example": '{"tool": "calendar_week", "args": {}}'
    },
    "calendar_create": {
        "description": "Create a new calendar event",
        "args": {
            "title": "Event title",
            "date": "Date in YYYY-MM-DD format",
            "time": "Start time HH:MM (24h format)",
            "duration": "Duration in minutes (default 60)",
            "description": "Event description (optional)"
        },
        "example": '{"tool": "calendar_create", "args": {"title": "Meeting with investors", "date": "2026-02-15", "time": "10:00", "duration": 60}}'
    }
}


def _load_calendar_config():
    """Load Google Calendar config from .env"""
    import os
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


def _get_events(time_min: str, time_max: str) -> list:
    """Fetch events from Google Calendar API"""
    import requests
    config = _load_calendar_config()
    
    cal_id = config.get('GOOGLE_CALENDAR_ID', '')
    api_key = config.get('GOOGLE_API_KEY', '')
    
    if not cal_id or not api_key:
        return None  # Signal that config is missing
    
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
    params = {
        "key": api_key,
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": 50
    }
    
    resp = requests.get(url, params=params, timeout=10)
    if resp.status_code == 200:
        return resp.json().get("items", [])
    else:
        return []


def _format_events(events: list, period: str) -> str:
    """Format events for display"""
    if events is None:
        return ("Google Calendar not configured.\n"
                "Add to .env file next to agent_v3.py:\n"
                "  GOOGLE_CALENDAR_ID=your-calendar-id@gmail.com\n"
                "  GOOGLE_API_KEY=your-api-key\n\n"
                "To get API key: https://console.cloud.google.com/apis/credentials\n"
                "Enable 'Google Calendar API' in your project.\n"
                "Calendar ID: found in Google Calendar Settings > Integrate Calendar.")
    
    if not events:
        return f"No events for {period}."
    
    lines = [f"📅 Events for {period} ({len(events)} total):"]
    for ev in events:
        start = ev.get("start", {})
        dt = start.get("dateTime", start.get("date", ""))
        summary = ev.get("summary", "No title")
        
        # Format time
        if "T" in dt:
            time_str = dt[11:16]
            lines.append(f"  {time_str} — {summary}")
        else:
            lines.append(f"  All day — {summary}")
        
        desc = ev.get("description", "")
        if desc:
            lines.append(f"          {desc[:80]}")
    
    return "\n".join(lines)


def calendar_today() -> str:
    """Show today's events"""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    time_min = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
    time_max = now.replace(hour=23, minute=59, second=59).isoformat() + "Z"
    events = _get_events(time_min, time_max)
    return _format_events(events, "today")


def calendar_week() -> str:
    """Show this week's events"""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    start = now - timedelta(days=now.weekday())
    start = start.replace(hour=0, minute=0, second=0)
    end = start + timedelta(days=7)
    
    time_min = start.isoformat() + "Z"
    time_max = end.isoformat() + "Z"
    events = _get_events(time_min, time_max)
    return _format_events(events, "this week")


def calendar_create(title: str, date: str, time: str = "09:00",
                    duration: int = 60, description: str = "") -> str:
    """Create a calendar event (requires OAuth2 or service account)"""
    config = _load_calendar_config()
    cal_id = config.get('GOOGLE_CALENDAR_ID', '')
    token = config.get('GOOGLE_OAUTH_TOKEN', '')
    
    if not token:
        # Can't create events with just API key — need OAuth
        return (f"Event planned: '{title}' on {date} at {time} ({duration} min)\n\n"
                f"To auto-create events in Google Calendar, you need OAuth2 setup.\n"
                f"Alternative: I can create an n8n workflow that manages your calendar.\n"
                f"Ask me: 'create n8n workflow to add event to Google Calendar'")
    
    # If we have OAuth token, create directly
    import requests
    from datetime import datetime, timedelta
    
    start_dt = f"{date}T{time}:00"
    end_minutes = int(duration)
    start_obj = datetime.fromisoformat(start_dt)
    end_obj = start_obj + timedelta(minutes=end_minutes)
    
    event_body = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_dt + "+01:00", "timeZone": "Europe/Stockholm"},
        "end": {"dateTime": end_obj.isoformat() + "+01:00", "timeZone": "Europe/Stockholm"}
    }
    
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    resp = requests.post(url, json=event_body, headers=headers, timeout=10)
    if resp.status_code in (200, 201):
        ev = resp.json()
        return f"Event created: '{title}' on {date} at {time}\nLink: {ev.get('htmlLink', '')}"
    else:
        return f"Error creating event: {resp.status_code} — {resp.text[:200]}"


TOOLS = {
    "calendar_today": lambda args: calendar_today(),
    "calendar_week": lambda args: calendar_week(),
    "calendar_create": lambda args: calendar_create(
        args.get("title", ""), args.get("date", ""),
        args.get("time", "09:00"), args.get("duration", 60),
        args.get("description", "")
    ),
}
