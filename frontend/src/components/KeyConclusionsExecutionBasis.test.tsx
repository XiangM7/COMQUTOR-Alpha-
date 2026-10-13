import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { adaptKeyConclusionsResponse } from "../api/evidenceTrace";
import { KeyConclusionsPanel } from "./KeyConclusionsPanel";

// The research page's key-conclusions panel states the run-level execution basis BEFORE any claim is opened: a recomputation of a
// saved run's inputs is labelled as such -- never as a Fresh Run -- and names the saved run it recomputes. A run outside the evidence
// contract and the recompute entry carries no execution basis, and its panel is unchanged.

const SOURCE = "12591384-0b26-470d-a99d-a49c00be440b";
const EXEC = "consumption-20261012T000034Z-673b19aa";
// the execution_basis object exactly as the production route builds it for a consumption recompute execution
const BASIS = {
  execution_run_id: EXEC,
  execution_type: "alpha_evidence_consumption_recompute",
  based_on_run_id: SOURCE,
  root_research_run_id: null,
  recomputation_of_saved_inputs: true,
  label:
    "Recomputation of a saved run's inputs under the evidence contract -- not a Fresh Run. This execution made no model, search or data-fetch call; every stance is the source run's saved result (nothing was re-judged).",
  stance_ledger: { available: true, integrity: "MATCHES_MANIFEST", sha256: "6076153fdde048e5", owner_run_id: SOURCE, binding: "SOURCE_RUN_DECLARED", usable: true },
};

function keyView(extra: Record<string, unknown>) {
  const adapted = adaptKeyConclusionsResponse({
    run_id: EXEC,
    ticker: "NVDA",
    status: "ok",
    key_conclusions: { rule: "final-decision chain", claim_count: 0, status_counts: {}, groups: [], agent_wording_verified_count: 0, ...extra },
  });
  if (!adapted.ok) throw new Error(adapted.reason);
  return adapted.value;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("KeyConclusionsPanel: run-level execution basis", () => {
  it("labels a recomputation of saved inputs as not a Fresh Run and names the saved run, before any claim is opened", async () => {
    vi.spyOn(client, "getKeyConclusions").mockResolvedValue(keyView({ execution_basis: BASIS }));
    render(<KeyConclusionsPanel runId={EXEC} />);
    const note = await screen.findByTestId("key-conclusions-execution-basis");
    expect(note.textContent).toContain(BASIS.label);
    expect(note.textContent).toContain(`Saved run: ${SOURCE}`);
    expect(note.className).toBe("evidence-trace-execution-basis-label");
  });

  it("shows no execution basis for a run that carries none", async () => {
    vi.spyOn(client, "getKeyConclusions").mockResolvedValue(keyView({}));
    render(<KeyConclusionsPanel runId="12591384-0b26-470d-a99d-a49c00be440b" />);
    await screen.findByText("No final-decision claims were found in this run.");
    expect(screen.queryByTestId("key-conclusions-execution-basis")).toBeNull();
  });
});
