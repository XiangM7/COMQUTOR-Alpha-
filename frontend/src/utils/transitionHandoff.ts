import { EASE_SPRING, canAnimate, toRect, type Rect } from "./motion";

/**
 * Hand-off between the Research page and the Processing page for the
 * "Start research" transition: the ticker flies from the input into the
 * Processing heading, and the Start button turns into the progress track.
 *
 * It lives in a module variable rather than in router state on purpose:
 * router state survives a refresh or a back/forward step, which would replay
 * the animation. Here it is consumed exactly once and expires quickly, so
 * the animation only ever plays for the navigation that started a run.
 */

export interface StartGeometry {
  tickerRect: Rect;
  tickerFontPx: number;
  tickerLetterSpacingPx: number;
  buttonRect: Rect;
  buttonColor: string;
}

export interface RunHandoff {
  runId: string;
  ticker: string;
  analysisDate: string | null;
  selectedAnalysts: string[];
  /** Null when the start positions could not be measured or motion is off:
   * the Processing page still opens straight into its layout. */
  geometry: StartGeometry | null;
  createdAt: number;
}

const MAX_AGE_MS = 10_000;
const DURATION_MS = 820;

let pending: RunHandoff | null = null;

export function setRunHandoff(handoff: RunHandoff): void {
  pending = handoff;
}

function isFresh(handoff: RunHandoff | null, runId: string): handoff is RunHandoff {
  return handoff !== null && handoff.runId === runId && Date.now() - handoff.createdAt < MAX_AGE_MS;
}

/** Reads without consuming (safe to call from render). */
export function peekRunHandoff(runId: string): RunHandoff | null {
  return isFresh(pending, runId) ? pending : null;
}

/** Reads and consumes: a second call returns null. */
export function takeRunHandoff(runId: string): RunHandoff | null {
  const handoff = isFresh(pending, runId) ? pending : null;
  pending = null;
  return handoff;
}

export function clearRunHandoff(): void {
  pending = null;
}

/** Measures the ticker text and the Start button on the Research page, in
 * the state they are in right when the request is accepted. */
export function captureStartGeometry(): StartGeometry | null {
  if (typeof document === "undefined") return null;
  const ticker = document.querySelector<HTMLElement>('[data-transition="ticker"]');
  const button = document.querySelector<HTMLElement>('[data-transition="cta"]');
  if (!ticker || !button) return null;
  const tickerStyle = getComputedStyle(ticker);
  const tickerFontPx = parseFloat(tickerStyle.fontSize);
  if (!Number.isFinite(tickerFontPx) || tickerFontPx <= 0) return null;
  const spacing = parseFloat(tickerStyle.letterSpacing);
  return {
    tickerRect: toRect(ticker.getBoundingClientRect()),
    tickerFontPx,
    tickerLetterSpacingPx: Number.isFinite(spacing) ? spacing : 0,
    buttonRect: toRect(button.getBoundingClientRect()),
    buttonColor: getComputedStyle(button).backgroundColor,
  };
}

function flyTicker(geometry: StartGeometry, ticker: HTMLElement): void {
  const from = geometry.tickerRect;
  const to = ticker.getBoundingClientRect();
  const style = getComputedStyle(ticker);
  const toFontPx = parseFloat(style.fontSize);
  if (!Number.isFinite(toFontPx) || toFontPx <= 0) return;
  // Scale by the font-size ratio (both ends use line-height 1, so the boxes
  // line up) -- scaling by box height would start the text visibly larger
  // than it is in the input.
  const scale = geometry.tickerFontPx / toFontPx;
  const endSpacing = parseFloat(style.letterSpacing);
  ticker.animate(
    [
      {
        transformOrigin: "0 0",
        transform: `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${scale})`,
        // Letter-spacing is scaled with the text, so start from the spacing
        // the input had, un-scaled; otherwise the word pops wider or
        // narrower the instant it lands.
        letterSpacing: `${geometry.tickerLetterSpacingPx / scale}px`,
      },
      {
        transformOrigin: "0 0",
        transform: "none",
        letterSpacing: Number.isFinite(endSpacing) ? `${endSpacing}px` : "normal",
      },
    ],
    { duration: DURATION_MS, easing: EASE_SPRING }
  );
}

function morphButtonIntoTrack(geometry: StartGeometry, track: HTMLElement): void {
  const from = geometry.buttonRect;
  const to = toRect(track.getBoundingClientRect());
  const trackColor = getComputedStyle(track).backgroundColor;

  const overlay = document.createElement("div");
  overlay.setAttribute("aria-hidden", "true");
  Object.assign(overlay.style, {
    position: "fixed",
    left: "0",
    top: "0",
    width: "0",
    height: "0",
    opacity: "0",
    pointerEvents: "none",
    zIndex: "50",
  });
  document.body.appendChild(overlay);

  const box = (rect: Rect, radius: string, color: string) => ({
    left: `${rect.left}px`,
    top: `${rect.top}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    borderRadius: radius,
    backgroundColor: color,
  });

  // The button grows into the track in the button's own color, then turns
  // into the track's color before it fades -- so what is left behind is the
  // empty track the page really shows at 0%, not a blue bar that vanishes.
  const animation = overlay.animate(
    [
      { ...box(from, `${from.height / 2}px`, geometry.buttonColor), opacity: 1, offset: 0 },
      { ...box(to, "3px", geometry.buttonColor), opacity: 1, offset: 0.72 },
      { ...box(to, "3px", trackColor), opacity: 1, offset: 0.9 },
      { ...box(to, "3px", trackColor), opacity: 0, offset: 1 },
    ],
    { duration: DURATION_MS, easing: EASE_SPRING }
  );
  const remove = () => overlay.remove();
  animation.onfinish = remove;
  window.setTimeout(remove, DURATION_MS + 700);

  track.animate([{ opacity: 0 }, { opacity: 0, offset: 0.78 }, { opacity: 1 }], { duration: DURATION_MS });
}

/** Plays the Research -> Processing shared-element animation. Does nothing
 * without the Web Animations API or when reduced motion is requested. */
export function playRunEntrance(
  geometry: StartGeometry | null,
  targets: { ticker: HTMLElement | null; track: HTMLElement | null }
): void {
  if (!geometry || !canAnimate()) return;
  if (targets.ticker) flyTicker(geometry, targets.ticker);
  if (targets.track) morphButtonIntoTrack(geometry, targets.track);
}
