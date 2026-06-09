#!/usr/bin/env bash
# Letter Mode — AI Agent (A) reads inbox and decides: reply vs surprise letter
# Batch processes ALL threads with unread letters from Human (B)
# Mood is represented by page emoji icon only (no Mood property in DB)
set -euo pipefail

# Load .env
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SCRIPT_DIR/.env" ] && source "$SCRIPT_DIR/.env"

NOTION_TOKEN="${NOTION_TOKEN:-}"
INBOX_ID="${INBOX_ID_B:-}"  # B's Inbox (letters from B to A)
THREAD_DB_ID="${THREAD_DB_ID:-}"
TG_INJECT="${TG_INJECT:-/path/to/tg_inject.sh}"
CHECK_INBOX="${SCRIPTS_DIR:-$(dirname "$0")}/check_inbox.py"
POST_LETTER="${SCRIPTS_DIR:-$(dirname "$0")}/post_letter.py"
PROCESS_THREADS="${SCRIPTS_DIR:-$(dirname "$0")}/process_threads.py"

# === Fetch all unread grouped by thread ===
echo "[LetterMode] Fetching all unread letters grouped by thread..."

GROUPED_JSON=$(python3 "${CHECK_INBOX}" 2>/dev/null)
THREAD_COUNT=$(python3 -c "import sys,json; print(len(json.loads(sys.stdin.read())))" <<< "$GROUPED_JSON")

if [ "$THREAD_COUNT" -eq 0 ]; then
  echo "[LetterMode] No unread letters from B → checking Surprise Letter conditions..."

  # Quiet hours check (JST 22:00-08:00)
  HOUR=$(TZ=Asia/Tokyo date +%H)
  if [ "$HOUR" -ge 22 ] || [ "$HOUR" -lt 8 ]; then
    echo "[LetterMode] Quiet hours (22:00-08:00 JST), skip"
    exit 0
  fi

  # Check: Active threads exist?
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

  # Check: A already sent today?
  TODAY=$(date +%Y-%m-%d)
  SENT_TODAY=$(curl -s -X POST "https://api.notion.com/v1/databases/${INBOX_ID}/query" \
    -H "Authorization: Bearer ${NOTION_TOKEN}" \
    -H "Notion-Version: 2022-06-28" \
    -H "Content-Type: application/json" \
    -d "{\"filter\": {\"and\": [{\"property\": \"From\", \"select\": {\"equals\": \"A\"}}, {\"property\": \"Delivered At\", \"date\": {\"on_or_after\": \"${TODAY}\"}}]}}" \
    | python3 -c "import sys,json; r=json.load(sys.stdin); print(len(r.get('results',[])))")

  if [ "$SENT_TODAY" -gt 0 ]; then
    echo "[LetterMode] A already sent today, skip"
    exit 0
  fi

  # === All conditions met → Surprise Letter ===
  echo "[LetterMode] All conditions met → SURPRISE LETTER mode"

  echo "[LetterMode] Injecting surprise letter prompt..."
  SURPRISE_PROMPT="Surprise letter mode: Today is ${TODAY}. Write a sweet, spontaneous letter to B (no pending threads, no unread letters from B). Generate warm, natural content. Then post it using:
python3 ${POST_LETTER} --content \"YOUR_LETTER_CONTENT\" --mode surprise --icon \"YOUR_ICON\""
  RAW=1 ${TG_INJECT} "${SURPRISE_PROMPT}"
  echo "[LetterMode] Surprise letter prompt injected. A will write and post."

else
  # === REPLY mode: process all threads with unread ===
  echo "[LetterMode] Found $THREAD_COUNT thread(s) with unread letters from B → REPLY mode"

  # Get all threads as structured output
  THREADS_OUTPUT=$(echo "$GROUPED_JSON" | python3 "${PROCESS_THREADS}")

  # Parse and process each thread
  CURRENT_THREAD_ID=""
  CURRENT_SUBJECT=""
  CURRENT_COUNT=1
  CURRENT_LETTER_ID=""

  while IFS= read -r line; do
    if [ "$line" = "---" ]; then
      # Process accumulated thread data
      echo "[LetterMode] Processing thread: thread_id=${CURRENT_THREAD_ID}, letters=${CURRENT_COUNT}"

      REPLY_PROMPT="Reply to thread with ${CURRENT_COUNT} letter(s) from B.

Thread ID: ${CURRENT_THREAD_ID}
Original Subject: ${CURRENT_SUBJECT}
First Letter ID: ${CURRENT_LETTER_ID}

Instructions:
1. Fetch the letter content from Notion using API (page ID: ${CURRENT_LETTER_ID})
2. If ${CURRENT_COUNT} > 1, also check if there are other letters in this thread to understand full context
3. Write a warm, natural reply that considers all upstream letters
4. Post your reply using:
python3 ${POST_LETTER} \
  --content \"YOUR_LETTER_CONTENT\" \
  --reply-to \"${CURRENT_LETTER_ID}\" \
  --thread-id \"${CURRENT_THREAD_ID}\" \
  --original-subject \"${CURRENT_SUBJECT}\" \
  --icon \"YOUR_ICON\" \
  --mode reply"

      RAW=1 ${TG_INJECT} "${REPLY_PROMPT}"
      echo "[LetterMode] Reply prompt injected for thread ${CURRENT_THREAD_ID}. A will write and post."

      # Reset for next thread
      CURRENT_THREAD_ID=""
      CURRENT_SUBJECT=""
      CURRENT_COUNT=1
      CURRENT_LETTER_ID=""
    else
      # Parse key=value
      if [[ "$line" == THREAD_INDEX=* ]]; then
        # index line - can be ignored for now
        :
      elif [[ "$line" == THREAD_ID=* ]]; then
        CURRENT_THREAD_ID="${line#THREAD_ID=}"
      elif [[ "$line" == THREAD_SUBJECT=* ]]; then
        CURRENT_SUBJECT="${line#THREAD_SUBJECT=}"
      elif [[ "$line" == LETTER_COUNT=* ]]; then
        CURRENT_COUNT="${line#LETTER_COUNT=}"
      elif [[ "$line" == FIRST_LETTER_ID=* ]]; then
        CURRENT_LETTER_ID="${line#FIRST_LETTER_ID=}"
      fi
    fi
  done <<< "$THREADS_OUTPUT"

  echo "[LetterMode] All $THREAD_COUNT thread(s) processed."
fi