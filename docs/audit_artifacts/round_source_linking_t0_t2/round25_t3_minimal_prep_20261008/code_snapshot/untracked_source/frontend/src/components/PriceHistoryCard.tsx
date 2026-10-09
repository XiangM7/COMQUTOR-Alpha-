import { useRef, useState } from "react";
import { toRect } from "../utils/motion";
import { RANGES, buildPriceScale, formatChange, formatPrice, type PriceHistory } from "../utils/priceHistory";
import { CandleSvg } from "./CandleSvg";
import { PriceHistorySheet } from "./PriceHistorySheet";

const MINI_HEIGHT = 128;
const MINI_DAYS = RANGES.find((entry) => entry.key === "3M")?.days ?? 63;

/**
 * Compact "Price history, 3 months" card. The whole card is one button: it
 * opens the full chart, which grows out of the card.
 */
export function PriceHistoryCard({ history }: { history: PriceHistory }) {
  const [open, setOpen] = useState(false);
  const cardRef = useRef<HTMLButtonElement>(null);

  const candles = history.candles.slice(-MINI_DAYS);
  const first = candles[0];
  const last = candles[candles.length - 1];
  if (!first || !last) return null;
  const change = formatChange(last.close, first.open);
  const scale = buildPriceScale(candles, MINI_HEIGHT);

  return (
    <>
      <button
        ref={cardRef}
        type="button"
        className={open ? "price-card price-card-hidden" : "price-card"}
        aria-haspopup="dialog"
        aria-label={`Open ${history.ticker} price history`}
        onClick={() => setOpen(true)}
      >
        <span className="price-card-top">
          <span className="price-card-heading">
            <span className="price-card-title">
              Price history, 3 months{history.isSample ? " · Sample data" : ""}
            </span>
            <span className="price-card-figures">
              <span className="price-card-last">{formatPrice(last.close)}</span>
              <span className={`price-change price-change-${change.direction}`}>{change.text} over 3 months</span>
            </span>
          </span>
          <span className="price-card-expand" aria-hidden="true">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7.5 1.5h3v3M4.5 10.5h-3v-3M10.5 1.5 7 5M1.5 10.5 5 7" />
            </svg>
          </span>
        </span>
        <span className="price-card-chart">
          <CandleSvg candles={candles} priceHeight={MINI_HEIGHT} scale={scale} />
        </span>
      </button>
      {open ? (
        <PriceHistorySheet
          history={history}
          getOriginRect={() => (cardRef.current ? toRect(cardRef.current.getBoundingClientRect()) : null)}
          onClosed={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}
