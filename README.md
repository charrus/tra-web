# TRA Treasurer Assistant

A web application to help Tenant and Resident Association (TRA) treasurers manage their finances. Built with Python and Flask, based on the Hammersmith & Fulham Council TRA finance training materials.

## Features

- **Dashboard** — Overview of income, expenditure, net balance, and restricted/unrestricted fund breakdown
- **Income Cashbook** — Record income by category (Donations, Hall Hire, Grants, Fees for Activities) with restricted/unrestricted fund tracking
- **Expenditure Cashbook** — Record spending by category (Insurance, Printing, Activities, Cleaning, etc.) as Capital or Revenue
- **Petty Cash** — Track a small float for day-to-day items with receipt tracking for audit trail
- **Annual Budget** — Set budgeted amounts per category and compare against actuals with variance reporting
- **Bank Reconciliation** — Tick off transactions against your bank statement to reconcile accounts
- **Treasurer Report** — Printable report with opening/closing balance, income/expenditure by category, cash in hand, and signature lines
- **User Authentication** — Login system with password hashing, role-based access (admin/member), and user management
- **Settings** — Configure TRA name, financial year, opening bank balance, and petty cash float

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

## Getting Started

1. **Install dependencies:**

   ```
   uv sync
   ```

2. **Run the application:**

   ```
   uv run python app.py
   ```

3. **Open in your browser:**

   ```
   http://127.0.0.1:5000
   ```

4. **Log in with the default credentials:**

   - Username: `admin`
   - Password: `admin`

   Change the password after first login via the sidebar.

5. **Configure your TRA** by going to **Settings** and entering your TRA name, financial year start, and opening bank balance.

## Project Structure

```
tra-web/
├── app.py                  # Flask application
├── pyproject.toml          # Project config and dependencies
├── data/                   # JSON data files (created at runtime)
│   ├── income.json
│   ├── expenditure.json
│   ├── petty_cash.json
│   ├── budget.json
│   ├── settings.json
│   └── users.json
└── templates/
    ├── base.html           # Layout with sidebar navigation
    ├── login.html          # Login page
    ├── dashboard.html      # Financial overview
    ├── income.html         # Income cashbook
    ├── income_form.html    # Add income entry
    ├── expenditure.html    # Expenditure cashbook
    ├── expenditure_form.html
    ├── petty_cash.html     # Petty cash tracker
    ├── petty_cash_form.html
    ├── budget.html         # Budget vs actuals
    ├── budget_edit.html    # Edit budget
    ├── reconciliation.html # Bank reconciliation
    ├── report.html         # Printable treasurer report
    ├── settings.html       # App settings
    ├── users.html          # User management (admin)
    ├── user_form.html      # Add user (admin)
    └── change_password.html
```

## User Roles

| Role   | Permissions                                        |
|--------|----------------------------------------------------|
| Admin  | Full access including user management               |
| Member | View and edit transactions, budgets, and reports    |

## Data Storage

All data is stored as JSON files in the `data/` directory. No database setup is required. Back up this directory to preserve your financial records.

## Key Concepts

These align with the H&F Council TRA finance training:

- **Restricted Funds** — Money received for a specific purpose (e.g. council grants) that must be spent on that purpose
- **Unrestricted Funds** — Money that can be used freely (e.g. hall hire income, donations)
- **Capital vs Revenue** — Capital expenditure is one-off larger items; Revenue is ongoing running costs
- **Reconciliation** — Matching your cashbook records against your bank statement
- **Dual Authorisation** — The principle that two people should authorise payments (tracked via the audit trail)
