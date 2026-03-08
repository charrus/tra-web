import os
from datetime import date
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash

import db

app = Flask(__name__, static_url_path="", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "tra-treasurer-secret-key-change-in-production")

# Initialise database on startup
db.init_db()


def get_conn():
    if "db" not in g:
        g.db = db.get_db()
    return g.db


@app.teardown_appcontext
def close_db(exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


# --- Authentication ---


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated


def create_initial_admin():
    conn = db.get_db()
    if db.user_count(conn) == 0:
        db.create_user(
            conn, "admin", generate_password_hash("admin"), "Administrator", "admin"
        )
    conn.close()


create_initial_admin()


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.get_user(get_conn(), username)
        if user and check_password_hash(user["password_hash"], password):
            session["user"] = user["username"]
            session["user_name"] = user.get("name", username)
            session["user_role"] = user.get("role", "member")
            flash(f"Welcome, {user.get('name', username)}!", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        user = db.get_user(get_conn(), session["user"])
        if not user or not check_password_hash(user["password_hash"], current):
            flash("Current password is incorrect.", "error")
        elif len(new_pw) < 4:
            flash("New password must be at least 4 characters.", "error")
        elif new_pw != confirm:
            flash("New passwords do not match.", "error")
        else:
            db.update_user_password(get_conn(), session["user"], generate_password_hash(new_pw))
            flash("Password changed successfully.", "success")
            return redirect(url_for("dashboard"))
    return render_template("change_password.html")


@app.route("/users")
@login_required
def user_list():
    if session.get("user_role") != "admin":
        flash("Only administrators can manage users.", "error")
        return redirect(url_for("dashboard"))
    users = db.get_all_users(get_conn())
    safe_users = [
        {"username": u["username"], "name": u.get("name", ""), "role": u.get("role", "member")}
        for u in users
    ]
    return render_template("users.html", users=safe_users)


@app.route("/users/add", methods=["GET", "POST"])
@login_required
def user_add():
    if session.get("user_role") != "admin":
        flash("Only administrators can add users.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "member")
        if not username or not password:
            flash("Username and password are required.", "error")
        elif db.get_user(get_conn(), username):
            flash("A user with that username already exists.", "error")
        elif len(password) < 4:
            flash("Password must be at least 4 characters.", "error")
        else:
            db.create_user(get_conn(), username, generate_password_hash(password), name or username, role)
            flash(f"User '{username}' created.", "success")
            return redirect(url_for("user_list"))
    return render_template("user_form.html")


@app.route("/users/delete/<username>", methods=["POST"])
@login_required
def user_delete(username):
    if session.get("user_role") != "admin":
        flash("Only administrators can delete users.", "error")
        return redirect(url_for("dashboard"))
    if username == session["user"]:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("user_list"))
    db.delete_user(get_conn(), username)
    flash(f"User '{username}' deleted.", "success")
    return redirect(url_for("user_list"))


# --- Helpers ---


def get_financial_year_dates(settings):
    start_month = settings.get("financial_year_start_month", 4)
    start_year = settings.get("financial_year_start_year", 2025)
    start = date(start_year, start_month, 1)
    if start_month == 1:
        end = date(start_year, 12, 31)
    else:
        end = date(start_year + 1, start_month - 1, 28)
        if start_month - 1 in (1, 3, 5, 7, 8, 10, 12):
            end = end.replace(day=31)
        elif start_month - 1 == 2:
            end = end.replace(day=28)
        else:
            end = end.replace(day=30)
    return start, end


def parse_amount(value):
    cleaned = value.strip().replace("\u00a3", "").replace(",", "")
    return round(float(cleaned), 2)


INCOME_CATEGORIES = [
    "Donations",
    "Hall Hire",
    "Grants",
    "Fees for Activities",
    "Other Income",
]

EXPENDITURE_CATEGORIES = [
    "Internet and Mobile",
    "Printing",
    "Activities",
    "Insurance",
    "Stationery",
    "Licences",
    "Training",
    "Volunteer Expenses",
    "Venue Hire",
    "Cleaning",
    "Building/Maintenance",
    "Capital Items",
    "Other",
]

FUND_TYPES = ["Unrestricted", "Restricted"]


# --- Dashboard ---


@app.route("/")
@login_required
def dashboard():
    conn = get_conn()
    settings = db.get_settings(conn)
    income = db.get_all_income(conn)
    expenditure = db.get_all_expenditure(conn)
    petty_cash = db.get_all_petty_cash(conn)

    total_income = sum(i["amount"] for i in income)
    total_expenditure = sum(e["amount"] for e in expenditure)
    total_petty_spent = sum(p["amount"] for p in petty_cash)
    net_balance = total_income - total_expenditure

    restricted_income = sum(i["amount"] for i in income if i.get("fund_type") == "Restricted")
    unrestricted_income = sum(i["amount"] for i in income if i.get("fund_type") == "Unrestricted")

    recent_income = income[:5]
    recent_expenditure = expenditure[:5]

    return render_template(
        "dashboard.html",
        settings=settings,
        total_income=total_income,
        total_expenditure=total_expenditure,
        net_balance=net_balance,
        restricted_income=restricted_income,
        unrestricted_income=unrestricted_income,
        petty_cash_spent=total_petty_spent,
        recent_income=recent_income,
        recent_expenditure=recent_expenditure,
    )


# --- Income ---


@app.route("/income")
@login_required
def income_list():
    income = db.get_all_income(get_conn())
    total = sum(i["amount"] for i in income)
    cat_totals = {}
    for i in income:
        cat = i.get("category", "Other")
        cat_totals[cat] = cat_totals.get(cat, 0) + i["amount"]
    return render_template(
        "income.html",
        income=income,
        total=total,
        categories=INCOME_CATEGORIES,
        category_totals=cat_totals,
    )


@app.route("/income/add", methods=["GET", "POST"])
@login_required
def income_add():
    if request.method == "POST":
        db.add_income(
            get_conn(),
            request.form["date"],
            request.form["description"],
            request.form.get("reference", ""),
            parse_amount(request.form["amount"]),
            request.form["category"],
            request.form.get("fund_type", "Unrestricted"),
        )
        flash("Income entry added successfully.", "success")
        return redirect(url_for("income_list"))
    return render_template(
        "income_form.html",
        categories=INCOME_CATEGORIES,
        fund_types=FUND_TYPES,
        entry=None,
    )


@app.route("/income/delete/<int:entry_id>", methods=["POST"])
@login_required
def income_delete(entry_id):
    db.delete_income(get_conn(), entry_id)
    flash("Income entry deleted.", "success")
    return redirect(url_for("income_list"))


# --- Expenditure ---


@app.route("/expenditure")
@login_required
def expenditure_list():
    expenditure = db.get_all_expenditure(get_conn())
    total = sum(e["amount"] for e in expenditure)
    cat_totals = {}
    for e in expenditure:
        cat = e.get("category", "Other")
        cat_totals[cat] = cat_totals.get(cat, 0) + e["amount"]
    return render_template(
        "expenditure.html",
        expenditure=expenditure,
        total=total,
        categories=EXPENDITURE_CATEGORIES,
        category_totals=cat_totals,
    )


@app.route("/expenditure/add", methods=["GET", "POST"])
@login_required
def expenditure_add():
    if request.method == "POST":
        db.add_expenditure(
            get_conn(),
            request.form["date"],
            request.form["description"],
            request.form.get("reference", ""),
            parse_amount(request.form["amount"]),
            request.form["category"],
            request.form.get("expenditure_type", "Revenue"),
        )
        flash("Expenditure entry added successfully.", "success")
        return redirect(url_for("expenditure_list"))
    return render_template(
        "expenditure_form.html",
        categories=EXPENDITURE_CATEGORIES,
        entry=None,
    )


@app.route("/expenditure/delete/<int:entry_id>", methods=["POST"])
@login_required
def expenditure_delete(entry_id):
    db.delete_expenditure(get_conn(), entry_id)
    flash("Expenditure entry deleted.", "success")
    return redirect(url_for("expenditure_list"))


# --- Petty Cash ---


@app.route("/petty-cash")
@login_required
def petty_cash_list():
    conn = get_conn()
    petty_cash = db.get_all_petty_cash(conn)
    settings = db.get_settings(conn)
    float_amount = float(settings.get("petty_cash_float", 50))
    total_spent = sum(p["amount"] for p in petty_cash)
    remaining = float_amount - total_spent
    return render_template(
        "petty_cash.html",
        entries=petty_cash,
        float_amount=float_amount,
        total_spent=total_spent,
        remaining=remaining,
    )


@app.route("/petty-cash/add", methods=["GET", "POST"])
@login_required
def petty_cash_add():
    if request.method == "POST":
        db.add_petty_cash(
            get_conn(),
            request.form["date"],
            request.form["description"],
            parse_amount(request.form["amount"]),
            request.form.get("receipt", "No"),
        )
        flash("Petty cash entry added.", "success")
        return redirect(url_for("petty_cash_list"))
    return render_template("petty_cash_form.html")


@app.route("/petty-cash/reset", methods=["POST"])
@login_required
def petty_cash_reset():
    db.clear_petty_cash(get_conn())
    flash("Petty cash float has been reset.", "success")
    return redirect(url_for("petty_cash_list"))


# --- Budget ---


@app.route("/budget")
@login_required
def budget_view():
    conn = get_conn()
    budget = db.get_budget(conn)
    income = db.get_all_income(conn)
    expenditure = db.get_all_expenditure(conn)

    if not budget["income"] and not budget["expenditure"]:
        budget = {
            "income": {cat: 0 for cat in INCOME_CATEGORIES},
            "expenditure": {cat: 0 for cat in EXPENDITURE_CATEGORIES},
        }

    actual_income = {}
    for i in income:
        cat = i.get("category", "Other Income")
        actual_income[cat] = actual_income.get(cat, 0) + i["amount"]

    actual_expenditure = {}
    for e in expenditure:
        cat = e.get("category", "Other")
        actual_expenditure[cat] = actual_expenditure.get(cat, 0) + e["amount"]

    budget_income_total = sum(budget.get("income", {}).values())
    budget_expenditure_total = sum(budget.get("expenditure", {}).values())
    actual_income_total = sum(actual_income.values())
    actual_expenditure_total = sum(actual_expenditure.values())

    return render_template(
        "budget.html",
        budget=budget,
        actual_income=actual_income,
        actual_expenditure=actual_expenditure,
        income_categories=INCOME_CATEGORIES,
        expenditure_categories=EXPENDITURE_CATEGORIES,
        budget_income_total=budget_income_total,
        budget_expenditure_total=budget_expenditure_total,
        actual_income_total=actual_income_total,
        actual_expenditure_total=actual_expenditure_total,
    )


@app.route("/budget/edit", methods=["GET", "POST"])
@login_required
def budget_edit():
    conn = get_conn()
    if request.method == "POST":
        budget = {"income": {}, "expenditure": {}}
        for cat in INCOME_CATEGORIES:
            val = request.form.get(f"income_{cat}", "0")
            budget["income"][cat] = parse_amount(val) if val else 0
        for cat in EXPENDITURE_CATEGORIES:
            val = request.form.get(f"expenditure_{cat}", "0")
            budget["expenditure"][cat] = parse_amount(val) if val else 0
        db.save_budget(conn, budget)
        flash("Budget saved successfully.", "success")
        return redirect(url_for("budget_view"))

    budget = db.get_budget(conn)
    if not budget["income"] and not budget["expenditure"]:
        budget = {
            "income": {cat: 0 for cat in INCOME_CATEGORIES},
            "expenditure": {cat: 0 for cat in EXPENDITURE_CATEGORIES},
        }
    return render_template(
        "budget_edit.html",
        budget=budget,
        income_categories=INCOME_CATEGORIES,
        expenditure_categories=EXPENDITURE_CATEGORIES,
    )


# --- Reconciliation ---


@app.route("/reconciliation", methods=["GET", "POST"])
@login_required
def reconciliation():
    conn = get_conn()
    if request.method == "POST":
        entry_type = request.form.get("type")
        entry_id = int(request.form.get("id"))
        if entry_type == "income":
            db.toggle_income_reconciled(conn, entry_id)
        elif entry_type == "expenditure":
            db.toggle_expenditure_reconciled(conn, entry_id)
        return redirect(url_for("reconciliation"))

    income = db.get_all_income(conn)
    expenditure = db.get_all_expenditure(conn)
    settings = db.get_settings(conn)

    opening_balance = float(settings.get("opening_balance", 0))
    total_income = sum(i["amount"] for i in income)
    total_expenditure = sum(e["amount"] for e in expenditure)
    closing_balance = opening_balance + total_income - total_expenditure

    unreconciled_income = [i for i in income if not i.get("reconciled")]
    unreconciled_expenditure = [e for e in expenditure if not e.get("reconciled")]

    return render_template(
        "reconciliation.html",
        income=sorted(income, key=lambda x: x["date"]),
        expenditure=sorted(expenditure, key=lambda x: x["date"]),
        opening_balance=opening_balance,
        total_income=total_income,
        total_expenditure=total_expenditure,
        closing_balance=closing_balance,
        unreconciled_income_count=len(unreconciled_income),
        unreconciled_expenditure_count=len(unreconciled_expenditure),
    )


# --- Treasurer Report ---


@app.route("/report")
@login_required
def treasurer_report():
    conn = get_conn()
    settings = db.get_settings(conn)
    income = db.get_all_income(conn)
    expenditure = db.get_all_expenditure(conn)
    petty_cash = db.get_all_petty_cash(conn)

    opening_balance = float(settings.get("opening_balance", 0))
    total_income = sum(i["amount"] for i in income)
    total_expenditure = sum(e["amount"] for e in expenditure)
    closing_balance = opening_balance + total_income - total_expenditure
    petty_cash_in_hand = float(settings.get("petty_cash_float", 50)) - sum(
        p["amount"] for p in petty_cash
    )

    income_by_cat = {}
    for i in income:
        cat = i.get("category", "Other")
        income_by_cat[cat] = income_by_cat.get(cat, 0) + i["amount"]

    exp_by_cat = {}
    for e in expenditure:
        cat = e.get("category", "Other")
        exp_by_cat[cat] = exp_by_cat.get(cat, 0) + e["amount"]

    fy_start, fy_end = get_financial_year_dates(settings)

    return render_template(
        "report.html",
        settings=settings,
        opening_balance=opening_balance,
        income_by_category=income_by_cat,
        expenditure_by_category=exp_by_cat,
        total_income=total_income,
        total_expenditure=total_expenditure,
        closing_balance=closing_balance,
        petty_cash_in_hand=petty_cash_in_hand,
        balance_carried_forward=closing_balance + max(petty_cash_in_hand, 0),
        fy_start=fy_start,
        fy_end=fy_end,
        today=date.today(),
    )


# --- Settings ---


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    conn = get_conn()
    if request.method == "POST":
        settings = {
            "tra_name": request.form.get("tra_name", "My TRA"),
            "financial_year_start_month": request.form.get("financial_year_start_month", "4"),
            "financial_year_start_year": request.form.get("financial_year_start_year", "2025"),
            "opening_balance": str(parse_amount(request.form.get("opening_balance", "0"))),
            "petty_cash_float": str(parse_amount(request.form.get("petty_cash_float", "50"))),
        }
        db.save_settings(conn, settings)
        flash("Settings saved.", "success")
        return redirect(url_for("settings_page"))
    settings = db.get_settings(conn)
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    return render_template("settings.html", settings=settings, months=months)


# --- Template filters ---


@app.template_filter("currency")
def currency_filter(value):
    try:
        return f"\u00a3{float(value):,.2f}"
    except (ValueError, TypeError):
        return "\u00a30.00"


asgi_app = __import__("asgiref.wsgi", fromlist=["WsgiToAsgi"]).WsgiToAsgi(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:asgi_app",
        host="0.0.0.0",
        port=5000,
        reload=True,
    )
