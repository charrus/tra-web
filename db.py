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

def add_bank_statement_row(conn, date, details, transaction_type, amount_in, amount_out, upload_batch):
    conn.execute(
        "INSERT INTO bank_statements (date, details, transaction_type, amount_in, amount_out, upload_batch) VALUES (?, ?, ?, ?, ?, ?)",
        (date, details, transaction_type, amount_in, amount_out, upload_batch),
    )


def commit(conn):
    conn.commit()


def get_all_bank_statements(conn):
    return rows_to_list(conn.execute("SELECT * FROM bank_statements ORDER BY date DESC, id DESC").fetchall())


def get_unmatched_bank_statements(conn):
    return rows_to_list(conn.execute(
        "SELECT * FROM bank_statements WHERE matched_id IS NULL ORDER BY date, id"
    ).fetchall())


def match_bank_statement(conn, stmt_id, matched_type, matched_id):
    conn.execute(
        "UPDATE bank_statements SET matched_type = ?, matched_id = ? WHERE id = ?",
        (matched_type, matched_id, stmt_id),
    )
    if matched_type == "income":
        conn.execute("UPDATE income SET reconciled = 1 WHERE id = ?", (matched_id,))
    elif matched_type == "expenditure":
        conn.execute("UPDATE expenditure SET reconciled = 1 WHERE id = ?", (matched_id,))
    conn.commit()


def unmatch_bank_statement(conn, stmt_id):
    row = conn.execute("SELECT matched_type, matched_id FROM bank_statements WHERE id = ?", (stmt_id,)).fetchone()
    if row and row["matched_id"]:
        if row["matched_type"] == "income":
            conn.execute("UPDATE income SET reconciled = 0 WHERE id = ?", (row["matched_id"],))
        elif row["matched_type"] == "expenditure":
            conn.execute("UPDATE expenditure SET reconciled = 0 WHERE id = ?", (row["matched_id"],))
    conn.execute(
        "UPDATE bank_statements SET matched_type = NULL, matched_id = NULL WHERE id = ?",
        (stmt_id,),
    )
    conn.commit()


def clear_bank_statements(conn):
    conn.execute("UPDATE income SET reconciled = 0 WHERE reconciled = 1 AND id IN (SELECT matched_id FROM bank_statements WHERE matched_type = 'income')")
    conn.execute("UPDATE expenditure SET reconciled = 0 WHERE reconciled = 1 AND id IN (SELECT matched_id FROM bank_statements WHERE matched_type = 'expenditure')")
    conn.execute("DELETE FROM bank_statements")
    conn.commit()


def get_upload_batches(conn):
    rows = conn.execute(
        "SELECT upload_batch, COUNT(*) as count, MIN(date) as min_date, MAX(date) as max_date FROM bank_statements GROUP BY upload_batch ORDER BY upload_batch DESC"
    ).fetchall()
    return rows_to_list(rows)
