import { useMemo } from "react";
import { computeDeterministicLayout } from "./layout";
import type { SelectableGraphNode, StructureGraphEdge } from "./graphTypes";

const VIEW_WIDTH = 960;
const VIEW_HEIGHT = 560;
const PADDING = 64;

interface StructureGraphViewProps {
  nodes: SelectableGraphNode[];
  edges: StructureGraphEdge[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}

const EDGE_TYPE_LABELS: Record<string, string> = {
  causal: "causal",
  supportive: "supportive",
  conflicting: "conflicting",
};

function nodeShape(node: SelectableGraphNode): "star" | "diamond" | "circle" {
  if (node.isDominant) return "star";
  if (node.isConflictRelated) return "diamond";
  return "circle";
}

function nodeStatusText(node: SelectableGraphNode): string {
  const parts: string[] = [];
  if (node.isDominant) parts.push("dominant alpha");
  if (node.isConflictRelated) parts.push("conflict-related");
  if (node.alpha_ids.length === 0) parts.push("unmapped factor");
  return parts.length > 0 ? parts.join(", ") : "factor";
}

export function StructureGraphView({ nodes, edges, selectedNodeId, onSelectNode }: StructureGraphViewProps) {
  const layout = useMemo(() => computeDeterministicLayout(nodes, edges), [nodes, edges]);

  const scaled = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    for (const node of nodes) {
      const position = layout.positions.get(node.id);
      if (!position) continue;
      map.set(node.id, {
        x: PADDING + position.x * (VIEW_WIDTH - PADDING * 2),
        y: PADDING + position.y * (VIEW_HEIGHT - PADDING * 2),
      });
    }
    return map;
  }, [nodes, layout]);

  if (nodes.length === 0) {
    return (
      <div className="panel empty-state">
        <p className="empty-state-title">This structure graph has no nodes.</p>
      </div>
    );
  }

  return (
    <div className="structure-graph-view">
      <svg
        role="img"
        aria-labelledby="structure-graph-title"
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        className="structure-graph-svg"
      >
        <title id="structure-graph-title">
          Structure graph with {nodes.length} factor nodes and {edges.length} relationships
        </title>
        <g className="structure-graph-edges">
          {edges.map((edge) => {
            const from = scaled.get(edge.source);
            const to = scaled.get(edge.target);
            if (!from || !to) return null;
            return (
              <line
                key={`${edge.source}->${edge.target}-${edge.edge_type}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                className={`graph-edge graph-edge-${edge.edge_type}`}
              >
                <title>
                  {edge.source} → {edge.target} ({EDGE_TYPE_LABELS[edge.edge_type] ?? edge.edge_type})
                </title>
              </line>
            );
          })}
        </g>
        <g className="structure-graph-nodes">
          {nodes.map((node) => {
            const position = scaled.get(node.id);
            if (!position) return null;
            const shape = nodeShape(node);
            const isSelected = node.id === selectedNodeId;
            const label = `${node.label} (${node.id}). ${nodeStatusText(node)}. Score ${node.score.toFixed(2)}.`;
            return (
              <g
                key={node.id}
                tabIndex={0}
                role="button"
                aria-label={label}
                aria-pressed={isSelected}
                className={`graph-node graph-node-${shape}${isSelected ? " graph-node-selected" : ""}`}
                transform={`translate(${position.x}, ${position.y})`}
                onClick={() => onSelectNode(node.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectNode(node.id);
                  }
                }}
              >
                <NodeMarker shape={shape} />
                <text className="graph-node-label" y={28} textAnchor="middle">
                  {node.label.length > 18 ? `${node.label.slice(0, 17)}…` : node.label}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      <p className="visually-hidden">
        Text alternative: {nodes.length} factor nodes -{" "}
        {nodes.map((node) => `${node.label} (${nodeStatusText(node)})`).join("; ")}.
      </p>
    </div>
  );
}

function NodeMarker({ shape }: { shape: "star" | "diamond" | "circle" }) {
  if (shape === "star") {
    return <polygon points="0,-16 4,-5 16,-5 6,3 10,15 0,8 -10,15 -6,3 -16,-5 -4,-5" className="graph-node-shape" />;
  }
  if (shape === "diamond") {
    return <polygon points="0,-14 14,0 0,14 -14,0" className="graph-node-shape" />;
  }
  return <circle r={12} className="graph-node-shape" />;
}
