import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "tra.db"


def get_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'member'
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            reference TEXT DEFAULT '',
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            fund_type TEXT NOT NULL DEFAULT 'Unrestricted',
            reconciled INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS expenditure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            reference TEXT DEFAULT '',
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            expenditure_type TEXT NOT NULL DEFAULT 'Revenue',
            reconciled INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS petty_cash (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            receipt TEXT NOT NULL DEFAULT 'No'
        );

        CREATE TABLE IF NOT EXISTS budget (
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (type, category)
        );

        CREATE TABLE IF NOT EXISTS bank_statements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            transaction_type TEXT NOT NULL DEFAULT '',
            amount_in REAL NOT NULL DEFAULT 0,
            amount_out REAL NOT NULL DEFAULT 0,
            matched_type TEXT DEFAULT NULL,
            matched_id INTEGER DEFAULT NULL,
            upload_batch TEXT NOT NULL DEFAULT ''
        );
    """)
    conn.commit()
    conn.close()


# --- Helpers to convert sqlite3.Row to plain dict ---

def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    if "reconciled" in d:
        d["reconciled"] = bool(d["reconciled"])
    return d


def rows_to_list(rows):
    return [row_to_dict(r) for r in rows]


# --- Users ---

def get_all_users(conn):
    return rows_to_list(conn.execute("SELECT * FROM users").fetchall())


def get_user(conn, username):
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return row_to_dict(row)


def create_user(conn, username, password_hash, name, role):
    conn.execute(
        "INSERT INTO users (username, password_hash, name, role) VALUES (?, ?, ?, ?)",
        (username, password_hash, name, role),
    )
    conn.commit()


def update_user_password(conn, username, password_hash):
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (password_hash, username),
    )
    conn.commit()


def delete_user(conn, username):
    conn.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()


def user_count(conn):
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# --- Settings ---

DEFAULT_SETTINGS = {
    "tra_name": "My TRA",
    "financial_year_start_month": "4",
    "financial_year_start_year": "2025",
    "opening_balance": "0",
    "petty_cash_float": "50",
}


def get_settings(conn):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = dict(DEFAULT_SETTINGS)
    for row in rows:
        settings[row["key"]] = row["value"]
    # Convert numeric fields
    result = {}
    for k, v in settings.items():
        if k in ("financial_year_start_month", "financial_year_start_year"):
            result[k] = int(v)
        elif k in ("opening_balance", "petty_cash_float"):
            result[k] = float(v)
        else:
            result[k] = v
    return result


def save_settings(conn, settings):
    for key, value in settings.items():
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
    conn.commit()


# --- Income ---

def get_all_income(conn):
    return rows_to_list(conn.execute("SELECT * FROM income ORDER BY date DESC").fetchall())


def add_income(conn, date, description, reference, amount, category, fund_type):
    conn.execute(
        "INSERT INTO income (date, description, reference, amount, category, fund_type) VALUES (?, ?, ?, ?, ?, ?)",
        (date, description, reference, amount, category, fund_type),
    )
    conn.commit()


def delete_income(conn, entry_id):
    _release_bank_matches(conn, "income", entry_id)
    conn.execute("DELETE FROM income WHERE id = ?", (entry_id,))
    conn.commit()


def toggle_income_reconciled(conn, entry_id):
    conn.execute("UPDATE income SET reconciled = NOT reconciled WHERE id = ?", (entry_id,))
    conn.commit()


# --- Expenditure ---

def get_all_expenditure(conn):
    return rows_to_list(conn.execute("SELECT * FROM expenditure ORDER BY date DESC").fetchall())


def add_expenditure(conn, date, description, reference, amount, category, expenditure_type):
    conn.execute(
        "INSERT INTO expenditure (date, description, reference, amount, category, expenditure_type) VALUES (?, ?, ?, ?, ?, ?)",
        (date, description, reference, amount, category, expenditure_type),
    )
    conn.commit()


def delete_expenditure(conn, entry_id):
    _release_bank_matches(conn, "expenditure", entry_id)
    conn.execute("DELETE FROM expenditure WHERE id = ?", (entry_id,))
    conn.commit()


def toggle_expenditure_reconciled(conn, entry_id):
    conn.execute("UPDATE expenditure SET reconciled = NOT reconciled WHERE id = ?", (entry_id,))
    conn.commit()


# --- Petty Cash ---

def get_all_petty_cash(conn):
    return rows_to_list(conn.execute("SELECT * FROM petty_cash ORDER BY date DESC").fetchall())


def add_petty_cash(conn, date, description, amount, receipt):
    conn.execute(
        "INSERT INTO petty_cash (date, description, amount, receipt) VALUES (?, ?, ?, ?)",
        (date, description, amount, receipt),
    )
    conn.commit()


def clear_petty_cash(conn):
    conn.execute("DELETE FROM petty_cash")
    conn.commit()


# --- Budget ---

def get_budget(conn):
    rows = conn.execute("SELECT type, category, amount FROM budget").fetchall()
    budget = {"income": {}, "expenditure": {}}
    for row in rows:
        budget[row["type"]][row["category"]] = row["amount"]
    return budget


def save_budget(conn, budget):
    conn.execute("DELETE FROM budget")
    for btype in ("income", "expenditure"):
        for category, amount in budget.get(btype, {}).items():
            conn.execute(
                "INSERT INTO budget (type, category, amount) VALUES (?, ?, ?)",
                (btype, category, amount),
            )
    conn.commit()


# --- Bank Statements ---

# Entry types a bank statement may be matched against, mapped to their table.
# Used to keep table names out of string-formatted SQL.
ENTRY_TABLES = {"income": "income", "expenditure": "expenditure"}


def entry_exists(conn, entry_type, entry_id):
    table = ENTRY_TABLES.get(entry_type)
    if table is None:
        return False
    row = conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (entry_id,)).fetchone()
    return row is not None


def bank_statement_exists(conn, stmt_id):
    row = conn.execute("SELECT 1 FROM bank_statements WHERE id = ?", (stmt_id,)).fetchone()
    return row is not None


def bank_match_for(conn, entry_type, entry_id):
    """Return the bank statement currently matched to a cashbook entry, or None."""
    row = conn.execute(
        "SELECT * FROM bank_statements WHERE matched_type = ? AND matched_id = ?",
        (entry_type, entry_id),
    ).fetchone()
    return row_to_dict(row)


def bank_statement_row_count(conn, date, details, transaction_type, amount_in, amount_out):
    """How many identical rows are already stored. A statement may legitimately contain
    the same transaction twice in a day, so duplicate detection compares counts."""
    return conn.execute(
        "SELECT COUNT(*) FROM bank_statements WHERE date = ? AND details = ? AND transaction_type = ?"
        " AND amount_in = ? AND amount_out = ?",
        (date, details, transaction_type, amount_in, amount_out),
    ).fetchone()[0]


def _release_bank_matches(conn, entry_type, entry_id):
    """Clear any bank statement match pointing at a cashbook entry. Does not commit."""
    conn.execute(
        "UPDATE bank_statements SET matched_type = NULL, matched_id = NULL"
        " WHERE matched_type = ? AND matched_id = ?",
        (entry_type, entry_id),
    )


def _clear_match(conn, stmt_id):
    """Unreconcile whatever a statement points at and clear the match. Does not commit."""
    row = conn.execute(
        "SELECT matched_type, matched_id FROM bank_statements WHERE id = ?", (stmt_id,)
    ).fetchone()
    if row and row["matched_id"]:
        table = ENTRY_TABLES.get(row["matched_type"])
        if table is not None:
            conn.execute(f"UPDATE {table} SET reconciled = 0 WHERE id = ?", (row["matched_id"],))
    conn.execute(
        "UPDATE bank_statements SET matched_type = NULL, matched_id = NULL WHERE id = ?",
        (stmt_id,),
    )


def add_bank_statement_row(conn, date, details, transaction_type, amount_in, amount_out, upload_batch):
    conn.execute(
        "INSERT INTO bank_statements (date, details, transaction_type, amount_in, amount_out, upload_batch) VALUES (?, ?, ?, ?, ?, ?)",
        (date, details, transaction_type, amount_in, amount_out, upload_batch),
    )


def commit(conn):
    conn.commit()


def get_all_bank_statements(conn):
    return rows_to_list(conn.execute("SELECT * FROM bank_statements ORDER BY date DESC, id DESC").fetchall())


def match_bank_statement(conn, stmt_id, matched_type, matched_id):
    table = ENTRY_TABLES.get(matched_type)
    if table is None:
        return False
    # Release any entry this statement was previously matched to.
    _clear_match(conn, stmt_id)
    # A cashbook entry may have at most one bank statement match.
    previous = conn.execute(
        "SELECT id FROM bank_statements WHERE matched_type = ? AND matched_id = ? AND id != ?",
        (matched_type, matched_id, stmt_id),
    ).fetchall()
    for row in previous:
        _clear_match(conn, row["id"])
    conn.execute(
        "UPDATE bank_statements SET matched_type = ?, matched_id = ? WHERE id = ?",
        (matched_type, matched_id, stmt_id),
    )
    conn.execute(f"UPDATE {table} SET reconciled = 1 WHERE id = ?", (matched_id,))
    conn.commit()
    return True


def unmatch_bank_statement(conn, stmt_id):
    _clear_match(conn, stmt_id)
    conn.commit()


def clear_bank_statements(conn):
    conn.execute("UPDATE income SET reconciled = 0 WHERE reconciled = 1 AND id IN (SELECT matched_id FROM bank_statements WHERE matched_type = 'income')")
    conn.execute("UPDATE expenditure SET reconciled = 0 WHERE reconciled = 1 AND id IN (SELECT matched_id FROM bank_statements WHERE matched_type = 'expenditure')")
    conn.execute("DELETE FROM bank_statements")
    conn.commit()
