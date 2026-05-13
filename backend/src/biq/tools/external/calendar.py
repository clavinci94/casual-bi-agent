"""Commerce calendar: upcoming events that matter to a Shopify shop.

Two sources merged:

1. National statutory holidays via the `holidays` package — they affect
   shipping cut-offs, customer service load, and conversion patterns
   (people shop more on bank holidays, but warehouses ship less).

2. Commerce-cycle dates that recur every year but aren't legal holidays:
   Black Friday, Cyber Monday, Singles' Day, Mother's / Father's Day,
   Valentine's, etc. These are hard-coded because they are deterministic
   relative to the calendar.

The merchant gets one chronological list with countdowns, so they can
see at a glance "in 28 days is Father's Day — start the campaign now".
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

import holidays

EventKind = Literal["national_holiday", "commerce_event", "religious"]


@dataclass
class _CommerceEvent:
    """A recurring commerce date and how to compute it for any year."""

    name: str
    note: str
    countries: tuple[str, ...]  # ("CH", "DE", "AT") or subset
    # date_for(year) returns the date in that year
    date_for_year: Any

    def for_year(self, year: int) -> date:
        return self.date_for_year(year)


# --- date math for movable feasts ------------------------------------


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth weekday (Mon=0..Sun=6) of a given month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Return the last given weekday in the month."""
    days_in_month = monthrange(year, month)[1]
    last = date(year, month, days_in_month)
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _us_thanksgiving(year: int) -> date:
    # 4th Thursday of November (US) — Black Friday is the day after.
    return _nth_weekday_of_month(year, 11, weekday=3, n=4)


def _black_friday(year: int) -> date:
    return _us_thanksgiving(year) + timedelta(days=1)


def _cyber_monday(year: int) -> date:
    return _us_thanksgiving(year) + timedelta(days=4)


def _mothers_day_de_ch(year: int) -> date:
    # CH/DE: 2nd Sunday of May. (DE shifts to 4th Sunday if it falls on
    # Pentecost, but that hasn't happened in decades — accept the edge case.)
    return _nth_weekday_of_month(year, 5, weekday=6, n=2)


def _fathers_day_ch(year: int) -> date:
    # CH: 1st Sunday in June. (DE uses Christi Himmelfahrt — already covered
    # by the holidays package, no need to duplicate.)
    return _nth_weekday_of_month(year, 6, weekday=6, n=1)


# --- commerce events -------------------------------------------------

_COMMERCE_EVENTS: list[_CommerceEvent] = [
    _CommerceEvent(
        name="Valentinstag",
        note="Geschenk-Kategorien promoten, Lieferversprechen ≤2 Tage vor 14.2.",
        countries=("CH", "DE", "AT"),
        date_for_year=lambda y: date(y, 2, 14),
    ),
    _CommerceEvent(
        name="Muttertag",
        note="Promo-Window 3 Wochen vorher starten — Express-Versand-Hinweis.",
        countries=("CH", "DE", "AT"),
        date_for_year=_mothers_day_de_ch,
    ),
    _CommerceEvent(
        name="Vatertag (CH)",
        note="CH-spezifisch (1. Sonntag im Juni). Promo-Window 2-3 Wochen vorher.",
        countries=("CH",),
        date_for_year=_fathers_day_ch,
    ),
    _CommerceEvent(
        name="Singles' Day",
        note="Wachsende E-Commerce-Aktion in der DACH-Region — 24h-Sale prüfen.",
        countries=("CH", "DE", "AT"),
        date_for_year=lambda y: date(y, 11, 11),
    ),
    _CommerceEvent(
        name="Black Friday",
        note="Umsatzstärkster Tag des Jahres — Bestände, Marketing, Server-Kapazität "
        "und Versandpartner müssen 4+ Wochen vorher vorbereitet sein.",
        countries=("CH", "DE", "AT"),
        date_for_year=_black_friday,
    ),
    _CommerceEvent(
        name="Cyber Monday",
        note="Online-only Verlängerung des BFCM-Wochenendes.",
        countries=("CH", "DE", "AT"),
        date_for_year=_cyber_monday,
    ),
    _CommerceEvent(
        name="Heiligabend",
        note="Letzter Versandtag in CH/DE typischerweise 22.12. — Cutoff klar kommunizieren.",
        countries=("CH", "DE", "AT"),
        date_for_year=lambda y: date(y, 12, 24),
    ),
    _CommerceEvent(
        name="Stephanstag / 2. Weihnachtstag",
        note="Wichtigster Retouren- und Gutschein-Einlöse-Tag.",
        countries=("CH", "DE", "AT"),
        date_for_year=lambda y: date(y, 12, 26),
    ),
    _CommerceEvent(
        name="Silvester",
        note="Letzte Verkaufstage des Geschäftsjahres — Steuer-relevante Promotionen prüfen.",
        countries=("CH", "DE", "AT"),
        date_for_year=lambda y: date(y, 12, 31),
    ),
]


# --- main entry point ------------------------------------------------


def _kind_for_holiday(name: str) -> EventKind:
    """Classify a national-holiday name as religious or strictly civic.
    Pure cosmetics for the UI tone — has no functional consequence.
    """
    religious_markers = (
        "weihnachten",
        "karfreitag",
        "ostern",
        "ostermontag",
        "pfingst",
        "auffahrt",
        "himmelfahrt",
        "fronleichnam",
        "allerheiligen",
        "maria",
    )
    n = name.lower()
    return "religious" if any(m in n for m in religious_markers) else "national_holiday"


def commerce_calendar(
    country: str = "CH",
    *,
    limit: int = 8,
    window_days: int = 270,
    today: date | None = None,
) -> dict[str, Any]:
    """Return the upcoming commerce + holiday calendar for one country.

    Args:
        country: ISO code — CH, DE, AT supported. Anything else: only
            commerce events that are flagged for that country (effectively
            falls back to the global set).
        limit: maximum number of events to return.
        window_days: only consider events in [today, today + window_days).
        today: override for testing; defaults to date.today().

    Returns:
        Sorted (by date) list under "events", each with name, date,
        days_away, kind, note, country.
    """
    today = today or date.today()
    horizon = today + timedelta(days=window_days)
    years = sorted({today.year, horizon.year})

    items: list[dict[str, Any]] = []

    # National holidays
    try:
        national = holidays.country_holidays(country, years=years)
        for d, name in national.items():
            if today <= d < horizon:
                items.append(
                    {
                        "name": name,
                        "date": d.isoformat(),
                        "days_away": (d - today).days,
                        "kind": _kind_for_holiday(name),
                        "note": "Versand und Support pausieren — Lieferversprechen anpassen.",
                        "country": country,
                    }
                )
    except (KeyError, NotImplementedError):
        # Unknown country code: no national holidays, just commerce events.
        pass

    # Commerce events
    for event in _COMMERCE_EVENTS:
        if country not in event.countries:
            continue
        for y in years:
            try:
                d = event.for_year(y)
            except Exception:
                continue
            if today <= d < horizon:
                items.append(
                    {
                        "name": event.name,
                        "date": d.isoformat(),
                        "days_away": (d - today).days,
                        "kind": "commerce_event",
                        "note": event.note,
                        "country": country,
                    }
                )

    # Deduplicate by (name, date) — a few commerce events overlap with the
    # holidays package (e.g. some DE subdivisions list Heiligabend).
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for it in items:
        key = (it["name"].lower(), it["date"])
        if key not in seen:
            seen.add(key)
            deduped.append(it)

    deduped.sort(key=lambda it: it["date"])

    return {
        "country": country,
        "today": today.isoformat(),
        "window_days": window_days,
        "events": deduped[:limit],
    }
