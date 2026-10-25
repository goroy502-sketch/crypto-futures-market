
window.CryptoIndicators = {
  sma(values, period) {
    if (values.length < period) return null;

    const recent = values.slice(-period).map(Number);
    return recent.reduce((sum, value) => sum + value, 0) / period;
  },

  ema(values, period) {
    if (values.length < period) return null;

    const alpha = 2 / (period + 1);
    let result = values.slice(0, period)
      .map(Number)
      .reduce((sum, value) => sum + value, 0) / period;

    for (let i = period; i < values.length; i++) {
      result = Number(values[i]) * alpha + result * (1 - alpha);
    }

    return result;
  },

  rsi(closes, period = 14) {
    if (closes.length <= period) return null;

    let gains = 0;
    let losses = 0;

    for (let i = closes.length - period; i < closes.length; i++) {
      const change = Number(closes[i]) - Number(closes[i - 1]);
      if (change > 0) gains += change;
      else losses -= change;
    }

    if (losses === 0) return 100;
    return 100 - 100 / (1 + gains / losses);
  }
};

console.log("Crypto indicators loaded");
