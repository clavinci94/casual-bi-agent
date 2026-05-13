# SSO via Bearer-JWT — Setup-Anleitung

Für den Übergang von „Single-Tenant mit Shared-Key" zu „Enterprise-fähig mit
echter Benutzer-Identität". Funktioniert mit jedem IdP der OIDC + JWKS
unterstützt — getestete Beispiele: Auth0, Azure AD, Okta, Keycloak.

Frontend bleibt unverändert: in der Praxis steht das Dashboard hinter einem
Reverse Proxy (oder einem Next.js BFF-Layer), der den Bearer-Token vom
SSO-Provider holt und an die FastAPI weiterreicht. Diese Doku beschreibt
ausschliesslich die Backend-Seite.

## 1. Modus aktivieren

In `.env`:

```
BIQ_AUTH_MODE=bearer_jwt
BIQ_JWT_JWKS_URL=https://<your-tenant>.auth0.com/.well-known/jwks.json
BIQ_JWT_ISSUER=https://<your-tenant>.auth0.com/
BIQ_JWT_AUDIENCE=https://api.causal-bi.example.com
```

Backend neu starten — alle `/api/*` Routen verlangen jetzt einen gültigen
Bearer-Token.

## 2. Auth0 — konkretes Beispiel

1. **Auth0-Dashboard** → **APIs** → **Create API**
   - Name: `causal-bi-api`
   - Identifier: `https://api.causal-bi.example.com` (das wird die
     `audience` im JWT)
   - Signing Algorithm: `RS256` (Default)
2. **Applications** → **Create Application** (Type: Single Page Application)
   - Allowed Callback URLs: `https://<your-dashboard-host>/auth/callback`
   - Allowed Web Origins: `https://<your-dashboard-host>`
3. Im Dashboard-Frontend integrierst du das Auth0 SDK
   (`@auth0/auth0-react`); das SDK liefert dir per `getAccessTokenSilently`
   einen JWT mit der konfigurierten `audience`.
4. Frontend hängt den JWT als `Authorization: Bearer <token>` an jeden
   FastAPI-Call. Im aktuellen Stand der `frontend/lib/api.ts` ist das
   ein 5-Zeilen-Edit (`request()`-Helper).

JWKS-URL für Auth0:
```
https://<your-tenant>.auth0.com/.well-known/jwks.json
```

## 3. Azure AD — Eckdaten

- **App Registration** → Redirect URI: `https://<dashboard>/auth/callback`
- **API permissions** → expose an API (definiert deine `audience`)
- JWKS-URL: `https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys`
- Issuer: `https://login.microsoftonline.com/<tenant-id>/v2.0`

## 4. Keycloak (self-hosted) — Eckdaten

- Realm → Clients → Create
- Access Type: `public` (für SPA) oder `confidential` (für Server-Side)
- JWKS-URL: `https://<keycloak-host>/realms/<realm>/protocol/openid-connect/certs`
- Issuer: `https://<keycloak-host>/realms/<realm>`

## 5. Welche Claims nutzt das Backend?

Nach erfolgreicher Validierung legt der Auth-Layer die JWT-Claims auf
`request.state.user` ab. Route-Handler können dann z.B. lesen:

```python
@router.get("/me")
def whoami(request: Request) -> dict:
    user = getattr(request.state, "user", {}) or {}
    return {
        "email": user.get("email"),
        "sub":   user.get("sub"),
        "roles": user.get("https://causal-bi.example.com/roles", []),
    }
```

Aktuell sind alle Routen *gleich* geschützt (entweder authentifiziert
oder nicht). Per-Endpoint-Rollen oder Per-Tenant-Isolation sind eine
spätere Erweiterung — die Stelle dafür ist die `require_api_key`
Dependency in `biq/api/auth.py`.

## 6. Lokale Entwicklung

Während du am Backend arbeitest, willst du nicht jedes Mal echte
JWT-Tokens generieren. Zwei Optionen:

- **`BIQ_AUTH_MODE=disabled`** im lokalen `.env` — alle Routen offen
- **`BIQ_AUTH_MODE=api_key`** + `BIQ_API_KEY=dev-key` — klassische
  Single-Key-Auth, Tests + curl-Calls funktionieren weiter

Default ist `api_key` damit nichts an der existierenden Toolchain
bricht.

## 7. Sicherheits-Checkliste vor dem Produktiv-Schalten

- [ ] `BIQ_JWT_JWKS_URL` zeigt auf den **produktiven** IdP-Endpoint, nicht
      auf einen Staging-Tenant
- [ ] `BIQ_JWT_ISSUER` ist exakt der Issuer-String im Token (Trailing
      Slash kann variieren — beide Versionen prüfen)
- [ ] `BIQ_JWT_AUDIENCE` ist die spezifische API, nicht der Account
- [ ] HTTPS überall — Bearer-Tokens dürfen nie über plain HTTP gehen
- [ ] Token-Expiry ist sinnvoll konfiguriert (typisch 1h Access-Token,
      Refresh über IdP)
- [ ] Logging der Auth-Failures aktiviert (`biq.api.auth` schreibt sie
      schon mit `_logger.warning`)
- [ ] PII-Felder im JWT (E-Mail, Name) werden nicht in Audit-Logs
      eingebrannt — der Stack speichert standardmässig nur `approver`,
      keinen vollen JWT-Body

## 8. Migration von API-Key zu JWT — Step-by-Step

1. JWT-Validierung live testen mit `BIQ_AUTH_MODE=bearer_jwt` im
   Staging-Env
2. Frontend auf Auth0-Login umstellen (Login-Page + Token-Refresh)
3. Bestehende n8n-Workflows / Skripte: Maschinenkonten im IdP anlegen
   (Auth0: Client Credentials Grant), sie erhalten kurzlebige JWTs
4. Erst dann produktiv `BIQ_AUTH_MODE=bearer_jwt` setzen — bis dahin
   laufen API-Keys + JWT parallel via zwei Backend-Instanzen
