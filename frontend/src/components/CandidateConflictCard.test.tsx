import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ConflictAdmissibility, ConflictCandidateEvaluation } from "../api/types";
import { CandidateConflictCard } from "./CandidateConflictCard";

// QA Closure v0.1.2 Item 3 (Candidate Conflict vs Main Conflict Strict
// Separation). This component has no `isMain`/main-conflict concept at
// all -- these tests confirm that structurally, not just by convention:
// no combination of input fields can make it render "Main conflict".

function makeAdmissibility(overrides: Partial<ConflictAdmissibility> = {}): ConflictAdmissibility {
  return {
    admissibility_version: "conflict_evidence_admissibility.v1",
    status: "candidate",
    reason_codes: ["INSUFFICIENT_BULL_SUPPORTING_EVIDENCE"],
    bull_score: 65.0,
    bear_score: 60.0,
    bull_supporting_evidence_count: 1,
    bear_supporting_evidence_count: 2,
    bull_ticker_specific_support_count: 0,
    bear_ticker_specific_support_count: 2,
    bull_supporting_fact_group_ids: ["g1"],
    bear_supporting_fact_group_ids: ["g2", "g3"],
    ...overrides,
  };
}

function makeEvaluation(overrides: Partial<ConflictCandidateEvaluation> = {}): ConflictCandidateEvaluation {
  return {
    alpha_a: "A101",
    alpha_b: "A304",
    outcome: "suppressed",
    reason_codes: [],
    evidence_audit: {
      alpha_a: { alpha_id: "A101", qualifying_claim_ids: ["c1"], qualifying_count: 1, excluded: [] },
      alpha_b: { alpha_id: "A304", qualifying_claim_ids: ["c2", "c3"], qualifying_count: 2, excluded: [] },
    },
    bull_alpha_id: "A101",
    bear_alpha_id: "A304",
    admissibility: makeAdmissibility(),
    ...overrides,
  };
}

describe("CandidateConflictCard", () => {
  it("shows the Potential conflict badge once B2 has been evaluated, and never Main conflict", () => {
    render(<CandidateConflictCard evaluation={makeEvaluation()} />);
    expect(screen.getByText("Potential conflict")).toBeInTheDocument();
    expect(screen.queryByText(/main conflict/i)).not.toBeInTheDocument();
  });

  it("uses plain product language, not B2 pipeline-stage vocabulary, in the default copy", () => {
    render(<CandidateConflictCard evaluation={makeEvaluation()} />);
    expect(
      screen.getByText("Evidence is not yet strong enough for inclusion as the main structural conflict.")
    ).toBeInTheDocument();
    expect(screen.getByText(/\bB2\b/)).not.toBeVisible();
  });

  it("shows 'Not evaluated' (never 'Potential conflict') for a pair rejected before B2", () => {
    render(
      <CandidateConflictCard
        evaluation={makeEvaluation({
          outcome: "rejected",
          reason_codes: ["MISSING_LEFT_EVIDENCE"],
          admissibility: undefined,
          bull_alpha_id: undefined,
          bear_alpha_id: undefined,
        })}
      />
    );
    expect(screen.getByText("Not evaluated")).toBeInTheDocument();
    expect(screen.queryByText("Potential conflict")).not.toBeInTheDocument();
    expect(
      screen.getByText("This declared pair did not have enough evidence to be evaluated as a potential conflict.")
    ).toBeInTheDocument();
    expect(screen.queryByText(/main conflict/i)).not.toBeInTheDocument();
    // The raw rejection reason code is preserved, just relocated under Technical details.
    expect(screen.getByText("MISSING_LEFT_EVIDENCE")).not.toBeVisible();
  });

  // Fail-closed coverage for task section 5, Case A (status=candidate,
  // is_main=true): this component has no isMain prop and no "Main
  // conflict" string anywhere in its source, so even a malformed
  // evaluation object that claims outcome="admitted" (a shape this
  // component should never actually receive -- ConflictRadarPage filters
  // outcome !== "admitted" before rendering it) still cannot produce a
  // Main Conflict badge. The mislabeling risk, if any, is strictly
  // under-claiming ("Potential conflict" for a genuinely-admitted pair),
  // never over-claiming main-conflict status.
  it("never renders Main conflict even for a malformed evaluation claiming outcome=admitted", () => {
    render(
      <CandidateConflictCard
        evaluation={makeEvaluation({
          outcome: "admitted",
          admissibility: makeAdmissibility({ status: "admitted", reason_codes: [] }),
        })}
      />
    );
    expect(screen.queryByText(/main conflict/i)).not.toBeInTheDocument();
    expect(screen.getByText("Potential conflict")).toBeInTheDocument();
  });

  it("keeps candidate evidence UI visible when the backend provides it", () => {
    render(
      <CandidateConflictCard
        evaluation={makeEvaluation({
          evidence_ui: {
            schema_version: "conflict_evidence_ui.v1",
            bull_evidence: [],
            bear_evidence: [],
            counter_evidence: [],
            missing_evidence: [],
            qualification_gaps: [],
            invalidation_conditions: {
              bull_alpha: { alpha_id: "A101", alpha_name: null, approval_status: "not_defined", source: null, version: null, conditions: [] },
              bear_alpha: { alpha_id: "A304", alpha_name: null, approval_status: "not_defined", source: null, version: null, conditions: [] },
            },
          },
        })}
      />
    );
    expect(screen.getByText("No evidence gaps identified.")).toBeInTheDocument();
  });

  it("hides the B2 admissibility diagnostic (scores, evidence counts, reason codes) behind Technical details by default", () => {
    render(<CandidateConflictCard evaluation={makeEvaluation()} />);
    expect(screen.getByText("65.0")).not.toBeVisible();
    expect(screen.getByText("60.0")).not.toBeVisible();
    expect(screen.getByText("INSUFFICIENT_BULL_SUPPORTING_EVIDENCE")).not.toBeVisible();
  });

  it("still exposes the exact raw admissibility diagnostic once Technical details is opened", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    render(<CandidateConflictCard evaluation={makeEvaluation()} />);
    await user.click(screen.getByText("Technical details"));
    expect(screen.getByText("65.0")).toBeVisible();
    expect(screen.getByText("60.0")).toBeVisible();
    expect(screen.getByText("INSUFFICIENT_BULL_SUPPORTING_EVIDENCE")).toBeVisible();
  });
});
