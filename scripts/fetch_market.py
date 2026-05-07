import requests

BINANCE_URLS = [
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
]


def fetch_klines(symbol: str, interval: str, limit: int = 240) -> list[dict]:
    rows = None
    last_error = None
    for url in BINANCE_URLS:
        try:
            response = requests.get(
                url,
                params={"symbol": symbol, "interval": interval, "limit": limit},
                timeout=20,
            )
            response.raise_for_status()
            rows = response.json()
            break
        except requests.RequestException as error:
            last_error = error

    if rows is None:
        raise RuntimeError(
            f"Failed to fetch klines for {symbol} {interval} from Binance public endpoints."
        ) from last_error

    candles = []
    for row in rows:
        candles.append(
            {
                "open_time": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
                "close_time": int(row[6]),
            }
        )
    return candles


def fetch_market_data(symbol: str) -> dict[str, list[dict]]:
    return {
        "1d": fetch_klines(symbol, "1d", 240),
        "4h": fetch_klines(symbol, "4h", 240),
        "1h": fetch_klines(symbol, "1h", 240),
    }
