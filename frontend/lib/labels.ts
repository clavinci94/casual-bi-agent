/**
 * Klartext-Labels für interne Werte.
 *
 * Backend-Felder (trigger, status, severity, etc.) sind technisch. Hier
 * mappen wir sie auf manager-lesbare Begriffe. Default-Fallback ist immer
 * der Originalwert, damit unbekannte Werte sichtbar bleiben statt versteckt.
 */

export function friendlyTrigger(trigger: string | null | undefined): string {
  switch (trigger) {
    case "cli":
      return "Manuelle Anfrage";
    case "api":
      return "Dashboard-Anfrage";
    case "n8n":
      return "Geplante Analyse";
    case "schedule":
      return "Zeitgesteuert";
    case "test":
      return "Test";
    default:
      return trigger ?? "—";
  }
}

export function friendlyStatus(status: string | null | undefined): string {
  switch (status) {
    case "ok":
      return "Abgeschlossen";
    case "running":
      return "Läuft gerade";
    case "error":
      return "Fehlgeschlagen";
    case "pending":
      return "Wartet auf Freigabe";
    case "approved":
      return "Freigegeben";
    case "rejected":
      return "Abgelehnt";
    default:
      return status ?? "—";
  }
}

export function statusTone(
  status: string | null | undefined,
): "success" | "warning" | "danger" | "accent" | "neutral" {
  switch (status) {
    case "ok":
    case "approved":
      return "success";
    case "running":
      return "accent";
    case "error":
    case "rejected":
      return "danger";
    case "pending":
      return "warning";
    default:
      return "neutral";
  }
}

export function friendlySeverity(severity: string | null | undefined): string {
  switch (severity) {
    case "high":
      return "Hohe Priorität";
    case "medium":
      return "Mittlere Priorität";
    case "low":
      return "Niedrige Priorität";
    default:
      return severity ?? "—";
  }
}

export function severityTone(
  severity: string | null | undefined,
): "danger" | "warning" | "neutral" {
  if (severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "neutral";
}

/**
 * Manager-readable component label.
 * "device=mobile"      → "Mobile Geräte"
 * "device=tablet"      → "Tablets"
 * "mobile_checkout"    → "Mobile Checkout"
 */
export function friendlyComponent(component: string | null | undefined): string {
  if (!component) return "—";
  if (component === "device=mobile") return "Mobile Geräte";
  if (component === "device=tablet") return "Tablets";
  if (component === "device=desktop") return "Desktop";
  return component.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export function friendlyKpi(kpi: string | null | undefined): string {
  if (!kpi) return "—";
  switch (kpi) {
    case "conversion_rate":
      return "Conversion Rate";
    case "aov":
    case "average_order_value":
      return "Durchschnittlicher Bestellwert";
    case "gross_margin":
      return "Bruttomarge";
    case "refund_rate":
      return "Rückgabequote";
    case "delivery_time_p95":
      return "Lieferzeit (95 %-Perzentil)";
    case "review_score_avg":
      return "Durchschnittliche Bewertung";
    case "repeat_purchase_rate":
      return "Wiederholungskauf-Rate";
    case "churn_30d":
      return "30-Tage-Abwanderung";
    default:
      return kpi;
  }
}

/**
 * Build a one-sentence summary of an Insight in plain German.
 * E.g. "Die Conversion Rate auf Mobile Geräte fiel um 40,1 % zwischen
 *       7. April und 5. Mai 2018."
 */
export function insightSentence(props: {
  kpi?: string;
  component?: string | null;
  relative_change?: number;
  period_start?: string;
  period_end?: string;
}): string {
  const kpi = friendlyKpi(props.kpi);
  const comp = props.component ? friendlyComponent(props.component) : null;
  const change = props.relative_change;
  const period = formatPeriod(props.period_start, props.period_end);

  if (change == null || !Number.isFinite(change)) {
    return [
      `${kpi}`,
      comp ? `auf ${comp}` : null,
      period ? `im Zeitraum ${period}` : null,
    ]
      .filter(Boolean)
      .join(" ");
  }

  const pct = Math.abs(change * 100);
  const direction = change > 0 ? "stieg um" : "fiel um";
  const pctStr = `${pct.toFixed(1).replace(".", ",")} %`;
  return [
    `${kpi}`,
    comp ? `auf ${comp}` : null,
    `${direction} ${pctStr}`,
    period ? `(${period})` : null,
  ]
    .filter(Boolean)
    .join(" ");
}

function formatPeriod(
  start: string | null | undefined,
  end: string | null | undefined,
): string | null {
  if (!start || !end) return null;
  const fmt = new Intl.DateTimeFormat("de-CH", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  try {
    return `${fmt.format(new Date(start))} bis ${fmt.format(new Date(end))}`;
  } catch {
    return `${start} bis ${end}`;
  }
}

export function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 1) return "gerade eben";
  if (minutes < 60) return `vor ${minutes} Min.`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `vor ${hours} Std.`;
  const days = Math.round(hours / 24);
  if (days < 30) return `vor ${days} Tagen`;
  return d.toLocaleDateString("de-CH", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function fmtConfidence(c: number | null | undefined): string | null {
  if (c == null || !Number.isFinite(c)) return null;
  return `${Math.round(c * 100)} % Sicherheit`;
}
