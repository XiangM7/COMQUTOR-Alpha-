import type { StructureGraphEdge, StructureGraphNode } from "../api/types";

export interface GraphNodePosition {
  id: string;
  /** Normalized 0..1 coordinates -- callers scale to their own viewBox. */
  x: number;
  y: number;
  layer: number;
  indexInLayer: number;
}

export interface GraphLayoutResult {
  positions: Map<string, GraphNodePosition>;
  layerCount: number;
  maxNodesInLayer: number;
}

export interface SelectableGraphNode extends StructureGraphNode {
  /** True when this node's alpha_ids intersect the run's dominant_alphas. */
  isDominant: boolean;
  /** True when this node's alpha_ids intersect an alpha_id appearing in a
   * real, persisted Week 4 conflict (never guessed by the frontend). */
  isConflictRelated: boolean;
}

export type { StructureGraphEdge, StructureGraphNode };
