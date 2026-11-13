from majority.config import DEFAULTS
from majority.layout import in_safe_zone, safe_box


def test_safe_zone_bounds():
    assert safe_box(DEFAULTS) == (65, 270, 950, 1440)
    assert in_safe_zone((100, 300, 900, 1400), DEFAULTS)
    assert not in_safe_zone((100, 200, 900, 1400), DEFAULTS)    # залезло под шапку
    assert not in_safe_zone((100, 300, 1000, 1400), DEFAULTS)   # под кнопками справа
    assert not in_safe_zone((100, 300, 900, 1500), DEFAULTS)    # под подписью снизу
