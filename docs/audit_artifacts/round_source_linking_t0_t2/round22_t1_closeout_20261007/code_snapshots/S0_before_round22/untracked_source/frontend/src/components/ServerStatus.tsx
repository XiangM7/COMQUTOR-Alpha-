import { useReadiness } from "../hooks/useReadiness";
import { describeServerStatus } from "../utils/serverStatus";

/** Server status shown at the right of the navigation bar: a dot plus one
 * line of text. The full error message, when there is one, is kept in the
 * tooltip and shown in full on the Research page. */
export function ServerStatus() {
  const { readiness, errorMessage } = useReadiness();
  const { tone, label } = describeServerStatus(readiness, errorMessage);
  return (
    <p className="server-status" role="status" title={errorMessage ?? undefined}>
      <span className={`server-status-dot server-status-dot-${tone}`} aria-hidden="true" />
      <span>{label}</span>
    </p>
  );
}
