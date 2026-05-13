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

/** Key into the lucide icon set (see components/kpi-icon.tsx). */
export type KpiIconKey =
  | "cart"
  | "wallet"
  | "piggy"
  | "truck"
  | "star"
  | "undo"
  | "repeat"
  | "churn";

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
   * - _pct columns (DB convention) are 0..100; set scale=0.01 so the
   *   formatter sees a 0..1 fraction and renders "40.3 %".
   * - Currency views still expose BRL — set scale to the BRL→CHF rate
   *   (0.16 per the project ADR) and unit to currency_chf.
   * - For columns already in the target unit (gross_margin is a 0..1
   *   fraction, p95_days is days), leave scale at 1.
   */
  valueScale: number;
  /** Short, manager-readable title shown on cards. Keep ≤ 3 words. */
  title: string;
  /** One-line "what does this measure" — shown right under the title. */
  subtitle: string;
  /** Longer description used on the detail page only. */
  description: string;
  /** What to watch out for (mirrors "typical_misinterpretation"). */
  caveat?: string;
  /** Business team responsible — used for grouping. */
  owner: KpiOwner;
  /** Visual icon. */
  icon: KpiIconKey;
  /** "day" or "week" — what the date column is called. */
  dateField: "day" | "week";
  /** If higher = better. Drives the colour of the trend arrow. */
  higherIsBetter: boolean;
  /** Default time window. */
  defaultRangeDays: number;
  /** Options the user can compare by. */
  groupOptions: GroupOption[];
};

// BRL → CHF, documented in the project ADR. Mirror of biq.config.settings.brl_to_chf.
const BRL_TO_CHF = 0.16;

export const KPI_META: Record<string, KpiMeta> = {
  conversion_rate_daily: {
    valueField: "conversion_rate_pct",
    valueScale: 0.01,
    unit: "percent",
    title: "Kaufabschlüsse",
    subtitle: "Wie viele Besucher tatsächlich kaufen",
    description:
      "Anteil der Besucher-Sitzungen, die mindestens eine Bestellung auslösen. Die zentrale Funnel-Kennzahl des Online-Shops.",
    caveat:
      "Bot-Traffic ist enthalten, solange er nicht ausdrücklich gefiltert wird.",
    owner: "Marketing",
    icon: "cart",
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
    title: "Bestellwert",
    subtitle: "Was ein Kunde im Schnitt ausgibt",
    description:
      "Mittlerer Umsatz pro Bestellung in CHF (umgerechnet aus BRL zum dokumentierten Festkurs). Zeigt, wie viel Kunden pro Checkout ausgeben.",
    caveat:
      "Frachtkosten sind nicht abgezogen — dafür die Bruttomarge betrachten. Der CHF-Wert basiert auf einem festen BRL-Kurs; ADR aktualisieren, wenn sich der Kurs spürbar bewegt.",
    owner: "Revenue",
    icon: "wallet",
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
    subtitle: "Was vom Umsatz übrig bleibt",
    description:
      "Umsatz minus Wareneinstandskosten und Fracht, als Anteil am Umsatz. Der Gesundheits-Check für die Profitabilität.",
    caveat:
      "Die Wareneinstandskosten werden aus Produktgewicht × Festwert geschätzt — als Richtgrösse zu verstehen, nicht als exakter Wert.",
    owner: "Finance",
    icon: "piggy",
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
    title: "Lieferzeit",
    subtitle: "Wie lange die langsamsten Lieferungen brauchen",
    description:
      "Wie lange die langsamsten 5 % der Lieferungen dauern, in Arbeitstagen. Ein Kundenerlebnis-Indikator — steigt dieser Wert, häufen sich Beschwerden.",
    owner: "Logistics",
    icon: "truck",
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
    title: "Kundenzufriedenheit",
    subtitle: "Durchschnittliche Sterne-Bewertung",
    description:
      "Mittlere Kundenbewertung (1 bis 5), gewichtet auf die letzten 90 Tage. Frühwarn-Signal für Qualitätsprobleme.",
    owner: "Quality",
    icon: "star",
    dateField: "week",
    higherIsBetter: true,
    defaultRangeDays: 90,
    groupOptions: [{ field: "category", label: "Nach Produktkategorie" }],
  },
  refund_rate: {
    valueField: "refund_rate_pct",
    valueScale: 0.01,
    unit: "percent",
    title: "Rückgaben",
    subtitle: "Anteil stornierter oder retournierter Bestellungen",
    description:
      "Anteil der Bestellungen, die storniert oder nicht verfügbar sind. Eine hohe oder steigende Quote belastet die Marge und deutet auf operative Probleme hin.",
    owner: "Finance",
    icon: "undo",
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
    title: "Wiederkäufer",
    subtitle: "Kunden, die ein zweites Mal bestellen",
    description:
      "Anteil der Kunden, die innerhalb von 90 Tagen ein zweites Mal bestellen. Der beste einzelne Frühindikator für langfristigen Umsatz.",
    owner: "Retention",
    icon: "repeat",
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
    title: "Abwanderung",
    subtitle: "Kunden, die nicht mehr kaufen",
    description:
      "Anteil der zuletzt aktiven Kunden, die in den letzten 30 Tagen aufgehört haben zu kaufen. Das Gegenteil von Kundenbindung.",
    caveat:
      "Einmal-Kunden werden tendenziell als Abwanderer überbewertet.",
    owner: "Retention",
    icon: "churn",
    dateField: "week",
    higherIsBetter: false,
    defaultRangeDays: 90,
    groupOptions: [
      { field: "segment", label: "Nach Kundensegment" },
      { field: "region", label: "Nach Region" },
    ],
  },

  // ----- Shopify (Live oder simulierter Plus-Shop) -----
  shopify_orders_daily: {
    valueField: "orders_completed",
    valueScale: 1,
    unit: "count",
    title: "Tagesbestellungen (Shopify)",
    subtitle: "Anzahl abgeschlossener Bestellungen pro Tag",
    description:
      "Bestellvolumen aus dem angebundenen Shopify-(Plus-)Shop. Zeigt die operative Last und reagiert sehr direkt auf Marketing-Aktivität sowie technische Probleme.",
    owner: "Revenue",
    icon: "cart",
    dateField: "day",
    higherIsBetter: true,
    defaultRangeDays: 60,
    groupOptions: [{ field: "channel", label: "Nach Kanal" }],
  },
  shopify_aov_daily: {
    valueField: "aov_chf",
    valueScale: 1,
    unit: "currency_chf",
    title: "Bestellwert (Shopify)",
    subtitle: "Durchschnittlicher Auftragswert pro Tag",
    description:
      "Mittlerer Umsatz pro Bestellung aus dem Shopify-Shop, in Shop-Original-Währung. Eine sinkende Kennzahl bei stabilen Bestellzahlen deutet auf Rabattaktionen oder verschobene Sortimente hin.",
    owner: "Revenue",
    icon: "wallet",
    dateField: "day",
    higherIsBetter: true,
    defaultRangeDays: 60,
    groupOptions: [{ field: "channel", label: "Nach Kanal" }],
  },
  shopify_refund_rate_weekly: {
    valueField: "refund_rate_pct",
    valueScale: 0.01,
    unit: "percent",
    title: "Rückgaben (Shopify)",
    subtitle: "Anteil stornierter oder retournierter Shopify-Bestellungen",
    description:
      "Wochenraten der Rückgabe-/Storno-Quote. Eine plötzliche Steigerung deutet auf Qualitätsprobleme, falsche Produktbeschreibungen oder Liefer-Engpässe hin.",
    owner: "Quality",
    icon: "undo",
    dateField: "week",
    higherIsBetter: false,
    defaultRangeDays: 90,
    groupOptions: [{ field: "channel", label: "Nach Kanal" }],
  },
  shopify_repeat_rate_weekly: {
    valueField: "repeat_rate_pct",
    valueScale: 0.01,
    unit: "percent",
    title: "Wiederkäufer (Shopify)",
    subtitle: "Anteil Neukunden mit zweiter Bestellung in 90 Tagen",
    description:
      "Kohortenbetrachtung: Wie viel Prozent der in einer Woche neu gewonnenen Kunden bestellen innerhalb von 90 Tagen ein zweites Mal? Der einzelne wichtigste Frühindikator für Customer Lifetime Value.",
    owner: "Retention",
    icon: "repeat",
    dateField: "week",
    higherIsBetter: true,
    defaultRangeDays: 180,
    groupOptions: [],
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
