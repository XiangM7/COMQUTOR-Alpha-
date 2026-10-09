import { Link } from "react-router-dom";
import type {
  AlphaActivation,
  AlphaClassificationCompletion,
  AlphaConflict,
  CanonicalResearchResponse,
} from "../api/types";
import { describeApiError } from "../api/errors";
import { useResearchGraph } from "../hooks/useResearchGraph";
import { ALPHA_LEVEL_BUCKETS, bucketForAlpha, type AlphaLevelBucket } from "../utils/alphaLevelBucketing";
import { LoadingPanel } from "./LoadingPanel";

// Product Demo Hardening Phase 2B: a compact, top-level orientation section
// for the main Research results page. Presentation-only -- it never
// recomputes an Alpha's level, score, or conflict admissibility; every
// value shown here is read verbatim from the same production fields
// StructureGraphPage/ConflictRadarPage already render in full detail.
//
// "Active Structures" (part A) reuses the graph endpoint (same one
// StructureGraphPage fetches) because CanonicalResearchResponse only
// carries dominant_alphas/main_conflict, not the full Alpha list. Dominant
// (part B) and Main Conflict (part C) are derived directly from `research`
// (already in memory on ResearchRunPage) -- no additional fetch for those.

const ACTIVE_ALPHA_BUCKETS: AlphaLevelBucket[] = ALPHA_LEVEL_BUCKETS.map((b) => b.key).filter(
  (key): key is AlphaLevelBucket => key !== "candidate"
);

function activeAlphasFrom(alphas: AlphaActivation[]): AlphaActivation[] {
  const byBucket = new Map<AlphaLevelBucket, AlphaActivation[]>();
  for (const alpha of alphas) {
    const bucket = bucketForAlpha(alpha);
    const list = byBucket.get(bucket) ?? [];
    list.push(alpha);
    byBucket.set(bucket, list);
  }
  // Preserve the same bucket order StructureGraphPage itself displays
  // (active, capped_active, dominant, regime_level); no new ranking.
  return ACTIVE_ALPHA_BUCKETS.flatMap((bucket) => byBucket.get(bucket) ?? []);
}

function AlphaChip({ alphaId, alphaName }: { alphaId: string; alphaName: string }) {
  return (
    <li className="structural-snapshot-alpha-chip">
      <span className="structural-snapshot-alpha-id">{alphaId}</span>
      <span className="structural-snapshot-alpha-name">{alphaName}</span>
    </li>
  );
}

// 2026-10-06 (round 14, section 6): when the backend reports Alpha
// classification as incomplete, an empty active/dominant/conflict result is
// "cannot be determined yet", never "none exists". Read verbatim from the
// backend's own alpha_classification_status -- not re-derived here.
function isClassificationIncomplete(research: CanonicalResearchResponse): boolean {
  return research.alpha_classification_status === "incomplete";
}

function unresolvedClaimsText(completion: AlphaClassificationCompletion | null | undefined): string | null {
  if (!completion) return null;
  const unresolved = completion.call_failure_count + completion.not_executed_count;
  return `${unresolved} of ${completion.total_claims} claims have no usable classification result`;
}

function ClassificationIncompleteNotice({ research }: { research: CanonicalResearchResponse }) {
  const detail = unresolvedClaimsText(research.alpha_classification_completion);
  return (
    <p className="structural-snapshot-classification-incomplete" role="status">
      Alpha classification is incomplete for this run{detail ? ` (${detail})` : ""}. Empty results below cannot yet be
      read as &ldquo;no such structure exists&rdquo;.
    </p>
  );
}

type GraphState = ReturnType<typeof useResearchGraph>;

function ActiveStructuresSection({ graphState, incomplete }: { graphState: GraphState; incomplete: boolean }) {
  const { graph, isLoading, error, runMismatch, reload } = graphState;

  if (isLoading && !graph) {
    return (
      <div className="structural-snapshot-part structural-snapshot-active">
        <h3>Active structures</h3>
        <LoadingPanel label="Loading structural detail…" />
      </div>
    );
  }

  if (runMismatch) {
    return (
      <div className="structural-snapshot-part structural-snapshot-active">
        <h3>Active structures</h3>
        <p className="structural-snapshot-unavailable">Structural detail is temporarily unavailable.</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="structural-snapshot-part structural-snapshot-active">
        <h3>Active structures</h3>
        <p className="structural-snapshot-unavailable">{describeApiError(error)}</p>
        <button type="button" className="button button-secondary" onClick={reload}>
          Retry
        </button>
      </div>
    );
  }

  if (!graph || !("nodes" in graph)) {
    // GRAPH_NOT_READY (or any other not-ready/unavailable shape) is a
    // distinct state from a genuinely completed, zero-active-Alpha result
    // -- never presented as "no structure dominates" (see Section 19).
    return (
      <div className="structural-snapshot-part structural-snapshot-active">
        <h3>Active structures</h3>
        <p className="structural-snapshot-not-ready">Structural detail is not ready yet for this run.</p>
      </div>
    );
  }

  const activeAlphas = activeAlphasFrom(graph.activation.alphas);

  return (
    <div className="structural-snapshot-part structural-snapshot-active">
      <h3>Active structures</h3>
      {activeAlphas.length === 0 ? (
        incomplete ? (
          <p className="structural-snapshot-not-ready">Cannot be determined yet: Alpha classification is incomplete.</p>
        ) : (
          <p className="structural-snapshot-legitimate-empty">
            No Alpha structure currently meets the active threshold.
          </p>
        )
      ) : (
        <ul className="structural-snapshot-alpha-chip-list">
          {activeAlphas.map((alpha) => (
            <AlphaChip key={alpha.alpha_id} alphaId={alpha.alpha_id} alphaName={alpha.alpha_name} />
          ))}
        </ul>
      )}
    </div>
  );
}

function DominantStructureSection({
  research,
  graphState,
}: {
  research: CanonicalResearchResponse;
  graphState: GraphState;
}) {
  if (research.structure_graph_status !== "ready") {
    return (
      <div className="structural-snapshot-part structural-snapshot-dominant">
        <h3>Dominant structure</h3>
        <p className="structural-snapshot-not-ready">Structural detail is not ready yet for this run.</p>
      </div>
    );
  }

  if (research.dominant_alphas.length === 0 && isClassificationIncomplete(research)) {
    return (
      <div className="structural-snapshot-part structural-snapshot-dominant">
        <h3>Dominant structure</h3>
        <p className="structural-snapshot-not-ready">Cannot be determined yet: Alpha classification is incomplete.</p>
      </div>
    );
  }

  if (research.dominant_alphas.length === 0) {
    // 2026-10-06 (round 12 audit fix): this detail text previously rendered
    // unconditionally whenever dominant_alphas was empty, asserting "several
    // active forces are present" even when activeAlphasFrom(graph.activation
    // .alphas) is ALSO empty -- confirmed factually wrong against a real run
    // (c904d4cc) with zero active AND zero dominant alphas. Now reads the
    // SAME graph data ActiveStructuresSection already fetches (passed down
    // from the shared parent fetch, not a second independent call) so the
    // two panels can never contradict each other.
    const graph = graphState.graph;
    const hasActiveAlphas =
      graph && "nodes" in graph ? activeAlphasFrom(graph.activation.alphas).length > 0 : null;

    return (
      <div className="structural-snapshot-part structural-snapshot-dominant">
        <h3>Dominant structure</h3>
        <p className="structural-snapshot-legitimate-empty">No single structure currently dominates.</p>
        {hasActiveAlphas === true && (
          <p className="structural-snapshot-legitimate-empty-detail">
            Several active forces are present, but none has reached dominant status.
          </p>
        )}
        {hasActiveAlphas === false && (
          <p className="structural-snapshot-legitimate-empty-detail">
            No active structure currently exists for this run.
          </p>
        )}
        {hasActiveAlphas === null && (
          <p className="structural-snapshot-legitimate-empty-detail">
            Active-structure detail could not be loaded to confirm whether any force is currently active.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="structural-snapshot-part structural-snapshot-dominant">
      <h3>Dominant structure</h3>
      <ul className="structural-snapshot-alpha-chip-list">
        {research.dominant_alphas.map((alpha) => (
          <AlphaChip key={alpha.alpha_id} alphaId={alpha.alpha_id} alphaName={alpha.alpha_name} />
        ))}
      </ul>
    </div>
  );
}

// Neither alpha_a/alpha_b's ordering, nor bull/bear, is assumed here --
// mirrors ConflictCard's own bull_structure/bear_structure-first pattern,
// resolving each side's human-readable name by matching alpha_id rather
// than guessing a fixed position.
function conflictSideName(conflict: AlphaConflict, alphaId: string): string {
  if (conflict.bull_structure.alpha_id === alphaId) return conflict.bull_structure.alpha_name;
  if (conflict.bear_structure.alpha_id === alphaId) return conflict.bear_structure.alpha_name;
  return alphaId;
}

function MainConflictSection({ runId, research }: { runId: string; research: CanonicalResearchResponse }) {
  if (research.conflict_status !== "ready") {
    return (
      <div className="structural-snapshot-part structural-snapshot-conflict">
        <h3>Main structural conflict</h3>
        <p className="structural-snapshot-not-ready">Conflict analysis is not ready yet for this run.</p>
      </div>
    );
  }

  const conflict = research.main_conflict;

  if (!conflict && isClassificationIncomplete(research)) {
    return (
      <div className="structural-snapshot-part structural-snapshot-conflict">
        <h3>Main structural conflict</h3>
        <p className="structural-snapshot-not-ready">Cannot be determined yet: Alpha classification is incomplete.</p>
        <Link to={`/runs/${encodeURIComponent(runId)}/conflicts`} className="structural-snapshot-nav-link">
          View conflict details
        </Link>
      </div>
    );
  }

  if (!conflict) {
    return (
      <div className="structural-snapshot-part structural-snapshot-conflict">
        <h3>Main structural conflict</h3>
        <p className="structural-snapshot-legitimate-empty">
          No high-confidence structural conflict is currently admitted. This does not mean the position carries no
          risk.
        </p>
        <Link to={`/runs/${encodeURIComponent(runId)}/conflicts`} className="structural-snapshot-nav-link">
          View conflict details
        </Link>
      </div>
    );
  }

  return (
    <div className="structural-snapshot-part structural-snapshot-conflict">
      <h3>Main structural conflict</h3>
      <p className="structural-snapshot-conflict-pair">
        <span>
          {conflict.alpha_a} — {conflictSideName(conflict, conflict.alpha_a)}
        </span>
        <span className="structural-snapshot-conflict-vs" aria-label="versus">
          vs
        </span>
        <span>
          {conflict.alpha_b} — {conflictSideName(conflict, conflict.alpha_b)}
        </span>
      </p>
      <Link to={`/runs/${encodeURIComponent(runId)}/conflicts`} className="structural-snapshot-nav-link">
        View conflict details
      </Link>
    </div>
  );
}

export function StructuralSnapshot({ runId, research }: { runId: string; research: CanonicalResearchResponse }) {
  // Fetched ONCE here and passed to both ActiveStructuresSection and
  // DominantStructureSection -- previously each panel that needed it would
  // have fetched independently, and DominantStructureSection did not fetch
  // it at all (see that component's own note on the real contradiction this
  // caused).
  const graphState = useResearchGraph(runId);
  return (
    <section className="panel structural-snapshot-panel" aria-labelledby="structural-snapshot-heading">
      <h2 id="structural-snapshot-heading">Structural snapshot</h2>
      {isClassificationIncomplete(research) && <ClassificationIncompleteNotice research={research} />}
      <div className="structural-snapshot-grid">
        <ActiveStructuresSection graphState={graphState} incomplete={isClassificationIncomplete(research)} />
        <DominantStructureSection research={research} graphState={graphState} />
        <MainConflictSection runId={runId} research={research} />
      </div>
      <Link to={`/runs/${encodeURIComponent(runId)}/structure`} className="structural-snapshot-nav-link">
        View structure graph
      </Link>
    </section>
  );
}
