
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://public.coindcx.com/market_data"
OUT = Path("docs/signals.csv")
HEADERS = [
    "symbol", "price", "signal", "rsi", "adx",
    "macd", "macdSignal", "emaTrend", "volume",
    "updatedAt", "bbUpper", "bbLower", "atr",
    "volumeBreakout", "timeframe"
]


def get_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "CryptoFuturesScanner/2.0"}
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def ema(values, period):
    if len(values) < period:
        return []
    alpha = 2 / (period + 1)
    result = sum(values[:period]) / period
    output = [None] * (period - 1) + [result]
    for value in values[period:]:
        result = value * alpha + result * (1 - alpha)
        output.append(result)
    return output


def rsi(values, period=14):
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1]
               for i in range(1, len(values))]
    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def macd(values):
    fast = ema(values, 12)
    slow = ema(values, 26)
    if not fast or not slow:
        return None, None, None
    line = [a - b for a, b in zip(fast, slow)]
    signal_line = ema(line, 9)
    if not signal_line:
        return None, None, None
    return line[-1], signal_line[-1], (line[-2], signal_line[-2])


def adx(candles, period=14):
    if len(candles) < period * 2 + 1:
        return None
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(candles)):
        prev, cur = candles[i - 1], candles[i]
        up = cur["high"] - prev["high"]
        down = prev["low"] - cur["low"]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
        trs.append(max(
            cur["high"] - cur["low"],
            abs(cur["high"] - prev["close"]),
            abs(cur["low"] - prev["close"])
        ))

    dx_values = []
    for i in range(period - 1, len(trs)):
        tr_sum = sum(trs[i - period + 1:i + 1])
        if tr_sum == 0:
            dx_values.append(0)
            continue
        pdi = 100 * sum(plus_dm[i - period + 1:i + 1]) / tr_sum
        mdi = 100 * sum(minus_dm[i - period + 1:i + 1]) / tr_sum
        denom = pdi + mdi
        dx_values.append(100 * abs(pdi - mdi) / denom if denom else 0)

    if len(dx_values) < period:
        return None
    value = sum(dx_values[:period]) / period
    for dx in dx_values[period:]:
        value = (value * (period - 1) + dx) / period
    return value


def make_15m_candles(raw):
    buckets = {}
    now_ms = int(time.time() * 1000)
    current_bucket = (now_ms // 900000) * 900000

    for c in raw:
        try:
            t = int(c["time"])
            if t < 10**12:
                t *= 1000
            bucket = (t // 900000) * 900000
            # Only fully closed 15-minute candles
            if bucket + 900000 > current_bucket:
                continue
            item = {
                "time": t,
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": float(c.get("volume", 0) or 0)
            }
            buckets.setdefault(bucket, []).append(item)
        except (KeyError, TypeError, ValueError):
            continue

    output = []
    for bucket in sorted(buckets):
        group = sorted(buckets[bucket], key=lambda x: x["time"])
        # Require all three 5-minute candles for a complete 15-minute bar
        slots = {((x["time"] // 300000) * 300000) for x in group}
        expected = {bucket, bucket + 300000, bucket + 600000}
        if not expected.issubset(slots):
            continue
        output.append({
            "time": bucket,
            "open": group[0]["open"],
            "high": max(x["high"] for x in group),
            "low": min(x["low"] for x in group),
            "close": group[-1]["close"],
            "volume": sum(x["volume"] for x in group)
        })
    return output


def analyze(symbol, price, candles, updated):
    if len(candles) < 60:
        raise ValueError("Not enough closed 15-minute candles")

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    e9, e21 = ema(closes, 9), ema(closes, 21)
    rsi_value = rsi(closes)
    macd_value, macd_signal, previous = macd(closes)
    adx_value = adx(candles)

    if not e9 or not e21 or macd_value is None:
        raise ValueError("Indicator history is incomplete")

    if e9[-1] > e21[-1]:
        trend = "BULLISH"
    elif e9[-1] < e21[-1]:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"

    cross_up = previous[0] <= previous[1] and macd_value > macd_signal
    cross_down = previous[0] >= previous[1] and macd_value < macd_signal

    if cross_up:
        signal = "BULLISH MACD CROSS"
    elif cross_down:
        signal = "BEARISH MACD CROSS"
    elif trend == "BULLISH" and rsi_value is not None and rsi_value < 70:
        signal = "BULLISH"
    elif trend == "BEARISH" and rsi_value is not None and rsi_value > 30:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"

    recent = closes[-20:]
    mean = sum(recent) / len(recent)
    variance = sum((x - mean) ** 2 for x in recent) / len(recent)
    sd = variance ** 0.5

    tr_values = []
    for i in range(1, len(candles)):
        tr_values.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        ))
    atr_value = sum(tr_values[-14:]) / min(14, len(tr_values))

    avg_volume = sum(volumes[-21:-1]) / 20
    volume_breakout = bool(avg_volume and volumes[-1] > avg_volume * 1.5)

    return {
        "symbol": symbol,
        "price": price,
        "signal": signal,
        "rsi": round(rsi_value, 2) if rsi_value is not None else "",
        "adx": round(adx_value, 2) if adx_value is not None else "",
        "macd": round(macd_value, 8),
        "macdSignal": round(macd_signal, 8),
        "emaTrend": trend,
        "volume": round(volumes[-1], 4),
        "updatedAt": updated,
        "bbUpper": round(mean + 2 * sd, 8),
        "bbLower": round(mean - 2 * sd, 8),
        "atr": round(atr_value, 8),
        "volumeBreakout": volume_breakout,
        "timeframe": "15m"
    }


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    updated = datetime.now(timezone.utc).isoformat()

    payload = get_json(BASE + "/v3/current_prices/futures/rt")
    prices = payload.get("prices", {})
    if not isinstance(prices, dict) or not prices:
        raise RuntimeError("CoinDCX returned no futures prices")

    pairs = []
    for symbol, info in prices.items():
        if not symbol.endswith("_USDT") or not isinstance(info, dict):
            continue
        try:
            price = float(info.get("ls", 0))
            volume = float(info.get("v", 0))
            if price > 0:
                pairs.append((symbol, price, volume))
        except (TypeError, ValueError):
            continue

    # Scan all returned USDT futures pairs, highest 24h volume first
    pairs.sort(key=lambda x: x[2], reverse=True)
    print("USDT futures pairs found:", len(pairs))

    rows = []
    errors = 0
    now = int(time.time())
    for index, (symbol, price, _) in enumerate(pairs, start=1):
        try:
            params = urllib.parse.urlencode({
                "pair": symbol,
                "from": now - 5 * 86400,
                "to": now,
                "resolution": "5",
                "pcode": "f"
            })
            data = get_json(BASE + "/candlesticks?" + params)
            raw = data.get("data", [])
            if data.get("s") not in (None, "ok"):
                raise ValueError("Candle API status: " + str(data.get("s")))

            candles = make_15m_candles(raw)
            row = analyze(symbol, price, candles, updated)
            rows.append(row)
            print(f"[{index}/{len(pairs)}] OK {symbol}: {row['signal']}")

        except Exception as exc:
            errors += 1
            print(f"[{index}/{len(pairs)}] SKIP {symbol}: {exc}")

        time.sleep(0.20)

    # Keep a valid CSV even if some pairs fail, but fail the run if none work.
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    print("Pairs found:", len(pairs))
    print("Pairs scanned successfully:", len(rows))
    print("Pairs skipped:", errors)
    print("CSV saved:", OUT)

    if not rows:
        raise RuntimeError("No pairs scanned successfully; inspect SKIP logs.")


if __name__ == "__main__":
    main()
