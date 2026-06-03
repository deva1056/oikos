import logging
from datetime import date

from core.ai import extract_search_profile
from core.memory import (
    CONTEXT_NOTE_LIMIT,
    _parse_tags,
    get_all_tags,
    normalize_tag,
    query_notes,
    tag_value,
)
from core.timeutils import day_range_utc, format_dt, period_bounds

logger = logging.getLogger(__name__)

SELECTED_LIMIT = 30


def _resolve_dates(profile: dict, tz_name: str):
    """Из профиля → (date_field, lo, hi) для SQL. Период → Python-границы; иначе ISO от модели."""
    period = profile.get("period")
    sd = ed = None
    if period:
        sd, ed = period_bounds(period, tz_name)
    elif profile.get("date_from") and profile.get("date_to"):
        try:
            sd = date.fromisoformat(profile["date_from"])
            ed = date.fromisoformat(profile["date_to"])
        except ValueError:
            sd = ed = None

    if not sd:
        return None, None, None

    # по умолчанию ищем по дате события; created — только если модель явно попросила
    field = "created_at" if profile.get("date_field") == "created" else "event_date"
    if field == "event_date":
        return field, sd, ed
    lo, hi = day_range_utc(sd, ed, tz_name)
    return field, lo, hi


def get_relevant_context(question: str, viewer_tz: str = None) -> str:
    """Вопрос → профиль поиска → срез заметок по дате/тегам/людям → текст для LLM.

    Сам по себе устойчив: при сбое профайлера откатывается на последние заметки.
    """
    known = [t for t, _ in get_all_tags()]
    try:
        profile = extract_search_profile(question, viewer_tz, known)
    except Exception as e:  # noqa: BLE001
        logger.error("search profile failed: %s", type(e).__name__)
        profile = {}

    # дата — жёсткий фильтр (на уровне SQL)
    field, lo, hi = _resolve_dates(profile, viewer_tz)
    rows = query_notes(field, lo, hi, CONTEXT_NOTE_LIMIT)

    # автор — жёсткий фильтр (структурный, надёжный)
    authors = [a.strip().lower() for a in profile.get("authors", []) if a.strip()]
    if authors:
        rows = [
            r for r in rows
            if any(a in (r["author_name"] or "").lower() or (r["author_name"] or "").lower() in a
                   for a in authors)
        ]

    # теги/люди — МЯГКИЙ фильтр: сужают, когда совпали по значению, но не голодят
    # модель, если не совпали (теги разрежены/непоследовательны) → откат к набору.
    wanted = {tag_value(normalize_tag(t)) for t in profile.get("tags_any", [])}
    wanted |= {tag_value(normalize_tag(t)) for t in profile.get("tags_all", [])}
    wanted |= {tag_value(normalize_tag(p)) for p in profile.get("people", [])}
    wanted.discard("")
    if wanted:
        tag_hits = [r for r in rows if wanted & {tag_value(t) for t in _parse_tags(r["tags"])}]
        rows = tag_hits or rows  # soft: пусто по тегам → оставляем то, что есть

    selected = sorted(rows, key=lambda r: r["created_at"])[:SELECTED_LIMIT]

    # диагностика (без текста заметок): что извлёк профиль и сколько ушло модели
    logger.info(
        "retrieval: profile=%s field=%s -> selected=%d",
        {k: v for k, v in profile.items() if v}, field, len(selected),
    )

    if not selected:
        return "Подходящих заметок не найдено."

    return "\n".join(
        f"[{format_dt(r['created_at'], viewer_tz)}] {r['author_name']}: {r['text']}"
        for r in selected
    )
