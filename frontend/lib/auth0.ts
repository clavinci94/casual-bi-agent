/**
 * Auth0 SDK instance — server-side configuration. Used by the
 * middleware to intercept /auth/* routes and by server components to
 * read the current session.
 *
 * SDK v4 reads configuration from environment variables:
 *   AUTH0_SECRET            — random 32-byte hex, encrypts the session cookie
 *   AUTH0_BASE_URL          — http://localhost:3000 (dev) or production URL
 *   AUTH0_ISSUER_BASE_URL   — https://<tenant>.eu.auth0.com (no trailing /)
 *   AUTH0_CLIENT_ID         — from the Application's Settings tab
 *   AUTH0_CLIENT_SECRET     — same
 *   AUTH0_AUDIENCE          — must match the backend BIQ_JWT_AUDIENCE
 *   AUTH0_SCOPE             — "openid profile email"
 */
import { Auth0Client } from "@auth0/nextjs-auth0/server";

// SDK v4 reads the tenant from AUTH0_DOMAIN (bare hostname). We keep
// AUTH0_ISSUER_BASE_URL as the single source of truth because the backend
// JWT validator also uses it as the JWT `iss` claim, so we feed the SDK
// from there explicitly instead of duplicating the value into AUTH0_DOMAIN.
const issuer = process.env.AUTH0_ISSUER_BASE_URL ?? "";
const domain = issuer ? issuer.replace(/^https?:\/\//, "").replace(/\/$/, "") : undefined;

export const auth0 = new Auth0Client({
  domain,
  authorizationParameters: {
    audience: process.env.AUTH0_AUDIENCE,
    scope: process.env.AUTH0_SCOPE ?? "openid profile email",
  },
});
