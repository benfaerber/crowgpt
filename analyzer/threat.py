"""Semantic threat translator head for corvid call regions.

Runs alongside BirdNET's call-type head on CPU with zero extra dependencies:
takes the BirdNET 3072-d pooled region embedding plus 52 crow-band prosodic
and envelope-tempo features extracted strictly over the region's crow-detected
windows, and returns Platt-calibrated one-vs-rest probabilities + prior-adjusted
likelihood ratios (`lift`) across four semantic classes:

    owl | hawk | terrestrial | non_threat

The head is optional per species (currently trained for American Crow from
Experiment 0102's 378 strict witnessed Xeno-canto + Macaulay archive recordings).
Species without a `threat_clf.joblib` simply return `None`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import joblib
import librosa
import numpy as np
from scipy.signal import butter, filtfilt, find_peaks
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
TRAINING = HERE.parent / "pipelines" / "training"
MODELS_DIR = TRAINING / "models"
sys.path.insert(0, str(TRAINING))
import pooling  # noqa: E402
from pooling import pool  # noqa: E402

THREAT_CLASSES = ("owl", "hawk", "terrestrial", "non_threat")

PROSODY_NAMES = (
    "duration_s",
    "crow_frac",
    "band_rms_mean",
    "band_rms_std",
    "band_rms_p90_p50",
    "duty_cycle",
    "onset_rate_hz",
    "centroid_hz_mean",
    "centroid_hz_std",
    "bandwidth_hz_mean",
    "flatness_mean",
    "flatness_std",
    "zcr_mean",
    "rolloff_hz_mean",
    "low_mid_ratio",
    *(f"mfcc_mean_{i}" for i in range(13)),
    *(f"mfcc_std_{i}" for i in range(13)),
)

SPEED_NAMES = (
    "peak_rate_med",
    "peak_rate_p90",
    "burst_hz_med",
    "burst_hz_p75",
    "med_ipi_s",
    "mod_centroid_hz",
    "dom_mod_hz",
    "slow_0.5_1.8",
    "mid_1.8_3.2",
    "fast_3.2_7.0",
    "fast_to_slow",
)

AUX_DIM = len(PROSODY_NAMES) + len(SPEED_NAMES)  # 41 + 11 = 52
THREAT_FEATURE = f"{pooling.FEATURE}+prosody_speed_{AUX_DIM}"


class ThreatMismatch(RuntimeError):
    """Refuse a threat head whose feature provenance or dimensions do not match."""


def extract_prosody(y: np.ndarray, sr: int, windows: list[tuple[float, float]]) -> np.ndarray:
    """Crow-band (600-4500 Hz) prosodic & spectral-MFCC summary (41-d)."""
    if len(y) == 0:
        return np.zeros(len(PROSODY_NAMES), dtype=np.float32)

    dur = len(y) / sr
    if windows:
        chunks = []
        for s, e in windows:
            i0 = max(0, int(s * sr))
            i1 = min(len(y), int(e * sr))
            if i1 - i0 >= int(0.5 * sr):
                chunks.append(y[i0:i1])
        seg_y = np.concatenate(chunks) if chunks else y
        crow_frac = min(1.0, (len(seg_y) / sr) / max(dur, 1e-6))
    else:
        seg_y = y
        crow_frac = 0.0

    seg_y = seg_y[: 60 * sr]
    hop = 512
    n_fft = 1024
    S = np.abs(librosa.stft(seg_y, n_fft=n_fft, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    band = (freqs >= 600) & (freqs <= 4500)
    low_band = (freqs >= 600) & (freqs < 1800)
    mid_band = (freqs >= 1800) & (freqs <= 4500)

    S_band = S[band, :]
    band_rms = np.sqrt(np.mean(S_band ** 2, axis=0) + 1e-12)
    p50 = float(np.percentile(band_rms, 50))
    p90 = float(np.percentile(band_rms, 90))
    p20 = float(np.percentile(band_rms, 20))
    thresh = max(p20 * 2.5, float(np.mean(band_rms)) * 0.8)
    duty_cycle = float(np.mean(band_rms > thresh))

    onset_env = librosa.onset.onset_strength(
        S=librosa.amplitude_to_db(S_band + 1e-8), sr=sr, hop_length=hop,
    )
    onsets = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, hop_length=hop,
        wait=int(0.18 * sr / hop), backtrack=False,
    )
    onset_rate = float(len(onsets) / max(len(seg_y) / sr, 1e-3))

    act = band_rms >= p50
    if not np.any(act):
        act = np.ones_like(band_rms, dtype=bool)
    S_act = S[:, act]

    centroid = librosa.feature.spectral_centroid(S=S_act, sr=sr)[0]
    bandwidth = librosa.feature.spectral_bandwidth(S=S_act, sr=sr)[0]
    flatness = librosa.feature.spectral_flatness(S=S_band[:, act] + 1e-10)[0]
    rolloff = librosa.feature.spectral_rolloff(S=S_act, sr=sr)[0]
    zcr = librosa.feature.zero_crossing_rate(seg_y, frame_length=n_fft, hop_length=hop)[0]
    low_e = float(np.mean(S[low_band, :][:, act] ** 2))
    mid_e = float(np.mean(S[mid_band, :][:, act] ** 2))
    low_mid_ratio = float(np.log((low_e + 1e-10) / (mid_e + 1e-10)))

    mfccs = librosa.feature.mfcc(y=seg_y, sr=sr, n_mfcc=13, fmin=500, fmax=6000)
    vec = np.array([
        dur,
        crow_frac,
        float(np.mean(band_rms)),
        float(np.std(band_rms)),
        float(p90 / max(p50, 1e-8)),
        duty_cycle,
        onset_rate,
        float(np.mean(centroid)),
        float(np.std(centroid)),
        float(np.mean(bandwidth)),
        float(np.mean(flatness)),
        float(np.std(flatness)),
        float(np.mean(zcr)),
        float(np.mean(rolloff)),
        low_mid_ratio,
        *np.mean(mfccs, axis=1).tolist(),
        *np.std(mfccs, axis=1).tolist(),
    ], dtype=np.float32)
    return np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)


def extract_speed(y: np.ndarray, sr: int, windows: list[tuple[float, float]] | None = None) -> np.ndarray:
    """Crow-band (700-4500 Hz) envelope peak-rate & modulation spectrum features (11-d)."""
    if windows:
        chunks = []
        for s, e in windows:
            i0 = max(0, int(s * sr))
            i1 = min(len(y), int(e * sr))
            if i1 - i0 >= int(0.5 * sr):
                chunks.append(y[i0:i1])
        seg = np.concatenate(chunks) if chunks else y
    else:
        seg = y

    seg = seg[: 60 * sr]
    if len(seg) < int(sr * 1.5):
        return np.zeros(len(SPEED_NAMES), dtype=np.float32)

    b, a = butter(4, [700.0 / (sr / 2), 4500.0 / (sr / 2)], btype="band")
    yf = filtfilt(b, a, seg).astype(np.float32)

    # 100 Hz envelope (10 ms resolution)
    hop = max(1, int(round(sr / 100.0)))
    env = librosa.feature.rms(y=yf, frame_length=hop * 2, hop_length=hop)[0]
    env_sr = sr / hop
    env_s = np.convolve(env, np.ones(3) / 3.0, mode="same")

    win = int(round(3.0 * env_sr))
    if len(env_s) < win:
        env_s = np.pad(env_s, (0, win - len(env_s)))
    n_win = len(env_s) // win
    chunks_e = env_s[: n_win * win].reshape(n_win, win)
    chunk_rms = np.mean(chunks_e, axis=1)
    act_mask = chunk_rms >= max(np.percentile(chunk_rms, 50), 0.35 * np.max(chunk_rms))
    act_chunks = chunks_e[act_mask] if np.any(act_mask) else chunks_e

    peak_rates, all_ipis, mod_spectra = [], [], []
    freqs = np.fft.rfftfreq(win, d=1.0 / env_sr)
    for ch in act_chunks:
        lo, hi = np.percentile(ch, 10), np.percentile(ch, 98)
        if hi - lo < 1e-6:
            continue
        cn = np.clip((ch - lo) / (hi - lo), 0.0, 1.5)
        peaks, _ = find_peaks(cn, distance=max(1, int(0.12 * env_sr)), prominence=0.18, height=0.25)
        peak_rates.append(len(peaks) / 3.0)
        if len(peaks) >= 2:
            ipis = np.diff(peaks) / env_sr
            all_ipis.extend(ipis[(ipis >= 0.12) & (ipis <= 2.0)].tolist())
        cz = (cn - np.mean(cn)) * np.hanning(win)
        mod_spectra.append(np.abs(np.fft.rfft(cz)) ** 2)

    if not mod_spectra:
        return np.zeros(len(SPEED_NAMES), dtype=np.float32)

    ms = np.mean(mod_spectra, axis=0)
    m_all = (freqs >= 0.5) & (freqs <= 8.0)
    m_slow = (freqs >= 0.5) & (freqs < 1.8)
    m_mid = (freqs >= 1.8) & (freqs < 3.2)
    m_fast = (freqs >= 3.2) & (freqs <= 7.0)
    tot = float(np.sum(ms[m_all]) + 1e-12)
    sf = float(np.sum(ms[m_slow]) / tot)
    mf = float(np.sum(ms[m_mid]) / tot)
    ff = float(np.sum(ms[m_fast]) / tot)
    mc = float(np.sum(freqs[m_all] * ms[m_all]) / tot)
    df = float(freqs[m_all][int(np.argmax(ms[m_all]))])
    med_ipi = float(np.median(all_ipis)) if all_ipis else 1.5
    p25_ipi = float(np.percentile(all_ipis, 25)) if all_ipis else 1.5

    vec = np.array([
        float(np.median(peak_rates)),
        float(np.percentile(peak_rates, 90)),
        float(1.0 / max(med_ipi, 0.12)),
        float(1.0 / max(p25_ipi, 0.12)),
        med_ipi,
        mc,
        df,
        sf,
        mf,
        ff,
        float(np.log((ff + 1e-4) / (sf + 1e-4))),
    ], dtype=np.float32)
    return np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)


def extract_region_aux(audio_path: Path | str, windows: list[tuple[float, float]]) -> np.ndarray:
    """Decode audio once at 22050 Hz and extract the 52-d prosody + speed vector for a region."""
    y, sr = librosa.load(str(audio_path), sr=22050, mono=True, duration=180.0)
    pros = extract_prosody(y, sr, windows)
    spd = extract_speed(y, sr, windows)
    return np.concatenate([pros, spd]).astype(np.float32)


class CalibratedThreatHead:
    """Block-standardized One-vs-Rest head with out-of-fold Platt sigmoid calibration."""

    def __init__(self, classes: list[str] | tuple[str, ...], C: float = 0.05, prosody_weight: float = 0.35):
        self.classes = list(classes)
        self.C = C
        self.prosody_weight = prosody_weight
        self.bn_scaler = StandardScaler()
        self.aux_scaler = StandardScaler()
        self.models: dict[str, LogisticRegression] = {}
        self.calibrators: dict[str, LogisticRegression] = {}
        self.priors: dict[str, float] = {}

    def _transform(self, X_bn: np.ndarray, X_aux: np.ndarray | None, fit: bool = False) -> np.ndarray:
        bn = self.bn_scaler.fit_transform(X_bn) if fit else self.bn_scaler.transform(X_bn)
        if X_aux is None or self.prosody_weight <= 0:
            return bn
        aux = self.aux_scaler.fit_transform(X_aux) if fit else self.aux_scaler.transform(X_aux)
        scale = self.prosody_weight * np.sqrt(bn.shape[1] / max(aux.shape[1], 1))
        return np.hstack([bn, aux * scale])

    def fit(self, X_bn: np.ndarray, X_aux: np.ndarray | None, y: np.ndarray, groups: np.ndarray):
        cv = StratifiedGroupKFold(n_splits=5)
        oof_scores = {c: np.zeros(len(y), dtype=np.float64) for c in self.classes}
        for c in self.classes:
            yb = (y == c).astype(int)
            self.priors[c] = float(np.mean(yb))
            for tr, te in cv.split(X_bn, yb, groups):
                sc_b = StandardScaler().fit(X_bn[tr])
                bn_tr, bn_te = sc_b.transform(X_bn[tr]), sc_b.transform(X_bn[te])
                if X_aux is not None and self.prosody_weight > 0:
                    sc_a = StandardScaler().fit(X_aux[tr])
                    s = self.prosody_weight * np.sqrt(bn_tr.shape[1] / max(X_aux.shape[1], 1))
                    Xtr = np.hstack([bn_tr, sc_a.transform(X_aux[tr]) * s])
                    Xte = np.hstack([bn_te, sc_a.transform(X_aux[te]) * s])
                else:
                    Xtr, Xte = bn_tr, bn_te
                clf = LogisticRegression(C=self.C, max_iter=3000, class_weight="balanced").fit(Xtr, yb[tr])
                oof_scores[c][te] = clf.decision_function(Xte)

        X_full = self._transform(X_bn, X_aux, fit=True)
        for c in self.classes:
            yb = (y == c).astype(int)
            self.models[c] = LogisticRegression(C=self.C, max_iter=3000, class_weight="balanced").fit(X_full, yb)
            self.calibrators[c] = LogisticRegression(C=1.0, max_iter=1000).fit(oof_scores[c][:, None], yb)
        return self

    def predict_proba(self, X_bn: np.ndarray, X_aux: np.ndarray | None = None) -> np.ndarray:
        X = self._transform(X_bn, X_aux, fit=False)
        out = np.zeros((len(X), len(self.classes)), dtype=np.float64)
        for j, c in enumerate(self.classes):
            raw = self.models[c].decision_function(X)[:, None]
            out[:, j] = self.calibrators[c].predict_proba(raw)[:, 1]
        return out


def check_threat_bundle(bundle: dict, model_path: Path | str) -> None:
    """Refuse a threat head with missing provenance or incompatible feature dimensions."""
    feature = bundle.get("feature")
    if feature != THREAT_FEATURE:
        raise ThreatMismatch(
            f"{model_path} was trained on '{feature}'; analyzer expects '{THREAT_FEATURE}'."
        )
    bn_dim = bundle.get("bn_dim")
    aux_dim = bundle.get("aux_dim")
    if bn_dim != pooling.POOLED_DIM or aux_dim != AUX_DIM:
        raise ThreatMismatch(
            f"{model_path} expects ({bn_dim}, {aux_dim}) dims; "
            f"analyzer produces ({pooling.POOLED_DIM}, {AUX_DIM})."
        )


class ThreatHead:
    """One species' calibrated semantic threat translator."""

    def __init__(self, display: str, model_path: Path, metrics_path: Path):
        bundle = joblib.load(model_path)
        check_threat_bundle(bundle, model_path)
        self.display = display
        self.path = Path(model_path)
        self.model: CalibratedThreatHead = bundle["model"]
        self.classes: list[str] = list(bundle["classes"])
        self.priors: dict[str, float] = dict(bundle.get("priors") or getattr(self.model, "priors", {}))
        self.metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()[:6]

    def predict_region(
        self,
        embeddings: list[np.ndarray],
        audio_path: Path | str | None = None,
        windows: list[tuple[float, float]] | None = None,
        aux: np.ndarray | None = None,
    ) -> dict:
        """Return calibrated probabilities, prior-adjusted lifts, caw speed, and top label."""
        bn_vec = pool(embeddings).reshape(1, -1).astype(np.float32)
        if aux is None:
            if audio_path is not None:
                aux_vec = extract_region_aux(audio_path, windows or [])
            else:
                aux_vec = np.zeros(AUX_DIM, dtype=np.float32)
        else:
            aux_vec = np.asarray(aux, dtype=np.float32).reshape(-1)

        probs_arr = self.model.predict_proba(bn_vec, aux_vec.reshape(1, -1))[0]
        probs = {c: round(float(probs_arr[j]), 3) for j, c in enumerate(self.classes)}
        lift = {
            c: round(float(probs_arr[j] / max(self.priors.get(c, 0.25), 1e-4)), 2)
            for j, c in enumerate(self.classes)
        }
        top_prob = max(self.classes, key=lambda c: probs[c])
        # Prior-adjusted verdict: pick the strongest elevated threat if any threat has lift >= 1.5
        # and non_threat is not overwhelmingly dominant; otherwise non_threat.
        threat_classes = [c for c in self.classes if c != "non_threat"]
        best_threat = max(threat_classes, key=lambda c: lift[c]) if threat_classes else top_prob
        if best_threat and lift[best_threat] >= 1.5 and probs.get("non_threat", 0.0) < 0.70:
            verdict = best_threat
        else:
            verdict = "non_threat" if "non_threat" in probs else top_prob

        caws_per_s = round(float(aux_vec[len(PROSODY_NAMES)]), 2) if len(aux_vec) == AUX_DIM else 0.0
        return {
            "label": verdict,
            "top_prob": top_prob,
            "probs": probs,
            "lift": lift,
            "caws_per_s": caws_per_s,
            "model": f"threat@{self.fingerprint}",
        }


class ThreatRegistry:
    """Maps a detected species common name to its semantic threat head, if shipped."""

    def __init__(self, models_dir: Path = MODELS_DIR):
        self.heads: dict[str, ThreatHead] = {}
        for directory in sorted(p for p in models_dir.glob("*") if p.is_dir()):
            model = directory / "threat_clf.joblib"
            if model.exists():
                display = directory.name.replace("-", " ").title()
                self.heads[self.key(display)] = ThreatHead(
                    display, model, directory / "threat_metrics.json",
                )

    @staticmethod
    def key(name: str) -> str:
        return " ".join((name or "").replace("-", " ").lower().split())

    def for_species(self, common_name: str) -> ThreatHead | None:
        return self.heads.get(self.key(common_name))
