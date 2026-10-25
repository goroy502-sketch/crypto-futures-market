
document.addEventListener("DOMContentLoaded", () => {
  const body = document.getElementById("signals-body");
  const status = document.getElementById("status");
  const count = document.getElementById("count");
  const search = document.getElementById("search");
  const filter = document.getElementById("signalFilter");
  const refresh = document.getElementById("refresh");

  let allRows = [];

  const columns = [
    "symbol", "price", "signal", "signalScore", "rsi", "adx",
    "macd", "macdSignal", "emaTrend", "volume",
    "volumeBreakout", "bbUpper", "bbLower", "atr",
    "timeframe", "updatedAt"
  ];

  function parseCSV(text) {
    const lines = text.trim().split(/\r?\n/);
    if (lines.length < 2) return [];

    const headers = lines[0].split(",").map(x => x.trim());

    return lines.slice(1).map(line => {
      const values = line.split(",");
      const row = {};
      headers.forEach((header, i) => {
        row[header] = (values[i] || "").trim();
      });
      return row;
    });
  }

  function render() {
    const query = search.value.trim().toUpperCase();
    const selected = filter.value;

    const rows = allRows.filter(row => {
      const matchesCoin =
        (row.symbol || "").toUpperCase().includes(query);

      const signal = (row.signal || "").toUpperCase();
      const matchesSignal =
        selected === "ALL" || signal.includes(selected);

      return matchesCoin && matchesSignal;
    });

    body.replaceChildren();

    rows.forEach(row => {
      const tr = document.createElement("tr");

      columns.forEach(key => {
        const td = document.createElement("td");
        td.textContent = row[key] || "—";

        if (key === "signal" || key === "emaTrend") {
          const value = (row[key] || "").toUpperCase();
          td.className = value.includes("BULLISH")
            ? "bull"
            : value.includes("BEARISH")
              ? "bear"
              : "neutral";
        }

        tr.appendChild(td);
      });

      body.appendChild(tr);
    });

    count.textContent =
      `Showing ${rows.length} of ${allRows.length} coins`;
  }

  async function loadData() {
    status.textContent = "Loading scanner results...";
    refresh.disabled = true;

    try {
      const response = await fetch(
        "signals.csv?t=" + Date.now(),
        { cache: "no-store" }
      );

      if (!response.ok) {
        throw new Error("CSV loading failed: HTTP " + response.status);
      }

      const text = await response.text();
      allRows = parseCSV(text);

      if (!allRows.length) {
        throw new Error("CSV is empty or has no data rows");
      }

      render();
      status.textContent = "Scanner data loaded successfully";
    } catch (error) {
      status.textContent = error.message;
      count.textContent = "Data could not be loaded";
      console.error(error);
    } finally {
      refresh.disabled = false;
    }
  }

  search.addEventListener("input", render);
  filter.addEventListener("change", render);
  refresh.addEventListener("click", loadData);

  loadData();
});
