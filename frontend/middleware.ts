import { NextResponse, type NextRequest } from "next/server";
import { auth0 } from "@/lib/auth0";

/**
 * Auth0 v4 middleware — intercepts /auth/login, /auth/logout, /auth/callback,
 * /auth/profile, /auth/access-token to drive the SSO flow. Other routes
 * pass through unchanged.
 *
 * Local-dev escape hatch: when AUTH0_ISSUER_BASE_URL is missing or still
 * contains the REPLACE_ME placeholder, we skip the Auth0 logic entirely
 * so the dashboard keeps loading. As soon as the operator fills in a
 * real Auth0 tenant domain, SSO kicks in automatically on the next
 * dev-server restart.
 */
function isAuth0Configured(): boolean {
  const issuer = process.env.AUTH0_ISSUER_BASE_URL ?? "";
  if (!issuer) return false;
  if (issuer.includes("REPLACE_ME")) return false;
  return true;
}

export async function middleware(request: NextRequest) {
  if (!isAuth0Configured()) {
    return NextResponse.next();
  }
  return auth0.middleware(request);
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - _next/static (build assets)
     * - _next/image (image optimisation)
     * - favicon.ico, icons, etc.
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|gif|svg|webp|ico)$).*)",
  ],
};
