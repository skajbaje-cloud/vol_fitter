# vol_fitter

Delta-space implied vol surface fitter, fed by LSEG Workspace chain snapshots.

## Setup (Anaconda Prompt)

```
conda create -n vol_fitter python=3.12 -y
conda activate vol_fitter
cd /d "G:\My Drive\SK work\Trading\Vol Fitter"
pip install -r requirements.txt
```

LSEG Workspace must be running and signed in.

## Scripts

| File | What it does |
|---|---|
| `batch_probe.py` | Finds the largest `get_data` batch that works for the chain. Run once. |
| `snap_plot.py` | Snaps the full .STOXX50E chain and plots bid/ask vs strike per expiry. |

## First run

```
python batch_probe.py     # note the largest clean size
python snap_plot.py       # after setting BATCH to that size
```
