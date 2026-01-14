import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import calendar

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

# ---------- DATABASE CONNECTION ----------
def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME"),
        port=int(os.environ.get("DB_PORT", 3306))
    )

# ---------- HOME ----------
@app.route("/")
def home():
    return redirect(url_for("dashboard")) if "user_id" in session else redirect(url_for("login"))

# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if not username or not password:
            flash("All fields required", "error")
            return redirect(url_for("register"))

        if password != confirm:
            flash("Passwords do not match", "error")
            return redirect(url_for("register"))

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
            if cursor.fetchone():
                flash("Username already exists", "error")
                conn.close()
                return redirect(url_for("register"))

            hashed = generate_password_hash(password)
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (%s, %s)",
                (username, hashed)
            )
            conn.commit()
            conn.close()

            flash("Account created!", "success")
            return redirect(url_for("login"))

        except mysql.connector.Error as e:
            flash(f"Database error: {e}", "error")
            return redirect(url_for("register"))

    return render_template("register.html")

# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
            user = cursor.fetchone()
            conn.close()

            if user and check_password_hash(user["password"], password):
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                return redirect(url_for("dashboard"))

            flash("Invalid credentials", "error")
        except mysql.connector.Error as e:
            flash(f"Database error: {e}", "error")

    return render_template("login.html")

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "success")
    return redirect(url_for("login"))

# ---------- DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    year = request.args.get("year", default=datetime.now().year, type=int)
    month = request.args.get("month", default=datetime.now().month, type=int)

    cal = calendar.Calendar()
    month_days_flat = [d for w in cal.monthdayscalendar(year, month) for d in w]

    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM events")
        events = cursor.fetchall()

        events_by_day = {}
        for e in events:
            if e["event_date"].year == year and e["event_date"].month == month:
                day = e["event_date"].day
                events_by_day.setdefault(day, []).append(e)

        cursor.execute("""
            SELECT e.name, e.event_date FROM registrations r
            JOIN events e ON r.event_id = e.id
            WHERE r.user_id = %s
            ORDER BY e.event_date
        """, (session["user_id"],))
        registrations = cursor.fetchall()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Database error: {e}", "error")
        events_by_day = {}
        registrations = []

    return render_template(
        "dashboard.html",
        username=session["username"],
        month=month,
        year=year,
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year,
        month_name=calendar.month_name[month],
        month_days_flat=month_days_flat,
        events_by_day=events_by_day,
        registrations=registrations
    )

# ---------- ADD EVENT ----------
@app.route("/add_event", methods=["GET", "POST"])
def add_event():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"]
        date = request.form["event_date"]

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO events (name, event_date, created_by) VALUES (%s, %s, %s)",
                (name, date, session["user_id"])
            )
            conn.commit()
            conn.close()
            flash("Event added", "success")
        except mysql.connector.Error as e:
            flash(f"Database error: {e}", "error")

        return redirect(url_for("dashboard"))

    return render_template("add_event.html")

# ---------- REGISTER EVENT ----------
@app.route("/register_event/<int:event_id>")
def register_event(event_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM registrations WHERE user_id=%s AND event_id=%s",
            (session["user_id"], event_id)
        )

        if cursor.fetchone():
            flash("Already registered", "error")
        else:
            cursor.execute(
                "INSERT INTO registrations (user_id, event_id) VALUES (%s, %s)",
                (session["user_id"], event_id)
            )
            conn.commit()
            flash("Registered successfully", "success")
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Database error: {e}", "error")

    return redirect(url_for("dashboard"))

# ---------- EVENTS BY DAY ----------
@app.route("/events/<int:year>/<int:month>/<int:day>")
def events_by_day(year, month, day):
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM events WHERE event_date=%s",
            (f"{year}-{month:02d}-{day:02d}",)
        )
        events = cursor.fetchall()
        conn.close()
    except mysql.connector.Error as e:
        flash(f"Database error: {e}", "error")
        events = []

    return render_template("events_by_day.html", events=events, year=year, month=month, day=day)

# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
