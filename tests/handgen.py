"""Synthetic MediaPipe-like hands (21 landmarks) for tests."""
import math

import numpy as np

FINGER_BASES = [(1, -60), (5, -15), (9, 0), (13, 15), (17, 30)]  # first landmark index, base angle (deg)
SEG = [0.35, 0.25, 0.2, 0.18]


def hand(curls=(0, 0, 0, 0, 0), mirror=False):
    """(21, 2) points in a local frame, wrist at origin, fingers pointing up (-y). Size ~1."""
    pts = np.zeros((21, 2))
    for f, (start, base) in enumerate(FINGER_BASES):
        ang = math.radians(base)
        p = np.zeros(2)
        for j in range(4):
            seg = SEG[j] * (0.7 if f == 0 else 1.0) * (0.9 if f == 4 else 1.0)
            if j == 0 and f > 0:
                seg = 0.45  # palm (wrist -> MCP)
            p = p + seg * np.array([math.sin(ang), -math.cos(ang)])
            pts[start + j] = p
            if j >= (0 if f == 0 else 1) - 0:
                ang += math.radians(curls[f]) * (1 if j > 0 or f == 0 else 0)
    if mirror:
        pts[:, 0] *= -1
    return pts


def place(local, center, scale=0.15, angle_deg=0.0, aspect=16 / 9):
    """Local hand -> normalized image coords (0..1), as MediaPipe would report them."""
    a = math.radians(angle_deg)
    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    iso = (local @ rot.T) * scale + np.array([center[0] * aspect, center[1]])
    return iso / np.array([aspect, 1.0])


def seal(curls_l, curls_r, cx=0.5, cy=0.6, scale=0.15, angle=0.0, gap=0.55, noise=0.0, rng=None):
    """Two hands as one rigid group (gap in hand units), then placed/rotated/scaled together."""
    rng = rng or np.random.default_rng(0)
    left = place(hand(curls_l) + np.array([-gap, 0]), (cx, cy), scale, angle)
    right = place(hand(curls_r, mirror=True) + np.array([gap, 0]), (cx, cy), scale, angle)
    if noise:
        left = left + rng.normal(0, noise, left.shape)
        right = right + rng.normal(0, noise, right.shape)
    return [right, left]  # deliberately unsorted
