import type { ReactNode, Ref } from "react";

interface ProgressSummaryProps {
  /** Large line: the time estimate, or the final state. */
  headline: string;
  /** Backend-reported percentage, or null when the run reports none. */
  percent: number | null;
  /** Width, in percentage points, of the animated band that marks the
   * stage being worked on (starts at `percent`). 0 for none. */
  activeBandWidth: number;
  basis: string;
  elapsed: string | null;
  trackRef?: Ref<HTMLDivElement>;
  className?: string;
  children?: ReactNode;
}

/**
 * Estimate, percentage and progress bar. The percentage is always the value
 * the backend last reported -- nothing here makes it move on its own. The
 * animated band only shows which stretch of the bar is being worked on.
 */
export function ProgressSummary({ headline, percent, activeBandWidth, basis, elapsed, trackRef, className, children }: ProgressSummaryProps) {
  return (
    <section aria-label="Progress" className={className ? `progress-summary ${className}` : "progress-summary"}>
      <div className="progress-headline-row">
        <p className="progress-headline" aria-live="polite">
          {headline}
        </p>
        {percent !== null ? <p className="progress-percent">{percent}%</p> : null}
      </div>
      <div
        ref={trackRef}
        className="progress-track"
        role="progressbar"
        aria-label="Research progress"
        aria-valuemin={0}
        aria-valuemax={100}
        {...(percent !== null ? { "aria-valuenow": percent } : {})}
      >
        <div className="progress-fill" style={{ width: `${percent ?? 0}%` }} />
        {percent !== null && activeBandWidth > 0 ? (
          <div className="progress-band" style={{ left: `${percent}%`, width: `${activeBandWidth}%` }} />
        ) : null}
      </div>
      <div className="progress-meta">
        <span>{basis}</span>
        {elapsed ? <span>Elapsed {elapsed}</span> : null}
      </div>
      {children}
    </section>
  );
}
