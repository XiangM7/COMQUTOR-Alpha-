import { useMemo } from "react";
import { isSamplePriceHistoryEnabled, makeSamplePriceHistory, type PriceHistory } from "../utils/priceHistory";

/**
 * Daily price history for the Processing page's chart, or null when there is
 * none -- the chart card then simply is not shown.
 *
 * The backend has no price-history endpoint yet, so today the only source is
 * a clearly labelled sample series, available only when the frontend is
 * started with VITE_SAMPLE_PRICE_HISTORY=1 (a development aid). When the
 * endpoint exists, fetch it here (only candles up to the analysis date) and
 * return the same PriceHistory shape; nothing else needs to change.
 */
export function usePriceHistory(ticker: string | undefined, analysisDate: string | null | undefined): PriceHistory | null {
  return useMemo(() => {
    if (!ticker || !isSamplePriceHistoryEnabled()) return null;
    return makeSamplePriceHistory(ticker, analysisDate ?? null);
  }, [ticker, analysisDate]);
}
