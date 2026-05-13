"use client";

import Link from "next/link";

export function Card({
  children,
  className = "",
  /** "lg" gives the hero/featured cards a 32px rounding (Tavily-style) */
  size = "default",
}: {
  children: React.ReactNode;
  className?: string;
  size?: "default" | "lg";
}) {
  const radius = size === "lg" ? "rounded-[2rem]" : "rounded-[1.5rem]";
  return (
    <div
      className={`bg-[var(--color-surface)] border border-[var(--color-border)] ${radius} ${className}`}
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
  // Tavily-style: solid pills, no border. Neutral pill is the same near-black
  // as the main accent so primary metadata reads as a "chip", not as decoration.
  const map: Record<string, string> = {
    neutral:
      "bg-[var(--color-accent)] text-[var(--color-accent-fg)]",
    success:
      "bg-[color-mix(in_oklch,var(--color-success)_22%,var(--color-surface))] text-[oklch(0.35_0.10_150)]",
    warning:
      "bg-[color-mix(in_oklch,var(--color-warning)_25%,var(--color-surface))] text-[oklch(0.38_0.13_75)]",
    danger:
      "bg-[color-mix(in_oklch,var(--color-danger)_18%,var(--color-surface))] text-[var(--color-danger)]",
    accent:
      "bg-[color-mix(in_oklch,var(--color-accent)_14%,var(--color-surface))] text-[var(--color-accent)]",
  };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium ${map[tone]}`}
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
