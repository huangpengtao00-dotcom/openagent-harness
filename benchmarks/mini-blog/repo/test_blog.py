from blog import create_post


def test_slug_conflict_returns_409():
    assert create_post({"hello"}, "hello")["status"] == 409
