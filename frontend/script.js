"use strict";
// TaxoWave dashboard — TypeScript source (compiled to script.js via tsc).
// Talks to the FastAPI backend, renders every chart/map/panel, and drives
// the "Re-run pipeline" live console.
// ---------- Palette (mirrors style.css) ----------
const GRID = "rgba(148,196,196,0.10)";
const PALETTE = ["#4FE7C1", "#9C8CF0", "#FF8A65", "#F2C078", "#6FA8DC", "#E58AC0", "#7FD97F", "#C08CE5", "#5CC9C9"];
async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok)
        throw new Error("Failed to load " + url);
    return res.json();
}
async function postJSON(url) {
    const res = await fetch(url, { method: "POST" });
    if (!res.ok)
        throw new Error("Failed to POST " + url);
    return res.json();
}
function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
// =====================================================================
// Ambient particle field (drifting eDNA reads) — background canvas
// =====================================================================
function initAmbientField() {
    const canvas = document.getElementById("bg-canvas");
    if (!canvas)
        return;
    const ctx = canvas.getContext("2d");
    let w = 0, h = 0;
    let particles = [];
    function resize() {
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
    }
    function init() {
        resize();
        const count = Math.min(90, Math.floor(w / 18));
        particles = Array.from({ length: count }, () => ({
            x: Math.random() * w, y: Math.random() * h,
            vx: (Math.random() - 0.5) * 0.15, vy: (Math.random() - 0.5) * 0.15,
            r: Math.random() * 1.6 + 0.6,
        }));
    }
    function step() {
        ctx.clearRect(0, 0, w, h);
        for (const p of particles) {
            p.x += p.vx;
            p.y += p.vy;
            if (p.x < 0 || p.x > w)
                p.vx *= -1;
            if (p.y < 0 || p.y > h)
                p.vy *= -1;
        }
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const a = particles[i], b = particles[j];
                const d = Math.hypot(a.x - b.x, a.y - b.y);
                if (d < 130) {
                    ctx.strokeStyle = `rgba(79,231,193,${0.09 * (1 - d / 130)})`;
                    ctx.lineWidth = 0.5;
                    ctx.beginPath();
                    ctx.moveTo(a.x, a.y);
                    ctx.lineTo(b.x, b.y);
                    ctx.stroke();
                }
            }
        }
        for (const p of particles) {
            ctx.beginPath();
            ctx.fillStyle = "rgba(159,182,180,0.55)";
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fill();
        }
        requestAnimationFrame(step);
    }
    window.addEventListener("resize", resize);
    init();
    step();
}
// =====================================================================
// Count-up
// =====================================================================
function animateCount(el, target, duration = 1200) {
    const start = performance.now();
    function tick(now) {
        const p = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(target * eased).toLocaleString();
        if (p < 1)
            requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
}
// =====================================================================
// Chart instances (recreated on each render so re-runs stay simple)
// =====================================================================
let phylumChart = null;
let groupChart = null;
let topTaxaChart = null;
let map = null;
let markersLayer = null;
let groupChartRotation = 0;
let groupChartRafStarted = false;
Chart.defaults.color = "#9FB6B4";
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 12;
function renderHeroCounters(o) {
    const vals = [o.total_sequences, o.total_stations, o.known_taxa_count, o.novel_cluster_count];
    document.querySelectorAll(".hval").forEach((el, i) => animateCount(el, vals[i]));
}
function renderStatGrid(o) {
    const grid = document.getElementById("stat-grid");
    const stats = [
        [o.total_sequences.toLocaleString(), "ASV sequences processed"],
        [o.total_reads.toLocaleString(), "total sequencing reads"],
        [o.classified_pct + "%", "matched to known taxa"],
        [o.novel_pct + "%", "unmatched — routed to clustering"],
        [String(o.known_taxa_count), "known species identified"],
        [String(o.novel_cluster_count), "candidate novel clusters"],
    ];
    grid.innerHTML = stats.map(([num, lbl]) => `<div class="stat-tile"><div class="num">${num}</div><div class="lbl">${lbl}</div></div>`).join("");
}
function renderPhylumChart(data) {
    if (phylumChart)
        phylumChart.destroy();
    phylumChart = new Chart(document.getElementById("phylumChart"), {
        type: "bar",
        data: {
            labels: data.map((d) => d.phylum),
            datasets: [{
                    data: data.map((d) => d.reads),
                    backgroundColor: data.map((d, i) => d.phylum.includes("Unassigned") ? "#FF8A65" : PALETTE[i % PALETTE.length]),
                    borderRadius: 3, barThickness: 16,
                }],
        },
        options: {
            indexAxis: "y", responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => c.parsed.x.toLocaleString() + " reads" } } },
            scales: { x: { grid: { color: GRID }, ticks: { callback: (v) => Number(v).toLocaleString() } }, y: { grid: { display: false } } },
        },
    });
}
function renderGroupChart(data) {
    if (groupChart)
        groupChart.destroy();
    groupChart = new Chart(document.getElementById("groupChart"), {
        type: "doughnut",
        data: {
            labels: data.map((d) => d.group),
            datasets: [{
                    data: data.map((d) => d.count),
                    backgroundColor: data.map((d, i) => d.group.includes("novel") ? "#FF8A65" : PALETTE[i % PALETTE.length]),
                    borderColor: "#0E2A38", borderWidth: 2,
                }],
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: "62%",
            rotation: groupChartRotation, animation: { duration: 0 },
            plugins: { legend: { position: "bottom", labels: { boxWidth: 10, padding: 14, font: { size: 11 } } } },
        },
    });
    if (!groupChartRafStarted) {
        groupChartRafStarted = true;
        (function spin() {
            groupChartRotation = (groupChartRotation + 0.25) % 360;
            if (groupChart) {
                groupChart.options.rotation = groupChartRotation;
                groupChart.update("none");
            }
            requestAnimationFrame(spin);
        })();
    }
}
function renderTopTaxaChart(data) {
    if (topTaxaChart)
        topTaxaChart.destroy();
    topTaxaChart = new Chart(document.getElementById("topTaxaChart"), {
        type: "bar",
        data: {
            labels: data.map((d) => d.taxon),
            datasets: [{ data: data.map((d) => d.reads), backgroundColor: "#4FE7C1", borderRadius: 3, barThickness: 14 }],
        },
        options: {
            indexAxis: "y", responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => c.parsed.x.toLocaleString() + " reads" } } },
            scales: {
                x: { grid: { color: GRID }, ticks: { callback: (v) => Number(v).toLocaleString() } },
                y: { grid: { display: false }, ticks: { font: { style: "italic" } } },
            },
        },
    });
}
function renderStationList(stations) {
    const el = document.getElementById("station-list");
    el.innerHTML = stations.map((s) => `
    <div class="station-row">
      <div class="srow-top"><span class="sname">${s.station_name}</span><span class="sid">${s.station_id}</span></div>
      <div class="smetrics">
        <span>Shannon <b>${s.shannon}</b></span>
        <span>Richness <b>${s.richness}</b></span>
        <span>Novel <b>${s.novel_taxa}</b></span>
        <span>${s.depth_m}m</span>
      </div>
    </div>
  `).join("");
}
function renderMap(stations) {
    const mapEl = document.getElementById("leafletMap");
    if (!mapEl)
        return;
    if (!map) {
        map = L.map("leafletMap", { zoomControl: true, attributionControl: false }).setView([15.5, 65], 4);
        L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", { maxZoom: 8, minZoom: 3 }).addTo(map);
        markersLayer = L.layerGroup().addTo(map);
    }
    markersLayer.clearLayers();
    const maxShannon = Math.max(...stations.map((s) => s.shannon), 0.01);
    stations.forEach((s) => {
        const intensity = s.shannon / maxShannon;
        const color = intensity > 0.66 ? "#4FE7C1" : intensity > 0.33 ? "#F2C078" : "#FF8A65";
        const radius = 6 + Math.sqrt(s.sequence_count) * 1.4;
        L.circleMarker([s.latitude, s.longitude], { radius, color, weight: 1, fillColor: color, fillOpacity: 0.45 })
            .addTo(markersLayer)
            .bindPopup(`<b>${s.station_name}</b><br>${s.sequence_count} sequences · ${s.depth_m}m depth<br>Shannon ${s.shannon} · Richness ${s.richness}<br>Novel taxa: ${s.novel_taxa}`);
    });
}
function renderClusterCards(clusters) {
    const el = document.getElementById("cluster-cards");
    el.innerHTML = clusters.map((c) => `
    <div class="cluster-card">
      <div class="ctop"><h4>${c.cluster}</h4><span class="novelty">${(c.novelty_score * 100).toFixed(0)}% novel</span></div>
      <div class="cmeta">
        <span>Sequences <b>${c.sequence_count}</b></span>
        <span>Reads <b>${c.total_reads.toLocaleString()}</b></span>
        <span>Stations <b>${c.station_count}</b></span>
      </div>
      <div class="cseq">${c.representative_sequence}</div>
    </div>
  `).join("");
}
let orbitBodies = [];
let orbitRafStarted = false;
function setOrbitData(clusters) {
    const maxCount = Math.max(...clusters.map((c) => c.sequence_count), 1);
    orbitBodies = clusters.map((c, i) => {
        const prev = orbitBodies[i];
        return {
            name: c.cluster,
            color: PALETTE[i % PALETTE.length],
            radius: 38 + c.novelty_score * 150,
            angle: prev ? prev.angle : Math.random() * Math.PI * 2,
            speed: (0.0026 + (i % 5) * 0.0009) * (i % 2 === 0 ? 1 : -1),
            size: 6 + (c.sequence_count / maxCount) * 16,
            count: c.sequence_count,
        };
    });
}
function initClusterOrbit() {
    const canvas = document.getElementById("clusterOrbit");
    if (!canvas)
        return;
    const ctx = canvas.getContext("2d");
    function resize() {
        const rect = canvas.parentElement.getBoundingClientRect();
        canvas.width = rect.width;
        canvas.height = rect.height;
    }
    window.addEventListener("resize", resize);
    resize();
    function draw() {
        const w = canvas.width, h = canvas.height;
        const cx = w / 2, cy = h / 2;
        ctx.clearRect(0, 0, w, h);
        const radii = Array.from(new Set(orbitBodies.map((b) => Math.round(b.radius / 20) * 20)));
        ctx.strokeStyle = "rgba(148,196,196,0.10)";
        ctx.lineWidth = 1;
        radii.forEach((r) => { ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke(); });
        ctx.beginPath();
        ctx.fillStyle = "#0E2A38";
        ctx.arc(cx, cy, 22, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#4FE7C1";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.fillStyle = "#4FE7C1";
        ctx.font = "9px 'IBM Plex Mono', monospace";
        ctx.textAlign = "center";
        ctx.fillText("eDNA", cx, cy - 2);
        ctx.fillText("pool", cx, cy + 9);
        orbitBodies.forEach((b) => {
            b.angle += b.speed;
            const x = cx + Math.cos(b.angle) * b.radius;
            const y = cy + Math.sin(b.angle) * b.radius * 0.55;
            ctx.beginPath();
            ctx.fillStyle = b.color;
            ctx.globalAlpha = 0.92;
            ctx.arc(x, y, b.size, 0, Math.PI * 2);
            ctx.fill();
            ctx.globalAlpha = 1;
            ctx.beginPath();
            ctx.strokeStyle = "rgba(8,28,42,0.6)";
            ctx.lineWidth = 1.5;
            ctx.arc(x, y, b.size, 0, Math.PI * 2);
            ctx.stroke();
        });
        requestAnimationFrame(draw);
    }
    if (!orbitRafStarted) {
        orbitRafStarted = true;
        draw();
    }
}
// =====================================================================
// Full render pass — used both on initial load and after a pipeline re-run
// =====================================================================
function renderReport(report) {
    renderHeroCounters(report.overview);
    renderStatGrid(report.overview);
    renderPhylumChart(report.taxonomy_composition);
    renderGroupChart(report.group_composition);
    renderStationList(report.stations);
    renderMap(report.stations);
    renderTopTaxaChart(report.top_taxa);
    renderClusterCards(report.novel_clusters);
    setOrbitData(report.novel_clusters);
}
// =====================================================================
// Live pipeline console
// =====================================================================
const LOG_STEPS = [
    "→ ingesting ASV sequences from Arabian Sea stations…",
    "→ matching sequences against curated reference taxa (4-mer Jaccard)…",
    "→ embedding unmatched reads as k-mer frequency vectors…",
    "→ clustering the unmatched pool with KMeans (novel-taxa discovery)…",
    "→ scoring biodiversity per station (Shannon · Simpson · Pielou · Chao1)…",
];
function consoleLine(text, cls = "") {
    const line = document.createElement("div");
    line.className = "console-line " + cls;
    line.textContent = text;
    return line;
}
function setStatus(state) {
    const badge = document.getElementById("pipeline-status");
    const dot = badge.querySelector(".status-dot");
    const label = badge.querySelector(".status-label");
    if (state === "idle") {
        label.textContent = "Idle";
        dot.style.background = "#72908D";
    }
    if (state === "running") {
        label.textContent = "Running";
        dot.style.background = "#F2C078";
    }
    if (state === "done") {
        label.textContent = "Complete";
        dot.style.background = "#4FE7C1";
    }
}
async function runPipelineWithConsole() {
    const btn = document.getElementById("run-pipeline-btn");
    const logEl = document.getElementById("console-log");
    btn.disabled = true;
    btn.textContent = "Running…";
    setStatus("running");
    logEl.innerHTML = "";
    logEl.appendChild(consoleLine(`$ TaxoWave run --source obis:arabian-sea --seed random`, "console-cmd"));
    const fetchPromise = postJSON("/api/run-pipeline");
    for (const step of LOG_STEPS) {
        logEl.appendChild(consoleLine(step));
        logEl.scrollTop = logEl.scrollHeight;
        await sleep(340);
    }
    const result = await fetchPromise;
    const o = result.report.overview;
    logEl.appendChild(consoleLine(`✓ pipeline complete in ${result.duration_ms}ms — ${o.total_sequences} sequences · ${o.classified_pct}% matched · ${o.novel_cluster_count} novel clusters flagged (seed ${o.run_seed})`, "console-done"));
    logEl.scrollTop = logEl.scrollHeight;
    renderReport(result.report);
    setStatus("done");
    btn.disabled = false;
    btn.textContent = "Re-run pipeline";
    setTimeout(() => setStatus("idle"), 2600);
}
// =====================================================================
// Custom cursor — soft ring + dot that trail the pointer with easing,
// and expand over interactive elements. No-op on touch devices.
// =====================================================================
function initCustomCursor() {
    if (!window.matchMedia("(pointer: fine)").matches)
        return;
    const ring = document.getElementById("cursor-ring");
    const dot = document.getElementById("cursor-dot");
    if (!ring || !dot)
        return;
    let mx = window.innerWidth / 2, my = window.innerHeight / 2;
    let rx = mx, ry = my;
    let shown = false;
    window.addEventListener("mousemove", (e) => {
        mx = e.clientX;
        my = e.clientY;
        if (!shown) {
            shown = true;
            ring.classList.add("is-visible");
            dot.classList.add("is-visible");
        }
        dot.style.transform = `translate(${mx}px, ${my}px) translate(-50%,-50%)`;
    });
    document.addEventListener("mouseleave", () => {
        ring.classList.remove("is-visible");
        dot.classList.remove("is-visible");
        shown = false;
    });
    function tick() {
        rx += (mx - rx) * 0.16;
        ry += (my - ry) * 0.16;
        ring.style.transform = `translate(${rx}px, ${ry}px) translate(-50%,-50%)`;
        requestAnimationFrame(tick);
    }
    tick();
    const hoverTargets = "a, button, .btn, .station-row, .cluster-card";
    document.addEventListener("mouseover", (e) => {
        const t = e.target;
        if (t.closest(hoverTargets))
            ring.classList.add("is-active");
    });
    document.addEventListener("mouseout", (e) => {
        const t = e.target;
        if (t.closest(hoverTargets))
            ring.classList.remove("is-active");
    });
}
// =====================================================================
// Scroll reveal — fade/rise sections in as they enter the viewport
// =====================================================================
function initScrollReveal() {
    const targets = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window) || targets.length === 0) {
        targets.forEach((t) => t.classList.add("is-visible"));
        return;
    }
    const io = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add("is-visible");
                io.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15, rootMargin: "0px 0px -60px 0px" });
    targets.forEach((t) => io.observe(t));
}
// =====================================================================
// Boot
// =====================================================================
(async function main() {
    initAmbientField();
    initClusterOrbit();
    initCustomCursor();
    initScrollReveal();
    const btn = document.getElementById("run-pipeline-btn");
    if (btn)
        btn.addEventListener("click", () => { runPipelineWithConsole(); });
    let report;
    try {
        report = await getJSON("/api/report");
    }
    catch (e) {
        const sub = document.querySelector(".hero-sub");
        if (sub)
            sub.textContent = "Could not reach the TaxoWave API. Start the backend (uvicorn main:app --reload) and reload this page.";
        return;
    }
    renderReport(report);
    const logEl = document.getElementById("console-log");
    if (logEl) {
        logEl.appendChild(consoleLine(`$ TaxoWave run --source obis:arabian-sea --seed ${report.overview.run_seed}`, "console-cmd"));
        logEl.appendChild(consoleLine(`✓ pipeline complete — ${report.overview.total_sequences} sequences · ${report.overview.classified_pct}% matched · ${report.overview.novel_cluster_count} novel clusters flagged`, "console-done"));
    }
})();