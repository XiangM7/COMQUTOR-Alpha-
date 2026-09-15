import { ReplayAllPanel } from "../components/ReplayAllPanel";

// Product Demo Hardening Phase 2C (P1-4): a narrowly-scoped, non-primary
// route hosting operator/engineering maintenance utilities that do not
// belong in the normal stakeholder research flow. Directly navigable by
// known URL only -- deliberately not linked from the stakeholder-facing
// header/navigation (never a substitute for real access control; this task
// is UI separation, not authentication).
export function OperatorPage() {
  return (
    <div className="operator-page">
      <section className="panel operator-page-intro">
        <h1>Operator Tools</h1>
        <p>Maintenance and replay utilities for persisted research runs.</p>
      </section>
      <ReplayAllPanel />
    </div>
  );
}
