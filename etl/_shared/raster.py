"""Render PDF pages without imposing an OCR-specific color convention."""

from __future__ import annotations

import numpy as np
import pymupdf


def render_page_rgb(
    page: pymupdf.Page, *, dpi: float
) -> tuple[np.ndarray, tuple[float, float]]:
    """Return an RGB uint8 raster and PDF-space page size in points."""
    if dpi <= 0:
        raise ValueError(f"dpi must be positive: {dpi}")
    zoom = dpi / 72.0
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    raw = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    if pixmap.n == 1:
        rgb = np.repeat(raw, 3, axis=2)
    else:
        rgb = raw[:, :, :3]
    return rgb, (float(page.rect.width), float(page.rect.height))
