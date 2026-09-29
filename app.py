import os
import sqlite3
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

DB_PATH = os.environ.get("DATABASE_PATH", "database.db")

SHOP_NAME = os.environ.get("SHOP_NAME", "Khatushyam Ji Chasme Wale")
SHOP_TAGLINE = os.environ.get("SHOP_TAGLINE", "COMPUTERISED EYE TESTING")
SHOP_ADDRESS = os.environ.get(
    "SHOP_ADDRESS",
    "RZ F-6 G/F Vijay Enclave, Near By Bittoo Bakery, Shiv Main Market, Palam Dabri Road MIR, New Delhi-110045"
)
SHOP_PHONE = os.environ.get("SHOP_PHONE", "8076274076")
SHOP_GSTIN = os.environ.get("SHOP_GSTIN", "")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_DEFAULT = os.environ.get("ADMIN_PASSWORD", "admin123")

LOW_STOCK_THRESHOLD = int(os.environ.get("LOW_STOCK_THRESHOLD", "5"))
STARTING_SNO = int(os.environ.get("STARTING_SNO", "1430"))

CATEGORIES = ["Frame", "Sunglasses", "Lens", "Contact Lens", "Accessory"]

TERMS_AND_CONDITIONS = os.environ.get(
    "TERMS_AND_CONDITIONS",
    "All sales final \u2605 Next Day Home Delivery \u2605 No Refund/Exchange \u2605 No Guarantee of color "
    "&amp; Breakage \u2605 Please collect your goods in 45 days otherwise we are not responsible. "
    "Repairing Work at your own risk."
)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def add_column_if_missing(conn, table, column, coltype):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            brand TEXT,
            power_type TEXT,
            mrp REAL NOT NULL DEFAULT 0,
            selling_price REAL NOT NULL DEFAULT 0,
            stock_qty INTEGER NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT 'pcs',
            barcode TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            mobile TEXT UNIQUE,
            address TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            presc_date TEXT NOT NULL,
            right_sph TEXT, right_cyl TEXT, right_axis TEXT, right_add TEXT,
            left_sph TEXT, left_cyl TEXT, left_axis TEXT, left_add TEXT,
            pd TEXT,
            notes TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_number TEXT NOT NULL UNIQUE,
            sno INTEGER,
            customer_id INTEGER,
            bill_date TEXT NOT NULL,
            delivery_date TEXT,
            bill_type TEXT NOT NULL DEFAULT 'Cash',
            prescription_id INTEGER,
            dist_r_sph TEXT, dist_r_cyl TEXT, dist_r_axis TEXT,
            dist_l_sph TEXT, dist_l_cyl TEXT, dist_l_axis TEXT,
            read_r_sph TEXT, read_r_cyl TEXT, read_r_axis TEXT,
            read_l_sph TEXT, read_l_cyl TEXT, read_l_axis TEXT,
            frame TEXT,
            glass TEXT,
            total REAL NOT NULL DEFAULT 0,
            advance REAL NOT NULL DEFAULT 0,
            amount_received REAL NOT NULL DEFAULT 0,
            change_returned REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bill_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            qty REAL NOT NULL,
            mrp REAL NOT NULL DEFAULT 0,
            rate REAL NOT NULL DEFAULT 0,
            discount_percent REAL NOT NULL DEFAULT 0,
            amount REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (bill_id) REFERENCES bills(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_date TEXT NOT NULL,
            notes TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    add_column_if_missing(conn, "bills", "status", "TEXT NOT NULL DEFAULT 'active'")
    for col in ["sno INTEGER", "delivery_date TEXT", "dist_r_sph TEXT", "dist_r_cyl TEXT",
                "dist_r_axis TEXT", "dist_l_sph TEXT", "dist_l_cyl TEXT", "dist_l_axis TEXT",
                "read_r_sph TEXT", "read_r_cyl TEXT", "read_r_axis TEXT", "read_l_sph TEXT",
                "read_l_cyl TEXT", "read_l_axis TEXT", "frame TEXT", "glass TEXT",
                "advance REAL NOT NULL DEFAULT 0", "frame_product_id INTEGER", "glass_product_id INTEGER"]:
        name, coltype = col.split(" ", 1)
        add_column_if_missing(conn, "bills", name, coltype)
    conn.commit()
    conn.close()


def get_next_sno(db):
    row = db.execute("SELECT value FROM settings WHERE key = 'next_sno'").fetchone()
    if row and row["value"]:
        next_sno = int(row["value"])
    else:
        next_sno = STARTING_SNO
    db.execute("INSERT INTO settings (key, value) VALUES ('next_sno', ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(next_sno + 1),))
    db.commit()
    return next_sno


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def get_setting(key, default=None):
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    db = get_db()
    db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    db.commit()


def get_admin_password_hash():
    stored = get_setting("admin_password_hash")
    if stored:
        return stored
    return generate_password_hash(ADMIN_PASSWORD_DEFAULT)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and check_password_hash(get_admin_password_hash(), password):
            session["logged_in"] = True
            session["username"] = username
            flash("Login successful!", "success")
            return redirect(url_for("home"))
        flash("Galat username ya password.", "error")
    return render_template("login.html", shop_name=SHOP_NAME)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logout ho gaya.", "success")
    return redirect(url_for("login"))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if not check_password_hash(get_admin_password_hash(), current):
            flash("Current password galat hai.", "error")
        elif len(new) < 4:
            flash("New password kam se kam 4 characters ka hona chahiye.", "error")
        elif new != confirm:
            flash("New password aur confirm password match nahi karte.", "error")
        else:
            set_setting("admin_password_hash", generate_password_hash(new))
            flash("Password successfully change ho gaya!", "success")
            return redirect(url_for("home"))
    return render_template("change_password.html", shop_name=SHOP_NAME)


# ---------------------------------------------------------------------------
# Utility: amount in words (Indian numbering)
# ---------------------------------------------------------------------------

def number_to_words_inr(amount):
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
            "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
            "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def two_digit(n):
        if n < 20:
            return ones[n]
        return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")

    def three_digit(n):
        if n >= 100:
            return ones[n // 100] + " Hundred" + (" " + two_digit(n % 100) if n % 100 else "")
        return two_digit(n)

    amount = round(float(amount), 2)
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))

    if rupees == 0:
        words = "Zero"
    else:
        parts = []
        crore = rupees // 10000000
        rupees %= 10000000
        lakh = rupees // 100000
        rupees %= 100000
        thousand = rupees // 1000
        rupees %= 1000
        hundred = rupees

        if crore:
            parts.append(three_digit(crore) + " Crore")
        if lakh:
            parts.append(three_digit(lakh) + " Lakh")
        if thousand:
            parts.append(three_digit(thousand) + " Thousand")
        if hundred:
            parts.append(three_digit(hundred))
        words = " ".join(parts)

    result = f"{words} Rupees"
    if paise:
        result += f" and {two_digit(paise)} Paise"
    return result + " Only"


@app.template_filter("inr_words")
def inr_words_filter(amount):
    return number_to_words_inr(amount)


@app.template_filter("inr")
def inr_filter(amount):
    try:
        return f"{float(amount):,.2f}"
    except (TypeError, ValueError):
        return amount


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def home():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    today_sales = db.execute(
        "SELECT COALESCE(SUM(total),0) s FROM bills WHERE bill_date >= ? AND status='active'",
        (today,)).fetchone()["s"]
    week_sales = db.execute(
        "SELECT COALESCE(SUM(total),0) s FROM bills WHERE bill_date >= ? AND status='active'",
        (week_ago,)).fetchone()["s"]
    month_sales = db.execute(
        "SELECT COALESCE(SUM(total),0) s FROM bills WHERE bill_date >= ? AND status='active'",
        (month_ago,)).fetchone()["s"]

    low_stock = db.execute(
        "SELECT * FROM products WHERE stock_qty <= ? ORDER BY stock_qty ASC",
        (LOW_STOCK_THRESHOLD,)).fetchall()

    best_sellers = db.execute("""
        SELECT bi.product_name, SUM(bi.qty) total_qty
        FROM bill_items bi JOIN bills b ON bi.bill_id = b.id
        WHERE b.bill_date >= ? AND b.status = 'active'
        GROUP BY bi.product_name ORDER BY total_qty DESC LIMIT 5
    """, (month_ago,)).fetchall()

    total_products = db.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
    total_customers = db.execute("SELECT COUNT(*) c FROM customers").fetchone()["c"]

    top_udhaar = db.execute("""
        SELECT * FROM (
            SELECT c.id, c.name, c.mobile,
            COALESCE((SELECT SUM(total) FROM bills WHERE customer_id=c.id AND bill_type='Credit' AND status='active'),0)
            - COALESCE((SELECT SUM(amount) FROM payments WHERE customer_id=c.id),0) AS balance
            FROM customers c
        ) WHERE balance > 0
        ORDER BY balance DESC LIMIT 5
    """).fetchall()

    return render_template("index.html", shop_name=SHOP_NAME, today_sales=today_sales,
                            week_sales=week_sales, month_sales=month_sales, low_stock=low_stock,
                            best_sellers=best_sellers, total_products=total_products,
                            total_customers=total_customers, top_udhaar=top_udhaar)


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def get_brands(conn):
    rows = conn.execute(
        "SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL AND TRIM(brand) != '' "
        "ORDER BY brand COLLATE NOCASE").fetchall()
    return [r["brand"] for r in rows]


@app.route("/products")
@login_required
def products():
    db = get_db()
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    query = "SELECT * FROM products WHERE 1=1"
    params = []
    if q:
        query += " AND (name LIKE ? OR brand LIKE ? OR barcode LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY name COLLATE NOCASE ASC"
    items = db.execute(query, params).fetchall()
    return render_template("products.html", shop_name=SHOP_NAME, products=items, q=q,
                            category=category, categories=CATEGORIES)


@app.route("/add-product", methods=["GET", "POST"])
@login_required
def add_product_page():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        brand = request.form.get("brand", "").strip()
        power_type = request.form.get("power_type", "").strip()
        mrp = float(request.form.get("mrp") or 0)
        selling_price = float(request.form.get("selling_price") or 0)
        stock_qty = int(request.form.get("stock_qty") or 0)
        unit = request.form.get("unit", "pcs").strip() or "pcs"
        barcode = request.form.get("barcode", "").strip()

        if not name or not category:
            flash("Product name aur category zaroori hai.", "error")
        else:
            db.execute("""
                INSERT INTO products (name, category, brand, power_type, mrp, selling_price,
                    stock_qty, unit, barcode, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, category, brand, power_type, mrp, selling_price, stock_qty, unit,
                  barcode, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            db.commit()
            flash(f'Product "{name}" add ho gaya!', "success")
            return redirect(url_for("products"))

    return render_template("add_product.html", shop_name=SHOP_NAME, categories=CATEGORIES,
                            brands=get_brands(db))


@app.route("/edit-product/<int:product_id>", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        flash("Product nahi mila.", "error")
        return redirect(url_for("products"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        brand = request.form.get("brand", "").strip()
        power_type = request.form.get("power_type", "").strip()
        mrp = float(request.form.get("mrp") or 0)
        selling_price = float(request.form.get("selling_price") or 0)
        stock_qty = int(request.form.get("stock_qty") or 0)
        unit = request.form.get("unit", "pcs").strip() or "pcs"
        barcode = request.form.get("barcode", "").strip()

        if not name or not category:
            flash("Product name aur category zaroori hai.", "error")
        else:
            db.execute("""
                UPDATE products SET name=?, category=?, brand=?, power_type=?, mrp=?,
                    selling_price=?, stock_qty=?, unit=?, barcode=? WHERE id=?
            """, (name, category, brand, power_type, mrp, selling_price, stock_qty, unit,
                  barcode, product_id))
            db.commit()
            flash("Product update ho gaya!", "success")
            return redirect(url_for("products"))

    return render_template("edit_product.html", shop_name=SHOP_NAME, product=product,
                            categories=CATEGORIES, brands=get_brands(db))


@app.route("/product/<int:product_id>/delete", methods=["POST"])
@login_required
def delete_product(product_id):
    db = get_db()
    used = db.execute("SELECT COUNT(*) c FROM bill_items WHERE product_id = ?",
                       (product_id,)).fetchone()["c"]
    if used > 0:
        flash("Ye product kisi bill mein use ho chuka hai, isliye delete nahi ho sakta.", "error")
    else:
        db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        db.commit()
        flash("Product delete ho gaya.", "success")
    return redirect(url_for("products"))


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------

@app.route("/stock", methods=["GET", "POST"])
@login_required
def stock():
    db = get_db()
    if request.method == "POST":
        product_id = request.form.get("product_id")
        qty = int(request.form.get("qty") or 0)
        mode = request.form.get("mode", "add")
        if not product_id or qty <= 0:
            flash("Product aur valid quantity chuniye.", "error")
        else:
            if mode == "add":
                db.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?",
                           (qty, product_id))
                flash("Stock add ho gaya!", "success")
            else:
                db.execute("UPDATE products SET stock_qty = MAX(stock_qty - ?, 0) WHERE id = ?",
                           (qty, product_id))
                flash("Stock kam kar diya gaya.", "success")
            db.commit()
        return redirect(url_for("stock"))

    q = request.args.get("q", "").strip()
    query = "SELECT * FROM products WHERE 1=1"
    params = []
    if q:
        query += " AND (name LIKE ? OR barcode LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    query += " ORDER BY name COLLATE NOCASE ASC"
    items = db.execute(query, params).fetchall()
    all_products = db.execute("SELECT id, name, brand, stock_qty, barcode FROM products "
                               "ORDER BY name COLLATE NOCASE ASC").fetchall()
    return render_template("stock.html", shop_name=SHOP_NAME, products=items,
                            all_products=all_products, q=q, low_stock_threshold=LOW_STOCK_THRESHOLD)


# ---------------------------------------------------------------------------
# Customers & Prescriptions
# ---------------------------------------------------------------------------

def customer_balance(db, customer_id):
    credit_total = db.execute(
        "SELECT COALESCE(SUM(total),0) s FROM bills WHERE customer_id=? AND bill_type='Credit' AND status='active'",
        (customer_id,)).fetchone()["s"]
    paid_total = db.execute(
        "SELECT COALESCE(SUM(amount),0) s FROM payments WHERE customer_id=?",
        (customer_id,)).fetchone()["s"]
    return round(credit_total - paid_total, 2)


@app.route("/customers")
@login_required
def customers():
    db = get_db()
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "")
    query = "SELECT * FROM customers WHERE 1=1"
    params = []
    if q:
        query += " AND (name LIKE ? OR mobile LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    query += " ORDER BY name COLLATE NOCASE ASC"
    rows = db.execute(query, params).fetchall()

    customer_list = []
    for r in rows:
        d = dict(r)
        d["balance"] = customer_balance(db, r["id"])
        customer_list.append(d)

    if sort == "balance":
        customer_list.sort(key=lambda c: c["balance"], reverse=True)

    return render_template("customers.html", shop_name=SHOP_NAME, customers=customer_list, q=q, sort=sort)


@app.route("/add-customer", methods=["GET", "POST"])
@login_required
def add_customer():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        address = request.form.get("address", "").strip()
        if not name:
            flash("Customer ka naam zaroori hai.", "error")
        else:
            try:
                db.execute("INSERT INTO customers (name, mobile, address, created_at) VALUES (?,?,?,?)",
                           (name, mobile or None, address, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                db.commit()
                flash(f'Customer "{name}" add ho gaya!', "success")
                return redirect(url_for("customers"))
            except sqlite3.IntegrityError:
                flash("Ye mobile number pehle se registered hai.", "error")
    return render_template("add_customer.html", shop_name=SHOP_NAME)


@app.route("/customer/<int:customer_id>")
@login_required
def customer_detail(customer_id):
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        flash("Customer nahi mila.", "error")
        return redirect(url_for("customers"))

    bills = db.execute("SELECT * FROM bills WHERE customer_id = ? AND status='active' ORDER BY bill_date DESC",
                        (customer_id,)).fetchall()
    payments = db.execute("SELECT * FROM payments WHERE customer_id = ? ORDER BY payment_date DESC",
                           (customer_id,)).fetchall()
    prescriptions = db.execute("SELECT * FROM prescriptions WHERE customer_id = ? ORDER BY presc_date DESC",
                                (customer_id,)).fetchall()
    balance = customer_balance(db, customer_id)

    return render_template("customer_detail.html", shop_name=SHOP_NAME, customer=customer,
                            bills=bills, payments=payments, prescriptions=prescriptions, balance=balance)


@app.route("/customer/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_customer(customer_id):
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        flash("Customer nahi mila.", "error")
        return redirect(url_for("customers"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        address = request.form.get("address", "").strip()
        if not name:
            flash("Customer ka naam zaroori hai.", "error")
        else:
            try:
                db.execute("UPDATE customers SET name=?, mobile=?, address=? WHERE id=?",
                           (name, mobile or None, address, customer_id))
                db.commit()
                flash("Customer detail update ho gayi!", "success")
                return redirect(url_for("customer_detail", customer_id=customer_id))
            except sqlite3.IntegrityError:
                flash("Ye mobile number kisi aur customer ka hai.", "error")

    return render_template("edit_customer.html", shop_name=SHOP_NAME, customer=customer)


@app.route("/customer/<int:customer_id>/delete", methods=["POST"])
@login_required
def delete_customer(customer_id):
    db = get_db()
    bill_count = db.execute("SELECT COUNT(*) c FROM bills WHERE customer_id = ?",
                             (customer_id,)).fetchone()["c"]
    payment_count = db.execute("SELECT COUNT(*) c FROM payments WHERE customer_id = ?",
                                (customer_id,)).fetchone()["c"]
    if bill_count > 0 or payment_count > 0:
        flash("Is customer ki billing/payment history hai, isliye delete nahi ho sakta.", "error")
    else:
        db.execute("DELETE FROM prescriptions WHERE customer_id = ?", (customer_id,))
        db.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        db.commit()
        flash("Customer delete ho gaya.", "success")
    return redirect(url_for("customers"))


@app.route("/customer/<int:customer_id>/prescription/add", methods=["GET", "POST"])
@login_required
def add_prescription(customer_id):
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        flash("Customer nahi mila.", "error")
        return redirect(url_for("customers"))

    if request.method == "POST":
        fields = ["right_sph", "right_cyl", "right_axis", "right_add",
                  "left_sph", "left_cyl", "left_axis", "left_add", "pd", "notes"]
        values = [request.form.get(f, "").strip() for f in fields]
        db.execute(f"""
            INSERT INTO prescriptions (customer_id, presc_date, {', '.join(fields)})
            VALUES (?, ?, {', '.join(['?']*len(fields))})
        """, (customer_id, datetime.now().strftime("%Y-%m-%d"), *values))
        db.commit()
        flash("Prescription save ho gaya!", "success")
        return redirect(url_for("customer_detail", customer_id=customer_id))

    return render_template("add_prescription.html", shop_name=SHOP_NAME, customer=customer)


@app.route("/customer/<int:customer_id>/payment", methods=["POST"])
@login_required
def add_payment(customer_id):
    db = get_db()
    amount = float(request.form.get("amount") or 0)
    notes = request.form.get("notes", "").strip()
    if amount <= 0:
        flash("Valid payment amount daaliye.", "error")
    else:
        db.execute("INSERT INTO payments (customer_id, amount, payment_date, notes) VALUES (?,?,?,?)",
                   (customer_id, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), notes))
        db.commit()
        flash(f"₹{amount:.2f} payment record ho gaya!", "success")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/api/customer_lookup")
@login_required
def api_customer_lookup():
    mobile = request.args.get("mobile", "").strip()
    db = get_db()
    row = db.execute("SELECT name, address FROM customers WHERE mobile = ?", (mobile,)).fetchone()
    if row:
        return jsonify({"found": True, "name": row["name"], "address": row["address"] or ""})
    return jsonify({"found": False})


def find_or_create_customer(db, name, mobile, address):
    if not name:
        return None
    if mobile:
        existing = db.execute("SELECT id FROM customers WHERE mobile = ?", (mobile,)).fetchone()
        if existing:
            db.execute("UPDATE customers SET name=?, address=? WHERE id=?",
                       (name, address, existing["id"]))
            db.commit()
            return existing["id"]
    cur = db.execute("INSERT INTO customers (name, mobile, address, created_at) VALUES (?,?,?,?)",
                      (name, mobile or None, address, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------

PRESCRIPTION_FIELDS = [
    "dist_r_sph", "dist_r_cyl", "dist_r_axis", "dist_l_sph", "dist_l_cyl", "dist_l_axis",
    "read_r_sph", "read_r_cyl", "read_r_axis", "read_l_sph", "read_l_cyl", "read_l_axis",
]


@app.route("/billing")
@login_required
def billing():
    db = get_db()
    all_products = db.execute("SELECT * FROM products ORDER BY name COLLATE NOCASE ASC").fetchall()
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("billing.html", shop_name=SHOP_NAME, products=all_products, today=today)


@app.route("/create-bill", methods=["POST"])
@login_required
def create_bill():
    db = get_db()
    customer_name = request.form.get("customer_name", "").strip()
    customer_mobile = request.form.get("customer_mobile", "").strip()
    customer_address = request.form.get("customer_address", "").strip()
    bill_date_input = request.form.get("bill_date", "").strip()
    delivery_date = request.form.get("delivery_date", "").strip()
    bill_type = request.form.get("bill_type", "Cash")
    frame = request.form.get("frame", "").strip()
    glass = request.form.get("glass", "").strip()
    frame_product_id = request.form.get("frame_product_id") or None
    glass_product_id = request.form.get("glass_product_id") or None
    total = float(request.form.get("total") or 0)
    advance = float(request.form.get("advance") or 0)

    presc = {f: request.form.get(f, "").strip() for f in PRESCRIPTION_FIELDS}

    if not customer_name:
        flash("Customer ka naam zaroori hai.", "error")
        return redirect(url_for("billing"))
    if total <= 0:
        flash("Total amount zaroori hai.", "error")
        return redirect(url_for("billing"))

    # Validate stock for any catalog-linked frame/glass before committing anything
    for pid, label in [(frame_product_id, "Frame"), (glass_product_id, "Glass")]:
        if pid:
            row = db.execute("SELECT name, stock_qty FROM products WHERE id = ?", (pid,)).fetchone()
            if not row:
                flash(f"Selected {label} product nahi mila.", "error")
                return redirect(url_for("billing"))
            if row["stock_qty"] < 1:
                flash(f'"{row["name"]}" ka stock khatam hai.', "error")
                return redirect(url_for("billing"))

    customer_id = find_or_create_customer(db, customer_name, customer_mobile, customer_address)

    bill_date = bill_date_input or datetime.now().strftime("%Y-%m-%d")
    sno = get_next_sno(db)
    bill_number = f"OPT-{sno}"
    change_returned = max(advance - total, 0)

    cur = db.execute(f"""
        INSERT INTO bills (bill_number, sno, customer_id, bill_date, delivery_date, bill_type,
            {', '.join(PRESCRIPTION_FIELDS)}, frame, glass, frame_product_id, glass_product_id,
            total, advance, amount_received, change_returned, status)
        VALUES (?,?,?,?,?,?, {', '.join(['?']*len(PRESCRIPTION_FIELDS))}, ?,?,?,?,?,?,?,?, 'active')
    """, (bill_number, sno, customer_id, bill_date, delivery_date, bill_type,
          *[presc[f] for f in PRESCRIPTION_FIELDS], frame, glass, frame_product_id, glass_product_id,
          round(total, 2), round(advance, 2), round(advance, 2), round(change_returned, 2)))
    bill_id = cur.lastrowid

    if frame_product_id:
        db.execute("UPDATE products SET stock_qty = stock_qty - 1 WHERE id = ?", (frame_product_id,))
    if glass_product_id:
        db.execute("UPDATE products SET stock_qty = stock_qty - 1 WHERE id = ?", (glass_product_id,))

    db.commit()

    flash(f"Bill S.No. {sno} successfully ban gaya!", "success")
    return redirect(url_for("view_bill", bill_id=bill_id))


@app.route("/bills")
@login_required
def bills():
    db = get_db()
    q = request.args.get("q", "").strip()
    query = """
        SELECT b.*, c.name as customer_name, c.mobile as customer_mobile
        FROM bills b LEFT JOIN customers c ON b.customer_id = c.id WHERE 1=1
    """
    params = []
    if q:
        query += " AND (b.bill_number LIKE ? OR c.name LIKE ? OR c.mobile LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    query += " ORDER BY b.bill_date DESC"
    all_bills = db.execute(query, params).fetchall()
    return render_template("bills.html", shop_name=SHOP_NAME, bills=all_bills, q=q)


@app.route("/bill/<int:bill_id>")
@login_required
def view_bill(bill_id):
    db = get_db()
    bill = db.execute("""
        SELECT b.*, c.name as customer_name, c.mobile as customer_mobile, c.address as customer_address
        FROM bills b LEFT JOIN customers c ON b.customer_id = c.id WHERE b.id = ?
    """, (bill_id,)).fetchone()
    if not bill:
        flash("Bill nahi mila.", "error")
        return redirect(url_for("bills"))

    balance = round((bill["total"] or 0) - (bill["advance"] or 0), 2)

    return render_template("bill.html", shop_name=SHOP_NAME, shop_tagline=SHOP_TAGLINE,
                            shop_address=SHOP_ADDRESS, shop_phone=SHOP_PHONE, shop_gstin=SHOP_GSTIN,
                            terms=TERMS_AND_CONDITIONS, bill=bill, balance=balance)


@app.route("/bill/<int:bill_id>/delete", methods=["POST"])
@login_required
def delete_bill(bill_id):
    db = get_db()
    bill = db.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
    if not bill:
        flash("Bill nahi mila.", "error")
        return redirect(url_for("bills"))

    if bill["frame_product_id"]:
        db.execute("UPDATE products SET stock_qty = stock_qty + 1 WHERE id = ?", (bill["frame_product_id"],))
    if bill["glass_product_id"]:
        db.execute("UPDATE products SET stock_qty = stock_qty + 1 WHERE id = ?", (bill["glass_product_id"],))

    db.execute("DELETE FROM bills WHERE id = ?", (bill_id,))
    db.commit()
    flash(f'Bill S.No. {bill["sno"] or bill["bill_number"]} delete ho gaya aur stock restore ho gaya.', "success")
    return redirect(url_for("bills"))


@app.route("/bill/<int:bill_id>/edit", methods=["GET", "POST"])
@login_required
def edit_bill(bill_id):
    db = get_db()
    bill = db.execute("""
        SELECT b.*, c.name as customer_name, c.mobile as customer_mobile
        FROM bills b LEFT JOIN customers c ON b.customer_id = c.id WHERE b.id = ?
    """, (bill_id,)).fetchone()
    if not bill:
        flash("Bill nahi mila.", "error")
        return redirect(url_for("bills"))

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        customer_mobile = request.form.get("customer_mobile", "").strip()
        delivery_date = request.form.get("delivery_date", "").strip()
        bill_type = request.form.get("bill_type", bill["bill_type"])
        frame = request.form.get("frame", "").strip()
        glass = request.form.get("glass", "").strip()
        new_frame_pid = request.form.get("frame_product_id") or None
        new_glass_pid = request.form.get("glass_product_id") or None
        total = float(request.form.get("total") or 0)
        advance = float(request.form.get("advance") or 0)
        presc = {f: request.form.get(f, "").strip() for f in PRESCRIPTION_FIELDS}

        old_frame_pid = bill["frame_product_id"]
        old_glass_pid = bill["glass_product_id"]

        # Validate stock for any newly-linked product before touching anything
        for old_pid, new_pid, label in [(old_frame_pid, new_frame_pid, "Frame"),
                                         (old_glass_pid, new_glass_pid, "Glass")]:
            if new_pid and new_pid != old_pid:
                row = db.execute("SELECT name, stock_qty FROM products WHERE id = ?", (new_pid,)).fetchone()
                if not row:
                    flash(f"Selected {label} product nahi mila.", "error")
                    return redirect(url_for("edit_bill", bill_id=bill_id))
                if row["stock_qty"] < 1:
                    flash(f'"{row["name"]}" ka stock khatam hai.', "error")
                    return redirect(url_for("edit_bill", bill_id=bill_id))

        # Restore stock for old links, then deduct for new links (only where the link changed)
        if old_frame_pid and old_frame_pid != new_frame_pid:
            db.execute("UPDATE products SET stock_qty = stock_qty + 1 WHERE id = ?", (old_frame_pid,))
        if old_glass_pid and old_glass_pid != new_glass_pid:
            db.execute("UPDATE products SET stock_qty = stock_qty + 1 WHERE id = ?", (old_glass_pid,))
        if new_frame_pid and new_frame_pid != old_frame_pid:
            db.execute("UPDATE products SET stock_qty = stock_qty - 1 WHERE id = ?", (new_frame_pid,))
        if new_glass_pid and new_glass_pid != old_glass_pid:
            db.execute("UPDATE products SET stock_qty = stock_qty - 1 WHERE id = ?", (new_glass_pid,))

        if bill["customer_id"] and customer_name:
            db.execute("UPDATE customers SET name=?, mobile=? WHERE id=?",
                       (customer_name, customer_mobile or None, bill["customer_id"]))

        set_clause = ", ".join(f"{f}=?" for f in PRESCRIPTION_FIELDS)
        db.execute(f"""
            UPDATE bills SET delivery_date=?, bill_type=?, frame=?, glass=?, frame_product_id=?,
                glass_product_id=?, total=?, advance=?, amount_received=?, change_returned=?, {set_clause}
            WHERE id=?
        """, (delivery_date, bill_type, frame, glass, new_frame_pid, new_glass_pid,
              round(total, 2), round(advance, 2), round(advance, 2), round(max(advance - total, 0), 2),
              *[presc[f] for f in PRESCRIPTION_FIELDS], bill_id))
        db.commit()
        flash("Bill update ho gaya!", "success")
        return redirect(url_for("view_bill", bill_id=bill_id))

    all_products = db.execute("SELECT * FROM products ORDER BY name COLLATE NOCASE ASC").fetchall()
    return render_template("edit_bill.html", shop_name=SHOP_NAME, bill=bill, products=all_products)


# ---------------------------------------------------------------------------
# Sales report
# ---------------------------------------------------------------------------

@app.route("/sales-report")
@login_required
def sales_report():
    db = get_db()
    start = request.args.get("start", "")
    end = request.args.get("end", "")

    query = "SELECT b.*, c.name as customer_name FROM bills b LEFT JOIN customers c ON b.customer_id=c.id WHERE b.status='active'"
    params = []
    if start:
        query += " AND b.bill_date >= ?"
        params.append(start)
    if end:
        query += " AND b.bill_date <= ?"
        params.append(end + " 23:59:59")
    query += " ORDER BY b.bill_date DESC"

    rows = db.execute(query, params).fetchall()
    total_sales = sum(r["total"] for r in rows)
    cash_sales = sum(r["total"] for r in rows if r["bill_type"] == "Cash")
    credit_sales = sum(r["total"] for r in rows if r["bill_type"] == "Credit")

    return render_template("sales_report.html", shop_name=SHOP_NAME, bills=rows,
                            total_sales=total_sales, cash_sales=cash_sales,
                            credit_sales=credit_sales, start=start, end=end)


@app.route("/sales-report/export")
@login_required
def export_sales_report():
    import csv
    import io
    from flask import Response

    db = get_db()
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    query = "SELECT b.*, c.name as customer_name FROM bills b LEFT JOIN customers c ON b.customer_id=c.id WHERE b.status='active'"
    params = []
    if start:
        query += " AND b.bill_date >= ?"
        params.append(start)
    if end:
        query += " AND b.bill_date <= ?"
        params.append(end + " 23:59:59")
    query += " ORDER BY b.bill_date DESC"
    rows = db.execute(query, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Bill Number", "Date", "Customer", "Type", "Total"])
    for r in rows:
        writer.writerow([r["bill_number"], r["bill_date"], r["customer_name"] or "Walk-in",
                          r["bill_type"], r["total"]])

    return Response(output.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": "attachment;filename=sales_report.csv"})


if __name__ == "__main__":
    init_db()
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
else:
    init_db()
