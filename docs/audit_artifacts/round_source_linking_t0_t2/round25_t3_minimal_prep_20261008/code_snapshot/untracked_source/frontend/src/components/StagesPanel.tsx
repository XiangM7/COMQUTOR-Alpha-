import type { RunNotification } from "../hooks/useRunNotification";
import { STAGE_GROUPS, type StageProgress, type StageState } from "../utils/processingStages";

const STATE_WORDS: Record<StageState, string> = {
  done: "completed",
  current: "in progress",
  failed: "failed",
  pending: "pending",
};

function StageMarker({ state }: { state: StageState }) {
  if (state === "done") {
    return (
      <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16">
        <circle cx="8" cy="8" r="8" fill="currentColor" />
        <path d="M4.6 8.2 7 10.5l4.4-4.8" fill="none" stroke="var(--color-surface)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (state === "current") return <span className="stage-dot stage-dot-current" aria-hidden="true" />;
  if (state === "failed") return <span className="stage-dot stage-dot-failed" aria-hidden="true" />;
  return <span className="stage-dot stage-dot-pending" aria-hidden="true" />;
}

function NotifyControl({ notification }: { notification: RunNotification }) {
  if (notification.permission === "default") {
    return (
      <button type="button" className="menu-text-button stages-notify" onClick={notification.enable}>
        Notify me when done
      </button>
    );
  }
  if (notification.permission === "granted") {
    return <p className="stages-note">You will get a notification when it finishes, if this tab is in the background.</p>;
  }
  if (notification.permission === "denied") {
    return <p className="stages-note">Notifications are blocked in your browser settings.</p>;
  }
  return null;
}

interface StagesPanelProps {
  progress: StageProgress;
  notification: RunNotification;
  /** The run is still going: only then does the leave-the-page note apply
   * and a notification make sense. */
  showNotify: boolean;
  className?: string;
}

/** Every stage of the run in four groups, each marked by shape and by words
 * (not by color alone). */
export function StagesPanel({ progress, notification, showNotify, className }: StagesPanelProps) {
  return (
    <section aria-labelledby="stages-title" className={className ? `stages-panel ${className}` : "stages-panel"}>
      <h2 id="stages-title">Stages</h2>
      {STAGE_GROUPS.map((group) => {
        const rows = progress.plan
          .map((entry, index) => ({ entry, state: progress.states[index] ?? "pending" }))
          .filter(({ entry }) => entry.group === group.key);
        if (rows.length === 0) return null;
        return (
          <div className="stages-group" key={group.key}>
            <p className="stages-group-name">{group.name}</p>
            <ol className="stages-list" aria-label={group.name}>
              {rows.map(({ entry, state }) => (
                <li key={entry.stage} className={`stage-row stage-row-${state}`}>
                  <span className="stage-marker">
                    <StageMarker state={state} />
                  </span>
                  <span className="stage-label">{entry.label}</span>
                  <span className={state === "current" || state === "failed" ? "stage-state" : "visually-hidden"}>
                    {STATE_WORDS[state]}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        );
      })}
      {showNotify ? (
        <div className="stages-footer">
          <p className="stages-note">You can leave this page. The run keeps going.</p>
          <NotifyControl notification={notification} />
        </div>
      ) : null}
    </section>
  );
}
