
def calculate_signal_score(rsi_value, adx_value, macd_value,
                           macd_signal, ema_trend, volume_breakout):
    bullish = 0
    bearish = 0

    if ema_trend == "BULLISH":
        bullish += 2
    elif ema_trend == "BEARISH":
        bearish += 2

    if macd_value is not None and macd_signal is not None:
        if macd_value > macd_signal:
            bullish += 2
        elif macd_value < macd_signal:
            bearish += 2

    if rsi_value is not None:
        if 50 < rsi_value < 70:
            bullish += 1
        elif 30 < rsi_value < 50:
            bearish += 1

    if adx_value is not None and adx_value >= 25:
        if bullish > bearish:
            bullish += 1
        elif bearish > bullish:
            bearish += 1

    if volume_breakout:
        if bullish > bearish:
            bullish += 1
        elif bearish > bullish:
            bearish += 1

    if bullish > bearish:
        return "BULLISH", bullish
    if bearish > bullish:
        return "BEARISH", bearish
    return "NEUTRAL", max(bullish, bearish)
