# crypto-report

`crypto-report` is a GitHub Pages project that publishes an hourly Korean crypto market report.

The initial MVP focuses on `BTCUSDT`, but the code is organized so additional symbols can be added later.

## Features

- Fetches Binance spot candles for `1d`, `4h`, and `1h`
- Computes RSI, swing levels, Fibonacci retracement zones, and simple wave-style heuristics
- Generates a Korean report in the independent `WaveK` analyst style
- Publishes the latest report, chart data, and history as static JSON for GitHub Pages
- Renders a research-style site with price, volume, and RSI charts for each timeframe

## Project structure

```text
crypto-report/
├─ index.html
├─ styles.css
├─ app.js
├─ data/
│  ├─ latest.json
│  ├─ history.json
│  └─ chart_data.json
├─ docs/
│  └─ wavek-style.md
├─ scripts/
│  ├─ fetch_market.py
│  ├─ analyze_market.py
│  └─ generate_report.py
├─ .github/
│  └─ workflows/
│     └─ hourly.yml
└─ requirements.txt
```

## Environment variables

- `OPENAI_API_KEY`: optional, used for Korean narrative generation
- `OPENAI_MODEL`: optional, defaults to `gpt-5-mini`
- `SYMBOL`: optional, defaults to `BTCUSDT`

## Local run

```bash
pip install -r requirements.txt
python scripts/generate_report.py
```

The generated files are written into `data/`.

