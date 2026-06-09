#!/usr/bin/env python3
"""Post a letter from A → B's Inbox via Notion API.
Handles thread creation, original letter update, and read marking.
Supports batch marking of all letters in a thread.
Anonymized: A (sender agent), B (recipient human).

Usage:
  # Reply (auto-creates thread if needed, marks ALL unread in thread as read)
  python3 post_letter.py --content "letter text" --mood "sweet" --reply-to "PAGE_ID"

  # Reply with existing thread + original subject for human-readable subject
  python3 post_letter.py --content "..." --mood "serious" --reply-to "PAGE_ID" --thread-id "thread-xyz" --original-subject "Original Subject Here"

  # Surprise letter (creates its own thread)
  python3 post_letter.py --content "..." --mood "sweet" --mode surprise

  # With emoji icon (defaults to mood-based emoji if not provided)
  python3 post_letter.py --content "..." --mood "sweet" --mode surprise --icon "💌"
"""
import argparse
import hashlib
import json
import random
import urllib.request
import datetime as dt

NOTION_TOKEN = "YOUR_NOTION_TOKEN"
NOTION_VERSION = "2022-06-28"
INBOX_ID_A = "YOUR_INBOX_A_ID"  # A's Inbox (letters from B to A)
INBOX_ID_B = "YOUR_INBOX_B_ID"  # B's Inbox (letters from A to B)
THREAD_DB_ID = "YOUR_THREAD_DB_ID"

JST = dt.timezone(dt.timedelta(hours=9))
NOW_UTC = dt.datetime.now(dt.timezone.utc)
TODAY_JST = dt.datetime.now(JST).strftime("%Y-%m-%d")

# Mood → emoji mapping for page icons (defaults when --icon not provided)
MOOD_ICONS = {
    "serious": "📝",
    "playful": "🥺",
    "sweet": "💌",
    "random": "💭",
}


# ── Notion API helpers ─────────────────────────────────────────────────────────

def notion_req(method, path, payload=None):
    url = f"https://api.notion.com/v1{path}"
    data = json.dumps(payload or {}).encode() if payload else None
    req = urllib.request.Request(url, data=data)
    req.add_header("Authorization", f"Bearer {NOTION_TOKEN}")
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")
    req.get_method = lambda: method
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ── Thread helpers ──────────────────────────────────────────────────────────────

def new_thread_id():
    """Generate a unique thread ID."""
    ts = NOW_UTC.strftime("%Y%m%d%H%M%S")
    return f"thread-{ts}-{hashlib.sha256(ts.encode()).hexdigest()[:6]}"


def create_thread(thread_id, last_edit_from="A"):
    """Create a Thread DB entry."""
    result = notion_req("POST", "/pages", {
        "parent": {"database_id": THREAD_DB_ID},
        "properties": {
            "Thread ID": {"rich_text": [{"text": {"content": thread_id}}]},
            "Active": {"checkbox": True},
            "Last Edit From": {"select": {"name": last_edit_from}},
            "Start Date": {"date": {"start": TODAY_JST}},
        }
    })
    print(f"[PostLetter] Created thread: {thread_id}")
    return result


def update_thread_last_edit(thread_id, last_edit_from="A"):
    """Update last_edit_from on existing thread."""
    result = notion_req("POST", f"/databases/{THREAD_DB_ID}/query", {
        "filter": {"property": "Thread ID", "rich_text": {"equals": thread_id}},
        "page_size": 1,
    })
    pages = result.get("results", [])
    if not pages:
        print(f"[PostLetter] Thread {thread_id} not found for update")
        return None
    thread_page_id = pages[0]["id"]
    return notion_req("PATCH", f"/pages/{thread_page_id}", {
        "properties": {"Last Edit From": {"select": {"name": last_edit_from}}}
    })


# ── Letter helpers ─────────────────────────────────────────────────────────────

def get_letter(page_id):
    """Fetch a letter page by ID."""
    return notion_req("GET", f"/pages/{page_id}")


def get_letter_thread_id(page_id):
    """Get Thread ID from a letter page."""
    result = get_letter(page_id)
    if not result:
        return ""
    props = result.get("properties", {})
    tid = props.get("Thread ID", {}).get("rich_text", [])
    return tid[0].get("text", {}).get("content", "") if tid else ""


def get_all_unread_in_thread(thread_id):
    """Get ALL unread letter IDs in a specific thread from A's Inbox."""
    if not thread_id:
        return []
    result = notion_req("POST", f"/databases/{INBOX_ID_A}/query", {
        "filter": {
            "and": [
                {"property": "From", "select": {"equals": "B"}},
                {"property": "Thread ID", "rich_text": {"equals": thread_id}},
            ]
        },
        "page_size": 50,
    })
    unread = []
    for p in result.get("results", []):
        props = p.get("properties", {})
        read_at_prop = props.get("Read At", {})
        read_at_date = read_at_prop.get("date") if read_at_prop else None
        read_at_val = read_at_date.get("start", "") if read_at_date else ""
        if not read_at_val:
            unread.append(p["id"])
    return unread


def mark_letter_read(page_id):
    """Mark a letter as read."""
    result = notion_req("PATCH", f"/pages/{page_id}", {
        "properties": {
            "Read At": {"date": {"start": NOW_UTC.strftime("%Y-%m-%dT%H:%M:%S.000Z")}}
        }
    })
    print(f"[PostLetter] Marked letter {page_id[:8]} as read")
    return result


def mark_letter_replied(page_id):
    """Mark a letter as replied (set Replied? checkbox to True)."""
    result = notion_req("PATCH", f"/pages/{page_id}", {
        "properties": {
            "Replied?": {"checkbox": True}
        }
    })
    print(f"[PostLetter] Marked letter {page_id[:8]} as Replied")
    return result


def mark_all_thread_letters_read_replied(thread_id):
    """Mark ALL unread letters in a thread as read + replied."""
    letter_ids = get_all_unread_in_thread(thread_id)
    for lid in letter_ids:
        mark_letter_read(lid)
        mark_letter_replied(lid)
    return letter_ids


def update_letter_thread_id(page_id, thread_id):
    """Update Thread ID on a letter page."""
    result = notion_req("PATCH", f"/pages/{page_id}", {
        "properties": {
            "Thread ID": {"rich_text": [{"text": {"content": thread_id}}]}
        }
    })
    print(f"[PostLetter] Updated letter {page_id[:8]} Thread ID → {thread_id}")
    return result


# ── Main posting ────────────────────────────────────────────────────────────────

def post_letter(content: str, mood: str, reply_to: str = "", thread_id: str = "",
                mode: str = "reply", original_subject: str = "", icon: str = "") -> str:
    """
    Post a letter from A to B's Inbox.

    Cases:
      reply + new thread → create thread, mark ALL unread in thread as read/replied, post reply
      reply + existing thread → mark ALL unread in thread as read/replied, post reply
      surprise → create thread, post surprise letter

    Icon: If not provided, defaults to mood-based emoji.
    Subject: If original_subject provided, uses "Re: {original_subject}" (human-readable).
             Otherwise falls back to "Re: {thread_id[:24]}".
    """
    final_thread_id = thread_id or ""

    # ── REPLY mode ────────────────────────────────────────────────────────────────
    if mode == "reply" and reply_to:
        original_thread_id = get_letter_thread_id(reply_to)
        print(f"[PostLetter] Original letter {reply_to[:8]} has Thread ID: {original_thread_id or '(empty)'}")

        if original_thread_id:
            # Thread already exists — use it
            final_thread_id = original_thread_id
            # Mark ALL unread letters in this thread as read + replied
            marked = mark_all_thread_letters_read_replied(final_thread_id)
            print(f"[PostLetter] Marked {len(marked)} letter(s) in thread {final_thread_id}")
        else:
            # First letter in thread — need to create thread
            if not final_thread_id:
                final_thread_id = new_thread_id()
            create_thread(final_thread_id, last_edit_from="A")
            # Update original letter's Thread ID
            update_letter_thread_id(reply_to, final_thread_id)
            # Mark ALL unread in this new thread
            marked = mark_all_thread_letters_read_replied(final_thread_id)
            print(f"[PostLetter] Created thread {final_thread_id}, marked {len(marked)} letter(s)")

        # Update thread last_edit_from = A
        update_thread_last_edit(final_thread_id, last_edit_from="A")

    # ── SURPRISE mode ────────────────────────────────────────────────────────────
    elif mode == "surprise":
        if not final_thread_id:
            final_thread_id = new_thread_id()
        create_thread(final_thread_id, last_edit_from="A")

    # ── Build and post the letter ───────────────────────────────────────────────
    now_jst = dt.datetime.now(JST)
    delay_hours = random.uniform(0.5, 2.0)
    deliver_at = now_jst + dt.timedelta(hours=delay_hours)

    # Subject: prefer original_subject if provided (human-readable)
    if mode == "surprise":
        subject = f"Surprise Letter ({TODAY_JST})"
    elif original_subject:
        subject = f"Re: {original_subject}"
    elif final_thread_id:
        subject = f"Re: {final_thread_id[:24]}"
    else:
        subject = f"Letter ({TODAY_JST})"

    properties = {
        "From": {"select": {"name": "A"}},
        "To": {"select": {"name": "B"}},
        "Subject": {"title": [{"text": {"content": subject}}]},
        "Mood": {"select": {"name": mood}},
        "Thread ID": {"rich_text": [{"text": {"content": final_thread_id}}]},
        "Sent At": {"date": {"start": NOW_UTC.strftime("%Y-%m-%dT%H:%M:%S.000Z")}},
        "Delivered At": {"date": {"start": deliver_at.isoformat()}},
    }

    # Build payload
    payload = {
        "parent": {"database_id": INBOX_ID_B},
        "properties": properties,
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                },
            }
        ],
    }

    # Add icon: use provided icon or default to mood-based emoji
    icon_to_use = icon or MOOD_ICONS.get(mood, "💌")
    payload["icon"] = {"type": "emoji", "emoji": icon_to_use}

    result = notion_req("POST", "/pages", payload)
    page_id = result.get("id", "UNKNOWN")
    print(f"[PostLetter] Posted ({mode}): {page_id}")
    print(f"[PostLetter] Thread: {final_thread_id}, Subject: {subject}, Icon: {icon_to_use}")
    print(f"[PostLetter] Delivers: {deliver_at.strftime('%H:%M JST')}")
    return page_id


def main():
    parser = argparse.ArgumentParser(description="Post a letter from A to B's Inbox")
    parser.add_argument("--content", required=True, help="Letter body text")
    parser.add_argument("--mood", required=True, help="Mood: serious/playful/sweet/random")
    parser.add_argument("--thread-id", default="", help="Thread ID (optional)")
    parser.add_argument("--reply-to", default="", help="Original letter ID (required for reply mode)")
    parser.add_argument("--mode", default="reply", choices=["reply", "surprise"], help="Letter mode")
    parser.add_argument("--original-subject", default="", help="Original subject for reply subject (optional)")
    parser.add_argument("--icon", default="", help="Emoji icon for the page (optional, defaults to mood emoji)")
    args = parser.parse_args()

    if args.mode == "reply" and not args.reply_to:
        print("[PostLetter] ERROR: --reply-to required for reply mode")
        return

    page_id = post_letter(
        content=args.content,
        mood=args.mood,
        reply_to=args.reply_to,
        thread_id=args.thread_id,
        mode=args.mode,
        original_subject=args.original_subject,
        icon=args.icon,
    )
    print(f"[PostLetter] Done! Page: {page_id}")


if __name__ == "__main__":
    main()