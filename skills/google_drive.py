"""
Skill: google_drive
Description: Upload, list, and share files on Google Drive.
Uses Google Drive API v3 with service account or OAuth token.

Setup options (in .env):

Option A — Service Account (easiest, recommended):
  1. Go to https://console.cloud.google.com/
  2. Create project, enable Google Drive API
  3. Create Service Account, download JSON key
  4. Save the key file, add path to .env:
     GOOGLE_DRIVE_SERVICE_ACCOUNT=C:/path/to/service-account.json
  5. Share a Google Drive folder with the service account email

Option B — OAuth Token (for personal Drive):
  GOOGLE_DRIVE_TOKEN=your-oauth-access-token
  (You'll need to refresh this periodically)

Option C — API Key (read-only, public files only):
  GOOGLE_DRIVE_API_KEY=your-api-key

Author: Jane's Agent Builder
"""

import json
import os
import mimetypes

SKILL_NAME = "google_drive"
SKILL_VERSION = "1.0"
SKILL_DESCRIPTION = "Upload, list, and share files on Google Drive"
SKILL_TOOLS = {
    "gdrive_upload": {
        "description": "Upload a file to Google Drive",
        "args": {
            "path": "Local file path to upload",
            "folder_id": "Google Drive folder ID (optional, uploads to root if empty)",
            "share": "Make file shareable via link (true/false, default false)"
        },
        "example": '{"tool": "gdrive_upload", "args": {"path": "C:/Users/Dator/Desktop/report.xlsx", "share": true}}'
    },
    "gdrive_list": {
        "description": "List files in Google Drive (root or specific folder)",
        "args": {
            "folder_id": "Folder ID (optional, lists root)",
            "query": "Search query (optional, e.g. 'report')"
        },
        "example": '{"tool": "gdrive_list", "args": {"query": "report"}}'
    },
    "gdrive_share": {
        "description": "Share a Google Drive file — get a public link",
        "args": {
            "file_id": "Google Drive file ID",
            "email": "Optional: share with specific email"
        },
        "example": '{"tool": "gdrive_share", "args": {"file_id": "1abc...", "email": "colleague@gmail.com"}}'
    },
    "gdrive_status": {
        "description": "Check Google Drive connection and configuration",
        "args": {},
        "example": '{"tool": "gdrive_status", "args": {}}'
    }
}


def _load_drive_config():
    """Load Google Drive config from .env"""
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


def _get_access_token():
    """Get access token from service account or direct token"""
    config = _load_drive_config()

    # Option A: Service account JSON
    sa_path = config.get("GOOGLE_DRIVE_SERVICE_ACCOUNT", "")
    if sa_path and os.path.exists(sa_path):
        try:
            import jwt  # PyJWT
            import time as _time

            with open(sa_path, 'r') as f:
                sa = json.load(f)

            now = int(_time.time())
            payload = {
                "iss": sa["client_email"],
                "scope": "https://www.googleapis.com/auth/drive",
                "aud": "https://oauth2.googleapis.com/token",
                "iat": now,
                "exp": now + 3600
            }
            signed = jwt.encode(payload, sa["private_key"], algorithm="RS256")

            import requests
            resp = requests.post("https://oauth2.googleapis.com/token", data={
                "grant_type": "urn:ietf:params:oauth:grant_type:jwt-bearer",
                "assertion": signed
            }, timeout=10)

            if resp.status_code == 200:
                return resp.json().get("access_token")
            return None
        except ImportError:
            return None  # PyJWT not installed
        except Exception:
            return None

    # Option B: Direct OAuth token
    token = config.get("GOOGLE_DRIVE_TOKEN", "")
    if token:
        return token

    return None


def _setup_instructions():
    """Return setup instructions"""
    return (
        "Google Drive not configured.\n\n"
        "=== Quick Setup (Service Account) ===\n"
        "1. Go to https://console.cloud.google.com/\n"
        "2. Create project -> Enable 'Google Drive API'\n"
        "3. Create Service Account -> Download JSON key\n"
        "4. Add to .env:\n"
        "   GOOGLE_DRIVE_SERVICE_ACCOUNT=C:/path/to/service-account.json\n"
        "5. Share your Google Drive folder with the service account email\n\n"
        "=== Alternative: Direct Token ===\n"
        "Add to .env:\n"
        "   GOOGLE_DRIVE_TOKEN=ya29.your-oauth-token\n"
        "(Get from https://developers.google.com/oauthplayground)\n\n"
        "=== Alternative: n8n Workflow ===\n"
        "Create n8n workflow to upload files to Drive automatically.\n"
        "Ask: 'create n8n workflow to upload files to Google Drive'"
    )


def gdrive_upload(path: str, folder_id: str = "", share: bool = False) -> str:
    """Upload a file to Google Drive"""
    if not os.path.exists(path):
        return f"File not found: {path}"

    token = _get_access_token()
    if not token:
        return _setup_instructions()

    import requests

    file_name = os.path.basename(path)
    mime_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    file_size = os.path.getsize(path)

    # Metadata
    metadata = {"name": file_name}
    if folder_id:
        metadata["parents"] = [folder_id]

    headers = {"Authorization": f"Bearer {token}"}

    try:
        # For files under 5MB, use simple upload
        if file_size < 5 * 1024 * 1024:
            url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"

            import io
            boundary = "===boundary==="
            body = io.BytesIO()

            # Part 1: metadata
            body.write(f"--{boundary}\r\n".encode())
            body.write(b"Content-Type: application/json; charset=UTF-8\r\n\r\n")
            body.write(json.dumps(metadata).encode())
            body.write(b"\r\n")

            # Part 2: file
            body.write(f"--{boundary}\r\n".encode())
            body.write(f"Content-Type: {mime_type}\r\n\r\n".encode())
            with open(path, 'rb') as f:
                body.write(f.read())
            body.write(f"\r\n--{boundary}--\r\n".encode())

            headers["Content-Type"] = f"multipart/related; boundary={boundary}"
            resp = requests.post(url, headers=headers, data=body.getvalue(), timeout=60)

        else:
            # Resumable upload for larger files
            url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable"
            headers["Content-Type"] = "application/json"
            init_resp = requests.post(url, headers=headers,
                                      json=metadata, timeout=30)

            if init_resp.status_code != 200:
                return f"Upload init failed: {init_resp.status_code} — {init_resp.text[:200]}"

            upload_url = init_resp.headers.get("Location")
            with open(path, 'rb') as f:
                resp = requests.put(upload_url, data=f,
                                    headers={"Content-Type": mime_type,
                                             "Content-Length": str(file_size)},
                                    timeout=300)

        if resp.status_code in (200, 201):
            file_data = resp.json()
            file_id = file_data.get("id", "")
            result = (f"Uploaded: {file_name} ({file_size / 1024:.1f} KB)\n"
                      f"File ID: {file_id}")

            # Share if requested
            if share and file_id:
                share_result = gdrive_share(file_id)
                result += f"\n{share_result}"

            return result
        else:
            return f"Upload failed: {resp.status_code} — {resp.text[:300]}"

    except Exception as e:
        return f"Upload error: {e}"


def gdrive_list(folder_id: str = "", query: str = "") -> str:
    """List files in Google Drive"""
    token = _get_access_token()
    if not token:
        return _setup_instructions()

    import requests

    params = {
        "pageSize": 30,
        "fields": "files(id,name,mimeType,size,modifiedTime,webViewLink)",
        "orderBy": "modifiedTime desc"
    }

    # Build query
    q_parts = ["trashed = false"]
    if folder_id:
        q_parts.append(f"'{folder_id}' in parents")
    if query:
        q_parts.append(f"name contains '{query}'")
    params["q"] = " and ".join(q_parts)

    headers = {"Authorization": f"Bearer {token}"}

    try:
        resp = requests.get("https://www.googleapis.com/drive/v3/files",
                            headers=headers, params=params, timeout=15)

        if resp.status_code != 200:
            return f"Error: {resp.status_code} — {resp.text[:200]}"

        files = resp.json().get("files", [])
        if not files:
            return "No files found." + (f" (query: '{query}')" if query else "")

        lines = [f"=== Google Drive ({len(files)} files) ==="]
        for f in files:
            size = f.get("size", "")
            size_str = f"{int(size) / 1024:.1f} KB" if size else "folder"
            date = f.get("modifiedTime", "")[:10]
            name = f.get("name", "?")
            fid = f.get("id", "")
            link = f.get("webViewLink", "")

            is_folder = f.get("mimeType") == "application/vnd.google-apps.folder"
            icon = "[D]" if is_folder else "   "
            lines.append(f"  {icon} {name} | {size_str} | {date}")
            lines.append(f"       ID: {fid}")
            if link:
                lines.append(f"       Link: {link}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error listing files: {e}"


def gdrive_share(file_id: str, email: str = "") -> str:
    """Share a file — make public link or share with specific email"""
    token = _get_access_token()
    if not token:
        return _setup_instructions()

    import requests
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        if email:
            # Share with specific user
            data = {
                "role": "reader",
                "type": "user",
                "emailAddress": email
            }
            resp = requests.post(
                f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
                headers=headers, json=data, timeout=10
            )
        else:
            # Make publicly accessible via link
            data = {
                "role": "reader",
                "type": "anyone"
            }
            resp = requests.post(
                f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
                headers=headers, json=data, timeout=10
            )

        if resp.status_code in (200, 201):
            link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
            if email:
                return f"Shared with {email}\nLink: {link}"
            return f"Public link created:\n{link}"
        else:
            return f"Error sharing: {resp.status_code} — {resp.text[:200]}"

    except Exception as e:
        return f"Error sharing: {e}"


def gdrive_status() -> str:
    """Check Google Drive status"""
    config = _load_drive_config()
    lines = ["=== Google Drive Status ==="]

    sa_path = config.get("GOOGLE_DRIVE_SERVICE_ACCOUNT", "")
    token = config.get("GOOGLE_DRIVE_TOKEN", "")

    if sa_path:
        if os.path.exists(sa_path):
            lines.append(f"Auth: Service Account (file found)")
            try:
                with open(sa_path) as f:
                    sa = json.load(f)
                lines.append(f"  Email: {sa.get('client_email', '?')}")
                lines.append(f"  Project: {sa.get('project_id', '?')}")
            except:
                lines.append(f"  Error reading service account file")

            # Test connection
            t = _get_access_token()
            if t:
                lines.append(f"  Token: OK (obtained successfully)")
            else:
                lines.append(f"  Token: FAILED")
                lines.append(f"  Check: pip install PyJWT")
        else:
            lines.append(f"Auth: Service Account path configured but file not found")
            lines.append(f"  Path: {sa_path}")
    elif token:
        lines.append(f"Auth: Direct OAuth token (may expire)")
        lines.append(f"  Token: {token[:20]}...")
    else:
        lines.append(f"Auth: Not configured")
        lines.append(f"\n{_setup_instructions()}")

    # Check PyJWT
    try:
        import jwt
        lines.append(f"PyJWT: installed")
    except ImportError:
        lines.append(f"PyJWT: not installed (needed for service account)")
        lines.append(f"  Install: pip install PyJWT")

    return "\n".join(lines)


TOOLS = {
    "gdrive_upload": lambda args: gdrive_upload(
        args.get("path", ""), args.get("folder_id", ""),
        args.get("share", False)
    ),
    "gdrive_list": lambda args: gdrive_list(
        args.get("folder_id", ""), args.get("query", "")
    ),
    "gdrive_share": lambda args: gdrive_share(
        args.get("file_id", ""), args.get("email", "")
    ),
    "gdrive_status": lambda args: gdrive_status(),
}
