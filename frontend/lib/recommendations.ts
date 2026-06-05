import type { Recommendation } from "./types";

function normalizeTitle(title: string): string {
  return title
    .toLocaleLowerCase("de-CH")
    .replace(/\s+/g, " ")
    .trim();
}

export function uniqueRecommendationsByTitle(
  recommendations: Recommendation[],
): Recommendation[] {
  const seen = new Set<string>();
  const unique: Recommendation[] = [];

  for (const recommendation of recommendations) {
    const key = normalizeTitle(recommendation.title);
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(recommendation);
  }

  return unique;
}
