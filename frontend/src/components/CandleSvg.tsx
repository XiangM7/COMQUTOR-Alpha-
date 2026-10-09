import { buildPriceScale, type Candle, type PriceScale } from "../utils/priceHistory";

const VIEW_WIDTH = 1000;

interface CandleSvgProps {
  candles: Candle[];
  /** Height of the price area in px. */
  priceHeight: number;
  /** Extra height below the price area for volume bars; 0 for none. */
  volumeHeight?: number;
  scale?: PriceScale;
  showGrid?: boolean;
  activeIndex?: number | null;
}

/**
 * Daily candles as plain SVG shapes. Up days are hollow green, down days are
 * solid red (shape differs, not just color). It stretches to the width of its
 * container; strokes stay 1px thanks to non-scaling strokes.
 */
export function CandleSvg({ candles, priceHeight, volumeHeight = 0, scale, showGrid = false, activeIndex = null }: CandleSvgProps) {
  const priceScale = scale ?? buildPriceScale(candles, priceHeight);
  const slot = VIEW_WIDTH / Math.max(1, candles.length);
  const totalHeight = priceHeight + volumeHeight;

  return (
    <svg
      className="candle-svg"
      viewBox={`0 0 ${VIEW_WIDTH} ${totalHeight}`}
      preserveAspectRatio="none"
      width="100%"
      height={totalHeight}
      aria-hidden="true"
      focusable="false"
    >
      {showGrid
        ? priceScale.ticks.map((tick) => (
            <line
              key={tick}
              className="candle-grid"
              x1={0}
              x2={VIEW_WIDTH}
              y1={priceScale.y(tick)}
              y2={priceScale.y(tick)}
              vectorEffect="non-scaling-stroke"
            />
          ))
        : null}
      {candles.map((candle, index) => {
        const up = candle.close >= candle.open;
        const center = (index + 0.5) * slot;
        const bodyWidth = slot * 0.64;
        const bodyTop = priceScale.y(Math.max(candle.open, candle.close));
        const bodyHeight = Math.max(1, Math.abs(priceScale.y(candle.open) - priceScale.y(candle.close)));
        const direction = up ? "up" : "down";
        const volumeBarHeight =
          volumeHeight > 0 && priceScale.maxVolume > 0 ? Math.max(1, (candle.volume / priceScale.maxVolume) * (volumeHeight - 2)) : 0;
        return (
          <g key={candle.date}>
            {volumeBarHeight > 0 ? (
              <rect
                className={index === activeIndex ? "candle-volume candle-volume-active" : "candle-volume"}
                x={center - bodyWidth / 2}
                y={totalHeight - volumeBarHeight}
                width={bodyWidth}
                height={volumeBarHeight}
              />
            ) : null}
            <line
              className={`candle-wick candle-wick-${direction}`}
              x1={center}
              x2={center}
              y1={priceScale.y(candle.high)}
              y2={priceScale.y(candle.low)}
              vectorEffect="non-scaling-stroke"
            />
            <rect
              className={`candle-body candle-body-${direction}`}
              x={center - bodyWidth / 2}
              y={bodyTop}
              width={bodyWidth}
              height={bodyHeight}
              vectorEffect="non-scaling-stroke"
            />
          </g>
        );
      })}
    </svg>
  );
}
