import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import requests
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash


def load_env():
    """Read the local .env file. On Vercel, settings come from its own dashboard instead."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)

PAYMENT_MODES = ["Cash", "GCash", "Maya", "Card"]
STATUSES = ["Pending", "Preparing", "Ready", "Completed", "Cancelled"]
PH_TZ = timezone(timedelta(hours=8))

MENU = {
    "Coffee": [
        {"name": "Espresso", "price": 90},
        {"name": "Americano", "price": 100},
        {"name": "Caffe Latte", "price": 130},
        {"name": "Iced Caramel Macchiato", "price": 150},
    ],
    "Brownies": [
        {"name": "Classic Fudge Brownie", "price": 85},
        {"name": "Walnut Brownie", "price": 95},
    ],
    "Cookies": [
        {"name": "Chocolate Chip Cookie", "price": 65},
        {"name": "Oatmeal Raisin Cookie", "price": 65},
    ],
    "Pasta": [
        {"name": "Creamy Carbonara", "price": 180},
        {"name": "Spaghetti Bolognese", "price": 170},
        {"name": "Aglio e Olio", "price": 160},
    ],
}

# name -> price lookup, so the server calculates the total itself
PRICES = {item["name"]: item["price"] for items in MENU.values() for item in items}


def db(method, table, params=None, json=None, returning=False):
    """Talk to the Supabase database."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase settings are missing (.env file or Vercel environment variables).")
    headers = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    if SUPABASE_KEY.startswith("eyJ"):  # older style keys also need this header
        headers["Authorization"] = "Bearer " + SUPABASE_KEY
    if returning:
        headers["Prefer"] = "return=representation"
    res = requests.request(
        method, f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers, params=params, json=json, timeout=10,
    )
    if not res.ok:
        raise RuntimeError(f"Supabase error {res.status_code}: {res.text}")
    return res.json() if res.text else None


def fmt_time(value):
    try:
        return datetime.fromisoformat(value).astimezone(PH_TZ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return value


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


PAGE = """
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Our Menu</title>
  <style>
    body { font-family: sans-serif; max-width: 480px; margin: auto; padding: 16px 16px 90px; background: #faf6f1; }
    h1 { text-align: center; color: #4b2e1e; }
    h2 { color: #6f4e37; border-bottom: 2px solid #d9c3ad; padding-bottom: 4px; }
    .item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; }
    .info small { display: block; color: #777; }
    .ctrl { display: flex; align-items: center; gap: 10px; }
    .ctrl button { width: 32px; height: 32px; border-radius: 50%; border: none; background: #6f4e37; color: white; font-size: 18px; }
    .qty { min-width: 20px; text-align: center; }
    .bar { position: fixed; left: 0; right: 0; bottom: 0; background: #4b2e1e; color: white; padding: 14px 16px; display: none; justify-content: space-between; align-items: center; }
    .bar button, .primary { background: #d9a066; border: none; padding: 10px 16px; border-radius: 8px; font-size: 16px; }
    .secondary { background: none; border: 1px solid #6f4e37; padding: 10px 16px; border-radius: 8px; font-size: 16px; margin-top: 8px; }
    label { display: block; margin-top: 12px; font-weight: bold; }
    input, select { width: 100%; padding: 10px; font-size: 16px; margin-top: 4px; box-sizing: border-box; }
    .line { display: flex; justify-content: space-between; padding: 4px 0; }
    .hidden { display: none; }
  </style>
</head>
<body>

<div id="menuView">
  <h1>☕ Our Menu</h1>
  {% for category, items in menu.items() %}
    <h2>{{ category }}</h2>
    {% for item in items %}
      <div class="item" data-name="{{ item.name }}" data-price="{{ item.price }}">
        <div class="info"><span>{{ item.name }}</span><small>₱{{ item.price }}</small></div>
        <div class="ctrl">
          <button onclick="change(this, -1)">-</button>
          <span class="qty">0</span>
          <button onclick="change(this, 1)">+</button>
        </div>
      </div>
    {% endfor %}
  {% endfor %}
</div>

<div class="bar" id="bar">
  <span id="barText"></span>
  <button onclick="openCheckout()">View order</button>
</div>

<div id="checkoutView" class="hidden">
  <h1>Your Order</h1>
  <div id="lines"></div>
  <p><b>Total: ₱<span id="sum"></span></b></p>

  <label for="cname">Your name</label>
  <input id="cname" placeholder="e.g. Maria" autocomplete="name">

  <label for="pay">Mode of payment</label>
  <select id="pay">
    <option value="">Choose...</option>
    {% for p in modes %}<option>{{ p }}</option>{% endfor %}
  </select>

  <button class="primary" style="margin-top:16px; width:100%;" onclick="placeOrder()">Place order</button>
  <button class="secondary" style="width:100%;" onclick="closeCheckout()">Back to menu</button>
</div>

<div id="doneView" class="hidden">
  <h1>✅ Order received!</h1>
  <p id="doneText"></p>
  <button class="primary" onclick="location.reload()">Order again</button>
</div>

<script>
const cart = {};

function change(btn, delta) {
  const row = btn.closest('.item');
  const name = row.dataset.name;
  const price = Number(row.dataset.price);
  const current = cart[name] ? cart[name].qty : 0;
  const qty = Math.max(0, current + delta);
  if (qty === 0) { delete cart[name]; } else { cart[name] = { price: price, qty: qty }; }
  row.querySelector('.qty').textContent = qty;
  renderBar();
}

function totals() {
  let count = 0, sum = 0;
  for (const n in cart) { count += cart[n].qty; sum += cart[n].qty * cart[n].price; }
  return { count: count, sum: sum };
}

function renderBar() {
  const t = totals();
  document.getElementById('bar').style.display = t.count ? 'flex' : 'none';
  document.getElementById('barText').textContent = t.count + ' item(s) - ₱' + t.sum;
}

function openCheckout() {
  const box = document.getElementById('lines');
  box.innerHTML = '';
  for (const n in cart) {
    const div = document.createElement('div');
    div.className = 'line';
    div.textContent = cart[n].qty + ' x ' + n + '  —  ₱' + (cart[n].qty * cart[n].price);
    box.appendChild(div);
  }
  document.getElementById('sum').textContent = totals().sum;
  document.getElementById('menuView').classList.add('hidden');
  document.getElementById('bar').style.display = 'none';
  document.getElementById('checkoutView').classList.remove('hidden');
}

function closeCheckout() {
  document.getElementById('checkoutView').classList.add('hidden');
  document.getElementById('menuView').classList.remove('hidden');
  renderBar();
}

async function placeOrder() {
  const name = document.getElementById('cname').value.trim();
  const payment = document.getElementById('pay').value;
  if (!name) { alert('Please enter your name.'); return; }
  if (!payment) { alert('Please choose a mode of payment.'); return; }

  const items = {};
  for (const n in cart) { items[n] = cart[n].qty; }

  try {
    const res = await fetch('/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, payment: payment, items: items })
    });
    const data = await res.json();
    if (!data.ok) { alert(data.error || 'Something went wrong.'); return; }
    document.getElementById('doneText').textContent =
      'Thank you, ' + name + '! Your order number is #' + data.order_id +
      '. Total: ₱' + data.total + ' (' + payment + '). Please wait for your order.';
    document.getElementById('checkoutView').classList.add('hidden');
    document.getElementById('doneView').classList.remove('hidden');
  } catch (e) {
    alert('Could not send your order. Please try again.');
  }
}
</script>
</body>
</html>
"""

LOGIN_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Admin Login</title>
  <style>
    body { font-family: sans-serif; max-width: 360px; margin: 60px auto; padding: 16px; }
    input, button { width: 100%; padding: 10px; font-size: 16px; margin-top: 8px; box-sizing: border-box; }
    button { background: #6f4e37; color: white; border: none; border-radius: 6px; }
    .error { color: #b00020; }
  </style>
</head>
<body>
  <h1>Admin Login</h1>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post">
    <input name="username" placeholder="Username" required>
    <input name="password" type="password" placeholder="Password" required>
    <button>Log in</button>
  </form>
</body>
</html>
"""

ADMIN_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Manage Orders</title>
  <style>
    body { font-family: sans-serif; padding: 16px; }
    .top { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
    .filters a { margin-right: 10px; }
    .filters a.on { font-weight: bold; text-decoration: none; color: black; }
    table { border-collapse: collapse; width: 100%; margin-top: 12px; }
    th, td { border: 1px solid #ccc; padding: 8px; text-align: left; vertical-align: top; }
    th { background: #eee; }
    form { display: flex; gap: 6px; }
  </style>
</head>
<body>
  <div class="top">
    <h1>Manage Orders</h1>
    <div>Logged in as <b>{{ admin }}</b> | <a href="{{ url_for('admin_logout') }}">Log out</a></div>
  </div>
  <p>Completed sales: <b>₱{{ sales }}</b></p>

  <div class="filters">
    <a href="{{ url_for('admin_orders') }}" class="{{ 'on' if not current else '' }}">All</a>
    {% for s in statuses %}
      <a href="{{ url_for('admin_orders', status=s) }}" class="{{ 'on' if current == s else '' }}">{{ s }}</a>
    {% endfor %}
  </div>

  <table>
    <tr><th>#</th><th>Time</th><th>Name</th><th>Payment</th><th>Items</th><th>Total</th><th>Status</th></tr>
    {% for r in rows %}
      <tr>
        <td>{{ r[0] }}</td><td>{{ r[5] }}</td><td>{{ r[1] }}</td><td>{{ r[2] }}</td>
        <td>{{ r[3] }}</td><td>₱{{ r[4] }}</td>
        <td>
          <form method="post" action="{{ url_for('update_status', order_id=r[0]) }}">
            <input type="hidden" name="current" value="{{ current }}">
            <select name="status">
              {% for s in statuses %}<option {% if s == r[6] %}selected{% endif %}>{{ s }}</option>{% endfor %}
            </select>
            <button>Update</button>
          </form>
        </td>
      </tr>
    {% endfor %}
  </table>
  <p>Refresh the page to see new orders.</p>
</body>
</html>
"""


@app.route("/")
def menu():
    return render_template_string(PAGE, menu=MENU, modes=PAYMENT_MODES)


@app.route("/order", methods=["POST"])
def order():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    payment = data.get("payment")
    items = data.get("items") or {}

    if not name:
        return jsonify(ok=False, error="Please enter your name."), 400
    if payment not in PAYMENT_MODES:
        return jsonify(ok=False, error="Please choose a valid mode of payment."), 400

    lines, total = [], 0
    for item_name, qty in items.items():
        if item_name in PRICES and isinstance(qty, int) and qty > 0:
            total += PRICES[item_name] * qty
            lines.append(f"{qty} x {item_name}")

    if not lines:
        return jsonify(ok=False, error="Your cart is empty."), 400

    try:
        saved = db(
            "POST", "orders",
            json={
                "customer_name": name,
                "payment_mode": payment,
                "items": ", ".join(lines),
                "total": total,
            },
            returning=True,
        )
    except Exception as e:
        print("Order error:", e)
        return jsonify(ok=False, error="Sorry, we could not save your order. Please try again."), 500

    return jsonify(ok=True, order_id=saved[0]["id"], total=total)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        rows = []
        try:
            rows = db("GET", "admins", params={"select": "password_hash", "username": f"eq.{username}"})
        except Exception as e:
            print("Login error:", e)
            error = "Could not reach the database. Please try again."
        if rows and check_password_hash(rows[0]["password_hash"], password):
            session.clear()
            session["admin"] = username
            return redirect(url_for("admin_orders"))
        if not error:
            error = "Wrong username or password."
    return render_template_string(LOGIN_PAGE, error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_orders():
    current = request.args.get("status", "")
    params = {
        "select": "id,customer_name,payment_mode,items,total,created_at,status",
        "order": "id.desc",
        "limit": "200",
    }
    if current in STATUSES:
        params["status"] = f"eq.{current}"
    else:
        current = ""
    try:
        data = db("GET", "orders", params=params)
        done = db("GET", "orders", params={"select": "total", "status": "eq.Completed"})
    except Exception as e:
        print("Admin load error:", e)
        return "Could not load orders. Check your database settings.", 500

    rows = [
        (r["id"], r["customer_name"], r["payment_mode"], r["items"],
         r["total"], fmt_time(r["created_at"]), r["status"])
        for r in data
    ]
    sales = sum(r["total"] for r in done)
    return render_template_string(
        ADMIN_PAGE, rows=rows, statuses=STATUSES, current=current,
        sales=sales, admin=session["admin"],
    )


@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@login_required
def update_status(order_id):
    status = request.form.get("status")
    if status in STATUSES:
        try:
            db("PATCH", "orders", params={"id": f"eq.{order_id}"}, json={"status": status})
        except Exception as e:
            print("Update error:", e)
    return redirect(url_for("admin_orders", status=request.form.get("current", "")))


if __name__ == "__main__":
    app.run(debug=True)