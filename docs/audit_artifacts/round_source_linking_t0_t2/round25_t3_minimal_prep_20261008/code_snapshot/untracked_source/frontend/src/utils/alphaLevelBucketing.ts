import type { AlphaActivation } from "../api/types";

// John's Alpha-level UI partition (John Item 8, Alpha-Level Display
// Normalization). Display level and blocked status are two orthogonal
// dimensions: the primary bucket below is derived ONLY from the
// authoritative display level (activation_level, falling back to
// qualified_level/status for a historical payload) and is never
// overridden by is_blocked. A blocked Alpha keeps its own display level
// (e.g. a capped_active Alpha blocked from "dominant" stays in "Capped
// active alphas") and is additionally, independently surfaced in the
// orthogonal Blocked view (see StructureGraphPage's own `blockedAlphas`)
// -- it may legitimately appear in both places at once.
//
// Round 5 (2026-10-04): extracted out of StructureGraphPage.tsx (a react-
// refresh/only-export-components fix -- that file's default export is a
// component, and Fast Refresh breaks when a component file also exports
// plain values/functions). Moved here rather than disabled, since
// StructuralSnapshot.tsx already imports these as real, reused utility
// logic, not component-local detail.
export type AlphaLevelBucket = "active" | "capped_active" | "dominant" | "regime_level" | "candidate";

export const ALPHA_LEVEL_BUCKETS: { key: AlphaLevelBucket; title: string }[] = [
  { key: "active", title: "Active alphas" },
  { key: "capped_active", title: "Capped active alphas" },
  { key: "dominant", title: "Dominant alphas" },
  { key: "regime_level", title: "Regime-level alphas" },
  { key: "candidate", title: "Candidate alphas" },
];

/** Exported (Product Demo Hardening Phase 2B) so StructuralSnapshot can
 * reuse this exact, already-production bucketing logic for the main
 * Research page's compact Active Structures list -- never a second,
 * independently-invented definition of "meaningfully active." */
export function bucketForAlpha(alpha: AlphaActivation): AlphaLevelBucket {
  // activation_level is the backend's own presentation-only display field
  // (alpha_level_classifier.CAPPED_ACTIVE et al.) -- read directly, never
  // recomputed here from score/is_blocked/blocked_from. qualified_level,
  // then `status`, are the fallback for a historical payload that
  // predates activation_level entirely.
  const level = alpha.activation_level ?? alpha.qualified_level ?? alpha.status;
  if (level === "capped_active") return "capped_active";
  if (level === "regime_level") return "regime_level";
  if (level === "dominant") return "dominant";
  if (level === "active") return "active";
  return "candidate";
}
