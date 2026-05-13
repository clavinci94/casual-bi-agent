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

export const auth0 = new Auth0Client({
  authorizationParameters: {
    audience: process.env.AUTH0_AUDIENCE,
    scope: process.env.AUTH0_SCOPE ?? "openid profile email",
  },
});
