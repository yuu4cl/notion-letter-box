#!/usr/bin/env python3
"""Check B's Inbox for unread letters from A."""
import json
import os
import urllib.request
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
INBOX_ID = os.environ.get("INBOX_ID_B", "")


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


def check_unread_from_A():
    """Return list of unread letters from A in B's Inbox."""
    result = notion_req("POST", f"/databases/{INBOX_ID}/query", {
        "filter": {"property": "From", "select": {"equals": "A"}},
        "sorts": [{"property": "Delivered At", "direction": "descending"}],
        "page_size": 5,
    })

    unread = []
    for p in result.get("results", []):
        props = p.get("properties", {})

        # Safe extraction: Read At can have date: None in Notion API
        read_at_prop = props.get("Read At", {})
        read_at_date = read_at_prop.get("date") if read_at_prop else None
        read_at_val = read_at_date.get("start", "") if read_at_date else ""

        if not read_at_val:
            subject = props.get("Subject", {}).get("title", [])
            subject_text = subject[0].get("text", {}).get("content", "") if subject else "(no subject)"

            thread_id = props.get("Thread ID", {}).get("rich_text", [])
            thread_text = thread_id[0].get("text", {}).get("content", "") if thread_id else ""

            delivered_prop = props.get("Delivered At", {})
            delivered_date = delivered_prop.get("date") if delivered_prop else None
            delivered_val = delivered_date.get("start", "") if delivered_date else ""

            mood = props.get("Mood", {}).get("select", {}).get("name", "")

            unread.append({
                "id": p["id"],
                "subject": subject_text,
                "thread": thread_text,
                "delivered": delivered_val,
                "mood": mood,
            })

    return unread


if __name__ == "__main__":
    unread = check_unread_from_A()
    print(json.dumps(unread))
    print(f"Unread count: {len(unread)}", file=__import__("sys").stderr)