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
  const selectedNodeConflictCount = selectedNode
    ? selectedNode.alpha_ids.reduce((count, alphaId) => {
        if (!conflicts || !("conflicts" in conflicts)) return count;
        return (
          count +
          conflicts.conflicts.filter((conflict) => conflict.alpha_a === alphaId || conflict.alpha_b === alphaId).length
        );
      }, 0)
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
                  conflictCount={selectedNodeConflictCount}
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
                isDominant
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
