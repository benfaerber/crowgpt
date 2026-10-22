"""Ben's jpeg drawings -> map icons: 64 px data-URIs in the layer + 128 px
PNG masters in images/.

The pipeline earns each step from a defect: the frame circle is the
component spanning ~the whole image (new-batch drawings ship inside one);
paper texture needs a minimum component size (the Cooper's); alpha floods
the closed outline to a solid silhouette because distance-from-paper alpha
turned every white belly transparent; and `bird_only` keeps just the
largest figure and whatever touches it — the raven's sound waves and
CRAA-CRAA text were drawn detached, and Ben wants only the open beak.
"""
import base64
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

#: icon name -> (source jpeg, bird_only, eye_boost, all_dark)
#: all_dark: the bird has no white plumage, so every paper-coloured pocket
#: below the eye zone is trapped background, not feathers.
JOBS = {
    "owl-icon": ("owl-icon.jpeg", False, False, False),
    "hawk-icon": ("hawk-icon.jpeg", False, False, False),
    "peregrine-icon": ("peregrine-icon.jpeg", False, False, False),
    "crow-icon": ("crow-icon.jpeg", False, True, True),
    "coopers-hawk-icon": ("coopers-hawk-icon.jpeg", False, False, False),
    "raven-icon": ("raven-icon.jpeg", True, False, True),
    "magpie-icon": ("black-billed-magpie-icon.jpeg", False, True, False),
}


def boost_eye(img, keep, solid):
    """Redraw the eye bigger and crisper, the cartoonist's small-size trick.

    At pin size the white eye ring collapses to a smudge. The eye is the
    round paper-coloured hole in the upper half of the bird; it gets
    repainted at ~1.35x with a clean pupil and catchlight, at full
    resolution so the downscale antialiases it.
    """
    from PIL import ImageDraw
    holes = solid & ~keep
    labels, n = ndimage.label(holes)
    ys_all, xs_all = np.where(solid)
    top, height = ys_all.min(), ys_all.max() - ys_all.min()
    best = None
    for i in range(1, n + 1):
        ys, xs = np.where(labels == i)
        w, h = xs.max() - xs.min(), ys.max() - ys.min()
        if not (10 < w < 200 and 10 < h < 200):
            continue
        if abs(w - h) > 0.4 * max(w, h):
            continue
        if ys.mean() > top + 0.5 * height:
            continue
        if best is None or len(ys) > best[0]:
            best = (len(ys), (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2,
                    max(w, h) / 2)
    if best is None:
        return img
    _, cx, cy, r = best
    r2 = r * 1.35
    canvas = Image.fromarray(img.astype(np.uint8))
    draw = ImageDraw.Draw(canvas)
    def disc(radius, fill, dx=0.0, dy=0.0):
        draw.ellipse([cx + dx - radius, cy + dy - radius,
                      cx + dx + radius, cy + dy + radius], fill=fill)
    disc(r2 * 1.12, (26, 26, 30))          # outline ring
    disc(r2, (255, 255, 255))              # sclera
    disc(r2 * 0.58, (20, 20, 24), dx=-r2 * 0.12)   # pupil, toward the beak
    disc(r2 * 0.16, (255, 255, 255), dx=-r2 * 0.3, dy=-r2 * 0.25)  # catchlight
    return np.asarray(canvas).astype(int)


def process(path, bird_only=False, eye_boost=False, all_dark=False):
    img = np.asarray(Image.open(path).convert("RGB")).astype(int)
    h, w, _ = img.shape
    paper = np.median(img.reshape(-1, 3), axis=0)
    dist = np.abs(img - paper).sum(axis=2)
    ink = dist > 60
    labels, n = ndimage.label(ink)
    sizes = ndimage.sum_labels(ink, labels, index=np.arange(1, n + 1))
    keep = np.zeros_like(ink)
    kept_ids = []
    for i in range(1, n + 1):
        ys, _ = np.where(labels == i)
        if (ys.max() - ys.min()) / h > 0.9 or sizes[i - 1] < 400:
            continue
        keep |= labels == i
        kept_ids.append(i)
    if bird_only:
        main = kept_ids[int(np.argmax([sizes[i - 1] for i in kept_ids]))]
        reach = ndimage.binary_dilation(labels == main, iterations=6)
        keep = np.zeros_like(ink)
        for i in kept_ids:
            member = labels == i
            if i == main or (member & reach).any():
                keep |= member
    closed = ndimage.binary_closing(keep, iterations=2)
    solid = ndimage.binary_fill_holes(closed)
    # Punch trapped background back out: the pockets between legs, tail and
    # branch are enclosed exactly like a white belly, but they are
    # paper-coloured AND sit against the branch — plumage white never rests
    # directly on brown. The bottom-quarter rule stays for branchless art.
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    brown = (r > 90) & (r < 210) & (g > 45) & (g < 150) & (b < 110) \
        & (r > g) & (g > b)
    holes, nh = ndimage.label(solid & ~closed)
    ys_all, _ = np.where(solid)
    top, height = ys_all.min(), ys_all.max() - ys_all.min()
    for i in range(1, nh + 1):
        member = holes == i
        if dist[member].mean() >= 45:
            continue
        # Pockets are small; bodies are not. The census across all seven
        # drawings put every true pocket under ~8k px and every plumage
        # region over ~17k — without this cap the branch rule ate the
        # Cooper's cream body, which stands close enough to touch brown.
        if member.sum() >= 10_000:
            continue
        ys, _ = np.where(member)
        frac = (ys.mean() - top) / height
        low = frac > 0.65
        below_eyes = all_dark and frac > 0.25
        on_branch = (ndimage.binary_dilation(member, iterations=10) & brown).any()
        if low or below_eyes or on_branch:
            solid &= ~member
    if eye_boost:
        img = boost_eye(img, keep, solid)
    alpha = ndimage.gaussian_filter(solid.astype(float), sigma=1.5)
    ys, xs = np.where(solid)
    pad = 8
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, h)
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, w)
    rgba = np.dstack([img[y0:y1, x0:x1],
                      np.clip(alpha[y0:y1, x0:x1] * 255, 0, 255)]).astype(np.uint8)
    out = Image.fromarray(rgba, "RGBA")
    side = max(out.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(out, ((side - out.width) // 2, (side - out.height) // 2))
    return canvas


def main():
    layer = json.loads((OUT / "scout_layer.json").read_text())
    for name, (source, bird_only, eye_boost, all_dark) in JOBS.items():
        canvas = process(REPO / "data" / "temp-images" / source,
                         bird_only, eye_boost, all_dark)
        canvas.resize((128, 128), Image.LANCZOS).save(REPO / "images" / f"{name}.png")
        buf = io.BytesIO()
        canvas.resize((64, 64), Image.LANCZOS).save(buf, "PNG")
        layer["icons"][name] = ("data:image/png;base64,"
                                + base64.b64encode(buf.getvalue()).decode())
        print(f"{name}: {len(buf.getvalue()) // 1024} KB"
              + (" (bird only)" if bird_only else ""))
    (OUT / "scout_layer.json").write_text(json.dumps(layer) + "\n")


if __name__ == "__main__":
    main()
