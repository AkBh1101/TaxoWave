# TaxoWave — eDNA Taxonomy & Biodiversity Platform

Classifies taxonomic diversity and assesses marine biodiversity from
environmental DNA (eDNA) recovered from Arabian Sea water samples — and,
unlike a plain BLAST/alignment pipeline, **keeps and clusters the sequences
that don't match anything in a reference database** instead of discarding
them, so undocumented or cryptic species show up as flagged candidates
instead of disappearing.

Built against the shape of an OBIS (Ocean Biodiversity Information System)
Arabian Sea eDNA export. A synthetic-but-structurally-realistic dataset is
bundled (`backend/data_generator.py`) so the whole pipeline runs end-to-end
out of the box — swap it for a real OBIS/DarwinCore loader to run on live
data; every downstream function consumes the same fields.

## Project structure

```
TaxoWave/
├── backend/
│   ├── main.py             FastAPI app — API routes + serves the frontend
│   ├── pipeline.py         k-mer classification, novel-taxa clustering, diversity metrics
│   ├── data_generator.py   Synthetic OBIS-style Arabian Sea eDNA dataset
│   └── requirements.txt
├── frontend/
│   ├── index.html          Dashboard markup (Tailwind + custom "deep water" system)
│   ├── style.css           Hand-built visual system: waves, particle field, console, orbit
│   ├── tailwind.css        Precompiled Tailwind output (utility classes, preflight off)
│   ├── script.ts           TypeScript source — typed API models + all rendering logic
│   ├── script.js           Compiled output of script.ts (what the browser actually loads)
│   ├── tsconfig.json
│   └── vendor/              Self-hosted Chart.js + Leaflet (no CDN dependency at demo time)
└── README.md
```

## Run it

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000** — the same FastAPI process serves both the
JSON API and the dashboard, so there's nothing else to start.

If you edit `frontend/script.ts`, recompile it before reloading the page:

```bash
cd frontend
npx tsc -p tsconfig.json
```

(`script.js` is committed pre-compiled, so this is only needed if you change
the TypeScript source. Tailwind's output is likewise pre-built into
`tailwind.css` — regenerate it with `npx tailwindcss -i input.css -o
tailwind.css --minify` from a directory with `tailwindcss` installed and a
config pointing at `index.html`/`script.ts` if you add new utility classes.)

## Live pipeline re-runs

The dashboard isn't a static snapshot. Its **Live Run** section (top of the
page) has a *Re-run pipeline* button that calls `POST /api/run-pipeline` —
this re-executes the full pipeline (ingest → classify → cluster → score)
against a freshly-seeded batch of synthetic sequences, in real time, and the
whole dashboard (counters, charts, map, cluster cards, orbit visualization)
re-renders with the new numbers when it completes. The console panel streams
real progress lines while the request is in flight and reports the actual
server-side run time and random seed used.

## How the pipeline works

1. **Ingest & clean** — ASV (Amplicon Sequence Variant) records come in with
   station, depth, and read-count metadata.
2. **Reference match** — each sequence is compared against a curated set of
   Arabian Sea reference taxa using 4-mer Jaccard similarity. A confident
   hit (similarity ≥ 0.42) gets a species name, phylum, and confidence score.
3. **Cluster the unmatched** — sequences below that threshold are embedded
   as 256-dimensional k-mer frequency vectors and clustered with KMeans
   (cluster count scaled to pool size). This is the part that finds species
   no database has a name for: sequences from the same undescribed organism
   still group together even with zero reference hits.
4. **Score biodiversity** — per station: richness, Shannon diversity,
   Simpson's index, Pielou evenness, and Chao1 estimated richness, computed
   across both known taxa and novel clusters together.
5. **Surface for review** — novel clusters are ranked by size and a novelty
   score (`1 − best reference similarity`) so a biologist can prioritize
   which ones are worth targeted follow-up sequencing.

## API

| Endpoint | Returns |
|---|---|
| `GET /api/report` | everything below, in one call (what the dashboard uses) |
| `POST /api/run-pipeline` | re-runs the full pipeline on a fresh random seed, returns `{duration_ms, report}` |
| `GET /api/overview` | headline counts: sequences, stations, % classified/novel |
| `GET /api/taxonomy-composition` | reads per phylum |
| `GET /api/group-composition` | ASV counts per organism group |
| `GET /api/stations` | per-station diversity metrics + coordinates |
| `GET /api/novel-clusters` | candidate novel taxa, ranked, with PCA points |
| `GET /api/top-taxa` | best-matched known species by read count |
| `GET /api/sequences?limit=` | raw ASV-level records |

## Visual design notes

- **Waves & particle field** — the hero background layers an animated
  drifting-particle canvas (each dot is a stand-in for an eDNA read) with two
  CSS-animated SVG wave paths, in the same "abyss + bioluminescent cyan"
  palette as the rest of the dashboard.
- **Cluster orbits** — each novel-taxon cluster is drawn as a body
  continuously revolving around a central "eDNA pool" core: orbital radius
  encodes novelty score, size encodes sequence count. Pure canvas 2D,
  `requestAnimationFrame`-driven, no chart library needed.
- **Continuously-rotating donut** — the organism-groups chart is a normal
  Chart.js doughnut whose `rotation` option is incremented every animation
  frame, so it spins slowly and continuously rather than sitting static.
- **Tailwind** is used for the interactive components added on top of the
  hand-built design system (the pipeline console panel, status badge, run
  button) — `corePlugins.preflight` is disabled in `tailwind.config.js` so it
  doesn't fight with the existing hand-tuned CSS reset.

## What this brings to the table

- **Solves the reference-database bias.** Most eDNA tools only ever report
  what's already catalogued. Arabian Sea eDNA in particular is
  under-referenced — a large share of real-world reads come back with no
  confident match. This pipeline turns that "unclassified" bucket into a
  ranked discovery list instead of a dead end.
- **Minutes, not days.** Manual taxonomic assignment from raw sequence data
  is slow, expert-bottlenecked work. This gives a marine biologist a
  diversity snapshot and a novel-taxa shortlist in one pipeline run.
- **Standard, defensible ecology metrics.** Shannon, Simpson, Pielou, and
  Chao1 are the metrics biodiversity assessments are actually graded on —
  not a custom score.
- **Region-agnostic.** Nothing here is Arabian-Sea-specific except the
  bundled reference set and station list; point it at another OBIS export
  and the same pipeline runs.
- **Policy-actionable.** Per-station richness and novel-taxa counts map
  directly onto conservation prioritization, invasive-species early
  warning, and ecosystem health tracking.

## Extending to a real OBIS dataset

Replace `generate_dataset()` in `backend/data_generator.py` with a loader
that reads an OBIS DarwinCore Archive (occurrence + DNA-derived-data
extension) and returns the same record shape: `asv_id`, `station_id`,
`station_name`, `latitude`, `longitude`, `depth_m`, `sequence`,
`read_count`. `pipeline.py` needs no changes. For production-scale
reference matching, swap the k-mer Jaccard matcher for a proper aligner
(BLAST, VSEARCH) or a pretrained DNA embedding model (DNABERT, Nucleotide
Transformer) feeding the same clustering step.
