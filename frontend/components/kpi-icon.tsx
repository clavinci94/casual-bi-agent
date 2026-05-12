"use client";

import {
  ShoppingCart,
  Wallet,
  PiggyBank,
  Truck,
  Star,
  Undo2,
  Repeat,
  UserMinus,
  type LucideIcon,
} from "lucide-react";
import type { KpiIconKey } from "@/lib/kpi-metadata";

/**
 * Visual identity for each KPI. Keep this map tight — every key is also
 * documented in lib/kpi-metadata.ts. Adding a new KPI here is the same
 * weight as adding a friendly title.
 */
const ICONS: Record<KpiIconKey, LucideIcon> = {
  cart: ShoppingCart,
  wallet: Wallet,
  piggy: PiggyBank,
  truck: Truck,
  star: Star,
  undo: Undo2,
  repeat: Repeat,
  churn: UserMinus,
};

export function KpiIcon({
  name,
  className = "size-5",
}: {
  name: KpiIconKey;
  className?: string;
}) {
  const Icon = ICONS[name];
  return <Icon className={className} aria-hidden="true" />;
}
