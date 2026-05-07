const FALLBACK_TEXT = "데이터가 준비되면 이 영역이 자동으로 갱신됩니다.";
const CHART_ERROR_TEXT = "차트 라이브러리 또는 데이터 로딩 문제로 시각화에 실패했습니다.";

function formatList(items, emptyText = "데이터 대기 중") {
  if (!Array.isArray(items) || items.length === 0) {
    return `<li>${emptyText}</li>`;
  }

  return items.map((item) => `<li>${item}</li>`).join("");
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = value || FALLBACK_TEXT;
  }
}

function formatReadableParagraphs(value) {
  if (!value || typeof value !== "string") {
    return value;
  }

  return value
    .replace(/([.!?])\s+/g, "$1\n\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function formatDualTimezone(isoString) {
  if (!isoString) {
    return "-";
  }

  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) {
    return isoString;
  }

  const utc = new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC"
  }).format(parsed).replace(",", "");

  const seoul = new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Asia/Seoul"
  }).format(parsed).replace(",", "");

  return `UTC ${utc}\n서울 ${seoul}`;
}

function formatReportTitle(symbol) {
  if (symbol === "BTCUSDT") {
    return "비트코인";
  }

  return symbol || "암호화폐";
}

function setList(id, items, emptyText) {
  const element = document.getElementById(id);
  if (element) {
    element.innerHTML = formatList(items, emptyText);
  }
}

function scenarioTargets(label, values) {
  if (!Array.isArray(values) || values.length === 0) {
    return `${label}: 확인 대기`;
  }

  return `${label}: ${values.join(" / ")}`;
}

function buildChartSeries(dataPoints) {
  return (dataPoints || []).map((candle) => ({
    time: candle.time,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close
  }));
}

function buildVolumeSeries(dataPoints) {
  return (dataPoints || []).map((candle) => ({
    time: candle.time,
    value: candle.volume,
    color: candle.close >= candle.open ? "rgba(31, 122, 90, 0.55)" : "rgba(178, 75, 63, 0.55)"
  }));
}

function buildRsiSeries(dataPoints) {
  return (dataPoints || [])
    .filter((candle) => typeof candle.rsi === "number")
    .map((candle) => ({
      time: candle.time,
      value: candle.rsi
    }));
}

function setChartError(container, message = CHART_ERROR_TEXT) {
  if (!container) {
    return;
  }

  container.innerHTML = `<div class="chart-empty">${message}</div>`;
}

function createChart(containerId, rsiContainerId, candles) {
  const priceContainer = document.getElementById(containerId);
  const rsiContainer = document.getElementById(rsiContainerId);

  if (!priceContainer || !rsiContainer) {
    return;
  }

  if (!window.LightweightCharts) {
    setChartError(priceContainer, "차트 라이브러리를 불러오지 못했습니다.");
    setChartError(rsiContainer, "RSI 차트를 불러오지 못했습니다.");
    return;
  }

  if (!Array.isArray(candles) || candles.length === 0) {
    setChartError(priceContainer, "가격 데이터가 아직 준비되지 않았습니다.");
    setChartError(rsiContainer, "RSI 데이터가 아직 준비되지 않았습니다.");
    return;
  }

  try {
    const commonLayout = {
      layout: {
        background: { color: "transparent" },
        textColor: "#4f5660"
      },
      grid: {
        vertLines: { color: "rgba(24, 33, 43, 0.06)" },
        horzLines: { color: "rgba(24, 33, 43, 0.06)" }
      },
      rightPriceScale: {
        borderColor: "rgba(24, 33, 43, 0.12)"
      },
      timeScale: {
        borderColor: "rgba(24, 33, 43, 0.12)"
      }
    };

    const priceChart = LightweightCharts.createChart(priceContainer, {
      ...commonLayout,
      width: priceContainer.clientWidth,
      height: priceContainer.clientHeight
    });

    const candleSeries = priceChart.addCandlestickSeries({
      upColor: "#1f7a5a",
      downColor: "#b24b3f",
      wickUpColor: "#1f7a5a",
      wickDownColor: "#b24b3f",
      borderVisible: false
    });
    candleSeries.setData(buildChartSeries(candles));

    const volumeSeries = priceChart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "",
      scaleMargins: {
        top: 0.78,
        bottom: 0
      }
    });
    volumeSeries.setData(buildVolumeSeries(candles));
    priceChart.timeScale().fitContent();

    const rsiChart = LightweightCharts.createChart(rsiContainer, {
      ...commonLayout,
      width: rsiContainer.clientWidth,
      height: rsiContainer.clientHeight
    });

    const rsiSeries = rsiChart.addLineSeries({
      color: "#143f6b",
      lineWidth: 2
    });
    rsiSeries.setData(buildRsiSeries(candles));

    const rsi70 = rsiChart.addLineSeries({
      color: "rgba(178, 75, 63, 0.5)",
      lineWidth: 1
    });
    const rsi30 = rsiChart.addLineSeries({
      color: "rgba(31, 122, 90, 0.5)",
      lineWidth: 1
    });

    const rangeLines = candles.map((candle) => candle.time);
    rsi70.setData(rangeLines.map((time) => ({ time, value: 70 })));
    rsi30.setData(rangeLines.map((time) => ({ time, value: 30 })));
    rsiChart.timeScale().fitContent();

    function resizeCharts() {
      priceChart.applyOptions({
        width: priceContainer.clientWidth,
        height: priceContainer.clientHeight
      });
      rsiChart.applyOptions({
        width: rsiContainer.clientWidth,
        height: rsiContainer.clientHeight
      });
    }

    window.addEventListener("resize", resizeCharts);
  } catch (error) {
    console.error(`Failed to render chart for ${containerId}.`, error);
    setChartError(priceContainer);
    setChartError(rsiContainer, "RSI 차트 렌더링에 실패했습니다.");
  }
}

async function loadPage() {
  const [latestResponse, historyResponse, chartResponse] = await Promise.all([
    fetch("data/latest.json"),
    fetch("data/history.json"),
    fetch("data/chart_data.json")
  ]);

  const latest = await latestResponse.json();
  const history = await historyResponse.json();
  const chartData = await chartResponse.json();

  const symbol = latest.symbol || "BTCUSDT";
  document.getElementById("page-title").textContent = formatReportTitle(symbol);
  setText("summary", formatReadableParagraphs(latest.summary));
  setText("updated-at", formatDualTimezone(latest.updated_at));
  setText("daily-view", formatReadableParagraphs(latest.daily_view));
  setText("h4-view", formatReadableParagraphs(latest.h4_view));
  setText("h1-view", formatReadableParagraphs(latest.h1_view));
  setText("conclusion", formatReadableParagraphs(latest.conclusion));
  setText("disclaimer", latest.disclaimer);

  setList("support-levels", latest.key_levels?.support, "분석 대기 중");
  setList("resistance-levels", latest.key_levels?.resistance, "분석 대기 중");
  setList("invalidation-levels", latest.key_levels?.invalidations, "분석 대기 중");

  setText("bullish-condition", formatReadableParagraphs(`조건: ${latest.scenarios?.bullish?.condition || FALLBACK_TEXT}`));
  setText("bullish-targets", scenarioTargets("목표", latest.scenarios?.bullish?.targets));
  setText("bullish-invalidation", formatReadableParagraphs(`무효화: ${latest.scenarios?.bullish?.invalidation || FALLBACK_TEXT}`));
  setText("bullish-probability", formatReadableParagraphs(`평가: ${latest.scenarios?.bullish?.probability_comment || FALLBACK_TEXT}`));

  setText("bearish-condition", formatReadableParagraphs(`조건: ${latest.scenarios?.bearish?.condition || FALLBACK_TEXT}`));
  setText("bearish-targets", scenarioTargets("목표", latest.scenarios?.bearish?.targets));
  setText("bearish-invalidation", formatReadableParagraphs(`무효화: ${latest.scenarios?.bearish?.invalidation || FALLBACK_TEXT}`));
  setText("bearish-probability", formatReadableParagraphs(`평가: ${latest.scenarios?.bearish?.probability_comment || FALLBACK_TEXT}`));

  setText("neutral-condition", formatReadableParagraphs(`조건: ${latest.scenarios?.neutral?.condition || FALLBACK_TEXT}`));
  setText("neutral-range", scenarioTargets("범위", latest.scenarios?.neutral?.range));
  setText("neutral-invalidation", formatReadableParagraphs(`무효화: ${latest.scenarios?.neutral?.invalidation || FALLBACK_TEXT}`));
  setText("neutral-probability", formatReadableParagraphs(`평가: ${latest.scenarios?.neutral?.probability_comment || FALLBACK_TEXT}`));

  const historyList = document.getElementById("history-list");
  historyList.innerHTML = "";

  (history || []).slice(0, 8).forEach((item) => {
    const li = document.createElement("li");
    li.className = "history-item";
    li.innerHTML = `
      <span class="history-meta">${formatDualTimezone(item.updated_at)}</span>
      <strong>${item.symbol || symbol}</strong>
      <p>${formatReadableParagraphs(item.summary || FALLBACK_TEXT)}</p>
    `;
    historyList.appendChild(li);
  });

  if (!historyList.children.length) {
    historyList.innerHTML = `<li class="history-item">${FALLBACK_TEXT}</li>`;
  }

  createChart("chart-1d-price", "chart-1d-rsi", chartData.timeframes?.["1d"] || []);
  createChart("chart-4h-price", "chart-4h-rsi", chartData.timeframes?.["4h"] || []);
  createChart("chart-1h-price", "chart-1h-rsi", chartData.timeframes?.["1h"] || []);
}

loadPage().catch((error) => {
  console.error("Failed to load report data.", error);
});
