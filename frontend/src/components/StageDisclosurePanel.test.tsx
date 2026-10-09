import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StageDisclosurePanel } from "./StageDisclosurePanel";

describe("StageDisclosurePanel", () => {
  it("lists degraded sub-steps and keeps graph construction separate from model structure extraction", () => {
    render(
      <StageDisclosurePanel
        disclosure={{
          schema_version: "comqutor.stage_disclosure.v1",
          degraded_stages: ["claim_enrichment", "structure_extraction"],
          notes: ["Claim enrichment: 9 of 9 batches did not use a model result (7 timed out)."],
          stages: [
            { stage: "claim_enrichment", task: "structured_adapter", status: "model_not_used", calls: 9 },
            { stage: "structure_extraction", task: "structure_extractor", status: "model_not_used", calls: 2 },
            { stage: "structure_graph", task: null, status: "built" },
          ],
        }}
      />,
    );
    expect(screen.getByText("Processing completeness")).toBeInTheDocument();
    expect(screen.getByText(/9 of 9 batches did not use a model result/)).toBeInTheDocument();
    expect(screen.getAllByText("no model result used (deterministic fallback)")).toHaveLength(2);
    expect(screen.getByText("Structure Graph construction")).toBeInTheDocument();
    expect(screen.getByText("built")).toBeInTheDocument();
  });

  it("renders nothing for a backend that sends no disclosure", () => {
    const { container } = render(<StageDisclosurePanel disclosure={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
