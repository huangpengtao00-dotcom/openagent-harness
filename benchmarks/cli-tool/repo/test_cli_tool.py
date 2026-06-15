from cli_tool import main


def test_invalid_flag_returns_nonzero():
    assert main(["--bad"]) == 2
