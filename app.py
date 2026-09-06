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

def _parse_date_range(args):
    """Loosely parse start_date/end_date query args (YYYY-MM-DD).

    Returns (start_date, end_date), each either a valid YYYY-MM-DD
    string or None, validated independently. If both parse but
    start_date > end_date, both are reset to None (whole range treated
    as unfiltered)."""

    def _valid(value):
        if not value:
            return None
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            return None

    start_date = _valid(args.get("start_date"))
    end_date = _valid(args.get("end_date"))

    if start_date and end_date and start_date > end_date:
        return None, None

    return start_date, end_date


def build_transaction_history(user_id, start_date=None, end_date=None):
    """Return list of dicts for profile.html `transactions`:
    date, description, category, amount ('₹X.XX' str). Newest-first.
    Empty list if the user has no expenses."""
    rows = get_recent_expenses(user_id, limit=10, start_date=start_date, end_date=end_date)
    return [
        {
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": f"₹{row['amount']:.2f}",
        }
        for row in rows
    ]


def build_profile_summary(user_id, start_date=None, end_date=None):
    """Return (user, stats) for profile.html.
    user: name, email, initials, member_since ('Month YYYY').
    stats: total_spent ('₹X.XX' str), transaction_count (int),
    top_category (str or '—')."""
    user_row = get_user_by_id(user_id)
    stats_data = get_expense_stats(user_id, start_date=start_date, end_date=end_date)

    initials = "".join(part[0].upper() for part in user_row["name"].split()[:2])
    created_at = datetime.strptime(user_row["created_at"][:10], "%Y-%m-%d")
    member_since = created_at.strftime("%B %Y")

    user = {
        "name": user_row["name"],
        "email": user_row["email"],
        "initials": initials,
        "member_since": member_since,
    }

    stats = {
        "total_spent": f"₹{stats_data['total_spent']:.2f}",
        "transaction_count": stats_data["transaction_count"],
        "top_category": stats_data["top_category"] or "—",
    }

    return user, stats


def build_category_breakdown(user_id, start_date=None, end_date=None):
    """Return list of dicts for profile.html `categories`:
    name, total ('₹X.XX' str), percent (int, sums to 100),
    width_class (int, multiple of 10, min 10). Empty list if no expenses."""
    rows = get_category_totals(user_id, start_date=start_date, end_date=end_date)
    if not rows:
        return []

    grand_total = sum(row["total"] for row in rows)
    if grand_total <= 0:
        return []

    percents = [int((row["total"] / grand_total) * 100) for row in rows]
    remainder = 100 - sum(percents)
    percents[0] += remainder

    categories = []
    for row, percent in zip(rows, percents):
        width_class = max(10, (percent // 10) * 10)
        categories.append({
            "name": row["category"],
            "total": f"₹{row['total']:.2f}",
            "percent": percent,
            "width_class": width_class,
        })
    return categories


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    start_date, end_date = _parse_date_range(request.args)

    user, stats = build_profile_summary(user_id, start_date, end_date)
    transactions = build_transaction_history(user_id, start_date, end_date)
    categories = build_category_breakdown(user_id, start_date, end_date)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        start_date=start_date or "",
        end_date=end_date or "",
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
