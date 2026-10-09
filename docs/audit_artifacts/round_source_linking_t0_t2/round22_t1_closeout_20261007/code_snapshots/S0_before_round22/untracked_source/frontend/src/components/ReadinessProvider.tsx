import type { ReactNode } from "react";
import { ReadinessContext, useReadinessLoader } from "../hooks/useReadiness";

/** Loads server readiness once and shares it with everything below. */
export function ReadinessProvider({ children }: { children: ReactNode }) {
  const state = useReadinessLoader();
  return <ReadinessContext.Provider value={state}>{children}</ReadinessContext.Provider>;
}
