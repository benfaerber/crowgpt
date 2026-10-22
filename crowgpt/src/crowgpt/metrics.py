"""Spectral distances for the gate and the judge.

Multi-resolution STFT rather than a single log-mel, because a caw's identity is
partly in 10-30 ms pulse structure and a 25 ms-hop mel integrates exactly that
away. The three scales are the Parallel WaveGAN convention scaled to 24 kHz; the
128-point one (5.3 ms) is the one that catches onset smearing, which is the
first thing a codec loses.
"""

import numpy as np
from scipy.signal import stft

SCALES = ((2048, 512, 1200), (512, 128, 240), (128, 32, 60))


def _magnitude(samples, n_fft, hop, win_length):
    _, _, spectrum = stft(
        samples,
        nperseg=win_length,
        noverlap=win_length - hop,
        nfft=n_fft,
        padded=True,
        boundary="zeros",
    )
    return np.abs(spectrum)


def multi_res_stft_distance(reference, estimate):
    """Mean spectral-convergence + log-magnitude distance across three scales.

    Lower is closer. Sensitive to the same length, so callers must align first.
    """
    reference = np.asarray(reference, dtype=np.float64)
    estimate = np.asarray(estimate, dtype=np.float64)
    n = min(reference.size, estimate.size)
    reference, estimate = reference[:n], estimate[:n]

    losses = []
    for n_fft, hop, win_length in SCALES:
        if n < win_length:
            continue
        ref_mag = _magnitude(reference, n_fft, hop, win_length)
        est_mag = _magnitude(estimate, n_fft, hop, win_length)
        width = min(ref_mag.shape[1], est_mag.shape[1])
        ref_mag, est_mag = ref_mag[:, :width], est_mag[:, :width]

        denominator = np.linalg.norm(ref_mag) or 1e-12
        convergence = np.linalg.norm(ref_mag - est_mag) / denominator
        log_distance = np.mean(
            np.abs(np.log(ref_mag + 1e-7) - np.log(est_mag + 1e-7))
        )
        losses.append(convergence + log_distance)
    return float(np.mean(losses)) if losses else float("nan")


def codebook_entropy(codes, codebook_size=1024):
    """Bits actually used per residual stage, out of a possible 10.

    A stage well under the ceiling is close to noise, and paying sequence length
    for it buys nothing. This is what picks the number of codebooks, not the
    round-trip score on its own.
    """
    codes = np.asarray(codes)
    out = []
    for stage in codes:
        counts = np.bincount(stage.reshape(-1), minlength=codebook_size).astype(np.float64)
        probabilities = counts[counts > 0] / counts.sum()
        out.append(float(-np.sum(probabilities * np.log2(probabilities))))
    return out


def frechet_distance(real, generated, eps=1e-6):
    """Fréchet distance between two sets of embeddings. Lower is closer.

    The standard generative-audio metric, and the reason to want it here is
    statistical power. A detection rate thresholds every clip at 0.25 and throws
    the rest of the signal away, so telling a 50% model from a 61% one needs
    hundreds of samples — the judge gave two readings of ONE model 18 points
    apart. This compares the whole distribution, mean and covariance together,
    and moves smoothly rather than in units of one clip crossing a threshold.

    It also answers a different question. A detection rate asks "did BirdNET
    call this a crow"; this asks "does the set of generated calls occupy the
    same region as the set of real ones". A model that produced one perfect caw
    over and over would score well on the first and badly on this.

    Implementation is the usual FID one: means, covariances, and the trace of
    the geometric mean. The diagonal nudge for a singular covariance — which is
    what a few hundred samples in 1024 dimensions gives you — is applied only if
    the plain square root fails, because applying it always shifts the floor off
    zero and a metric you cannot sanity-check is worth less than one you can.
    """
    from scipy import linalg

    real = np.asarray(real, dtype=np.float64)
    generated = np.asarray(generated, dtype=np.float64)
    if real.ndim != 2 or generated.ndim != 2:
        raise ValueError("embeddings must be [n, dim]")
    if min(len(real), len(generated)) < 2:
        raise ValueError("need at least two of each to estimate a covariance")

    mu_real, mu_gen = real.mean(axis=0), generated.mean(axis=0)
    cov_real = np.cov(real, rowvar=False)
    cov_gen = np.cov(generated, rowvar=False)

    # Nudge the diagonal only if the plain square root fails. Adding eps
    # unconditionally biases the trace term by -2*eps*dim, which is small but
    # means two identical sets do not score exactly zero — and a metric whose
    # floor is not zero is one nobody can sanity-check.
    covmean, _ = linalg.sqrtm(cov_real @ cov_gen, disp=False)
    if not np.isfinite(covmean).all():
        offset = np.eye(cov_real.shape[0]) * eps
        covmean, _ = linalg.sqrtm((cov_real + offset) @ (cov_gen + offset), disp=False)
    if np.iscomplexobj(covmean):
        # A tiny imaginary part is numerical noise from sqrtm; a large one means
        # the inputs were not usable and silently taking the real part would
        # hide that.
        if not np.allclose(covmean.imag, 0, atol=1e-3):
            raise ValueError("covariance square root is complex — embeddings are degenerate")
        covmean = covmean.real

    diff = mu_real - mu_gen
    return float(diff @ diff + np.trace(cov_real) + np.trace(cov_gen) - 2 * np.trace(covmean))


def bootstrap_ci(values, statistic=np.mean, resamples=2000, level=0.95, seed=0):
    """Percentile bootstrap interval, because a bare percentage invites belief.

    Every score this project quotes came with no error bar until two readings of
    the same model landed 18 points apart.
    """
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return None, None
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, values.size, size=(resamples, values.size))
    stats = np.sort(statistic(values[draws], axis=1))
    tail = (1 - level) / 2
    return float(stats[int(tail * resamples)]), float(stats[int((1 - tail) * resamples) - 1])


def paired_difference(a, b, resamples=2000, level=0.95, seed=0):
    """Bootstrap the difference between two models scored on the SAME conditions.

    Pairing is what makes a few hundred clips enough. Most of the variance in a
    judged score is the condition — which ambience clip, which species, which
    seed — not the model, and comparing matched conditions cancels it. An
    interval that excludes zero is a real difference; one that spans it is not,
    however far apart the two averages look.
    """
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError("paired comparison needs the same conditions on both sides")
    differences = a - b
    low, high = bootstrap_ci(differences, resamples=resamples, level=level, seed=seed)
    return {
        "mean_difference": float(differences.mean()),
        "ci": (low, high),
        "significant": bool(low is not None and (low > 0 or high < 0)),
        "n_pairs": int(differences.size),
    }
