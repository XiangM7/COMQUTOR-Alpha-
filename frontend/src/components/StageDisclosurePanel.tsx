import type { StageDisclosure } from "../api/types";

// T4 round 32: which model-assisted sub-steps of this run were degraded or fell back to deterministic processing,
// read from the run's own semantic ledger (GET /api/research/{run_id} -> stage_disclosure). A run's "Completed" status
// means the flow finished; it does not mean every sub-step produced a model result -- this panel says which did not.

const STAGE_LABELS: Record<string, string> = {
  claim_enrichment: "Claim enrichment",
  content_support_verification: "Content support verification",
  alpha_classification: "Alpha classification",
  evidence_stance: "Evidence stance",
  structure_extraction: "Model structure extraction",
  structure_graph: "Structure Graph construction",
};

const STATUS_LABELS: Record<string, string> = {
  model_complete: "model result used for every call",
  degraded: "degraded: some calls fell back",
  model_not_used: "no model result used (deterministic fallback)",
  not_run: "no model call",
  not_recorded: "not recorded",
  built: "built",
  not_built: "not built",
};

export function StageDisclosurePanel({ disclosure }: { disclosure: StageDisclosure | null | undefined }) {
  if (!disclosure) return null;
  return (
    <div className="stage-disclosure" data-testid="stage-disclosure">
      <h3>Processing completeness</h3>
      {disclosure.degraded_stages.length === 0 ? (
        <p>No model-assisted sub-step was degraded.</p>
      ) : (
        <ul className="stage-disclosure-notes">
          {disclosure.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      <table className="stage-disclosure-table">
        <thead>
          <tr>
            <th>Sub-step</th>
            <th>Result</th>
            <th>Calls</th>
          </tr>
        </thead>
        <tbody>
          {disclosure.stages.map((stage) => (
            <tr key={stage.stage}>
              <td>{STAGE_LABELS[stage.stage] ?? stage.stage}</td>
              <td>{STATUS_LABELS[stage.status] ?? stage.status}</td>
              <td>{stage.calls ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
