"""
User preference storage backed by a local JSON file.
No database required – keeps setup minimal.
"""
import json
from pathlib import Path
from typing import Any, Dict

PREFS_PATH = Path(__file__).parent / "user_preferences.json"

DEFAULT_PREFERENCES: Dict[str, Any] = {
    "important_senders": [],        # e.g. ["boss@company.com"]
    "important_domains": [],        # e.g. ["company.com"]
    "priority_keywords": [          # boosts priority score when found in email
        "urgent", "deadline", "asap", "action required", "invoice", "contract"
    ],
    "ignored_senders": [],          # these are skipped during classification
    "top_per_category": 5,
    "default_email_count": 30,
}


def load_preferences() -> Dict[str, Any]:
    if not PREFS_PATH.exists():
        save_preferences(DEFAULT_PREFERENCES)
        return DEFAULT_PREFERENCES.copy()
    with open(PREFS_PATH) as f:
        stored = json.load(f)
    # Always merge with defaults so newly added keys are present
    return {**DEFAULT_PREFERENCES, **stored}


def save_preferences(prefs: Dict[str, Any]) -> None:
    PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PREFS_PATH, "w") as f:
        json.dump(prefs, f, indent=2)
