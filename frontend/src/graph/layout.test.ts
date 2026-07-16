import { describe, expect, it } from "vitest";
import { computeDeterministicLayout } from "./layout";

const NODES = [{ id: "b" }, { id: "a" }, { id: "c" }];
const EDGES = [
  { source: "a", target: "b", edge_type: "causal" as const },
  { source: "b", target: "c", edge_type: "causal" as const },
];

describe("computeDeterministicLayout", () => {
  it("produces identical coordinates for the same input across repeated calls", () => {
    const first = computeDeterministicLayout(NODES, EDGES);
    const second = computeDeterministicLayout(NODES, EDGES);
    for (const id of ["a", "b", "c"]) {
      expect(second.positions.get(id)).toEqual(first.positions.get(id));
    }
  });

  it("produces identical coordinates regardless of input node/edge array order", () => {
    const shuffledNodes = [...NODES].reverse();
    const shuffledEdges = [...EDGES].reverse();
    const original = computeDeterministicLayout(NODES, EDGES);
    const shuffled = computeDeterministicLayout(shuffledNodes, shuffledEdges);
    for (const id of ["a", "b", "c"]) {
      expect(shuffled.positions.get(id)).toEqual(original.positions.get(id));
    }
  });

  it("places causally-later nodes in a later layer (monotonically increasing x)", () => {
    const layout = computeDeterministicLayout(NODES, EDGES);
    const a = layout.positions.get("a");
    const b = layout.positions.get("b");
    const c = layout.positions.get("c");
    expect(a?.layer).toBe(0);
    expect(b?.layer).toBe(1);
    expect(c?.layer).toBe(2);
    expect(a?.x).toBeLessThan(b?.x ?? Infinity);
    expect(b?.x).toBeLessThan(c?.x ?? Infinity);
  });

  it("uses stable id-based tie-break ordering within a layer", () => {
    const layout = computeDeterministicLayout(
      [{ id: "z" }, { id: "y" }, { id: "x" }],
      [] // no causal edges -- all three land in layer 0
    );
    const x = layout.positions.get("x");
    const y = layout.positions.get("y");
    const z = layout.positions.get("z");
    // Sorted order x, y, z -> increasing index/y-coordinate.
    expect((x?.indexInLayer ?? 0) < (y?.indexInLayer ?? 0)).toBe(true);
    expect((y?.indexInLayer ?? 0) < (z?.indexInLayer ?? 0)).toBe(true);
  });

  it("handles an empty node list without throwing", () => {
    const layout = computeDeterministicLayout([], []);
    expect(layout.positions.size).toBe(0);
  });

  it("terminates even if a defensive cycle exists in the causal edges", () => {
    const cyclicEdges = [
      { source: "a", target: "b", edge_type: "causal" as const },
      { source: "b", target: "a", edge_type: "causal" as const },
    ];
    expect(() => computeDeterministicLayout([{ id: "a" }, { id: "b" }], cyclicEdges)).not.toThrow();
  });

  it("ignores non-causal edges for layering purposes", () => {
    const layout = computeDeterministicLayout(
      [{ id: "a" }, { id: "b" }],
      [{ source: "a", target: "b", edge_type: "supportive" as const }]
    );
    expect(layout.positions.get("a")?.layer).toBe(0);
    expect(layout.positions.get("b")?.layer).toBe(0);
  });
});
