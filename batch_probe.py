"""
Find the largest get_data batch that works for the .STOXX50E chain.
Tries growing batch sizes, times each, and checks nothing was silently dropped.
"""
import time

import lseg.data as ld                      # or: import refinitiv.data as ld
from lseg.data.discovery import Chain       # or: from refinitiv.data.discovery import Chain

CHAIN = "0#STXE*.EX"
FIELDS = ["BID", "ASK", "STRIKE_PRC", "EXPIR_DATE", "PUTCALLIND"]


def expand(chain_ric):
    out = []
    for ric in Chain(name=chain_ric).constituents:
        out += expand(ric) if ric.startswith("0#") else [ric]
    return out


ld.open_session()
try:
    rics = expand(CHAIN)
    print(f"chain size: {len(rics)} RICs ({len(rics) * len(FIELDS)} datapoints)")

    sizes = [500, 1000, 2000, 4000, 8000, len(rics)]
    for n in sorted({min(s, len(rics)) for s in sizes}):
        t0 = time.time()
        try:
            df = ld.get_data(universe=rics[:n], fields=FIELDS)
            secs = time.time() - t0
            got = df["Instrument"].nunique()
            filled = df["BID"].notna().sum() + df["ASK"].notna().sum()
            print(f"{n:>6} RICs: {secs:6.1f}s  returned {got:>6}  "
                  f"bid/ask filled {filled}")
        except Exception as e:
            print(f"{n:>6} RICs: FAILED after {time.time() - t0:.1f}s -> {e}")
            break
        time.sleep(2)
finally:
    ld.close_session()
