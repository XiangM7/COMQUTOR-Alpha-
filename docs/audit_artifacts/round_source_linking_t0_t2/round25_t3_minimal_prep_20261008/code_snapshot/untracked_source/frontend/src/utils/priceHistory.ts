/** One trading day. `volume` is in millions of shares. */
export interface Candle {
  /** YYYY-MM-DD */
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface PriceHistory {
  ticker: string;
  /** Analysis date, YYYY-MM-DD. The series never runs past it, so nothing
   * after the analysis date can influence how the chart reads. */
  asOf: string;
  /** True for made-up demo prices, which are always labelled as such. */
  isSample: boolean;
  /** Oldest first. */
  candles: Candle[];
}

export const RANGES = [
  { key: "1M", days: 22 },
  { key: "3M", days: 63 },
  { key: "6M", days: 126 },
] as const;
export type RangeKey = (typeof RANGES)[number]["key"];

/** Sample prices are a development aid only: off unless explicitly enabled,
 * so no made-up price can reach a real user. */
export function isSamplePriceHistoryEnabled(): boolean {
  return import.meta.env.VITE_SAMPLE_PRICE_HISTORY === "1";
}

function toIsoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function parseIsoDate(value: string | null): Date {
  const match = value ? /^(\d{4})-(\d{2})-(\d{2})$/.exec(value) : null;
  if (!match) return new Date();
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

function hashTicker(ticker: string): number {
  let hash = 7;
  for (const char of ticker) hash = (hash * 31 + char.charCodeAt(0)) % 2147483646;
  return hash + 1;
}

/** Deterministic made-up daily candles ending on the last weekday on or
 * before `asOf`. Never real prices. */
export function makeSamplePriceHistory(ticker: string, asOf: string | null): PriceHistory {
  let seed = hashTicker(ticker);
  const random = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };

  const days: Date[] = [];
  const cursor = parseIsoDate(asOf);
  const total = Math.max(...RANGES.map((range) => range.days));
  while (days.length < total) {
    const weekday = cursor.getDay();
    if (weekday !== 0 && weekday !== 6) days.unshift(new Date(cursor));
    cursor.setDate(cursor.getDate() - 1);
  }

  let close = 60 + (hashTicker(ticker) % 300);
  const candles = days.map((day): Candle => {
    const open = close * (1 + (random() - 0.5) * 0.012);
    close = open * (1 + (random() - 0.47) * 0.034);
    const high = Math.max(open, close) * (1 + random() * 0.012);
    const low = Math.min(open, close) * (1 - random() * 0.012);
    const volume = 180 + random() * 160 + Math.abs(close - open) * 18;
    return { date: toIsoDate(day), open, high, low, close, volume };
  });

  const last = candles[candles.length - 1];
  return { ticker, asOf: last ? last.date : toIsoDate(parseIsoDate(asOf)), isSample: true, candles };
}

export interface PriceScale {
  y: (value: number) => number;
  ticks: number[];
  maxVolume: number;
}

/** Vertical scale for `height` px with 8px of padding and "nice" gridlines. */
export function buildPriceScale(candles: Candle[], height: number): PriceScale {
  let low = Infinity;
  let high = -Infinity;
  let maxVolume = 0;
  for (const candle of candles) {
    low = Math.min(low, candle.low);
    high = Math.max(high, candle.high);
    maxVolume = Math.max(maxVolume, candle.volume);
  }
  if (!Number.isFinite(low) || !Number.isFinite(high) || high === low) {
    return { y: () => height / 2, ticks: [], maxVolume };
  }
  const magnitude = Math.pow(10, Math.floor(Math.log10((high - low) / 3)));
  const step =
    [1, 2, 2.5, 5, 10].map((multiple) => multiple * magnitude).find((candidate) => (high - low) / candidate <= 4) ??
    magnitude * 10;
  const top = Math.ceil(high / step) * step;
  const bottom = Math.floor(low / step) * step;
  const ticks: number[] = [];
  for (let value = bottom; value <= top + 1e-9; value += step) ticks.push(value);
  return {
    y: (value) => 8 + ((top - value) / (top - bottom)) * (height - 16),
    ticks,
    maxVolume,
  };
}

export function formatPrice(value: number): string {
  return value.toFixed(2);
}

export function formatTick(value: number): string {
  return Math.abs(value) >= 10 ? value.toFixed(0) : value.toFixed(1);
}

export function formatVolume(millions: number): string {
  return `${Math.round(millions)}M`;
}

export function formatShortDate(iso: string): string {
  return parseIsoDate(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export interface Change {
  text: string;
  direction: "up" | "down" | "flat";
}

/** "+3.21 (+2.10%)" from `from` to `to`, with a real minus sign. */
export function formatChange(to: number, from: number): Change {
  const delta = to - from;
  const direction = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "";
  const percent = from === 0 ? 0 : (delta / from) * 100;
  return { text: `${sign}${Math.abs(delta).toFixed(2)} (${sign}${Math.abs(percent).toFixed(2)}%)`, direction };
}
