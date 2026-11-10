# Low-cost multispectral logger and dataset for food adulteration

Code and a sample dataset for a low-cost, Arduino-based multispectral rig (SparkFun/ams AS7265x "Triad" + ams AS7341 + 3 LDR modules on an Arduino Uno). The rig was used to log spectra of 5 pure foods and of 6 adulteration series (5 to 40 % in steps of 5) recorded on 2026-03-13 and 2026-03-15.

This repository contains:

- the **PC-side logger** that records the rig's serial stream to CSV,
- a **reference Arduino sketch** for the rig (reconstructed, see the warning below),
- the **script that builds the structured dataset** from the raw logger files,
- a **small sample of the dataset** (11 of the 53 samples) plus the complete metadata and per-sample mean spectra.

> **Read this first**
> 1. The Arduino sketch here is a **reconstruction**, not the firmware that recorded the data. The original `.ino` was not kept. The reconstruction was written from the serial protocol the logger expects and was **only compile-checked** (Arduino Uno); it has never been run on the hardware. Sensor gain, integration time and pin wiring in it are placeholders. Do not cite it as the acquisition firmware.
> 2. Only a **sample** of the data is included. The full dataset has 53 files and 3,637 frames; this repository holds 11 files and 789 frames (see "Dataset sample").
> 3. Adulterant identities and the "%" unit (presumably % w/w) were not recorded at collection. They were inferred from the original file names and should be confirmed by the authors before being relied on.

## Repository layout

```
.
├── README.md
├── code/
│   ├── requirements.txt
│   ├── arduino/
│   │   ├── README.md                                   serial protocol, status, upload instructions
│   │   └── spectral_logger_reconstructed/
│   │       └── spectral_logger_reconstructed.ino       reference sketch (compile-checked only)
│   ├── logger/
│   │   └── multispectcode.py                           live display + CSV logger (Python, matplotlib, pyserial)
│   └── dataset/
│       └── build_dataset.py                            raw logger CSVs -> structured dataset
└── sample dataset/                                     SAMPLE of the dataset (described below)
    ├── raw_renamed/                                    11 logger files with systematic names (original 32-column format)
    ├── processed/
    │   ├── spectral_frames_sample.csv                  all frames of the same 11 samples, labelled, with QC flags (789 rows x 54 columns)
    │   └── spectral_file_means.csv                     mean of every channel for ALL 53 samples
    └── metadata/
        ├── file_manifest.csv                           ALL 53 files: original name, new name, labels, session, duration, QC fractions, SHA-256
        └── column_dictionary.csv                       every column of the master table: group, meaning, unit, dtype
```

## Hardware and serial protocol

| Part | Role |
|---|---|
| Arduino Uno | Reads all sensors, streams over USB serial at 115200 baud |
| AS7265x "Triad" | 18 channels, 410 to 940 nm |
| AS7341 | 8 visible channels + Clear + NIR |
| 3 x LDR modules | Light level read on the Arduino ADC (0 to 1023) |

The Arduino sends one text line about every 2 s: `DATA,<31 comma-separated numbers>`.

| Index | Content |
|---|---|
| 0 to 17 | AS7265x 410, 435, 460, 485, 510, 535, 560, 585, 610, 645, 680, 705, 730, 760, 810, 860, 900, 940 nm |
| 18 to 27 | AS7341 415, 445, 480, 515, 555, 590, 630, 680 nm, Clear, NIR (raw 16-bit counts) |
| 28 to 30 | LDR 1 to 3 (ADC 0 to 1023) |

More detail, library versions and upload steps are in [code/arduino/README.md](code/arduino/README.md).

## Quick start

```
pip install -r code/requirements.txt
```

**Record data** (rig connected; omit the port to auto-detect):

```
python code/logger/multispectcode.py COM3
```

A window shows all 31 channels live. *Start Log* appends every frame to `spectral_log.csv` (with a PC timestamp); *Save CSV* appends one snapshot. The logger clips negative readings to 0 and does not write a sample label, concentration or sensor settings, so rename or annotate each file yourself. The logger script is the one the dataset files came from (their format matches it exactly); the reconstructed sketch has not been run with it on hardware.

> `pip install serial` installs an unrelated package. If the logger fails with an import error, run `pip uninstall serial` and then `pip install pyserial`.

**Rebuild the structured dataset** from a folder of raw logger CSVs (the full raw files are not in this repository):

```
python code/dataset/build_dataset.py <RAW_LOGGER_DIR> [<OUTPUT_DIR>]
```

The default output folder is `dataset_rebuilt/`, so the shipped sample is never overwritten. Run on the full set of 53 original files, the script reproduces the complete dataset file for file (checked by comparing SHA-256 hashes of all 62 output files); the sample here was cut from that output. The script classifies files by the original (inconsistent) file names, so it will not work on arbitrarily named files.

## Dataset sample

The sample contains the pure reference and the 20 % level of every series, so each food and each adulterant is represented once:

| Matrix | Adulterant (inferred) | Session | Sample files included |
|---|---|---|---|
| chili | yellow-colourant | 2026-03-13 | `chili_none_00pct`, `chili_yellow-colourant_20pct` |
| milk | batter | 2026-03-13 | `milk_none_00pct`, `milk_batter_20pct` |
| milk | besan (gram flour) | 2026-03-15 | `milk_none_00pct` (pure reference is from 03-13, not the same day), `milk_besan_20pct` |
| coconut-oil | palm-oil | 2026-03-15 | `coconut-oil_none_00pct`, `coconut-oil_palm-oil_20pct` |
| mustard-oil | palm-oil | 2026-03-15 | `mustard-oil_none_00pct`, `mustard-oil_palm-oil_20pct` |
| maida (refined flour) | chalk | 2026-03-15 | `maida_none_00pct`, `maida_chalk_20pct` |

File naming: `{matrix}_{adulterant}_{pct:02d}pct.csv` (pure reference: `none`, `00pct`). `raw_renamed/` files are byte-identical copies of the logger output. The processed table adds labels, session information and QC flags; **no sensor value was changed or removed**. Column definitions are in `dataset/metadata/column_dictionary.csv`. Because the metadata and `spectral_file_means.csv` cover all 53 samples, they list files that are not in `raw_renamed/`.

### Known data-quality problems (from the QC flags, full dataset)

| Issue | Extent |
|---|---|
| AS7265x 485 nm reads 0 (failed read) | 80.7 % of frames; treat the channel as missing |
| AS7341 Clear saturated (65535) | 100 % of frames; unusable |
| AS7341 NIR saturated | 75.8 % of frames |
| AS7341 680 nm / 630 nm saturated | 12.7 % / 4.8 % overall; nearly all frames of pure milk and milk + batter at 680 nm |
| Timing gaps (> 4 s between frames) | 6 frames in 6 files (spacing is otherwise about 2.06 s) |
| LDR channels | 32 to 43 of 1023, nearly constant. Probably saturated digital outputs of LM393 comparator modules rather than light levels (not confirmed, original firmware missing) |

Channels usable throughout: all AS7265x except 485 nm (17) and AS7341 415 to 590 nm (6).

### Using the data correctly

- **One file is one sample preparation.** Frames inside a file are near-duplicates (autocorrelated). Never split frames randomly into train and test sets; split by `sample_id`. There is one preparation per level, so file-level validation means leaving a whole concentration level out.
- **No replicates, and level is confounded with time.** Levels were always measured in ascending order, and the two sessions differ (for example LDR-2 shifts from about 37 to about 42 between the days).
- No dark or white reference recordings exist, so no reflectance or absorbance normalisation is possible.
- The sensor settings (gain, integration time, LED state), sample mass or volume, sample holder, sensor distance and illumination were not documented.

```python
import pandas as pd
df = pd.read_csv("dataset/processed/spectral_frames_sample.csv")
good = df[~df.qc_time_gap]            # the dead 485 nm channel is dropped below, so do not filter frames on it
cols = [c for c in df.columns if c.startswith("as7265x_") and c != "as7265x_485nm"] + \
       [c for c in df.columns if c.startswith("as7341_") and c.endswith("nm") and c not in ("as7341_630nm", "as7341_680nm")]
X, y, groups = good[cols], good.pct_adulterant, good.sample_id   # use `groups` for GroupKFold
```

## Citation and licence

Citation details will be added once the associated article is published. No licence file has been added yet; add one (for example MIT for code and CC BY 4.0 for data) before making the repository public.
