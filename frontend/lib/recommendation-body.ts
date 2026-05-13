// Parses the (sometimes very long) free-text `body` of a recommendation into
// scannable parts so a manager can grasp the decision in seconds without
// having to read a prose essay.

export type ParsedBody = {
  kernaussage: string;
  beweis?: string;
  steps: string[];
  fullBody: string;
};

const ACTION_KEYWORDS = [
  /Recommended\s+(?:next\s+)?(?:steps?|actions?)[\s\-:]+/i,
  /Empfohlene\s+(?:n[aä]chste\s+)?(?:Schritte|Massnahmen|Maßnahmen)[\s\-:]+/i,
  /Vorschlag[\s\-:]+/i,
  /Vorgeschlagene\s+(?:n[aä]chste\s+)?(?:Schritte|Massnahmen|Maßnahmen)[\s\-:]+/i,
  /Recommendation[\s\-:]+/i,
  /N[aä]chste\s+Schritte[\s\-:]+/i,
];

function firstSentence(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  // German + English sentence-end heuristic: take up to the first ". " that
  // is followed by a capital letter (so "p=0.001" doesn't end the sentence).
  const m = trimmed.match(/^([\s\S]+?[.!?])\s+(?=[A-ZÄÖÜ"„])/);
  return (m?.[1] ?? trimmed).trim();
}

function extractActions(raw: string): string[] {
  // Match: "(1) ...", "1) ...", "1. ..."  — split on the next marker.
  // Be permissive: items may contain commas, sub-clauses, em-dashes, units.
  const matches = Array.from(
    raw.matchAll(
      /(?:^|\s)\(?(\d+)[\.\)]\s+([^]*?)(?=(?:\s\(?\d+[\.\)]\s)|$)/g,
    ),
  );
  const items = matches
    .map((m) => m[2].trim().replace(/[\s;,.]+$/, ""))
    .filter((s) => s.length > 8 && s.length < 400);
  return items;
}

export function parseRecommendationBody(body: string): ParsedBody {
  const fullBody = body.trim();

  // 1. Find an "actions" / "Vorschlag" / "Empfehlung" pivot.
  let actionStart = -1;
  let actionMatchLen = 0;
  for (const re of ACTION_KEYWORDS) {
    const m = fullBody.match(re);
    if (m && m.index !== undefined && (actionStart < 0 || m.index < actionStart)) {
      actionStart = m.index;
      actionMatchLen = m[0].length;
    }
  }

  let prose = fullBody;
  let actionSection = "";
  if (actionStart >= 0) {
    prose = fullBody.slice(0, actionStart).trim();
    actionSection = fullBody.slice(actionStart + actionMatchLen).trim();
  }

  // 2. Try to pull numbered steps out of the action section.
  let steps = extractActions(actionSection);

  // 3. Fallback: if no numbered steps appeared in the action section but the
  // section is short, treat it as a single step. If still nothing, search the
  // full body for stray numbered items.
  if (steps.length === 0 && actionSection) {
    if (actionSection.length < 280) {
      steps = [actionSection.replace(/[\s;,.]+$/, "")];
    } else {
      steps = extractActions(fullBody);
    }
  }
  if (steps.length === 0) {
    steps = extractActions(fullBody);
  }

  // 4. Kernaussage: first sentence of the prose part (or full body if there
  // was no action pivot).
  const kernaussage = firstSentence(prose || fullBody);

  // 5. Beweis: everything else from the prose part — only show if it adds
  // information beyond the Kernaussage.
  const proseRest = prose.slice(kernaussage.length).trim();
  const beweis = proseRest.length > 0 ? proseRest : undefined;

  return { kernaussage, beweis, steps, fullBody };
}
