"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUser } from "@auth0/nextjs-auth0";
import {
  BarChart3,
  BookOpen,
  CompassIcon,
  HomeIcon,
  LayoutDashboard,
  LogIn,
  LogOut,
  RadarIcon,
  Settings,
  SparklesIcon,
  TimerReset,
  User2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

const PRIMARY: NavItem[] = [
  { href: "/home", label: "Home", icon: HomeIcon },
  { href: "/", label: "Übersicht", icon: LayoutDashboard },
  { href: "/investigate", label: "Neue Analyse", icon: SparklesIcon },
  { href: "/kpis", label: "Kennzahlen", icon: BarChart3 },
  { href: "/markt-radar", label: "Markt-Radar", icon: RadarIcon },
  { href: "/runs", label: "Aktivität", icon: TimerReset },
];

const SECONDARY: NavItem[] = [
  { href: "/insights", label: "Lernerfahrungen", icon: BookOpen },
  { href: "/settings", label: "Einstellungen", icon: Settings },
];

export function Sidebar() {
  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-bg)] h-screen sticky top-0">
      <BrandHeader />
      <nav className="flex-1 px-3 py-2 overflow-y-auto">
        <div className="label-micro px-3 mt-3 mb-2">Hauptbereich</div>
        <ul className="space-y-0.5">
          {PRIMARY.map((it) => (
            <NavLink key={it.href} item={it} />
          ))}
        </ul>

        <div className="label-micro px-3 mt-6 mb-2">Weitere</div>
        <ul className="space-y-0.5">
          {SECONDARY.map((it) => (
            <NavLink key={it.href} item={it} />
          ))}
        </ul>
      </nav>
      <UserCard />
    </aside>
  );
}

function BrandHeader() {
  return (
    <Link
      href="/"
      className="flex items-center gap-2 px-5 py-5 group"
    >
      <span className="size-7 rounded-xl bg-[var(--color-accent)] text-[var(--color-accent-fg)] flex items-center justify-center">
        <CompassIcon className="size-4" />
      </span>
      <span className="font-semibold tracking-tight text-[15px] group-hover:opacity-80">
        Causal BI
      </span>
    </Link>
  );
}

function NavLink({ item }: { item: NavItem }) {
  const pathname = usePathname();
  const active =
    item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
  const Icon = item.icon;
  return (
    <li>
      <Link
        href={item.href}
        className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
          active
            ? "bg-[var(--color-surface)] text-[var(--color-fg)] font-medium shadow-[0_1px_2px_rgba(0,0,0,0.03)]"
            : "text-[var(--color-muted)] hover:text-[var(--color-fg)] hover:bg-[var(--color-surface-sunken)]"
        }`}
      >
        <Icon className="size-4 shrink-0" />
        <span className="truncate">{item.label}</span>
      </Link>
    </li>
  );
}

function UserCard() {
  const { user, isLoading } = useUser();

  if (isLoading) {
    return (
      <div className="border-t border-[var(--color-border)] px-3 py-3">
        <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg animate-pulse">
          <span className="size-7 rounded-full bg-[var(--color-surface-sunken)] shrink-0" />
          <div className="h-3 w-20 rounded bg-[var(--color-surface-sunken)]" />
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="border-t border-[var(--color-border)] px-3 py-3">
        <a
          href="/auth/login"
          className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-[var(--color-surface-sunken)] text-sm font-medium"
        >
          <span className="size-7 rounded-full bg-[var(--color-accent)] text-[var(--color-accent-fg)] flex items-center justify-center shrink-0">
            <LogIn className="size-3.5" />
          </span>
          <span>Anmelden</span>
        </a>
      </div>
    );
  }

  const name =
    (user.name as string | undefined) ??
    (user.email as string | undefined) ??
    "Angemeldet";
  const sub = (user.email as string | undefined) ?? "Auth0";
  const picture = user.picture as string | undefined;

  return (
    <div className="border-t border-[var(--color-border)] px-3 py-3">
      <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg">
        <span className="size-7 rounded-full bg-[var(--color-surface-sunken)] flex items-center justify-center shrink-0 overflow-hidden">
          {picture ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={picture} alt={name} className="size-full object-cover" />
          ) : (
            <User2 className="size-3.5 text-[var(--color-muted)]" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-medium truncate">{name}</div>
          <div className="text-[10px] text-[var(--color-muted)] truncate">
            {sub}
          </div>
        </div>
        <a
          href="/auth/logout"
          title="Abmelden"
          aria-label="Abmelden"
          className="text-[var(--color-muted)] hover:text-[var(--color-fg)] shrink-0 p-1"
        >
          <LogOut className="size-3.5" />
        </a>
      </div>
    </div>
  );
}
