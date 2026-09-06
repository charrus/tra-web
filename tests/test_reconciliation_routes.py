import io

import db

CSV = (
    "Date,Details,Transaction Type,In,Out\n"
    "05/09/2025,GOOGLE CLOUD EMEA,Direct Debit,,7.00\n"
    "19/08/2025,QCE TRA funds,Inward Payment,4146.33,\n"
)


def upload(client, content=CSV, filename="statement.csv"):
    return client.post(
        "/reconciliation/upload",
        data={"csv_file": (io.BytesIO(content.encode()), filename)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def statement_count(conn):
    return conn.execute("SELECT COUNT(*) FROM bank_statements").fetchone()[0]


def test_upload_stores_rows(client, conn):
    upload(client)
    assert statement_count(conn) == 2


def test_reuploading_the_same_file_skips_duplicates(client, conn):
    upload(client)
    response = upload(client)
    assert statement_count(conn) == 2
    assert b"Skipped 2 already present" in response.data


def test_repeated_transactions_in_one_file_are_all_kept(client, conn):
    """Two identical charges on the same day are a real pattern, not a duplicate."""
    doubled = CSV + "05/09/2025,GOOGLE CLOUD EMEA,Direct Debit,,7.00\n"
    upload(client, doubled)
    assert statement_count(conn) == 3


def test_partial_overlap_adds_only_the_new_rows(client, conn):
    upload(client)
    extra = CSV + "01/07/2025,GOOGLE IRELAND,BACS Payment Received,0.25,\n"
    upload(client, extra)
    assert statement_count(conn) == 3


def test_upload_reports_bad_date_without_storing_anything(client, conn):
    response = upload(client, "Date,Details,Transaction Type,In,Out\n31/31/2025,Bad,DD,,7.00\n")
    assert b"Error parsing CSV" in response.data
    assert statement_count(conn) == 0


def test_oversized_upload_is_rejected_with_a_message(client, conn):
    import app as app_module

    oversized = "x" * (app_module.app.config["MAX_CONTENT_LENGTH"] + 1024)
    response = upload(client, oversized)

    assert b"too large" in response.data
    assert statement_count(conn) == 0


def test_match_with_missing_fields_does_not_error(client):
    response = client.post("/reconciliation/match", data={}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Invalid match request" in response.data


def test_match_rejects_unknown_type(client, conn):
    db.add_income(conn, "2025-09-05", "Donation", "", 10.0, "Donations", "Unrestricted")
    income_id = conn.execute("SELECT MAX(id) FROM income").fetchone()[0]
    db.add_bank_statement_row(conn, "2025-09-05", "In", "Inward Payment", 10.0, 0.0, "b")
    db.commit(conn)
    stmt_id = conn.execute("SELECT MAX(id) FROM bank_statements").fetchone()[0]

    response = client.post(
        "/reconciliation/match",
        data={"stmt_id": stmt_id, "matched_type": "banana", "matched_id": income_id},
        follow_redirects=True,
    )

    assert b"Invalid match request" in response.data
    row = conn.execute("SELECT matched_id FROM bank_statements WHERE id = ?", (stmt_id,)).fetchone()
    assert row["matched_id"] is None


def test_match_rejects_missing_cashbook_entry(client, conn):
    db.add_bank_statement_row(conn, "2025-09-05", "In", "Inward Payment", 10.0, 0.0, "b")
    db.commit(conn)
    stmt_id = conn.execute("SELECT MAX(id) FROM bank_statements").fetchone()[0]

    response = client.post(
        "/reconciliation/match",
        data={"stmt_id": stmt_id, "matched_type": "income", "matched_id": 999},
        follow_redirects=True,
    )
    assert b"cashbook entry no longer exists" in response.data


def test_unmatch_with_missing_field_does_not_error(client):
    response = client.post("/reconciliation/unmatch", data={}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Invalid transaction" in response.data


def test_toggle_refuses_to_unreconcile_a_matched_entry(client, conn):
    db.add_income(conn, "2025-09-05", "Donation", "", 10.0, "Donations", "Unrestricted")
    income_id = conn.execute("SELECT MAX(id) FROM income").fetchone()[0]
    db.add_bank_statement_row(conn, "2025-09-05", "In", "Inward Payment", 10.0, 0.0, "b")
    db.commit(conn)
    stmt_id = conn.execute("SELECT MAX(id) FROM bank_statements").fetchone()[0]
    db.match_bank_statement(conn, stmt_id, "income", income_id)

    response = client.post(
        "/reconciliation/toggle",
        data={"type": "income", "id": income_id},
        follow_redirects=True,
    )

    assert b"matched to a bank transaction" in response.data
    assert conn.execute("SELECT reconciled FROM income WHERE id = ?", (income_id,)).fetchone()[0] == 1


def test_toggle_works_for_an_unmatched_entry(client, conn):
    db.add_income(conn, "2025-09-05", "Donation", "", 10.0, "Donations", "Unrestricted")
    income_id = conn.execute("SELECT MAX(id) FROM income").fetchone()[0]

    client.post("/reconciliation/toggle", data={"type": "income", "id": income_id}, follow_redirects=True)

    assert conn.execute("SELECT reconciled FROM income WHERE id = ?", (income_id,)).fetchone()[0] == 1


def test_description_with_backslash_does_not_break_the_page(client, conn):
    """A trailing backslash used to run the inline script's string literal on,
    breaking every Match button on the page."""
    db.add_income(conn, "2025-09-05", "Refund\\", "", 10.0, "Donations", "Unrestricted")
    db.add_bank_statement_row(conn, "2025-09-05", "In", "Inward Payment", 10.0, 0.0, "b")
    db.commit(conn)

    response = client.get("/reconciliation")

    assert response.status_code == 200
    assert b'"Refund\\\\"' in response.data


def test_description_with_markup_is_not_embedded_as_html(client, conn):
    db.add_income(conn, "2025-09-05", "<script>alert(1)</script>", "", 10.0, "Donations", "Unrestricted")
    db.add_bank_statement_row(conn, "2025-09-05", "In", "Inward Payment", 10.0, 0.0, "b")
    db.commit(conn)

    response = client.get("/reconciliation")

    assert b"<script>alert(1)</script>" not in response.data
