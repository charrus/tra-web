import pytest

from app import parse_bank_csv

HEADER = "Date,Details,Transaction Type,In,Out\n"


def parse(*lines):
    return parse_bank_csv(HEADER + "".join(line + "\n" for line in lines))


def test_strips_currency_symbol():
    rows = parse("05/09/2025,GOOGLE CLOUD EMEA,Direct Debit,,£7.00")
    assert rows[0]["amount_out"] == 7.00
    assert rows[0]["amount_in"] == 0.0


def test_strips_thousands_separator():
    rows = parse("19/08/2025,QCE TRA funds,Inward Payment,\"£1,234.56\",")
    assert rows[0]["amount_in"] == 1234.56


def test_signed_out_column_stored_as_magnitude():
    """Some banks sign the Out column. A negative amount would render as a blank
    row and never match, so magnitudes are stored."""
    rows = parse("05/09/2025,GOOGLE CLOUD EMEA,Direct Debit,,-7.00")
    assert rows[0]["amount_out"] == 7.00


def test_converts_dd_mm_yyyy_to_iso():
    rows = parse("05/09/2025,Anything,Direct Debit,,7.00")
    assert rows[0]["date"] == "2025-09-05"


def test_accepts_iso_dates():
    rows = parse("2025-09-05,Anything,Direct Debit,,7.00")
    assert rows[0]["date"] == "2025-09-05"


def test_unparseable_date_is_rejected_with_row_number():
    with pytest.raises(ValueError) as excinfo:
        parse(
            "05/09/2025,Fine,Direct Debit,,7.00",
            "31/31/2025,Bad date,Direct Debit,,7.00",
        )
    assert "row 3" in str(excinfo.value)


def test_unparseable_amount_is_rejected_with_row_number():
    with pytest.raises(ValueError) as excinfo:
        parse("05/09/2025,Bad amount,Direct Debit,,seven pounds")
    assert "row 2" in str(excinfo.value)


def test_truncated_row_does_not_crash():
    """DictReader short-fills a truncated row with None, not ''."""
    rows = parse("05/09/2025,Details only")
    assert rows[0]["details"] == "Details only"
    assert rows[0]["amount_in"] == 0.0
    assert rows[0]["amount_out"] == 0.0


def test_blank_date_rows_are_skipped():
    rows = parse(
        "05/09/2025,Real row,Direct Debit,,7.00",
        ",Trailing total line,,,7.00",
    )
    assert len(rows) == 1


def test_parses_real_metro_export(sample_csv):
    rows = parse_bank_csv(sample_csv)
    assert rows
    assert all(len(r["date"]) == 10 and r["date"][4] == "-" for r in rows)
    assert all(r["amount_in"] >= 0 and r["amount_out"] >= 0 for r in rows)
