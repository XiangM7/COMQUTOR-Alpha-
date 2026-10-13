import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { adaptEvidenceTraceItemResponse } from "../api/evidenceTrace";
import judged from "../api/__fixtures__/evidence_trace_relevance_judged.json";
import unresolved from "../api/__fixtures__/evidence_trace_relevance_unresolved.json";
import failed from "../api/__fixtures__/evidence_trace_relevance_failed.json";
import unjudged from "../api/__fixtures__/evidence_trace_relevance_unjudged.json";
import judgedV2 from "../api/__fixtures__/evidence_trace_relevance_judged_v2.json";
import judgedV3 from "../api/__fixtures__/evidence_trace_relevance_judged_v3.json";
import legacyClaim from "../api/__fixtures__/evidence_trace_claim_31.json";
import { EvidenceTraceView } from "./EvidenceTraceDetail";

/** P4 phase 1 -- the relevance section shows exactly what the API verified (real backend fixtures, simulated test data). */

type Raw = {
  item: {
    relevance_judgment: {
      label: string;
      tier: string | null;
      reason: string | null;
      basis: string | null;
      unresolved_reason: string | null;
      anchors: { element_id: string; label: string; occurrences: { list: string; phrase: string }[] }[];
      source: { owner_run_id: string; call_id: string | null };
    };
  };
};

function section(payload: unknown) {
  const adapted = adaptEvidenceTraceItemResponse(payload);
  if (!adapted.ok) throw new Error(adapted.reason);
  render(<EvidenceTraceView item={adapted.value.item} />);
  return screen.getByTestId("evidence-trace-relevance");
}

const rj = (payload: unknown) => (payload as Raw).item.relevance_judgment;

describe("EvidenceTraceView: relevance section", () => {
  it("shows a judged tier with its definition anchors, basis, owner run and the TEST DATA mark", () => {
    const node = section(judged);
    const r = rj(judged);
    expect(within(node).getByTestId("evidence-trace-relevance-tier").textContent).toBe(r.tier);
    expect(within(node).getByTestId("evidence-trace-relevance-test-data").textContent).toBe("TEST DATA");
    expect(within(node).getByText(r.label)).toBeInTheDocument();
    const anchor = r.anchors[0];
    const phrase = anchor?.occurrences[0]?.phrase;
    if (!anchor || !phrase) throw new Error("the judged fixture must carry an anchor with an occurrence");
    expect(node.textContent).toContain(anchor.element_id);
    expect(node.textContent).toContain(phrase);
    expect(within(node).getByText(r.basis as string)).toBeInTheDocument();
    expect(node.textContent).toContain(r.source.owner_run_id);
    expect(node.textContent).toContain("Weight");
  });

  it("shows an unresolved pair with its reason and no tier", () => {
    const node = section(unresolved);
    expect(within(node).queryByTestId("evidence-trace-relevance-tier")).toBeNull();
    expect(within(node).getByText(rj(unresolved).unresolved_reason as string)).toBeInTheDocument();
  });

  it("alerts on a failed pair, names the failure reason and shows no tier", () => {
    const node = section(failed);
    expect(within(node).queryByTestId("evidence-trace-relevance-tier")).toBeNull();
    expect(within(node).getByRole("alert").textContent).toBe(rj(failed).label);
    expect(within(node).getByText(rj(failed).reason as string)).toBeInTheDocument();
  });

  it("shows an unjudged pair as UNJUDGED with the reason -- no tier, no test-data mark, no source", () => {
    const node = section(unjudged);
    expect(within(node).getByText("UNJUDGED")).toBeInTheDocument();
    expect(within(node).getByText(rj(unjudged).reason as string)).toBeInTheDocument();
    expect(within(node).queryByTestId("evidence-trace-relevance-tier")).toBeNull();
    expect(within(node).queryByTestId("evidence-trace-relevance-test-data")).toBeNull();
    expect(within(node).queryByText("Source")).toBeNull();
  });

  it("shows the claim words a prompt-v2 judgment quoted, and the versions of its own record", () => {
    const node = section(judgedV2);
    const r = judgedV2.item.relevance_judgment;
    const quote = r.anchors[0]?.evidence_quotes[0];
    if (!quote) throw new Error("the v2 fixture must carry a quoted anchor");
    expect(within(node).getByTestId("evidence-trace-relevance-quote").textContent).toContain(`“${quote}”`);
    expect(node.textContent).toContain(r.source.prompt_version);
    expect(node.textContent).toContain(r.source.criterion_version);
  });

  it("shows each quote with its statement mode, where the tier came from, and the statements considered", () => {
    const node = section(judgedV3);
    const r = judgedV3.item.relevance_judgment;
    const quote = r.anchors[0]?.evidence_quotes[0];
    const mode = r.anchors[0]?.evidence_modes[0];
    if (!quote || !mode) throw new Error("the v3 fixture must carry a quoted anchor with a mode");
    expect(within(node).getByTestId("evidence-trace-relevance-quote").textContent).toContain(`“${quote}” (${mode})`);
    expect(within(node).getByTestId("evidence-trace-relevance-tier-source").textContent).toContain("derived by the program");
    const statements = within(node).getByTestId("evidence-trace-relevance-statements");
    expect(statements.textContent).toContain(`${r.statements.length} statement(s) considered`);
    expect(statements.textContent).toContain(r.statements[0]?.quote ?? "");
  });

  it("shows no tier source and no statements for a prompt-v2 judgment", () => {
    const node = section(judgedV2);
    expect(within(node).queryByTestId("evidence-trace-relevance-tier-source")).toBeNull();
    expect(within(node).queryByTestId("evidence-trace-relevance-statements")).toBeNull();
  });

  it("shows no quote line for a prompt-v1 judgment", () => {
    const node = section(judged);
    expect(within(node).queryByTestId("evidence-trace-relevance-quote")).toBeNull();
    expect(node.textContent).toContain("alpha_relevance.judge.prompt.v1");
  });

  it("shows no relevance section for a payload without one", () => {
    const adapted = adaptEvidenceTraceItemResponse(legacyClaim);
    if (!adapted.ok) throw new Error(adapted.reason);
    render(<EvidenceTraceView item={adapted.value.item} />);
    expect(screen.queryByTestId("evidence-trace-relevance")).toBeNull();
  });
});
