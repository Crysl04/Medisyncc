import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from psycopg2.pool import SimpleConnectionPool
import psycopg2
from contextlib import contextmanager

# ---------------------
# Basic app config
# ---------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-fallback-secret-change-me")

# ---------------------
# Admin credentials (temporary)
# ---------------------
# You may remove or replace this with a proper user table.
ADMIN_CREDENTIALS = {
    'admin': {
        'password': generate_password_hash('1234'),
        'name': 'Ma. Fe M. Cantutay'
    },
    'admin2': {
        'password': generate_password_hash('4321'),
        'name': 'Assistant Admin'
    }
}

# ---------------------
# Database connection pool
# ---------------------
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set. Set it in Render dashboard.")

# Render and some providers give a DATABASE_URL that starts with 'postgres://'
# psycopg2 expects 'postgresql://' in some installs, so normalize:
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Configure pool sizes as appropriate for your Render plan
MIN_CONN = int(os.environ.get("DB_POOL_MIN", 1))
MAX_CONN = int(os.environ.get("DB_POOL_MAX", 20))

try:
    pool = SimpleConnectionPool(MIN_CONN, MAX_CONN, dsn=DATABASE_URL)
except Exception as e:
    raise RuntimeError(f"Failed to initialize DB connection pool: {e}")

@contextmanager
def get_cursor():
    """
    Context manager yielding a cursor from pooled connection.
    Commits if no exception, rolls back on exception, and returns conn to pool.
    Usage:
        with get_cursor() as cur:
            cur.execute(...)
            rows = cur.fetchall()
    """
    conn = None
    cur = None
    try:
        conn = pool.getconn()
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            pool.putconn(conn)

# ---------------------
# Helper utilities
# ---------------------
def is_logged_in():
    return session.get("logged_in", False)

def login_user(username):
    session["logged_in"] = True
    session["username"] = username

def logout_user():
    session.clear()

# ---------------------
# Routes (example set; adapt to your existing templates & SQL)
# ---------------------
@app.route("/")
def index():
    # Example: fetch summary data for index page
    products = []
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT product_id, product_name, brand_name, batch_number, expiration_date, quantity
                FROM Product
                ORDER BY product_name
                LIMIT 200
            """)
            rows = cur.fetchall()
            for r in rows:
                products.append({
                    "product_id": r[0],
                    "product_name": r[1],
                    "brand_name": r[2],
                    "batch_number": r[3],
                    "expiration_date": r[4],
                    "quantity": r[5]
                })
    except Exception as e:
        app.logger.error("Index DB error: %s", e)
        flash("Could not load products.", "danger")

    return render_template("index.html", products=products)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # Example: check in ADMIN_CREDENTIALS first (temporary)
        admin = ADMIN_CREDENTIALS.get(username)
        if admin and check_password_hash(admin["password"], password):
            login_user(username)
            flash("Logged in successfully.", "success")
            return redirect(url_for("index"))

        # Alternatively, check a user table in DB (recommended)
        try:
            with get_cursor() as cur:
                cur.execute("SELECT username, password_hash FROM users WHERE username = %s", (username,))
                row = cur.fetchone()
                if row and check_password_hash(row[1], password):
                    login_user(username)
                    flash("Logged in successfully.", "success")
                    return redirect(url_for("index"))
        except Exception as e:
            app.logger.error("Login DB error: %s", e)
            flash("Login failed.", "danger")

        flash("Invalid credentials.", "danger")
        return redirect(url_for("login"))
    return render_template("admin.html")  # or login.html if you have one

@app.route("/logout")
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("index"))

# Example product page (list)
@app.route("/products")
def products():
    items = []
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT product_id, product_name, brand_name, unit, quantity, status
                FROM Product
                ORDER BY product_name
            """)
            for r in cur.fetchall():
                items.append({
                    "product_id": r[0],
                    "product_name": r[1],
                    "brand_name": r[2],
                    "unit": r[3],
                    "quantity": r[4],
                    "status": r[5]
                })
    except Exception as e:
        app.logger.error("Products error: %s", e)
        flash("Failed to load products.", "danger")

    return render_template("products.html", products=items)  # ensure products.html exists or adapt

# Transaction endpoint to add stock-in or stock-out (example)
@app.route("/transaction/add", methods=["POST"])
def add_transaction():
    if not is_logged_in():
        flash("Login required", "warning")
        return redirect(url_for("login"))

    product_id = request.form.get("product_id")
    change_qty = int(request.form.get("quantity", 0))
    ttype = request.form.get("type", "stock-in")  # 'stock-in' or 'stock-out'
    created_by = session.get("username", "system")

    try:
        with get_cursor() as cur:
            # Insert transaction
            cur.execute("""
                INSERT INTO Transaction (product_id, quantity, type, created_by, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                RETURNING id
            """, (product_id, change_qty, ttype, created_by))
            tx_id = cur.fetchone()[0]

            # Update product quantity (example)
            if ttype == "stock-in":
                cur.execute("UPDATE Product SET quantity = quantity + %s WHERE product_id = %s", (change_qty, product_id))
            else:
                cur.execute("UPDATE Product SET quantity = GREATEST(quantity - %s, 0) WHERE product_id = %s", (change_qty, product_id))

        flash("Transaction recorded.", "success")
    except Exception as e:
        app.logger.error("Add transaction error: %s", e)
        flash("Failed to record transaction.", "danger")

    return redirect(url_for("index"))

# Notifications example
@app.route("/notifications")
def notifications():
    notes = []
    try:
        with get_cursor() as cur:
            cur.execute("SELECT id, message, created_at, is_read FROM Notification ORDER BY created_at DESC LIMIT 50")
            for r in cur.fetchall():
                notes.append({"id": r[0], "message": r[1], "created_at": r[2], "is_read": r[3]})
    except Exception as e:
        app.logger.error("Notifications error: %s", e)
        flash("Could not load notifications.", "danger")

    return render_template("notification.html", notifications=notes)

# Simple health check
@app.route("/healthz")
def healthz():
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
            _ = cur.fetchone()
        return jsonify({"status": "ok"})
    except Exception as e:
        app.logger.error("Health check failed: %s", e)
        return jsonify({"status": "error", "detail": str(e)}), 500

# ---------------------
# Shutdown handler to close pool (optional)
# ---------------------
@app.teardown_appcontext
def close_db_pool(exc):
    # we intentionally do NOT close the pool here because Render restarts may call teardown multiple times.
    # If you need to close the pool on process stop, handle it in a separate management script.
    pass

# NOTE: Do NOT call init_db() here. On Render, we'll run migrations / schema separately.
# Do NOT include app.run() — Render will use gunicorn to run the app.
