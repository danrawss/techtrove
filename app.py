from dotenv import load_dotenv
import os
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
import uuid
import re
from helpers import apology, login_required, get_time, get_cart_count, get_wishlist_count, send_email

# Load environment variables
load_dotenv()

# Configure application
app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
DATABASE_URL = os.getenv("DATABASE_URL")
db = SQL(DATABASE_URL)

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username:
            return apology("must provide username", 403)
        if not password:
            return apology("must provide password", 403)

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        session["user_id"] = rows[0]["id"]
        return redirect("/")
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    session.clear()
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username:
            return apology("Username cannot be blank.", 400)
        if not password or password != confirmation:
            return apology("Passwords must match.", 400)       
        if len(password) < 8 or not re.search(r"[a-z]", password) or not re.search(r"[A-Z]", password) \
           or not re.search(r"\d", password) or not re.search(r"[@$!%*?&]", password):
            return apology("Password must be at least 8 characters long, include a mix of upper and lower case letters, a number, and a special character.", 400)
        
        usernamecheck = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(usernamecheck) > 0:
            return apology("Username already exists. Please choose a different one.", 400)

        db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", username,
                   generate_password_hash(request.form.get("password"), method='pbkdf2', salt_length=16))
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/")
@login_required
def index():
    """Render the homepage"""
    user_id = session["user_id"]
    cart_count = get_cart_count(user_id)
    wishlist_count = get_wishlist_count(user_id)
    return render_template("index.html", cart_count=cart_count, wishlist_count=wishlist_count)


@app.route("/search")
@login_required
def search():
    """Search for products"""
    user_id = session["user_id"]
    cart_count = get_cart_count(user_id)
    wishlist_count = get_wishlist_count(user_id)

    query = request.args.get("query")
    if not query:
        return redirect("/")  

    products = db.execute("SELECT * FROM products WHERE product_name LIKE ?", f"%{query}%")
    return render_template("search_results.html", products=products, query=query, cart_count=cart_count, wishlist_count=wishlist_count)


@app.route("/search/autocomplete", methods=["GET"])
def search_autocomplete():
    """Provide autocomplete suggestions for the search bar"""
    query = request.args.get("q", "").lower()  
    if not query:
        return jsonify([])  

    results = db.execute(
        "SELECT product_name FROM products WHERE LOWER(product_name) LIKE ? LIMIT 10",
        f"%{query}%"
    )  
    suggestions = [row["product_name"] for row in results]
    return jsonify(suggestions)


# Routes for shopping cart
@app.route("/cart")
@login_required
def view_cart():
    user_id = session["user_id"]
    cart_items = db.execute("SELECT product_name, product_price, quantity FROM shopping_cart WHERE user_id = ?", user_id) 
    total_price = sum(float(item["product_price"]) * int(item["quantity"]) for item in cart_items)
    cart_count = get_cart_count(user_id)
    wishlist_count = get_wishlist_count(user_id)
    return render_template("cart.html", cart_items=cart_items, total_price=total_price, cart_count=cart_count, wishlist_count=wishlist_count)


@app.route("/cart/add", methods=["POST"])
@login_required
def add_to_cart():
    """Add an item to the shopping cart"""
    user_id = session["user_id"]
    data = request.get_json()  
    if not data:
        return jsonify({"error": "No data provided"}), 400

    product_id = data.get("product_id")
    product_quantity = data.get("quantity", 1)
    product = db.execute("SELECT product_name, product_price FROM products WHERE id = ?", product_id)

    if not product:
        return jsonify({"error": "Product not found"}), 404

    product_name = product[0]["product_name"]
    product_price = float(product[0]["product_price"])

    existing_item = db.execute("SELECT * FROM shopping_cart WHERE user_id = ? AND product_name = ?", user_id, product_name)
    if existing_item:
        db.execute("UPDATE shopping_cart SET quantity = quantity + ? WHERE user_id = ? AND product_name = ?", product_quantity, user_id, product_name)
    else:
        db.execute("INSERT INTO shopping_cart (user_id, product_name, product_price, quantity) VALUES (?, ?, ?, ?)", user_id, product_name, product_price, product_quantity)

    total_items = get_cart_count(user_id)
    return jsonify({"message": "Item added to cart", "total_items": total_items})


@app.route("/cart/remove", methods=["POST"])
@login_required
def remove_from_cart():
    """Remove an item from the shopping cart"""
    user_id = session["user_id"]
    product_name = request.json.get("product_name")

    db.execute("DELETE FROM shopping_cart WHERE user_id = ? AND product_name = ?", user_id, product_name)
    cart_items = db.execute("SELECT SUM(quantity) AS total_items FROM shopping_cart WHERE user_id = ?", user_id)
    total_items = cart_items[0]["total_items"] if cart_items[0]["total_items"] else 0

    cart_items = db.execute("SELECT product_price, quantity FROM shopping_cart WHERE user_id = ?", user_id)
    total_price = sum(float(item["product_price"]) * int(item["quantity"]) for item in cart_items)
    return jsonify({"message": "Item removed from cart", "total_items": total_items, "total_price": float(total_price) if total_price else 0.00})


# Routes for wishlist
@app.route("/wishlist")
@login_required
def view_wishlist():
    user_id = session["user_id"]
    wishlist_items = db.execute("SELECT products.* FROM wishlist JOIN products ON wishlist.product_id = products.id WHERE wishlist.user_id = ?", user_id)

    cart_count = get_cart_count(user_id)
    wishlist_count = get_wishlist_count(user_id)
    return render_template("wishlist.html", wishlist_items=wishlist_items, cart_count=cart_count, wishlist_count=wishlist_count)


@app.route("/wishlist/add", methods=["POST"])
@login_required
def add_to_wishlist():
    user_id = session["user_id"]
    data = request.get_json()
    product_id = data.get("product_id")

    if not product_id:
        return jsonify({"error": "Product ID is required"}), 400

    existing_item = db.execute("SELECT * FROM wishlist WHERE user_id = ? AND product_id = ?", user_id, product_id)

    if not existing_item:
        db.execute("INSERT INTO wishlist (user_id, product_id) VALUES (?, ?)", user_id, product_id)

    total_items = get_wishlist_count(user_id)    
    return jsonify({"message": "Item added to wishlist", "total_items": total_items})


@app.route("/wishlist/remove", methods=["POST"])
@login_required
def remove_from_wishlist():
    user_id = session["user_id"]
    data = request.get_json()
    product_id = data.get("product_id")

    if product_id:
        db.execute("DELETE FROM wishlist WHERE user_id = ? AND product_id = ?", user_id, product_id)
        total_items = get_wishlist_count(user_id)  
        return jsonify({"message": "Item removed from wishlist", "total_items": total_items})
    else:
        return jsonify({"error": "Product ID is required"}), 400
    

# Routes for checkout
@app.route("/checkout", methods=["GET", "POST"])
@login_required
def view_checkout():
    user_id = session.get("user_id")

    cart_items = db.execute("SELECT product_name, product_price, quantity FROM shopping_cart WHERE user_id = ?", user_id)
    total_price = sum(float(item["product_price"]) * int(item["quantity"]) for item in cart_items)

    if request.method == "POST":
        data = request.get_json()
        full_name = data.get("fullName")
        address = data.get("address")
        city = data.get("city")
        postal_code = data.get("postalCode")
        phone = data.get("phone")
        email = data.get("email")

        if not all([full_name, address, city, postal_code, phone]):
            return jsonify({"error": "All shipping fields are required"}), 400

        db.execute("DELETE FROM shopping_cart WHERE user_id = ?", user_id)

        order_id = uuid.uuid4().hex
        order_time = get_time()

        for item in cart_items:
            db.execute(
                "INSERT INTO orders (order_id, user_id, product_name, product_price, quantity, total_price, full_name, address, city, postal_code, phone, email, order_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                order_id,
                user_id,
                item["product_name"],
                item["product_price"],
                item["quantity"],
                total_price,
                full_name,
                address,
                city,
                postal_code,
                phone,
                email,
                order_time,
            )

        email_subject = "Your TechTrove Order Confirmation"
        email_body = (
            f"Dear {full_name},\n\n"
            "Thank you for your order! Here are the details:\n\n"
            "Shipping Address:\n"
            f"{address}\n"
            f"{city}, {postal_code}\n\n"
            "Order Summary:\n"
        )
        for item in cart_items:
            email_body += f"- {item['product_name']} x {item['quantity']} - ${float(item['product_price']) * int(item['quantity']):.2f}\n"
        email_body += f"\nTotal: ${total_price:.2f}\n\nWe hope to see you again soon!\n\nTechTrove Team"

        try:
            send_email(email, email_subject, email_body)
        except Exception as e:
            return jsonify({"error": f"Failed to send email: {str(e)}"}), 500
        
        return jsonify({"message": "Order placed successfully", "redirect_url": "/checkout_success"}), 200

    return render_template("checkout.html", cart_items=cart_items, total_price=total_price)


@app.route("/checkout_success")
@login_required
def checkout_success():
    return render_template("checkout_success.html")


# Routes for brand pages
@app.route("/apple")
@login_required
def view_apple():
    """Render the Apple products page with categories"""
    user_id = session["user_id"]
    cart_count = get_cart_count(user_id)
    wishlist_count = get_wishlist_count(user_id)

    categories = db.execute("SELECT DISTINCT category FROM products WHERE brand = 'Apple'")
    categorized_products = {}
    
    for category in categories:
        category_name = category['category']
        products = db.execute("SELECT * FROM products WHERE brand = 'Apple' AND category = ?", category_name)
        categorized_products[category_name] = products

    best_products = db.execute("SELECT * FROM products WHERE brand = 'Apple' ORDER BY product_price DESC LIMIT 3")

    return render_template("apple.html", categorized_products=categorized_products, best_products=best_products, cart_count=cart_count, wishlist_count=wishlist_count)


@app.route("/samsung")
@login_required
def view_samsung():
    """Render the Samsung products page"""
    user_id = session["user_id"]
    cart_count = get_cart_count(user_id)
    wishlist_count = get_wishlist_count(user_id)

    categories = db.execute("SELECT DISTINCT category FROM products WHERE brand = 'Samsung'")
    categorized_products = {}
    
    for category in categories:
        category_name = category['category']
        products = db.execute("SELECT * FROM products WHERE brand = 'Samsung' AND category = ?", category_name)
        categorized_products[category_name] = products

    best_products = db.execute("SELECT * FROM products WHERE brand = 'Samsung' ORDER BY product_price DESC LIMIT 3")

    return render_template("samsung.html", categorized_products=categorized_products, best_products=best_products, cart_count=cart_count, wishlist_count=wishlist_count)


@app.route("/xiaomi")
@login_required
def view_xiaomi():
    """Render the Xiaomi products page"""
    user_id = session["user_id"]
    cart_count = get_cart_count(user_id)
    wishlist_count = get_wishlist_count(user_id)

    categories = db.execute("SELECT DISTINCT category FROM products WHERE brand = 'Xiaomi'")
    categorized_products = {}
    
    for category in categories:
        category_name = category['category']
        products = db.execute("SELECT * FROM products WHERE brand = 'Xiaomi' AND category = ?", category_name)
        categorized_products[category_name] = products

    best_products = db.execute("SELECT * FROM products WHERE brand = 'Xiaomi' ORDER BY product_price DESC LIMIT 3")

    return render_template("xiaomi.html", categorized_products=categorized_products, best_products=best_products, cart_count=cart_count, wishlist_count=wishlist_count)
