// Product Demo Hardening Phase 2D: default-view jargon cleanup.
//
// Single, shared, pure, frontend-only translation from a raw internal
// activation-level token (dominant/regime_level/active/capped_active/
// candidate/watch/inactive) to the product-facing word a stakeholder should
// see. This is DISPLAY TRANSLATION ONLY: it never mutates a stored/API
// value, never gets written back into an API/model object, and never
// introduces a new backend/semantic activation level -- callers keep using
// the raw value for bucketing, CSS classes, and Technical Details; only the
// human-facing label text goes through this formatter.
//
// Centralized here (rather than duplicated per-component, per task section
// 9) so every place a level is rendered as text -- AlphaCard, ConflictCard,
// StructureGraphPage -- shows the exact same product word for the exact
// same underlying state.

const LEVEL_DISPLAY_LABELS: Record<string, string> = {
  dominant: "Dominant",
  // regime_level is a sustained/confirmed form of Dominant from a
  // stakeholder's perspective; the raw distinction remains available
  // wherever the raw value itself is separately preserved (Technical
  // Details, bucket grouping, CSS classes).
  regime_level: "Dominant",
  active: "Active",
  // capped_active is still Active from a stakeholder's perspective; the
  // "why it's limited" detail is conveyed separately (e.g. AlphaCard's own
  // cap-reason row), never invented here.
  capped_active: "Active",
  candidate: "Emerging",
  watch: "Watchlist",
  inactive: "Inactive",
};

/**
 * Format a raw activation-level token for stakeholder-facing display.
 *
 * Fails safe on an unrecognized future value: never crashes, never silently
 * maps it to an incorrect known state -- humanizes it conservatively
 * (underscore-separated words, title-cased) instead.
 */
export function formatActivationLevelForDisplay(rawLevel: string | null | undefined): string {
  if (!rawLevel) return "Not available";
  const known = LEVEL_DISPLAY_LABELS[rawLevel];
  if (known) return known;
  return rawLevel
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
