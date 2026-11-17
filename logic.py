"""CloudBite demo - business logic (SQLite, no external dependencies).

Rule implemented: a customer who cancels AFTER food preparation has started
(about 5 minutes after ordering) is charged the discount amount. The food is
offered at a discount to customers in the same area.
  * order already paid -> refund = amount - charge
  * order not paid     -> charge is added to the customer's NEXT order
"""
import sqlite3
import threading
import time

RESCUE_WINDOW_SEC = 5 * 60   # food is considered "preparing" about 5 min after ordering
DISCOUNT_PCT = 30            # discount on the rescued food (also the charge to the canceller)

_lock = threading.RLock()
_db = sqlite3.connect(":memory:", check_same_thread=False)
_db.row_factory = sqlite3.Row


class RuleError(Exception):
    """Raised when a business rule blocks an action (shown to the user)."""


SCHEMA = """
CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT, area TEXT);
CREATE TABLE foods(id INTEGER PRIMARY KEY, name TEXT, restaurant TEXT, area TEXT, price INTEGER);
CREATE TABLE orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, food_id INT, food_name TEXT,
  restaurant TEXT, area TEXT, base_price INT, extra_charge INT, amount INT,
  paid INT, status TEXT, created_at REAL, refund INT DEFAULT 0, note TEXT DEFAULT '',
  rescued INT DEFAULT 0);
CREATE TABLE offers(
  id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INT, food_name TEXT, restaurant TEXT,
  area TEXT, original_price INT, offer_price INT, discount INT, canceller_id INT,
  status TEXT, buyer_id INT, created_at REAL);
CREATE TABLE charges(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, amount INT, from_order INT,
  status TEXT, applied_to_order INT);
CREATE TABLE notifications(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, message TEXT, offer_id INT, created_at REAL);
CREATE TABLE stats(key TEXT PRIMARY KEY, value INT);
"""


def reset():
    """(Re)create the database with demo data."""
    with _lock:
        for t in ("users", "foods", "orders", "offers", "charges", "notifications", "stats"):
            _db.execute(f"DROP TABLE IF EXISTS {t}")
        _db.executescript(SCHEMA)
        _db.executemany("INSERT INTO users VALUES(?,?,?)", [
            (1, "Harshit", "Adyar"), (2, "Abhay", "Adyar"),
            (3, "Priya", "Adyar"), (4, "Rahul", "T Nagar")])
        _db.executemany("INSERT INTO foods VALUES(?,?,?,?,?)", [
            (1, "Chicken Biryani", "Spice Hub", "Adyar", 300),
            (2, "Paneer Wrap", "Wrap Corner", "Adyar", 180),
            (3, "Masala Dosa", "Dosa Palace", "Adyar", 120)])
        _db.executemany("INSERT INTO stats VALUES(?,?)", [
            ("late_cancellations", 0), ("meals_rescued", 0),
            ("charges_recovered", 0), ("food_saved_value", 0)])
        _db.commit()


def _rows(sql, args=()):
    return [dict(r) for r in _db.execute(sql, args).fetchall()]


def _bump(key, n=1):
    _db.execute("UPDATE stats SET value = value + ? WHERE key=?", (n, key))


def _is_preparing(order):
    """Food counts as 'preparing' ~5 min after the order is placed."""
    return (time.time() - order["created_at"]) >= RESCUE_WINDOW_SEC


def place_order(user_id, food_id, paid):
    with _lock:
        user = _db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        food = _db.execute("SELECT * FROM foods WHERE id=?", (food_id,)).fetchone()
        if not user or not food:
            raise RuleError("Unknown user or food item.")
        pending = _rows("SELECT * FROM charges WHERE user_id=? AND status='pending'", (user_id,))
        extra = sum(c["amount"] for c in pending)
        amount = food["price"] + extra
        note = f"Includes Rs {extra} cancellation charge from an earlier order." if extra else ""
        cur = _db.execute(
            "INSERT INTO orders(user_id,food_id,food_name,restaurant,area,base_price,extra_charge,"
            "amount,paid,status,created_at,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, food_id, food["name"], food["restaurant"], food["area"], food["price"],
             extra, amount, 1 if paid else 0, "Placed", time.time(), note))
        oid = cur.lastrowid
        for c in pending:
            _db.execute("UPDATE charges SET status='applied', applied_to_order=? WHERE id=?",
                        (oid, c["id"]))
        if extra:
            _bump("charges_recovered", extra)
        _db.commit()
        return oid


def skip_time(order_id):
    """Demo helper: pretend 5 minutes have passed since the order was placed."""
    with _lock:
        o = _db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not o:
            raise RuleError("Order not found.")
        _db.execute("UPDATE orders SET created_at=? WHERE id=?",
                    (o["created_at"] - RESCUE_WINDOW_SEC, order_id))
        _db.commit()


def cancel_order(order_id):
    with _lock:
        o = _db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not o:
            raise RuleError("Order not found.")
        o = dict(o)
        if o["status"] in ("Cancelled", "Delivered"):
            raise RuleError(f"Order is already {o['status']}.")

        # Early cancellation: food not started -> free cancel, full refund if paid.
        if not _is_preparing(o):
            refund = o["amount"] if o["paid"] else 0
            _db.execute("UPDATE orders SET status='Cancelled', refund=?, note=? WHERE id=?",
                        (refund, "Cancelled before cooking started. No charge.", order_id))
            _db.commit()
            return {"late": False, "message": "Cancelled before cooking started. No charge."}

        # Late cancellation: charge = discount given on the rescued food.
        charge = round(o["base_price"] * DISCOUNT_PCT / 100)
        offer_price = o["base_price"] - charge
        if o["paid"]:
            refund = o["amount"] - charge
            note = f"Late cancellation. Charge Rs {charge}; refunded Rs {refund}."
        else:
            refund = 0
            _db.execute("INSERT INTO charges(user_id,amount,from_order,status) VALUES(?,?,?,'pending')",
                        (o["user_id"], charge, order_id))
            note = f"Late cancellation. Rs {charge} will be added to your next order."
        _db.execute("UPDATE orders SET status='Cancelled', refund=?, note=? WHERE id=?",
                    (refund, note, order_id))
        cur = _db.execute(
            "INSERT INTO offers(order_id,food_name,restaurant,area,original_price,offer_price,"
            "discount,canceller_id,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (order_id, o["food_name"], o["restaurant"], o["area"], o["base_price"], offer_price,
             charge, o["user_id"], "open", time.time()))
        offer_id = cur.lastrowid
        nearby = _rows("SELECT * FROM users WHERE area=? AND id<>?", (o["area"], o["user_id"]))
        for u in nearby:
            _db.execute(
                "INSERT INTO notifications(user_id,message,offer_id,created_at) VALUES(?,?,?,?)",
                (u["id"], f"{o['food_name']} from {o['restaurant']} is available at Rs {offer_price} "
                          f"(Rs {o['base_price']}) near you.", offer_id, time.time()))
        _bump("late_cancellations")
        _db.commit()
        return {"late": True, "message": note, "offer_id": offer_id, "notified": len(nearby)}


def claim_offer(offer_id, user_id):
    """First customer in the same area to claim gets the food."""
    with _lock:
        user = _db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        offer = _db.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
        if not user or not offer:
            raise RuleError("Offer not found.")
        if user["area"] != offer["area"]:
            raise RuleError("This offer is only for customers in the same area.")
        if user["id"] == offer["canceller_id"]:
            raise RuleError("You cannot buy the food you cancelled.")
        cur = _db.execute("UPDATE offers SET status='sold', buyer_id=? WHERE id=? AND status='open'",
                          (user_id, offer_id))
        if cur.rowcount == 0:
            raise RuleError("Sorry, this offer has already been taken.")
        cur = _db.execute(
            "INSERT INTO orders(user_id,food_id,food_name,restaurant,area,base_price,extra_charge,"
            "amount,paid,status,created_at,note,rescued) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)",
            (user_id, 0, offer["food_name"], offer["restaurant"], offer["area"],
             offer["offer_price"], 0, offer["offer_price"], 1, "Preparing", time.time() - RESCUE_WINDOW_SEC,
             f"Rescued food at a discount (saved Rs {offer['discount']})."))
        _bump("meals_rescued")
        _bump("food_saved_value", offer["original_price"])
        _db.commit()
        return cur.lastrowid


def state():
    with _lock:
        now = time.time()
        orders = _rows("SELECT * FROM orders ORDER BY id DESC")
        for o in orders:
            o["preparing"] = _is_preparing(o)
            o["seconds_to_prep"] = max(0, int(RESCUE_WINDOW_SEC - (now - o["created_at"])))
        return {
            "users": _rows("SELECT * FROM users"),
            "foods": _rows("SELECT * FROM foods"),
            "orders": orders,
            "offers": _rows("SELECT * FROM offers ORDER BY id DESC"),
            "charges": _rows("SELECT * FROM charges ORDER BY id DESC"),
            "notifications": _rows("SELECT * FROM notifications ORDER BY id DESC"),
            "stats": {r["key"]: r["value"] for r in _rows("SELECT * FROM stats")},
            "config": {"window_min": RESCUE_WINDOW_SEC // 60, "discount_pct": DISCOUNT_PCT},
        }


reset()
