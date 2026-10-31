import os, sys, time
os.environ.setdefault("OMP_NUM_THREADS", "4"); os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "4")
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "fieldserver" / "src"))
t0 = time.monotonic()
from analyzer import birdnet, quality
print(f"model load: {time.monotonic()-t0:.1f}s", flush=True)
from fieldserver.stores.media import MediaStore

db = Path(os.environ.get("FIELD_DB") or REPO / "fieldserver" / "instance" / "field.db")
store = MediaStore(db, db.parent / "media")
import sqlite3
conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
for cid in [int(a) for a in sys.argv[1:]] or (197, 158, 153):
    row = conn.execute("select m.*, c.duration_sec, c.latitude lat, c.longitude lon from media m join captures c on c.id=m.capture_id where c.id=? and m.kind='audio' order by m.id desc limit 1", (cid,)).fetchone()
    path = store.path(dict(row))
    t = time.monotonic(); env, dur = birdnet.waveform_envelope(path); t_env = time.monotonic()-t
    t = time.monotonic(); wav = birdnet.to_wav(path); t_wav = time.monotonic()-t
    t = time.monotonic(); calls = birdnet.analyze(wav, lat=row["lat"], lon=row["lon"]); t_an = time.monotonic()-t
    t = time.monotonic(); quality.measure(wav); t_q = time.monotonic()-t
    wav.unlink(missing_ok=True)
    print(f"capture {cid}: {row['duration_sec']:.0f}s audio, {row['bytes']/1e6:.2f} MB flac | envelope {t_env:.1f}s, decode {t_wav:.1f}s, birdnet {t_an:.1f}s, quality {t_q:.1f}s, total {t_env+t_wav+t_an+t_q:.1f}s, {len(calls)} calls", flush=True)
