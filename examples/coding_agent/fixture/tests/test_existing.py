from timebox import format_seconds


def test_existing_format():
    assert format_seconds(3661) == "1h 1m 1s"
