"""Раскладка кадра 1080×1920: всё значимое (текст, цифры, полосы) — внутри безопасной зоны."""
W, H = 1080, 1920


def safe_box(cfg):
    z = cfg.get("safeZone") or {}
    return (z.get("left", 65), z.get("top", 270), W - z.get("right", 130), z.get("bottom", 1440))


def in_safe_zone(box, cfg):
    """box = (x0, y0, x1, y1) в пикселях кадра."""
    l, t, r, b = safe_box(cfg)
    x0, y0, x1, y1 = box
    return x0 >= l and y0 >= t and x1 <= r and y1 <= b
