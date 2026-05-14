import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Network,
  Radar,
  SearchCheck,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui";
import { PageHeader } from "@/components/page-header";

export const metadata = {
  title: "Causal BI · Home",
  description:
    "Ein agentisches Business-Intelligence-System mit kausaler Inferenz, "
    + "Human-in-the-Loop-Freigabe und organisationaler Erinnerung.",
};

type Capability = {
  icon: LucideIcon;
  label: string;
  title: string;
  body: string;
  link?: { href: string; label: string };
};

const CAPABILITIES: Capability[] = [
  {
    icon: SearchCheck,
    label: "Erkennen",
    title: "Anomalien finden, ohne dass jemand danach sucht",
    body:
      "Der Investigation-Agent geht jeden Tag durch alle KPI-Sichten, "
      + "vergleicht aktuelle Werte mit der historischen Verteilung und "
      + "meldet, was statistisch auffällt — bevor es ein Mensch im "
      + "Dashboard bemerkt.",
    link: { href: "/investigate", label: "Neue Analyse starten" },
  },
  {
    icon: Network,
    label: "Verstehen",
    title: "Kausale Ursachen statt nur Korrelationen",
    body:
      "Statt 'A ging hoch, B ging runter' liefert Causal BI saubere "
      + "Effekt-Schätzungen — Difference-in-Differences, Pre/Post-Vergleiche, "
      + "Confounder-Kontrolle über externe Signale wie Wetter, Marktindizes "
      + "und Trends.",
    link: { href: "/kpis", label: "Kennzahlen ansehen" },
  },
  {
    icon: ShieldCheck,
    label: "Entscheiden",
    title: "Empfehlungen mit Freigabe-Workflow",
    body:
      "Jede Empfehlung landet als Karte mit Befund, Begründung und "
      + "vorgeschlagener Aktion. Manager:innen geben frei, lehnen ab oder "
      + "ändern den Vorschlag. Jede Entscheidung wird mit Zeitstempel und "
      + "Begründung im Audit-Log festgehalten.",
    link: { href: "/", label: "Empfehlungen auf der Übersicht" },
  },
  {
    icon: Radar,
    label: "Beobachten",
    title: "Markt-Radar für DACH-Commerce",
    body:
      "Tägliches Briefing um 07:00: DACH-Nachrichten, Commerce-Kalender, "
      + "Shopify-Plattform-Status, Yahoo-Finance-Indizes und Google-Trends "
      + "in einer Manager-tauglichen Synthese — automatisch oder auf Knopfdruck.",
    link: { href: "/markt-radar", label: "Markt-Radar öffnen" },
  },
  {
    icon: BookOpen,
    label: "Lernen",
    title: "Wissensgraph wächst mit jeder Entscheidung",
    body:
      "Was wurde empfohlen, was wurde freigegeben, was hat es bewirkt? "
      + "Nach Ablauf der Beobachtungszeit misst das System die tatsächliche "
      + "Wirkung und speichert sie als Outcome — gefüttert in zukünftige "
      + "Analysen, damit der Agent aus echten Resultaten lernt.",
    link: { href: "/insights", label: "Lernerfahrungen ansehen" },
  },
];

const LAYERS: { layer: string; what: string }[] = [
  {
    layer: "1 · Datenquellen",
    what:
      "Shopify-Bestellungen (Sim und Live), externe Signale aus News-APIs, "
      + "Google Trends, Yahoo Finance, Commerce-Kalender.",
  },
  {
    layer: "2 · Rohschicht",
    what:
      "Postgres mit pgvector. Schema-getrennte Bereiche raw / kpi / docs / "
      + "kg / audit halten Rohbestand, abgeleitete Sichten und Audit-Log auseinander.",
  },
  {
    layer: "3 · Semantische Schicht",
    what:
      "kpi.*-Views als Single-Source-of-Truth für Formeln und Granularität — "
      + "der KPI-Katalog in YAML hält die Definition versioniert.",
  },
  {
    layer: "4 · AI-Analytics",
    what:
      "LangGraph-Agenten (Data → Stats → Causal → Narrative → Review) mit "
      + "Anthropic Claude. Briefing-Modell ist auf der Einstellungen-Seite "
      + "zwischen Haiku, Sonnet und Opus wechselbar.",
  },
  {
    layer: "5 · Entscheidungsschicht",
    what:
      "Next.js-Dashboard mit Freigabe-Queue, Audit-Trail, Aktivitätsstrip, "
      + "Lernerfahrungen, R-Shiny-Visualisierungen und Slack-Alerts via n8n.",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-10">
      <PageHeader
        label="Willkommen"
        title="Causal BI"
        description={
          "Ein agentisches Business-Intelligence-System, das Anomalien selbst findet, "
          + "Ursachen mit kausaler Inferenz aufdeckt, Empfehlungen mit Freigabe-Workflow "
          + "übergibt und aus den tatsächlichen Resultaten lernt."
        }
      />

      <Card className="p-8 sm:p-10 relative overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 -right-24 size-72 rounded-full bg-[color-mix(in_oklch,var(--color-accent)_22%,transparent)] blur-3xl"
        />
        <div className="relative max-w-3xl space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--color-surface-sunken)] text-xs">
            <Sparkles className="size-3.5 text-[var(--color-accent)]" />
            <span className="font-medium">Built for managers, not engineers</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight leading-tight">
            Vom Datenpunkt zur Entscheidung — mit Mensch in der Schleife.
          </h2>
          <p className="text-[15px] text-[var(--color-muted)] leading-relaxed">
            Causal BI vereint Anomalie-Erkennung, kausale Inferenz, einen
            DACH-Markt-Radar und einen wachsenden Wissensgraphen in einem
            Werkzeug. Statt isolierte Dashboards zeigt es konkrete
            Handlungsempfehlungen — und misst nach der Freigabe selbst, ob
            sie funktioniert haben.
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              href="/"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[var(--color-accent)] text-[var(--color-accent-fg)] text-sm font-medium hover:opacity-90 transition-opacity"
            >
              Zur Übersicht
              <ArrowRight className="size-4" />
            </Link>
            <Link
              href="/markt-radar"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-[var(--color-border)] text-sm font-medium hover:bg-[var(--color-surface-sunken)] transition-colors"
            >
              Markt-Radar öffnen
            </Link>
            <Link
              href="/investigate"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-[var(--color-border)] text-sm font-medium hover:bg-[var(--color-surface-sunken)] transition-colors"
            >
              Eigene Analyse starten
            </Link>
          </div>
        </div>
      </Card>

      <section className="space-y-5">
        <div>
          <div className="label-micro mb-1.5">Was macht Causal BI?</div>
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight">
            Fünf Fähigkeiten, ein durchgehender Lernzyklus.
          </h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {CAPABILITIES.map((c) => (
            <CapabilityCard key={c.title} cap={c} />
          ))}
        </div>
      </section>

      <section className="space-y-5">
        <div>
          <div className="label-micro mb-1.5">Wie es funktioniert</div>
          <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight">
            Fünf Schichten, sauber getrennt.
          </h2>
          <p className="text-sm text-[var(--color-muted)] mt-2 max-w-2xl leading-relaxed">
            Jede Schicht hat eine klare Verantwortung. Das macht das System
            erweiterbar — neue Datenquellen landen in Schicht 1, neue Agents
            in Schicht 4, ohne dass darüber- oder darunterliegende Schichten
            angefasst werden.
          </p>
        </div>
        <Card className="divide-y divide-[var(--color-border)]">
          {LAYERS.map((l) => (
            <div
              key={l.layer}
              className="flex flex-col sm:flex-row gap-3 sm:gap-6 px-5 py-4"
            >
              <div className="sm:w-44 shrink-0 font-medium text-[var(--color-fg)]">
                {l.layer}
              </div>
              <div className="text-sm text-[var(--color-muted)] leading-relaxed">
                {l.what}
              </div>
            </div>
          ))}
        </Card>
      </section>

      <section>
        <Card className="p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6 justify-between">
          <div className="max-w-2xl">
            <div className="label-micro mb-1.5">Kosten unter Kontrolle</div>
            <h3 className="text-lg sm:text-xl font-semibold tracking-tight">
              Auf jeder Karte ein Schalter — auf jeder Schicht ein Audit.
            </h3>
            <p className="text-sm text-[var(--color-muted)] mt-2 leading-relaxed">
              Daily-Briefing pausieren, Modellstufe von Sonnet auf Haiku
              senken, Sim-/Live-Daten umschalten — alles direkt aus den
              Einstellungen, ohne Deploy.
            </p>
          </div>
          <Link
            href="/settings"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-[var(--color-border)] text-sm font-medium hover:bg-[var(--color-surface-sunken)] transition-colors shrink-0"
          >
            Einstellungen öffnen
            <ArrowRight className="size-4" />
          </Link>
        </Card>
      </section>
    </div>
  );
}

function CapabilityCard({ cap }: { cap: Capability }) {
  const Icon = cap.icon;
  return (
    <Card className="p-5 sm:p-6 flex flex-col h-full">
      <div className="flex items-center gap-2 mb-3">
        <span className="size-9 rounded-xl bg-[var(--color-surface-sunken)] flex items-center justify-center">
          <Icon className="size-4 text-[var(--color-accent)]" />
        </span>
        <span className="label-micro">{cap.label}</span>
      </div>
      <h3 className="font-semibold text-[15px] tracking-tight leading-snug mb-2">
        {cap.title}
      </h3>
      <p className="text-sm text-[var(--color-muted)] leading-relaxed flex-1">
        {cap.body}
      </p>
      {cap.link ? (
        <Link
          href={cap.link.href}
          className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-[var(--color-accent)] hover:opacity-80"
        >
          {cap.link.label}
          <ArrowRight className="size-3.5" />
        </Link>
      ) : null}
    </Card>
  );
}
