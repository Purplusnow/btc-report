from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from uuid import uuid4

import requests

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from analyze_market import analyze_market, calculate_rsi
from fetch_market import fetch_market_data

DATA_DIR = ROOT_DIR / "data"
SEOUL = ZoneInfo("Asia/Seoul")
STARTING_BALANCE = 1000.0
STRATEGY_EXPIRY_HOURS = 48
MIN_RISK_REWARD = 1.8


def load_style_guide() -> str:
    return (ROOT_DIR / "docs" / "wavek-style.md").read_text(encoding="utf-8")


def serialize_chart_data(market_data: dict[str, list[dict]]) -> dict[str, list[dict]]:
    result = {}
    for timeframe, candles in market_data.items():
        closes = [candle["close"] for candle in candles]
        rsi_values = calculate_rsi(closes)
        result[timeframe] = []
        for candle, rsi in zip(candles, rsi_values):
            result[timeframe].append(
                {
                    "time": candle["open_time"] // 1000,
                    "open": candle["open"],
                    "high": candle["high"],
                    "low": candle["low"],
                    "close": candle["close"],
                    "volume": candle["volume"],
                    "rsi": round(rsi, 2) if rsi is not None else None,
                }
            )
    return result


def serialize_overlays(base_report: dict) -> dict[str, dict]:
    overlays = {}
    meta_timeframes = base_report.get("meta", {}).get("timeframes", {})
    for timeframe, analysis in meta_timeframes.items():
        overlays[timeframe] = {
            "trendlines": analysis.trendlines,
            "structure_hint": analysis.structure_hint,
        }
    return overlays


def parse_price(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def extract_first_price(text: str | None) -> str:
    if not text:
        return ""
    for token in str(text).replace("/", " ").split():
        if parse_price(token) is not None:
            return token
    return ""


def build_strategy_review(base_report: dict) -> str:
    daily = base_report["meta"]["timeframes"]["1d"]
    h4 = base_report["meta"]["timeframes"]["4h"]
    h1 = base_report["meta"]["timeframes"]["1h"]
    h1_rsi = f"{h1.rsi:.1f}" if h1.rsi is not None else "데이터 부족"
    return (
        f"일봉은 {daily.trend}, 4시간봉은 {h4.wave_bias}, "
        f"1시간봉은 {h1.trend}이며 RSI는 {h1_rsi}입니다. "
        f"거래량 해석은 '{h1.volume_comment}'에 가깝습니다."
    )


def strategy_signature(strategy: dict) -> str:
    return "|".join(
        [
            strategy.get("symbol", ""),
            strategy.get("side", ""),
            str(strategy.get("entry_price", "")),
            str(strategy.get("stop_price", "")),
            str(strategy.get("take_profit", "")),
            str(strategy.get("trigger_timeframe", "")),
            str(strategy.get("trigger_type", "")),
            str(strategy.get("trigger_price", "")),
            str(strategy.get("confirmation_bars", "")),
        ]
    )


def compute_return_pct(side: str, entry_price: float | None, exit_price: float | None) -> float:
    if entry_price is None or exit_price is None or entry_price == 0:
        return 0.0
    if side == "long":
        return (exit_price - entry_price) / entry_price
    if side == "short":
        return (entry_price - exit_price) / entry_price
    return 0.0


def compute_risk_reward(side: str, entry_price: float | None, stop_price: float | None, take_profit_price: float | None) -> float:
    if entry_price is None or stop_price is None or take_profit_price is None:
        return 0.0

    if side == "long":
        risk = entry_price - stop_price
        reward = take_profit_price - entry_price
    else:
        risk = stop_price - entry_price
        reward = entry_price - take_profit_price

    if risk <= 0:
        return 0.0
    return max(reward / risk, 0.0)


def pick_take_profit(side: str, entry_price: float | None, stop_price: float | None, targets: list[str]) -> str:
    parsed_targets = []
    for target in targets:
        value = parse_price(target)
        if value is not None:
            parsed_targets.append((target, value))

    if entry_price is not None and stop_price is not None:
        if side == "long":
            for raw, value in parsed_targets:
                if value > entry_price and compute_risk_reward(side, entry_price, stop_price, value) >= MIN_RISK_REWARD:
                    return raw
        elif side == "short":
            for raw, value in parsed_targets:
                if value < entry_price and compute_risk_reward(side, entry_price, stop_price, value) >= MIN_RISK_REWARD:
                    return raw

    if entry_price is not None and stop_price is not None:
        risk = abs(entry_price - stop_price)
        if risk > 0:
            if side == "long":
                return f"{entry_price + risk * MIN_RISK_REWARD:,.2f}"
            if side == "short":
                return f"{entry_price - risk * MIN_RISK_REWARD:,.2f}"

    return targets[0] if targets else ""


def build_structured_trigger(side: str, chosen: dict) -> dict:
    trigger_token = extract_first_price(chosen.get("condition", ""))
    trigger_price = parse_price(trigger_token)
    if side == "long":
        return {
            "trigger_price_text": trigger_token,
            "trigger_price": trigger_price,
            "trigger_timeframe": "4h",
            "trigger_type": "close_above",
            "confirmation_bars": 1,
            "trigger_text": f"4시간봉 종가가 {trigger_token} 위에서 1개 봉 마감하면 진입",
        }

    return {
        "trigger_price_text": trigger_token,
        "trigger_price": trigger_price,
        "trigger_timeframe": "1h",
        "trigger_type": "close_below",
        "confirmation_bars": 1,
        "trigger_text": f"1시간봉 종가가 {trigger_token} 아래에서 1개 봉 마감하면 진입",
    }


def build_cancel_rule(side: str, cancel_price_text: str) -> dict:
    cancel_price = parse_price(cancel_price_text)
    if side == "long":
        return {
            "cancel_price": cancel_price,
            "cancel_price_text": cancel_price_text,
            "cancel_timeframe": "1h",
            "cancel_type": "close_below",
            "cancel_text": f"1시간봉 종가가 {cancel_price_text} 아래에서 마감하면 추천 취소",
        }

    return {
        "cancel_price": cancel_price,
        "cancel_price_text": cancel_price_text,
        "cancel_timeframe": "1h",
        "cancel_type": "close_above",
        "cancel_text": f"1시간봉 종가가 {cancel_price_text} 위에서 마감하면 추천 취소",
    }


def choose_best_strategy(base_report: dict, latest_report: dict) -> tuple[str, dict, str]:
    daily = base_report["meta"]["timeframes"]["1d"]
    h4 = base_report["meta"]["timeframes"]["4h"]
    h1 = base_report["meta"]["timeframes"]["1h"]
    scores = {"long": 0, "short": 0, "wait": 0}

    if daily.trend == "uptrend":
        scores["long"] += 2
    elif daily.trend == "downtrend":
        scores["short"] += 2
    else:
        scores["wait"] += 1

    if h4.wave_bias == "impulse-up":
        scores["long"] += 2
    elif h4.wave_bias == "impulse-down":
        scores["short"] += 2
    else:
        scores["wait"] += 1

    if h1.trend == "uptrend":
        scores["long"] += 1
    elif h1.trend == "downtrend":
        scores["short"] += 1
    else:
        scores["wait"] += 1

    if h1.rsi is not None:
        if h1.rsi >= 55:
            scores["long"] += 1
        elif h1.rsi <= 45:
            scores["short"] += 1
        else:
            scores["wait"] += 1

    if h1.divergence == "bullish":
        scores["long"] += 1
    elif h1.divergence == "bearish":
        scores["short"] += 1

    if "줄어들고 있어" in h1.volume_comment:
        scores["wait"] += 1
    elif "확장되며" in h1.volume_comment:
        if h1.trend == "uptrend":
            scores["long"] += 1
        elif h1.trend == "downtrend":
            scores["short"] += 1

    actionable_scores = {"long": scores["long"], "short": scores["short"]}
    best_side = max(actionable_scores, key=actionable_scores.get)
    competing = min(actionable_scores.values())
    confidence_note = "조건 충족 시 진입을 검토할 수 있는 전략입니다."
    if actionable_scores[best_side] - competing <= 1:
        confidence_note = "박스 또는 혼조 성격이 남아 있어 확신도는 높지 않으며, 조건 확인 이후 접근이 적절합니다."
    elif actionable_scores[best_side] - competing >= 3:
        confidence_note = "상대적으로 우세한 방향성이 확인되는 편이지만, 무효화 이탈 시 빠른 재평가가 필요합니다."

    scenarios = latest_report["scenarios"]
    scenario_map = {
        "long": scenarios["bullish"],
        "short": scenarios["bearish"],
    }
    return best_side, scenario_map[best_side], confidence_note


def build_strategy_ideas(base_report: dict, latest_report: dict) -> list[dict]:
    symbol = latest_report["symbol"]
    created_at = latest_report["updated_at"]
    best_side, chosen, confidence_note = choose_best_strategy(base_report, latest_report)
    label_map = {
        "long": "우세 전략 아이디어",
        "short": "우세 전략 아이디어",
    }
    side_label_map = {
        "long": "상승 우세",
        "short": "하락 우세",
    }

    trigger = build_structured_trigger(best_side, chosen)
    trigger_token = trigger["trigger_price_text"]
    stop_token = extract_first_price(chosen.get("invalidation", ""))
    cancel_rule = build_cancel_rule(best_side, stop_token)
    targets = chosen.get("targets", chosen.get("range", []))
    entry_price_value = parse_price(trigger_token)
    stop_price_value = parse_price(stop_token)
    take_profit = pick_take_profit(best_side, entry_price_value, stop_price_value, targets)
    take_profit_value = parse_price(take_profit)
    risk_reward = compute_risk_reward(best_side, entry_price_value, stop_price_value, take_profit_value)
    review_note = build_strategy_review(base_report)
    return [
        {
            "id": str(uuid4()),
            "created_at": created_at,
            "symbol": symbol,
            "label": f"{label_map[best_side]} · {side_label_map[best_side]}",
            "side": best_side,
            "direction_label": "롱" if best_side == "long" else "숏",
            "status": "pending",
            "status_label": "대기중",
            "entry_price": trigger_token,
            "trigger_price": trigger["trigger_price"],
            "trigger_timeframe": trigger["trigger_timeframe"],
            "trigger_type": trigger["trigger_type"],
            "confirmation_bars": trigger["confirmation_bars"],
            "trigger_text": trigger["trigger_text"],
            "trigger_text_natural": chosen.get("condition", ""),
            "cancel_price": cancel_rule["cancel_price"],
            "cancel_price_text": cancel_rule["cancel_price_text"],
            "cancel_timeframe": cancel_rule["cancel_timeframe"],
            "cancel_type": cancel_rule["cancel_type"],
            "cancel_text": cancel_rule["cancel_text"],
            "expiry_hours": STRATEGY_EXPIRY_HOURS,
            "targets": targets,
            "take_profit": take_profit,
            "risk_reward": round(risk_reward, 2),
            "stop_price": stop_token,
            "rationale": f"{chosen.get('probability_comment', '')} {confidence_note} 목표가는 최소 손익비 {MIN_RISK_REWARD:.1f}:1 기준을 우선 반영합니다.".strip(),
            "opened_at": None,
            "closed_at": None,
            "review_note": review_note,
            "outcome_note": "",
            "signature": "",
        },
    ]


def trigger_satisfied(strategy: dict, market_data: dict[str, list[dict]]) -> tuple[bool, str | None]:
    timeframe = strategy.get("trigger_timeframe", "1h")
    trigger_type = strategy.get("trigger_type")
    trigger_price = strategy.get("trigger_price")
    confirmation_bars = int(strategy.get("confirmation_bars", 1) or 1)
    created_ts = int(datetime.fromisoformat(strategy["created_at"]).timestamp())
    candles = market_data.get(timeframe, [])
    relevant = [candle for candle in candles if candle["open_time"] // 1000 >= created_ts]

    if trigger_price is None or trigger_type not in {"close_above", "close_below"}:
        return False, None

    streak = 0
    for candle in relevant:
        close_price = candle["close"]
        matched = close_price > trigger_price if trigger_type == "close_above" else close_price < trigger_price
        streak = streak + 1 if matched else 0
        if streak >= confirmation_bars:
            opened_at = datetime.fromtimestamp(candle["close_time"] // 1000, tz=SEOUL).isoformat(timespec="seconds")
            return True, opened_at

    return False, None


def cancel_satisfied(strategy: dict, market_data: dict[str, list[dict]]) -> tuple[bool, str | None]:
    timeframe = strategy.get("cancel_timeframe", "1h")
    cancel_type = strategy.get("cancel_type")
    cancel_price = strategy.get("cancel_price")
    created_ts = int(datetime.fromisoformat(strategy["created_at"]).timestamp())
    candles = market_data.get(timeframe, [])
    relevant = [candle for candle in candles if candle["open_time"] // 1000 >= created_ts]

    if cancel_price is None or cancel_type not in {"close_above", "close_below"}:
        return False, None

    for candle in relevant:
        close_price = candle["close"]
        matched = close_price > cancel_price if cancel_type == "close_above" else close_price < cancel_price
        if matched:
            canceled_at = datetime.fromtimestamp(candle["close_time"] // 1000, tz=SEOUL).isoformat(timespec="seconds")
            return True, canceled_at

    return False, None


def evaluate_strategy(strategy: dict, market_data: dict[str, list[dict]], now: str) -> dict:
    updated = deepcopy(strategy)
    side = updated.get("side")
    stop_price = parse_price(updated.get("stop_price"))
    target_price = parse_price(updated.get("take_profit") or (updated.get("targets", [None])[0] if updated.get("targets") else None))
    entry_price = parse_price(updated.get("entry_price"))
    created_ts = int(datetime.fromisoformat(updated["created_at"]).timestamp())
    now_dt = datetime.fromisoformat(now)
    relevant = [candle for candle in market_data["1h"] if candle["open_time"] // 1000 >= created_ts]
    opened = updated.get("opened_at") is not None

    for candle in relevant:
        candle_time = datetime.fromtimestamp(candle["open_time"] // 1000, tz=SEOUL).isoformat(timespec="seconds")
        high = candle["high"]
        low = candle["low"]

        if not opened:
            is_triggered, opened_at = trigger_satisfied(updated, market_data)
            is_canceled, canceled_at = cancel_satisfied(updated, market_data)

            if is_canceled and canceled_at and (not opened_at or canceled_at <= opened_at):
                updated["status"] = "canceled"
                updated["status_label"] = "추천 취소"
                updated["closed_at"] = canceled_at
                updated["outcome_note"] = f"진입 전 {updated.get('cancel_text', '무효 조건')}이 충족되어 추천이 취소되었습니다."
                return updated

            if is_triggered and opened_at:
                updated["opened_at"] = opened_at
                updated["status"] = "open"
                updated["status_label"] = "진행중"
                opened = True

        if opened:
            if side == "long":
                if stop_price is not None and low <= stop_price:
                    updated["status"] = "lost"
                    updated["status_label"] = "손절"
                    updated["closed_at"] = candle_time
                    updated["outcome_note"] = f"보유 후 {updated['stop_price']} 이탈로 손절 처리되었습니다."
                    updated["return_pct"] = compute_return_pct(side, entry_price, stop_price)
                    return updated
                if target_price is not None and high >= target_price:
                    updated["status"] = "won"
                    updated["status_label"] = "익절"
                    updated["closed_at"] = candle_time
                    updated["outcome_note"] = f"보유 후 익절가 {updated.get('take_profit') or updated['targets'][0]}에 도달했습니다."
                    updated["return_pct"] = compute_return_pct(side, entry_price, target_price)
                    return updated
            elif side == "short":
                if stop_price is not None and high >= stop_price:
                    updated["status"] = "lost"
                    updated["status_label"] = "손절"
                    updated["closed_at"] = candle_time
                    updated["outcome_note"] = f"보유 후 {updated['stop_price']} 회복으로 손절 처리되었습니다."
                    updated["return_pct"] = compute_return_pct(side, entry_price, stop_price)
                    return updated
                if target_price is not None and low <= target_price:
                    updated["status"] = "won"
                    updated["status_label"] = "익절"
                    updated["closed_at"] = candle_time
                    updated["outcome_note"] = f"보유 후 익절가 {updated.get('take_profit') or updated['targets'][0]}에 도달했습니다."
                    updated["return_pct"] = compute_return_pct(side, entry_price, target_price)
                    return updated

    created_dt = datetime.fromisoformat(updated["created_at"])
    expiry_hours = int(updated.get("expiry_hours", STRATEGY_EXPIRY_HOURS) or STRATEGY_EXPIRY_HOURS)
    if updated["status"] == "pending" and (now_dt - created_dt).total_seconds() >= expiry_hours * 3600:
        updated["status"] = "expired"
        updated["status_label"] = "만료"
        updated["outcome_note"] = f"{expiry_hours}시간 내 진입 조건이 충족되지 않아 만료 처리되었습니다."
        return updated


def apply_balance_curve(history: list[dict]) -> tuple[list[dict], dict]:
    chronological = sorted(history, key=lambda item: item.get("created_at", ""))
    balance = STARTING_BALANCE

    for item in chronological:
        item["balance_before"] = round(balance, 2)
        status = item.get("status")
        return_pct = float(item.get("return_pct", 0.0) or 0.0)
        if status in {"won", "lost"}:
            pnl_amount = balance * return_pct
            balance += pnl_amount
            item["pnl_amount"] = round(pnl_amount, 2)
            item["balance_after"] = round(balance, 2)
        else:
            item["pnl_amount"] = 0.0
            item["balance_after"] = round(balance, 2)

    updated_history = sorted(chronological, key=lambda item: item.get("created_at", ""), reverse=True)
    closed = [item for item in chronological if item.get("status") in {"won", "lost"}]
    wins = sum(1 for item in chronological if item.get("status") == "won")
    losses = sum(1 for item in chronological if item.get("status") == "lost")
    pending = sum(1 for item in chronological if item.get("status") == "pending")
    open_count = sum(1 for item in chronological if item.get("status") == "open")
    expired = sum(1 for item in chronological if item.get("status") == "expired")
    canceled = sum(1 for item in chronological if item.get("status") == "canceled")
    win_rate = f"{(wins / len(closed) * 100):.1f}%" if closed else "0.0%"
    cumulative_pnl = balance - STARTING_BALANCE
    summary = {
        "starting_balance": round(STARTING_BALANCE, 2),
        "current_balance": round(balance, 2),
        "cumulative_pnl": round(cumulative_pnl, 2),
        "cumulative_return_pct": f"{(cumulative_pnl / STARTING_BALANCE * 100):.2f}%",
        "total": len(chronological),
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "open": open_count,
        "expired": expired,
        "canceled": canceled,
        "win_rate": win_rate,
    }
    return updated_history, summary


def update_strategy_history(base_report: dict, latest_report: dict, market_data: dict[str, list[dict]]) -> tuple[list[dict], dict]:
    history_path = DATA_DIR / "strategy_history.json"
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
    else:
        history = []

    now = latest_report["updated_at"]
    updated_history = [
        evaluate_strategy(item, market_data, now)
        if item.get("status") in {"pending", "open"} else item
        for item in history
    ]
    new_ideas = build_strategy_ideas(base_report, latest_report)
    for idea in new_ideas:
        idea["signature"] = strategy_signature(idea)

    normalized_history = []
    seen_signatures = set()
    for item in updated_history:
        item_signature = item.get("signature") or strategy_signature(item)
        item["signature"] = item_signature
        is_active = item.get("status") in {"pending", "open"}
        if is_active and item_signature in seen_signatures:
            continue
        if is_active:
            seen_signatures.add(item_signature)
        normalized_history.append(item)

    active_signatures = {
        item["signature"]
        for item in normalized_history
        if item.get("status") in {"pending", "open"}
    }
    ideas_to_add = [idea for idea in new_ideas if idea["signature"] not in active_signatures]

    updated_history = ideas_to_add + normalized_history
    updated_history = updated_history[:120]
    return apply_balance_curve(updated_history)


def build_prompt(base_report: dict) -> str:
    style_guide = load_style_guide()
    return f"""
You are WaveK, an independent virtual crypto market analyst.
Write in Korean.
Use conditional, professional market language.
Do not imitate any real public figure.
Do not provide direct investment advice or certainty.
Always explain each timeframe by combining price structure, RSI, and volume together.
Prefer concise labeled lines such as 추세, 파동, 가격 구조, RSI, 거래량 해석 when useful.

Style guide:
{style_guide}

Draft data:
{json.dumps(base_report, ensure_ascii=False, indent=2)}

Return JSON only with this exact schema:
{{
  "summary": "string",
  "daily_view": "string",
  "h4_view": "string",
  "h1_view": "string",
  "scenarios": {{
    "bullish": {{
      "condition": "string",
      "targets": ["string"],
      "invalidation": "string",
      "probability_comment": "string"
    }},
    "bearish": {{
      "condition": "string",
      "targets": ["string"],
      "invalidation": "string",
      "probability_comment": "string"
    }},
    "neutral": {{
      "condition": "string",
      "range": ["string"],
      "invalidation": "string",
      "probability_comment": "string"
    }}
  }},
  "conclusion": "string"
}}
""".strip()


def request_openai_report(base_report: dict) -> dict | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": build_prompt(base_report),
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload.get("output_text", "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def merge_llm_fields(base_report: dict, llm_report: dict | None) -> dict:
    if not llm_report:
        return base_report

    merged = deepcopy(base_report)
    for field in ("summary", "daily_view", "h4_view", "h1_view", "conclusion"):
        if llm_report.get(field):
            merged[field] = llm_report[field]

    scenarios = llm_report.get("scenarios", {})
    for key in ("bullish", "bearish", "neutral"):
        if key in scenarios and isinstance(scenarios[key], dict):
            merged["scenarios"][key].update(
                {
                    nested_key: nested_value
                    for nested_key, nested_value in scenarios[key].items()
                    if nested_value
                }
            )
    return merged


def update_history(latest_report: dict) -> list[dict]:
    history_path = DATA_DIR / "history.json"
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
    else:
        history = []

    entry = {
        "symbol": latest_report["symbol"],
        "updated_at": latest_report["updated_at"],
        "summary": latest_report["summary"],
        "conclusion": latest_report["conclusion"],
    }
    history.insert(0, entry)
    return history[:72]


def main() -> None:
    symbol = os.getenv("SYMBOL", "BTCUSDT")
    report_timestamp = os.getenv("REPORT_TIMESTAMP")
    report_version = os.getenv("REPORT_VERSION")
    now = report_timestamp or datetime.now(tz=SEOUL).isoformat(timespec="seconds")
    version = report_version or datetime.now(tz=SEOUL).strftime("%Y.%m.%d.%H.%M")
    market_data = fetch_market_data(symbol)
    base_report = analyze_market(symbol, market_data)
    default_conclusion = (
        "현재는 상위 시간봉 구조와 단기 지지 여부를 함께 확인하는 접근이 더 유리합니다."
    )

    latest_report = {
        "symbol": symbol,
        "updated_at": now,
        "version": version,
        "summary": base_report.get("summary", ""),
        "daily_view": base_report.get("daily_view", ""),
        "h4_view": base_report.get("h4_view", ""),
        "h1_view": base_report.get("h1_view", ""),
        "key_levels": base_report.get(
            "key_levels",
            {"support": [], "resistance": [], "invalidations": []},
        ),
        "scenarios": base_report.get(
            "scenarios",
            {
                "bullish": {
                    "condition": "",
                    "targets": [],
                    "invalidation": "",
                    "probability_comment": "",
                },
                "bearish": {
                    "condition": "",
                    "targets": [],
                    "invalidation": "",
                    "probability_comment": "",
                },
                "neutral": {
                    "condition": "",
                    "range": [],
                    "invalidation": "",
                    "probability_comment": "",
                },
            },
        ),
        "strategy_ideas": [],
        "strategy_summary": {
            "starting_balance": STARTING_BALANCE,
            "current_balance": STARTING_BALANCE,
            "cumulative_pnl": 0,
            "cumulative_return_pct": "0.00%",
            "total": 0,
            "wins": 0,
            "losses": 0,
            "pending": 0,
            "open": 0,
            "expired": 0,
            "canceled": 0,
            "win_rate": "0.0%",
        },
        "conclusion": base_report.get("conclusion", default_conclusion),
        "disclaimer": "본 콘텐츠는 투자 조언이 아니며, 모든 투자 판단과 책임은 투자자 본인에게 있습니다.",
    }

    latest_report = merge_llm_fields(latest_report, request_openai_report(latest_report))
    strategy_history, strategy_summary = update_strategy_history(base_report, latest_report, market_data)
    latest_report["strategy_ideas"] = strategy_history[:1]
    latest_report["strategy_summary"] = strategy_summary
    chart_data = {
        "symbol": symbol,
        "updated_at": now,
        "timeframes": serialize_chart_data(market_data),
        "overlays": serialize_overlays(base_report),
    }
    history = update_history(latest_report)

    (DATA_DIR / "latest.json").write_text(
        json.dumps(latest_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DATA_DIR / "history.json").write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DATA_DIR / "chart_data.json").write_text(
        json.dumps(chart_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (DATA_DIR / "strategy_history.json").write_text(
        json.dumps(strategy_history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
