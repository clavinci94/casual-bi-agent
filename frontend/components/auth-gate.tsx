"use client";

import { useEffect, useState } from "react";
import { clearApiKey, getApiKey, setApiKey } from "@/lib/api";

/**
 * Gates the app behind an API-key input. The key is stored in localStorage
 * and sent as X-API-Key on every backend call.
 *
 * If FastAPI is running without BIQ_API_KEY set, any non-empty value will
 * pass — we still gate the UI so the user is conscious of what env they're
 * pointing at.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [hasKey, setHasKey] = useState(false);
  const [input, setInput] = useState("");

  useEffect(() => {
    setHasKey(Boolean(getApiKey()));
    setReady(true);
  }, []);

  if (!ready) {
    // Avoid the flash-of-unauthenticated content while we read localStorage.
    return null;
  }

  if (!hasKey) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-[var(--color-bg)]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const trimmed = input.trim();
            if (!trimmed) return;
            setApiKey(trimmed);
            setHasKey(true);
          }}
          className="w-full max-w-md bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl shadow-sm p-8 space-y-4"
        >
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              Causal BI · Dashboard
            </h1>
            <p className="text-sm text-[var(--color-muted)] mt-1">
              Sign in with the X-API-Key set on the FastAPI backend
              (<span className="mono">BIQ_API_KEY</span>). If the backend is
              open (dev mode), any non-empty value works.
            </p>
          </div>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
              API key
            </span>
            <input
              type="password"
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="biq-…"
              className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] mono text-sm"
            />
          </label>
          <button
            type="submit"
            className="w-full py-2 rounded-lg bg-[var(--color-accent)] text-[var(--color-accent-fg)] font-medium hover:opacity-90"
          >
            Sign in
          </button>
        </form>
      </div>
    );
  }

  return (
    <>
      {children}
      <button
        type="button"
        onClick={() => {
          clearApiKey();
          setHasKey(false);
        }}
        className="fixed bottom-4 right-4 text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)] mono"
      >
        sign out
      </button>
    </>
  );
}
