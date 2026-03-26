"""
Email classification and priority scoring.

Classification strategy:
  1. Use Gmail's built-in category labels when present (most accurate).
  2. Fall back to keyword-signal scoring against subject + snippet.

Priority scoring is per-category and produces a 0.0–1.0 float.
Emails are sorted descending before the top-N slice.
"""
from collections import defaultdict
from typing import Dict, List
import re

# fmt: off
_BUSINESS_SIGNALS = {
    "urgent": 3.0, "asap": 2.5, "action required": 3.0, "time sensitive": 2.5,
    "deadline": 2.5, "due today": 3.0, "overdue": 3.5, "follow up": 1.5,
    "response needed": 2.5, "please review": 2.0, "approve": 2.0,
    "approval": 2.0, "invoice": 2.5, "payment": 2.5, "contract": 2.5,
    "meeting": 2.0, "conference": 1.5, "project": 1.5, "report": 1.5,
    "client": 2.0, "budget": 2.0, "quarterly": 1.5, "proposal": 2.0,
    "reminder": 1.5, "schedule": 1.5,
}

_PROMO_SIGNALS = {
    "sale": 2.0, "off": 1.5, "discount": 2.0, "promo": 2.5, "coupon": 3.0,
    "deal": 2.0, "offer": 1.5, "free shipping": 2.5, "clearance": 2.0,
    "limited time": 2.5, "flash sale": 3.0, "expires": 2.5, "save": 1.5,
    "exclusive": 1.5, "code": 1.0, "shop now": 1.5, "order now": 1.5,
    "black friday": 3.0, "cyber monday": 3.0, "holiday sale": 2.5,
    "members only": 2.0, "% off": 3.0, "buy now": 1.5,
}

_PROMO_SENDER_SIGNALS = [
    "newsletter", "noreply", "no-reply", "deals", "promo", "marketing",
    "offers", "sales", "notifications", "info@", "hello@", "news@",
]
# fmt: on


def classify_and_score_emails(emails: List[Dict], prefs: Dict) -> Dict[str, List[Dict]]:
    """
    Classify each email into a category and compute its priority score.
    Returns a dict mapping category name → list sorted by score desc.
    """
    ignored = {s.lower() for s in prefs.get("ignored_senders", [])}
    categorized: Dict[str, List[Dict]] = defaultdict(list)

    for email in emails:
        sender = email.get("sender", "").lower()
        if any(s in sender for s in ignored):
            continue

        category = _determine_category(email)
        score = _priority_score(email, category, prefs)
        email["category"] = category
        email["priority_score"] = score
        categorized[category].append(email)

    for cat in categorized:
        categorized[cat].sort(key=lambda e: e["priority_score"], reverse=True)

    return dict(categorized)


def _determine_category(email: Dict) -> str:
    gmail_cat = email.get("gmail_category", "")
    # Gmail's labeling is reliable for promotions/social/updates
    if gmail_cat in ("promotions", "social", "updates", "forums"):
        return gmail_cat

    text = f"{email['subject']} {email.get('snippet', '')}".lower()
    sender = email.get("sender", "").lower()

    # Commercial sender heuristic
    if any(sig in sender for sig in _PROMO_SENDER_SIGNALS):
        return "promotions"

    promo = sum(w for k, w in _PROMO_SIGNALS.items() if k in text)
    biz = sum(w for k, w in _BUSINESS_SIGNALS.items() if k in text)

    if promo > biz and promo >= 2.0:
        return "promotions"
    if biz >= 2.0:
        return "business"
    return gmail_cat or "updates"


def _priority_score(email: Dict, category: str, prefs: Dict) -> float:
    score = 0.0
    text = f"{email['subject']} {email.get('body', '')[:600]}".lower()
    subject = email["subject"].lower()
    sender = email.get("sender", "").lower()

    # Gmail signals
    if email.get("is_unread"):
        score += 0.12
    if email.get("is_important"):
        score += 0.22

    # User preference boosts
    for s in (x.lower() for x in prefs.get("important_senders", [])):
        if s in sender:
            score += 0.38
            break

    for d in (x.lower() for x in prefs.get("important_domains", [])):
        if d in sender:
            score += 0.28
            break

    kw_hits = sum(1 for k in prefs.get("priority_keywords", []) if k.lower() in text)
    score += min(kw_hits * 0.08, 0.24)

    # Category-specific scoring
    if category == "business":
        score += _biz_score(text, subject)
    elif category == "promotions":
        score += _promo_score(text, subject)

    return min(round(score, 4), 1.0)


def _biz_score(text: str, subject: str) -> float:
    score = sum(min(w * 0.04, 0.12) for k, w in _BUSINESS_SIGNALS.items() if k in text)
    if re.search(r"\b(urgent|asap|important|action required|time.sensitive)\b", subject):
        score += 0.18
    # Real person email: no unsubscribe link
    if "unsubscribe" not in text:
        score += 0.08
    return min(score, 0.55)


def _promo_score(text: str, subject: str) -> float:
    score = 0.0
    discounts = re.findall(r"(\d+)\s*%\s*off", text)
    if discounts:
        top = max(int(d) for d in discounts)
        score += min(top / 100.0 * 0.45, 0.38)
    if re.search(r"\b[A-Z0-9]{5,12}\b", text):  # has coupon code
        score += 0.14
    if re.search(r"(flash sale|ends today|last chance|limited time|tonight only)", text):
        score += 0.14
    if "free shipping" in text:
        score += 0.08
    return min(score, 0.55)
