def _rsi(prices: list[float], period: int) -> list[float]:
    if period <= 0:
        return [50.0] * len(prices)
    gains = [0.0] * len(prices)
    losses = [0.0] * len(prices)
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i - 1]
        gains[i] = max(delta, 0.0)
        losses[i] = max(-delta, 0.0)
    rsi = [50.0] * len(prices)
    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, len(prices)):
        if i < period:
            avg_gain += gains[i]
            avg_loss += losses[i]
            continue
        if i == period:
            avg_gain /= period
            avg_loss /= period
        else:
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 0.0
        rsi[i] = 100.0 - (100.0 / (1.0 + rs)) if rs > 0 else 100.0
    return rsi


def compute_signal(prices: list[float]) -> list[int]:
    short_window = 8
    long_window = 20
    rsi_period = 14
    rsi_ceiling = 70.0

    if long_window <= short_window:
        long_window = short_window + 1

    rsi_vals = _rsi(prices, rsi_period)

    signals: list[int] = [0] * len(prices)
    for i in range(len(prices)):
        if i < long_window:
            signals[i] = 0
            continue
        short_ma = sum(prices[i - short_window + 1 : i + 1]) / short_window
        long_ma = sum(prices[i - long_window + 1 : i + 1]) / long_window
        if short_ma > long_ma and rsi_vals[i] < rsi_ceiling:
            signals[i] = 1
        else:
            signals[i] = 0
    return signals
