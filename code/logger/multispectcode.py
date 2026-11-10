"""
Real-Time Spectral Analyzer – Numerical Display + CSV Logger
============================================================
Shows all 31 sensor channels as live-updating numbers.

Buttons:
  [Save CSV]  – append one timestamped snapshot to spectral_log.csv
  [Start Log] – continuously append every incoming reading to CSV
               (click again to stop)

Channel layout (matches Arduino firmware):
  Index  0-17  → AS7265X  (18 channels, 410–940 nm, calibrated float)
  Index 18-27  → AS7341   (10 channels, 415–NIR, raw uint16)
  Index 28-30  → LDR1, LDR2, LDR3  (ADC 0-1023)

Usage:
  pip install pyserial matplotlib
  python spectral_monitor.py          # auto-detect port
  python spectral_monitor.py /dev/ttyUSB0
"""

import sys
import csv
import os
import datetime
import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Button

BAUD_RATE     = 115200
POLL_INTERVAL = 200        # ms between display refreshes
NUM_CHANNELS  = 31
CSV_FILE      = "spectral_log.csv"

LABELS_7265X = [
    "410nm", "435nm", "460nm", "485nm", "510nm", "535nm",
    "560nm", "585nm", "610nm", "645nm", "680nm", "705nm",
    "730nm", "760nm", "810nm", "860nm", "900nm", "940nm",
]
LABELS_7341 = [
    "415nm", "445nm", "480nm", "515nm", "555nm",
    "590nm", "630nm", "680nm*", "Clear",  "NIR",
]
LABELS_LDR = ["LDR-1", "LDR-2", "LDR-3"]

CSV_HEADERS = (
    ["Timestamp"]
    + [f"AS7265X_{l}" for l in LABELS_7265X]
    + [f"AS7341_{l}"  for l in LABELS_7341]
    + [f"LDR_{l}"     for l in LABELS_LDR]
)


# ── Serial helpers ───────────────────────────────────────────
def find_arduino_port():
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if any(k in desc for k in ("arduino", "ch340", "cp210", "ftdi", "uart")):
            return p.device
    return None


def open_serial(port):
    if port is None:
        port = find_arduino_port()
    if port is None:
        print("ERROR: No serial port found.")
        print("  python spectral_monitor.py /dev/ttyUSB0")
        return None
    try:
        s = serial.Serial(port, BAUD_RATE, timeout=0.1)
        print(f"Connected → {port} @ {BAUD_RATE} baud")
        return s
    except serial.SerialException as e:
        print(f"ERROR opening {port}: {e}")
        return None


# ── Main ─────────────────────────────────────────────────────
def main():
    port_arg = sys.argv[1] if len(sys.argv) > 1 else None
    ser = open_serial(port_arg)

    # ── Figure ────────────────────────────────────────────────
    fig = plt.figure(figsize=(18, 10), facecolor="#1e1e1e")
    fig.suptitle("Real-Time Spectral Analyzer  —  Numerical Display",
                 color="white", fontsize=14, y=0.998)

    # Main text display axes (no plot, just text objects)
    ax = fig.add_axes([0.01, 0.13, 0.98, 0.85])
    ax.set_facecolor("#1e1e1e")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Button axes
    ax_b1 = fig.add_axes([0.01, 0.02, 0.13, 0.07])
    ax_b2 = fig.add_axes([0.16, 0.02, 0.13, 0.07])

    # Status bar axes
    ax_st = fig.add_axes([0.31, 0.02, 0.68, 0.07])
    ax_st.set_facecolor("#252525")
    ax_st.axis("off")

    # ── Layout constants ──────────────────────────────────────
    # y positions (axes-fraction, 0=bottom, 1=top)
    Y_HDR1  = 0.975   # AS7265X header
    Y_LBL1A = 0.905   # row-1 channel labels
    Y_VAL1A = 0.820   # row-1 values
    Y_LBL1B = 0.730   # row-2 channel labels
    Y_VAL1B = 0.645   # row-2 values
    Y_DIV2  = 0.600   # divider
    Y_HDR2  = 0.585   # AS7341 header
    Y_LBL2  = 0.515
    Y_VAL2  = 0.430
    Y_DIV3  = 0.385   # divider
    Y_HDR3  = 0.370   # LDR header
    Y_LBL3  = 0.295
    Y_VAL3  = 0.185

    def section_hdr(y, text, color="#9999ff"):
        ax.text(0.005, y, text, transform=ax.transAxes,
                fontsize=9.5, fontweight="bold", color=color, va="top",
                fontfamily="monospace")

    def divider(y):
        ax.plot([0.005, 0.995], [y, y], color="#404040", lw=0.8,
                transform=ax.transAxes, clip_on=False)

    def make_value_cell(x, y_lbl, label, y_val, lbl_col, val_col, val_size=15):
        ax.text(x, y_lbl, label, transform=ax.transAxes,
                ha="center", va="top", fontsize=8,
                color=lbl_col, fontfamily="monospace")
        return ax.text(x, y_val, "---", transform=ax.transAxes,
                       ha="center", va="top", fontsize=val_size,
                       fontweight="bold", color=val_col, fontfamily="monospace")

    # ── AS7265X section (18 channels, 2 × 9) ─────────────────
    section_hdr(Y_HDR1,
        "AS7265X   Spectral Sensor   18 channels   410 – 940 nm   calibrated float")
    xs9 = [0.02 + i * (0.96 / 9) + (0.96 / 18) for i in range(9)]

    val_7265x = []
    for i in range(9):   # row 1: channels 0-8
        val_7265x.append(
            make_value_cell(xs9[i], Y_LBL1A, LABELS_7265X[i],
                            Y_VAL1A, "#88aadd", "#00ff99"))
    for i in range(9):   # row 2: channels 9-17
        val_7265x.append(
            make_value_cell(xs9[i], Y_LBL1B, LABELS_7265X[9 + i],
                            Y_VAL1B, "#88aadd", "#00ff99"))

    # ── AS7341 section (10 channels, 1 row) ───────────────────
    divider(Y_DIV2)
    section_hdr(Y_HDR2,
        "AS7341   Spectral Sensor   10 channels   415 nm – NIR   raw uint16",
        color="#ffbb88")
    xs10 = [0.02 + i * (0.96 / 10) + (0.96 / 20) for i in range(10)]

    val_7341 = []
    for i in range(10):
        val_7341.append(
            make_value_cell(xs10[i], Y_LBL2, LABELS_7341[i],
                            Y_VAL2, "#ddaa77", "#ff9944"))

    # ── LDR section (3 sensors) ───────────────────────────────
    divider(Y_DIV3)
    section_hdr(Y_HDR3,
        "LDR   Light-Dependent Resistors   3 sensors   ADC  0 – 1023",
        color="#ffee88")
    xs_ldr = [0.18, 0.50, 0.82]

    val_ldr = []
    for i in range(3):
        val_ldr.append(
            make_value_cell(xs_ldr[i], Y_LBL3, LABELS_LDR[i],
                            Y_VAL3, "#ddcc77", "#ffdd00", val_size=26))

    # ── Status line ───────────────────────────────────────────
    st_info = ax_st.text(0.01, 0.70, "Waiting for data...",
                          transform=ax_st.transAxes, fontsize=9,
                          color="#aaaaaa", va="center")
    st_save = ax_st.text(0.01, 0.20, f"CSV: {CSV_FILE}  (not saved yet)",
                          transform=ax_st.transAxes, fontsize=8,
                          color="#777777", va="center")

    # ── Buttons ───────────────────────────────────────────────
    btn_save = Button(ax_b1, "Save CSV",
                      color="#1a3a1a", hovercolor="#2d5a2d")
    btn_save.label.set_color("white")
    btn_save.label.set_fontsize(11)

    btn_log = Button(ax_b2, "Start Log",
                     color="#1a1a3a", hovercolor="#2d2d5a")
    btn_log.label.set_color("white")
    btn_log.label.set_fontsize(11)

    # ── Shared state ──────────────────────────────────────────
    state = {
        "v7265x": [0.0] * 18,
        "v7341":  [0.0] * 10,
        "vldr":   [0.0] * 3,
        "errors": 0,
        "total":  0,
        "log_fh": None,
        "log_wr": None,
    }
    logging_on = [False]
    leftover   = [""]

    def _csv_row(vals):
        ts  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        row = (
            [ts]
            + [f"{v:.4f}" for v in vals[0:18]]
            + [str(int(v)) for v in vals[18:28]]
            + [str(int(v)) for v in vals[28:31]]
        )
        return ts, row

    def save_snapshot(_event=None):
        vals = state["v7265x"] + state["v7341"] + state["vldr"]
        ts, row = _csv_row(vals)
        new_file = not os.path.exists(CSV_FILE)
        with open(CSV_FILE, "a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(CSV_HEADERS)
            w.writerow(row)
        st_save.set_text(f"Saved snapshot → {CSV_FILE}   [{ts}]")
        st_save.set_color("#88ff88")
        print(f"[CSV] Snapshot saved at {ts}")

    def toggle_log(_event=None):
        if not logging_on[0]:
            logging_on[0] = True
            new_file = not os.path.exists(CSV_FILE)
            state["log_fh"] = open(CSV_FILE, "a", newline="")
            state["log_wr"] = csv.writer(state["log_fh"])
            if new_file:
                state["log_wr"].writerow(CSV_HEADERS)
            btn_log.label.set_text("Stop Log")
            ax_b2.set_facecolor("#3a1a1a")
            st_save.set_text(f"Logging every reading → {CSV_FILE}")
            st_save.set_color("#ffaa44")
            print(f"[CSV] Continuous logging started → {CSV_FILE}")
        else:
            logging_on[0] = False
            if state["log_fh"]:
                state["log_fh"].close()
                state["log_fh"] = None
                state["log_wr"] = None
            btn_log.label.set_text("Start Log")
            ax_b2.set_facecolor("#1a1a3a")
            st_save.set_text(f"Logging stopped  ·  data in {CSV_FILE}")
            st_save.set_color("#888888")
            print("[CSV] Continuous logging stopped.")

    btn_save.on_clicked(save_snapshot)
    btn_log.on_clicked(toggle_log)

    # ── Animation update ──────────────────────────────────────
    def update(_frame):
        if ser is None or not ser.is_open:
            return
        try:
            while ser.in_waiting:
                leftover[0] += ser.read(ser.in_waiting).decode(
                    "utf-8", errors="replace")
        except serial.SerialException:
            return

        *complete, leftover[0] = leftover[0].split("\n")
        for raw in complete:
            line = raw.strip()
            if not line.startswith("DATA,"):
                if line:
                    print(f"[Arduino] {line}")
                continue
            parts = line.split(",")
            if len(parts) != NUM_CHANNELS + 1:
                state["errors"] += 1
                continue
            try:
                vals = [float(p) for p in parts[1:]]
            except ValueError:
                state["errors"] += 1
                continue

            vals = [max(0.0, v) for v in vals]
            state["v7265x"] = vals[0:18]
            state["v7341"]  = vals[18:28]
            state["vldr"]   = vals[28:31]
            state["total"] += 1

            # Continuous CSV write
            if logging_on[0] and state["log_wr"]:
                ts, row = _csv_row(vals)
                state["log_wr"].writerow(row)
                state["log_fh"].flush()

        # Refresh text values
        for i, t in enumerate(val_7265x):
            t.set_text(f"{state['v7265x'][i]:.2f}")
        for i, t in enumerate(val_7341):
            t.set_text(f"{int(state['v7341'][i])}")
        for i, t in enumerate(val_ldr):
            t.set_text(f"{int(state['vldr'][i])}")

        ts  = datetime.datetime.now().strftime("%H:%M:%S")
        ok1 = any(v > 0 for v in state["v7265x"])
        ok2 = any(v > 0 for v in state["v7341"])
        st_info.set_text(
            f"Port: {ser.port if ser else '?'}   "
            f"Update: {ts}   "
            f"Frames: {state['total']}   "
            f"Errors: {state['errors']}   "
            f"AS7265X: {'OK ✓' if ok1 else 'NO DATA'}   "
            f"AS7341: {'OK ✓' if ok2 else 'NO DATA'}"
        )
        st_info.set_color("#44ff88" if (ok1 or ok2) else "#ffaa44")
        fig.canvas.draw_idle()

    ani = animation.FuncAnimation(   # noqa: F841
        fig, update, interval=POLL_INTERVAL, blit=False, cache_frame_data=False
    )

    plt.show()

    if logging_on[0] and state["log_fh"]:
        state["log_fh"].close()
    if ser and ser.is_open:
        ser.close()
        print("Serial port closed.")


if __name__ == "__main__":
    main()
