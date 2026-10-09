import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { ServerStatus } from "./ServerStatus";

interface AppShellProps {
  children: ReactNode;
}

/** Top-level page frame: skip link, sticky translucent navigation, main
 * landmark. Deliberately restrained -- a professional research tool, not a
 * marketing shell. */
export function AppShell({ children }: AppShellProps) {
  const { pathname } = useLocation();
  const onOperator = pathname === "/operator" || pathname.startsWith("/operator/");

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="app-header">
        <nav className="app-nav" aria-label="Primary">
          <Link to="/research" className="app-brand">
            COMQUTOR Alpha
          </Link>
          <div className="app-nav-links">
            <Link
              to="/research"
              className={onOperator ? "app-nav-link" : "app-nav-link app-nav-link-active"}
              aria-current={pathname === "/research" ? "page" : undefined}
            >
              Research
            </Link>
            <Link
              to="/operator"
              className={onOperator ? "app-nav-link app-nav-link-active" : "app-nav-link"}
              aria-current={pathname === "/operator" ? "page" : undefined}
            >
              Operator
            </Link>
          </div>
          <ServerStatus />
        </nav>
      </header>
      <main id="main-content" className="app-main">
        {children}
      </main>
      <footer className="app-footer">
        <p className="app-disclaimer">Research analysis only — not financial advice.</p>
      </footer>
    </div>
  );
}
