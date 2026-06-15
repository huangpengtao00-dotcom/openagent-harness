from app import divide


def test_divide_zero_returns_none():
    assert divide(4, 0) is None
