# Arduino firmware

## The original firmware is missing
The sketch that actually recorded the March 2026 dataset is **not available**. If it is found (an `.ino` file in the Arduino IDE's sketchbook folder or on the PC used for logging), it should be added here as `spectral_logger_original/spectral_logger_original.ino`. It matters because the sensor settings (gain, integration time, LED state) and the exact pin wiring are only recorded there.

## Reconstructed reference sketch (not the original)
`spectral_logger_reconstructed/spectral_logger_reconstructed.ino` was written **from the serial protocol the Python logger expects**, so the rig can be driven and `../logger/multispectcode.py` tested. It is *not* the firmware used for the dataset.

- Status: **compile-checked only** (Arduino Uno, `arduino:avr` 1.8.6; SparkFun Spectral Triad AS7265X 1.0.5, Adafruit AS7341 1.4.1, Adafruit BusIO 1.17.4; 36 % flash, 22 % RAM). It has never been run on the hardware.
- Sensor gain, integration time and the wiring are **placeholders/assumptions** (see the header comment of the sketch).
- It should be compared with, or replaced by, the original sketch before anything is claimed about how the data were acquired.

## Serial protocol (what the logger expects)
115200 baud; one text line per measurement (about every 2 s):
```
DATA,<31 comma-separated numbers>
```
| Index | Content |
|---|---|
| 0-17 | AS7265x 410, 435, 460, 485, 510, 535, 560, 585, 610, 645, 680, 705, 730, 760, 810, 860, 900, 940 nm |
| 18-27 | AS7341 415, 445, 480, 515, 555, 590, 630, 680 nm, Clear, NIR (raw 16-bit counts) |
| 28-30 | LDR 1-3 (Arduino ADC, 0-1023) |

Lines that do not start with `DATA,` are echoed by the logger as `[Arduino] ...`. A line with the wrong number of fields is counted as an error.

## Upload
Arduino IDE: install the libraries *SparkFun Spectral Triad AS7265X* and *Adafruit AS7341*, open the `.ino`, select *Arduino Uno*, upload. Or with the CLI:
```
arduino-cli lib install "SparkFun Spectral Triad AS7265X" "Adafruit AS7341"
arduino-cli compile --fqbn arduino:avr:uno spectral_logger_reconstructed
arduino-cli upload  --fqbn arduino:avr:uno -p COMx spectral_logger_reconstructed
```
