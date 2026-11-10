"""Build the structured dataset from the raw logger CSVs in <project>/data+code (originals are never modified).

Outputs (all under <project>/dataset/):
  (under OUTPUT_DIR, see usage below)
  raw_renamed/        byte-identical copies of the 53 logger files with systematic names
  processed/          spectral_frames.csv (master, one row per frame), by_matrix/*.csv, spectral_file_means.csv
  metadata/           file_manifest.csv, column_dictionary.csv
Run:  python build_dataset.py [RAW_LOGGER_DIR] [OUTPUT_DIR]
"""
import glob
import hashlib
import os
import re
import shutil
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.normpath(os.path.join(HERE, "..", ".."))
# Usage: python build_dataset.py [RAW_LOGGER_DIR] [OUTPUT_DIR]
# The full raw logger files are not part of this repository, so point RAW_LOGGER_DIR at your copy.
# Default output is <repo>/dataset_rebuilt so the shipped sample in <repo>/dataset is never overwritten.
SRC = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(PROJECT, "data+code")
ROOT = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(PROJECT, "dataset_rebuilt")
RAW, PROC, META = (os.path.join(ROOT, d) for d in ("raw_renamed", "processed", "metadata"))
for d in (RAW, PROC, os.path.join(PROC, "by_matrix"), META):
    os.makedirs(d, exist_ok=True)

SAT = 65535                      # AS7341 16-bit ceiling
GAP_S = 4.0                      # a frame arriving > 4 s after the previous one (median spacing 2.06 s) is flagged

# series -> (matrix, adulterant, pure reference sample). Adulterant names are INFERRED from the original file names.
SERIES = {
    "chili_yellow":           ("chili",        "yellow-colourant", "chili_none_00pct"),
    "milk_batter":            ("milk",         "batter",           "milk_none_00pct"),
    "milk_besan":             ("milk",         "besan",            "milk_none_00pct"),
    "coconut-oil_palm-oil":   ("coconut-oil",  "palm-oil",         "coconut-oil_none_00pct"),
    "mustard-oil_palm-oil":   ("mustard-oil",  "palm-oil",         "mustard-oil_none_00pct"),
    "maida_chalk":            ("maida",        "chalk",            "maida_none_00pct"),
}
PURE_FILES = {"pure_chili": "chili", "puremilk": "milk", "purecoconadoil": "coconut-oil",
              "puremoyda": "maida", "puremustardoil": "mustard-oil"}


def classify(fname):
    """original file name -> (series or None, matrix, adulterant, pct)."""
    n = fname.lower().replace(".csv", "")
    if n in PURE_FILES:
        return None, PURE_FILES[n], "none", 0
    if "bason" in n:
        s = "milk_besan"
    elif "batter" in n:
        s = "milk_batter"
    elif "chili+yellow" in n:
        s = "chili_yellow"
    elif "coconad" in n:
        s = "coconut-oil_palm-oil"
    elif n.startswith(("mus", "mul")):
        s = "mustard-oil_palm-oil"
    elif n.startswith("moyda"):
        s = "maida_chalk"
    else:
        raise ValueError(f"cannot classify {fname}")
    tail = "20" if "(+pum20)" in n else None
    if tail is None:
        m = re.findall(r"(2o|\d+)", n.split("(")[-1])
        tail = {"2o": "20"}.get(m[0], m[0])          # 'moyda+chock(2o)' is a typo for 20
    matrix, adulterant, _ = SERIES[s]
    return s, matrix, adulterant, int(tail)


def sample_id(matrix, adulterant, pct):
    return f"{matrix}_{adulterant}_{pct:02d}pct"


# ------------------------------------------------------------------ column naming
def new_columns(cols):
    out = {}
    for c in cols:
        if c == "Timestamp":
            continue
        if c.startswith("AS7265X_"):
            out[c] = "as7265x_" + c.split("_", 1)[1].lower()                  # as7265x_410nm
        elif c.startswith("AS7341_"):
            k = c.split("_", 1)[1].lower().rstrip("*")                       # as7341_680nm (asterisk dropped), as7341_clear, as7341_nir
            out[c] = "as7341_" + k
        elif c.startswith("LDR_LDR-"):
            out[c] = "ldr_" + c[-1]                                          # ldr_1..3
        else:
            raise ValueError(c)
    return out


def main():
    files = sorted(glob.glob(os.path.join(SRC, "*.csv")))
    assert len(files) == 53, len(files)
    frames, manifest = [], []
    for f in files:
        orig = os.path.basename(f)
        series, matrix, adulterant, pct = classify(orig)
        sid = sample_id(matrix, adulterant, pct)
        new_name = sid + ".csv"
        shutil.copy2(f, os.path.join(RAW, new_name))
        df = pd.read_csv(f)
        ts = pd.to_datetime(df["Timestamp"], format="%Y-%m-%d %H:%M:%S.%f")
        df = df.rename(columns=new_columns(df.columns))
        spec = [c for c in df.columns if c.startswith(("as7265x_", "as7341_", "ldr_"))]
        d = pd.DataFrame({
            "sample_id": sid, "series": series if series else f"{matrix}_pure", "matrix": matrix, "adulterant": adulterant,
            "pct_adulterant": pct, "is_pure": pct == 0, "source_file": orig,
            "session_date": ts.dt.date.astype(str), "frame_idx": np.arange(len(df)),
            "timestamp": ts.dt.strftime("%Y-%m-%dT%H:%M:%S.%f").str[:-3],
            "t_elapsed_s": (ts - ts.iloc[0]).dt.total_seconds().round(3),
            "dt_s": ts.diff().dt.total_seconds().round(3),
        })
        for c in spec:
            d[c] = df[c].astype(int) if c.startswith(("as7265x_", "ldr_")) or c.startswith("as7341_") else df[c]
        # ---- QC flags (nothing is dropped or altered; flags only)
        d["qc_as7265x_485nm_dead"] = d["as7265x_485nm"] == 0
        d["qc_as7341_clear_sat"] = d["as7341_clear"] >= SAT
        d["qc_as7341_nir_sat"] = d["as7341_nir"] >= SAT
        d["qc_as7341_630nm_sat"] = d["as7341_630nm"] >= SAT
        d["qc_as7341_680nm_sat"] = d["as7341_680nm"] >= SAT
        d["qc_as7341_n_sat"] = d[[c for c in d.columns if c.startswith("qc_as7341_") and c.endswith("_sat")]].sum(axis=1)
        d["qc_time_gap"] = d["dt_s"] > GAP_S
        frames.append(d)
        manifest.append(dict(
            sample_id=sid, new_file=f"raw_renamed/{new_name}", original_file=orig, series=d["series"].iat[0], matrix=matrix,
            adulterant=adulterant, pct_adulterant=pct, session_date=d["session_date"].iat[0],
            recorded_start=d["timestamp"].iat[0], n_frames=len(d), duration_s=float(d["t_elapsed_s"].iat[-1]),
            median_dt_s=float(d["dt_s"].median()), max_dt_s=float(d["dt_s"].max()),
            frac_485nm_dead=round(float(d["qc_as7265x_485nm_dead"].mean()), 3),
            frac_clear_sat=round(float(d["qc_as7341_clear_sat"].mean()), 3), frac_nir_sat=round(float(d["qc_as7341_nir_sat"].mean()), 3),
            frac_630nm_sat=round(float(d["qc_as7341_630nm_sat"].mean()), 3), frac_680nm_sat=round(float(d["qc_as7341_680nm_sat"].mean()), 3),
            sha256_original=hashlib.sha256(open(f, "rb").read()).hexdigest(),
        ))

    A = pd.concat(frames, ignore_index=True)
    M = pd.DataFrame(manifest)

    # ---- sessions and pure-reference bookkeeping
    dates = sorted(A["session_date"].unique())
    sess = {d_: f"S{i + 1}" for i, d_ in enumerate(dates)}
    A.insert(A.columns.get_loc("session_date") + 1, "session_id", A["session_date"].map(sess))
    M.insert(M.columns.get_loc("session_date") + 1, "session_id", M["session_date"].map(sess))
    ref_of = {s: v[2] for s, v in SERIES.items()}
    pure_date = M[M.pct_adulterant == 0].set_index("sample_id")["session_date"].to_dict()
    M["pure_reference"] = [ref_of.get(s, sid) for s, sid in zip(M["series"], M["sample_id"])]
    M["pure_reference_same_day"] = [pure_date[r] == d_ for r, d_ in zip(M["pure_reference"], M["session_date"])]
    M = M.sort_values(["matrix", "series", "pct_adulterant"]).reset_index(drop=True)
    A = A.merge(M[["sample_id", "pure_reference", "pure_reference_same_day"]], on="sample_id", how="left")
    # tidy column order
    ids = ["sample_id", "series", "matrix", "adulterant", "pct_adulterant", "is_pure", "session_id", "session_date",
           "pure_reference", "pure_reference_same_day", "source_file", "frame_idx", "timestamp", "t_elapsed_s", "dt_s"]
    spec_cols = [c for c in A.columns if c.startswith(("as7265x_", "as7341_", "ldr_")) and not c.startswith("qc_")]
    qc_cols = [c for c in A.columns if c.startswith("qc_")]
    A = A[ids + spec_cols + qc_cols]
    A = A.sort_values(["matrix", "series", "pct_adulterant", "frame_idx"]).reset_index(drop=True)
    A.insert(0, "frame_id", np.arange(1, len(A) + 1))

    # ---- write
    A.to_csv(os.path.join(PROC, "spectral_frames.csv"), index=False)
    for mtx, g in A.groupby("matrix"):
        g.to_csv(os.path.join(PROC, "by_matrix", f"{mtx}.csv"), index=False)
    means = A.groupby(["sample_id", "series", "matrix", "adulterant", "pct_adulterant", "session_id"], sort=False)[spec_cols].mean().round(2)
    means.insert(0, "n_frames", A.groupby(["sample_id", "series", "matrix", "adulterant", "pct_adulterant", "session_id"], sort=False).size())
    means.reset_index().sort_values(["matrix", "series", "pct_adulterant"]).to_csv(os.path.join(PROC, "spectral_file_means.csv"), index=False)
    M.to_csv(os.path.join(META, "file_manifest.csv"), index=False)
    write_dictionary(spec_cols, qc_cols)
    print(f"frames {len(A)}  files {len(M)}  matrices {A.matrix.nunique()}  series {A.series.nunique()}  sessions {dates}")


def write_dictionary(spec_cols, qc_cols):
    rows = [
        ("frame_id", "id", "Running frame number across the whole table (1-based)", "", "int"),
        ("sample_id", "id", "{matrix}_{adulterant}_{pct:02d}pct; one sample = one logger file", "", "str"),
        ("series", "id", "Adulteration series ({matrix}_{adulterant}) or {matrix}_pure for pure references", "", "str"),
        ("matrix", "label", "Food matrix: chili, milk, coconut-oil, mustard-oil, maida", "", "str"),
        ("adulterant", "label", "Adulterant (INFERRED from original file names; confirm): yellow-colourant, batter, besan, palm-oil, chalk; 'none' for pure", "", "str"),
        ("pct_adulterant", "label", "Adulterant level, 0 for pure (unit presumed % w/w; not documented at collection)", "%", "int"),
        ("is_pure", "label", "True for the pure reference samples", "", "bool"),
        ("session_id", "meta", "Recording day: S1 = 2026-03-13, S2 = 2026-03-15", "", "str"),
        ("session_date", "meta", "Calendar date from the logger timestamp", "", "date"),
        ("pure_reference", "meta", "sample_id of the pure reference for this series", "", "str"),
        ("pure_reference_same_day", "meta", "False when the pure reference was recorded on a different day (milk_besan)", "", "bool"),
        ("source_file", "meta", "Original logger file name in data+code/", "", "str"),
        ("frame_idx", "meta", "0-based frame index within the file", "", "int"),
        ("timestamp", "meta", "PC clock at logging, ISO 8601, no timezone", "", "str"),
        ("t_elapsed_s", "meta", "Seconds since the first frame of the file", "s", "float"),
        ("dt_s", "meta", "Seconds since previous frame (NaN for the first frame)", "s", "float"),
    ]
    nm = {"as7265x": "AS7265x (3-chip triad), 410-940 nm, logged values are whole numbers", "as7341": "AS7341, 16-bit counts, ceiling 65535", "ldr": "LDR module read on the Arduino ADC (0-1023)"}
    for c in spec_cols:
        k = c.split("_")[0]
        extra = ""
        if c == "as7341_680nm":
            extra = "; original header 'AS7341_680nm*' (asterisk unexplained in the source)"
        if c in ("as7341_clear", "as7341_nir"):
            extra = "; broadband channel, mostly saturated"
        if c.startswith("ldr"):
            extra = "; 3-pin LM393 module (DO output), values barely vary; see README"
        rows.append((c, "signal", nm[k] + extra, "counts" if k != "ldr" else "ADC", "int"))
    qcd = {
        "qc_as7265x_485nm_dead": "AS7265x 485 nm channel reads 0 (dead/failed read; ~81 % of frames)",
        "qc_as7341_clear_sat": "AS7341 Clear channel at 65535", "qc_as7341_nir_sat": "AS7341 NIR channel at 65535",
        "qc_as7341_630nm_sat": "AS7341 630 nm channel at 65535", "qc_as7341_680nm_sat": "AS7341 680 nm channel at 65535",
        "qc_as7341_n_sat": "Number of saturated AS7341 channels in the frame",
        "qc_time_gap": f"Frame arrived > {GAP_S:g} s after the previous frame",
    }
    for c in qc_cols:
        rows.append((c, "qc", qcd[c], "", "int" if c.endswith("n_sat") else "bool"))
    pd.DataFrame(rows, columns=["column", "group", "description", "unit", "dtype"]).to_csv(os.path.join(META, "column_dictionary.csv"), index=False)


if __name__ == "__main__":
    main()
