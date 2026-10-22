"""Stage 2: measure every arm with band SNR and the real analyzer.

    pipelines/representation/.venv-birdnet/bin/python stage2_analyze.py

Reads band SNR but does not let it decide. It is a 99th-over-10th-percentile
ratio, so an arm that gates the quiet passages toward zero inflates it almost by
construction — the same mechanism that puts merged captures at infinity. Species
confidence and detection count are what the question turns on.
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.snr import band_snr  # noqa: E402

from analyzer import analyze  # noqa: E402

MOWER = [94, 95, 96, 97]
ARMS = ["raw", "hp300", "band16", "denoise", "hp300_denoise"]
LAT, LON = 40.77, -111.88  # site, ~1 km rounded on purpose
ARMS_DIR = Path(__file__).resolve().parent / "work" / "arms"
RESULTS = Path(__file__).resolve().parent / "results.json"


def main():
    rows = []
    for cid in MOWER:
        for arm in ARMS:
            path = ARMS_DIR / f"{cid}-{arm}.wav"
            x, sr = sf.read(path, always_2d=False)
            regions = analyze(path, lat=LAT, lon=LON)
            confs = [r["crow_conf"] for r in regions]
            rows.append({
                "capture": cid,
                "arm": arm,
                "band_snr_db": round(float(band_snr(x, sr)), 2),
                "n_regions": len(regions),
                "max_crow_conf": round(max(confs), 3) if confs else None,
                "mean_crow_conf": round(float(np.mean(confs)), 3) if confs else None,
                "species": sorted({r["species"] for r in regions}),
                "call_types": sorted({str(r["call_type"]) for r in regions}),
                "total_region_sec": round(
                    sum(r["end"] - r["start"] for r in regions), 1),
            })
            print(f"  {cid} {arm:<14} snr={rows[-1]['band_snr_db']:>6.2f}  "
                  f"n={len(regions)}  max={rows[-1]['max_crow_conf']}")

    RESULTS.write_text(json.dumps(rows, indent=2))

    print("\n" + "=" * 78)
    print("BAND SNR (dB) — inflated by gating, read with suspicion")
    print("=" * 78)
    print(f"{'capture':>8}  " + "".join(f"{a:>15}" for a in ARMS))
    for cid in MOWER:
        vals = {r["arm"]: r["band_snr_db"] for r in rows if r["capture"] == cid}
        print(f"{cid:>8}  " + "".join(f"{vals[a]:>15.2f}" for a in ARMS))

    print("\n" + "=" * 78)
    print("MAX SPECIES CONFIDENCE — the honest measure")
    print("=" * 78)
    print(f"{'capture':>8}  " + "".join(f"{a:>15}" for a in ARMS))
    for cid in MOWER:
        vals = {r["arm"]: r["max_crow_conf"] for r in rows if r["capture"] == cid}
        print(f"{cid:>8}  " + "".join(
            f"{(f'{vals[a]:.3f}' if vals[a] is not None else 'none'):>15}" for a in ARMS))

    print("\n" + "=" * 78)
    print("DETECTED REGIONS  (count / total seconds)")
    print("=" * 78)
    print(f"{'capture':>8}  " + "".join(f"{a:>15}" for a in ARMS))
    for cid in MOWER:
        vals = {r["arm"]: r for r in rows if r["capture"] == cid}
        print(f"{cid:>8}  " + "".join(
            f"{vals[a]['n_regions']:>10} /{vals[a]['total_region_sec']:>4.0f}s" for a in ARMS))

    print("\n" + "=" * 78)
    print("TOTALS ACROSS THE FOUR CAPTURES")
    print("=" * 78)
    for arm in ARMS:
        sub = [r for r in rows if r["arm"] == arm]
        confs = [r["max_crow_conf"] for r in sub if r["max_crow_conf"] is not None]
        print(f"  {arm:<15} regions={sum(r['n_regions'] for r in sub):>3}  "
              f"captures detected={len(confs)}/4  "
              f"mean max-conf={np.mean(confs):.3f}" if confs else
              f"  {arm:<15} nothing detected")


if __name__ == "__main__":
    main()
