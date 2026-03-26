"""
Smart Mail Mentor — FastAPI backend

Endpoints
─────────
GET  /health              — liveness check + model name
GET  /auth/status         — is Gmail connected?
GET  /auth/gmail          — start OAuth flow (returns URL to open in browser)
GET  /auth/callback       — OAuth redirect target (browser hits this)
POST /api/summarize       — main summarization endpoint
GET  /api/preferences     — read user preferences
PUT  /api/preferences     — update user preferences

Run
───
  uvicorn main:app --host 127.0.0.1 --port 8000 --reload
"""
import time
from typing import List, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()  # reads .env if present

from classifier import classify_and_score_emails
from email_fetcher import GmailFetcher
from extractor import extract_insights
from preferences import load_preferences, save_preferences
from summarizer import EmailSummarizer

app = FastAPI(title="Smart Mail Mentor", version="1.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

_summarizer = EmailSummarizer()

VALID_COUNTS = {10, 20, 30, 40}
VALID_CATEGORIES = {"business", "promotions", "social", "updates", "forums", "personal"}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SummarizeRequest(BaseModel):
    mode: str = "count"                     # "count" | "daterange"
    count: Optional[int] = 30              # 10 | 20 | 30 | 40
    start_date: Optional[str] = None       # YYYY-MM-DD
    end_date: Optional[str] = None         # YYYY-MM-DD
    categories: Optional[List[str]] = None # subset of VALID_CATEGORIES
    top_per_category: int = 5              # how many per category card


class PreferencesUpdate(BaseModel):
    important_senders: Optional[List[str]] = None
    important_domains: Optional[List[str]] = None
    priority_keywords: Optional[List[str]] = None
    ignored_senders: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "summarizer": _summarizer.model_name}


@app.get("/auth/status")
def auth_status():
    fetcher = GmailFetcher()
    return {"authenticated": fetcher.is_authenticated()}


@app.get("/auth/gmail")
def auth_start():
    """
    Call this to begin the OAuth flow.
    Returns a URL the user should open in their browser.
    """
    fetcher = GmailFetcher()
    try:
        url = fetcher.get_auth_url()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "auth_url": url,
        "message": "Open this URL in your browser to connect your Gmail account.",
    }


@app.get("/auth/callback")
def auth_callback(code: str = Query(...)):
    """Google redirects here after the user approves access."""
    fetcher = GmailFetcher()
    try:
        fetcher.handle_callback(code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Auth failed: {exc}")
    return {
        "status": "authenticated",
        "message": "Gmail connected successfully. You can close this tab.",
    }


@app.post("/api/summarize")
def summarize(req: SummarizeRequest):
    """
    Main endpoint.  Fetches emails, classifies them, summarizes the top-N
    per category, and returns structured insights.
    """
    t0 = time.perf_counter()

    # Validate
    if req.mode not in ("count", "daterange"):
        raise HTTPException(400, "mode must be 'count' or 'daterange'")
    if req.mode == "daterange" and (not req.start_date or not req.end_date):
        raise HTTPException(400, "start_date and end_date are required for daterange mode")
    if req.top_per_category < 1 or req.top_per_category > 20:
        raise HTTPException(400, "top_per_category must be between 1 and 20")

    # Auth check
    fetcher = GmailFetcher()
    if not fetcher.is_authenticated():
        raise HTTPException(
            status_code=401,
            detail="Gmail not connected.  Visit http://localhost:8000/auth/gmail first.",
        )

    # Fetch
    if req.mode == "daterange":
        emails = fetcher.fetch_by_date_range(req.start_date, req.end_date)
    else:
        count = req.count if req.count in VALID_COUNTS else 30
        emails = fetcher.fetch_by_count(count)

    if not emails:
        return {
            "status": "success",
            "metadata": {"total_fetched": 0, "processing_time_ms": 0},
            "summary": {},
        }

    # Classify + score
    prefs = load_preferences()
    categorized = classify_and_score_emails(emails, prefs)

    # Build result
    target_cats = req.categories or ["business", "promotions", "social", "updates"]
    summary: dict = {}

    for cat in target_cats:
        cat_emails = categorized.get(cat, [])
        top = cat_emails[: req.top_per_category]

        cards = []
        for rank, email in enumerate(top, 1):
            text_summary = _summarizer.summarize(email.get("body", ""), max_sentences=3)
            insights = extract_insights(email, cat)
            cards.append(
                {
                    "rank": rank,
                    "id": email["id"],
                    "sender": email["sender"],
                    "sender_name": email["sender_name"],
                    "subject": email["subject"],
                    "received_at": email["received_at"],
                    "priority_score": email["priority_score"],
                    "summary": text_summary or email.get("snippet", ""),
                    **insights,
                }
            )

        summary[cat] = {
            "total_in_category": len(cat_emails),
            "showing": len(cards),
            "emails": cards,
        }

    elapsed_ms = round((time.perf_counter() - t0) * 1000)

    return {
        "status": "success",
        "metadata": {
            "total_fetched": len(emails),
            "processing_time_ms": elapsed_ms,
            "mode": req.mode,
            "count_requested": req.count if req.mode == "count" else None,
            "date_range": (
                {"start": req.start_date, "end": req.end_date}
                if req.mode == "daterange"
                else None
            ),
            "summarizer": _summarizer.model_name,
        },
        "summary": summary,
    }


@app.get("/api/preferences")
def get_prefs():
    return load_preferences()


@app.put("/api/preferences")
def update_prefs(body: PreferencesUpdate):
    current = load_preferences()
    updates = body.model_dump(exclude_none=True)
    current.update(updates)
    save_preferences(current)
    return {"status": "updated", "preferences": current}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
