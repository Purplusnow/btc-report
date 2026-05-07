from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
        "conclusion": base_report.get("conclusion", default_conclusion),
        "disclaimer": "본 콘텐츠는 투자 조언이 아니며, 모든 투자 판단과 책임은 투자자 본인에게 있습니다.",
    }

    latest_report = merge_llm_fields(latest_report, request_openai_report(latest_report))
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


if __name__ == "__main__":
    main()
