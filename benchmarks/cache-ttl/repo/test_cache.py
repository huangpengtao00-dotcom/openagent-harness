from cache import get_cached


def test_expired_entry_is_evicted_and_returns_none():
    store = {"token": {"value": "abc", "expires_at": 10}}
    assert get_cached(store, "token", now=10) is None
    assert "token" not in store


def test_fresh_entry_is_returned():
    store = {"token": {"value": "abc", "expires_at": 11}}
    assert get_cached(store, "token", now=10) == "abc"
