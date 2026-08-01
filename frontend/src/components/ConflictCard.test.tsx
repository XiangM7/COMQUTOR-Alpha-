import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AlphaConflict } from "../api/types";
import { ConflictCard } from "./ConflictCard";

function makeConflict(overrides: Partial<AlphaConflict> = {}): AlphaConflict {
  return {
    conflict_id: "A301__A304",
    alpha_a: "A301",
    alpha_b: "A304",
    bull_alpha_id: "A301",
    bear_alpha_id: "A304",
    bull_structure: {
      alpha_id: "A301",
      alpha_name: "GPU Demand",
      activation_score: 66.5,
      status: "active",
      direction: "positive",
      claim_ids: ["c1"],
      source_agent_output_ids: ["o1"],
      agents: ["news_agent"],
      evidence: ["GPU demand is accelerating."],
      match_scores: [0.9],
    },
    bear_structure: {
      alpha_id: "A304",
      alpha_name: "Valuation Risk",
      activation_score: 55.2,
      status: "active",
      direction: "negative",
      claim_ids: ["b1", "b2"],
      source_agent_output_ids: ["o2", "o3"],
      agents: ["bear_researcher", "news_agent"],
      evidence: ["Valuation multiples remain stretched.", "Valuation multiples look stretched too."],
      match_scores: [0.8, 0.75],
    },
    components: {
      activation_a: 66.5,
      activation_b: 55.2,
      minimum_activation: 55.2,
      contradiction_weight: 0.9,
      alpha_a_evidence_strength: 0.9,
      alpha_b_evidence_strength: 0.78,
      evidence_strength: 0.84,
    },
    alpha_a_strength: 0.9,
    alpha_b_strength: 0.78,
    evidence_strength: 0.84,
    conflict_score: 36.8,
    conflict_level: "medium_high",
    reason_codes: [],
    explanation: "GPU Demand and Valuation Risk present a structural tension.",
    bull_evidence: [
      { claim_id: "c1", claim_text: "GPU demand is accelerating.", agent: "news_agent", match_score: 0.9, relation: "activation" },
    ],
    bear_evidence: [
      {
        claim_id: "b1",
        claim_text: "Valuation multiples remain stretched.",
        agent: "bear_researcher",
        match_score: 0.8,
        relation: "activation",
      },
      {
        claim_id: "b2",
        claim_text: "Valuation multiples look stretched too.",
        agent: "news_agent",
        match_score: 0.75,
        relation: "activation",
      },
    ],
    ...overrides,
  };
}

describe("ConflictCard", () => {
  it("shows independent-fact stats per side when the API provides them (A304 profile)", () => {
    render(
      <ConflictCard
        conflict={makeConflict({
          bull_raw_claim_count: 1,
          bull_unique_fact_count: 1,
          bull_distinct_agent_count: 1,
          bull_overlap_ratio: 0.0,
          bear_raw_claim_count: 11,
          bear_unique_fact_count: 5,
          bear_distinct_agent_count: 5,
          bear_overlap_ratio: 0.5455,
        })}
      />
    );
    expect(screen.getByText(/from 11 raw supporting claims/)).toBeInTheDocument();
    expect(screen.getByText(/Evidence overlap: 54.5%/)).toBeInTheDocument();
    // Must never present the raw count as if it were the independent count.
    expect(screen.queryByText(/Independent evidence facts: 11/)).not.toBeInTheDocument();
  });

  it("omits fact stats gracefully when the API predates these fields", () => {
    render(<ConflictCard conflict={makeConflict()} />);
    expect(screen.queryByText(/Independent evidence facts/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw supporting claims/)).not.toBeInTheDocument();
  });

  it("renders one evidence card per fact group, not one per raw paraphrase claim", () => {
    render(
      <ConflictCard
        conflict={makeConflict({
          bear_structure: {
            ...makeConflict().bear_structure,
            evidence_facts: [
              {
                evidence_fact_group_id: "fact1",
                representative_claim_id: "b1",
                member_claim_ids: ["b1", "b2"],
                supporting_agents: ["bear_researcher", "news_agent"],
                grouping_method: "evidence_fact_index.v1",
              },
            ],
          },
        })}
      />
    );
    // Only ONE bear evidence card despite 2 raw claims.
    const bearCards = screen.getAllByText("Valuation multiples remain stretched.");
    expect(bearCards).toHaveLength(1);
    expect(screen.getByText("1 merged paraphrase(s)")).toBeInTheDocument();
    // The merged paraphrase is available on expand inside the "merged"
    // detail, never rendered as its own top-level "text" paragraph the way
    // a representative claim is.
    expect(
      screen.getByText("Valuation multiples look stretched too.").closest(".conflict-side-evidence-merged")
    ).not.toBeNull();
    expect(screen.queryAllByText("Valuation multiples look stretched too.", { selector: "p" })).toHaveLength(0);
  });

  it("falls back to per-claim evidence cards when evidence_facts is unavailable", () => {
    render(<ConflictCard conflict={makeConflict()} />);
    expect(screen.getByText("Valuation multiples remain stretched.")).toBeInTheDocument();
    expect(screen.getByText("Valuation multiples look stretched too.")).toBeInTheDocument();
  });
});
