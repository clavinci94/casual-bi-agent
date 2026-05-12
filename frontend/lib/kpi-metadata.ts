/**
 * Manager-friendly metadata for each kpi.* view.
 *
 * Source of truth for naming + unit + ownership stays docs/kpi-catalog.yaml
 * on the backend. This file is a hand-mirrored UX layer — when a KPI is
 * added or renamed in the catalog, mirror it here. The keys MUST match
 * the view names served by /api/kpis.
 */

export type KpiOwner =
  | "Marketing"
  | "Revenue"
  | "Finance"
  | "Logistics"
  | "Quality"
  | "Retention";

/** Display label for an owner team in the UI. */
export const OWNER_LABELS: Record<KpiOwner, string> = {
  Marketing: "Marketing",
  Revenue: "Umsatz",
  Finance: "Finanzen",
  Logistics: "Logistik",
  Quality: "Qualität",
  Retention: "Kundenbindung",
};

export type KpiUnit = "percent" | "currency_chf" | "days" | "score" | "count";

export type GroupOption = {
  /** column name in the row payload */
  field: string;
  /** label shown to the user */
  label: string;
};

export type KpiMeta = {
  /** primary numeric column used for the headline + chart */
  valueField: string;
  unit: KpiUnit;
  /**
   * Multiplier applied to the raw column before formatting.
   * - Columns ending in `_pct` (DB convention) are already in percent
   *   (e.g. 40.34 means 40.34 %). With unit=percent + scale=0.01 the
   *   formatter sees a 0..1 fraction and shows "40.3 %".
   * - Currency views still expose BRL — set scale to the BRL→CHF rate
   *   (0.16 per the project ADR) and unit to currency_chf.
   * - For columns already in the target unit (e.g. gross_margin is a
   *   0..1 fraction, p95_days is days), leave scale at 1.
   */
  valueScale: number;
  /** plain-language title shown in cards + headlines */
  title: string;
  /** one-sentence plain-language description */
  description: string;
  /** what to watch out for (mirrors "typical_misinterpretation" in the yaml) */
  caveat?: string;
  /** business team responsible — used for grouping in the index */
  owner: KpiOwner;
  /** "day" or "week" — what the date column is called */
  dateField: "day" | "week";
  /** if higher = better. Drives the colour of the trend arrow. */
  higherIsBetter: boolean;
  /** default time window (days back from today / latest data) */
  defaultRangeDays: number;
  /** options the user can compare by */
  groupOptions: GroupOption[];
};

// BRL → CHF, documented in the project ADR. Mirror of biq.config.settings.brl_to_chf.
const BRL_TO_CHF = 0.16;

export const KPI_META: Record<string, KpiMeta> = {
  conversion_rate_daily: {
    valueField: "conversion_rate_pct",
    valueScale: 0.01,
    unit: "percent",
    title: "Conversion Rate",
    description:
      "Anteil der Besucher-Sitzungen, die mindestens eine Bestellung auslösen. Die zentrale Funnel-Kennzahl des Online-Shops.",
    caveat:
      "Bot-Traffic ist enthalten, solange er nicht ausdrücklich gefiltert wird.",
    owner: "Marketing",
    dateField: "day",
    higherIsBetter: true,
    defaultRangeDays: 30,
    groupOptions: [
      { field: "device", label: "Nach Endgerät" },
      { field: "channel", label: "Nach Akquisitions-Kanal" },
    ],
  },
  aov_daily: {
    valueField: "aov_brl",
    valueScale: BRL_TO_CHF,
    unit: "currency_chf",
    title: "Durchschnittlicher Bestellwert",
    description:
      "Mittlerer Umsatz pro Bestellung in CHF (umgerechnet aus BRL zum dokumentierten Festkurs). Zeigt, wie viel Kunden pro Checkout ausgeben.",
    caveat:
      "Frachtkosten sind nicht abgezogen — dafür die Bruttomarge betrachten. Der CHF-Wert basiert auf einem festen BRL-Kurs; ADR aktualisieren, wenn sich der Kurs spürbar bewegt.",
    owner: "Revenue",
    dateField: "day",
    higherIsBetter: true,
    defaultRangeDays: 30,
    groupOptions: [
      { field: "category", label: "Nach Produktkategorie" },
      { field: "region", label: "Nach Region" },
    ],
  },
  gross_margin_weekly: {
    valueField: "gross_margin",
    valueScale: 1,
    unit: "percent",
    title: "Bruttomarge",
    description:
      "Umsatz minus Wareneinstandskosten und Fracht, als Anteil am Umsatz. Der Gesundheits-Check für die Profitabilität.",
    caveat:
      "Die Wareneinstandskosten werden aus Produktgewicht × Festwert geschätzt — als Richtgrösse zu verstehen, nicht als exakter Wert.",
    owner: "Finance",
    dateField: "week",
    higherIsBetter: true,
    defaultRangeDays: 90,
    groupOptions: [
      { field: "category", label: "Nach Produktkategorie" },
      { field: "region", label: "Nach Region" },
    ],
  },
  delivery_time_p95: {
    valueField: "p95_days",
    valueScale: 1,
    unit: "days",
    title: "Lieferzeit (95 %-Perzentil)",
    description:
      "Wie lange die langsamsten 5 % der Lieferungen dauern, in Arbeitstagen. Ein Kundenerlebnis-Indikator — steigt dieser Wert, häufen sich Beschwerden.",
    owner: "Logistics",
    dateField: "day",
    higherIsBetter: false,
    defaultRangeDays: 30,
    groupOptions: [
      { field: "region", label: "Nach Region" },
      { field: "category", label: "Nach Produktkategorie" },
    ],
  },
  review_score_avg: {
    valueField: "avg_score",
    valueScale: 1,
    unit: "score",
    title: "Durchschnittliche Bewertung",
    description:
      "Mittlere Kundenbewertung (1 bis 5), gewichtet auf die letzten 90 Tage. Frühwarn-Signal für Qualitätsprobleme.",
    owner: "Quality",
    dateField: "week",
    higherIsBetter: true,
    defaultRangeDays: 90,
    groupOptions: [{ field: "category", label: "Nach Produktkategorie" }],
  },
  refund_rate: {
    valueField: "refund_rate_pct",
    valueScale: 0.01,
    unit: "percent",
    title: "Rückgabequote",
    description:
      "Anteil der Bestellungen, die storniert oder nicht verfügbar sind. Eine hohe oder steigende Quote belastet die Marge und deutet auf operative Probleme hin.",
    owner: "Finance",
    dateField: "week",
    higherIsBetter: false,
    defaultRangeDays: 90,
    groupOptions: [
      { field: "category", label: "Nach Produktkategorie" },
      { field: "region", label: "Nach Region" },
      { field: "payment_type", label: "Nach Zahlungsart" },
    ],
  },
  repeat_purchase_rate: {
    valueField: "repeat_rate_pct",
    valueScale: 0.01,
    unit: "percent",
    title: "Wiederholungskauf-Rate",
    description:
      "Anteil der Kunden, die innerhalb von 90 Tagen ein zweites Mal bestellen. Der beste einzelne Frühindikator für langfristigen Umsatz.",
    owner: "Retention",
    dateField: "week",
    higherIsBetter: true,
    defaultRangeDays: 90,
    groupOptions: [
      { field: "segment", label: "Nach Kundensegment" },
      { field: "region", label: "Nach Region" },
    ],
  },
  churn_30d: {
    valueField: "churn_rate_pct",
    valueScale: 0.01,
    unit: "percent",
    title: "30-Tage-Abwanderung",
    description:
      "Anteil der zuletzt aktiven Kunden, die in den letzten 30 Tagen aufgehört haben zu kaufen. Das Gegenteil von Kundenbindung.",
    caveat:
      "Einmal-Kunden werden tendenziell als Abwanderer überbewertet.",
    owner: "Retention",
    dateField: "week",
    higherIsBetter: false,
    defaultRangeDays: 90,
    groupOptions: [
      { field: "segment", label: "Nach Kundensegment" },
      { field: "region", label: "Nach Region" },
    ],
  },
};

export const OWNER_ORDER: KpiOwner[] = [
  "Marketing",
  "Revenue",
  "Finance",
  "Logistics",
  "Quality",
  "Retention",
];

/** Returns null if a view name has no UX metadata (so the UI can hide it). */
export function metaFor(view: string): KpiMeta | null {
  return KPI_META[view] ?? null;
}
