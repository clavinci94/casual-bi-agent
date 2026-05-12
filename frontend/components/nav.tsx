"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/runs", label: "Investigations" },
  { href: "/kpis", label: "KPIs" },
  { href: "/insights", label: "Knowledge graph" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 group">
          <span className="size-2 rounded-full bg-[var(--color-accent)]" />
          <span className="font-semibold tracking-tight group-hover:opacity-80">
            Causal BI
          </span>
        </Link>
        <nav className="flex items-center gap-1">
          {ITEMS.map((it) => {
            const active =
              it.href === "/"
                ? pathname === "/"
                : pathname.startsWith(it.href);
            return (
              <Link
                key={it.href}
                href={it.href}
                className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                  active
                    ? "bg-[var(--color-bg)] text-[var(--color-fg)] font-medium"
                    : "text-[var(--color-muted)] hover:text-[var(--color-fg)] hover:bg-[var(--color-bg)]"
                }`}
              >
                {it.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
