"""
Test script: snap the full Euro Stoxx 50 (.STOXX50E) option chain from LSEG
Workspace and plot bid/ask vs strike, one panel per expiry.

pip install lseg-data pandas matplotlib
"""
import math
import time

import matplotlib.pyplot as plt
import pandas as pd
import lseg.data as ld
from lseg.data.discovery import Chain

CHAIN = "0#STXE*.EX"        # Eurex Euro Stoxx 50 options
UNDERLYING = ".STOXX50E"
FIELDS = ["BID", "ASK", "STRIKE_PRC", "EXPIR_DATE", "PUTCALLIND"]
BATCH = 500                 # raise to the max batch_probe.py finds
PAUSE = 0.25


def expand(chain_ric):
    """Expand a chain, recursing into any sub-chains (RICs starting with 0#)."""
    out = []
    for ric in Chain(name=chain_ric).constituents:
        out += expand(ric) if ric.startswith("0#") else [ric]
    return out


def get_with_retry(rics, fields, tries=4):
    for k in range(tries):
        try:
            return ld.get_data(universe=rics, fields=fields)
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 ** k)


def snap():
    rics = expand(CHAIN)
    print(f"{len(rics)} option RICs")
    frames = []
    for i in range(0, len(rics), BATCH):
        frames.append(get_with_retry(rics[i:i + BATCH], FIELDS))
        time.sleep(PAUSE)
    spot = get_with_retry([UNDERLYING], ["TRDPRC_1"])["TRDPRC_1"].iloc[0]
    return pd.concat(frames, ignore_index=True), spot


def plot(df, spot):
    df = df.dropna(subset=["STRIKE_PRC", "EXPIR_DATE"])
    df = df[df["BID"].notna() | df["ASK"].notna()]
    df["EXPIR_DATE"] = pd.to_datetime(df["EXPIR_DATE"])
    df["is_call"] = df["PUTCALLIND"].astype(str).str.upper().str.startswith("C")

    expiries = sorted(df["EXPIR_DATE"].unique())
    ncols = 5
    nrows = math.ceil(len(expiries) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3 * nrows),
                             squeeze=False)

    for ax, exp in zip(axes.flat, expiries):
        d = df[df["EXPIR_DATE"] == exp]
        for is_call, color, label in [(True, "tab:blue", "call"),
                                      (False, "tab:red", "put")]:
            s = d[d["is_call"] == is_call]
            ax.scatter(s["STRIKE_PRC"], s["BID"], s=6, marker="v",
                       color=color, label=f"{label} bid")
            ax.scatter(s["STRIKE_PRC"], s["ASK"], s=6, marker="^",
                       color=color, alpha=0.5, label=f"{label} ask")
        ax.axvline(spot, color="grey", lw=0.8, ls="--")
        ax.set_title(pd.Timestamp(exp).strftime("%Y-%m-%d"), fontsize=9)
        ax.tick_params(labelsize=7)

    for ax in list(axes.flat)[len(expiries):]:
        ax.axis("off")

    axes[0, 0].legend(fontsize=6)
    fig.suptitle(f"{UNDERLYING} options: bid/ask vs strike (spot {spot:.0f})")
    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    ld.open_session()
    try:
        df, spot = snap()
    finally:
        ld.close_session()
    plot(df, spot)
