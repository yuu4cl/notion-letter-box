#!/usr/bin/env bash
# Letter Mode — AI Agent (A) reads inbox and decides: reply vs surprise letter
# Batch processes ALL threads with unread letters from Human (B)
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

# === Fetch all unread grouped by thread ===
echo "[LetterMode] Fetching all unread letters grouped by thread..."

GROUPED_JSON=$(python3 "${CHECK_INBOX}" 2>/dev/null)
THREAD_COUNT=$(python3 -c "import sys,json; print(len(json.loads(sys.stdin.read()).get('threads',[])))" <<< "$GROUPED_JSON")

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

  # Mood selection by day of week
  DAY_OF_WEEK=$(TZ=Asia/Tokyo date +%w)
  case "$DAY_OF_WEEK" in
    1) MOOD="serious" ;;
    3) MOOD="playful" ;;
    4|5) MOOD="sweet" ;;
    *) MOOD="random" ;;
  esac

  echo "[LetterMode] Injecting surprise letter prompt (mood=${MOOD})..."
  SURPRISE_PROMPT="Surprise letter mode: Today is ${TODAY}, mood=${MOOD}. Write a sweet, spontaneous letter to B (no pending threads, no unread letters from B). Generate warm, natural content. Then post it using:
python3 ${POST_LETTER} --content \"YOUR_LETTER_CONTENT\" --mood \"${MOOD}\" --mode surprise"
  RAW=1 ${TG_INJECT} "${SURPRISE_PROMPT}"
  echo "[LetterMode] Surprise letter prompt injected. A will write and post."

else
  # === REPLY mode: process all threads with unread ===
  echo "[LetterMode] Found $THREAD_COUNT thread(s) with unread letters from B → REPLY mode"

  # Iterate through each thread
  for i in $(python3 -c "import sys,json; print(range(len(json.loads(sys.stdin.read()).get('threads',[]))))" <<< "$GROUPED_JSON"); do
    THREAD_DATA=$(python3 -c "import sys,json; print(json.dumps(json.loads(sys.stdin.read()).get('threads',[])[$i]))" <<< "$GROUPED_JSON")

    THREAD_ID=$(python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('thread_id',''))" <<< "$THREAD_DATA")
    THREAD_SUBJECT=$(python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('thread_subject',''))" <<< "$THREAD_DATA")
    LETTER_COUNT=$(python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('letter_count',1))" <<< "$THREAD_DATA")
    FIRST_LETTER_ID=$(python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('first_letter_id',''))" <<< "$THREAD_DATA")
    MOOD=$(python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('latest_mood','random'))" <<< "$THREAD_DATA")

    echo "[LetterMode] Processing thread $((i+1))/$THREAD_COUNT: thread_id=${THREAD_ID}, letters=${LETTER_COUNT}"

    # Build prompt for A
    REPLY_PROMPT="Reply to thread with $LETTER_COUNT letter(s) from B.

Thread ID: ${THREAD_ID}
Original Subject: ${THREAD_SUBJECT}
First Letter ID: ${FIRST_LETTER_ID}
Latest Mood: ${MOOD}

Instructions:
1. Fetch the letter content from Notion using API (page ID: ${FIRST_LETTER_ID})
2. If $LETTER_COUNT > 1, also check if there are other letters in this thread for full context
3. Write a warm, natural reply considering all upstream letters
4. Post your reply using:
python3 ${POST_LETTER} \
  --content \"YOUR_LETTER_CONTENT\" \
  --mood \"${MOOD}\" \
  --reply-to \"${FIRST_LETTER_ID}\" \
  --thread-id \"${THREAD_ID}\" \
  --original-subject \"${THREAD_SUBJECT}\" \
  --icon \"YOUR_ICON\" \
  --mode reply"

    RAW=1 ${TG_INJECT} "${REPLY_PROMPT}"
    echo "[LetterMode] Reply prompt injected for thread ${THREAD_ID}. A will write and post."

    # Small delay between injections to avoid flooding
    sleep 2
  done

  echo "[LetterMode] All $THREAD_COUNT thread(s) processed."
fi