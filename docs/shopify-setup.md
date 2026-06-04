# Shopify Dev-Store → causal-bi Anbindung

Schritt-für-Schritt-Anleitung, damit dein causal-bi-System mit echten,
laufend aktualisierten E-Commerce-Daten arbeitet. Kostet nichts
(Shopify Partner und Dev-Stores sind kostenlos), dauert ca. 20 Minuten
Einrichtung + 1× initial sync.

## 1. Shopify Partner-Account anlegen (5 Min, einmalig)

1. https://partners.shopify.com → **Become a partner** / **Sign up**
2. E-Mail, Passwort, ein paar Firmen-Daten (Privatperson reicht)
3. Bestätigungs-E-Mail klicken

## 2. Development-Store erstellen (3 Min)

1. Im Partner Dashboard: **Stores** → **Add store** → **Development store**
2. Optionen:
   - **Store name**: `causal-bi-demo` (oder beliebig)
   - **Store purpose**: *Build a new app or test theme*
   - **Demo data**: ✓ aktivieren — Shopify füllt den Store mit ~50 Produkten
     und ein paar Test-Bestellungen, perfekt für den ersten Lauf
3. **Create development store** → wenige Sekunden warten
4. Du landest in der Store-Admin unter `https://<store-name>.myshopify.com/admin`

## 3. Custom App + Admin-API-Token (5 Min)

Damit unser Backend lesen kann:

1. Store-Admin → **Settings** (unten links) → **Apps and sales channels**
2. **Develop apps** → falls Pop-up: **Allow custom app development**
3. **Create an app** → Name z.B. `causal-bi-connector` → **Create app**
4. **Configuration** → **Admin API integration** → **Configure**:
   - Aktiviere folgende **Admin API access scopes** (nur Lesen):
     - `read_orders`
     - `read_customers`
     - `read_products`
   - **Save**
5. **Install app** (oben rechts) → **Install**
6. Auf **API credentials** → **Admin API access token** → **Reveal token once**
   - Wert beginnt mit `shpat_...`
   - **Sofort kopieren** — Shopify zeigt ihn nur **einmal** an
7. Falls vergessen: die App löschen und neu erstellen

## 4. Token in .env eintragen

Im Repo-Root, in `/Users/claudio/causal-bi/.env`:

```
SHOPIFY_SHOP_DOMAIN=your-store-name.myshopify.com
SHOPIFY_ADMIN_API_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Backend neu starten:
```bash
make api-serve   # oder den laufenden Prozess Ctrl+C und neu starten
```

## 5. Initial Sync

```bash
make shopify-sync
```

Output sollte etwa so aussehen:
```json
[
  {"entity": "products",  "rows_upserted": 52,  "since_iso": null},
  {"entity": "customers", "rows_upserted": 18,  "since_iso": null},
  {"entity": "orders",    "rows_upserted": 23,  "since_iso": null}
]
```

Prüfen in psql:
```sql
SELECT COUNT(*) FROM raw.shopify_orders;
SELECT COUNT(*) FROM raw.shopify_customers;
SELECT COUNT(*) FROM raw.shopify_products;
SELECT * FROM raw.shopify_sync_log ORDER BY started_at DESC LIMIT 5;
```

## 6. Inkrementeller Re-Sync (für Cron / n8n)

Jede weitere Synchronisation soll nur Änderungen seit dem letzten
erfolgreichen Lauf holen:

```bash
make shopify-sync-incremental
```

Dies pickt automatisch das `finished_at` des letzten erfolgreichen
Eintrags in `raw.shopify_sync_log` pro Entity als `updated_at_min`.

### n8n-Workflow (optional)

`n8n/workflows/shopify-hourly-sync.json` ist vorbereitet — importiere
ihn in deine n8n-Instanz, dann läuft `make shopify-sync-incremental`
stündlich.

## 7. KPIs gegen die Shopify-Daten

Shopify-spezifische KPI-Views sind inzwischen umgesetzt. Die wichtigsten
Views sind:

- `kpi.shopify_orders_daily`
- `kpi.shopify_aov_daily`
- `kpi.shopify_refund_rate_weekly`
- `kpi.shopify_repeat_rate_weekly`

Demo- und Live-Daten koexistieren in denselben `raw.shopify_*` Tabellen.
Jede Zeile trägt `data_source = 'sim'` oder `data_source = 'live'`.
Die KPI-Views lesen die aktive Quelle über die Postgres-Session-Variable
`biq.data_source`, die vom Backend anhand der Systemkonfiguration gesetzt
wird. So kann das Dashboard zwischen simuliertem Shopify-Shop und echtem
Dev-Store-Sync wechseln, ohne Daten zu löschen oder Views umzubauen.

Der Anomaly-Detector kann Shopify-Tagesbestellungen pro Kanal prüfen:

```bash
uv run python scripts/detect_anomalies.py --source shopify
```

## Troubleshooting

| Symptom | Ursache / Fix |
|---|---|
| `SHOPIFY_SHOP_DOMAIN and SHOPIFY_ADMIN_API_TOKEN must be set` | `.env` nicht angepasst oder Backend nicht neu gestartet. |
| `401 Unauthorized` | Token falsch kopiert oder die App nicht installiert. Custom App → Install. |
| `403 Forbidden` auf `/orders.json` | Scope `read_orders` fehlt. Custom-App-Config → Scopes → Save → App neu installieren. |
| Sync hängt bei `429 Retry-After` | Shopify-Rate-Limit. Der Connector wartet automatisch — bei großen Stores einfach Geduld haben. |
| `make shopify-sync` läuft, aber 0 Zeilen | Demo-Daten nicht aktiviert oder noch keine Bestellungen. Im Store-Admin → Demo-Daten aktivieren oder manuell ein paar Bestellungen anlegen. |

## Sicherheit

- Token **niemals committen** — `.env` ist gitignored
- Bei Verdacht auf Leak: App im Store-Admin **uninstall** + neu installieren, Token wird neu erzeugt
- Token hat **read-only** Scope — schreibt nichts in deinen Store, kann aber alle Kunden-/Bestelldaten lesen
