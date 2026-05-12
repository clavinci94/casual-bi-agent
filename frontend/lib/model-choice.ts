/**
 * Per-browser model preference for the investigator.
 *
 * Persisted in localStorage so the user picks once. The "id" is the
 * literal Anthropic model identifier — passed straight through to
 * POST /api/investigations/llm as the `model` field.
 */

const STORAGE_KEY = "biq.model_choice";

export type ModelTier = "haiku" | "sonnet" | "opus";

export type ModelChoice = {
  tier: ModelTier;
  id: string;
  /** Plain-German name shown on the picker card. */
  name: string;
  /** One-line positioning. */
  blurb: string;
  /** Approximate cost per investigation in CHF (rounded, after cache). */
  costHint: string;
  /** When the user should consider this tier. */
  bestFor: string;
};

export const MODELS: Record<ModelTier, ModelChoice> = {
  haiku: {
    tier: "haiku",
    id: "claude-haiku-4-5-20251001",
    name: "Schnell & günstig",
    blurb:
      "Für Routine-Checks und einfache Fragen, wenn es schnell gehen muss.",
    costHint: "≈ CHF 0,05 pro Analyse",
    bestFor: "Routine-Auswertungen",
  },
  sonnet: {
    tier: "sonnet",
    id: "claude-sonnet-4-6",
    name: "Standard",
    blurb:
      "Ausgewogene Tiefe und Kosten. Für die meisten geschäftlichen Fragen geeignet.",
    costHint: "≈ CHF 0,15 pro Analyse",
    bestFor: "Standard-Untersuchungen",
  },
  opus: {
    tier: "opus",
    id: "claude-opus-4-7",
    name: "Maximale Tiefe",
    blurb:
      "Für komplexe, mehrschichtige Fälle, wo Qualität wichtiger ist als Kosten.",
    costHint: "≈ CHF 0,80 pro Analyse",
    bestFor: "Komplexe Sonderfälle",
  },
};

export const DEFAULT_TIER: ModelTier = "sonnet";

export function getStoredTier(): ModelTier {
  if (typeof window === "undefined") return DEFAULT_TIER;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw === "haiku" || raw === "sonnet" || raw === "opus") return raw;
  return DEFAULT_TIER;
}

export function setStoredTier(tier: ModelTier): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, tier);
}
