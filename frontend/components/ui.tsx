"use client";

import Link from "next/link";

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl shadow-[0_1px_2px_rgba(0,0,0,0.03)] ${className}`}
    >
      {children}
    </div>
  );
}

export function SectionTitle({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between mb-3">
      <div className="flex items-baseline gap-3">
        <h2 className="text-sm font-semibold tracking-tight uppercase text-[var(--color-muted)]">
          {title}
        </h2>
        {hint ? (
          <span className="text-xs text-[var(--color-muted)]">{hint}</span>
        ) : null}
      </div>
      {action}
    </div>
  );
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "accent";
}) {
  const map: Record<string, string> = {
    neutral:
      "bg-[var(--color-bg)] text-[var(--color-muted)] border-[var(--color-border)]",
    success: "bg-emerald-50 text-emerald-700 border-emerald-200",
    warning: "bg-amber-50 text-amber-800 border-amber-200",
    danger: "bg-red-50 text-red-700 border-red-200",
    accent:
      "bg-[color-mix(in_oklch,var(--color-accent)_15%,white)] text-[var(--color-accent)] border-[color-mix(in_oklch,var(--color-accent)_30%,white)]",
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${map[tone]}`}
    >
      {children}
    </span>
  );
}

export function ErrorMessage({ error }: { error: unknown }) {
  const message =
    error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div className="text-sm text-[var(--color-danger)] bg-red-50 border border-red-200 rounded-md px-3 py-2 mono">
      {message}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="text-sm text-[var(--color-muted)] animate-pulse">{label}</div>
  );
}

export function MutedLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="text-[var(--color-accent)] hover:underline font-medium"
    >
      {children}
    </Link>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-sm text-[var(--color-muted)] py-6 text-center">
      {children}
    </div>
  );
}
