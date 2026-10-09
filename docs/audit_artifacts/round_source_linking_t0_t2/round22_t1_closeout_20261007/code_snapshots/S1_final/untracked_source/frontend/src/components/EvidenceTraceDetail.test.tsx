import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { adaptEvidenceTraceItemResponse, adaptKeyConclusionsResponse } from "../api/evidenceTrace";
import type { AlphaEvidenceDetail } from "../api/types";
import claim31 from "../api/__fixtures__/evidence_trace_claim_31.json";
import claim10 from "../api/__fixtures__/evidence_trace_claim_10_a304.json";
import keyConclusions from "../api/__fixtures__/evidence_key_conclusions.json";
import { AlphaCard } from "./AlphaCard";
import { EvidenceTraceView } from "./EvidenceTraceDetail";
import { KeyConclusionsPanel } from "./KeyConclusionsPanel";

function item(payload: unknown) {
  const adapted = adaptEvidenceTraceItemResponse(payload);
  if (!adapted.ok) throw new Error(adapted.reason);
  return adapted.value;
}

const CLAIM_31 = "c904d4cc-dc09-495c-aec5-b056979948e1:fundamental_agent:fundamentals_report:claim:31";

describe("EvidenceTraceView", () => {
  it("shows the actual material, where the claim sits in it, and the verification status -- not an internal id", () => {
    render(<EvidenceTraceView item={item(claim31).item} />);
    expect(screen.getByText("Verified: the saved source content supports this claim")).toBeInTheDocument();
    // the material: the saved row, with the cells the claim's numbers sit in
    const table = screen.getByRole("table");
    expect(within(table).getByText("Total Revenue")).toBeInTheDocument();
    expect(within(table).getAllByText("$11,536M").length).toBeGreaterThan(0);
    expect(within(table).getByText("2026-06-30")).toBeInTheDocument();
    // the location, the verifier's quoted material and the verification method
    expect(screen.getByText("excerpt and data_snapshot.periods for Total Revenue")).toBeInTheDocument();
    expect(screen.getByText(/2026-06-30=11536000000\.0/)).toBeInTheDocument();
    expect(screen.getByText(/LLM_CONTENT_SUPPORT_VERIFIED/)).toBeInTheDocument();
    expect(screen.getByText(/src_582ac24bf4319648:frag:0/)).toBeInTheDocument();
    // the report location of the claim, numbered like the claim everywhere else ("claim 31"), not by a 0-based index
    expect(screen.getByText(/Revenue acceleration is dramatic/)).toBeInTheDocument();
    expect(screen.getByText(/· claim 31$/)).toBeInTheDocument();
  });

  it("shows the four checks separately and never calls a rule-based stance or weight a model judgment", () => {
    render(<EvidenceTraceView item={item(claim31).item} />);
    for (const heading of ["1 · Source support", "2 · Alpha match", "3 · Stance", "4 · Official scoring"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByText(/no model judgment obtained/i)).toBeInTheDocument();
    expect(screen.getByText(/NOT a model judgment that the claim is irrelevant/)).toBeInTheDocument();
  });

  it("says whether the indicator inputs were saved and recomputed, or not saved (nothing backfilled)", () => {
    const base = item(claim31).item;
    const saved = { ...base, sources: base.sources.map((s) => ({ ...s, derived_inputs: {
      status: "SAVED", method: "stockstats", version: "stockstats==0.6.8", row_count: 1255, first_date: "2021-10-06", last_date: "2026-10-06",
      series_hash_ok: true, registry_pointer_matches: true, recomputation_status: "REPRODUCED", recomputation_indicators_checked: 11, recomputation_mismatched: [], note: null } })) };
    const { unmount } = render(<EvidenceTraceView item={saved} />);
    expect(screen.getByText(/Indicator inputs: 1255 rows saved \(2021-10-06 → 2026-10-06\) · stockstats==0\.6\.8 · recomputed from the saved inputs alone: REPRODUCED \(11 indicators\)/)).toBeInTheDocument();
    unmount();
    const notSaved = { ...base, sources: base.sources.map((s) => ({ ...s, derived_inputs: {
      status: "NOT_SAVED", method: "stockstats", version: "stockstats==0.6.8", row_count: 1255, first_date: "2021-10-06", last_date: "2026-10-06",
      series_hash_ok: null, registry_pointer_matches: null, recomputation_status: null, recomputation_indicators_checked: null, recomputation_mismatched: [], note: null } })) };
    render(<EvidenceTraceView item={notSaved} />);
    expect(screen.getByText(/Indicator inputs: not saved in this run \(stockstats, stockstats==0\.6\.8; window parameters only: 1255 rows \(2021-10-06 → 2026-10-06\)\)\. Nothing is backfilled\./)).toBeInTheDocument();
  });

  it("lists the numbers a claim states that no saved cell holds, without calling that a verdict", () => {
    render(<EvidenceTraceView item={item(claim10).item} />);
    expect(screen.getByRole("heading", { name: "Numbers not found in the saved data" })).toBeInTheDocument();
    expect(screen.getByText("$1.38")).toBeInTheDocument();
    expect(screen.getByText(/this is not a verdict on the claim/)).toBeInTheDocument();
  });

  it("lists percentages the system could not reproduce, saying that is not the same as wrong", () => {
    render(<EvidenceTraceView item={{ ...item(claim31).item, unreproduced_percent_tokens: ["+12.5%", "48.7%"] }} />);
    expect(screen.getByRole("heading", { name: "Percentages not reproduced from the saved rows" })).toBeInTheDocument();
    expect(screen.getByText("+12.5%")).toBeInTheDocument();
    expect(screen.getByText("48.7%")).toBeInTheDocument();
    expect(screen.getByText(/is not thereby wrong/)).toBeInTheDocument();
  });

  it("shows no such section when every number of the claim was found in the saved data", () => {
    render(<EvidenceTraceView item={item(claim31).item} />);
    expect(screen.queryByRole("heading", { name: "Numbers not found in the saved data" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Percentages not reproduced from the saved rows" })).toBeNull();
  });

  it("states an unresolved relation as unresolved, with its reason, next to a verified source", () => {
    render(<EvidenceTraceView item={item(claim10).item} />);
    expect(screen.getByText("Verified: the saved source content supports this claim")).toBeInTheDocument();
    expect(screen.getByText("Relation to the Alpha is not established")).toBeInTheDocument();
    expect(screen.getByText(/No model stance judgment was obtained/)).toBeInTheDocument();
    expect(screen.getByText("RELATION_NOT_SUPPORTING")).toBeInTheDocument();
  });
});

const EVIDENCE: AlphaEvidenceDetail[] = [
  {
    claim_id: CLAIM_31,
    claim: "Revenue grew from $7,685M (Q2'25) → $11,536M (Q2'26).",
    agent: "fundamental_agent",
    source_agent_output_id: "run:fundamental_agent:fundamentals_report",
    match_score: 0.1873,
    relation: "activation",
    matched_keywords: ["revenue"],
    matched_factors: [],
    assertion_status: "asserted",
    direction: "unknown",
  },
];

describe("AlphaCard evidence basis", () => {
  afterEach(() => vi.restoreAllMocks());

  const props = { alphaId: "A301", alphaName: "Revenue Acceleration", activationScore: 21.3, status: "candidate", evidenceDetail: EVIDENCE };

  it("offers no basis control when the card does not know its run (renders as before)", () => {
    render(<AlphaCard {...props} />);
    screen.getByText(/Evidence \(1\)/).click();
    expect(screen.queryByRole("button", { name: /view basis/i })).not.toBeInTheDocument();
  });

  it("fetches nothing until opened, then shows the claim's material, location and verification", async () => {
    const spy = vi.spyOn(client, "getEvidenceTrace").mockResolvedValue(item(claim31));
    const user = userEvent.setup();
    render(<AlphaCard {...props} runId="requal-run" />);
    await user.click(screen.getByText(/Evidence \(1\)/));
    expect(spy).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /view basis/i }));
    expect(spy).toHaveBeenCalledWith("requal-run", CLAIM_31, expect.anything());
    expect(await screen.findByText("excerpt and data_snapshot.periods for Total Revenue")).toBeInTheDocument();
    expect(screen.getByText("Verified: the saved source content supports this claim")).toBeInTheDocument();
  });

  it("shows a failed trace as a failure, not as an empty basis", async () => {
    vi.spyOn(client, "getEvidenceTrace").mockResolvedValue({ run_id: "requal-run", ticker: "AMD", status: "failed", error_code: "CLAIM_NOT_FOUND" });
    const user = userEvent.setup();
    render(<AlphaCard {...props} runId="requal-run" />);
    await user.click(screen.getByText(/Evidence \(1\)/));
    await user.click(screen.getByRole("button", { name: /view basis/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("CLAIM_NOT_FOUND");
  });
});

describe("KeyConclusionsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  function adaptedKey() {
    const adapted = adaptKeyConclusionsResponse(keyConclusions);
    if (!adapted.ok) throw new Error(adapted.reason);
    return adapted.value;
  }

  it("lists the final-decision claims with four separate statuses and flags the Agent's own 'verified' wording", async () => {
    vi.spyOn(client, "getKeyConclusions").mockResolvedValue(adaptedKey());
    const user = userEvent.setup();
    render(<KeyConclusionsPanel runId="requal-run" />);
    expect(await screen.findByRole("heading", { name: /key conclusions/i })).toBeInTheDocument();
    const group = await screen.findByText(/portfolio_manager \/ Synthesis of the Risk Debate/);
    await user.click(group);
    for (const column of ["Source support", "Alpha match", "Stance", "Official scoring"]) {
      expect((await screen.findAllByRole("columnheader", { name: column })).length).toBeGreaterThan(0);
    }
    expect(screen.getAllByText("Agent wrote “verified”").length).toBeGreaterThan(0);
    expect(screen.getAllByText("NOT_LINKED").length).toBeGreaterThan(0);
    expect(screen.getAllByText("RELATION_UNRESOLVED").length).toBeGreaterThan(0);
  });

  it("opens one claim's full trace on request, and fetches nothing for the rows until then", async () => {
    vi.spyOn(client, "getKeyConclusions").mockResolvedValue(adaptedKey());
    const traceSpy = vi.spyOn(client, "getEvidenceTrace").mockResolvedValue(item(claim10));
    const user = userEvent.setup();
    render(<KeyConclusionsPanel runId="requal-run" />);
    await user.click(await screen.findByText(/portfolio_manager \/ Synthesis of the Risk Debate/));
    expect(traceSpy).not.toHaveBeenCalled();
    const buttons = await screen.findAllByRole("button", { name: /why these statuses/i });
    await user.click(buttons[0]!);
    expect(traceSpy).toHaveBeenCalledTimes(1);
  });

  it("renders nothing without a run id and reports a failed load honestly", async () => {
    const { container } = render(<KeyConclusionsPanel runId={undefined} />);
    expect(container).toBeEmptyDOMElement();
    vi.spyOn(client, "getKeyConclusions").mockResolvedValue({ run_id: "r", ticker: null, status: "failed", error_code: "RUN_NOT_FOUND" });
    render(<KeyConclusionsPanel runId="r" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("RUN_NOT_FOUND");
  });
});
