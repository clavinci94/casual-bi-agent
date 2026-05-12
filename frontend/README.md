# Causal BI · Frontend

Next.js 15 (App Router, TypeScript, Tailwind 4) dashboard for the
[Causal BI backend](../backend). Talks to the FastAPI layer over HTTP —
no direct DB or Anthropic access from the client.

## Pages

| Route | What |
|---|---|
| `/` | Health tiles, pending HITL queue, recent runs |
| `/runs` | Investigation list with status + duration + cost |
| `/runs/[id]` | Full audit trail per run: plan, tool calls, params, errors |
| `/recommendations/[id]` | Approve / reject UI with audit-linked decision form |
| `/kpis` | List of `kpi.*` views the backend exposes |
| `/kpis/[view]` | Plotly time-series with date range + group-by selector |
| `/insights` | Knowledge-graph insights (what the system has learned) |

## Auth

The dashboard sends `X-API-Key` on every backend call. On first load, an
input gate prompts for the key; it lands in `localStorage`. To sign out,
hit the link in the bottom-right corner.

When the backend has `BIQ_API_KEY` unset (dev mode), any non-empty string
passes through.

## Run

```bash
# in a separate shell, with the backend up:
make api-serve          # FastAPI on :8000

make frontend-install   # one-time
make frontend-dev       # Next.js on :3000
```

Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` if the backend isn't on
`http://127.0.0.1:8000`.

## Tech notes

- **Plotly** loads via `dynamic(... { ssr: false })` so the 3 MB bundle is
  fetched only when a KPI page mounts. The initial bundle stays ~115 kB.
- **SWR** for client-side data fetching with 5 s dedup. No global store —
  each page owns its queries.
- **Tailwind 4** with the new `@theme` CSS-based config (no
  `tailwind.config.ts`). Tokens live in `app/globals.css`.
- Types in `lib/types.ts` are hand-mirrored from the Pydantic models in
  `backend/src/biq/api/*.py`. No codegen yet — keep them in sync.
