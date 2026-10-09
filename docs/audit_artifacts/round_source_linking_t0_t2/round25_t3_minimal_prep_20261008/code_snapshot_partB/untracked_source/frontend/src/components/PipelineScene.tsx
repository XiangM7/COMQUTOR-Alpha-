import {
  STRUCTURE_EDGE_COUNT,
  sceneForProgress,
  structureEdgesShown,
  type StageProgress,
  type StageState,
} from "../utils/processingStages";

interface SceneNode {
  key: string;
  label: string;
  state: StageState;
  /** Second node of a pair that pulses half a beat later. */
  offbeat?: boolean;
}

const ANALYST_LABELS: Record<string, string> = {
  market_analysis: "Market",
  sentiment_analysis: "Sentiment",
  news_analysis: "News",
  fundamentals_analysis: "Fundamentals",
};

function stateOf(progress: StageProgress, stage: string): StageState {
  const index = progress.plan.findIndex((entry) => entry.stage === stage);
  return index >= 0 ? (progress.states[index] ?? "pending") : "pending";
}

function nodesForScene(progress: StageProgress, scene: "prep" | "analysts" | "debate"): SceneNode[] {
  if (scene === "debate") {
    const debate = stateOf(progress, "research_debate");
    return [
      { key: "bull", label: "Bull case", state: debate },
      { key: "bear", label: "Bear case", state: debate, offbeat: true },
      { key: "trader", label: "Trader", state: stateOf(progress, "trading_plan") },
      { key: "risk", label: "Risk review", state: stateOf(progress, "risk_review") },
    ];
  }
  return progress.plan
    .filter((entry) => entry.group === "analysts")
    .map((entry) => ({
      key: entry.stage,
      label: ANALYST_LABELS[entry.stage] ?? entry.label,
      state: scene === "prep" ? "pending" : (stateOf(progress, entry.stage)),
    }));
}

function NodeRow({ nodes }: { nodes: SceneNode[] }) {
  return (
    <ol className="scene-row">
      {nodes.map((node) => (
        <li key={node.key} className="scene-node">
          <span
            className={`scene-dot scene-dot-${node.state}${node.state === "current" ? (node.offbeat ? " scene-dot-offbeat" : " scene-dot-pulse") : ""}`}
          >
            {node.state === "done" ? (
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 7.2 5.8 10 11 4" />
              </svg>
            ) : null}
          </span>
          <span className={`scene-label scene-label-${node.state}`}>{node.label}</span>
        </li>
      ))}
    </ol>
  );
}

type NodeKey = "c1" | "c2" | "c3" | "f1" | "f2" | "a1" | "a2" | "x";

const GRAPH_NODES: Record<NodeKey, { x: number; y: number; r: number; label?: string; labelAbove?: boolean }> = {
  c1: { x: 60, y: 28, r: 6, label: "Claims", labelAbove: true },
  c2: { x: 60, y: 86, r: 6 },
  c3: { x: 60, y: 144, r: 6 },
  f1: { x: 200, y: 56, r: 9, label: "Evidence" },
  f2: { x: 200, y: 116, r: 9 },
  a1: { x: 340, y: 48, r: 13, label: "Alphas", labelAbove: true },
  a2: { x: 340, y: 124, r: 13 },
  x: { x: 480, y: 86, r: 16, label: "Conflict" },
};

/** Claims -> evidence -> Alphas -> conflict, one more connection per
 * structure-analysis stage reached. */
const GRAPH_EDGES: ReadonlyArray<readonly [NodeKey, NodeKey]> = [
  ["c1", "f1"],
  ["c2", "f1"],
  ["c3", "f2"],
  ["f1", "a1"],
  ["f2", "a2"],
  ["f2", "a1"],
  ["a1", "x"],
  ["a2", "x"],
];

function StructureGraph({ progress, live }: { progress: StageProgress; live: boolean }) {
  const shown = Math.min(STRUCTURE_EDGE_COUNT, structureEdgesShown(progress));
  const linked = new Set<NodeKey>();
  GRAPH_EDGES.forEach(([from, to], index) => {
    if (index < shown) {
      linked.add(from);
      linked.add(to);
    }
  });

  return (
    <svg className="scene-graph" viewBox="0 0 560 168" role="presentation" focusable="false">
      {GRAPH_EDGES.map(([from, to], index) => {
        const a = GRAPH_NODES[from];
        const b = GRAPH_NODES[to];
        const on = index < shown;
        const latest = live && on && index === shown - 1;
        return (
          <line
            key={`${from}-${to}`}
            className={latest ? "scene-edge scene-edge-latest" : "scene-edge"}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            pathLength={1}
            strokeDasharray="1 1"
            strokeDashoffset={on ? 0 : 1}
          />
        );
      })}
      {(Object.keys(GRAPH_NODES) as NodeKey[]).map((key) => {
        const node = GRAPH_NODES[key];
        const on = linked.has(key);
        return (
          <g key={key}>
            <circle className={on ? "scene-graph-node scene-graph-node-on" : "scene-graph-node"} cx={node.x} cy={node.y} r={node.r} />
            {node.label ? (
              <text
                className={on ? "scene-graph-label scene-graph-label-on" : "scene-graph-label"}
                x={node.x}
                y={node.labelAbove ? node.y - node.r - 9 : node.y + node.r + 18}
                textAnchor="middle"
              >
                {node.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

interface PipelineSceneProps {
  progress: StageProgress;
  caption: string;
  /** The run is still going: only then is the newest connection drawn in
   * the accent color, as the one being made right now. */
  live: boolean;
}

/**
 * Decorative picture of where the run is, in three scenes chosen only by the
 * real current stage: analysts at work, bull/bear debate and decision, and
 * the structure being built. Everything visual is hidden from assistive
 * technology -- the Stages list carries the same facts as text -- and the
 * caption underneath says in words what is happening.
 */
export function PipelineScene({ progress, caption, live }: PipelineSceneProps) {
  const scene = sceneForProgress(progress);
  return (
    <section aria-label="Pipeline" className="pipeline-card">
      <div className="pipeline-stage" aria-hidden="true">
        {scene === "structure" ? (
          <StructureGraph progress={progress} live={live} />
        ) : (
          <NodeRow nodes={nodesForScene(progress, scene)} />
        )}
      </div>
      <p className="pipeline-caption" key={caption}>
        {caption}
      </p>
    </section>
  );
}
