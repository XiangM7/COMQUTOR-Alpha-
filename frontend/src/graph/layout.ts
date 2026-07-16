import type { GraphLayoutResult, GraphNodePosition, StructureGraphEdge, StructureGraphNode } from "./graphTypes";

/**
 * Deterministic, layered layout for the Structure Graph. No physics
 * simulation, no randomness: the same nodes/edges always produce the same
 * coordinates.
 *
 * Layering: each node's layer is the length of the longest `causal`-edge
 * path reaching it from a causal root (0 for a node with no incoming causal
 * edge) -- causal edges are documented (graph_builder.py) to run in
 * increasing rank order upstream, so this terminates in at most
 * `node_count` relaxation passes even if that invariant were ever violated
 * (a defensive bound, not a trust assumption). `supportive`/`conflicting`
 * edges do not affect layering (they are not causal-ordered), only causal
 * edges do.
 *
 * Within a layer, nodes are ordered by their own `id` (stable, always the
 * same regardless of input array order or dict iteration order upstream).
 */
export function computeDeterministicLayout(
  nodes: Pick<StructureGraphNode, "id">[],
  edges: Pick<StructureGraphEdge, "source" | "target" | "edge_type">[]
): GraphLayoutResult {
  const nodeIds = [...new Set(nodes.map((node) => node.id))].sort();
  const nodeIdSet = new Set(nodeIds);
  const causalEdges = edges.filter(
    (edge) => edge.edge_type === "causal" && nodeIdSet.has(edge.source) && nodeIdSet.has(edge.target)
  );

  const layer = new Map<string, number>();
  for (const id of nodeIds) layer.set(id, 0);

  const maxIterations = nodeIds.length + 1;
  for (let iteration = 0; iteration < maxIterations; iteration += 1) {
    let changed = false;
    for (const edge of causalEdges) {
      const candidate = (layer.get(edge.source) ?? 0) + 1;
      if (candidate > (layer.get(edge.target) ?? 0)) {
        layer.set(edge.target, candidate);
        changed = true;
      }
    }
    if (!changed) break;
  }

  const byLayer = new Map<number, string[]>();
  for (const id of nodeIds) {
    const nodeLayer = layer.get(id) ?? 0;
    const bucket = byLayer.get(nodeLayer);
    if (bucket) {
      bucket.push(id);
    } else {
      byLayer.set(nodeLayer, [id]);
    }
  }
  for (const bucket of byLayer.values()) bucket.sort();

  const layerKeys = [...byLayer.keys()];
  const layerCount = layerKeys.length > 0 ? Math.max(...layerKeys) + 1 : 1;
  const maxNodesInLayer =
    layerKeys.length > 0 ? Math.max(...[...byLayer.values()].map((bucket) => bucket.length)) : 1;

  const positions = new Map<string, GraphNodePosition>();
  for (const [nodeLayer, bucket] of byLayer.entries()) {
    bucket.forEach((id, index) => {
      const x = layerCount > 1 ? nodeLayer / (layerCount - 1) : 0.5;
      const y = bucket.length > 1 ? index / (bucket.length - 1) : 0.5;
      positions.set(id, { id, x, y, layer: nodeLayer, indexInLayer: index });
    });
  }

  return { positions, layerCount, maxNodesInLayer };
}
