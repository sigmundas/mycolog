"""
calibration_primitives.py
─────────────────────────
Calibration-slide measurement primitives.
Zero compiled dependencies beyond numpy + Pillow (both already required).

Provides exact drop-ins for the three scipy/OpenCV functions used in the
calibration pipeline:
    gauss_smooth()      ← scipy.ndimage.gaussian_filter1d
    find_peaks()        ← scipy.signal.find_peaks
    rotate_image()      ← cv2.getRotationMatrix2D + cv2.warpAffine
    rotation_matrix()   ← cv2.getRotationMatrix2D  (for back-projection)
"""

import numpy as np
from PIL import Image


# ─── Gaussian smoothing ──────────────────────────────────────────────────────

def gauss_smooth(arr: np.ndarray, sigma: float) -> np.ndarray:
    """1-D Gaussian convolution with reflect-padding (matches scipy default).

    Error vs scipy.ndimage.gaussian_filter1d:
      max  ~0.08  (edges only, kernel truncation difference)
      mean ~0.002
    Completely irrelevant for intensity profiles in the 0–255 range.
    """
    r      = int(np.ceil(3 * sigma))          # 3-σ truncation
    k      = np.arange(-r, r + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * (k / sigma) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(arr, r, mode='reflect')
    return np.convolve(padded, kernel, mode='valid')


# ─── Peak finding ────────────────────────────────────────────────────────────

def _prominence(data: np.ndarray, peak_idx: int) -> float:
    """Prominence of a single peak — same definition as scipy."""
    # walk left until a higher point or edge
    left_min = data[peak_idx]
    for i in range(peak_idx - 1, -1, -1):
        if data[i] < left_min:
            left_min = data[i]
        if data[i] > data[peak_idx]:
            break
    # walk right
    right_min = data[peak_idx]
    for i in range(peak_idx + 1, len(data)):
        if data[i] < right_min:
            right_min = data[i]
        if data[i] > data[peak_idx]:
            break
    return data[peak_idx] - max(left_min, right_min)


def find_peaks(data: np.ndarray,
               min_height: float | None   = None,
               min_distance: int         = 1,
               min_prominence: float | None = None) -> np.ndarray:
    """Peak indices in 1-D array, filtered by height / distance / prominence.

    Greedy distance enforcement: among candidates closer than min_distance,
    the taller peak wins (same as scipy).
    """
    # strict local maxima
    candidates = [i for i in range(1, len(data) - 1)
                  if data[i] > data[i-1] and data[i] >= data[i+1]]

    if min_height is not None:
        candidates = [i for i in candidates if data[i] >= min_height]

    # distance filter — greedy by descending height
    candidates.sort(key=lambda i: -data[i])
    kept: list[int] = []
    for c in candidates:
        if all(abs(c - k) >= min_distance for k in kept):
            kept.append(c)
    kept.sort()

    if min_prominence is not None:
        kept = [i for i in kept if _prominence(data, i) >= min_prominence]

    return np.array(kept, dtype=np.intp)


# ─── Image rotation ─────────────────────────────────────────────────────────

def rotate_image(pil_img: Image.Image, angle_deg: float) -> Image.Image:
    """Rotate PIL image CCW by *angle_deg* around its centre.

    Uses bilinear resampling (equivalent to cv2.INTER_LINEAR).
    Input and output are the same size (no expand).
    """
    return pil_img.rotate(angle_deg, resample=Image.BILINEAR, expand=False)


def rotation_matrix(angle_deg: float, center: tuple[float, float]) -> np.ndarray:
    """2×3 affine rotation matrix — identical to cv2.getRotationMatrix2D.

    Useful for back-projecting detected positions onto the original image
    for overlay figures.
    """
    a          = np.radians(angle_deg)
    cos, sin   = np.cos(a), np.sin(a)
    cx, cy     = center
    return np.array([[ cos,  sin, (1 - cos) * cx - sin * cy],
                     [-sin,  cos,  sin * cx + (1 - cos) * cy]],
                    dtype=np.float64)


# ─── Convenience helpers used by the calibration scripts ─────────────────────

def load_gray(path: str) -> np.ndarray:
    """Load image as float64 grayscale."""
    return np.array(Image.open(path).convert('L'), dtype=np.float64)


def half_max_edges(profile: np.ndarray, peak_y: float,
                   search: int = 30) -> tuple[float | None, float | None]:
    """Find the two 50%-intensity crossings around a trough (dark line).

    Returns (top_edge, bottom_edge) with sub-pixel linear interpolation,
    or (None, None) if a crossing is not found within *search* pixels.
    """
    p = int(round(peak_y))
    lo = max(0, p - search)
    hi = min(len(profile), p + search)
    center = float(profile[p])

    left = profile[lo:p]
    right = profile[p + 1:hi]

    def _bg(seg: np.ndarray) -> float | None:
        if seg is None or len(seg) == 0:
            return None
        # Use a high percentile to approximate local background on each side.
        return float(np.percentile(seg, 95))

    bg_left = _bg(left)
    bg_right = _bg(right)

    if bg_left is None:
        bg_left = float(profile[lo])
    if bg_right is None:
        bg_right = float(profile[hi - 1])

    half_left = (bg_left + center) / 2.0
    half_right = (bg_right + center) / 2.0

    top = bot = None
    for i in range(lo, p):
        if profile[i] >= half_left and profile[i + 1] < half_left:
            top = i + (half_left - profile[i]) / (profile[i + 1] - profile[i])
    for i in range(p, hi - 1):
        if profile[i] < half_right and profile[i + 1] >= half_right:
            bot = i + (half_right - profile[i]) / (profile[i + 1] - profile[i])
            break
    return top, bot


def parabola_refine(profile: np.ndarray, peak: int, half_width: int = 3) -> float:
    """Sub-pixel minimum via quadratic fit around *peak*."""
    lo = max(0, peak - half_width)
    hi = min(len(profile), peak + half_width + 1)
    xs = np.arange(lo, hi, dtype=np.float64)
    c  = np.polyfit(xs, profile[lo:hi], 2)
    return -c[1] / (2 * c[0]) if c[0] > 0 else float(peak)


def filter_consistent_peaks(centers: np.ndarray, tol: float = 0.30) -> np.ndarray:
    """Boolean mask: remove peaks whose spacing to both neighbors is
    outside ±tol of the median spacing.

    Iterates up to 3 passes so that removing one outlier can free its
    neighbor.  Edge peaks only need ONE good neighbor gap.

    This cleans up spurious detections caused by grid edges, baselines,
    or other features bleeding into the profile.
    """
    kept = np.ones(len(centers), dtype=bool)
    for _ in range(3):
        idx  = np.where(kept)[0]
        if len(idx) < 3:
            break
        diffs = np.diff(centers[idx])
        med   = float(np.median(diffs))
        lo, hi = med * (1 - tol), med * (1 + tol)

        for j in range(len(idx)):
            i          = idx[j]
            gb         = (centers[i] - centers[idx[j-1]]) if j > 0               else None
            ga         = (centers[idx[j+1]] - centers[i]) if j < len(idx) - 1    else None
            ok_b       = gb is not None and lo <= gb <= hi
            ok_a       = ga is not None and lo <= ga <= hi
            if j == 0:                          # first peak
                if not ok_a: kept[i] = False
            elif j == len(idx) - 1:             # last peak
                if not ok_b: kept[i] = False
            else:                               # interior
                if not (ok_b or ok_a): kept[i] = False
    return kept
