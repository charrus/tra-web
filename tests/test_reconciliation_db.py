import db


def add_income(conn, amount=10.0, description="Donation"):
    db.add_income(conn, "2025-09-05", description, "REF", amount, "Donations", "Unrestricted")
    return conn.execute("SELECT MAX(id) FROM income").fetchone()[0]


def add_expenditure(conn, amount=7.0, description="Google Cloud"):
    db.add_expenditure(conn, "2025-09-05", description, "REF", amount, "Other", "Revenue")
    return conn.execute("SELECT MAX(id) FROM expenditure").fetchone()[0]


def add_statement(conn, amount_in=10.0, amount_out=0.0, details="Inward Payment"):
    db.add_bank_statement_row(conn, "2025-09-05", details, "Inward Payment", amount_in, amount_out, "batch")
    db.commit(conn)
    return conn.execute("SELECT MAX(id) FROM bank_statements").fetchone()[0]


def reconciled(conn, table, entry_id):
    return bool(conn.execute(f"SELECT reconciled FROM {table} WHERE id = ?", (entry_id,)).fetchone()[0])


def test_match_sets_reconciled(conn):
    income_id = add_income(conn)
    stmt_id = add_statement(conn)
    db.match_bank_statement(conn, stmt_id, "income", income_id)
    assert reconciled(conn, "income", income_id)


def test_rematching_releases_the_previous_entry(conn):
    first = add_income(conn, description="First")
    second = add_income(conn, description="Second")
    stmt_id = add_statement(conn)

    db.match_bank_statement(conn, stmt_id, "income", first)
    db.match_bank_statement(conn, stmt_id, "income", second)

    assert not reconciled(conn, "income", first)
    assert reconciled(conn, "income", second)


def test_match_rejects_unknown_entry_type(conn):
    stmt_id = add_statement(conn)
    assert db.match_bank_statement(conn, stmt_id, "banana", 1) is False
    row = conn.execute("SELECT matched_id FROM bank_statements WHERE id = ?", (stmt_id,)).fetchone()
    assert row["matched_id"] is None


def test_unmatch_reverses_the_match(conn):
    income_id = add_income(conn)
    stmt_id = add_statement(conn)
    db.match_bank_statement(conn, stmt_id, "income", income_id)
    db.unmatch_bank_statement(conn, stmt_id)

    assert not reconciled(conn, "income", income_id)
    row = conn.execute("SELECT matched_id FROM bank_statements WHERE id = ?", (stmt_id,)).fetchone()
    assert row["matched_id"] is None


def test_deleting_matched_income_clears_the_bank_match(conn):
    income_id = add_income(conn)
    stmt_id = add_statement(conn)
    db.match_bank_statement(conn, stmt_id, "income", income_id)

    db.delete_income(conn, income_id)

    row = conn.execute("SELECT matched_type, matched_id FROM bank_statements WHERE id = ?", (stmt_id,)).fetchone()
    assert row["matched_id"] is None
    assert row["matched_type"] is None


def test_deleting_matched_expenditure_clears_the_bank_match(conn):
    exp_id = add_expenditure(conn)
    stmt_id = add_statement(conn, amount_in=0.0, amount_out=7.0)
    db.match_bank_statement(conn, stmt_id, "expenditure", exp_id)

    db.delete_expenditure(conn, exp_id)

    row = conn.execute("SELECT matched_id FROM bank_statements WHERE id = ?", (stmt_id,)).fetchone()
    assert row["matched_id"] is None


def test_clear_leaves_nothing_reconciled(conn):
    income_id = add_income(conn)
    exp_id = add_expenditure(conn)
    db.match_bank_statement(conn, add_statement(conn), "income", income_id)
    db.match_bank_statement(conn, add_statement(conn, 0.0, 7.0), "expenditure", exp_id)

    db.clear_bank_statements(conn)

    assert not reconciled(conn, "income", income_id)
    assert not reconciled(conn, "expenditure", exp_id)
    assert conn.execute("SELECT COUNT(*) FROM bank_statements").fetchone()[0] == 0


def test_bank_match_for_finds_the_claiming_statement(conn):
    income_id = add_income(conn)
    stmt_id = add_statement(conn)
    assert db.bank_match_for(conn, "income", income_id) is None
    db.match_bank_statement(conn, stmt_id, "income", income_id)
    assert db.bank_match_for(conn, "income", income_id)["id"] == stmt_id
