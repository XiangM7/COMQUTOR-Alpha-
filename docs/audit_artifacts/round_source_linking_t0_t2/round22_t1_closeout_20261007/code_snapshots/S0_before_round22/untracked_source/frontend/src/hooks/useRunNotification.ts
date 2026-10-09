import { useCallback, useEffect, useRef, useState } from "react";

export type NotificationPermissionState = "unsupported" | "default" | "granted" | "denied";

function currentPermission(): NotificationPermissionState {
  if (typeof Notification === "undefined") return "unsupported";
  return Notification.permission;
}

function pageIsInBackground(): boolean {
  if (typeof document === "undefined") return false;
  return document.visibilityState === "hidden" || !document.hasFocus();
}

const TERMINAL_COPY: Record<string, (ticker: string) => { title: string; body: string }> = {
  completed: (ticker) => ({ title: `${ticker} research is ready`, body: "The claims and evidence are ready to review." }),
  partial: (ticker) => ({ title: `${ticker} research finished partially`, body: "Some stages did not produce results." }),
  failed: (ticker) => ({ title: `${ticker} research did not finish`, body: "Open the run to see what happened." }),
};

export interface RunNotification {
  permission: NotificationPermissionState;
  /** Asks the browser for permission. Must be called from a click. */
  enable: () => void;
}

/**
 * Optional "notify me when it's done" for one run: a system notification
 * (top right on macOS) when the run reaches a final status while this tab is
 * in the background. It only ever fires for a run seen going from in
 * progress to finished -- opening an already-finished run stays silent --
 * and only after the user allowed notifications themselves. It works while
 * the page stays open; closing the page ends it.
 */
export function useRunNotification(runId: string | undefined, ticker: string | undefined, status: string | undefined): RunNotification {
  const [permission, setPermission] = useState<NotificationPermissionState>(currentPermission);
  const sawActiveRef = useRef(false);
  const notifiedRef = useRef(false);

  useEffect(() => {
    sawActiveRef.current = false;
    notifiedRef.current = false;
  }, [runId]);

  useEffect(() => {
    if (status === "queued" || status === "running") {
      sawActiveRef.current = true;
      return;
    }
    const copy = status ? TERMINAL_COPY[status] : undefined;
    if (!copy || !ticker || !runId) return;
    if (!sawActiveRef.current || notifiedRef.current) return;
    notifiedRef.current = true;
    if (currentPermission() !== "granted" || !pageIsInBackground()) return;
    const { title, body } = copy(ticker);
    const notification = new Notification(title, { body, tag: runId });
    notification.onclick = () => {
      window.focus();
      notification.close();
    };
  }, [status, ticker, runId]);

  const enable = useCallback(() => {
    if (typeof Notification === "undefined") return;
    void Notification.requestPermission().then((result) => setPermission(result));
  }, []);

  return { permission, enable };
}
