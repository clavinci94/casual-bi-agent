"use client";

import { useEffect, useState } from "react";
import { Zap, Sparkles, Gem, Check } from "lucide-react";
import {
  DEFAULT_TIER,
  getStoredTier,
  MODELS,
  setStoredTier,
  type ModelTier,
} from "@/lib/model-choice";

const ORDER: ModelTier[] = ["haiku", "sonnet", "opus"];

const ICONS: Record<ModelTier, typeof Zap> = {
  haiku: Zap,
  sonnet: Sparkles,
  opus: Gem,
};

/**
 * Three clickable cards letting the user pick the LLM tier for the
 * upcoming investigation. The chosen tier is mirrored back to the
 * parent via `onChange` AND persisted to localStorage, so the next
 * visit pre-selects the same tier.
 */
export function ModelPicker({
  value,
  onChange,
}: {
  value: ModelTier;
  onChange: (tier: ModelTier) => void;
}) {
  // Hydrate from localStorage on the client only — without this the
  // SSR-rendered card mismatches whatever was stored, and React would
  // hydrate-flash the previous choice for a frame.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    const stored = getStoredTier();
    if (stored !== value) onChange(stored);
    setHydrated(true);
    // We deliberately read storage once on mount; subsequent changes
    // come through onChange/select() below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function select(tier: ModelTier) {
    setStoredTier(tier);
    onChange(tier);
  }

  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium mb-2">
        Analyse-Modell wählen
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {ORDER.map((tier) => {
          const m = MODELS[tier];
          const Icon = ICONS[tier];
          const active = hydrated && tier === value;
          const recommended = tier === DEFAULT_TIER;
          return (
            <button
              key={tier}
              type="button"
              onClick={() => select(tier)}
              aria-pressed={active}
              className={`relative text-left p-4 rounded-xl border transition-all ${
                active
                  ? "border-[var(--color-accent)] bg-[color-mix(in_oklch,var(--color-accent)_6%,var(--color-surface))] ring-1 ring-[var(--color-accent)]"
                  : "border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-fg)]"
              }`}
            >
              {recommended && !active ? (
                <span className="absolute top-2 right-2 text-[10px] uppercase tracking-wider font-semibold text-[var(--color-accent)]">
                  Empfohlen
                </span>
              ) : null}
              {active ? (
                <span className="absolute top-2 right-2 inline-flex items-center justify-center size-5 rounded-full bg-[var(--color-accent)] text-[var(--color-accent-fg)]">
                  <Check className="size-3.5" />
                </span>
              ) : null}

              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center justify-center size-8 rounded-lg ${
                    active
                      ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)]"
                      : "bg-[var(--color-bg)] text-[var(--color-fg)]"
                  }`}
                >
                  <Icon className="size-4" />
                </span>
                <span className="font-semibold text-sm">{m.name}</span>
              </div>

              <p className="mt-2 text-xs text-[var(--color-muted)] leading-relaxed line-clamp-3">
                {m.blurb}
              </p>

              <div className="mt-3 flex items-center justify-between text-[11px]">
                <span className="text-[var(--color-muted)]">{m.bestFor}</span>
                <span className="font-medium tabular-nums">{m.costHint}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
