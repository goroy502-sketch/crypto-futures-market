
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://public.coindcx.com/market_data"
OUTPUT = "docs/signals.csv"
TIMEFRAME = "15m"

HEADERS = [
    "symbol", "price", "signal", "signalScore", "signalRating",
    "rsi", "adx", "macd", "macdSignal", "emaTrend",
    "volume", "volumeBreakout", "bbUpper", "bbLower",
    "atr", "timeframe", "updatedAt"
]


def get_json(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def ema(values, period):
    if len(values) < period:
        return None
    result = sum(values[:period]) / period
    multiplier = 2 / (period + 1)
    for value in values[period:]:
        result = value * multiplier + result * (1 - multiplier)
    return result


def rsi(values, period=14):
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(x, 0) for x in changes[-period:]]
    losses = [max(-x, 0) for x in changes[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def macd(values):
    if len(values) < 35:
        return None, None
    fast = []
    slow = []
    for i in range(1, len(values) + 1):
        fast.append(ema(values[:i], 12))
        slow.append(ema(values[:i], 26))
    line = [
        a - b for a, b in zip(fast, slow)
        if a is not None and b is not None
    ]
    if len(line) < 9:
        return None, None
    return line[-1], ema(line, 9)


def adx(candles, period=14):
    if len(candles) < period + 2:
        return None
    plus_dm, minus_dm, tr_values = [], [], []
    for i in range(1, len(candles)):
        prev, cur = candles[i - 1], candles[i]
        up = cur["high"] - prev["high"]
        down = prev["low"] - cur["low"]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
        tr_values.append(max(
            cur["high"] - cur["low"],
            abs(cur["high"] - prev["close"]),
            abs(cur["low"] - prev["close"])
        ))
    dx = []
    for i in range(period - 1, len(tr_values)):
        start = i - period + 1
        tr = sum(tr_values[start:i + 1])
        if tr == 0:
            continue
        plus = 100 * sum(plus_dm[start:i + 1]) / tr
        minus = 100 * sum(minus_dm[start:i + 1]) / tr
        total = plus + minus
        dx.append(100 * abs(plus - minus) / total if total else 0)
    return sum(dx[-period:]) / len(dx[-period:]) if dx else None



def calculate_signal_score(
    signal,
    rsi,
    adx,
    macd,
    macd_signal,
    ema_trend,
    volume_breakout
):
    score = 0

    # MACD direction: 25 points
    if macd is not None and macd_signal is not None:
        if signal == "BULLISH" and macd > macd_signal:
            score += 25
        elif signal == "BEARISH" and macd < macd_signal:
            score += 25

    # ADX trend strength: 20 points
    if adx is not None:
        if adx >= 25:
            score += 20
        elif adx >= 20:
            score += 10

    # RSI confirmation: 20 points
    if rsi is not None:
        if signal == "BULLISH" and 50 <= rsi <= 70:
            score += 20
        elif signal == "BEARISH" and 30 <= rsi <= 50:
            score += 20
        elif signal == "BULLISH" and rsi < 50:
            score += 8
        elif signal == "BEARISH" and rsi > 50:
            score += 8

    # EMA trend confirmation: 20 points
    if signal == "BULLISH" and ema_trend == "BULLISH":
        score += 20
    elif signal == "BEARISH" and ema_trend == "BEARISH":
        score += 20

    # Volume breakout: 15 points
    if volume_breakout:
        score += 15

    return min(score, 100)



def get_pairs():
    data = get_json(BASE + "/v3/current_prices/futures/rt")
    pairs = []
    if isinstance(data, dict):
        data = data.get("data", data)
    if isinstance(data, dict):
        data = [{"pair": k, "price": v} for k, v in data.items()]
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        pair = str(item.get("pair", item.get("symbol", "")))
        price = item.get("price", item.get("last_price", item.get("close")))
        if pair and "USDT" in pair.upper() and price is not None:
            pairs.append((pair, float(price)))
    return pairs


def get_candles(pair):
    now = int(time.time())
    start = now - 100 * 15 * 60
    query = urllib.parse.urlencode({
        "pair": pair,
        "from": start,
        "to": now,
        "resolution": "15",
        "pcode": "f"
    })
    data = get_json(BASE + "/candlesticks?" + query)
    if isinstance(data, dict):
        data = data.get("data", [])
    candles = []
    for item in data if isinstance(data, list) else []:
        try:
            stamp = item.get("time", item.get("timestamp"))
            stamp = float(stamp)
            if stamp > 10**12:
                stamp /= 1000
            candles.append({
                "time": int(stamp),
                "open": float(item.get("open")),
                "high": float(item.get("high")),
                "low": float(item.get("low")),
                "close": float(item.get("close")),
                "volume": float(item.get("volume", 0))
            })
        except (TypeError, ValueError):
            continue

    # Exclude the currently forming 15-minute candle.
    current_bucket = now - now % 900
    return sorted(
        [c for c in candles if c["time"] < current_bucket],
        key=lambda c: c["time"]
    )


def analyze(pair, price, candles):
    if len(candles) < 35:
        return None

    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    last = closes[-1]

    rsi_value = rsi(closes)
    macd_value, macd_signal = macd(closes)
    ema_fast = ema(closes, 9)
    ema_slow = ema(closes, 21)
    trend = (
        "BULLISH" if ema_fast > ema_slow
        else "BEARISH" if ema_fast < ema_slow
        else "NEUTRAL"
    )

    adx_value = adx(candles)
    sample = closes[-20:]
    mean = sum(sample) / len(sample)
    variance = sum((x - mean) ** 2 for x in sample) / len(sample)
    std = variance ** 0.5
    bb_upper = mean + 2 * std
    bb_lower = mean - 2 * std

    true_ranges = []
    for i in range(1, len(candles)):
        cur, prev = candles[i], candles[i - 1]
        true_ranges.append(max(
            cur["high"] - cur["low"],
            abs(cur["high"] - prev["close"]),
            abs(cur["low"] - prev["close"])
        ))
    atr = sum(true_ranges[-14:]) / min(14, len(true_ranges))

    avg_volume = (
        sum(volumes[-21:-1]) / len(volumes[-21:-1])
        if len(volumes) >= 21 else 0
    )
    volume_breakout = bool(avg_volume and volumes[-1] > avg_volume * 1.5)

    signal_label, signal_score = calculate_signal_score(
        rsi_value, adx_value, macd_value, macd_signal,
        trend, volume_breakout
    )

    return {
        "symbol": pair,
        "price": round(price, 8),
        "signal": signal_label,
        "signalScore": signal_score,
        "signalRating": signal_label,
        "rsi": round(rsi_value, 2) if rsi_value is not None else "",
        "adx": round(adx_value, 2) if adx_value is not None else "",
        "macd": round(macd_value, 8) if macd_value is not None else "",
        "macdSignal": round(macd_signal, 8) if macd_signal is not None else "",
        "emaTrend": trend,
        "volume": round(volumes[-1], 4),
        "volumeBreakout": volume_breakout,
        "bbUpper": round(bb_upper, 8),
        "bbLower": round(bb_lower, 8),
        "atr": round(atr, 8),
        "timeframe": TIMEFRAME,
        "updatedAt": datetime.fromtimestamp(
            candles[-1]["time"], timezone.utc
        ).isoformat()
    }


def main():
    os.makedirs("docs", exist_ok=True)
    print("Starting CoinDCX 15m futures scan...")
    pairs = get_pairs()
    print("USDT futures pairs found:", len(pairs))
    results = []

    for index, (pair, live_price) in enumerate(pairs, 1):
        try:
            candles = get_candles(pair)
            result = analyze(pair, live_price, candles)
            if result:
                results.append(result)
                print(index, "OK", pair, result["signal"], result["signalScore"])
            else:
                print(index, "SKIP", pair, "not enough candles")
        except Exception as error:
            print(index, "SKIP", pair, str(error)[:160])
        time.sleep(0.15)
print("CSV HEADERS:", HEADERS)
print("FIRST RESULT:", results[0] if results else "NO RESULTS")

    with open(OUTPUT, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(results)

    print("Scan complete. Results:", len(results))


if __name__ == "__main__":
    main()
