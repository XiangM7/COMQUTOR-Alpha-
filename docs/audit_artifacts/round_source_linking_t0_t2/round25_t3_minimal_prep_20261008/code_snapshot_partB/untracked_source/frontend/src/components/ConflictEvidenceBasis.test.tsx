import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { adaptEvidenceTraceItemResponse } from "../api/evidenceTrace";
import type { ConflictEvidenceUI, ConflictEvidenceUIItem } from "../api/types";
import legacyClaim90 from "../api/__fixtures__/evidence_trace_conflict_legacy_claim_90.json";
import positiveFixtureClaim31 from "../api/__fixtures__/evidence_trace_conflict_positive_FIXTURE_claim_31.json";
import { ConflictEvidenceSections } from "./ConflictEvidenceSections";

// T1 closeout (Round 22) -- the Conflict page offers the same "View basis" the Structure and Research pages have.
//
// Two data sets, never mixed up:
//  * LEGACY: a REAL claim of the HISTORICAL admitted conflict A301__A304 of run d5b60b8a-... (trimmed, as the production trace
//    route serves it). The run predates source linking: today's basis is "not linked / not verified", shown NEXT TO the saved
//    historical use (admitted / low / 14.26) -- never as "the judgment was wrong" or "there was no basis at the time".
//  * POSITIVE FIXTURE: the real claim 31 under a HAND-WRITTEN conflict. Explicitly a FIXTURE: no verified real admitted
//    conflict exists in any run, so this only proves a verified basis is shown beside the historical use.

const LEGACY_RUN = "d5b60b8a-66b8-44c1-9f55-ee345e58c48d";
const LEGACY_CLAIM = `${LEGACY_RUN}:news_agent:news_report:claim:90`;
const FIXTURE_RUN = "positive-fixture-run";
const FIXTURE_CLAIM = "c904d4cc-dc09-495c-aec5-b056979948e1:fundamental_agent:fundamentals_report:claim:31";

function trace(payload: unknown) {
  const adapted = adaptEvidenceTraceItemResponse(payload);
  if (!adapted.ok) throw new Error(adapted.reason);
  return adapted.value;
}

function evidenceItem(claimId: string, overrides: Partial<ConflictEvidenceUIItem> = {}): ConflictEvidenceUIItem {
  return {
    evidence_fact_group_id: `fact-${claimId.slice(-6)}`,
    representative_claim_id: claimId,
    member_claim_ids: [claimId],
    evidence_text: "Evidence text as the agent wrote it.",
    agents: ["news_agent"],
    source_agent_output_ids: [],
    target_alpha_id: "A304",
    evidence_stance: "opposes_alpha",
    stance_method: null,
    evidence_stance_version: "evidence_stance.deterministic.v1",
    stance_confidence_band: "high",
    ticker_specific: true,
    representative_match_score: 0.5,
    ...overrides,
  };
}

function evidenceUi(bull: ConflictEvidenceUIItem[], bear: ConflictEvidenceUIItem[], counter: ConflictEvidenceUIItem[] = []): ConflictEvidenceUI {
  return {
    schema_version: "conflict_evidence_ui.v1",
    bull_evidence: bull,
    bear_evidence: bear,
    counter_evidence: counter,
    missing_evidence: [],
    qualification_gaps: [],
    invalidation_conditions: {
      bull_alpha: { alpha_id: "A301", alpha_name: null, approval_status: "not_defined", source: null, version: null, conditions: [] },
      bear_alpha: { alpha_id: "A304", alpha_name: null, approval_status: "not_defined", source: null, version: null, conditions: [] },
    },
  } as ConflictEvidenceUI;
}

describe("Conflict evidence: View basis", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers no basis control without a run id and fetches nothing (renders as before)", () => {
    const spy = vi.spyOn(client, "getEvidenceTrace");
    render(<ConflictEvidenceSections evidenceUi={evidenceUi([evidenceItem("c1")], [evidenceItem("c2")])} bullAlphaId="A301" bearAlphaId="A304" />);
    expect(screen.queryByRole("button", { name: /view basis/i })).not.toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("offers View basis on every evidence item of every side (bull, bear and both counter groups), fetching only on click", async () => {
    const spy = vi.spyOn(client, "getEvidenceTrace").mockResolvedValue(trace(legacyClaim90));
    const ui = evidenceUi(
      [evidenceItem("bull-claim", { target_alpha_id: "A301" })],
      [evidenceItem("bear-claim")],
      [evidenceItem("counter-vs-bull", { counter_target_alpha_id: "A301" }), evidenceItem("counter-vs-bear", { counter_target_alpha_id: "A304" })],
    );
    const user = userEvent.setup();
    render(<ConflictEvidenceSections evidenceUi={ui} bullAlphaId="A301" bearAlphaId="A304" runId="some-run" />);
    const buttons = screen.getAllByRole("button", { name: /view basis/i });
    expect(buttons).toHaveLength(4);
    expect(spy).not.toHaveBeenCalled();
    await user.click(buttons[1] as HTMLElement);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith("some-run", "bear-claim", expect.anything());
  });

  it("LEGACY (real historical claim): shows the saved historical use unchanged next to a neutral 'not linked' current basis", async () => {
    vi.spyOn(client, "getEvidenceTrace").mockResolvedValue(trace(legacyClaim90));
    const user = userEvent.setup();
    render(
      <ConflictEvidenceSections evidenceUi={evidenceUi([], [evidenceItem(LEGACY_CLAIM)])} bullAlphaId="A301" bearAlphaId="A304" runId={LEGACY_RUN} />,
    );
    await user.click(screen.getByRole("button", { name: /view basis/i }));

    // 1. the historical use, exactly as the run saved it (this claim sits on two sides of the same saved conflict)
    const historical = (await screen.findByRole("heading", { name: "Historical use in this run (as saved)" })).closest("section") as HTMLElement;
    expect(within(historical).getByText(/Used as bear evidence of conflict A301__A304 — admitted, level low, score 14\.26\./)).toBeInTheDocument();
    expect(within(historical).getByText(/Used as counter-evidence of conflict A301__A304 — admitted, level low, score 14\.26\./)).toBeInTheDocument();
    expect(within(historical).getByText(/unchanged by anything shown in the current basis/)).toBeInTheDocument();

    // 2. the current basis: not linked / not verified, with the neutral reason
    expect(screen.getByRole("heading", { name: "Current basis" })).toBeInTheDocument();
    expect(screen.getByText("NOT_LINKED")).toBeInTheDocument();
    const legacyNote = screen.getAllByText(/This run was saved before source linking existed/);
    expect(legacyNote.length).toBeGreaterThan(0);
    expect(screen.getByText("No source linked; not verified")).toBeInTheDocument();
    expect(screen.getByText("No source is linked to this claim.")).toBeInTheDocument();
    // which of the four blocks are saved results and which are read against today's fields
    expect(screen.getByText(/results this run itself saved; only source support is read against today's source-link fields/)).toBeInTheDocument();
  });

  it("LEGACY: never calls the historical judgment wrong, baseless or invalid", async () => {
    vi.spyOn(client, "getEvidenceTrace").mockResolvedValue(trace(legacyClaim90));
    const user = userEvent.setup();
    const { container } = render(
      <ConflictEvidenceSections evidenceUi={evidenceUi([], [evidenceItem(LEGACY_CLAIM)])} bullAlphaId="A301" bearAlphaId="A304" runId={LEGACY_RUN} />,
    );
    await user.click(screen.getByRole("button", { name: /view basis/i }));
    await screen.findByRole("heading", { name: "Historical use in this run (as saved)" });
    // the one passage that NEGATES those words is the legacy note itself (shown as the note and as the status reason);
    // everything else the panel says must not contain them
    const note = trace(legacyClaim90).item.run_basis.note ?? "";
    expect(note).toContain("not a finding that the claim was wrong");
    const text = (container.querySelector(".evidence-trace")?.textContent ?? "").split(note).join("");
    expect(text).not.toMatch(/\b(wrong|incorrect|erroneous|invalid|fabricat\w*|baseless|without basis|no basis)\b/i);
    expect(text).not.toMatch(/judgments? (was|were|are|is) /i);
  });

  it("POSITIVE FIXTURE: a verified basis is shown next to the historical use, each under its own heading", async () => {
    vi.spyOn(client, "getEvidenceTrace").mockResolvedValue(trace(positiveFixtureClaim31));
    const user = userEvent.setup();
    render(
      <ConflictEvidenceSections
        evidenceUi={evidenceUi([evidenceItem(FIXTURE_CLAIM, { target_alpha_id: "A301" })], [])}
        bullAlphaId="A301"
        bearAlphaId="A304"
        runId={FIXTURE_RUN}
      />,
    );
    await user.click(screen.getByRole("button", { name: /view basis/i }));
    expect(await screen.findByText(/Used as bull evidence of conflict FIXTURE_A301__FIXTURE_BEAR — admitted, level medium, score 33\.30\./)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Current basis" })).toBeInTheDocument();
    expect(screen.getByText("Verified: the saved source content supports this claim")).toBeInTheDocument();
    expect(screen.getByText("excerpt and data_snapshot.periods for Total Revenue")).toBeInTheDocument();
    expect(screen.queryByText(/This run was saved before source linking existed/)).not.toBeInTheDocument(); // not a legacy run
  });

  it("shows a failed trace as a failure inside the conflict page, not as an empty basis", async () => {
    vi.spyOn(client, "getEvidenceTrace").mockResolvedValue({ run_id: "r", ticker: "AMD", status: "failed", error_code: "CLAIM_NOT_FOUND" });
    const user = userEvent.setup();
    render(<ConflictEvidenceSections evidenceUi={evidenceUi([evidenceItem("missing")], [])} bullAlphaId="A301" bearAlphaId="A304" runId="r" />);
    await user.click(screen.getByRole("button", { name: /view basis/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("CLAIM_NOT_FOUND");
  });
});
