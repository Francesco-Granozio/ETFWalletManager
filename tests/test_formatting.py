from app.utils.formatting import parse_decimal


def test_parse_decimal_accepts_italian_and_dot_decimal_formats():
    assert parse_decimal("14,56") == 14.56
    assert parse_decimal("14.56") == 14.56
    assert parse_decimal("1.234,56") == 1234.56
    assert parse_decimal("1,234.56") == 1234.56
