"""
data_generator.py
------------------
Builds a synthetic-but-structurally-realistic eDNA dataset in the shape of an
OBIS (Ocean Biodiversity Information System) occurrence export for the
Arabian Sea. Real OBIS eDNA downloads are large (raw FASTA + ASV tables +
Darwin Core metadata) and not bundled here, so this module generates a
dataset with the same fields, statistical shape, and biological plausibility
(real Arabian Sea coordinates, real higher-level marine taxa, realistic
18S rRNA-like nucleotide composition) so the full pipeline below is exercised
end-to-end. Swap `generate_dataset()` for a real OBIS/DarwinCore loader to
run this on live data -- every downstream function only needs the same
columns.
"""

import random
import hashlib
import numpy as np

RNG_SEED = 42

# ---------------------------------------------------------------------------
# Reference taxonomy: curated set of marine taxa genuinely recorded in / near
# the Arabian Sea (phytoplankton, zooplankton, fish, cnidarians, molluscs).
# Each gets a synthetic but fixed "reference barcode" sequence so k-mer
# matching below is deterministic and reproducible.
# ---------------------------------------------------------------------------
REFERENCE_TAXA = [
    ("Noctiluca scintillans",      "Dinoflagellata", "Phytoplankton"),
    ("Trichodesmium erythraeum",   "Cyanobacteria",  "Phytoplankton"),
    ("Chaetoceros curvisetus",     "Bacillariophyta","Phytoplankton"),
    ("Ceratium furca",             "Dinoflagellata", "Phytoplankton"),
    ("Calanus pacificus",          "Arthropoda",     "Zooplankton"),
    ("Euphausia diomedeae",        "Arthropoda",     "Zooplankton"),
    ("Oikopleura dioica",          "Chordata",       "Zooplankton"),
    ("Sagitta enflata",            "Chaetognatha",   "Zooplankton"),
    ("Acartia erythraea",          "Arthropoda",     "Zooplankton"),
    ("Thysanoessa spinifera",      "Arthropoda",     "Zooplankton"),
    ("Katsuwonus pelamis",         "Chordata",       "Fish"),
    ("Thunnus albacares",          "Chordata",       "Fish"),
    ("Sardinella longiceps",       "Chordata",       "Fish"),
    ("Rastrelliger kanagurta",     "Chordata",       "Fish"),
    ("Stolephorus indicus",        "Chordata",       "Fish"),
    ("Aurelia aurita",             "Cnidaria",        "Cnidarian"),
    ("Chrysaora chinensis",        "Cnidaria",        "Cnidarian"),
    ("Porites lutea",              "Cnidaria",        "Cnidarian"),
    ("Turbinaria peltata",         "Cnidaria",        "Cnidarian"),
    ("Loligo duvauceli",           "Mollusca",        "Mollusc"),
    ("Perna viridis",              "Mollusca",        "Mollusc"),
    ("Octopus cyanea",             "Mollusca",        "Mollusc"),
    ("Sepia pharaonis",            "Mollusca",        "Mollusc"),
    ("Lepidochelys olivacea",      "Chordata",        "Reptile"),
    ("Tursiops aduncus",           "Chordata",        "Mammal"),
]

BASES = "ACGT"


def _seeded_sequence(key: str, length: int, gc_bias: float) -> str:
    """Deterministic pseudo-sequence from a text key (stand-in for a real
    18S/COI barcode region) with a controllable GC content bias, so repeated
    runs are reproducible and different taxa look genuinely distinct."""
    h = int(hashlib.sha256(key.encode()).hexdigest(), 16)
    rnd = random.Random(h)
    seq = []
    for _ in range(length):
        if rnd.random() < gc_bias:
            seq.append(rnd.choice("GC"))
        else:
            seq.append(rnd.choice("AT"))
    return "".join(seq)


def _mutate(seq: str, rate: float, rnd: random.Random) -> str:
    out = list(seq)
    for i in range(len(out)):
        if rnd.random() < rate:
            out[i] = rnd.choice(BASES)
    return "".join(out)


# Arabian Sea bounding sampling stations (lat, lon), spanning the Indian
# west coast shelf, the open Arabian Sea, and the Omani upwelling zone --
# all real oceanographic regions used in OBIS Arabian Sea collections.
STATIONS = [
    ("AS-01", "Mumbai Shelf",         19.05, 71.9,  35),
    ("AS-02", "Goa Coastal",          15.30, 73.5,  40),
    ("AS-03", "Kochi Upwelling",       9.90, 75.2,  60),
    ("AS-04", "Lakshadweep Basin",    11.60, 72.6, 120),
    ("AS-05", "Gujarat Shelf",        21.60, 68.9,  25),
    ("AS-06", "Central Arabian Sea",  16.00, 65.0, 800),
    ("AS-07", "Oman Upwelling",       18.50, 58.5, 150),
    ("AS-08", "Gulf of Aden Mouth",   12.60, 47.0, 300),
    ("AS-09", "Socotra Trench",       12.30, 53.9, 950),
    ("AS-10", "Karachi Shelf",        24.60, 66.8,  30),
    ("AS-11", "Malabar Slope",        10.80, 74.5, 200),
    ("AS-12", "Lakshadweep Reef",     10.57, 72.64, 15),
]


def generate_dataset(n_asvs: int = 950, seed: int = RNG_SEED):
    """Returns a list of ASV (Amplicon Sequence Variant) records, each with
    a station, a synthetic sequence, and (for most) a true source taxon --
    including a deliberate fraction of divergent / unassigned sequences that
    stand in for undocumented or cryptic species, which is the realistic
    situation with Arabian Sea eDNA and the phenomenon the pipeline is built
    to surface."""
    rnd = random.Random(seed)
    np.random.seed(seed)

    # Build reference barcode sequences once.
    reference_seqs = {
        name: _seeded_sequence(name, 150, gc_bias=0.55)
        for name, _, _ in REFERENCE_TAXA
    }

    records = []
    for i in range(n_asvs):
        station = rnd.choice(STATIONS)
        station_id, station_name, lat, lon, depth = station

        # 78% of reads derive from a known reference taxon with realistic
        # PCR/sequencing divergence; 22% are drawn from a "ghost" taxon pool
        # (simulating undescribed / cryptic species with no close reference)
        # with much higher divergence from anything in REFERENCE_TAXA.
        if rnd.random() < 0.78:
            taxon_name, phylum, group = rnd.choice(REFERENCE_TAXA)
            base_seq = reference_seqs[taxon_name]
            seq = _mutate(base_seq, rate=rnd.uniform(0.01, 0.07), rnd=rnd)
            true_taxon = taxon_name
        else:
            # ghost / undescribed lineage: seed a novel sequence family so
            # several ASVs from the same "unknown species" cluster together
            ghost_id = f"ghost-{rnd.randint(1, 9)}"
            base_seq = _seeded_sequence(ghost_id, 150, gc_bias=rnd.uniform(0.3, 0.7))
            seq = _mutate(base_seq, rate=rnd.uniform(0.02, 0.05), rnd=rnd)
            true_taxon = None
            phylum, group = None, None

        records.append({
            "asv_id": f"ASV_{i+1:04d}",
            "station_id": station_id,
            "station_name": station_name,
            "latitude": lat + rnd.uniform(-0.15, 0.15),
            "longitude": lon + rnd.uniform(-0.15, 0.15),
            "depth_m": max(1, int(depth + rnd.uniform(-depth*0.2, depth*0.2))),
            "sequence": seq,
            "read_count": int(np.random.lognormal(mean=3.2, sigma=1.1)) + 1,
            "_true_taxon": true_taxon,   # ground truth, not used by pipeline
        })

    return records, reference_seqs, REFERENCE_TAXA
