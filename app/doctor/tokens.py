"""Token estimation for mixed CJK/latin text.

Coarse but decision-grade: CJK chars / 1.8 + other chars / 3.5, both ratios
configurable. Error vs real tokenizers is < 15% for typical rule files, which
is enough to decide "should this file go on a diet".
"""

from __future__ import annotations

import re

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")

DEFAULT_CJK_RATIO = 1.8
DEFAULT_OTHER_RATIO = 3.5


def estimate_tokens(text: str, cjk_ratio: float = DEFAULT_CJK_RATIO,
                    other_ratio: float = DEFAULT_OTHER_RATIO) -> int:
    """Estimate token count of `text` with dual-ratio weighting."""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return round(cjk / cjk_ratio + other / other_ratio)
