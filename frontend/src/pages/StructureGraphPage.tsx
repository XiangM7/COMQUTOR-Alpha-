import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { getResearchConflicts, getResearchGraph } from "../api/client";
import { ApiError, describeApiError } from "../api/errors";
import type { AlphaActivation, ConflictsResult, StructureGraphResult } from "../api/types";
import { RunNavigation } from "../components/RunNavigation";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingPanel } from "../components/LoadingPanel";
import { EmptyState } from "../components/EmptyState";
import { AlphaCard } from "../components/AlphaCard";
import { StructureGraphView } from "../graph/StructureGraphView";
import type { SelectableGraphNode } from "../graph/graphTypes";

// John's five-way, mutually-exclusive UI partition (task
// B4_ACTIVATION_LEVEL_ALIGNMENT, Decision 2). Priority order matters:
// is_blocked always wins first (an alpha that reached e.g. "active" only
// because it was blocked from "dominant" is shown as Blocked, not Active),
// then regime_level, then dominant, then active; everything else
// (candidate, or -- Decision 3 -- a historical inactive/watch payload) is
// Candidate. Backend qualified counts (run_audit's
// active_alpha_count/dominant_alpha_count/etc.) are computed independently
// and are not required to match this display-only partition's bucket
// sizes -- see comment on ADMISSIBLE_STATUSES/qualified counts.
type AlphaLevelBucket = "active" | "dominant" | "regime_level" | "candidate" | "blocked";

const ALPHA_LEVEL_BUCKETS: { key: AlphaLevelBucket; title: string }[] = [
  { key: "active", title: "Active alphas" },
  { key: "dominant", title: "Dominant alphas" },
  { key: "regime_level", title: "Regime-level alphas" },
  { key: "candidate", title: "Candidate alphas" },
  { key: "blocked", title: "Blocked alphas" },
];

function bucketForAlpha(alpha: AlphaActivation): AlphaLevelBucket {
  if (alpha.is_blocked === true) return "blocked";
  // qualified_level is always identical to `status` once B4 has run;
  // falling back to `status` here is what makes a historical payload
  // (predating qualified_level entirely) partition safely instead of
  // every alpha silently landing in "candidate".
  const level = alpha.qualified_level ?? alpha.status;
  if (level === "regime_level") return "regime_level";
  if (level === "dominant") return "dominant";
  if (level === "active") return "active";
  return "candidate";
}

function useGraphAndConflicts(runId: string | undefined) {
  const [graph, setGraph] = useState<StructureGraphResult | null>(null);
  const [conflicts, setConflicts] = useState<ConflictsResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  // Sprint 1 (Run Identity Integrity and Complete Artifact Export), Track
  // A1/frontend: a defensive data-integrity flag, distinct from `error`.
  // The AbortController below already prevents a *stale* (superseded)
  // request from ever overwriting newer state; this instead guards
  // against a response whose own embedded run_id disagrees with the
  // run_id it was actually requested for -- never silently rendered.
  const [runMismatch, setRunMismatch] = useState(false);

  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    // Clear the previous run's Graph/Conflict data immediately, before
    // the new fetch even starts -- otherwise a run switch (e.g. TSM ->
    // SNDK) keeps rendering the *previous* run's graph (including its
    // own ticker-labeled nodes, such as "TSM Revenue Growth") for the
    // entire loading window, which is exactly what `isLoading && !graph`
    // below is meant to prevent but cannot if `graph` is left stale.
    setGraph(null);
    setConflicts(null);
    setRunMismatch(false);
    setIsLoading(true);
    setError(null);
    Promise.all([
      getResearchGraph(runId, { signal: controller.signal }),
      getResearchConflicts(runId, { signal: controller.signal }),
    ])
      .then(([graphResult, conflictsResult]) => {
        if (controller.signal.aborted) return;
        const graphRunId = "run_id" in graphResult ? graphResult.run_id : null;
        const conflictsRunId = "run_id" in conflictsResult ? conflictsResult.run_id : null;
        if ((graphRunId && graphRunId !== runId) || (conflictsRunId && conflictsRunId !== runId)) {
          setRunMismatch(true);
          setIsLoading(false);
          return;
        }
        setGraph(graphResult);
        setConflicts(conflictsResult);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        const apiError = cause instanceof ApiError ? cause : ApiError.network();
        if (!apiError.isAborted) setError(apiError);
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, [runId, reloadToken]);

  return {
    graph,
    conflicts,
    error,
    isLoading,
    runMismatch,
    reload: () => setReloadToken((token) => token + 1),
  };
}

export function StructureGraphPage() {
  const { runId } = useParams<{ runId: string }>();
  const { graph, conflicts, error, isLoading, runMismatch, reload } = useGraphAndConflicts(runId);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const conflictAlphaIds = useMemo(() => {
    if (!conflicts || !("conflicts" in conflicts)) return new Set<string>();
    const ids = new Set<string>();
    for (const conflict of conflicts.conflicts) {
      ids.add(conflict.alpha_a);
      ids.add(conflict.alpha_b);
    }
    return ids;
  }, [conflicts]);

  // Reverse index: alpha_id -> human-readable labels of this run's admitted
  // conflicts involving that alpha ("A101 vs A304"). null (no conflict data
  // loaded) is distinct from an empty list (data loaded, no conflicts).
  const relatedConflictsByAlpha = useMemo(() => {
    if (!conflicts || !("conflicts" in conflicts)) return null;
    const index = new Map<string, string[]>();
    for (const conflict of conflicts.conflicts) {
      const label = `${conflict.alpha_a} vs ${conflict.alpha_b}`;
      for (const alphaId of [conflict.alpha_a, conflict.alpha_b]) {
        const existing = index.get(alphaId) ?? [];
        if (!existing.includes(label)) existing.push(label);
        index.set(alphaId, existing);
      }
    }
    return index;
  }, [conflicts]);

  const relatedConflictsFor = (alphaId: string): string[] | null =>
    relatedConflictsByAlpha === null ? null : relatedConflictsByAlpha.get(alphaId) ?? [];

  const dominantAlphaIds = useMemo(() => {
    if (!graph || !("dominant_alphas" in graph)) return new Set<string>();
    return new Set(graph.dominant_alphas.map((alpha) => alpha.alpha_id));
  }, [graph]);

  // The five-way partition itself (see bucketForAlpha above) -- built once
  // from the full, authoritative per-alpha activation list (never the
  // narrower dominant_alphas/active_alphas/etc. summary collections, which
  // are allowed to overlap with each other and are not a valid source for
  // a mutually-exclusive partition).
  const alphasByBucket = useMemo(() => {
    const buckets: Record<AlphaLevelBucket, AlphaActivation[]> = {
      active: [],
      dominant: [],
      regime_level: [],
      candidate: [],
      blocked: [],
    };
    if (!graph || !("activation" in graph)) return buckets;
    for (const alpha of graph.activation.alphas) {
      buckets[bucketForAlpha(alpha)].push(alpha);
    }
    return buckets;
  }, [graph]);

  // True when every scored alpha in this run predates task
  // B4_ACTIVATION_LEVEL_ALIGNMENT (no qualified_level anywhere) -- used to
  // label the whole partition as a legacy classification rather than
  // implying these five sections are B4-authoritative for an old run.
  const isLegacyClassification = useMemo(() => {
    if (!graph || !("activation" in graph)) return false;
    const alphas = graph.activation.alphas;
    return alphas.length > 0 && alphas.every((alpha) => alpha.qualified_level == null);
  }, [graph]);

  const selectableNodes: SelectableGraphNode[] = useMemo(() => {
    if (!graph || !("nodes" in graph)) return [];
    return graph.nodes.map((node) => ({
      ...node,
      isDominant: node.alpha_ids.some((id) => dominantAlphaIds.has(id)),
      isConflictRelated: node.alpha_ids.some((id) => conflictAlphaIds.has(id)),
    }));
  }, [graph, dominantAlphaIds, conflictAlphaIds]);

  if (!runId) {
    return <EmptyState title="Missing run_id" />;
  }

  if (isLoading && !graph) {
    return (
      <div className="structure-graph-page">
        <RunNavigation runId={runId} />
        <LoadingPanel label="Loading structure graph…" />
      </div>
    );
  }

  if (runMismatch) {
    return (
      <div className="structure-graph-page">
        <RunNavigation runId={runId} />
        <ErrorPanel
          message="Data Integrity Warning: the server returned data for a different run than the one currently selected. Refusing to render it."
          onRetry={reload}
        />
      </div>
    );
  }

  if (error) {
    return (
      <div className="structure-graph-page">
        <RunNavigation runId={runId} />
        <ErrorPanel message={describeApiError(error)} onRetry={reload} />
      </div>
    );
  }

  if (!graph || !("nodes" in graph)) {
    const errorCode = graph && "error_code" in graph ? graph.error_code : null;
    const message = graph && "message" in graph ? graph.message : null;
    return (
      <div className="structure-graph-page">
        <RunNavigation runId={runId} />
        <EmptyState
          title={errorCode === "GRAPH_NOT_READY" ? "Structure graph is not ready yet" : "Structure graph unavailable"}
          description={message ?? "This research run does not have a structure graph yet."}
        />
      </div>
    );
  }

  const selectedNode = selectableNodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedNodeActivation = selectedNode
    ? graph.activation.alphas.find((alpha) => selectedNode.alpha_ids.includes(alpha.alpha_id))
    : null;

  return (
    <div className="structure-graph-page">
      <RunNavigation runId={runId} />

      <section className="panel graph-overview-panel">
        <h1>Structure graph — {graph.ticker ?? "Unknown ticker"}</h1>
        <dl className="graph-overview-meta">
          <div>
            <dt>Schema version</dt>
            <dd>{graph.schema_version}</dd>
          </div>
          <div>
            <dt>Activation formula</dt>
            <dd>
              {graph.primary_activation_version ??
                graph.activation.formula_version ??
                "Not available"}
            </dd>
          </div>
          <div>
            {/* Backward-compatible, pre-existing meaning: dominant OR
                regime_level (task B4_ACTIVATION_LEVEL_ALIGNMENT section 12
                -- an A2-frozen field, never redefined). Labeled explicitly
                to avoid ambiguity with the exclusive "Dominant alphas"
                section below, which counts dominant only. */}
            <dt>Dominant or regime-level alphas</dt>
            <dd>{graph.dominant_alphas.length}</dd>
          </div>
          <div>
            <dt>Active alphas</dt>
            <dd>{alphasByBucket.active.length}</dd>
          </div>
          <div>
            <dt>Regime-level alphas</dt>
            <dd>{alphasByBucket.regime_level.length}</dd>
          </div>
          <div>
            <dt>Candidate alphas</dt>
            <dd>{alphasByBucket.candidate.length}</dd>
          </div>
          <div>
            <dt>Blocked alphas</dt>
            <dd>{alphasByBucket.blocked.length}</dd>
          </div>
          <div>
            <dt>Nodes</dt>
            <dd>{graph.nodes.length}</dd>
          </div>
          <div>
            <dt>Edges</dt>
            <dd>{graph.edges.length}</dd>
          </div>
        </dl>
        {isLegacyClassification ? (
          <p className="graph-overview-legacy-note" role="note">
            Legacy classification — this run predates the B4 alpha-level
            classifier; the sections below use each alpha's pre-existing
            activation status only.
          </p>
        ) : null}
      </section>

      {graph.nodes.length === 0 ? (
        <EmptyState title="This structure graph has no nodes" />
      ) : (
        <div className="structure-graph-layout">
          <section className="panel structure-graph-panel">
            <h2>Graph</h2>
            {graph.edges.length === 0 ? (
              <p className="structure-graph-no-edges" role="note">
                No admissible structural relationships were extracted. The
                factors below were identified, but no evidence-backed causal,
                supportive, or conflicting relationship between them was
                admitted.
              </p>
            ) : null}
            <StructureGraphView
              nodes={selectableNodes}
              edges={graph.edges}
              selectedNodeId={selectedNodeId}
              onSelectNode={setSelectedNodeId}
            />
          </section>
          <aside className="panel structure-graph-detail-panel" aria-label="Node detail">
            <h2>Node detail</h2>
            {selectedNode ? (
              selectedNodeActivation ? (
                <AlphaCard
                  alphaId={selectedNodeActivation.alpha_id}
                  alphaName={selectedNodeActivation.alpha_name}
                  activationScore={selectedNodeActivation.activation_score}
                  status={selectedNodeActivation.status}
                  direction={selectedNodeActivation.direction}
                  evidenceCount={selectedNodeActivation.evidence_count}
                  distinctSupportingAgents={selectedNodeActivation.distinct_supporting_agents}
                  relatedConflicts={relatedConflictsFor(selectedNodeActivation.alpha_id)}
                  evidenceDetail={selectedNodeActivation.evidence_detail}
                  activation={selectedNodeActivation}
                  isDominant={selectedNode.isDominant}
                />
              ) : (
                <EmptyState
                  title={selectedNode.label}
                  description="This factor node is not mapped to a scored Alpha."
                />
              )
            ) : (
              <p className="structure-graph-detail-placeholder">
                Select a node to see its Alpha activation details.
              </p>
            )}
          </aside>
        </div>
      )}

      <section className="panel structure-graph-edges-panel">
        <h2>Structural relationships</h2>
        {graph.edges.length === 0 ? (
          <p className="structure-graph-no-edges">
            No admissible structural relationships were extracted.
          </p>
        ) : (
          <ul className="structure-graph-edge-list">
            {graph.edges.map((edge) => (
              <li key={`${edge.source}-${edge.target}-${edge.edge_type}`} className="structure-graph-edge-item">
                <p className="structure-graph-edge-label">
                  <strong>{edge.source}</strong> → <strong>{edge.target}</strong>{" "}
                  <span className={`edge-type-label edge-type-${edge.edge_type}`}>{edge.edge_type}</span>{" "}
                  <span className="edge-assertion-label">({edge.assertion_status})</span>
                </p>
                <p className="structure-graph-edge-meta">
                  Weight {edge.weight.toFixed(2)}
                  {edge.agents.length > 0 ? <> · Agents: {edge.agents.join(", ")}</> : null}
                </p>
                {edge.evidence.length > 0 ? (
                  <ul className="structure-graph-edge-evidence">
                    {edge.evidence.map((text, index) => (
                      <li key={`${edge.claim_ids[index] ?? index}`}>{text}</li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* John's five-way, mutually-exclusive Alpha partition (task
          B4_ACTIVATION_LEVEL_ALIGNMENT, Decision 2) -- one section per
          bucket, each alpha appearing in exactly one via bucketForAlpha
          above. Each alpha here is the full activation entry already, so
          no separate lookup against graph.activation.alphas is needed. */}
      {ALPHA_LEVEL_BUCKETS.map(({ key, title }) => {
        const alphas = alphasByBucket[key];
        return (
          <section key={key} className={`panel alpha-level-panel alpha-level-panel-${key}`}>
            <h2>{title}</h2>
            {alphas.length === 0 ? (
              <EmptyState title={`No ${title.toLowerCase()} for this run`} />
            ) : (
              <div className="alpha-card-grid">
                {alphas.map((alpha) => (
                  <AlphaCard
                    key={alpha.alpha_id}
                    alphaId={alpha.alpha_id}
                    alphaName={alpha.alpha_name}
                    activationScore={alpha.activation_score}
                    status={alpha.status}
                    direction={alpha.direction}
                    evidenceCount={alpha.evidence_count}
                    distinctSupportingAgents={alpha.distinct_supporting_agents}
                    relatedConflicts={relatedConflictsFor(alpha.alpha_id)}
                    evidenceDetail={alpha.evidence_detail}
                    activation={alpha}
                    isDominant={key === "dominant"}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
