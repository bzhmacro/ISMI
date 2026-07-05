/* app.js (TEMPLATE) -- UI driver: load JSON, drive the worker, plot, correlate.
 * Falls back to the precomputed baseline if the worker can't start or the JSON
 * schema is old (graceful degradation). */
"use strict";

let DATA = null, worker = null, reqId = 0;

async function boot() {
  DATA = await fetch("data/index.json").then(r => r.json());
  document.getElementById("freshness").textContent =
    `data through ${DATA.data_through} · index recomputed live in your browser`;

  const sel = document.getElementById("backbone");
  Object.keys(DATA.backbones || {}).forEach(b => {
    const o = document.createElement("option"); o.value = o.textContent = b; sel.appendChild(o);
  });

  try {
    worker = new Worker("worker.js");
    worker.onmessage = e => { if (e.data.type === "result") draw(e.data); };
    worker.postMessage({ type: "init", panels: DATA.backbones });
    document.querySelectorAll("#controls input,#controls select")
      .forEach(el => el.addEventListener("input", recompute));
    recompute();
  } catch (err) {
    degrade();   // worker unavailable -> show the precomputed baseline, hide live controls
  }
}

function recompute() {
  const params = {
    ar: +document.getElementById("ar").value,
    W: +document.getElementById("W").value,
    k: +document.getElementById("k").value,
    scheme: document.getElementById("scheme").value,
  };
  worker.postMessage({ type: "compute", id: ++reqId,
                       backbone: document.getElementById("backbone").value, params });
}

function draw(res) {
  const dates = (DATA.author.dates) || [];
  Plotly.react("chart", [
    { x: dates, y: res.Index, name: "Index (live)", mode: "lines" },
    DATA.author.values && { x: dates, y: DATA.author.values, name: "Author", mode: "lines" },
  ].filter(Boolean), { margin: { t: 10 } }, { displayModeBar: false });
  // document.getElementById("corr").textContent = `corr w/ author: ${corr(...).toFixed(3)}`;
}

function degrade() {
  document.getElementById("controls").style.display = "none";
  const b = DATA.baseline && Object.values(DATA.baseline)[0];
  if (b) draw({ Index: b.Index.values });
}

boot();
