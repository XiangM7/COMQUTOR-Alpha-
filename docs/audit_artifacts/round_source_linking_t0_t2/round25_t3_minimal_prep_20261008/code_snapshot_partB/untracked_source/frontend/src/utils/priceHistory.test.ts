import { afterEach, describe, expect, it, vi } from "vitest";
import {
  RANGES,
  buildPriceScale,
  formatChange,
  formatShortDate,
  formatTick,
  isSamplePriceHistoryEnabled,
  makeSamplePriceHistory,
} from "./priceHistory";

describe("makeSamplePriceHistory", () => {
  it("is marked as sample data", () => {
    expect(makeSamplePriceHistory("NVDA", "2026-10-07").isSample).toBe(true);
  });

  it("produces six months of weekday candles", () => {
    const history = makeSamplePriceHistory("NVDA", "2026-10-07");
    expect(history.candles).toHaveLength(Math.max(...RANGES.map((range) => range.days)));
    for (const candle of history.candles) {
      const [year, month, day] = candle.date.split("-").map(Number);
      const weekday = new Date(year!, month! - 1, day).getDay();
      expect([0, 6]).not.toContain(weekday);
    }
  });

  it("never runs past the analysis date, so nothing after it can leak in", () => {
    // 2026-10-10 is a Saturday: the series must stop on Friday the 9th.
    const history = makeSamplePriceHistory("NVDA", "2026-10-10");
    expect(history.asOf).toBe("2026-10-09");
    expect(history.candles.at(-1)?.date).toBe("2026-10-09");
    expect(history.candles.every((candle) => candle.date <= "2026-10-10")).toBe(true);
    const wednesday = makeSamplePriceHistory("NVDA", "2026-10-07");
    expect(wednesday.candles.at(-1)?.date).toBe("2026-10-07");
  });

  it("is ordered oldest first with strictly increasing dates", () => {
    const dates = makeSamplePriceHistory("NVDA", "2026-10-07").candles.map((candle) => candle.date);
    expect([...dates].sort()).toEqual(dates);
    expect(new Set(dates).size).toBe(dates.length);
  });

  it("is deterministic per ticker and different between tickers", () => {
    const a = makeSamplePriceHistory("NVDA", "2026-10-07");
    expect(makeSamplePriceHistory("NVDA", "2026-10-07")).toEqual(a);
    expect(makeSamplePriceHistory("AMD", "2026-10-07").candles[0]?.open).not.toBe(a.candles[0]?.open);
  });

  it("keeps every candle internally consistent", () => {
    for (const candle of makeSamplePriceHistory("NVDA", "2026-10-07").candles) {
      expect(candle.high).toBeGreaterThanOrEqual(Math.max(candle.open, candle.close));
      expect(candle.low).toBeLessThanOrEqual(Math.min(candle.open, candle.close));
      expect(candle.volume).toBeGreaterThan(0);
    }
  });
});

describe("isSamplePriceHistoryEnabled", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("is off unless explicitly switched on", () => {
    expect(isSamplePriceHistoryEnabled()).toBe(false);
    vi.stubEnv("VITE_SAMPLE_PRICE_HISTORY", "0");
    expect(isSamplePriceHistoryEnabled()).toBe(false);
    vi.stubEnv("VITE_SAMPLE_PRICE_HISTORY", "1");
    expect(isSamplePriceHistoryEnabled()).toBe(true);
  });
});

describe("buildPriceScale", () => {
  const candles = makeSamplePriceHistory("NVDA", "2026-10-07").candles;

  it("maps higher prices higher up, inside the padded area", () => {
    const scale = buildPriceScale(candles, 330);
    const high = Math.max(...candles.map((candle) => candle.high));
    const low = Math.min(...candles.map((candle) => candle.low));
    expect(scale.y(high)).toBeLessThan(scale.y(low));
    expect(scale.y(high)).toBeGreaterThanOrEqual(8);
    expect(scale.y(low)).toBeLessThanOrEqual(330 - 8);
  });

  it("puts gridlines on round values that bracket the data", () => {
    const scale = buildPriceScale(candles, 330);
    const high = Math.max(...candles.map((candle) => candle.high));
    const low = Math.min(...candles.map((candle) => candle.low));
    expect(scale.ticks.length).toBeGreaterThanOrEqual(2);
    expect(scale.ticks[0]).toBeLessThanOrEqual(low);
    expect(scale.ticks.at(-1)).toBeGreaterThanOrEqual(high);
  });

  it("survives an empty or flat series", () => {
    expect(buildPriceScale([], 100).ticks).toEqual([]);
    const flat = [{ date: "2026-10-07", open: 10, high: 10, low: 10, close: 10, volume: 1 }];
    expect(buildPriceScale(flat, 100).y(10)).toBe(50);
  });
});

describe("formatting", () => {
  it("formats a change with a real minus sign", () => {
    expect(formatChange(103.21, 100)).toEqual({ text: "+3.21 (+3.21%)", direction: "up" });
    expect(formatChange(95, 100)).toEqual({ text: "−5.00 (−5.00%)", direction: "down" });
    expect(formatChange(100, 100)).toEqual({ text: "0.00 (0.00%)", direction: "flat" });
  });

  it("does not divide by zero", () => {
    expect(formatChange(5, 0).text).toBe("+5.00 (+0.00%)");
  });

  it("formats dates and ticks", () => {
    expect(formatShortDate("2026-10-07")).toBe("Oct 7");
    expect(formatTick(180)).toBe("180");
    expect(formatTick(2.5)).toBe("2.5");
  });
});
