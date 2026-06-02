import os

_raw = os.getenv("ALLOWED_IDS", "")
ALLOWED_IDS: set[str] = {uid.strip() for uid in _raw.split(",") if uid.strip()}


def is_allowed(user_id: str | int) -> bool:
    return str(user_id) in ALLOWED_IDS
