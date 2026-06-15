from pager import page


def test_second_page_starts_after_first_page():
    assert page([1, 2, 3, 4, 5], 2, 2) == [3, 4]
