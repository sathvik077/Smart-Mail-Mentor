# Smart Mail Mentor

![Mail Mentor Logo](https://github.com/user-attachments/assets/497ad4c7-78f0-4ed4-ae8a-686cd4b02c2c)

An email summarization system that pulls your top emails, classifies them by category, and surfaces what actually matters — coupon codes, expiry dates, action items, deadlines — without you having to read everything.

---

## How it works

```
Chrome Extension  →  FastAPI backend (localhost:8000)  →  Gmail API
                            ↓
                     Classify emails
                     (business / promotions / social / updates)
                            ↓
                     Score priority per category
                     (unread status, sender importance, keyword signals)
                            ↓
                     Summarize top-N with TextRank (or local transformer)
                            ↓
                     Extract insights
                     (coupon codes, discounts, expiry dates, action items)
                            ↓
                     Return structured JSON → rendered in popup
```

**Fetch modes**

| Mode | What it does |
|---|---|
| By count | Fetches top 10 / 20 / 30 / 40 most recent inbox emails |
| Date range | Fetches all emails between two dates you pick |

**Category cards shown in popup**

| Category | What you get |
|---|---|
| Business | Top 5 by priority — action items, deadlines, meeting info |
| Promotions | Top 5 by value — coupon code, discount %, expiry date, free shipping |
| Social | Top 5 — digest of social notifications |
| Updates | Top 5 — service alerts, receipts, shipping |

The "top 5" number is configurable in the popup (3 / 5 / 10).

---

## Project structure

```
Smart-Mail-Mentor/
├── backend/
│   ├── main.py             # FastAPI app — all HTTP endpoints
│   ├── email_fetcher.py    # Gmail API wrapper + OAuth2 flow
│   ├── classifier.py       # Category detection + priority scoring
│   ├── summarizer.py       # TextRank (default) or transformer model
│   ├── extractor.py        # Coupon codes, action items, deadlines, dates
│   ├── preferences.py      # User preference storage (local JSON)
│   ├── requirements.txt
│   └── .env.example
└── extension/
    ├── manifest.json       # Chrome extension manifest v3
    ├── popup.html/css/js   # UI — mode selector, category cards, settings
    ├── background.js       # Service worker (health check, badge)
    ├── content.js          # Gmail page integration (deep-link to thread)
    └── icons/
        └── generate_icons.py
```

---

## Setup

### Prerequisites

- Python 3.10+
- Google Chrome (or Chromium)
- A Google account with Gmail

---

### Step 1 — Google Cloud credentials

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable the **Gmail API**: APIs & Services → Library → search "Gmail API" → Enable
4. Create OAuth credentials: APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Web application**
   - Authorized redirect URIs: `http://localhost:8000/auth/callback`
5. Download the JSON file and save it to:
   ```
   backend/credentials/credentials.json
   ```

---

### Step 2 — Backend

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy env config
cp .env.example .env

# Start the server
python main.py
```

The server starts at `http://localhost:8000`.
Open `http://localhost:8000/docs` to see the interactive API docs.

---

### Step 3 — Connect Gmail (one-time)

1. Open `http://localhost:8000/auth/gmail` in your browser
2. Copy the `auth_url` from the JSON response and open it
3. Sign in with your Google account and allow access
4. You'll be redirected to `localhost:8000/auth/callback` — you'll see `"authenticated": true`

Credentials are stored in `backend/credentials/token.json` and auto-refreshed.
You never need to do this again unless you delete the token file.

---

### Step 4 — Chrome extension

```bash
# Generate the extension icons (run once)
python extension/icons/generate_icons.py
```

1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (toggle in the top-right)
3. Click **Load unpacked**
4. Select the `extension/` folder from this repo
5. The Smart Mail Mentor icon appears in your toolbar

Click the icon to open the popup.

---

## Usage

**By count:**
Pick 10 / 20 / 30 / 40 → Summarize Emails.
The backend fetches that many recent inbox emails and returns the top per category.

**By date range:**
Switch to "Date Range", pick start and end dates, click Summarize.

**Preferences:**
Click the ⚙ icon in the popup to set:
- Priority keywords (e.g. `urgent, deadline, invoice`)
- Important senders (e.g. `boss@company.com`)
- Important domains (e.g. `company.com`)

These boost priority scores during classification.

**What each category card shows (example):**

```
💼 Business  (12 emails · top 5)
  ─────────────────────────────────
  #1  CEO — John Smith              HIGH
  Q4 Strategy Meeting
  ✓ Please prepare the Q4 budget deck by Friday EOD
  📅 Deadline: Friday end of day

  #2  HR — People Ops               MED
  Updated benefits enrollment deadline
  ✓ Complete enrollment form by January 31
  ...

🏷️ Promotions  (8 emails · top 5)
  ─────────────────────────────────
  #1  Nike                          HIGH
  50% Off All Running Shoes — Flash Sale
  Nike is running a 50% flash sale on all running shoes.
  🎫 FLASH50   💰 50% off   ⏰ Exp: January 15   🚚 Free shipping

  #2  Spotify                       MED
  3 months free — Premium offer
  Get 3 months of Spotify Premium free with code PREMIUM3.
  🎫 PREMIUM3   💰 Free   ⏰ Exp: Jan 31
```

---

## Local model

The default summarization engine is **TextRank** — a pure-Python graph-based
extractive algorithm.  No model download, no GPU required, runs in ~5ms per
email.  Good enough for most use cases.

If you want abstractive (generative) summaries, two local models are supported:

### Option A — distilbart-cnn-6-6 (recommended)

A distilled version of BART, fine-tuned on CNN/DailyMail news articles.
Works well for email-length texts.

| Spec | Value |
|---|---|
| Model | `sshleifer/distilbart-cnn-6-6` |
| Size | ~300 MB |
| Speed | ~1–3s per email on CPU |
| Quality | Good |

```bash
# In backend/.env
SUMMARIZER_MODEL=distilbart

# Install extra dependencies
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers
```

The model is downloaded from HuggingFace on first startup (~300 MB) and
cached in `~/.cache/huggingface/`.

### Option B — flan-t5-small (fastest transformer)

An instruction-following T5 model.  Slightly faster than distilbart on CPU.

| Spec | Value |
|---|---|
| Model | `google/flan-t5-small` |
| Size | ~300 MB |
| Speed | ~1–2s per email on CPU |
| Quality | Good for short summaries |

```bash
# In backend/.env
SUMMARIZER_MODEL=flan-t5

# Install extra dependencies
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers sentencepiece
```

### Switching models

Edit `backend/.env`:

```ini
SUMMARIZER_MODEL=textrank    # default — no download
SUMMARIZER_MODEL=distilbart  # 300 MB download on first run
SUMMARIZER_MODEL=flan-t5     # 300 MB download on first run
```

Restart the server after changing this.  The model loads once at startup and
stays in memory.  If loading fails for any reason (model not downloaded,
insufficient memory), the server falls back to TextRank automatically.

### GPU acceleration

If you have a CUDA GPU, install the GPU version of PyTorch:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

Then change `device=-1` to `device=0` in `backend/summarizer.py`:

```python
self._pipe = pipeline(task, model=model_id, device=0)
```

---

## API reference

The full interactive docs are at `http://localhost:8000/docs` when the server
is running.

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Server status + active model name |
| `/auth/status` | GET | Whether Gmail is connected |
| `/auth/gmail` | GET | Start OAuth flow — returns URL to open |
| `/auth/callback` | GET | OAuth redirect target |
| `/api/summarize` | POST | Main endpoint — fetch, classify, summarize |
| `/api/preferences` | GET | Read current preferences |
| `/api/preferences` | PUT | Update preferences |

**POST /api/summarize — request body**

```json
{
  "mode": "count",
  "count": 30,
  "top_per_category": 5
}
```

```json
{
  "mode": "daterange",
  "start_date": "2025-01-01",
  "end_date": "2025-01-31",
  "top_per_category": 5
}
```

Valid `count` values: `10`, `20`, `30`, `40`.

**Response shape**

```json
{
  "status": "success",
  "metadata": {
    "total_fetched": 30,
    "processing_time_ms": 420,
    "mode": "count",
    "summarizer": "textrank"
  },
  "summary": {
    "business": {
      "total_in_category": 12,
      "showing": 5,
      "emails": [
        {
          "rank": 1,
          "sender": "john@company.com",
          "sender_name": "John Smith",
          "subject": "Q4 review",
          "received_at": "2025-01-15T09:30:00",
          "priority_score": 0.82,
          "summary": "Requesting attendance at Q4 review on Jan 20 at 2pm.",
          "action_items": ["Please prepare the budget deck"],
          "meeting_info": "Meeting scheduled on Jan 20 at 2pm",
          "deadlines": ["Due by Friday EOD"]
        }
      ]
    },
    "promotions": {
      "total_in_category": 8,
      "showing": 5,
      "emails": [
        {
          "rank": 1,
          "sender": "deals@nike.com",
          "sender_name": "Nike",
          "subject": "50% off — Flash Sale",
          "priority_score": 0.76,
          "summary": "Nike flash sale with 50% off all running shoes.",
          "promo_details": {
            "brand": "Nike",
            "discount": "50% off",
            "coupon_code": "FLASH50",
            "expiry_date": "January 15",
            "free_shipping": true
          }
        }
      ]
    }
  }
}
```

---

## Adding the extension to another browser

**Firefox (Manifest V2 required):**
Firefox does not support Manifest V3 service workers the same way.
Change `manifest.json` `"background"` from `"service_worker"` to:
```json
"background": { "scripts": ["background.js"] }
```
Then load via `about:debugging` → This Firefox → Load Temporary Add-on.

**Edge:**
Works the same as Chrome.  Load via `edge://extensions` → Developer mode → Load unpacked.

---

## Performance notes

- TextRank runs in ~5ms per email.  30 emails → typically under 500ms total.
- The Gmail API batch fetch is the bottleneck (~1–3s depending on message size).
- Transformer models add ~1–3s per email on CPU.  Not recommended for batches
  larger than 10 if you want sub-10s responses.
- The backend keeps the model in memory between requests, so only the first
  request after startup pays the load cost.

---

## Team

**Team 5 — Smart Mail Mentor**

| Name | Role |
|---|---|
| Sathvik Chowdary Samineni | Team lead, Gmail API integration, backend |
| Purushotham Kalangi | NLP pipeline, model integration, frontend |
| Rakesh Kuchipudi | Research, model evaluation, Python backend |
