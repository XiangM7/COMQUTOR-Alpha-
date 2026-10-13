import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { adaptEvidenceTraceItemResponse } from "../api/evidenceTrace";
import admitted from "../api/__fixtures__/evidence_trace_consumption_admitted.json";
import excluded from "../api/__fixtures__/evidence_trace_consumption_excluded.json";
import negationGoverns from "../api/__fixtures__/evidence_trace_consumption_negation_governs.json";
import negationReread from "../api/__fixtures__/evidence_trace_consumption_negation_reread.json";
import negationUnanchored from "../api/__fixtures__/evidence_trace_consumption_negation_unanchored.json";
import unjudged from "../api/__fixtures__/evidence_trace_consumption_unjudged.json";
import legacyClaim from "../api/__fixtures__/evidence_trace_claim_31.json";
import { EvidenceTraceView } from "./EvidenceTraceDetail";

/** The display skeleton for alpha_evidence_consumption.v2: it states what the contract decided, with the shared reason code. */

interface PayloadCopy {
  item: {
    consumption: {
      state: string;
      verification_error: string | null;
      attribution: Record<string, unknown>;
      relevance: Record<string, unknown>;
    };
  };
}

function view(payload: unknown, mutate?: (copy: PayloadCopy) => void) {
  const copy = JSON.parse(JSON.stringify(payload));
  mutate?.(copy);
  const adapted = adaptEvidenceTraceItemResponse(copy);
  if (!adapted.ok) throw new Error(adapted.reason);
  return render(<EvidenceTraceView item={adapted.value.item} />);
}

describe("EvidenceTraceView: consumption section", () => {
  it("states the execution basis of an original run and that its own ledger corroborated the stance", () => {
    view(excluded);
    const basis = screen.getByTestId("evidence-trace-execution-basis");
    expect(within(basis).getByText("Original research run.")).toBeInTheDocument();
    expect(within(basis).getByText(/this run's own ledger/)).toBeInTheDocument();
    expect(within(basis).queryByText(/Saved run it recomputes/)).not.toBeInTheDocument();
  });

  it("labels a derived recomputation as NOT a Fresh Run and names the saved source run whose ledger is bound", () => {
    view(excluded, (copy) => {
      (copy.item.consumption as unknown as Record<string, unknown>).execution_basis = {
        execution_run_id: "consumption-20261011T120000Z-0a1b2c3d",
        execution_type: "alpha_evidence_consumption_recompute",
        based_on_run_id: "12591384-0b26-470d-a99d-a49c00be440b",
        root_research_run_id: null,
        recomputation_of_saved_inputs: true,
        label: "Recomputation of a saved run's inputs under the evidence contract -- not a Fresh Run. This execution made no model, search or data-fetch call; every stance is the source run's saved result (nothing was re-judged).",
        stance_ledger: { available: true, integrity: "MATCHES_MANIFEST", owner_run_id: "12591384-0b26-470d-a99d-a49c00be440b", binding: "SOURCE_RUN_DECLARED", sha256: "a".repeat(64) },
      };
    });
    const basis = screen.getByTestId("evidence-trace-execution-basis");
    expect(within(basis).getByText(/not a Fresh Run/)).toBeInTheDocument();
    expect(within(basis).getByText("consumption-20261011T120000Z-0a1b2c3d")).toBeInTheDocument();
    expect(within(basis).getByText("Saved run it recomputes")).toBeInTheDocument();
    expect(within(basis).getByText(/bound to the saved source run/)).toBeInTheDocument();
    expect(within(basis).getByText("MATCHES_MANIFEST")).toBeInTheDocument();
  });

  it("says plainly that nothing is excluded when there is no usable ledger", () => {
    view(unjudged, (copy) => {
      (copy.item.consumption as unknown as Record<string, unknown>).execution_basis = {
        execution_run_id: "consumption-20261011T120000Z-0a1b2c3d",
        execution_type: "alpha_evidence_consumption_recompute",
        based_on_run_id: "dependency-20261007T220450Z-33128621",
        root_research_run_id: "c904d4cc-dc09-495c-aec5-b056979948e1",
        recomputation_of_saved_inputs: true,
        label: "Recomputation of a saved run's inputs under the evidence contract -- not a Fresh Run.",
        stance_ledger: { available: false, integrity: null, owner_run_id: null, binding: null, sha256: null },
      };
    });
    const basis = screen.getByTestId("evidence-trace-execution-basis");
    expect(within(basis).getByText("NO LEDGER")).toBeInTheDocument();
    expect(within(basis).getByText(/Model stances cannot be corroborated, so the stance policy excludes nothing/)).toBeInTheDocument();
    expect(within(basis).getByText(/original research run/)).toBeInTheDocument();
  });

  it("says a corroborated model opposition keeps the claim out of that Alpha's positive pool, with the shared reason code", () => {
    view(excluded);
    const section = screen.getByTestId("evidence-trace-consumption");
    expect(within(section).getByRole("heading", { name: "How the evidence contract used this claim" })).toBeInTheDocument();
    expect(within(section).getByText("alpha_evidence_consumption.v2")).toBeInTheDocument();
    expect(within(section).getByText("CURRENT")).toBeInTheDocument();
    expect(within(section).getByText("STANCE_MODEL_NOT_SUPPORTING")).toBeInTheDocument();
    expect(within(section).getByText(/Only this Alpha's pool is affected/)).toBeInTheDocument();
    expect(within(section).getByText(/The model judged the stance toward A301 as opposes_alpha/)).toBeInTheDocument();
    // the scoring status block (4) names the same code
    expect(screen.getAllByText(/STANCE_MODEL_NOT_SUPPORTING/).length).toBeGreaterThan(1);
  });

  it("does not claim an exclusion for an admitted claim and labels the weight as the rule-based fallback", () => {
    view(admitted);
    const section = screen.getByTestId("evidence-trace-consumption");
    expect(within(section).queryByText("STANCE_MODEL_NOT_SUPPORTING")).not.toBeInTheDocument();
    expect(within(section).getByText(/No exclusion from A301's positive pool by the stance policy/)).toBeInTheDocument();
    expect(within(section).getByText(/rule-based lexical score, consumed unchanged \(no model relevance judgment exists\)/)).toBeInTheDocument();
    expect(within(section).getByText(/Model weight: none\./)).toBeInTheDocument();
    expect(within(section).getByText(/relation activation · assertion asserted · polarity activation/)).toBeInTheDocument();
  });

  it("shows a model weight only when the payload carries one", () => {
    view(admitted, (copy) => {
      copy.item.consumption.relevance.model_weight = 0.42;
      copy.item.consumption.relevance.weight_authority = "MODEL";
    });
    const section = screen.getByTestId("evidence-trace-consumption");
    expect(within(section).getByText(/Model weight: 0\.42\./)).toBeInTheDocument();
    expect(within(section).queryByText(/Model weight: none\./)).not.toBeInTheDocument();
  });

  it("discloses an unjudged stance as adding no exclusion", () => {
    view(unjudged);
    const section = screen.getByTestId("evidence-trace-consumption");
    expect(within(section).getByText("UNJUDGED")).toBeInTheDocument();
    expect(within(section).getByText(/this adds no exclusion, and the other gates still apply/)).toBeInTheDocument();
  });

  it("says a present company name is not the same as the claim being about the company", () => {
    view(admitted, (copy) => {
      copy.item.consumption.attribution = {
        ...copy.item.consumption.attribution,
        category: "TARGET_NAME_ISSUER",
        ticker_specific: true,
        basis: [{ kind: "issuer_name", term: "NVIDIA" }],
        limits: ["NAME_PRESENCE_NOT_SUBJECT"],
        explanation: "The target company's name is present in the claim text; this does not establish that the claim is ABOUT the target.",
      };
    });
    const section = screen.getByTestId("evidence-trace-consumption");
    expect(within(section).getByText("TARGET_NAME_ISSUER")).toBeInTheDocument();
    expect(within(section).getByText(/does not establish that the claim is ABOUT the target/)).toBeInTheDocument();
    expect(within(section).getByText(/may still be about another company or a general topic/)).toBeInTheDocument();
    expect(within(section).getByText("NAME_PRESENCE_NOT_SUBJECT")).toBeInTheDocument();
    expect(within(section).getByText(/Matched: NVIDIA \(issuer name\)/)).toBeInTheDocument();
  });

  it("warns when the saved decision is stale or invalid instead of presenting it as current", () => {
    const { unmount } = view(admitted, (copy) => {
      copy.item.consumption.state = "STALE";
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/differs from the decision saved with the run/);
    unmount();
    view(admitted, (copy) => {
      copy.item.consumption.state = "INVALID:EVIDENCE_CONSUMPTION_BINDING_STALE";
      copy.item.consumption.verification_error = "EVIDENCE_CONSUMPTION_BINDING_STALE";
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/failed validation \(EVIDENCE_CONSUMPTION_BINDING_STALE\); it is not used as a basis/);
  });

  it("shows nothing for a run that never declared the contract", () => {
    view(legacyClaim);
    expect(screen.queryByTestId("evidence-trace-consumption")).not.toBeInTheDocument();
    expect(screen.queryByText(/alpha_evidence_consumption/)).not.toBeInTheDocument();
  });
});

describe("EvidenceTraceView: negation scope (alpha_statement_scope.v2)", () => {
  it("says the negation does not govern, names the removed part, and shows the stance read on that basis", () => {
    view(negationReread);
    const row = screen.getByTestId("evidence-trace-consumption-statement-scope");
    expect(within(row).getByText("NEGATION DOES NOT GOVERN")).toBeInTheDocument();
    expect(row).toHaveTextContent(/the negation sits only in the rejected alternative of a contrast; it does not negate A304's statement/);
    expect(row).toHaveTextContent("Not read as part of the statement: “They're not —”.");
    expect(
      screen.getByText(/relation activation · assertion asserted · basis: text rule re-read for this Alpha \(alpha_statement_scope\.v2/)
    ).toBeInTheDocument();
  });

  it("says when the negation still governs, and the stance stays unresolved on the text rule's reading", () => {
    view(negationGoverns);
    const row = screen.getByTestId("evidence-trace-consumption-statement-scope");
    expect(within(row).getByText("NEGATION GOVERNS")).toBeInTheDocument();
    expect(row).toHaveTextContent(/the negation still governs A304's statement \(not\); the claim is read as negated/);
    expect(row).not.toHaveTextContent(/Not read as part of the statement/);
    expect(screen.getByText(/relation mention · assertion negated · basis: text rule \(claim_semantics\)/)).toBeInTheDocument();
  });

  it("says a contrast is left in place when no model judgment anchors which side carries the Alpha's statement", () => {
    view(negationUnanchored);
    const row = screen.getByTestId("evidence-trace-consumption-statement-scope");
    expect(within(row).getByText("NEGATION GOVERNS")).toBeInTheDocument();
    expect(row).toHaveTextContent(/the words alone cannot tell whether A304's statement is the kept or the rejected part/);
    expect(row).toHaveTextContent(/Not removed without the anchor: “, not a forward EPS of \$15\.72 against a current quarterly run-rate of \$1\.38”\./);
    expect(row).toHaveTextContent(/Not read as part of the statement: “\[fragmentid: src7e133fa786f7aaa0:frag:0\]”/);
  });

  it("shows no negation-scope row when the text rule did not say negated, or the block carries no scope", () => {
    view(negationReread, (copy) => {
      const consumption = copy.item.consumption as unknown as Record<string, Record<string, unknown>>;
      consumption.statement_scope = { ...consumption.statement_scope, applies: false, governing_negation: false, changed: false, removed: [] };
    });
    expect(screen.queryByTestId("evidence-trace-consumption-statement-scope")).not.toBeInTheDocument();
  });

  it("shows no negation-scope row for a block saved before the scope existed", () => {
    view(admitted);
    expect(screen.queryByTestId("evidence-trace-consumption-statement-scope")).not.toBeInTheDocument();
  });
});
