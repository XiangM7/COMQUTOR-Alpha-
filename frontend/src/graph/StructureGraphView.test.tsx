import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StructureGraphView } from "./StructureGraphView";
import type { SelectableGraphNode } from "./graphTypes";

function baseNode(overrides: Partial<SelectableGraphNode>): SelectableGraphNode {
  return {
    id: "n1",
    node_type: "factor",
    label: "Demand growth",
    canonical_factor: "demand_growth",
    original_labels: ["Demand growth"],
    alpha_ids: [],
    ambiguous_alpha_ids: [],
    score: 0.5,
    claim_ids: [],
    source_agent_output_ids: [],
    agents: [],
    evidence: [],
    isDominant: false,
    isConflictRelated: false,
    ...overrides,
  };
}

describe("StructureGraphView", () => {
  it("renders an empty-graph message when there are no nodes", () => {
    render(<StructureGraphView nodes={[]} edges={[]} selectedNodeId={null} onSelectNode={vi.fn()} />);
    expect(screen.getByText(/no nodes/i)).toBeInTheDocument();
  });

  it("visually distinguishes a dominant alpha node", () => {
    const nodes = [baseNode({ id: "n1", isDominant: true, alpha_ids: ["A101"] })];
    render(<StructureGraphView nodes={nodes} edges={[]} selectedNodeId={null} onSelectNode={vi.fn()} />);
    const node = screen.getByRole("button", { name: /dominant alpha/i });
    expect(node).toHaveClass("graph-node-star");
  });

  it("supports keyboard selection (Enter) on a node", async () => {
    const user = userEvent.setup();
    const nodes = [baseNode({ id: "n1" })];
    const onSelectNode = vi.fn();
    render(<StructureGraphView nodes={nodes} edges={[]} selectedNodeId={null} onSelectNode={onSelectNode} />);

    const node = screen.getByRole("button", { name: /demand growth/i });
    node.focus();
    await user.keyboard("{Enter}");
    expect(onSelectNode).toHaveBeenCalledWith("n1");
  });

  it("supports keyboard selection (Space) on a node", async () => {
    const user = userEvent.setup();
    const nodes = [baseNode({ id: "n1" })];
    const onSelectNode = vi.fn();
    render(<StructureGraphView nodes={nodes} edges={[]} selectedNodeId={null} onSelectNode={onSelectNode} />);

    const node = screen.getByRole("button", { name: /demand growth/i });
    node.focus();
    await user.keyboard(" ");
    expect(onSelectNode).toHaveBeenCalledWith("n1");
  });

  it("only renders edges that reference real, backend-provided source/target node ids -- never a fabricated conflict edge", () => {
    const nodes = [baseNode({ id: "n1" }), baseNode({ id: "n2", label: "Supply constraint" })];
    const edges = [
      { source: "n1", target: "n2", edge_type: "conflicting" as const, weight: 0.8, assertion_status: "asserted", alpha_ids: [], claim_ids: [], source_agent_output_ids: [], agents: [], evidence: [], extraction_methods: [], rule_names: [] },
      // Dangling edge referencing a node that does not exist -- must be silently skipped, never invented.
      { source: "n1", target: "ghost", edge_type: "conflicting" as const, weight: 0.5, assertion_status: "asserted", alpha_ids: [], claim_ids: [], source_agent_output_ids: [], agents: [], evidence: [], extraction_methods: [], rule_names: [] },
    ];
    const { container } = render(
      <StructureGraphView nodes={nodes} edges={edges} selectedNodeId={null} onSelectNode={vi.fn()} />
    );
    const lines = container.querySelectorAll("line");
    expect(lines.length).toBe(1); // only the valid edge rendered
  });
});
