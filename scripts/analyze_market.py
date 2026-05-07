from __future__ import annotations

from dataclasses import dataclass
from statistics import mean


def calculate_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    if len(closes) < period + 1:
        return [None] * len(closes)

    gains = []
    losses = []
    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    values = [None] * period

    rs = avg_gain / avg_loss if avg_loss else float("inf")
    values.append(100 - (100 / (1 + rs)))

    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = max(change, 0)
        loss = max(-change, 0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        rs = avg_gain / avg_loss if avg_loss else float("inf")
        values.append(100 - (100 / (1 + rs)))

    return values


def identify_swing_points(candles: list[dict], window: int = 3) -> tuple[list[dict], list[dict]]:
    highs = []
    lows = []
    for index in range(window, len(candles) - window):
        current = candles[index]
        left = candles[index - window:index]
        right = candles[index + 1:index + 1 + window]
        if all(current["high"] >= point["high"] for point in left + right):
            highs.append(current)
        if all(current["low"] <= point["low"] for point in left + right):
            lows.append(current)
    return highs, lows


def estimate_divergence(candles: list[dict]) -> str | None:
    swing_highs, swing_lows = identify_swing_points(candles, window=2)
    if len(swing_highs) >= 2:
        first, second = swing_highs[-2], swing_highs[-1]
        if first.get("rsi") is not None and second.get("rsi") is not None:
            if second["high"] > first["high"] and second["rsi"] < first["rsi"]:
                return "bearish"
    if len(swing_lows) >= 2:
        first, second = swing_lows[-2], swing_lows[-1]
        if first.get("rsi") is not None and second.get("rsi") is not None:
            if second["low"] < first["low"] and second["rsi"] > first["rsi"]:
                return "bullish"
    return None


def fibonacci_levels(high_price: float, low_price: float) -> dict[str, float]:
    spread = high_price - low_price
    return {
        "0.382": high_price - spread * 0.382,
        "0.5": high_price - spread * 0.5,
        "0.618": high_price - spread * 0.618,
    }


def round_number_levels(price: float) -> list[float]:
    magnitude = 1000 if price >= 10000 else 100
    base = int(price // magnitude) * magnitude
    return [float(base - magnitude), float(base), float(base + magnitude)]


def trend_label(candles: list[dict]) -> str:
    closes = [candle["close"] for candle in candles[-20:]]
    start = mean(closes[:5])
    end = mean(closes[-5:])
    change = (end - start) / start if start else 0
    if change > 0.04:
        return "uptrend"
    if change < -0.04:
        return "downtrend"
    return "range"


def wave_bias(candles: list[dict]) -> str:
    highs, lows = identify_swing_points(candles)
    if len(highs) >= 3 and len(lows) >= 3:
        rising_highs = highs[-1]["high"] > highs[-2]["high"] > highs[-3]["high"]
        rising_lows = lows[-1]["low"] > lows[-2]["low"] > lows[-3]["low"]
        falling_highs = highs[-1]["high"] < highs[-2]["high"] < highs[-3]["high"]
        falling_lows = lows[-1]["low"] < lows[-2]["low"] < lows[-3]["low"]
        if rising_highs and rising_lows:
            return "impulse-up"
        if falling_highs and falling_lows:
            return "impulse-down"

    recent = candles[-24:]
    highs_only = [point["high"] for point in recent]
    lows_only = [point["low"] for point in recent]
    if max(highs_only) - min(highs_only) < mean(highs_only) * 0.03 and max(lows_only) - min(lows_only) < mean(lows_only) * 0.03:
        return "triangle-or-range"
    return "abc-or-complex"


def strongest_volume_node(candles: list[dict]) -> float:
    strongest = max(candles[-40:], key=lambda candle: candle["volume"])
    return (strongest["high"] + strongest["low"] + strongest["close"]) / 3


def build_trendline(start: dict, end: dict, latest_time: int, line_type: str) -> dict:
    start_time = start["open_time"] // 1000
    end_time = end["open_time"] // 1000
    latest = latest_time // 1000
    time_span = max(end_time - start_time, 1)
    start_value = start["low"] if line_type == "support" else start["high"]
    end_value = end["low"] if line_type == "support" else end["high"]
    slope = (end_value - start_value) / time_span
    extended_value = end_value + slope * max(latest - end_time, 0)

    return {
        "type": line_type,
        "slope": slope,
        "start": {"time": start_time, "value": round(start_value, 2)},
        "end": {"time": latest, "value": round(extended_value, 2)},
    }


def classify_structure(trendlines: list[dict]) -> str | None:
    support_line = next((line for line in trendlines if line["type"] == "support"), None)
    resistance_line = next((line for line in trendlines if line["type"] == "resistance"), None)
    if not support_line or not resistance_line:
        return None

    support_slope = support_line["slope"]
    resistance_slope = resistance_line["slope"]
    slope_gap = abs(support_slope - resistance_slope)
    baseline = max(abs(support_slope), abs(resistance_slope), 0.0001)

    if support_slope > 0 and resistance_slope > 0 and slope_gap / baseline < 0.35:
        return "상승 평행 채널 가능성"
    if support_slope < 0 and resistance_slope < 0 and slope_gap / baseline < 0.35:
        return "하락 평행 채널 가능성"
    if support_slope > 0 and resistance_slope < 0:
        return "수렴형 삼각 또는 쐐기 가능성"
    if support_slope < 0 and resistance_slope > 0:
        return "확산형 쐐기 또는 broadening 구조 가능성"
    if support_slope > 0 and resistance_slope > 0:
        return "상승 쐐기 가능성"
    if support_slope < 0 and resistance_slope < 0:
        return "하락 쐐기 가능성"
    return None


def detect_trendlines(candles: list[dict]) -> tuple[list[dict], str | None]:
    highs, lows = identify_swing_points(candles)
    trendlines = []
    latest_time = candles[-1]["open_time"]

    if len(lows) >= 2:
        trendlines.append(build_trendline(lows[-2], lows[-1], latest_time, "support"))
    if len(highs) >= 2:
        trendlines.append(build_trendline(highs[-2], highs[-1], latest_time, "resistance"))

    return trendlines, classify_structure(trendlines)


@dataclass
class TimeframeAnalysis:
    timeframe: str
    trend: str
    wave_bias: str
    divergence: str | None
    rsi: float | None
    last_close: float
    support: float
    resistance: float
    volume_reference: float
    fib_levels: dict[str, float]
    volume_comment: str
    trendlines: list[dict]
    structure_hint: str | None


def analyze_timeframe(candles: list[dict], timeframe: str) -> TimeframeAnalysis:
    closes = [candle["close"] for candle in candles]
    rsi_values = calculate_rsi(closes)

    enriched = []
    for candle, rsi in zip(candles, rsi_values):
        enriched.append({**candle, "rsi": rsi})

    highs, lows = identify_swing_points(enriched)
    trendlines, structure_hint = detect_trendlines(enriched)
    resistance = highs[-1]["high"] if highs else max(closes[-30:])
    support = lows[-1]["low"] if lows else min(closes[-30:])
    high_price = max(candle["high"] for candle in enriched[-90:])
    low_price = min(candle["low"] for candle in enriched[-90:])
    current_rsi = next((value for value in reversed(rsi_values) if value is not None), None)

    recent_volume = mean(candle["volume"] for candle in enriched[-10:])
    prior_volume = mean(candle["volume"] for candle in enriched[-30:-10])
    if recent_volume > prior_volume * 1.2:
        volume_comment = "거래량이 확장되며 방향성 신뢰도가 높아지는 구간입니다."
    elif recent_volume < prior_volume * 0.85:
        volume_comment = "거래량이 줄어들고 있어 추세보다는 수렴 또는 숨 고르기 가능성을 열어둘 필요가 있습니다."
    else:
        volume_comment = "거래량은 중립적이며 가격 구조 확인이 더 중요합니다."

    return TimeframeAnalysis(
        timeframe=timeframe,
        trend=trend_label(enriched),
        wave_bias=wave_bias(enriched),
        divergence=estimate_divergence(enriched),
        rsi=current_rsi,
        last_close=closes[-1],
        support=support,
        resistance=resistance,
        volume_reference=strongest_volume_node(enriched),
        fib_levels=fibonacci_levels(high_price, low_price),
        volume_comment=volume_comment,
        trendlines=trendlines,
        structure_hint=structure_hint,
    )


def format_price(value: float) -> str:
    return f"{value:,.2f}"


def describe_timeframe(analysis: TimeframeAnalysis) -> str:
    rsi_comment = "데이터 부족"
    if analysis.rsi is not None:
        if analysis.rsi >= 70:
            rsi_comment = f"{analysis.rsi:.1f}로 단기 과열 구간에 가깝습니다"
        elif analysis.rsi <= 30:
            rsi_comment = f"{analysis.rsi:.1f}로 단기 과매도 구간에 근접합니다"
        else:
            rsi_comment = f"{analysis.rsi:.1f}로 중립과 추세 구간의 중간에 위치합니다"

    divergence_comment = "뚜렷한 다이버전스 신호는 제한적입니다."
    if analysis.divergence == "bearish":
        divergence_comment = "가격 고점 대비 RSI가 둔화되어 있어 상승 5파 마무리 또는 조정 가능성을 경계할 구간입니다."
    elif analysis.divergence == "bullish":
        divergence_comment = "가격 저점 대비 RSI가 버티고 있어 하락 탄력 둔화 가능성을 열어둘 수 있습니다."

    trend_map = {
        "uptrend": "상위 저점이 유지되며 상승 추세 성격이 살아 있습니다.",
        "downtrend": "고점과 저점이 낮아지는 하락 추세 성격이 우세합니다.",
        "range": "뚜렷한 방향성보다는 박스 또는 수렴 해석이 유효합니다.",
    }

    wave_map = {
        "impulse-up": "상승 임펄스 진행 가능성이 높습니다",
        "impulse-down": "하락 임펄스 또는 하락 연장 해석에 무게가 실립니다",
        "triangle-or-range": "삼각수렴 또는 복합 조정 가능성을 열어둘 수 있습니다",
        "abc-or-complex": "ABC 또는 복합 조정 여부 확인이 더 중요합니다",
    }

    support_gap = abs(analysis.last_close - analysis.support)
    resistance_gap = abs(analysis.resistance - analysis.last_close)
    if support_gap < resistance_gap * 0.8:
        price_comment = "최근 가격이 지지 구간에 더 가까워 지지 유지 여부가 우선 확인 포인트입니다"
    elif resistance_gap < support_gap * 0.8:
        price_comment = "최근 가격이 저항 구간에 가까워 돌파 안착 여부가 핵심입니다"
    else:
        price_comment = "최근 가격은 지지와 저항 사이 중간 구간에 있어 방향 확인이 더 중요합니다"

    combined_signal = "가격 구조 확인이 우선입니다"
    if analysis.rsi is not None:
        if analysis.trend == "uptrend" and analysis.rsi >= 55:
            combined_signal = "가격 구조와 RSI가 함께 버티면 상승 추세 연장 가능성을 열어둘 수 있습니다"
        elif analysis.trend == "downtrend" and analysis.rsi <= 45:
            combined_signal = "가격 구조와 RSI가 함께 약하면 하락 추세 연장 가능성을 경계할 필요가 있습니다"
        elif 45 <= analysis.rsi <= 55:
            combined_signal = "RSI가 중립에 가까워 거래량과 가격 돌파 방향이 더 중요합니다"

    return "\n".join(
        [
            f"추세: {trend_map[analysis.trend]}",
            f"파동: {wave_map[analysis.wave_bias]}",
            f"가격 구조: {price_comment}",
            f"지지: {format_price(analysis.support)} / 저항: {format_price(analysis.resistance)}",
            f"거래량 중심 가격: {format_price(analysis.volume_reference)}",
            f"RSI: {rsi_comment}",
            f"가격·RSI 종합: {combined_signal}",
            f"추세선 구조: {analysis.structure_hint or '뚜렷한 대각 추세선 구조는 제한적입니다'}",
            f"다이버전스: {divergence_comment}",
            f"거래량 해석: {analysis.volume_comment}",
        ]
    )


def build_key_levels(daily: TimeframeAnalysis, h4: TimeframeAnalysis, h1: TimeframeAnalysis) -> dict[str, list[str]]:
    levels = {
        "support": sorted(
            {
                format_price(daily.support),
                format_price(h4.support),
                format_price(h1.support),
                format_price(daily.fib_levels["0.5"]),
            }
        ),
        "resistance": sorted(
            {
                format_price(daily.resistance),
                format_price(h4.resistance),
                format_price(h1.resistance),
                format_price(daily.fib_levels["0.382"]),
            }
        ),
        "invalidations": sorted(
            {
                format_price(h1.support),
                format_price(h4.support),
                format_price(daily.fib_levels["0.618"]),
            }
        ),
    }
    return levels


def probability_comment(primary: str, supporting: str, invalidation: str) -> str:
    return f"{primary} 다만 {supporting} 전까지는 단정적 접근보다 조건 확인이 우선이며, {invalidation} 이탈 시 대체 시나리오 비중을 높여야 합니다."


def analyze_market(symbol: str, market_data: dict[str, list[dict]]) -> dict:
    daily = analyze_timeframe(market_data["1d"], "1d")
    h4 = analyze_timeframe(market_data["4h"], "4h")
    h1 = analyze_timeframe(market_data["1h"], "1h")
    latest_price = market_data["1h"][-1]["close"]
    round_levels = [format_price(level) for level in round_number_levels(latest_price)]
    key_levels = build_key_levels(daily, h4, h1)
    key_levels["resistance"] = sorted(set(key_levels["resistance"] + round_levels[-2:]))
    key_levels["support"] = sorted(set(key_levels["support"] + round_levels[:2]))

    bullish_trigger = format_price(h4.resistance)
    bullish_invalidation = format_price(h1.support)
    bearish_trigger = format_price(h1.support)
    bearish_invalidation = format_price(h4.resistance)
    neutral_low = format_price(h1.support)
    neutral_high = format_price(h1.resistance)

    trend_kor = {
        "uptrend": "상승 추세",
        "downtrend": "하락 추세",
        "range": "중립 또는 박스 흐름",
    }
    wave_kor = {
        "impulse-up": "상승 임펄스 가능성",
        "impulse-down": "하락 임펄스 가능성",
        "triangle-or-range": "삼각수렴 또는 횡보 가능성",
        "abc-or-complex": "ABC 또는 복합 조정 가능성",
    }
    h1_rsi_text = f"{h1.rsi:.1f}" if h1.rsi is not None else "데이터 부족"

    summary = (
        f"{symbol}는 현재 일봉에서 {trend_kor[daily.trend]}, 4시간봉에서 {wave_kor[h4.wave_bias]}, "
        f"1시간봉에서는 {trend_kor[h1.trend]} 성격이 겹치는 구간입니다. "
        f"또한 1시간봉 RSI는 {h1_rsi_text} 수준이며 거래량 해석은 '{h1.volume_comment}'에 가깝습니다. "
        "따라서 단일 방향 단정은 피하고 가격 구조와 거래량 확인 뒤 대응하는 접근이 유리합니다."
    )

    conclusion = (
        f"현재는 {bullish_trigger} 돌파 확인과 {bearish_trigger} 지지 여부가 핵심 분기점입니다. "
        "추격 대응보다는 지지 확인 또는 돌파 안착 이후의 후속 반응, 그리고 그 과정에서 RSI와 거래량이 동반되는지 확인하는 편이 더 안정적입니다."
    )

    return {
        "symbol": symbol,
        "summary": summary,
        "daily_view": describe_timeframe(daily),
        "h4_view": describe_timeframe(h4),
        "h1_view": describe_timeframe(h1),
        "key_levels": key_levels,
        "scenarios": {
            "bullish": {
                "condition": f"{bullish_trigger} 상향 돌파 후 4시간봉 종가 안착이 확인될 때",
                "targets": [
                    format_price(daily.resistance),
                    format_price(max(daily.resistance, h4.resistance) * 1.03),
                ],
                "invalidation": f"{bullish_invalidation} 이탈",
                "probability_comment": probability_comment(
                    "상위 시간봉 저점이 유지되는 한 반등 연장 가능성은 열려 있습니다.",
                    f"{bullish_trigger} 돌파",
                    bullish_invalidation,
                ),
            },
            "bearish": {
                "condition": f"{bearish_trigger} 이탈 후 반등이 저항 전환으로 확인될 때",
                "targets": [
                    format_price(h4.support),
                    format_price(daily.fib_levels["0.618"]),
                ],
                "invalidation": f"{bearish_invalidation} 회복",
                "probability_comment": probability_comment(
                    "단기 구조가 무너지면 조정 파동 연장 가능성이 높아집니다.",
                    f"{bearish_trigger} 하향 이탈",
                    bearish_invalidation,
                ),
            },
            "neutral": {
                "condition": f"{neutral_low} ~ {neutral_high} 사이에서 거래량 감소와 함께 박스 흐름이 이어질 때",
                "range": [neutral_low, neutral_high],
                "invalidation": f"{bullish_trigger} 돌파 또는 {bearish_trigger} 이탈",
                "probability_comment": "방향성 확정보다는 수렴 해석이 우세한 구간이며, 박스 상하단 반응 확인이 중요합니다.",
            },
        },
        "conclusion": conclusion,
        "meta": {
            "timeframes": {
                "1d": daily,
                "4h": h4,
                "1h": h1,
            }
        },
    }
