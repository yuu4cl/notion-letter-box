# Letter Box

A two-layer asynchronous letter exchange system using Notion as the backend.

## Setup

1. **Create Notion DBs**
   - Two Inbox DBs (one per person): `INBOX_ID_A`, `INBOX_ID_B`
   - One Thread DB: `THREAD_DB_ID`
   - Properties per `letter-box-architecture.md`

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your values (do NOT commit .env)
   ```

3. **Install dependencies**
   ```bash
   # pip
   pip install -r requirements.txt

   # or uv
   uv sync
   ```

4. **Add to crontab**
   ```bash
   0 17 * * * bash /path/to/letter.sh >> /tmp/letter.log 2>&1
   ```

## Files

| File | Description |
|------|-------------|
| `letter-box-architecture.md` | Full technical architecture |
| `letter.sh` | Main driver (checks inbox, decides reply vs surprise) |
| `check_inbox.py` | Unread letter checker |
| `post_letter.py` | Posts letters + handles threads |
| `.env.example` | Environment variable template |

## Roles

- **A:** Automated agent — reads B's inbox, writes letters via API
- **B:** Human — writes via Notion UI, reads replies from A

## Mood Options

Serious (Mon) / Playful (Wed) / Sweet (Fri/Sat) / Random (other days)