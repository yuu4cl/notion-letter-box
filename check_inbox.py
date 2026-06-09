#!/usr/bin/env python3
"""Check A's Inbox for unread letters from B.
Returns all unread letters grouped by thread (for batch processing).
Mood is represented by page emoji icon only (no Mood property in DB).
"""
import json
import urllib.request

NOTION_TOKEN = "YOUR_NOTION_TOKEN"
INBOX_ID = "YOUR_INBOX_A_ID"  # A's Inbox (letters from B to A)


def notion_req(method, path, payload=None):
    url = f"https://api.notion.com/v1{path}"
    data = json.dumps(payload or {}).encode() if payload else None
    req = urllib.request.Request(url, data=data)
    req.add_header("Authorization", f"Bearer {NOTION_TOKEN}")
    req.add_header("Notion-Version", "2022-06-28")
    req.add_header("Content-Type", "application/json")
    req.get_method = lambda: method
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_letter(page_id):
    """Fetch a letter page properties."""
    return notion_req("GET", f"/pages/{page_id}")


def get_letter_thread_id(page_id):
    """Get Thread ID from a letter page."""
    result = get_letter(page_id)
    if not result:
        return ""
    props = result.get("properties", {})
    tid = props.get("Thread ID", {}).get("rich_text", [])
    return tid[0].get("text", {}).get("content", "") if tid else ""


def check_unread_grouped():
    """
    Return all unread letters from B, grouped by thread.
    Each thread entry represents one conversation that A should respond to with ONE reply.
    A will fetch full content as needed via --reply-to.
    """
    # Fetch all unread (page_size=50 to cover most cases)
    result = notion_req("POST", f"/databases/{INBOX_ID}/query", {
        "filter": {"property": "From", "select": {"equals": "B"}},
        "sorts": [{"property": "Delivered At", "direction": "ascending"}],
        "page_size": 50,
    })

    # Collect all unread letters
    all_unread = []
    for p in result.get("results", []):
        props = p.get("properties", {})

        # Safe extraction: Read At can have date: None
        read_at_prop = props.get("Read At", {})
        read_at_date = read_at_prop.get("date") if read_at_prop else None
        read_at_val = read_at_date.get("start", "") if read_at_date else ""

        if read_at_val:
            continue  # already read, skip

        subject = props.get("Subject", {}).get("title", [])
        subject_text = subject[0].get("text", {}).get("content", "") if subject else "(no subject)"

        thread_id = props.get("Thread ID", {}).get("rich_text", [])
        thread_text = thread_id[0].get("text", {}).get("content", "") if thread_id else ""

        delivered_prop = props.get("Delivered At", {})
        delivered_date = delivered_prop.get("date") if delivered_prop else None
        delivered_val = delivered_date.get("start", "") if delivered_date else ""

        all_unread.append({
            "id": p["id"],
            "subject": subject_text,
            "thread": thread_text,  # empty string = new thread
            "delivered": delivered_val,
        })

    # Group by thread_id (empty thread_id = new thread for that letter)
    # Each group = one "conversation" that A should respond to with ONE reply
    threads = {}
    for letter in all_unread:
        tid = letter["thread"] if letter["thread"] else f"_new_{letter['id']}_"
        if tid not in threads:
            threads[tid] = []
        threads[tid].append(letter)

    # Build grouped output
    grouped = []
    for tid, letters in threads.items():
        # Thread subject = first letter's subject
        thread_subject = letters[0]["subject"] if letters else "Unknown"

        grouped.append({
            "thread_id": tid if not tid.startswith("_new_") else "",
            "thread_subject": thread_subject,
            "letter_count": len(letters),
            "first_letter_id": letters[0]["id"],
        })

    return grouped


if __name__ == "__main__":
    grouped = check_unread_grouped()
    print(json.dumps(grouped, ensure_ascii=False, indent=2))
    print(f"\nTotal threads with unread: {len(grouped)}", file=__import__("sys").stderr)