import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRunNotification } from "./useRunNotification";

type FakeNotificationInstance = { title: string; options?: NotificationOptions; onclick: null | (() => void); close: () => void };

function stubNotification(permission: NotificationPermission) {
  const created: FakeNotificationInstance[] = [];
  const requestPermission = vi.fn().mockResolvedValue("granted");
  class FakeNotification {
    static permission = permission;
    static requestPermission = requestPermission;
    onclick: null | (() => void) = null;
    close = vi.fn();
    constructor(
      public title: string,
      public options?: NotificationOptions
    ) {
      created.push(this);
    }
  }
  vi.stubGlobal("Notification", FakeNotification);
  return { created, requestPermission };
}

function setBackground(background: boolean) {
  vi.spyOn(document, "visibilityState", "get").mockReturnValue(background ? "hidden" : "visible");
  vi.spyOn(document, "hasFocus").mockReturnValue(!background);
}

describe("useRunNotification", () => {
  beforeEach(() => setBackground(true));
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function run(initial: string) {
    return renderHook(({ status }) => useRunNotification("run-1", "NVDA", status), { initialProps: { status: initial } });
  }

  it("notifies once when a run seen in progress finishes while the tab is in the background", () => {
    const { created } = stubNotification("granted");
    const hook = run("running");
    hook.rerender({ status: "completed" });
    hook.rerender({ status: "completed" });

    expect(created).toHaveLength(1);
    expect(created[0]?.title).toBe("NVDA research is ready");
    expect(created[0]?.options?.tag).toBe("run-1");
  });

  it("has its own wording for a partial and a failed run", () => {
    const partial = stubNotification("granted");
    run("running").rerender({ status: "partial" });
    expect(partial.created[0]?.title).toBe("NVDA research finished partially");

    const failed = stubNotification("granted");
    run("queued").rerender({ status: "failed" });
    expect(failed.created[0]?.title).toBe("NVDA research did not finish");
  });

  it("stays silent when the user is looking at the tab", () => {
    setBackground(false);
    const { created } = stubNotification("granted");
    run("running").rerender({ status: "completed" });
    expect(created).toHaveLength(0);
  });

  it("stays silent for a run that was already finished when the page opened", () => {
    const { created } = stubNotification("granted");
    run("completed");
    expect(created).toHaveLength(0);
  });

  it("stays silent unless notifications were allowed", () => {
    const { created } = stubNotification("default");
    run("running").rerender({ status: "completed" });
    expect(created).toHaveLength(0);

    const denied = stubNotification("denied");
    run("running").rerender({ status: "completed" });
    expect(denied.created).toHaveLength(0);
  });

  it("brings the tab forward when the notification is clicked", () => {
    const { created } = stubNotification("granted");
    const focus = vi.spyOn(window, "focus").mockImplementation(() => undefined);
    run("running").rerender({ status: "completed" });

    created[0]?.onclick?.();

    expect(focus).toHaveBeenCalled();
    expect(created[0]?.close).toHaveBeenCalled();
  });

  it("reports the browser's permission and asks only when enable() is called", async () => {
    const { requestPermission } = stubNotification("default");
    const hook = run("running");
    expect(hook.result.current.permission).toBe("default");
    expect(requestPermission).not.toHaveBeenCalled();

    await act(async () => {
      hook.result.current.enable();
    });

    expect(requestPermission).toHaveBeenCalledTimes(1);
    expect(hook.result.current.permission).toBe("granted");
  });

  it("reports unsupported where the browser has no Notification API", () => {
    vi.stubGlobal("Notification", undefined);
    const hook = run("running");
    expect(hook.result.current.permission).toBe("unsupported");
    expect(() => hook.result.current.enable()).not.toThrow();
  });
});
