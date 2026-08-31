"""
pipeline.py
-----------
The analytical core: reference-based taxonomic classification for sequences
that resemble known Arabian Sea taxa, unsupervised clustering (k-mer
embedding + KMeans) for sequences that don't match anything in the reference
set, and classic ecological diversity statistics computed per station.

This is the part of the project that answers the brief directly: most eDNA
tools stop at "no BLAST hit -> discard", which silently throws away the
undocumented / cryptic species that matter most for biodiversity discovery.
Here, unmatched sequences are embedded and clustered instead, so they surface
as "Novel Cluster N" candidates for a biologist to follow up on.
"""

import math
import itertools
import random as _random
from collections import Counter, defaultdict

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from data_generator import generate_dataset

K = 4  # k-mer size for both reference matching and novel-taxa embedding
MATCH_THRESHOLD = 0.42  # Jaccard similarity below this -> "unclassified"


def random_seed():
    return _random.randint(1, 999_999)


# ---------------------------------------------------------------------------
# k-mer utilities
# ---------------------------------------------------------------------------
def kmer_set(seq: str, k: int = K):
    return {seq[i:i+k] for i in range(len(seq) - k + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


ALL_KMERS = ["".join(p) for p in itertools.product("ACGT", repeat=K)]
KMER_INDEX = {kmer: i for i, kmer in enumerate(ALL_KMERS)}


def kmer_frequency_vector(seq: str, k: int = K) -> np.ndarray:
    vec = np.zeros(len(ALL_KMERS), dtype=np.float64)
    n = 0
    for i in range(len(seq) - k + 1):
        idx = KMER_INDEX.get(seq[i:i+k])
        if idx is not None:
            vec[idx] += 1
            n += 1
    if n > 0:
        vec /= n
    return vec


# ---------------------------------------------------------------------------
# Diversity metrics
# ---------------------------------------------------------------------------
def shannon_index(counts):
    total = sum(counts)
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            h -= p * math.log(p)
    return round(h, 4)


def simpson_index(counts):
    total = sum(counts)
    if total <= 1:
        return 0.0
    d = sum(c * (c - 1) for c in counts) / (total * (total - 1))
    return round(1 - d, 4)


def pielou_evenness(shannon, richness):
    if richness <= 1:
        return 0.0
    return round(shannon / math.log(richness), 4)


def chao1(counts):
    """Chao1 richness estimator: observed richness + correction for rare
    (singleton/doubleton) taxa, which approximates how many more taxa likely
    exist in the true community beyond what was sampled."""
    s_obs = sum(1 for c in counts if c > 0)
    f1 = sum(1 for c in counts if c == 1)
    f2 = sum(1 for c in counts if c == 2)
    if f2 == 0:
        return round(s_obs + (f1 * (f1 - 1)) / 2, 2)
    return round(s_obs + (f1 ** 2) / (2 * f2), 2)


# ---------------------------------------------------------------------------
# Main pipeline: runs once at boot, cached in-process by main.py; can be
# re-invoked on demand (e.g. from the dashboard's "Re-run pipeline" button)
# with a fresh random seed to simulate a new batch of water samples.
# ---------------------------------------------------------------------------
def run_pipeline(seed=None):
    if seed is None:
        seed = random_seed()
    records, reference_seqs, reference_taxa = generate_dataset(seed=seed)

    ref_kmers = {name: kmer_set(seq) for name, seq in reference_seqs.items()}
    taxon_meta = {name: (phylum, group) for name, phylum, group in reference_taxa}

    unmatched = []
    for rec in records:
        seq_kmers = kmer_set(rec["sequence"])
        best_name, best_score = None, 0.0
        for name, kset in ref_kmers.items():
            score = jaccard(seq_kmers, kset)
            if score > best_score:
                best_name, best_score = name, score

        if best_score >= MATCH_THRESHOLD:
            phylum, group = taxon_meta[best_name]
            rec["taxon"] = best_name
            rec["phylum"] = phylum
            rec["group"] = group
            rec["confidence"] = round(best_score, 3)
            rec["status"] = "classified"
        else:
            rec["taxon"] = None
            rec["confidence"] = round(best_score, 3)
            rec["status"] = "unclassified"
            unmatched.append(rec)

    # ---- Novel taxa detection on the unclassified pool ----
    if len(unmatched) >= 4:
        X = np.array([kmer_frequency_vector(r["sequence"]) for r in unmatched])
        n_clusters = max(2, min(9, len(unmatched) // 8))
        km = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
        labels = km.fit_predict(X)

        # 2D projection purely for the frontend scatter plot
        pca = PCA(n_components=2, random_state=42)
        coords = pca.fit_transform(X)

        for rec, label, xy in zip(unmatched, labels, coords):
            rec["taxon"] = f"Novel Cluster {label + 1}"
            rec["group"] = "Putative novel taxon"
            rec["phylum"] = "Unassigned"
            rec["cluster_id"] = int(label)
            rec["pca_x"] = round(float(xy[0]), 4)
            rec["pca_y"] = round(float(xy[1]), 4)
    else:
        for rec in unmatched:
            rec["taxon"] = "Novel Cluster 1"
            rec["group"] = "Putative novel taxon"
            rec["phylum"] = "Unassigned"
            rec["cluster_id"] = 0
            rec["pca_x"], rec["pca_y"] = 0.0, 0.0

    return records, seed


def build_report(records, seed=None):
    total_seqs = len(records)
    classified = [r for r in records if r["status"] == "classified"]
    novel = [r for r in records if r["status"] == "unclassified"]

    # --- overview ---
    unique_known_taxa = len({r["taxon"] for r in classified})
    unique_novel_clusters = len({r["taxon"] for r in novel})
    overview = {
        "run_seed": seed,
        "total_sequences": total_seqs,
        "total_reads": sum(r["read_count"] for r in records),
        "total_stations": len({r["station_id"] for r in records}),
        "classified_count": len(classified),
        "novel_count": len(novel),
        "classified_pct": round(100 * len(classified) / total_seqs, 1),
        "novel_pct": round(100 * len(novel) / total_seqs, 1),
        "known_taxa_count": unique_known_taxa,
        "novel_cluster_count": unique_novel_clusters,
        "total_taxonomic_units": unique_known_taxa + unique_novel_clusters,
    }

    # --- taxonomy composition (by phylum, read-weighted) ---
    phylum_reads = Counter()
    for r in classified:
        phylum_reads[r["phylum"]] += r["read_count"]
    phylum_reads["Unassigned (novel)"] = sum(r["read_count"] for r in novel)
    taxonomy_composition = [
        {"phylum": k, "reads": v} for k, v in
        sorted(phylum_reads.items(), key=lambda kv: -kv[1])
    ]

    # --- group composition (Fish / Zooplankton / Phytoplankton / etc.) ---
    group_counts = Counter(r["group"] for r in classified)
    group_counts["Putative novel taxon"] = len(novel)
    group_composition = [
        {"group": k, "count": v} for k, v in
        sorted(group_counts.items(), key=lambda kv: -kv[1])
    ]

    # --- per-station diversity ---
    by_station = defaultdict(list)
    for r in records:
        by_station[r["station_id"]].append(r)

    stations = []
    for sid, recs in by_station.items():
        meta = recs[0]
        taxon_counts = Counter(r["taxon"] for r in recs)
        counts = list(taxon_counts.values())
        richness = len(taxon_counts)
        shannon = shannon_index(counts)
        stations.append({
            "station_id": sid,
            "station_name": meta["station_name"],
            "latitude": round(meta["latitude"], 3),
            "longitude": round(meta["longitude"], 3),
            "depth_m": meta["depth_m"],
            "sequence_count": len(recs),
            "richness": richness,
            "shannon": shannon,
            "simpson": simpson_index(counts),
            "evenness": pielou_evenness(shannon, richness),
            "chao1": chao1(counts),
            "novel_taxa": len({r["taxon"] for r in recs if r["status"] == "unclassified"}),
        })
    stations.sort(key=lambda s: -s["shannon"])

    # --- novel clusters detail ---
    by_cluster = defaultdict(list)
    for r in novel:
        by_cluster[r["taxon"]].append(r)

    novel_clusters = []
    for cname, recs in by_cluster.items():
        avg_conf = sum(r["confidence"] for r in recs) / len(recs)
        stations_hit = sorted({r["station_name"] for r in recs})
        novel_clusters.append({
            "cluster": cname,
            "sequence_count": len(recs),
            "total_reads": sum(r["read_count"] for r in recs),
            "stations": stations_hit,
            "station_count": len(stations_hit),
            "max_reference_similarity": round(avg_conf, 3),
            "novelty_score": round(1 - avg_conf, 3),
            "representative_sequence": recs[0]["sequence"],
            "points": [{"x": r["pca_x"], "y": r["pca_y"]} for r in recs],
        })
    novel_clusters.sort(key=lambda c: -c["sequence_count"])

    # --- known taxa leaderboard ---
    known_leaderboard = Counter()
    for r in classified:
        known_leaderboard[r["taxon"]] += r["read_count"]
    top_taxa = [
        {"taxon": k, "reads": v} for k, v in known_leaderboard.most_common(12)
    ]

    return {
        "overview": overview,
        "taxonomy_composition": taxonomy_composition,
        "group_composition": group_composition,
        "stations": stations,
        "novel_clusters": novel_clusters,
        "top_taxa": top_taxa,
    }
