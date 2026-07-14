"""Scientific figure metrics and annotations."""

from __future__ import annotations

import numpy as np


def threshold_crossings(x: np.ndarray, y: np.ndarray, threshold: float) -> list[float]:
    crossings: list[float] = []
    for index in range(len(x) - 1):
        left = y[index] - threshold
        right = y[index + 1] - threshold
        if left == 0:
            crossings.append(float(x[index]))
        if left * right < 0:
            t = (threshold - y[index]) / (y[index + 1] - y[index])
            crossings.append(float(x[index] + t * (x[index + 1] - x[index])))
    if y[-1] == threshold:
        crossings.append(float(x[-1]))
    return crossings


def s11_band(x: np.ndarray, y: np.ndarray, threshold: float = -10.0) -> dict | None:
    min_index = int(np.nanargmin(y))
    fr = float(x[min_index])
    crossings = threshold_crossings(x, y, threshold)
    left = [value for value in crossings if value <= fr]
    right = [value for value in crossings if value >= fr]
    if not left or not right:
        return {"fr": fr, "smin": float(y[min_index])}
    fl = max(left)
    fh = min(right)
    fc = (fl + fh) / 2.0
    bw = fh - fl
    fbw = bw / fc * 100.0 if fc else float("nan")
    return {"fr": fr, "smin": float(y[min_index]), "fl": fl, "fh": fh, "fc": fc, "bw": bw, "fbw": fbw}
