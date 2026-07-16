import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="panel empty-state">
      <h1>Page not found</h1>
      <p>The page you are looking for does not exist.</p>
      <Link to="/research" className="button button-primary">
        Go to Research
      </Link>
    </div>
  );
}
