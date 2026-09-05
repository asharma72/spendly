import os
import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import (
    get_db,
    init_db,
    seed_db,
    get_user_by_email,
    get_user_by_id,
    get_expense_stats,
    get_recent_expenses,
    get_category_totals,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password or not confirm_password:
        return render_template(
            "register.html",
            error="Please fill in all fields.",
            name=name,
            email=email,
        )

    if len(password) < 8:
        return render_template(
            "register.html",
            error="Password must be at least 8 characters.",
            name=name,
            email=email,
        )

    if password != confirm_password:
        return render_template(
            "register.html",
            error="Passwords do not match.",
            name=name,
            email=email,
        )

    if get_user_by_email(email) is not None:
        return render_template(
            "register.html",
            error="An account with this email already exists.",
            name=name,
            email=email,
        )

    password_hash = generate_password_hash(password)

    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
        user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return render_template(
            "register.html",
            error="An account with this email already exists.",
            name=name,
            email=email,
        )
    conn.close()

    session["user_id"] = user_id
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html",
            error="Invalid email or password.",
            email=email,
        )

    session["user_id"] = user["id"]
    return redirect(url_for("profile"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Profile page helpers                                                #
# ------------------------------------------------------------------ #

def build_transaction_history(user_id):
    """Return list of dicts for profile.html `transactions`:
    date, description, category, amount ('₹X.XX' str). Newest-first.
    Empty list if the user has no expenses."""
    rows = get_recent_expenses(user_id, limit=10)
    return [
        {
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": f"₹{row['amount']:.2f}",
        }
        for row in rows
    ]


def build_profile_summary(user_id):
    """Return (user, stats) for profile.html.
    user: name, email, initials, member_since ('Month YYYY').
    stats: total_spent ('₹X.XX' str), transaction_count (int),
    top_category (str or '—')."""
    raise NotImplementedError


def build_category_breakdown(user_id):
    """Return list of dicts for profile.html `categories`:
    name, total ('₹X.XX' str), percent (int, sums to 100),
    width_class (int, multiple of 10, min 10). Empty list if no expenses."""
    raise NotImplementedError


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "August 2026",
    }

    stats = {
        "total_spent": "₹305.53",
        "transaction_count": 8,
        "top_category": "Bills",
    }

    transactions = [
        {"date": "2026-08-21", "description": "Dinner with friends", "category": "Food", "amount": "₹34.75"},
        {"date": "2026-08-18", "description": "Birthday gift for a friend", "category": "Other", "amount": "₹20.00"},
        {"date": "2026-08-15", "description": "New running shoes", "category": "Shopping", "amount": "₹62.30"},
        {"date": "2026-08-12", "description": "Movie ticket", "category": "Entertainment", "amount": "₹15.99"},
        {"date": "2026-08-09", "description": "Pharmacy — allergy medication", "category": "Health", "amount": "₹25.00"},
        {"date": "2026-08-06", "description": "Electricity bill", "category": "Bills", "amount": "₹89.99"},
        {"date": "2026-08-03", "description": "Monthly metro pass", "category": "Transport", "amount": "₹45.00"},
        {"date": "2026-08-01", "description": "Grocery run at Trader Joe's", "category": "Food", "amount": "₹12.50"},
    ]

    categories = [
        {"name": "Bills", "total": "₹89.99", "percent": 29, "width_class": 30},
        {"name": "Shopping", "total": "₹62.30", "percent": 20, "width_class": 20},
        {"name": "Food", "total": "₹47.25", "percent": 15, "width_class": 20},
        {"name": "Transport", "total": "₹45.00", "percent": 15, "width_class": 20},
        {"name": "Health", "total": "₹25.00", "percent": 8, "width_class": 10},
        {"name": "Other", "total": "₹20.00", "percent": 7, "width_class": 10},
        {"name": "Entertainment", "total": "₹15.99", "percent": 5, "width_class": 10},
    ]

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
    )


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
