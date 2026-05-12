"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Settings, BookOpen, ChevronDown, User2 } from "lucide-react";

/**
 * Top navigation kept deliberately small. The four primary items are
 * the only things a manager needs daily; less-frequent destinations live
 * in the user menu (Lernerfahrungen, Einstellungen) so they don't add
 * cognitive load to the chrome.
 */
const PRIMARY = [
  { href: "/", label: "Übersicht" },
  { href: "/investigate", label: "Neue Analyse" },
  { href: "/kpis", label: "Kennzahlen" },
  { href: "/runs", label: "Aktivität" },
];

const SECONDARY = [
  { href: "/insights", label: "Lernerfahrungen", icon: BookOpen },
  { href: "/settings", label: "Einstellungen", icon: Settings },
];

export function Nav() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [menuOpen]);

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
          {PRIMARY.map((it) => {
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

          <div className="relative ml-2" ref={menuRef}>
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className="flex items-center gap-1.5 px-2 py-1.5 rounded-md text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)] hover:bg-[var(--color-bg)]"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
            >
              <User2 className="size-4" />
              <ChevronDown className="size-3 opacity-60" />
            </button>
            {menuOpen ? (
              <div
                role="menu"
                className="absolute right-0 top-full mt-1 min-w-[200px] bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg shadow-lg py-1 z-50"
              >
                {SECONDARY.map((it) => {
                  const Icon = it.icon;
                  return (
                    <Link
                      key={it.href}
                      href={it.href}
                      role="menuitem"
                      onClick={() => setMenuOpen(false)}
                      className="flex items-center gap-2 px-3 py-2 text-sm text-[var(--color-fg)] hover:bg-[var(--color-bg)]"
                    >
                      <Icon className="size-4 text-[var(--color-muted)]" />
                      {it.label}
                    </Link>
                  );
                })}
              </div>
            ) : null}
          </div>
        </nav>
      </div>
    </header>
  );
}
