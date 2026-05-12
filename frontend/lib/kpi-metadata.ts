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

export const KPI_META: Record<string, KpiMeta> = {
  conversion_rate_daily: {
    valueField: "conversion_rate",
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
    valueField: "aov",
    unit: "currency_chf",
    title: "Average order value",
    description:
      "Mean revenue per order, before refunds. Tracks how much customers spend per checkout.",
    caveat: "Does not net out freight — use Gross margin for that.",
    owner: "Revenue",
    dateField: "day",
    higherIsBetter: true,
    defaultRangeDays: 30,
    groupOptions: [{ field: "category", label: "By product category" }],
  },
  gross_margin_weekly: {
    valueField: "gross_margin",
    unit: "percent",
    title: "Gross margin",
    description:
      "Revenue minus cost of goods sold and freight, as a percentage of revenue. The bottom-line health check.",
    caveat:
      "COGS is estimated from product weight × a fixed constant — directional, not exact.",
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
    valueField: "delivery_time_p95_days",
    unit: "days",
    title: "Delivery time (95th percentile)",
    description:
      "How long the slowest 5 % of deliveries take, in business days. A customer-experience guardrail — when this rises, customers complain.",
    owner: "Logistics",
    dateField: "day",
    higherIsBetter: false,
    defaultRangeDays: 30,
    groupOptions: [{ field: "region", label: "By region" }],
  },
  review_score_avg: {
    valueField: "review_score_avg",
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
    valueField: "refund_rate",
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
    ],
  },
  repeat_purchase_rate: {
    valueField: "repeat_rate",
    unit: "percent",
    title: "Repeat purchase rate",
    description:
      "Share of customers who order a second time within 90 days. The single best predictor of long-term revenue.",
    owner: "Retention",
    dateField: "week",
    higherIsBetter: true,
    defaultRangeDays: 90,
    groupOptions: [{ field: "segment", label: "By customer segment" }],
  },
  churn_30d: {
    valueField: "churn_rate",
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
    groupOptions: [{ field: "segment", label: "By customer segment" }],
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
