"""
Gmail API wrapper.

Handles OAuth2 authentication and email fetching.
Parsed emails are plain Python dicts so the rest of the pipeline
has zero dependency on the Google SDK types.
"""
import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

_CREDS_PATH_ENV = os.getenv("GMAIL_CREDENTIALS_PATH")
CREDENTIALS_PATH = Path(_CREDS_PATH_ENV) if _CREDS_PATH_ENV else (
    Path(__file__).parent / "credentials" / "credentials.json"
)
TOKEN_PATH = Path(__file__).parent / "credentials" / "token.json"
FLOW_STATE_PATH = Path(__file__).parent / "credentials" / ".flow_state.json"
AUTH_REDIRECT_URI = "http://localhost:8000/auth/callback"


class GmailFetcher:
    def __init__(self):
        self._service = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def is_authenticated(self) -> bool:
        return self._get_valid_creds() is not None

    def _get_valid_creds(self) -> Optional[Credentials]:
        if not TOKEN_PATH.exists():
            return None
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json())
                return creds
            except Exception:
                pass
        return None

    def get_auth_url(self) -> str:
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(
                f"credentials.json not found at {CREDENTIALS_PATH}\n"
                "Download it from Google Cloud Console > APIs & Services > Credentials."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_PATH), SCOPES, redirect_uri=AUTH_REDIRECT_URI
        )
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        # Persist flow state so the callback handler can reconstruct it
        FLOW_STATE_PATH.write_text(json.dumps({"state": flow.state}))
        return auth_url

    def handle_callback(self, code: str) -> None:
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError("credentials.json not found.")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_PATH), SCOPES, redirect_uri=AUTH_REDIRECT_URI
        )
        flow.fetch_token(code=code)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(flow.credentials.to_json())
        FLOW_STATE_PATH.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def fetch_by_count(self, count: int, label: str = "INBOX") -> List[Dict]:
        """Return up to `count` most recent inbox emails."""
        svc = self._get_service()
        resp = svc.users().messages().list(
            userId="me", labelIds=[label], maxResults=count
        ).execute()
        return self._batch_fetch(svc, resp.get("messages", []))

    def fetch_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """
        Return emails received between start_date and end_date (YYYY-MM-DD).
        Gmail query format: after:YYYY/MM/DD before:YYYY/MM/DD
        """
        svc = self._get_service()
        after = start_date.replace("-", "/")
        before = end_date.replace("-", "/")
        query = f"after:{after} before:{before}"
        resp = svc.users().messages().list(
            userId="me", q=query, maxResults=500
        ).execute()
        return self._batch_fetch(svc, resp.get("messages", []))

    def _batch_fetch(self, svc, message_refs: List[Dict]) -> List[Dict]:
        """Fetch full message details for a list of {id, threadId} refs."""
        results = []
        for ref in message_refs:
            try:
                msg = svc.users().messages().get(
                    userId="me", id=ref["id"], format="full"
                ).execute()
                results.append(_parse_message(msg))
            except Exception:
                continue  # skip malformed messages rather than crashing
        return results

    def _get_service(self):
        if self._service:
            return self._service
        creds = self._get_valid_creds()
        if not creds:
            raise RuntimeError("Not authenticated. Visit /auth/gmail to connect your account.")
        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service


# ------------------------------------------------------------------
# Parsing helpers (module-level, no class state needed)
# ------------------------------------------------------------------

def _parse_message(msg: Dict) -> Dict:
    headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}
    sender_raw = headers.get("from", "")
    sender_name, sender_email = _split_sender(sender_raw)
    body = _extract_body(msg["payload"])
    snippet = msg.get("snippet", "")
    label_ids = msg.get("labelIds", [])

    return {
        "id": msg["id"],
        "thread_id": msg["threadId"],
        "sender": sender_email,
        "sender_name": sender_name,
        "subject": headers.get("subject", "(no subject)"),
        "received_at": _parse_date(headers.get("date", "")),
        "body": body or snippet,
        "snippet": snippet,
        "label_ids": label_ids,
        "gmail_category": _gmail_category(label_ids),
        "is_unread": "UNREAD" in label_ids,
        "is_important": "IMPORTANT" in label_ids,
    }


def _split_sender(raw: str):
    m = re.match(r'^"?([^"<]+?)"?\s*<([^>]+)>', raw.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return raw.strip(), raw.strip()


def _extract_body(payload: Dict) -> str:
    """Recursively walk MIME parts and return the first plain-text body."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            result = _extract_body(part)
            if result:
                return result
    if mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
            return re.sub(r"<[^>]+>", " ", html)
    return ""


_GMAIL_CATEGORY_MAP = {
    "CATEGORY_PROMOTIONS": "promotions",
    "CATEGORY_SOCIAL": "social",
    "CATEGORY_UPDATES": "updates",
    "CATEGORY_FORUMS": "forums",
    "CATEGORY_PERSONAL": "personal",
}


def _gmail_category(label_ids: List[str]) -> str:
    for label, cat in _GMAIL_CATEGORY_MAP.items():
        if label in label_ids:
            return cat
    return "business"


def _parse_date(date_str: str) -> str:
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        return datetime.utcnow().isoformat()
