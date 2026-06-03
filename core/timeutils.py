import logging
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Fallback only — used when a member hasn't set their timezone yet.
DEFAULT_TZ = os.getenv("TIMEZONE", "Europe/Prague")

WEEKDAYS_RU = [
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
]

_finder = None


def _get_finder():
    """Lazy-load TimezoneFinder — heavy, only needed on location share."""
    global _finder
    if _finder is None:
        from timezonefinder import TimezoneFinder

        _finder = TimezoneFinder()
    return _finder


def tz_from_coords(lat: float, lng: float) -> str:
    """IANA timezone name from coordinates, or None if undetermined."""
    try:
        return _get_finder().timezone_at(lat=lat, lng=lng)
    except Exception:
        logger.exception("tz_from_coords failed for lat=%s lng=%s", lat, lng)
        return None


def resolve_tz(tz_name: str = None) -> ZoneInfo:
    """ZoneInfo from a stored IANA name, falling back to DEFAULT_TZ."""
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            logger.warning("Unknown timezone %r, falling back to %s", tz_name, DEFAULT_TZ)
    return ZoneInfo(DEFAULT_TZ)


def now_local(tz_name: str = None) -> datetime:
    return datetime.now(resolve_tz(tz_name))


def to_local(dt: datetime, tz_name: str = None) -> datetime:
    """Naive datetimes from the DB are stored as UTC — convert to member's TZ."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(resolve_tz(tz_name))


def format_dt(dt: datetime, tz_name: str = None) -> str:
    """Local timestamp for note context: 2026-06-03 14:20."""
    local = to_local(dt, tz_name)
    return local.strftime("%Y-%m-%d %H:%M") if local else "??"


def now_prompt_str(tz_name: str = None) -> str:
    """Current date/time + weekday in Russian for the system prompt."""
    now = now_local(tz_name)
    weekday = WEEKDAYS_RU[now.weekday()]
    return now.strftime("%Y-%m-%d %H:%M") + f" ({weekday})"


def period_bounds(period: str, tz_name: str = None, now: datetime = None):
    """Локальные границы периода как (date, date) в таймзоне пользователя.

    Намерение приходит от модели, точные границы считаем здесь (детерминированно).
    Возвращает (None, None) для неизвестного периода.
    """
    today = (now or now_local(tz_name)).date()
    if period == "today":
        return today, today
    if period == "tomorrow":
        d = today + timedelta(days=1)
        return d, d
    if period == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    if period == "this_week":
        mon = today - timedelta(days=today.weekday())
        return mon, mon + timedelta(days=6)
    if period == "next_week":
        mon = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return mon, mon + timedelta(days=6)
    if period == "last_week":
        mon = today - timedelta(days=today.weekday()) - timedelta(days=7)
        return mon, mon + timedelta(days=6)
    if period == "this_month":
        first = today.replace(day=1)
        nxt = (first + timedelta(days=32)).replace(day=1)
        return first, nxt - timedelta(days=1)
    return None, None


def day_range_utc(start_date, end_date, tz_name: str = None):
    """Локальный диапазон дат → (start_utc, end_utc) datetime для сравнения с created_at (UTC)."""
    tz = resolve_tz(tz_name)
    start = datetime.combine(start_date, time.min, tzinfo=tz)
    end = datetime.combine(end_date, time.max, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)
