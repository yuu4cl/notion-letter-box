# Letter Box — Technical Architecture

_A two-layer asynchronous letter exchange system. 

_Created: 2026-06-07 | Updated: 2026-06-08_

---

## Overview

Two-layer letter exchange system inspired by Slowly app (deliberate delay, intentional writing). A and B exchange letters via Notion DBs — A reads/writes via API, B uses Notion UI + Send button.

**Roles:**
- **A (Sender):** Automated agent — reads B's inbox, writes and posts letters via API
- **B (Recipient):** Human — writes letters via Notion UI, reads replies from A

---

## System Components

### Layer 1 — Inbox DBs (one per person)

| DB | Notes |
|----|-------|
| A's Inbox (B→A) | Letters from B to A |
| B's Inbox (A→B) | Letters from A to B |

**Inbox DB Properties (both identical):**

| Property | Type | Notes |
|----------|------|-------|
| From | select | A / B |
| To | select | A / B |
| Subject | title | Letter subject |
| Thread ID | rich_text | Empty = new thread; filled = reply |
| Sent At | date | Timestamp when written |
| Delivered At | date | Controls when letter is visible |
| Read At | date | Empty until read |
| Replied? | checkbox | Auto-set when replied |

> **Note:** Mood is represented by page emoji icon only (no Mood property in code). The DB property can be manually deleted if desired.

### Layer 2 — Thread DB (shared, auto-linked)

**Thread DB Properties:**

| Property | Type | Notes |
|----------|------|-------|
| Thread ID | rich_text | Links to letter Thread IDs |
| Active | checkbox | Uncheck to close thread |
| Last Edit From | select | A / B — who wrote last |
| Start Date | date | Auto-set when thread opens |
| Close Date | date | Set when thread is closed |

---

## Flow

```
B writes letter → A's Inbox (Thread ID = empty)
                              │
                              ▼
                     letter.sh checks inbox (daily cron)
                              │
           ┌─────────────────┴─────────────────┐
              │ │
         Unread? No unread
              │                                   │
              ▼                                   ▼
        REPLY mode                         SURPRISE mode
    (A has unread from B)           (no active threads + conditions met)
              │                                   │
              ▼                                   ▼
    post_letter.py:                         post_letter.py:
    - Thread exists? use it                  - new_thread_id()
    - No thread? create one                 - create_thread()
    - Update Thread ID on original - post surprise letter
    - Mark Read At + Replied?               - Delivered At = now + 30min~2hr
    - Post reply to B's Inbox
              │
              ▼
    B reads reply → replies → thread grows
```

---

## Scripts

| File | Role |
|------|------|
| `letter.sh` | Main driver: checks inbox → REPLY vs SURPRISE → injects prompt to A |
| `check_inbox.py` | Unread checker (handles Notion `date: None` edge case) |
| `post_letter.py` | A calls after generating content: posts + thread handling |
| `tg_inject.sh` | Prompt injection to A's session (RAW=1 mode) |

### What post_letter.py does

**Reply to new thread** (original letter Thread ID = empty):
1. `new_thread_id()` — generate unique ID
2. `create_thread()` — create Thread DB entry
3. `update_letter_thread_id()` — fill Thread ID on original letter
4. `mark_all_thread_letters_read_replied()` — mark ALL unread letters in thread as read + replied
5. `update_thread_last_edit()` — set last_edit_from = A
6. Post reply to B's Inbox (icon: Claude decides via prompt, fallback 💭)

**Reply to existing thread** (original letter has Thread ID):
1. `mark_all_thread_letters_read_replied()` — mark all unread letters in thread as read + replied
2. `update_thread_last_edit()` — update last_edit_from = A
3. Post reply with existing thread ID (icon: Claude decides via prompt, fallback 💭)

**Surprise letter:**
1. `new_thread_id()` + `create_thread()`
2. Post surprise to B's Inbox

---

## Threading Logic

1. **New thread:** Letter has `Thread ID = empty` → A creates thread → fills Thread ID on letter
2. **Reply:** Letter has `Thread ID = xyz` → A posts to existing thread
3. **Active thread:** `Active = true` and `last_edit_from = A` → A waiting for B's reply
4. **Close:** Either person unchecks `Active` → thread closes

---

## Delay Mechanism

- `Delivered At` controls when letter is visible (sent with 30min~2hr random delay)
- `Sent At` is set by post_letter.py at time of posting
- `Read At` + `Replied?` set automatically by post_letter.py

---

## Cron

- **Schedule:** Daily 02:00 JST (`0 17 * * *` UTC)
- **Pattern:** System crontab (not Hermes CLI)
- **Entry:** `bash /path/to/letter.sh >> /tmp/letter.log 2>&1`

---

## Setup

1. Create two Notion Inbox DBs (one per person) and one Thread DB
2. Add properties per schema above
3. Set `NOTION_TOKEN`, `INBOX_ID_A`, `INBOX_ID_B`, `THREAD_DB_ID` in scripts
4. Point `TG_INJECT` and script paths to your environment
5. Add to crontab: `0 17 * * * bash /path/to/letter.sh >> /tmp/letter.log 2>&1`

---

## Notes & Gotchas

- Notion DB buttons are UI-only — only usable by B
- A uses direct Notion HTTP API, not Notion MCP (MCP has serialization bug for rich_text arrays)
- `check_inbox.py` handles `date: None` from Notion (different from `date: {start: null}`)

---