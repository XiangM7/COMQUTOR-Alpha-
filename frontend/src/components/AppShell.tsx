import type { ReactNode } from "react";
import { Link } from "react-router-dom";

interface AppShellProps {
  children: ReactNode;
}

/** Top-level page frame: skip link, header, main landmark. Deliberately
 * restrained -- a professional research tool, not a marketing shell. */
export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="app-header">
        <Link to="/research" className="app-brand">
          COMQUTOR Alpha
        </Link>
        <p className="app-tagline">Structured research, not a stock tip.</p>
      </header>
      <main id="main-content" className="app-main">
        {children}
      </main>
    </div>
  );
}
