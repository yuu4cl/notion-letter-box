#!/usr/bin/env python3
"""Post a letter from A → B's Inbox via Notion API.
Handles thread creation, original letter update, and read marking.

Usage:
  # Reply to A's letter (auto-creates thread if needed)
  python3 post_letter.py --content "letter text" --mood "sweet" --reply-to "PAGE_ID"

  # Surprise letter (creates its own thread)
  python3 post_letter.py --content "..." --mood "sweet" --mode surprise

  # Reply with existing thread
  python3 post_letter.py --content "..." --mood "serious" --reply-to "PAGE_ID" --thread-id "thread-xyz"
"""
import argparse
import hashlib
import json
import os
import random
import urllib.request
import datetime as dt
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_VERSION = os.environ.get("NOTION_VERSION", "2022-06-28")
INBOX_ID_A = os.environ.get("INBOX_ID_A", "")
INBOX_ID_B = os.environ.get("INBOX_ID_B", "")
THREAD_DB_ID = os.environ.get("THREAD_DB_ID", "")

JST = dt.timezone(dt.timedelta(hours=9))
NOW_UTC = dt.datetime.now(dt.timezone.utc)
TODAY_JST = dt.datetime.now(JST).strftime("%Y-%m-%d")


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
    return notion_req("GET", f"/pages/{page_id}")


def get_letter_thread_id(page_id):
    """Get Thread ID from a letter page."""
    result = get_letter(page_id)
    if not result:
        return None
    props = result.get("properties", {})
    tid = props.get("Thread ID", {}).get("rich_text", [])
    if tid:
        return tid[0].get("text", {}).get("content", "")
    return None


def mark_letter_read(page_id):
    """Mark a letter as read."""
    result = notion_req("PATCH", f"/pages/{page_id}", {
        "properties": {
            "Read At": {"date": {"start": NOW_UTC.strftime("%Y-%m-%dT%H:%M:%S.000Z")}}
        }
    })
    print(f"[PostLetter] Marked letter {page_id[:8]} as read")
    return result


def update_letter_thread_id(page_id, thread_id):
    """Update Thread ID on a letter page."""
    result = notion_req("PATCH", f"/pages/{page_id}", {
        "properties": {
            "Thread ID": {"rich_text": [{"text": {"content": thread_id}}]}
        }
    })
    print(f"[PostLetter] Updated letter {page_id[:8]} Thread ID → {thread_id}")
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


# ── Main posting ────────────────────────────────────────────────────────────────

def post_letter(content: str, mood: str, reply_to: str = "", thread_id: str = "",
                mode: str = "reply") -> str:
    """
    Post a letter from A to B's Inbox.

    Cases:
      reply + no existing Thread ID → create thread, update original, post reply
      reply + Thread ID exists → mark read + replied, post reply
      surprise → create thread, post surprise letter
    """
    final_thread_id = thread_id or ""

    # ── REPLY mode ─────────────────────────────────────────────────────────────
    if mode == "reply" and reply_to:
        original_thread_id = get_letter_thread_id(reply_to)
        print(f"[PostLetter] Original letter {reply_to[:8]} has Thread ID: {original_thread_id or '(empty)'}")

        if original_thread_id:
            final_thread_id = original_thread_id
            mark_letter_read(reply_to)
            mark_letter_replied(reply_to)
        else:
            if not final_thread_id:
                final_thread_id = new_thread_id()
            create_thread(final_thread_id, last_edit_from="A")
            update_letter_thread_id(reply_to, final_thread_id)
            mark_letter_read(reply_to)
            mark_letter_replied(reply_to)

        update_thread_last_edit(final_thread_id, last_edit_from="A")

    # ── SURPRISE mode ───────────────────────────────────────────────────────────
    elif mode == "surprise":
        if not final_thread_id:
            final_thread_id = new_thread_id()
        create_thread(final_thread_id, last_edit_from="A")

    # ── Build and post the letter ───────────────────────────────────────────────
    now_jst = dt.datetime.now(JST)
    delay_hours = random.uniform(0.5, 2.0)
    deliver_at = now_jst + dt.timedelta(hours=delay_hours)

    if mode == "surprise":
        subject = f"Surprise Letter ({TODAY_JST})"
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

    result = notion_req("POST", "/pages", payload)
    page_id = result.get("id", "UNKNOWN")
    print(f"[PostLetter] Posted ({mode}): {page_id}")
    print(f"[PostLetter] Thread: {final_thread_id}, Delivers: {deliver_at.strftime('%H:%M JST')}")
    return page_id


def main():
    parser = argparse.ArgumentParser(description="Post a letter from A to B's Inbox")
    parser.add_argument("--content", required=True, help="Letter body text")
    parser.add_argument("--mood", required=True, help="Mood: serious/playful/sweet/random")
    parser.add_argument("--thread-id", default="", help="Thread ID (optional)")
    parser.add_argument("--reply-to", default="", help="Original letter ID (required for reply mode)")
    parser.add_argument("--mode", default="reply", choices=["reply", "surprise"], help="Letter mode")
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
    )
    print(f"[PostLetter] Done! Page: {page_id}")


if __name__ == "__main__":
    main()