"""
main.py
-------
FastAPI application exposing the eDNA taxonomy/biodiversity pipeline as a
JSON API, and serving the ANALYTICA frontend dashboard as static files from
the same process. Run with:

    uvicorn main:app --reload --port 8000

then open http://localhost:8000 in a browser.
"""

import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from pipeline import run_pipeline, build_report

app = FastAPI(title="ANALYTICA — eDNA Taxonomy & Biodiversity API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Run the pipeline once at startup and cache the report in memory. A real
# deployment would trigger this on new-data-upload instead of at boot.
_RECORDS, _SEED = run_pipeline()
_REPORT = build_report(_RECORDS, seed=_SEED)
_LAST_RUN_MS = 0

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/api/overview")
def get_overview():
    return _REPORT["overview"]


@app.get("/api/taxonomy-composition")
def get_taxonomy_composition():
    return _REPORT["taxonomy_composition"]


@app.get("/api/group-composition")
def get_group_composition():
    return _REPORT["group_composition"]


@app.get("/api/stations")
def get_stations():
    return _REPORT["stations"]


@app.get("/api/novel-clusters")
def get_novel_clusters():
    return _REPORT["novel_clusters"]


@app.get("/api/top-taxa")
def get_top_taxa():
    return _REPORT["top_taxa"]


@app.get("/api/report")
def get_full_report():
    """Single call returning everything the dashboard needs."""
    return _REPORT


@app.post("/api/run-pipeline")
def rerun_pipeline():
    """Re-runs the full pipeline against a fresh (randomly-seeded) batch of
    synthetic Arabian Sea eDNA sequences — ingestion, k-mer classification,
    novel-taxa clustering and diversity scoring — and replaces the cached
    report. This is what the dashboard's "Re-run pipeline" button calls."""
    global _RECORDS, _SEED, _REPORT, _LAST_RUN_MS
    t0 = time.perf_counter()
    _RECORDS, _SEED = run_pipeline()
    _REPORT = build_report(_RECORDS, seed=_SEED)
    _LAST_RUN_MS = round((time.perf_counter() - t0) * 1000)
    return {"duration_ms": _LAST_RUN_MS, "report": _REPORT}


@app.get("/api/sequences")
def get_sequences(limit: int = 200):
    """Raw ASV-level records (paginated) for inspection/download."""
    slim = [
        {
            "asv_id": r["asv_id"],
            "station_id": r["station_id"],
            "station_name": r["station_name"],
            "taxon": r["taxon"],
            "status": r["status"],
            "confidence": r["confidence"],
            "read_count": r["read_count"],
        }
        for r in _RECORDS[:limit]
    ]
    return {"count": len(_RECORDS), "records": slim}


# ---- Serve the frontend dashboard ----
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")
