"use client";

import { useState } from "react";
import useSWR from "swr";
import { CalendarClock } from "lucide-react";
import { api } from "@/lib/api";
import { Card, Empty, ErrorMessage } from "@/components/ui";
import type { CommerceEvent } from "@/lib/types";

type Country = "CH" | "DE" | "AT";

const KIND_META: Record<
  string,
  { label: string; dot: string; pillBg: string }
> = {
  commerce_event: {
    label: "Verkaufstag",
    dot: "bg-[var(--color-warning)]",
    pillBg:
      "bg-[color-mix(in_oklch,var(--color-warning)_16%,var(--color-surface))] text-[var(--color-warning)]",
  },
  national_holiday: {
    label: "Nationalfeiertag",
    dot: "bg-[var(--color-danger)]",
    pillBg:
      "bg-[color-mix(in_oklch,var(--color-danger)_14%,var(--color-surface))] text-[var(--color-danger)]",
  },
  religious: {
    label: "Feiertag",
    dot: "bg-[var(--color-accent)]",
    pillBg:
      "bg-[color-mix(in_oklch,var(--color-accent)_14%,var(--color-surface))] text-[var(--color-accent)]",
  },
};

function kindMeta(kind: string) {
  return (
    KIND_META[kind] ?? {
      label: kind,
      dot: "bg-[var(--color-muted)]",
      pillBg: "bg-[var(--color-bg)] text-[var(--color-muted)]",
    }
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso + "T00:00:00").toLocaleDateString("de-CH", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function formatCountdown(days: number): string {
  if (days <= 0) return "heute";
  if (days === 1) return "morgen";
  if (days < 14) return `in ${days} Tagen`;
  if (days < 60) {
    const weeks = Math.round(days / 7);
    return `in ${weeks} Wochen`;
  }
  if (days < 365) {
    const months = Math.round(days / 30);
    return `in ${months} Monaten`;
  }
  return `in ${Math.round(days / 365)} Jahr+`;
}

export function CommerceCalendarWidget() {
  const [country, setCountry] = useState<Country>("CH");

  const { data, error, isLoading } = useSWR(
    ["commerce-calendar", country],
    () => api.externalCommerceCalendar({ country, limit: 8 }),
    { revalidateOnFocus: false },
  );

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="size-8 rounded-lg bg-[var(--color-bg)] flex items-center justify-center shrink-0">
            <CalendarClock className="size-4" />
          </span>
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
              Termine
            </div>
            <h2 className="text-base font-semibold">Commerce-Kalender</h2>
          </div>
        </div>
        <CountrySwitch value={country} onChange={setCountry} />
      </div>

      {isLoading ? (
        <div className="text-sm text-[var(--color-muted)] animate-pulse">
          Lade Termine …
        </div>
      ) : error ? (
        <ErrorMessage error={error} />
      ) : !data?.events?.length ? (
        <Empty>Keine Termine im Vorausschau-Fenster.</Empty>
      ) : (
        <EventList events={data.events} />
      )}

      <div className="mt-4 text-[11px] text-[var(--color-muted)]">
        {country === "CH"
          ? "Bundesfeiertage + Commerce-Termine"
          : country === "DE"
            ? "Gesetzliche Feiertage (DE) + Commerce-Termine"
            : "Gesetzliche Feiertage (AT) + Commerce-Termine"}
      </div>
    </Card>
  );
}

function CountrySwitch({
  value,
  onChange,
}: {
  value: Country;
  onChange: (c: Country) => void;
}) {
  const opts: Country[] = ["CH", "DE", "AT"];
  return (
    <div className="inline-flex rounded-md border border-[var(--color-border)] overflow-hidden shrink-0">
      {opts.map((c) => (
        <button
          key={c}
          type="button"
          onClick={() => onChange(c)}
          className={`px-2.5 py-1 text-xs font-medium ${
            c === value
              ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)]"
              : "text-[var(--color-muted)] hover:bg-[var(--color-bg)]"
          }`}
          aria-pressed={c === value}
        >
          {c}
        </button>
      ))}
    </div>
  );
}

function EventList({ events }: { events: CommerceEvent[] }) {
  return (
    <ul className="space-y-2.5">
      {events.map((e, i) => (
        <EventRow key={`${e.name}-${e.date}-${i}`} event={e} />
      ))}
    </ul>
  );
}

function EventRow({ event }: { event: CommerceEvent }) {
  const meta = kindMeta(event.kind);
  const imminent = event.days_away <= 2;

  return (
    <li className="flex gap-3 items-start">
      <span
        className={`size-2 rounded-full ${meta.dot} mt-2 shrink-0`}
        aria-hidden
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <div className="text-sm font-semibold leading-tight truncate">
            {event.name}
          </div>
          <span
            className={`text-[11px] px-1.5 py-0.5 rounded-full font-medium shrink-0 ${
              imminent
                ? "bg-[color-mix(in_oklch,var(--color-danger)_14%,var(--color-surface))] text-[var(--color-danger)]"
                : meta.pillBg
            }`}
          >
            {formatCountdown(event.days_away)}
          </span>
        </div>
        <div className="text-[11px] text-[var(--color-muted)] mt-0.5 tabular-nums">
          {formatDate(event.date)} · {meta.label}
        </div>
        {event.note ? (
          <p
            className="text-xs text-[var(--color-muted)] mt-1 leading-relaxed line-clamp-2"
            title={event.note}
          >
            {event.note}
          </p>
        ) : null}
      </div>
    </li>
  );
}
