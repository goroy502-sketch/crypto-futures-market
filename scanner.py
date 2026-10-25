
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://public.coindcx.com/market_data"
OUTPUT_FILE = "docs/signals.csv"


def get_json(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CryptoFuturesScanner/1.0"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def ema(values, period):
    if len(values) < period:
        return None

    alpha = 2 / (period + 1)
    result = sum(values[:period]) / period

    for value in values[period:]:
        result = value * alpha + result * (1 - alpha)

    return result


def rsi(closes, period=14):
    if len(closes) <= period:
        return None

    changes = [
        closes[i] - closes[i - 1]
        for i in range(len(closes) - period, len(closes))
    ]

    gains = sum(max(change, 0) for change in changes) / period
    losses = sum(max(-change, 0) for change in changes) / period

    if losses == 0:
        return 100.0

    return 100 - 100 / (1 + gains / losses)


def main():
    url = BASE_URL + "/v3/current_prices/futures/rt"
    payload = get_json(url)

    prices = payload.get("prices", payload)
    if not isinstance(prices, dict):
        raise RuntimeError("Unexpected CoinDCX prices response")

    pairs = []

    for symbol, item in prices.items():
        if not symbol.endswith("_USDT"):
            continue

        if isinstance(item, dict):
            price = item.get("ls") or item.get("p") or item.get("v")
        else:
            price = item

        try:
            price = float(price)
        except (TypeError, ValueError):
            continue

        if price > 0:
            pairs.append((symbol, price))

    print("Total USDT pairs found:", len(pairs))
print("Pairs to scan:", len(pairs))
    updated = datetime.now(timezone.utc).isoformat()

    # Start with 20 USDT futures pairs; we can expand after testing.
    for symbol, live_price in pairs:
        try:
            now = int(time.time())
            params = urllib.parse.urlencode({
                "pair": symbol,
                "from": now - 3 * 86400,
                "to": now,
                "resolution": "5",
                "pcode": "f"
            })

            candle_url = (
                BASE_URL + "/candlesticks?" + params
            )
            result = get_json(candle_url)
            candles = result.get("data", [])

            closes = []
            volumes = []

            for candle in candles:
                close = candle.get("close")
                volume = candle.get("volume", 0)

                if close is not None:
                    closes.append(float(close))
                    volumes.append(float(volume or 0))

            if len(closes) < 30:
                continue

            # RSI and EMA are calculated from available 5-minute closes.
            # Full 15-minute candle aggregation will be added after API testing.
            rsi_value = rsi(closes)
            ema9 = ema(closes, 9)
            ema21 = ema(closes, 21)

            if ema9 is not None and ema21 is not None and ema9 > ema21:
                signal = "BULLISH"
            elif ema9 is not None and ema21 is not None and ema9 < ema21:
                signal = "BEARISH"
            else:
                signal = "NEUTRAL"

            rows.append({
                "symbol": symbol,
                "price": live_price,
                "signal": signal,
                "rsi": round(rsi_value, 2) if rsi_value is not None else "",
                "adx": "",
                "macd": "",
                "macdSignal": "",
                "emaTrend": signal,
                "volume": round(volumes[-1], 4) if volumes else "",
                "updatedAt": updated
            })

            print("Scanned:", symbol, signal)
            time.sleep(0.15)

        except Exception as error:
            print("Skipped", symbol, "-", error)

    if not rows:
        raise RuntimeError(
            "No pairs scanned successfully; check API response and pair format."
        )

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print("Saved", len(rows), "rows to", OUTPUT_FILE)


if __name__ == "__main__":
    main()
