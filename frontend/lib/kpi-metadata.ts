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
    valueScale: 0.01, // column is 0..100 → divide so formatter sees a fraction
    unit: "percent",
    title: "Conversion rate",
    description:
      "Share of visitor sessions that end in at least one order. The headline funnel metric for the online shop.",
    caveat: "Includes bot traffic unless explicitly filtered.",
    owner: "Marketing",
    dateField: "day",
    higherIsBetter: true,
    defaultRangeDays: 30,
    groupOptions: [
      { field: "device", label: "By device" },
      { field: "channel", label: "By acquisition channel" },
    ],
  },
  aov_daily: {
    valueField: "aov_brl",
    valueScale: BRL_TO_CHF, // source is BRL; convert at display time
    unit: "currency_chf",
    title: "Average order value",
    description:
      "Mean revenue per order in CHF (converted from BRL at the documented fixed rate). Tracks how much customers spend per checkout.",
    caveat:
      "Does not net out freight — use Gross margin for that. CHF figure uses a fixed BRL rate; refresh the ADR when the rate moves materially.",
    owner: "Revenue",
    dateField: "day",
    higherIsBetter: true,
    defaultRangeDays: 30,
    groupOptions: [
      { field: "category", label: "By product category" },
      { field: "region", label: "By region" },
    ],
  },
  gross_margin_weekly: {
    valueField: "gross_margin",
    valueScale: 1, // column is already a 0..1 fraction
    unit: "percent",
    title: "Gross margin",
    description:
      "Revenue minus cost of goods sold and freight, as a percentage of revenue. The bottom-line health check.",
    caveat:
      "COGS is estimated from product weight times a fixed constant — directional, not exact.",
    owner: "Finance",
    dateField: "week",
    higherIsBetter: true,
    defaultRangeDays: 90,
    groupOptions: [
      { field: "category", label: "By product category" },
      { field: "region", label: "By region" },
    ],
  },
  delivery_time_p95: {
    valueField: "p95_days",
    valueScale: 1,
    unit: "days",
    title: "Delivery time (95th percentile)",
    description:
      "How long the slowest 5 % of deliveries take, in business days. A customer-experience guardrail — when this rises, customers complain.",
    owner: "Logistics",
    dateField: "day",
    higherIsBetter: false,
    defaultRangeDays: 30,
    groupOptions: [
      { field: "region", label: "By region" },
      { field: "category", label: "By product category" },
    ],
  },
  review_score_avg: {
    valueField: "avg_score",
    valueScale: 1,
    unit: "score",
    title: "Average review score",
    description:
      "Mean customer review score (1 to 5), weighted toward the last 90 days. Early-warning signal for quality issues.",
    owner: "Quality",
    dateField: "week",
    higherIsBetter: true,
    defaultRangeDays: 90,
    groupOptions: [{ field: "category", label: "By product category" }],
  },
  refund_rate: {
    valueField: "refund_rate_pct",
    valueScale: 0.01,
    unit: "percent",
    title: "Refund rate",
    description:
      "Share of orders that end up cancelled or unavailable. A high or rising refund rate burns margin and signals operational pain.",
    owner: "Finance",
    dateField: "week",
    higherIsBetter: false,
    defaultRangeDays: 90,
    groupOptions: [
      { field: "category", label: "By product category" },
      { field: "region", label: "By region" },
      { field: "payment_type", label: "By payment type" },
    ],
  },
  repeat_purchase_rate: {
    valueField: "repeat_rate_pct",
    valueScale: 0.01,
    unit: "percent",
    title: "Repeat purchase rate",
    description:
      "Share of customers who order a second time within 90 days. The single best predictor of long-term revenue.",
    owner: "Retention",
    dateField: "week",
    higherIsBetter: true,
    defaultRangeDays: 90,
    groupOptions: [
      { field: "segment", label: "By customer segment" },
      { field: "region", label: "By region" },
    ],
  },
  churn_30d: {
    valueField: "churn_rate_pct",
    valueScale: 0.01,
    unit: "percent",
    title: "30-day churn rate",
    description:
      "Share of recently-active customers who stopped buying in the last 30 days. The inverse of stickiness.",
    caveat:
      "Customers with a single one-off purchase are over-counted as churners.",
    owner: "Retention",
    dateField: "week",
    higherIsBetter: false,
    defaultRangeDays: 90,
    groupOptions: [
      { field: "segment", label: "By customer segment" },
      { field: "region", label: "By region" },
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
