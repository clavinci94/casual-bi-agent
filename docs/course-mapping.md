# Mapping zum BI-Leistungsnachweis

Diese Datei ordnet den aktuellen Projektstand den Vorgaben des Business-Intelligence-Leistungsnachweises zu. Die Übungen dienen als Vorbereitung; bewertet wird das Projekt als eigener Use Case mit Konzeption, prototypischer Umsetzung, Dokumentation und Präsentation.

## Bewertungslogik aus den Folien

| Vorgabe | Umsetzung Im Projekt | Nachweis |
|---|---|---|
| Eigener Unternehmens-Use-Case rund um generative KI | Agentic BI für E-Commerce- und Shopify-Plus-Brands im DACH-Raum | [`README.md`](../README.md), [`docs/strategy/business-plan.md`](strategy/business-plan.md) |
| Konzeption | 5-Layer-Architektur, Zielkunde, Problem, Methode, Roadmap und Business Case sind dokumentiert | [`docs/architecture.md`](architecture.md), [`docs/strategy/business-plan.md`](strategy/business-plan.md) |
| Prototypische Umsetzung | Backend, API, Dashboard, Agenten, R-Service, Postgres-Schemas, MCP-Tools und HITL sind implementiert | `backend/`, `frontend/`, `r-service/`, `db/schemas/` |
| Dokumentation | README, Architektur, Clean Architecture, KPI-Katalog, Deployment, Shopify-Setup und Präsentationsdrehbuch vorhanden | [`docs/`](.) |
| Präsentation | Demo-Flow und Q&A-Vorbereitung sind vorbereitet | [`docs/strategy/thesis-defense.md`](strategy/thesis-defense.md) |
| Originalität | Kombination aus Kausalanalyse, Agentic BI, Human-in-the-Loop und Knowledge Graph | [`README.md`](../README.md#was-es-besonders-macht) |
| Durchführbarkeit | CI, Tests, Dockerfiles, Render/Neon-Deployment und lokale Demo-Befehle vorhanden | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml), [`infra/deploy.md`](../infra/deploy.md) |

## Abdeckung des Week-11-Zielbilds

Die Week-11-Folien beschreiben ein BI-AI-System, das nicht nur Dashboards zeigt, sondern Daten sammelt, KPIs berechnet, Auffälligkeiten erkennt, Ursachen analysiert, Prognosen erstellt, Empfehlungen gibt und Entscheider per Agent unterstützt.

| Zielbild | Status | Umsetzung |
|---|---|---|
| Daten automatisch sammeln | Erfüllt | Olist Seed, simulierte Events, Shopify-Connector, externe Signale |
| KPIs konsistent berechnen | Erfüllt | `docs/kpi-catalog.yaml` und `kpi.*` Views |
| Auffälligkeiten erkennen | Erfüllt | Anomalie-Agent und KPI-Detektor |
| Ursachen analysieren | Erfüllt | Kontext-Tools, Release-/Campaign-Suche, externe Signale |
| Prognosen erstellen | Bewusst nicht Kernscope | Fokus liegt auf kausaler Erklärung beobachteter Phänomene; Forecasting ist Roadmap |
| Handlungsempfehlungen geben | Erfüllt | Investigator, Graph-Agent und Recommendation Queue |
| Entscheider per Chat/Agent unterstützen | Erfüllt | LLM-Investigator, FastAPI, Dashboard und HITL |

## Warum das Projekt bestnotenfähig ist

Das Projekt erfüllt nicht nur eine technische Demo, sondern zeigt einen vollständigen Management-Prozess:

```text
Daten -> KPI-Semantik -> Agentische Analyse -> Kausale Prüfung -> Empfehlung -> Freigabe -> Outcome -> Memory
```

Die besondere Stärke ist die Verbindung von BI-Theorie und produktnaher Umsetzung:

- Der Semantic Layer verhindert widersprüchliche KPI-Definitionen.
- Der Agent nutzt Tools statt frei zu halluzinieren.
- R/CausalImpact liefert statistische Strenge.
- Human-in-the-Loop hält den Menschen in der Entscheidung.
- Der Audit Trail macht den Prozess nachvollziehbar.
- Der Knowledge Graph sorgt dafür, dass Entscheidungen nicht vergessen werden.

## Präsentationsfokus

Für die Bewertung sollte die Präsentation nicht alle technischen Details zeigen. Der stärkste rote Faden ist:

1. Klassische BI zeigt Zahlen, aber keine Konsequenzen.
2. Causal BI erkennt eine echte Geschäftsabweichung.
3. Der Agent untersucht Daten, Kontext und externe Signale.
4. Statistik prüft, ob die Ursache belastbar ist.
5. Der Mensch entscheidet über die Massnahme.
6. Das System misst später das Ergebnis und lernt daraus.

Der wichtigste Satz für Einleitung und Schluss:

> Causal BI zeigt nicht nur Daten. Es bereitet Entscheidungen vor und lernt aus ihren Folgen.
