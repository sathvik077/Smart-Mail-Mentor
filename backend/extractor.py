"""
Domain-specific insight extraction.

Promotions → coupon codes, discount %, expiry dates, brand name, free shipping flag.
Business   → action items, meeting details, deadlines.

All extraction is regex-based — zero model downloads, runs in microseconds.
"""
import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Promotion patterns
# ---------------------------------------------------------------------------

# Most specific first so we don't get false positives from the generic ones
_COUPON_RE = [
    re.compile(
        r"(?:use\s+code|promo\s*code|coupon\s*code|discount\s*code|enter\s*code)"
        r"\s*[:\-]?\s*([A-Z0-9]{4,15})",
        re.IGNORECASE,
    ),
    re.compile(r"\bcode\s*[:\-]\s*([A-Z0-9]{4,15})\b", re.IGNORECASE),
    # All-caps alphanumeric 5-12 chars (exclude common English words)
    re.compile(r"\b([A-Z]{2,5}[0-9]{2,6}|[A-Z0-9]{6,12})\b"),
]

_COUPON_BLACKLIST = {
    "HTTP", "HTTPS", "HTML", "EMAIL", "GMAIL", "CLICK", "HERE",
    "SHOP", "VIEW", "OPEN", "READ", "MORE", "LEARN",
}

_DISCOUNT_RE = [
    re.compile(r"(\d+(?:\.\d+)?)\s*%\s*off", re.IGNORECASE),
    re.compile(r"(\d+(?:\.\d+)?)\s*percent\s*off", re.IGNORECASE),
    re.compile(r"save\s+(\d+)\s*%", re.IGNORECASE),
    re.compile(r"up\s+to\s+(\d+)\s*%\s*off", re.IGNORECASE),
    re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*off", re.IGNORECASE),
    re.compile(r"save\s+\$\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
]

_EXPIRY_RE = [
    # "expires January 31, 2025" / "valid until Jan 31"
    re.compile(
        r"(?:expires?|expiry|valid\s+(?:until|through)|ends?\s+(?:on\s+)?|offer\s+ends?)\s*[:\-]?\s*"
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4})",
        re.IGNORECASE,
    ),
    # "expires 01/31/2025"
    re.compile(
        r"(?:expires?|ends?|valid\s+through)\s*[:\-]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",
        re.IGNORECASE,
    ),
    # "ends tonight" / "today only"
    re.compile(r"\b(today only|tonight only|ends tonight|midnight tonight)\b", re.IGNORECASE),
]

_FREE_SHIP_RE = re.compile(r"free\s+(?:shipping|delivery)|ships?\s+free", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Business patterns
# ---------------------------------------------------------------------------

_ACTION_RE = [
    re.compile(r"please\s+([^.!?\n]{8,70})", re.IGNORECASE),
    re.compile(r"(?:can you|could you|would you)\s+([^.!?\n]{8,70})", re.IGNORECASE),
    re.compile(r"(?:need|needs)\s+(?:you\s+)?(?:to\s+)?([^.!?\n]{8,60})", re.IGNORECASE),
    re.compile(r"(?:action\s+(?:required|item))\s*[:\-]?\s*([^.!?\n]{8,70})", re.IGNORECASE),
]

_MEETING_RE = [
    re.compile(
        r"(?:meeting|call|sync|standup|stand-up|conference)\s+"
        r"(?:is\s+)?(?:scheduled\s+)?(?:on|at)\s+([^.!?\n]{5,60})",
        re.IGNORECASE,
    ),
    re.compile(r"join\s+(?:us|the\s+call)\s+(?:on|at)\s+([^.!?\n]{5,60})", re.IGNORECASE),
]

_DEADLINE_RE = [
    re.compile(
        r"(?:due|deadline)\s*(?:on|by|is)?\s*[:\-]?\s*([^.!?\n]{3,50})",
        re.IGNORECASE,
    ),
    re.compile(r"(?:submit|send|complete|finish)\s+(?:by|before)\s+([^.!?\n]{3,50})", re.IGNORECASE),
    re.compile(r"\b(?:by\s+(?:eod|cob|end\s+of\s+(?:day|week)|tomorrow|friday))[^.!?\n]*", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_insights(email: Dict, category: str) -> Dict[str, Any]:
    if category == "promotions":
        return _promo_insights(email)
    if category == "business":
        return _business_insights(email)
    return {}


# ---------------------------------------------------------------------------
# Promotion extraction
# ---------------------------------------------------------------------------

def _promo_insights(email: Dict) -> Dict[str, Any]:
    full_text = f"{email['subject']} {email.get('body', '')}"

    return {
        "promo_details": {
            "brand": _brand(email),
            "discount": _discount(full_text),
            "coupon_code": _coupon(full_text),
            "expiry_date": _expiry(full_text),
            "free_shipping": bool(_FREE_SHIP_RE.search(full_text)),
        }
    }


def _coupon(text: str) -> Optional[str]:
    for pattern in _COUPON_RE:
        m = pattern.search(text)
        if m:
            code = m.group(1).upper()
            if code in _COUPON_BLACKLIST:
                continue
            # Skip pure-alpha short codes (likely English words)
            if code.isalpha() and len(code) <= 5:
                continue
            return code
    return None


def _discount(text: str) -> Optional[str]:
    best = 0.0
    for pattern in _DISCOUNT_RE:
        for m in pattern.finditer(text):
            try:
                val = float(m.group(1))
                if val > best:
                    best = val
            except (IndexError, ValueError):
                pass
    if best > 0:
        # Format: "50% off" or "$10 off"
        return f"{int(best)}% off" if best == int(best) else f"{best}% off"
    return None


def _expiry(text: str) -> Optional[str]:
    for pattern in _EXPIRY_RE:
        m = pattern.search(text)
        if m:
            try:
                return m.group(1).strip()
            except IndexError:
                return m.group(0).strip()
    return None


def _brand(email: Dict) -> str:
    name = email.get("sender_name", "").strip()
    # Strip angle-bracket address if mixed in
    name = re.sub(r"<[^>]+>", "", name).strip()
    if name and not any(x in name.lower() for x in ("noreply", "no-reply", "newsletter", "info")):
        return name
    sender = email.get("sender", "")
    m = re.search(r"@([a-z0-9\-]+)\.", sender.lower())
    if m:
        return m.group(1).replace("-", " ").title()
    return name or sender


# ---------------------------------------------------------------------------
# Business extraction
# ---------------------------------------------------------------------------

def _business_insights(email: Dict) -> Dict[str, Any]:
    text = f"{email['subject']} {email.get('body', '')}"
    return {
        "action_items": _action_items(text)[:3],
        "meeting_info": _meeting_info(text),
        "deadlines": _deadlines(text)[:2],
    }


def _action_items(text: str) -> List[str]:
    seen: List[str] = []
    for pattern in _ACTION_RE:
        for m in pattern.finditer(text):
            item = m.group(0).strip().rstrip(".,;")
            item = item[0].upper() + item[1:] if item else item
            if item and item not in seen:
                seen.append(item)
    return seen[:5]


def _meeting_info(text: str) -> Optional[str]:
    for pattern in _MEETING_RE:
        m = pattern.search(text)
        if m:
            return m.group(0).strip()
    return None


def _deadlines(text: str) -> List[str]:
    found: List[str] = []
    for pattern in _DEADLINE_RE:
        for m in pattern.finditer(text):
            d = m.group(0).strip()
            if d and d not in found:
                found.append(d)
    return found[:3]
