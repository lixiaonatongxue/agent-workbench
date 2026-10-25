from app.doctor.tokens import estimate_tokens


def test_empty():
    assert estimate_tokens("") == 0


def test_pure_english():
    # 11 chars / 3.5 ≈ 3.14 → 3
    assert estimate_tokens("hello world") == 3


def test_pure_chinese():
    # 8 chars / 1.8 = 4.4 → 4
    assert estimate_tokens("使用包管理器安装") == 4


def test_mixed_weighting():
    text = "use pnpm 使用 pnpm"
    # cjk=2 → 2/1.8 ≈ 1.11 ; other=13 → 13/3.5 ≈ 3.71 → total ≈ 4.8 → 5
    assert estimate_tokens(text) == 5


def test_ratios_configurable():
    assert estimate_tokens("hello world", other_ratio=1.0) == 11
