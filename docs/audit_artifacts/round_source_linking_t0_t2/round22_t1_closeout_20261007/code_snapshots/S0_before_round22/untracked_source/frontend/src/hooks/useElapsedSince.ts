import { useEffect, useState } from "react";

/**
 * Whole-second clock: seconds of real time since `startMs` (a `Date.now()`
 * value), refreshed once a second while `active`. Used to keep the ETA and
 * the elapsed time moving between polls. It measures time only and is never
 * an input to the progress percentage.
 */
export function useElapsedSince(startMs: number | null, active: boolean): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active || startMs === null) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active, startMs]);

  return startMs === null ? 0 : Math.max(0, (now - startMs) / 1000);
}
