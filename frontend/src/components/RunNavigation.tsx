import { NavLink } from "react-router-dom";

interface RunNavigationProps {
  runId: string;
}

/** Shared navigation between the three result pages for one run_id. Every
 * link carries the run_id explicitly (via the URL), so navigating never
 * loses it and a page refresh on any of these routes still resolves the
 * same run. */
export function RunNavigation({ runId }: RunNavigationProps) {
  const encoded = encodeURIComponent(runId);
  return (
    <nav className="run-navigation" aria-label="Research run sections">
      <NavLink to={`/runs/${encoded}/research`} className={({ isActive }) => (isActive ? "run-nav-link active" : "run-nav-link")}>
        Research
      </NavLink>
      <NavLink to={`/runs/${encoded}/structure`} className={({ isActive }) => (isActive ? "run-nav-link active" : "run-nav-link")}>
        Structure Graph
      </NavLink>
      <NavLink to={`/runs/${encoded}/conflicts`} className={({ isActive }) => (isActive ? "run-nav-link active" : "run-nav-link")}>
        Conflict Radar
      </NavLink>
    </nav>
  );
}
