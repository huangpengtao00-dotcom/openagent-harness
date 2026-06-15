from csv_cleaner import clean_cell


def test_clean_cell_removes_utf8_bom():
    assert clean_cell("\ufeffname") == "name"
