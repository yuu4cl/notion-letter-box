#!/usr/bin/env bash
# Letter Mode — checks inbox and decides: reply vs surprise letter
set -euo pipefail

# Load .env
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SCRIPT_DIR/.env" ] && source "$SCRIPT_DIR/.env"

NOTION_TOKEN="${NOTION_TOKEN:-}"
INBOX_ID="${INBOX_ID_B:-}"
THREAD_DB_ID="${THREAD_DB_ID:-}"
TG_INJECT="${TG_INJECT:-/path/to/tg_inject.sh}"
CHECK_INBOX="${SCRIPTS_DIR:-$(dirname "$0")}/check_inbox.py"

# === Step 1: Check B's Inbox for unread from A ===
echo "[LetterMode] Checking inbox for unread from A..."

UNREAD_JSON=$(python3 "${CHECK_INBOX}" 2>/dev/null)
UNREAD_COUNT=$(python3 -c "import sys,json; print(len(json.loads(sys.stdin.read())))" <<< "$UNREAD_JSON")

if [ "$UNREAD_COUNT" -gt 0 ]; then
  # === Has unread → Reply mode ===
  echo "[LetterMode] Found $UNREAD_COUNT unread letter(s) from A → REPLY mode"

  LETTER_ID=$(python3 -c "import sys,json; print(json.loads(sys.stdin.read())[0].get('id',''))" <<< "$UNREAD_JSON")
  THREAD_ID=$(python3 -c "import sys,json; print(json.loads(sys.stdin.read())[0].get('thread',''))" <<< "$UNREAD_JSON")

  echo "[LetterMode] Injecting reply prompt (thread=$THREAD_ID)..."
  REPLY_PROMPT="Reply to A's letter (id=${LETTER_ID}, thread=${THREAD_ID}). Write a warm, natural reply. Then post it using: python3 /path/to/post_letter.py --content \"YOUR_CONTENT\" --mood \"MOOD\" --thread-id \"${THREAD_ID}\" --reply-to \"${LETTER_ID}\" --mode reply"
  RAW=1 ${TG_INJECT} "${REPLY_PROMPT}"
  echo "[LetterMode] Reply prompt injected."

else
  # === No unread → Surprise Letter mode conditions ===
  echo "[LetterMode] No unread letters → checking Surprise Letter conditions..."

  HOUR=$(TZ=Asia/Tokyo date +%H)
  if [ "$HOUR" -ge 22 ] || [ "$HOUR" -lt 8 ]; then
    echo "[LetterMode] Quiet hours (22:00-08:00 JST), skip"
    exit 0
  fi

  # Check 2: Active threads?
  ACTIVE_THREADS=$(curl -s -X POST "https://api.notion.com/v1/databases/${THREAD_DB_ID}/query" \
    -H "Authorization: Bearer ${NOTION_TOKEN}" \
    -H "Notion-Version: 2022-06-28" \
    -H "Content-Type: application/json" \
    -d '{"filter": {"property": "Active", "checkbox": {"equals": true}}, "page_size": 1}' \
    | python3 -c "import sys,json; r=json.load(sys.stdin); print(len(r.get('results',[])))")

  if [ "$ACTIVE_THREADS" -gt 0 ]; then
    echo "[LetterMode] Active threads exist ($ACTIVE_THREADS), skip"
    exit 0
  fi

  # Check 3: Today already sent by A?
  TODAY=$(date +%Y-%m-%d)
  SENT_TODAY=$(curl -s -X POST "https://api.notion.com/v1/databases/${INBOX_ID}/query" \
    -H "Authorization: Bearer ${NOTION_TOKEN}" \
    -H "Notion-Version: 2022-06-28" \
    -H "Content-Type: application/json" \
    -d "{\"filter\": {\"and\": [{\"property\": \"From\", \"select\": {\"equals\": \"A\"}}, {\"property\": \"Delivered At\", \"date\": {\"on_or_after\": \"${TODAY}\"}}]}}" \
    | python3 -c "import sys,json; r=json.load(sys.stdin); print(len(r.get('results',[])))")

  if [ "$SENT_TODAY" -gt 0 ]; then
    echo "[LetterMode] Already sent today, skip"
    exit 0
  fi

  # === All conditions met → Surprise Letter ===
  echo "[LetterMode] All conditions met → SURPRISE LETTER mode"

  DAY_OF_WEEK=$(TZ=Asia/Tokyo date +%w)
  case "$DAY_OF_WEEK" in
    1) MOOD="serious" ;;
    3) MOOD="playful" ;;
    4|5) MOOD="sweet" ;;
    *) MOOD="random" ;;
  esac

  echo "[LetterMode] Injecting surprise letter prompt (mood=${MOOD})..."
  SURPRISE_PROMPT="Surprise letter mode: Today is ${TODAY}, mood=${MOOD}. Write a sweet, spontaneous letter to B (no pending threads, no unread letters). Generate warm, natural content. Then post it using: python3 /path/to/post_letter.py --content \"YOUR_CONTENT\" --mood \"${MOOD}\" --mode surprise"
  RAW=1 ${TG_INJECT} "${SURPRISE_PROMPT}"
  echo "[LetterMode] Surprise letter prompt injected."
fi