import json
import os
from datetime import datetime

MEMORY_FILE = os.getenv("MEMORY_FILE", "data/memory.json")


def load_memory() -> dict:
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"members": {}, "notes": []}


def save_memory(memory: dict):
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def get_member_name(memory: dict, user_id) -> str:
    return memory["members"].get(str(user_id), {}).get("name")


def register_member(memory: dict, user_id, name: str):
    memory["members"][str(user_id)] = {"name": name}
    save_memory(memory)


def add_note(memory: dict, user_id, author_name: str, text: str, tags: list) -> dict:
    note = {
        "id": len(memory["notes"]) + 1,
        "author_id": str(user_id),
        "author": author_name,
        "text": text,
        "tags": tags,
        "timestamp": datetime.now().isoformat(),
    }
    memory["notes"].append(note)
    save_memory(memory)
    return note


def format_for_ai(memory: dict) -> str:
    if not memory["notes"]:
        return "Заметок пока нет."
    lines = []
    for note in memory["notes"]:
        ts = note["timestamp"][:16].replace("T", " ")
        tags_str = ", ".join(note["tags"]) if note["tags"] else "—"
        lines.append(f"[{ts}] {note['author']}: {note['text']}\n  → теги: {tags_str}")
    return "\n\n".join(lines)
