import { useEffect, useState } from "react";
import { getEvidenceTrace } from "../api/client";
import { ApiError, describeApiError } from "../api/errors";
import type {
  EvidenceTraceItem,
  TraceConflictAdoptionEntry,
  TraceConsumption,
  TraceDerivedCalculation,
  TraceDerivedInputs,
  TraceExecutionBasis,
  TraceMaterialRow,
  TraceRelevanceJudgment,
  TraceSource,
  TraceStatus,
} from "../api/evidenceTrace";
import "./evidenceTrace.css";

/**
 * T1 closure -- what lies behind one claim. Loaded on demand from the run's own saved artifacts
 * (GET .../evidence-trace?claim_id=), never computed in the browser.
 *
 * Four checks are shown side by side and never merged into one flag: source support, Alpha match, stance, and
 * what the claim actually contributed to the official score. Below them: the saved source material the claim
 * rests on (with the cells its numbers sit in), how that material was verified, any calculation reproduced from
 * the saved rows (arithmetic only), and how the claim relates to others that use the same observations.
 * An Agent writing "verified" in its own text is flagged as the Agent's wording, never as a system result.
 */

const SOURCE_ROLE_LABELS: Record<string, string> = {
  verified_basis: "Source the verification used",
  primary_link: "Linked source",
  cited: "Also cited by the claim",
};

function formatValue(value: number, unit: string | null): string {
  const abs = Math.abs(value);
  const scaled = abs >= 1e9 ? `${(value / 1e9).toFixed(3)}B` : abs >= 1e6 ? `${(value / 1e6).toFixed(1)}M` : String(value);
  return unit === "fraction_0_to_1" ? `${(value * 100).toFixed(2)}%` : scaled;
}

function StatusBlock({ title, status, extra }: { title: string; status: TraceStatus; extra?: string | null }) {
  return (
    <div className={`evidence-trace-status evidence-trace-status-${status.status_code.toLowerCase().replace(/_/g, "-")}`}>
      <h5>{title}</h5>
      <p className="evidence-trace-status-label">
        <span className="evidence-trace-chip">{status.status_code}</span> {status.label}
      </p>
      {extra ? <p className="evidence-trace-status-extra">{extra}</p> : null}
      <p className="evidence-trace-status-reason">{status.reason}</p>
    </div>
  );
}

const CONSUMPTION_STATE_NOTES: Record<string, string> = {
  CURRENT: "The saved decision equals a fresh recomputation from the run's saved inputs.",
  STALE:
    "A fresh recomputation from the run's current source verification or model ledger differs from the decision saved with the run. The run is shown as it was scored; running its Week 3 pass again brings the decision up to date.",
  MISSING: "This claim carries no saved decision under the contract.",
  NOT_APPLICABLE: "This claim is matched to no Alpha, so only the company-name decision exists.",
};

const WEIGHT_AUTHORITY_LABELS: Record<string, string> = {
  LEXICAL_RULE_FALLBACK: "rule-based lexical score, consumed unchanged (no model relevance judgment exists)",
};

function shortHash(value: string | null): string {
  return value ? `${value.slice(0, 12)}…` : "n/a";
}

const LEDGER_OK = new Set(["MATCHES_MANIFEST", "NO_MANIFEST"]);

/** Which run executed this evaluation, which saved run it recomputes, and whose model ledger corroborated the stances. */
function ExecutionBasisNote({ basis }: { basis: TraceExecutionBasis }) {
  const ledger = basis.stance_ledger;
  return (
    <div className="evidence-trace-execution-basis" data-testid="evidence-trace-execution-basis">
      <p className={basis.recomputation_of_saved_inputs ? "evidence-trace-execution-basis-label" : "evidence-trace-note"}>
        {basis.label ?? "The execution basis was not recorded."}
      </p>
      <dl className="evidence-trace-meta">
        <div>
          <dt>This execution</dt>
          <dd>
            <code>{basis.execution_run_id ?? "n/a"}</code>
            {basis.execution_type ? ` · ${basis.execution_type}` : ""}
          </dd>
        </div>
        {basis.based_on_run_id ? (
          <div>
            <dt>Saved run it recomputes</dt>
            <dd>
              <code>{basis.based_on_run_id}</code>
              {basis.root_research_run_id && basis.root_research_run_id !== basis.based_on_run_id ? (
                <>
                  {" "}
                  · original research run <code>{basis.root_research_run_id}</code>
                </>
              ) : null}
            </dd>
          </div>
        ) : null}
        <div>
          <dt>Stance ledger</dt>
          <dd>
            {ledger && ledger.available ? (
              <>
                run <code>{ledger.owner_run_id ?? "n/a"}</code> · {ledger.binding === "SOURCE_RUN_DECLARED" ? "bound to the saved source run" : "this run's own ledger"} ·{" "}
                <span className={`evidence-trace-chip${LEDGER_OK.has(ledger.integrity ?? "") ? "" : " evidence-trace-chip-warning"}`}>{ledger.integrity ?? "n/a"}</span>
              </>
            ) : (
              <span className="evidence-trace-chip evidence-trace-chip-warning">NO LEDGER</span>
            )}
            {ledger && ledger.available && !LEDGER_OK.has(ledger.integrity ?? "") ? " The ledger cannot corroborate any stance, so the stance policy excludes nothing." : ""}
            {!ledger || !ledger.available ? " Model stances cannot be corroborated, so the stance policy excludes nothing." : ""}
          </dd>
        </div>
      </dl>
    </div>
  );
}

/**
 * alpha_evidence_consumption.v2 -- shown only for a run that declared the contract. It states what the contract decided and why,
 * in words: which model stance toward the matched Alpha was used (or that none was), whether it keeps the claim out of that
 * Alpha's positive pool, whether the company's NAME appears in the claim (never "the claim is about the company"), and which
 * weight was consumed. Nothing here is computed in the browser.
 */
function ConsumptionSection({ consumption }: { consumption: TraceConsumption }) {
  const invalid = consumption.state.startsWith("INVALID");
  const note = invalid
    ? `The saved decision failed validation (${consumption.state.slice("INVALID:".length)}); it is not used as a basis.`
    : CONSUMPTION_STATE_NOTES[consumption.state] ?? "The state of the saved decision could not be determined.";
  const { stance, positive_admission: admission, attribution, relevance, text_rule: textRule, binding } = consumption;
  return (
    <section className="evidence-trace-section evidence-trace-consumption" data-testid="evidence-trace-consumption">
      <h5>How the evidence contract used this claim</h5>
      <p className="evidence-trace-note">
        <span className="evidence-trace-chip">{consumption.contract}</span>{" "}
        <span className={`evidence-trace-chip${consumption.state === "CURRENT" ? "" : " evidence-trace-chip-warning"}`}>{consumption.state}</span>
      </p>
      <p
        className={consumption.state === "CURRENT" ? "evidence-trace-note" : "evidence-trace-consumption-warning"}
        role={consumption.state === "CURRENT" ? undefined : "alert"}
      >
        {note}
        {consumption.verification_error ? ` (${consumption.verification_error})` : ""}
      </p>
      {consumption.execution_basis ? <ExecutionBasisNote basis={consumption.execution_basis} /> : null}
      <dl className="evidence-trace-meta">
        {stance ? (
          <div>
            <dt>Stance toward {consumption.alpha_id ?? "the matched Alpha"}</dt>
            <dd>
              <span className="evidence-trace-chip">{stance.state}</span> {stance.explanation ?? stance.label ?? "no stance recorded"}
            </dd>
          </div>
        ) : null}
        {admission ? (
          <div>
            <dt>Positive pool</dt>
            <dd>
              {admission.reason_code ? <span className="evidence-trace-chip evidence-trace-chip-warning">{admission.reason_code}</span> : null}{" "}
              {admission.explanation ?? (admission.admitted ? "Not excluded." : "Excluded.")}
            </dd>
          </div>
        ) : null}
        {attribution ? (
          <div>
            <dt>Company name</dt>
            <dd>
              <span className="evidence-trace-chip">{attribution.category ?? "n/a"}</span> {attribution.explanation}
              {attribution.ticker_specific ? " The claim may still be about another company or a general topic." : ""}
              {attribution.basis.length > 0 ? ` Matched: ${attribution.basis.map((entry) => `${entry.term} (${entry.kind.replace(/_/g, " ")})`).join(", ")}.` : ""}
              {attribution.other_issuers_named.length > 0 ? ` Other covered companies named: ${attribution.other_issuers_named.join(", ")}.` : ""}
              {attribution.limits.length > 0 ? (
                <>
                  {" "}
                  {attribution.limits.map((limit) => (
                    <span key={limit} className="evidence-trace-chip evidence-trace-chip-warning">
                      {limit}
                    </span>
                  ))}
                </>
              ) : null}
            </dd>
          </div>
        ) : null}
        {relevance ? (
          <div>
            <dt>Relevance weight</dt>
            <dd>
              {relevance.effective_weight !== null ? relevance.effective_weight : "n/a"} —{" "}
              {WEIGHT_AUTHORITY_LABELS[relevance.weight_authority ?? ""] ?? relevance.weight_authority ?? "authority not recorded"}
              {relevance.model_weight === null ? " Model weight: none." : ` Model weight: ${relevance.model_weight}.`}
            </dd>
          </div>
        ) : null}
        {consumption.statement_scope?.applies ? (
          <div data-testid="evidence-trace-consumption-statement-scope">
            <dt>Negation scope</dt>
            <dd>
              <span
                className={`evidence-trace-chip${consumption.statement_scope.governing_negation ? " evidence-trace-chip-warning" : ""}`}
              >
                {consumption.statement_scope.governing_negation ? "NEGATION GOVERNS" : "NEGATION DOES NOT GOVERN"}
              </span>{" "}
              {consumption.statement_scope.explanation}
              {consumption.statement_scope.removed.length > 0
                ? ` Not read as part of the statement: ${consumption.statement_scope.removed.map((item) => `“${item.text}”`).join("; ")}.`
                : ""}
              {consumption.statement_scope.not_applied.length > 0
                ? ` Not removed without the anchor: ${consumption.statement_scope.not_applied.map((item) => `“${item.text}”`).join("; ")}.`
                : ""}
            </dd>
          </div>
        ) : null}
        {textRule ? (
          <div>
            <dt>Text rule (unchanged)</dt>
            <dd>
              relation {textRule.relation ?? "n/a"} · assertion {textRule.assertion_status ?? "n/a"} · polarity {textRule.semantic_polarity ?? "n/a"}
            </dd>
          </div>
        ) : null}
        {binding ? (
          <div>
            <dt>Bound to</dt>
            <dd>
              record inputs <code>{shortHash(binding.input_sha256)}</code> · source state <code>{shortHash(binding.source_state_sha256)}</code> · model ledger{" "}
              {binding.ledger_integrity ?? "not available"}
              {binding.ledger_owner_run_id ? (
                <>
                  {" "}
                  of run <code>{binding.ledger_owner_run_id}</code>
                </>
              ) : null}
            </dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}

/**
 * P4 phase 1 -- the experimental relevance judgment of the claim and its matched Alpha, exactly as the API verified it: the state,
 * the tier (only for a JUDGED pair), the definition elements it is anchored to, the short basis, which run owns the judgment, and
 * why it is missing or failed. A simulated judgment is marked TEST DATA. Nothing here is computed in the browser.
 */
function RelevanceJudgmentSection({ judgment }: { judgment: TraceRelevanceJudgment }) {
  const failed = judgment.state === "FAILED";
  const source = judgment.source;
  return (
    <section className="evidence-trace-section evidence-trace-relevance" data-testid="evidence-trace-relevance">
      <h5>Relevance to {judgment.alpha_id ?? "the matched Alpha"} (experimental)</h5>
      <p className="evidence-trace-note">
        <span className="evidence-trace-chip">{judgment.contract}</span>{" "}
        <span className={`evidence-trace-chip${judgment.state === "JUDGED" ? "" : " evidence-trace-chip-warning"}`}>{judgment.state}</span>
        {judgment.tier ? (
          <>
            {" "}
            <span className="evidence-trace-chip" data-testid="evidence-trace-relevance-tier">
              {judgment.tier}
            </span>
          </>
        ) : null}
        {judgment.test_data ? (
          <>
            {" "}
            <span className="evidence-trace-chip evidence-trace-chip-warning" data-testid="evidence-trace-relevance-test-data">
              TEST DATA
            </span>
          </>
        ) : null}
      </p>
      <p className={failed ? "evidence-trace-consumption-warning" : "evidence-trace-note"} role={failed ? "alert" : undefined}>
        {judgment.label ?? "The relevance state could not be read."}
      </p>
      <dl className="evidence-trace-meta">
        {judgment.anchors.length > 0 ? (
          <div>
            <dt>Definition anchors</dt>
            <dd>
              {judgment.anchors.map((anchor) => (
                <div key={anchor.element_id}>
                  <code>{anchor.element_id}</code>
                  {anchor.label ? ` ${anchor.label}` : ""}
                  {anchor.ownership ? ` · ${anchor.ownership === "core" ? "core-owned" : "strong-eligible"}` : ""}
                  {anchor.occurrences.length > 0 ? ` · ${anchor.occurrences.map((o) => `${o.list}: “${o.phrase}”`).join("; ")}` : ""}
                  {anchor.evidence_quotes.length > 0 ? (
                    <div className="evidence-trace-note" data-testid="evidence-trace-relevance-quote">
                      claim words:{" "}
                      {anchor.evidence_quotes.map((quote, index) => `“${quote}”${anchor.evidence_modes[index] ? ` (${anchor.evidence_modes[index]})` : ""}`).join("; ")}
                    </div>
                  ) : null}
                </div>
              ))}
            </dd>
          </div>
        ) : null}
        {judgment.basis ? (
          <div>
            <dt>Basis</dt>
            <dd>{judgment.basis}</dd>
          </div>
        ) : null}
        {judgment.tier_source ? (
          <div>
            <dt>Tier from</dt>
            <dd data-testid="evidence-trace-relevance-tier-source">
              {judgment.tier_source === "element_ownership_q1"
                ? "the ownership of the elements the statements state (core wins), derived by the program"
                : "the model's judgment that no element is stated (weak or none)"}
            </dd>
          </div>
        ) : null}
        {judgment.statements.length > 0 ? (
          <div>
            <dt>Statements</dt>
            <dd>
              <details data-testid="evidence-trace-relevance-statements">
                <summary>{judgment.statements.length} statement(s) considered</summary>
                <ul>
                  {judgment.statements.map((s, index) => (
                    <li key={`${index}-${s.quote}`}>
                      “{s.quote}” — {s.object ?? "n/a"} / {s.property ?? "n/a"} — {s.mode ?? "n/a"} —{" "}
                      {s.element_id ? <code>{s.element_id}</code> : "no element"} — {s.hit ? "states it" : "does not state it"}
                      {s.why ? `: ${s.why}` : ""}
                    </li>
                  ))}
                </ul>
              </details>
            </dd>
          </div>
        ) : null}
        {judgment.unresolved_reason ? (
          <div>
            <dt>Why unresolved</dt>
            <dd>{judgment.unresolved_reason}</dd>
          </div>
        ) : null}
        {judgment.reason ? (
          <div>
            <dt>{judgment.state === "UNJUDGED" ? "Why no judgment" : "Failure reason"}</dt>
            <dd>
              <span className="evidence-trace-chip evidence-trace-chip-warning">{judgment.reason}</span>
              {judgment.reason_detail ? ` ${judgment.reason_detail}` : ""}
            </dd>
          </div>
        ) : null}
        {judgment.state !== "UNJUDGED" ? (
          <div>
            <dt>Source</dt>
            <dd>
              judgment of run <code>{source.owner_run_id ?? "n/a"}</code> · read by run <code>{source.execution_run_id ?? "n/a"}</code>
              {source.based_on_run_id ? (
                <>
                  {" "}
                  · saved run it derives from <code>{source.based_on_run_id}</code>
                </>
              ) : null}{" "}
              · {source.task ?? "n/a"} / {source.prompt_version ?? "n/a"} / {source.criterion_version ?? "n/a"} · provider{" "}
              {source.provider ?? "n/a"} / {source.model ?? "n/a"}
              {source.execution_mode ? ` (${source.execution_mode})` : ""} · ledger {source.ledger_directory ?? "n/a"}{" "}
              {source.ledger_integrity ?? "not available"}
              {source.call_id ? (
                <>
                  {" "}
                  · call <code>{source.call_id}</code>
                </>
              ) : null}
            </dd>
          </div>
        ) : null}
        <div>
          <dt>Weight</dt>
          <dd>none — {judgment.consumption_note ?? "the label is not consumed."}</dd>
        </div>
      </dl>
    </section>
  );
}

function MaterialRows({ rows }: { rows: TraceMaterialRow[] }) {
  if (rows.length === 0) return null;
  return (
    <table className="evidence-trace-material">
      <caption>Saved rows the claim&apos;s numbers sit in (cells used by the claim are marked)</caption>
      <thead>
        <tr>
          <th scope="col">Row</th>
          <th scope="col">Period</th>
          <th scope="col">Saved value</th>
          <th scope="col">Stated in claim as</th>
        </tr>
      </thead>
      <tbody>
        {rows.flatMap((row) =>
          row.cells.map((cell, index) => (
            <tr key={`${row.label}-${cell.period ?? index}`} className={cell.used ? "evidence-trace-cell-used" : undefined}>
              {index === 0 ? (
                <th scope="row" rowSpan={row.cells.length}>
                  {row.label}
                  {row.unit ? <span className="evidence-trace-unit"> ({row.unit})</span> : null}
                </th>
              ) : null}
              <td>{cell.period ?? "—"}</td>
              <td>{formatValue(cell.value, row.unit)}</td>
              <td>{cell.used ? cell.token ?? "used" : ""}</td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

function SourceView({ source }: { source: TraceSource }) {
  if (!source.resolved) {
    return (
      <li className="evidence-trace-source">
        <p>
          <code>{source.source_id}</code> — not found in this run&apos;s source registry.
        </p>
      </li>
    );
  }
  return (
    <li className="evidence-trace-source">
      <p className="evidence-trace-source-title">
        <strong>{source.title ?? source.source_id}</strong>{" "}
        <span className="evidence-trace-chip">{SOURCE_ROLE_LABELS[source.role] ?? source.role}</span>
      </p>
      <dl className="evidence-trace-meta">
        <div>
          <dt>Provider</dt>
          <dd>
            {source.provider ?? "unknown"}
            {source.instrument ? ` · ${source.instrument}` : ""}
            {source.source_type ? ` · ${source.source_type}` : ""}
          </dd>
        </div>
        {source.observation_date ? (
          <div>
            <dt>Observation date</dt>
            <dd>{source.observation_date}</dd>
          </div>
        ) : null}
        <div>
          <dt>Captured</dt>
          <dd>
            {source.retrieved_at ?? "unknown"}
            {source.time_basis?.note ? ` — ${source.time_basis.note}` : ""}
          </dd>
        </div>
        <div>
          <dt>Location</dt>
          <dd>
            fragment <code>{source.fragment_id ?? "none saved"}</code>
            {source.content_hash ? (
              <>
                {" "}
                · content hash <code>{source.content_hash.slice(0, 12)}…</code>
              </>
            ) : null}
          </dd>
        </div>
      </dl>
      {source.derived_inputs ? <DerivedInputsLine inputs={source.derived_inputs} /> : null}
      {source.has_saved_content ? (
        <MaterialRows rows={source.material_rows} />
      ) : (
        <p className="evidence-trace-no-content">
          No content was saved for this source (title and link only). A title or link proves the source exists; it
          cannot show that the source supports the claim.
        </p>
      )}
      {source.has_saved_content && source.material_rows.length === 0 && source.excerpt_text ? (
        <blockquote className="evidence-trace-excerpt">
          {source.excerpt_text}
          {source.excerpt_truncated ? "…" : ""}
        </blockquote>
      ) : null}
      {source.url ? (
        <a href={source.url} target="_blank" rel="noopener noreferrer" className="evidence-trace-link">
          Open source
        </a>
      ) : null}
    </li>
  );
}

function CalculationView({ calculation }: { calculation: TraceDerivedCalculation }) {
  return (
    <li className="evidence-trace-calculation">
      <p>
        <strong>{calculation.metric.replace(/_/g, " ")}</strong>
        {calculation.comparison ? ` (${calculation.comparison})` : ""}: <code>{calculation.formula}</code>
      </p>
      <p>
        Result {calculation.computed.toFixed(2)}% · claim states <code>{calculation.stated_token}</code> ·{" "}
        <span className="evidence-trace-chip">{calculation.status}</span>
      </p>
      <ul className="evidence-trace-calculation-inputs">
        {calculation.inputs.map((input) => (
          <li key={`${input.label}-${input.period}`}>
            {input.label} @ {input.period ?? "—"} = {formatValue(input.value, input.unit)}
          </li>
        ))}
      </ul>
      <p className="evidence-trace-note">{calculation.scope_note}</p>
    </li>
  );
}

const ADOPTION_SIDE_LABELS: Record<string, string> = {
  bull: "bull evidence",
  bear: "bear evidence",
  counter: "counter-evidence",
};

/** One saved placement of the claim in a conflict, worded as what the run did -- never as a verdict on that judgment. */
function describeAdoption(entry: TraceConflictAdoptionEntry): string {
  const side = ADOPTION_SIDE_LABELS[entry.side] ?? `${entry.side} evidence`;
  const paraphrase = entry.is_representative ? "" : " (as a merged paraphrase of the listed evidence)";
  if (entry.conflict_status === "admitted") {
    const level = entry.conflict_level ? `, level ${entry.conflict_level}` : "";
    const score = entry.conflict_score !== null ? `, score ${entry.conflict_score.toFixed(2)}` : "";
    return `Used as ${side} of conflict ${entry.conflict_id}${paraphrase} — admitted${level}${score}.`;
  }
  return `Listed as ${side} in the evaluation of conflict ${entry.conflict_id}${paraphrase} — not admitted (${entry.conflict_status ?? "status not saved"}).`;
}

function DerivedInputsLine({ inputs }: { inputs: TraceDerivedInputs }) {
  const range = inputs.first_date && inputs.last_date ? ` (${inputs.first_date} → ${inputs.last_date})` : "";
  if (inputs.status === "SAVED") {
    const checked = inputs.recomputation_indicators_checked !== null ? ` (${inputs.recomputation_indicators_checked} indicators)` : "";
    const mismatched = inputs.recomputation_mismatched.length > 0 ? ` — differs for ${inputs.recomputation_mismatched.join(", ")}` : "";
    return (
      <p className="evidence-trace-derived-inputs">
        Indicator inputs: {inputs.row_count ?? "?"} rows saved{range}
        {inputs.version ? ` · ${inputs.version}` : ""} · recomputed from the saved inputs alone:{" "}
        {inputs.recomputation_status ?? "n/a"}
        {checked}
        {mismatched}.
      </p>
    );
  }
  return (
    <p className="evidence-trace-derived-inputs">
      Indicator inputs: not saved in this run ({inputs.method ?? "method n/a"}
      {inputs.version ? `, ${inputs.version}` : ""}; window parameters only
      {inputs.row_count !== null ? `: ${inputs.row_count} rows${range}` : ""}). Nothing is backfilled.
    </p>
  );
}

export function EvidenceTraceView({ item }: { item: EvidenceTraceItem }) {
  const support = item.source_support;
  const content = support.content_support;
  const stanceExtra = item.stance.evidence_stance
    ? `Stance ${item.stance.evidence_stance} · decided by ${item.stance.method ?? "unknown"} · relation ${item.stance.relation ?? "n/a"} · assertion ${item.stance.assertion_status ?? "n/a"}` +
      (item.stance.relation_basis ? ` · basis: ${item.stance.relation_basis}` : "")
    : null;
  const scoringExtra = item.scoring.in_official_pool
    ? `Weight ${item.scoring.weight_contribution ?? 0} · rule match score ${item.scoring.match_score_lexical ?? "n/a"}`
    : item.scoring.not_scored_code;
  const dep = item.dependency;
  return (
    <div className="evidence-trace" data-testid={`evidence-trace-${item.claim_id}`}>
      {item.claim.agent_wording.self_labeled_verified ? (
        <p className="evidence-trace-agent-wording" role="note">
          <span className="evidence-trace-chip evidence-trace-chip-warning">Agent wording</span>{" "}
          {item.claim.agent_wording.note}
        </p>
      ) : null}

      {item.conflict_adoption.entries.length > 0 ? (
        <section className="evidence-trace-section evidence-trace-historical-use">
          <h5>Historical use in this run (as saved)</h5>
          <ul>
            {item.conflict_adoption.entries.map((entry) => (
              <li key={`${entry.conflict_id}-${entry.side}`}>{describeAdoption(entry)}</li>
            ))}
          </ul>
          {item.conflict_adoption.note ? <p className="evidence-trace-note">{item.conflict_adoption.note}</p> : null}
        </section>
      ) : null}

      {item.conflict_adoption.entries.length > 0 || !item.run_basis.link_fields_saved ? (
        <h5 className="evidence-trace-current-basis-heading">Current basis</h5>
      ) : null}
      {!item.run_basis.link_fields_saved && item.run_basis.note ? (
        <>
          <p className="evidence-trace-legacy-note" role="note">
            {item.run_basis.note}
          </p>
          <p className="evidence-trace-note">
            Alpha match, stance and official scoring below are the results this run itself saved; only source support is
            read against today&apos;s source-link fields.
          </p>
        </>
      ) : null}

      <div className="evidence-trace-statuses">
        <StatusBlock
          title="1 · Source support"
          status={support}
          extra={`Link ${support.link_status ?? "n/a"}${support.link_method ? ` (${support.link_method})` : ""} · content ${content.status ?? "n/a"}`}
        />
        <StatusBlock
          title="2 · Alpha match"
          status={item.alpha_match}
          extra={item.alpha_match.matched_alpha ? `Matched ${item.alpha_match.matched_alpha}` : null}
        />
        <StatusBlock title="3 · Stance" status={item.stance} extra={stanceExtra} />
        <StatusBlock title="4 · Official scoring" status={item.scoring} extra={scoringExtra} />
      </div>

      {item.consumption ? <ConsumptionSection consumption={item.consumption} /> : null}
      {item.relevance_judgment ? <RelevanceJudgmentSection judgment={item.relevance_judgment} /> : null}

      <section className="evidence-trace-section">
        <h5>Source material and where the claim sits in it</h5>
        {item.sources.length === 0 ? (
          <p className="evidence-trace-no-content">No source is linked to this claim.</p>
        ) : (
          <ul className="evidence-trace-sources">
            {item.sources.map((source) => (
              <SourceView key={source.source_id} source={source} />
            ))}
          </ul>
        )}
        {content.supporting_quote_or_data ? (
          <div className="evidence-trace-quote">
            <h6>Material the verifier relied on</h6>
            <blockquote>{content.supporting_quote_or_data}</blockquote>
            {content.used_location ? (
              <p>
                Located at: <code>{content.used_location}</code>
                {content.used_source_id ? (
                  <>
                    {" "}
                    in <code>{content.used_source_id}</code>
                  </>
                ) : null}
              </p>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="evidence-trace-section">
        <h5>How it was verified</h5>
        <dl className="evidence-trace-meta">
          <div>
            <dt>Method</dt>
            <dd>
              {content.method ?? "none"}
              {content.task_version ? ` · ${content.task_version}` : ""}
              {content.support_basis ? ` · basis ${content.support_basis}` : ""}
            </dd>
          </div>
          {content.core_proposition ? (
            <div>
              <dt>What was checked</dt>
              <dd>{content.core_proposition}</dd>
            </div>
          ) : null}
          {content.rationale ? (
            <div>
              <dt>Verifier&apos;s reasoning</dt>
              <dd>{content.rationale}</dd>
            </div>
          ) : null}
          {content.unsupported_remainder ? (
            <div>
              <dt>Not backed by the source</dt>
              <dd>
                {content.unsupported_remainder}
                {content.unsupported_materiality ? ` (${content.unsupported_materiality.toLowerCase()})` : ""}
              </dd>
            </div>
          ) : null}
          {content.fallback_reason ? (
            <div>
              <dt>Technical failure</dt>
              <dd>{content.fallback_reason}</dd>
            </div>
          ) : null}
          <div>
            <dt>Counts as verified evidence</dt>
            <dd>
              {support.eligible ? "yes" : "no"} ({support.eligibility_reason_code ?? "n/a"})
              {support.eligibility_time_basis ? ` · time basis ${support.eligibility_time_basis.basis}` : ""}
            </dd>
          </div>
        </dl>
      </section>

      {item.derived_calculations.length > 0 ? (
        <section className="evidence-trace-section">
          <h5>Calculations reproduced from the saved rows</h5>
          <ul className="evidence-trace-calculations">
            {item.derived_calculations.map((calculation) => (
              <CalculationView key={calculation.calc_id} calculation={calculation} />
            ))}
          </ul>
        </section>
      ) : null}

      {item.numbers_not_found_in_saved_data.length > 0 ? (
        <section className="evidence-trace-section">
          <h5>Numbers not found in the saved data</h5>
          <p>
            {item.numbers_not_found_in_saved_data.map((token, index) => (
              <code key={`${token}-${index}`}>{token}</code>
            ))}
          </p>
          <p className="evidence-trace-note">
            This step compares the claim&apos;s numbers with the numeric cells saved for the cited source. A number can be
            missing because it is the Agent&apos;s own level or estimate, or comes from somewhere else; this is not a
            verdict on the claim.
          </p>
        </section>
      ) : null}

      {item.unreproduced_percent_tokens.length > 0 ? (
        <section className="evidence-trace-section">
          <h5>Percentages not reproduced from the saved rows</h5>
          <p>
            {item.unreproduced_percent_tokens.map((token, index) => (
              <code key={`${token}-${index}`}>{token}</code>
            ))}
          </p>
          <p className="evidence-trace-note">
            Only named margins and changes between two values the claim itself quotes are recomputed. A percentage that
            is not reproduced is not thereby wrong; it simply has no recorded calculation here.
          </p>
        </section>
      ) : null}

      {item.scoring.fact_group && item.scoring.fact_group.member_claim_ids.length > 0 ? (
        <section className="evidence-trace-section">
          <h5>Evidence fact and dependencies</h5>
          <p>
            Counted as one independent fact made up of {item.scoring.fact_group.member_claim_ids.length} claim(s)
            {item.scoring.fact_group.member_claim_ids.length > 1 ? " (this one included)" : ""}; each keeps its own
            citations and wording.
            {item.scoring.alpha_result
              ? ` ${item.scoring.alpha_id} has ${item.scoring.alpha_result.claims_in_pool ?? "?"} claims, ${item.scoring.alpha_result.independent_facts ?? "?"} independent facts, ${item.scoring.alpha_result.distinct_agents ?? "?"} agent(s), ${item.scoring.alpha_result.distinct_sources ?? "?"} source(s).`
              : ""}
          </p>
          {dep.depends_on ? (
            <p>
              Derived from <code>{dep.depends_on.split(":claim:")[1] ? `claim ${dep.depends_on.split(":claim:")[1]}` : dep.depends_on}</code>:
              every observation this claim uses is stated by that claim.
            </p>
          ) : null}
          {dep.depended_by.length > 0 ? (
            <p>
              Used as the basis of {dep.depended_by.length} other claim(s):{" "}
              {dep.depended_by.map((id) => `claim ${id.split(":claim:")[1] ?? id}`).join(", ")}.
            </p>
          ) : null}
          {dep.shares_inputs_with.length > 0 ? (
            <p>Shares some data (not the same fact) with: {dep.shares_inputs_with.length} claim(s).</p>
          ) : null}
          {dep.note ? <p className="evidence-trace-note">{dep.note}</p> : null}
        </section>
      ) : null}

      <section className="evidence-trace-section">
        <h5>Where it appears in the report</h5>
        <p>
          {item.claim.agent}
          {item.claim.section ? ` · section “${item.claim.section}”` : ""}
          {item.claim_id.includes(":claim:") ? ` · claim ${item.claim_id.split(":claim:")[1]}` : ""}
        </p>
        {item.claim.paragraph ? <blockquote className="evidence-trace-excerpt">{item.claim.paragraph}</blockquote> : null}
      </section>
      {item.note ? <p className="evidence-trace-note">{item.note}</p> : null}
    </div>
  );
}

/** Loads and shows the trace of one claim; fetched only once this component is mounted (i.e. when opened). */
export function EvidenceTraceDetail({ runId, claimId }: { runId: string; claimId: string }) {
  const [item, setItem] = useState<EvidenceTraceItem | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setItem(null);
    setError(null);
    getEvidenceTrace(runId, claimId, { signal: controller.signal })
      .then((result) => {
        if ("item" in result) setItem(result.item);
        else setError(result.error_code ?? "The evidence trace is not available for this claim.");
      })
      .catch((cause: unknown) => {
        if (cause instanceof ApiError && cause.isAborted) return;
        setError(cause instanceof ApiError ? describeApiError(cause) : "The evidence trace could not be loaded.");
      });
    return () => controller.abort();
  }, [runId, claimId]);

  if (error) return <p className="evidence-trace-error" role="alert">{error}</p>;
  if (!item) return <p className="evidence-trace-loading">Loading evidence trace…</p>;
  return <EvidenceTraceView item={item} />;
}

/** A "View basis" toggle for one claim: nothing is fetched until it is opened. */
export function EvidenceBasisToggle({ runId, claimId }: { runId: string; claimId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="evidence-basis-toggle">
      <button
        type="button"
        className="button button-secondary evidence-basis-button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "Hide basis" : "View basis"}
      </button>
      {open ? <EvidenceTraceDetail runId={runId} claimId={claimId} /> : null}
    </div>
  );
}
