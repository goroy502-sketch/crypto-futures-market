
document.addEventListener("DOMContentLoaded", async () => {
  const body = document.getElementById("signals-body");
  const status = document.getElementById("status");

  if (!body) {
    console.error("Missing table body: signals-body");
    if (status) status.textContent =
      "Table setup missing. Update index.html first.";
    return;
  }

  try {
    if (status) status.textContent = "Loading scanner results...";

    const response = await fetch("signals.csv?t=" + Date.now());

    if (!response.ok) {
      throw new Error("signals.csv not found: " + response.status);
    }

    const csv = await response.text();
    const lines = csv.trim().split(/\r?\n/);

    if (lines.length < 2) {
      throw new Error("No scanner results found");
    }

    const headers = lines[0].split(",").map(x => x.trim());
    const rows = lines.slice(1).map(line => {
      const values = line.split(",");
      return Object.fromEntries(
        headers.map((header, i) => [header, values[i] ?? ""])
      );
    });

    body.replaceChildren();

    rows.forEach(row => {
      const tr = document.createElement("tr");

      [
        row.symbol,
        row.price,
        row.signal,
        row.rsi,
        row.adx,
        row.macd,
        row.emaTrend,
        row.updatedAt
      ].forEach(value => {
        const td = document.createElement("td");
        td.textContent = value || "—";
        tr.appendChild(td);
      });

      body.appendChild(tr);
    });

    if (status) {
      status.textContent = `Loaded ${rows.length} scanner results`;
    }
  } catch (error) {
    console.error(error);
    if (status) status.textContent = error.message;
  }
});
