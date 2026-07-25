import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { getResearchConflicts, getResearchGraph } from "../api/client";
import { ApiError, describeApiError } from "../api/errors";
import type { ConflictsResult, StructureGraphResult } from "../api/types";
import { RunNavigation } from "../components/RunNavigation";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingPanel } from "../components/LoadingPanel";
import { EmptyState } from "../components/EmptyState";
import { AlphaCard } from "../components/AlphaCard";
import { StructureGraphView } from "../graph/StructureGraphView";
import type { SelectableGraphNode } from "../graph/graphTypes";

function useGraphAndConflicts(runId: string | undefined) {
  const [graph, setGraph] = useState<StructureGraphResult | null>(null);
  const [conflicts, setConflicts] = useState<ConflictsResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    setIsLoading(true);
    setError(null);
    Promise.all([
      getResearchGraph(runId, { signal: controller.signal }),
      getResearchConflicts(runId, { signal: controller.signal }),
    ])
      .then(([graphResult, conflictsResult]) => {
        if (controller.signal.aborted) return;
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

  return { graph, conflicts, error, isLoading, reload: () => setReloadToken((token) => token + 1) };
}

export function StructureGraphPage() {
  const { runId } = useParams<{ runId: string }>();
  const { graph, conflicts, error, isLoading, reload } = useGraphAndConflicts(runId);
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
            <dt>Dominant alphas</dt>
            <dd>{graph.dominant_alphas.length}</dd>
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

      <section className="panel dominant-alphas-panel">
        <h2>Dominant alphas</h2>
        {graph.dominant_alphas.length === 0 ? (
          <EmptyState title="No dominant alphas for this run" />
        ) : (
          <div className="alpha-card-grid">
            {graph.dominant_alphas.map((alpha) => (
              <AlphaCard
                key={alpha.alpha_id}
                alphaId={alpha.alpha_id}
                alphaName={alpha.alpha_name}
                activationScore={alpha.activation_score}
                status={alpha.status}
                direction={alpha.direction}
                evidenceCount={alpha.evidence_summary.evidence_count}
                distinctSupportingAgents={alpha.evidence_summary.distinct_supporting_agents}
                relatedConflicts={relatedConflictsFor(alpha.alpha_id)}
                evidenceDetail={
                  graph.activation.alphas.find((entry) => entry.alpha_id === alpha.alpha_id)
                    ?.evidence_detail ?? null
                }
                activation={
                  graph.activation.alphas.find((entry) => entry.alpha_id === alpha.alpha_id) ??
                  null
                }
                isDominant
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
