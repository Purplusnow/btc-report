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

function formatSeoulTime(isoString) {
  if (!isoString) {
    return "-";
  }

  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) {
    return isoString;
  }

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

  return `서울 ${seoul}`;
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

function renderStrategyIdeas(items) {
  const element = document.getElementById("strategy-ideas");
  if (!element) {
    return;
  }

  const ideas = Array.isArray(items) ? items : [];
  if (!ideas.length) {
    element.innerHTML = `<div class="strategy-item wait"><p>${FALLBACK_TEXT}</p></div>`;
    return;
  }

  element.innerHTML = ideas.map((idea) => `
    <div class="strategy-item ${idea.side || "wait"}">
      <h3>${idea.label || "전략 아이디어"}</h3>
      <p>${formatReadableParagraphs(`방향: ${idea.direction_label || "-"}`)}</p>
      <p>${formatReadableParagraphs(`조건 요약: ${idea.trigger_text_natural || idea.trigger_text || FALLBACK_TEXT}`)}</p>
      <p>${formatReadableParagraphs(`추적 규칙: ${idea.trigger_text || FALLBACK_TEXT}`)}</p>
      <p>${formatReadableParagraphs(`진입가: ${idea.entry_price || "-"}`)}</p>
      <p>${formatReadableParagraphs(`손절가: ${idea.stop_price || "-"}`)}</p>
      <p>${formatReadableParagraphs(`익절가: ${idea.take_profit || "-"}`)}</p>
      <p>${formatReadableParagraphs(`메모: ${idea.rationale || FALLBACK_TEXT}`)}</p>
      <p>${formatReadableParagraphs(`평가 기준: ${idea.review_note || FALLBACK_TEXT}`)}</p>
    </div>
  `).join("");
}

function renderStrategyMetrics(summary) {
  const element = document.getElementById("strategy-metrics");
  if (!element) {
    return;
  }

  const stats = summary || {};
  element.innerHTML = `
    <div class="metric-row">
      <div class="metric-card"><span>초기 자금</span><strong>$${Number(stats.starting_balance ?? 1000).toFixed(2)}</strong></div>
      <div class="metric-card"><span>현재 잔고</span><strong>$${Number(stats.current_balance ?? 1000).toFixed(2)}</strong></div>
      <div class="metric-card"><span>누적 손익</span><strong>$${Number(stats.cumulative_pnl ?? 0).toFixed(2)}</strong></div>
    </div>
    <div class="metric-row">
      <div class="metric-card"><span>수익률</span><strong>${stats.cumulative_return_pct || "0.00%"}</strong></div>
      <div class="metric-card"><span>승률</span><strong>${stats.win_rate || "0.0%"}</strong></div>
      <div class="metric-card"><span>승 / 패</span><strong>${stats.wins ?? 0} / ${stats.losses ?? 0}</strong></div>
    </div>
    <div class="metric-row">
      <div class="metric-card"><span>대기</span><strong>${stats.pending ?? 0}</strong></div>
      <div class="metric-card"><span>보유중</span><strong>${stats.open ?? 0}</strong></div>
      <div class="metric-card"><span>만료</span><strong>${stats.expired ?? 0}</strong></div>
    </div>
  `;
}

function renderStrategyHistory(items) {
  const element = document.getElementById("strategy-history-list");
  if (!element) {
    return;
  }

  const history = Array.isArray(items) ? items : [];
  if (!history.length) {
    element.innerHTML = `<li class="history-item">${FALLBACK_TEXT}</li>`;
    return;
  }

  element.innerHTML = history.slice(0, 8).map((item) => `
    <li class="history-item">
      <span class="history-meta">${formatSeoulTime(item.created_at)} · ${item.label || "-"} · ${item.status_label || item.status || "-"}</span>
      <strong>${item.symbol || "-"}</strong>
      <p>${item.direction_label || "-"} · 진입 ${item.entry_price || "-"} / 손절 ${item.stop_price || "-"} / 익절 ${item.take_profit || "-"}</p>
      <p>잔고 $${Number(item.balance_before ?? 0).toFixed(2)} → $${Number(item.balance_after ?? 0).toFixed(2)} / 손익 $${Number(item.pnl_amount ?? 0).toFixed(2)}</p>
      <p>${item.outcome_note || item.trigger_text || FALLBACK_TEXT}</p>
    </li>
  `).join("");
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

function renderTrendlines(priceChart, overlays) {
  const trendlines = overlays?.trendlines || [];
  const dashedStyle = window.LightweightCharts?.LineStyle?.LargeDashed ?? 2;

  trendlines.forEach((trendline) => {
    const isSupport = trendline.type === "support";
    const series = priceChart.addLineSeries({
      color: isSupport ? "rgba(31, 122, 90, 0.9)" : "rgba(178, 75, 63, 0.9)",
      lineWidth: 2,
      lineStyle: dashedStyle,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false
    });

    series.setData([
      trendline.start,
      trendline.end
    ]);
  });
}

function createChart(containerId, volumeContainerId, rsiContainerId, candles, overlays) {
  const priceContainer = document.getElementById(containerId);
  const volumeContainer = document.getElementById(volumeContainerId);
  const rsiContainer = document.getElementById(rsiContainerId);

  if (!priceContainer || !volumeContainer || !rsiContainer) {
    return;
  }

  if (!window.LightweightCharts) {
    setChartError(priceContainer, "차트 라이브러리를 불러오지 못했습니다.");
    setChartError(volumeContainer, "거래량 차트를 불러오지 못했습니다.");
    setChartError(rsiContainer, "RSI 차트를 불러오지 못했습니다.");
    return;
  }

  if (!Array.isArray(candles) || candles.length === 0) {
    setChartError(priceContainer, "가격 데이터가 아직 준비되지 않았습니다.");
    setChartError(volumeContainer, "거래량 데이터가 아직 준비되지 않았습니다.");
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

    const volumeChart = LightweightCharts.createChart(volumeContainer, {
      ...commonLayout,
      width: volumeContainer.clientWidth,
      height: volumeContainer.clientHeight
    });

    const volumeSeries = volumeChart.addHistogramSeries({
      priceFormat: { type: "volume" },
      color: "rgba(20, 63, 107, 0.35)"
    });
    volumeSeries.setData(buildVolumeSeries(candles));
    renderTrendlines(priceChart, overlays);
    priceChart.timeScale().fitContent();
    volumeChart.timeScale().fitContent();

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
      volumeChart.applyOptions({
        width: volumeContainer.clientWidth,
        height: volumeContainer.clientHeight
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
    setChartError(volumeContainer, "거래량 차트 렌더링에 실패했습니다.");
    setChartError(rsiContainer, "RSI 차트 렌더링에 실패했습니다.");
  }
}

async function loadPage() {
  const [latestResponse, historyResponse, chartResponse, strategyResponse] = await Promise.all([
    fetch("data/latest.json"),
    fetch("data/history.json"),
    fetch("data/chart_data.json"),
    fetch("data/strategy_history.json")
  ]);

  const latest = await latestResponse.json();
  const history = await historyResponse.json();
  const chartData = await chartResponse.json();
  const strategyHistory = await strategyResponse.json();

  const symbol = latest.symbol || "BTCUSDT";
  document.getElementById("page-title").textContent = formatReportTitle(symbol);
  setText("summary", formatReadableParagraphs(latest.summary));
  setText("updated-at", formatSeoulTime(latest.updated_at));
  setText("daily-view", formatReadableParagraphs(latest.daily_view));
  setText("h4-view", formatReadableParagraphs(latest.h4_view));
  setText("h1-view", formatReadableParagraphs(latest.h1_view));
  setText("conclusion", formatReadableParagraphs(latest.conclusion));
  setText("disclaimer", latest.disclaimer);
  renderStrategyIdeas(latest.strategy_ideas || []);
  renderStrategyMetrics(latest.strategy_summary || {});
  renderStrategyHistory(strategyHistory || []);

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
      <span class="history-meta">${formatSeoulTime(item.updated_at)}</span>
      <strong>${item.symbol || symbol}</strong>
      <p>${formatReadableParagraphs(item.summary || FALLBACK_TEXT)}</p>
    `;
    historyList.appendChild(li);
  });

  if (!historyList.children.length) {
    historyList.innerHTML = `<li class="history-item">${FALLBACK_TEXT}</li>`;
  }

  createChart(
    "chart-1d-price",
    "chart-1d-volume",
    "chart-1d-rsi",
    chartData.timeframes?.["1d"] || [],
    chartData.overlays?.["1d"] || {}
  );
  createChart(
    "chart-4h-price",
    "chart-4h-volume",
    "chart-4h-rsi",
    chartData.timeframes?.["4h"] || [],
    chartData.overlays?.["4h"] || {}
  );
  createChart(
    "chart-1h-price",
    "chart-1h-volume",
    "chart-1h-rsi",
    chartData.timeframes?.["1h"] || [],
    chartData.overlays?.["1h"] || {}
  );
}

loadPage().catch((error) => {
  console.error("Failed to load report data.", error);
});
