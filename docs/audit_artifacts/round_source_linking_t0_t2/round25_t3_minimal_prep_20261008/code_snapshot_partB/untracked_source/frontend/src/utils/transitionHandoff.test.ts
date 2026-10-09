import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  captureStartGeometry,
  clearRunHandoff,
  peekRunHandoff,
  playRunEntrance,
  setRunHandoff,
  takeRunHandoff,
  type RunHandoff,
  type StartGeometry,
} from "./transitionHandoff";

function handoff(overrides: Partial<RunHandoff> = {}): RunHandoff {
  return {
    runId: "run-1",
    ticker: "NVDA",
    analysisDate: "2026-10-07",
    selectedAnalysts: ["market"],
    geometry: null,
    createdAt: Date.now(),
    ...overrides,
  };
}

describe("run hand-off store", () => {
  beforeEach(() => clearRunHandoff());
  afterEach(() => {
    vi.useRealTimers();
    clearRunHandoff();
  });

  it("can be read without being consumed", () => {
    setRunHandoff(handoff());
    expect(peekRunHandoff("run-1")?.ticker).toBe("NVDA");
    expect(peekRunHandoff("run-1")?.ticker).toBe("NVDA");
  });

  it("is consumed exactly once", () => {
    setRunHandoff(handoff());
    expect(takeRunHandoff("run-1")?.ticker).toBe("NVDA");
    expect(takeRunHandoff("run-1")).toBeNull();
    expect(peekRunHandoff("run-1")).toBeNull();
  });

  it("is only for the run it was made for", () => {
    setRunHandoff(handoff({ runId: "run-1" }));
    expect(peekRunHandoff("run-2")).toBeNull();
    expect(takeRunHandoff("run-2")).toBeNull();
    // A wrong-run visit also clears it: it must not wait around for later.
    expect(peekRunHandoff("run-1")).toBeNull();
  });

  it("expires, so a stale hand-off can never replay the animation later", () => {
    vi.useFakeTimers();
    setRunHandoff(handoff({ createdAt: Date.now() }));
    vi.advanceTimersByTime(11_000);
    expect(peekRunHandoff("run-1")).toBeNull();
    expect(takeRunHandoff("run-1")).toBeNull();
  });
});

describe("captureStartGeometry", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("returns null when the Research page elements are not there", () => {
    expect(captureStartGeometry()).toBeNull();
  });

  it("measures the ticker text and the Start button", () => {
    document.body.innerHTML = `
      <span data-transition="ticker" style="font-size: 32px; letter-spacing: -0.64px">NVDA</span>
      <button data-transition="cta" style="background-color: rgb(0, 113, 227)">Starting…</button>`;
    const ticker = document.querySelector<HTMLElement>('[data-transition="ticker"]')!;
    const button = document.querySelector<HTMLElement>('[data-transition="cta"]')!;
    ticker.getBoundingClientRect = () => new DOMRect(425, 448, 83, 32);
    button.getBoundingClientRect = () => new DOMRect(890, 517, 150, 44);

    expect(captureStartGeometry()).toEqual({
      tickerRect: { left: 425, top: 448, width: 83, height: 32 },
      tickerFontPx: 32,
      tickerLetterSpacingPx: -0.64,
      buttonRect: { left: 890, top: 517, width: 150, height: 44 },
      buttonColor: "rgb(0, 113, 227)",
    });
  });
});

describe("playRunEntrance", () => {
  const geometry: StartGeometry = {
    tickerRect: { left: 425, top: 448, width: 83, height: 32 },
    tickerFontPx: 32,
    tickerLetterSpacingPx: -0.64,
    buttonRect: { left: 890, top: 517, width: 150, height: 44 },
    buttonColor: "rgb(0, 113, 227)",
  };
  const originalAnimate = Element.prototype.animate;

  afterEach(() => {
    Element.prototype.animate = originalAnimate;
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  function mount() {
    document.body.innerHTML = `
      <span id="ticker" style="font-size: 56px; letter-spacing: -1.96px">NVDA</span>
      <div id="track" style="background-color: rgb(232, 232, 237)"></div>`;
    const ticker = document.getElementById("ticker")!;
    const track = document.getElementById("track")!;
    ticker.getBoundingClientRect = () => new DOMRect(184, 118, 145, 56);
    track.getBoundingClientRect = () => new DOMRect(184, 270, 795, 6);
    return { ticker, track };
  }

  it("does nothing where the Web Animations API is unavailable (jsdom)", () => {
    const { ticker, track } = mount();
    expect(() => playRunEntrance(geometry, { ticker, track })).not.toThrow();
  });

  it("does nothing without start positions", () => {
    const animate = vi.fn();
    Element.prototype.animate = animate as unknown as typeof Element.prototype.animate;
    const { ticker, track } = mount();
    playRunEntrance(null, { ticker, track });
    expect(animate).not.toHaveBeenCalled();
  });

  it("flies the ticker by font-size ratio and un-scales its letter-spacing", () => {
    const animate = vi.fn(() => ({}) as Animation);
    Element.prototype.animate = animate as unknown as typeof Element.prototype.animate;
    const { ticker } = mount();

    playRunEntrance(geometry, { ticker, track: null });

    expect(animate).toHaveBeenCalledTimes(1);
    const [keyframes] = animate.mock.calls[0] as unknown as [Keyframe[]];
    const scale = 32 / 56;
    expect(keyframes[0]?.transform).toBe(`translate(${425 - 184}px, ${448 - 118}px) scale(${scale})`);
    expect(keyframes[1]?.transform).toBe("none");
    // -0.64px at the input, scaled up by 1/scale at the heading's size.
    expect(parseFloat(String(keyframes[0]?.letterSpacing))).toBeCloseTo(-0.64 / scale, 5);
    expect(keyframes[1]?.letterSpacing).toBe("-1.96px");
  });

  it("turns the button into the track, ending in the track's own color", () => {
    const overlayAnimate = vi.fn(() => ({}) as Animation);
    const trackAnimate = vi.fn(() => ({}) as Animation);
    Element.prototype.animate = function (this: Element, ...args: unknown[]) {
      return (this.id === "track" ? trackAnimate : overlayAnimate)(...(args as [])) as Animation;
    } as unknown as typeof Element.prototype.animate;
    const { track } = mount();

    playRunEntrance(geometry, { ticker: null, track });

    const [overlayFrames] = overlayAnimate.mock.calls[0] as unknown as [Keyframe[]];
    expect(overlayFrames[0]).toMatchObject({ left: "890px", top: "517px", width: "150px", height: "44px", backgroundColor: "rgb(0, 113, 227)" });
    expect(overlayFrames[1]).toMatchObject({ left: "184px", top: "270px", width: "795px", height: "6px", backgroundColor: "rgb(0, 113, 227)" });
    const last = overlayFrames[overlayFrames.length - 1];
    expect(last).toMatchObject({ backgroundColor: "rgb(232, 232, 237)", opacity: 0 });
    // The real track fades in underneath.
    expect(trackAnimate).toHaveBeenCalledTimes(1);
  });
});
