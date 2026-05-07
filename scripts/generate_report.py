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


def build_strategy_ideas(latest_report: dict) -> list[dict]:
    symbol = latest_report["symbol"]
    created_at = latest_report["updated_at"]
    bullish = latest_report["scenarios"]["bullish"]
    bearish = latest_report["scenarios"]["bearish"]
    neutral = latest_report["scenarios"]["neutral"]

    return [
        {
            "id": str(uuid4()),
            "created_at": created_at,
            "symbol": symbol,
            "label": "상승 전략 아이디어",
            "side": "long",
            "status": "pending",
            "status_label": "대기중",
            "entry_price": bullish["condition"].split(" ")[0],
            "trigger_price": parse_price(bullish["condition"].split(" ")[0]),
            "trigger_text": bullish["condition"],
            "targets": bullish.get("targets", []),
            "stop_price": bullish.get("invalidation", ""),
            "rationale": bullish.get("probability_comment", ""),
            "opened_at": None,
            "closed_at": None,
            "outcome_note": "",
        },
        {
            "id": str(uuid4()),
            "created_at": created_at,
            "symbol": symbol,
            "label": "하락 전략 아이디어",
            "side": "short",
            "status": "pending",
            "status_label": "대기중",
            "entry_price": bearish["condition"].split(" ")[0],
            "trigger_price": parse_price(bearish["condition"].split(" ")[0]),
            "trigger_text": bearish["condition"],
            "targets": bearish.get("targets", []),
            "stop_price": bearish.get("invalidation", ""),
            "rationale": bearish.get("probability_comment", ""),
            "opened_at": None,
            "closed_at": None,
            "outcome_note": "",
        },
        {
            "id": str(uuid4()),
            "created_at": created_at,
            "symbol": symbol,
            "label": "관망 전략 아이디어",
            "side": "wait",
            "status": "pending",
            "status_label": "대기중",
            "entry_price": "",
            "trigger_price": None,
            "trigger_text": neutral["condition"],
            "targets": neutral.get("range", []),
            "stop_price": neutral.get("invalidation", ""),
            "rationale": neutral.get("probability_comment", ""),
            "opened_at": None,
            "closed_at": None,
            "outcome_note": "방향 확정보다는 박스 상하단 반응을 기다리는 전략입니다.",
        },
    ]


def evaluate_strategy(strategy: dict, candles: list[dict], now: str) -> dict:
    updated = deepcopy(strategy)
    side = updated.get("side")
    trigger_price = updated.get("trigger_price")
    stop_price = parse_price(updated.get("stop_price"))
    target_price = parse_price(updated.get("targets", [None])[0] if updated.get("targets") else None)
    created_ts = int(datetime.fromisoformat(updated["created_at"]).timestamp())
    now_dt = datetime.fromisoformat(now)
    if side == "wait":
        created_dt = datetime.fromisoformat(updated["created_at"])
        if (now_dt - created_dt).total_seconds() >= 24 * 3600:
            updated["status"] = "expired"
            updated["status_label"] = "만료"
        return updated

    relevant = [candle for candle in candles if candle["open_time"] // 1000 >= created_ts]
    opened = updated.get("opened_at") is not None

    for candle in relevant:
        candle_time = datetime.fromtimestamp(candle["open_time"] // 1000, tz=SEOUL).isoformat(timespec="seconds")
        high = candle["high"]
        low = candle["low"]

        if not opened:
            if side == "long" and trigger_price is not None and high >= trigger_price:
                updated["opened_at"] = candle_time
                updated["status"] = "open"
                updated["status_label"] = "진행중"
                opened = True
            elif side == "short" and trigger_price is not None and low <= trigger_price:
                updated["opened_at"] = candle_time
                updated["status"] = "open"
                updated["status_label"] = "진행중"
                opened = True

        if opened:
            if side == "long":
                if stop_price is not None and low <= stop_price:
                    updated["status"] = "lost"
                    updated["status_label"] = "손절"
                    updated["closed_at"] = candle_time
                    updated["outcome_note"] = f"{updated['stop_price']} 이탈로 손절 처리되었습니다."
                    return updated
                if target_price is not None and high >= target_price:
                    updated["status"] = "won"
                    updated["status_label"] = "목표 도달"
                    updated["closed_at"] = candle_time
                    updated["outcome_note"] = f"첫 목표가 {updated['targets'][0]}에 도달했습니다."
                    return updated
            elif side == "short":
                if stop_price is not None and high >= stop_price:
                    updated["status"] = "lost"
                    updated["status_label"] = "손절"
                    updated["closed_at"] = candle_time
                    updated["outcome_note"] = f"{updated['stop_price']} 회복으로 손절 처리되었습니다."
                    return updated
                if target_price is not None and low <= target_price:
                    updated["status"] = "won"
                    updated["status_label"] = "목표 도달"
                    updated["closed_at"] = candle_time
                    updated["outcome_note"] = f"첫 목표가 {updated['targets'][0]}에 도달했습니다."
                    return updated

    created_dt = datetime.fromisoformat(updated["created_at"])
    if updated["status"] == "pending" and (now_dt - created_dt).total_seconds() >= 48 * 3600:
        updated["status"] = "expired"
        updated["status_label"] = "만료"
        updated["outcome_note"] = "48시간 내 진입 조건이 충족되지 않아 만료 처리되었습니다."
    return updated


def update_strategy_history(latest_report: dict, market_data: dict[str, list[dict]]) -> tuple[list[dict], dict]:
    history_path = DATA_DIR / "strategy_history.json"
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
    else:
        history = []

    now = latest_report["updated_at"]
    updated_history = [
        evaluate_strategy(item, market_data["1h"], now)
        if item.get("status") in {"pending", "open"} else item
        for item in history
    ]
    updated_history = build_strategy_ideas(latest_report) + updated_history
    updated_history = updated_history[:120]

    wins = sum(1 for item in updated_history if item.get("status") == "won")
    losses = sum(1 for item in updated_history if item.get("status") == "lost")
    pending = sum(1 for item in updated_history if item.get("status") == "pending")
    open_count = sum(1 for item in updated_history if item.get("status") == "open")
    expired = sum(1 for item in updated_history if item.get("status") == "expired")
    closed = wins + losses
    win_rate = f"{(wins / closed * 100):.1f}%" if closed else "0.0%"
    summary = {
        "total": len(updated_history),
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "open": open_count,
        "expired": expired,
        "win_rate": win_rate,
    }
    return updated_history, summary


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
    now = datetime.now(tz=SEOUL).isoformat(timespec="seconds")
    market_data = fetch_market_data(symbol)
    base_report = analyze_market(symbol, market_data)
    default_conclusion = (
        "현재는 상위 시간봉 구조와 단기 지지 여부를 함께 확인하는 접근이 더 유리합니다."
    )

    latest_report = {
        "symbol": symbol,
        "updated_at": now,
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
            "total": 0,
            "wins": 0,
            "losses": 0,
            "pending": 0,
            "open": 0,
            "expired": 0,
            "win_rate": "0.0%",
        },
        "conclusion": base_report.get("conclusion", default_conclusion),
        "disclaimer": "본 콘텐츠는 투자 조언이 아니며, 모든 투자 판단과 책임은 투자자 본인에게 있습니다.",
    }

    latest_report = merge_llm_fields(latest_report, request_openai_report(latest_report))
    strategy_history, strategy_summary = update_strategy_history(latest_report, market_data)
    latest_report["strategy_ideas"] = strategy_history[:3]
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
