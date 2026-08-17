import { useState } from "react";
import type {
  AlphaInvalidationEntry,
  ConflictEvidenceUI,
  ConflictEvidenceUIItem,
  ConflictMissingEvidenceItem,
  ConflictQualificationGapItem,
} from "../api/types";

// B5 Conflict Radar Evidence UI (task B5_CONFLICT_RADAR_EVIDENCE_UI). Every
// list here is already deterministically ordered by the backend (ticker-
// specific first, then match score descending, then evidence_fact_group_id
// ascending) -- this component never re-sorts, never re-filters by stance,
// and never recomputes a deficit/threshold. It only renders what the
// backend already decided.

const DEFAULT_VISIBLE_COUNT = 5;

const MISSING_EVIDENCE_LABELS: Record<string, string> = {
  INSUFFICIENT_SUPPORTING_EVIDENCE: "Insufficient supporting evidence",
  NO_TICKER_SPECIFIC_SUPPORTING_EVIDENCE: "No ticker-specific supporting evidence",
  NO_ADMISSIBLE_SUPPORTING_POLARITY: "Evidence present, but none of it is admissible support",
};

function stanceMethodLabel(item: ConflictEvidenceUIItem): string {
  if (item.stance_method === "llm") return "LLM-reviewed";
  if (item.stance_method === "deterministic_fallback") return "deterministic (LLM fallback)";
  return "deterministic (LLM not attempted)";
}

function EvidenceFactCard({ item }: { item: ConflictEvidenceUIItem }) {
  const otherMembers = item.member_claim_ids.filter((id) => id !== item.representative_claim_id);
  return (
    <li className="evidence-ui-item">
      <p className="evidence-ui-item-text">{item.evidence_text}</p>
      <p className="evidence-ui-item-meta">
        <span>Agents: {item.agents.join(", ") || "unknown"}</span>
        {" · "}
        <span>Match {item.representative_match_score.toFixed(2)}</span>
        {" · "}
        <span>Target Alpha: {item.target_alpha_id}</span>
        {" · "}
        <span>{item.ticker_specific ? "Ticker-specific" : "Not ticker-specific"}</span>
        {" · "}
        <span>
          Stance: {item.evidence_stance} ({stanceMethodLabel(item)}
          {item.evidence_stance_version ? `, ${item.evidence_stance_version}` : ""})
        </span>
        {item.stance_confidence_band ? (
          <>
            {" · "}
            <span>Confidence: {item.stance_confidence_band}</span>
          </>
        ) : null}
        {item.supports_counter_alpha_id ? (
          <>
            {" · "}
            <span>Supports counter Alpha {item.supports_counter_alpha_id}</span>
          </>
        ) : null}
      </p>
      {otherMembers.length > 0 ? (
        <details className="evidence-ui-item-merged">
          <summary>{otherMembers.length} merged paraphrase(s)</summary>
          <ul>
            {otherMembers.map((id) => (
              <li key={id}>{id}</li>
            ))}
          </ul>
        </details>
      ) : null}
      <p className="evidence-ui-item-id">
        <code>{item.evidence_fact_group_id}</code>
        {item.source_agent_output_ids.length > 0 ? (
          <>
            {" · Source: "}
            <code>{item.source_agent_output_ids.join(", ")}</code>
          </>
        ) : null}
      </p>
    </li>
  );
}

function EvidenceFactList({ items, emptyMessage }: { items: ConflictEvidenceUIItem[]; emptyMessage: string }) {
  const [expanded, setExpanded] = useState(false);
  if (items.length === 0) {
    return <p className="evidence-ui-section-empty">{emptyMessage}</p>;
  }
  const visible = expanded ? items : items.slice(0, DEFAULT_VISIBLE_COUNT);
  return (
    <>
      <ul className="evidence-ui-list">
        {visible.map((item) => (
          <EvidenceFactCard
            key={`${item.evidence_fact_group_id}::${item.counter_target_alpha_id ?? item.target_alpha_id}`}
            item={item}
          />
        ))}
      </ul>
      {items.length > DEFAULT_VISIBLE_COUNT ? (
        <button
          type="button"
          className="evidence-ui-show-toggle"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Show less" : `Show all (${items.length})`}
        </button>
      ) : null}
    </>
  );
}

function EvidenceSection({
  title,
  items,
  emptyMessage,
}: {
  title: string;
  items: ConflictEvidenceUIItem[];
  emptyMessage: string;
}) {
  return (
    <section className="evidence-ui-section">
      <h4>
        {title} ({items.length})
      </h4>
      <EvidenceFactList items={items} emptyMessage={emptyMessage} />
    </section>
  );
}

function CounterEvidenceSection({
  items,
  bullAlphaId,
  bearAlphaId,
}: {
  items: ConflictEvidenceUIItem[];
  bullAlphaId: string;
  bearAlphaId: string;
}) {
  const againstBull = items.filter((item) => item.counter_target_alpha_id === bullAlphaId);
  const againstBear = items.filter((item) => item.counter_target_alpha_id === bearAlphaId);
  return (
    <section className="evidence-ui-section counter-evidence-section">
      <h4>Counter Evidence ({items.length})</h4>
      <div className="counter-evidence-groups">
        <div className="counter-evidence-group">
          <p className="counter-evidence-group-title">Against bull structure ({bullAlphaId})</p>
          <EvidenceFactList
            items={againstBull}
            emptyMessage="No counter evidence against the bull structure."
          />
        </div>
        <div className="counter-evidence-group">
          <p className="counter-evidence-group-title">Against bear structure ({bearAlphaId})</p>
          <EvidenceFactList
            items={againstBear}
            emptyMessage="No counter evidence against the bear structure."
          />
        </div>
      </div>
    </section>
  );
}

function MissingEvidenceSection({ items }: { items: ConflictMissingEvidenceItem[] }) {
  return (
    <section className="evidence-ui-section missing-evidence-section">
      <h4>Missing Evidence</h4>
      {items.length === 0 ? (
        <p className="evidence-ui-section-empty">No B2 evidence gaps identified.</p>
      ) : (
        <ul>
          {items.map((item, index) => (
            <li key={`${item.side}-${item.missing_reason_code}-${index}`} className="missing-evidence-item">
              <span className="missing-evidence-side">
                {item.side === "bull" ? "Bull" : "Bear"} ({item.alpha_id})
              </span>
              {" — "}
              <span>{MISSING_EVIDENCE_LABELS[item.missing_reason_code] ?? item.missing_reason_code}</span>
              {": "}
              <span>
                {item.current_value} of {item.required_value} required (deficit {item.deficit})
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function QualificationGapsSection({ items }: { items: ConflictQualificationGapItem[] }) {
  // `items` is only ever reached once the whole evidence_ui block is
  // present (see ConflictCard's historical fallback below) -- at that
  // point qualification_gaps is a required, non-optional field, so an
  // empty array here is the backend's own explicit "zero gaps" answer,
  // never a historical/absent-field case standing in for one.
  return (
    <section className="evidence-ui-section qualification-gaps-section">
      <h4>Qualification gaps</h4>
      {items.length === 0 ? (
        <p className="evidence-ui-section-empty">No qualification gaps identified.</p>
      ) : (
        <>
          <p className="qualification-gaps-note">
            Not an evidence gap -- an Activation-score shortfall for this side.
          </p>
          <ul>
            {items.map((item, index) => (
              <li key={`${item.side}-${item.gap_reason_code}-${index}`}>
                <span>
                  {item.side === "bull" ? "Bull" : "Bear"} ({item.alpha_id})
                </span>
                {" — Activation score "}
                <span>{item.current_value != null ? item.current_value.toFixed(1) : "unavailable"}</span>
                {` (requires >= ${item.required_value.toFixed(0)})`}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function InvalidationSection({ entry, roleLabel }: { entry: AlphaInvalidationEntry; roleLabel: string }) {
  return (
    <section className="evidence-ui-section invalidation-section">
      <h4>
        What would invalidate {roleLabel} — {entry.alpha_id}
        {entry.alpha_name ? ` (${entry.alpha_name})` : ""}?
      </h4>
      {entry.approval_status === "approved" ? (
        <>
          <ul>
            {entry.conditions.map((condition) => (
              <li key={condition.condition_id}>{condition.condition_text}</li>
            ))}
          </ul>
          <p className="invalidation-provenance">
            Source: {entry.source} · Version: {entry.version}
          </p>
        </>
      ) : (
        <p className="invalidation-pending">
          Invalidation conditions have not yet been product-approved for this Alpha.
        </p>
      )}
    </section>
  );
}

export function ConflictEvidenceSections({
  evidenceUi,
  bullAlphaId,
  bearAlphaId,
}: {
  evidenceUi: ConflictEvidenceUI;
  bullAlphaId: string;
  bearAlphaId: string;
}) {
  return (
    <div className="conflict-evidence-ui">
      <div className="evidence-ui-row">
        <EvidenceSection
          title="Bull Evidence"
          items={evidenceUi.bull_evidence}
          emptyMessage="No supporting evidence for the bull structure."
        />
        <EvidenceSection
          title="Bear Evidence"
          items={evidenceUi.bear_evidence}
          emptyMessage="No supporting evidence for the bear structure."
        />
      </div>
      <div className="evidence-ui-row">
        <CounterEvidenceSection
          items={evidenceUi.counter_evidence}
          bullAlphaId={bullAlphaId}
          bearAlphaId={bearAlphaId}
        />
        <MissingEvidenceSection items={evidenceUi.missing_evidence} />
      </div>
      <QualificationGapsSection items={evidenceUi.qualification_gaps} />
      <div className="evidence-ui-row invalidation-conditions-row">
        <InvalidationSection entry={evidenceUi.invalidation_conditions.bull_alpha} roleLabel="the bull alpha" />
        <InvalidationSection entry={evidenceUi.invalidation_conditions.bear_alpha} roleLabel="the bear alpha" />
      </div>
    </div>
  );
}
