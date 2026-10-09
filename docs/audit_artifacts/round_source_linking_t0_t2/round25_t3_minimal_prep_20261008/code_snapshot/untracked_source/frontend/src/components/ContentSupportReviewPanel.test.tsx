import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ContentSupportReviewPanel } from "./ContentSupportReviewPanel";

function renderPanel(runId = "run-1", claimId = "claim-1") {
  return render(
    <MemoryRouter>
      <ContentSupportReviewPanel runId={runId} claimId={claimId} />
    </MemoryRouter>
  );
}

describe("ContentSupportReviewPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("is collapsed by default and does not fetch history until expanded", () => {
    const reviewsSpy = vi.spyOn(client, "getContentSupportReviews");
    renderPanel();
    expect(screen.getByRole("button", { name: /review this claim's source/i })).toBeInTheDocument();
    expect(reviewsSpy).not.toHaveBeenCalled();
  });

  it("states plainly that the reviewer field is not an authenticated identity", async () => {
    vi.spyOn(client, "getContentSupportReviews").mockResolvedValue({
      status: "ok", run_id: "run-1", reviews: [], count: 0,
    });
    vi.spyOn(client, "getReevaluationExecutions").mockResolvedValue({
      status: "ok", run_id: "run-1", executions: [], count: 0,
    });
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /review this claim's source/i }));
    expect(screen.getByText(/never an authenticated identity/i)).toBeInTheDocument();
  });

  it("refuses to save with an empty reviewer or rationale, never calling the API", async () => {
    vi.spyOn(client, "getContentSupportReviews").mockResolvedValue({
      status: "ok", run_id: "run-1", reviews: [], count: 0,
    });
    vi.spyOn(client, "getReevaluationExecutions").mockResolvedValue({
      status: "ok", run_id: "run-1", executions: [], count: 0,
    });
    const submitSpy = vi.spyOn(client, "submitContentSupportReview");
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /review this claim's source/i }));
    await user.click(screen.getByRole("button", { name: /save review/i }));
    expect(await screen.findByText(/enter your name or identifier/i)).toBeInTheDocument();
    expect(submitSpy).not.toHaveBeenCalled();
  });

  it("a failed save is shown as a failure, never displayed as success", async () => {
    vi.spyOn(client, "getContentSupportReviews").mockResolvedValue({
      status: "ok", run_id: "run-1", reviews: [], count: 0,
    });
    vi.spyOn(client, "getReevaluationExecutions").mockResolvedValue({
      status: "ok", run_id: "run-1", executions: [], count: 0,
    });
    vi.spyOn(client, "submitContentSupportReview").mockResolvedValue({
      status: "failed",
      run_id: "run-1",
      ticker: "NVDA",
      error_code: "CLAIM_NOT_ELIGIBLE_FOR_REVIEW",
      message: "This claim has no valid source link to review against.",
    });
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /review this claim's source/i }));
    await user.type(screen.getByLabelText(/reviewer/i), "analyst_a");
    await user.type(screen.getByLabelText(/rationale/i), "matches the excerpt");
    await user.click(screen.getByRole("button", { name: /save review/i }));

    expect(await screen.findByText(/no valid source link to review against/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Saved as/)).not.toBeInTheDocument();
  });

  it("a successful save shows the saved verdict and a link to the new execution's results", async () => {
    vi.spyOn(client, "getContentSupportReviews").mockResolvedValue({
      status: "ok", run_id: "run-1", reviews: [], count: 0,
    });
    vi.spyOn(client, "getReevaluationExecutions").mockResolvedValue({
      status: "ok", run_id: "run-1", executions: [], count: 0,
    });
    vi.spyOn(client, "submitContentSupportReview").mockResolvedValue({
      status: "ok",
      run_id: "run-1",
      claim_id: "claim-1",
      content_support_status: "SUPPORTS",
      content_support_review: {
        schema_version: "content_support_review.v1",
        status: "SUPPORTS",
        method: "HUMAN_REVIEWED",
        reviewer: "analyst_a",
        rationale: "matches the excerpt",
        reviewed_at: "2026-09-29T00:00:00Z",
        claim_id: "claim-1",
        linked_source_id: "s1:frag-0",
        content_hash: "sha256:x",
        review_id: "abc123",
      },
      reevaluation: {
        status: "ok",
        run_id: "run-1",
        execution_id: "review-20260929T000000Z-abcdef12",
        based_on_run_id: "run-1",
        review_log_entry_count: 1,
      },
    });
    const user = userEvent.setup();
    renderPanel("run-1", "claim-1");
    await user.click(screen.getByRole("button", { name: /review this claim's source/i }));
    await user.type(screen.getByLabelText(/reviewer/i), "analyst_a");
    await user.type(screen.getByLabelText(/rationale/i), "matches the excerpt");
    await user.click(screen.getByRole("button", { name: /save review/i }));

    expect(await screen.findByText(/Saved as SUPPORTS by analyst_a/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /view results/i });
    expect(link).toHaveAttribute("href", "/runs/review-20260929T000000Z-abcdef12/research");
  });

  it("shows prior review history and past executions after reload (re-fetched on expand)", async () => {
    vi.spyOn(client, "getContentSupportReviews").mockResolvedValue({
      status: "ok",
      run_id: "run-1",
      reviews: [
        {
          schema_version: "content_support_review.v1",
          status: "SUPPORTS",
          method: "HUMAN_REVIEWED",
          reviewer: "analyst_a",
          rationale: "earlier rationale",
          reviewed_at: "2026-09-28T00:00:00Z",
          claim_id: "claim-1",
          linked_source_id: "s1:frag-0",
          content_hash: "sha256:x",
          review_id: "earlier-review",
        },
      ],
      count: 1,
    });
    vi.spyOn(client, "getReevaluationExecutions").mockResolvedValue({
      status: "ok",
      run_id: "run-1",
      executions: [
        { execution_id: "review-earlier-exec", triggered_at: "2026-09-28T00:00:00Z", review_log_entry_count: 1 },
      ],
      count: 1,
    });
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /review this claim's source/i }));

    expect(await screen.findByText(/earlier rationale/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review.*applied/i })).toHaveAttribute(
      "href",
      "/runs/review-earlier-exec/research"
    );
  });
});
