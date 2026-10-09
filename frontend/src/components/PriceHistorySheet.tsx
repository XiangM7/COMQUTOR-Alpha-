import { useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { createPortal } from "react-dom";
import { useDialogFocus } from "../hooks/useDialogFocus";
import { EASE_SPRING, canAnimate, type Rect } from "../utils/motion";
import {
  RANGES,
  buildPriceScale,
  formatChange,
  formatPrice,
  formatShortDate,
  formatTick,
  formatVolume,
  type PriceHistory,
  type RangeKey,
} from "../utils/priceHistory";
import { CandleSvg } from "./CandleSvg";

const PRICE_HEIGHT = 330;
const VOLUME_HEIGHT = 46;
const CHART_HEIGHT = PRICE_HEIGHT + VOLUME_HEIGHT;
const OPEN_MS = 560;
const CLOSE_MS = 460;

interface PriceHistorySheetProps {
  history: PriceHistory;
  /** Where the card is right now, so the sheet can grow out of it and
   * shrink back into it. Null when it cannot be measured. */
  getOriginRect: () => Rect | null;
  /** Called once the closing animation is done. */
  onClosed: () => void;
}

function transformBetween(from: Rect, to: DOMRect): string {
  return `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${from.width / to.width}, ${from.height / to.height})`;
}

/**
 * Full-size price history over the Processing page. The card it opened from
 * grows into this sheet (and the sheet shrinks back into the card on close);
 * the page behind is dimmed and blurred. Candles only run to the analysis
 * date. Keyboard: focus moves in, Tab stays inside, Esc closes, and focus
 * returns to the card.
 */
export function PriceHistorySheet({ history, getOriginRect, onClosed }: PriceHistorySheetProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  const closingRef = useRef(false);
  const [range, setRange] = useState<RangeKey>("3M");
  const [hover, setHover] = useState<number | null>(null);

  function requestClose() {
    if (closingRef.current) return;
    closingRef.current = true;
    const dialog = dialogRef.current;
    const origin = getOriginRect();
    if (!dialog || !origin || !canAnimate()) {
      onClosed();
      return;
    }
    const to = dialog.getBoundingClientRect();
    bodyRef.current?.animate([{ opacity: 1 }, { opacity: 0, offset: 0.4 }, { opacity: 0 }], { duration: CLOSE_MS, fill: "forwards" });
    backdropRef.current?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: CLOSE_MS - 40, fill: "forwards" });
    const animation = dialog.animate([{ transform: "none" }, { transform: transformBetween(origin, to) }], {
      duration: CLOSE_MS,
      easing: EASE_SPRING,
      fill: "forwards",
    });
    animation.onfinish = onClosed;
  }

  useDialogFocus(dialogRef, requestClose);

  // The card grows into the sheet.
  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    const origin = getOriginRect();
    if (!dialog || !origin || !canAnimate()) return;
    const to = dialog.getBoundingClientRect();
    dialog.animate([{ transform: transformBetween(origin, to) }, { transform: "none" }], { duration: OPEN_MS, easing: EASE_SPRING });
    bodyRef.current?.animate([{ opacity: 0 }, { opacity: 0, offset: 0.35 }, { opacity: 1 }], { duration: OPEN_MS });
    backdropRef.current?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 400, easing: "ease-out" });
    // Runs once, when the sheet mounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const days = RANGES.find((entry) => entry.key === range)?.days ?? 63;
  const candles = history.candles.slice(-days);
  const scale = buildPriceScale(candles, PRICE_HEIGHT);
  const lastIndex = candles.length - 1;
  const shownIndex = hover ?? lastIndex;
  const shown = candles[shownIndex];
  const previous = candles[shownIndex - 1] ?? shown;
  const change = shown && previous ? formatChange(shown.close, previous.close) : null;
  const labelIndexes = candles.length
    ? [0, Math.round(lastIndex / 3), Math.round((2 * lastIndex) / 3), lastIndex]
    : [];

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const box = event.currentTarget.getBoundingClientRect();
    if (box.width <= 0 || candles.length === 0) return;
    const index = Math.floor(((event.clientX - box.left) / box.width) * candles.length);
    setHover(Math.min(candles.length - 1, Math.max(0, index)));
  }

  return createPortal(
    <>
      <div ref={backdropRef} className="price-sheet-backdrop" onClick={requestClose} />
      <div
        ref={dialogRef}
        className="price-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="price-sheet-title"
        tabIndex={-1}
      >
        <div ref={bodyRef} className="price-sheet-body">
          <div className="price-sheet-header">
            <div className="price-sheet-heading">
              <h2 id="price-sheet-title">{history.ticker} price history</h2>
              {shown ? (
                <div className="price-sheet-readout">
                  <span className="price-sheet-close-price">{formatPrice(shown.close)}</span>
                  {change ? <span className={`price-change price-change-${change.direction}`}>{change.text}</span> : null}
                  <span className="price-sheet-date">
                    {hover === null ? `Close, ${formatShortDate(shown.date)}` : formatShortDate(shown.date)}
                  </span>
                </div>
              ) : null}
              {shown ? (
                <div className="price-sheet-stats">
                  <span>Open {formatPrice(shown.open)}</span>
                  <span>High {formatPrice(shown.high)}</span>
                  <span>Low {formatPrice(shown.low)}</span>
                  <span>Volume {formatVolume(shown.volume)}</span>
                </div>
              ) : null}
            </div>
            <div className="price-sheet-controls">
              <div className="segmented" role="group" aria-label="Range">
                {RANGES.map((entry) => (
                  <button
                    key={entry.key}
                    type="button"
                    className="segmented-option"
                    aria-pressed={range === entry.key}
                    onClick={() => {
                      setRange(entry.key);
                      setHover(null);
                    }}
                  >
                    {entry.key}
                  </button>
                ))}
              </div>
              <button type="button" className="icon-button" data-autofocus aria-label="Close price history" onClick={requestClose}>
                <svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                  <path d="M2 2l8 8M10 2l-8 8" />
                </svg>
              </button>
            </div>
          </div>

          <div className="price-chart-row">
            <div
              className="price-chart"
              style={{ height: CHART_HEIGHT + 24 }}
              onPointerMove={handlePointerMove}
              onPointerLeave={() => setHover(null)}
            >
              <CandleSvg
                candles={candles}
                priceHeight={PRICE_HEIGHT}
                volumeHeight={VOLUME_HEIGHT}
                scale={scale}
                showGrid
                activeIndex={hover}
              />
              <div className="price-chart-asof" aria-hidden="true" style={{ height: PRICE_HEIGHT }} />
              <span className="price-chart-asof-label">Analysis date</span>
              {hover !== null ? (
                <div
                  className="price-chart-cross"
                  aria-hidden="true"
                  style={{ height: CHART_HEIGHT, left: `${((hover + 0.5) / candles.length) * 100}%` }}
                />
              ) : null}
              <div className="price-chart-xlabels" style={{ top: CHART_HEIGHT + 6 }} aria-hidden="true">
                {labelIndexes.map((index) => (
                  <span key={index}>{candles[index] ? formatShortDate(candles[index].date) : ""}</span>
                ))}
              </div>
            </div>
            <div className="price-chart-yaxis" aria-hidden="true" style={{ height: PRICE_HEIGHT }}>
              {scale.ticks.map((tick) => (
                <span key={tick} style={{ top: scale.y(tick) - 7 }}>
                  {formatTick(tick)}
                </span>
              ))}
            </div>
          </div>

          <p className="price-sheet-note">
            Daily candles through the analysis date, so nothing after it can influence the read.
            {history.isSample ? " Sample data, not real prices." : ""}
          </p>
        </div>
      </div>
    </>,
    document.body
  );
}
