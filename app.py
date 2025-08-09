from flask import Flask, request, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import random
import os

app = Flask(__name__)
CORS(app)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///orders.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ------------------- MODELS -------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(200))
    sku = db.Column(db.String(50))
    mrp = db.Column(db.Float)
    offer_price = db.Column(db.Float)
    in_stock = db.Column(db.Boolean, default=True)
    stock_number = db.Column(db.Integer)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    status = db.Column(db.String(50), default='Pending')
    price_paid = db.Column(db.Float, default=0.0)
    payment_status = db.Column(db.String(50), default='Pending')  # Paid, Pending, Failed
    delivery_status = db.Column(db.String(50), default='Not Dispatched')  # Not Dispatched, In Transit, Delivered, Returned
    order_date = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('orders', lazy=True))
    product = db.relationship('Product', backref=db.backref('orders', lazy=True))

# ------------------- DATABASE INITIALIZATION -------------------

def init_database():
    """Initialize database tables and sample data if needed"""
    try:
        # Create all tables
        db.create_all()
        
        # Check if we need to populate sample data
        if User.query.count() == 0 and Product.query.count() == 0:
            # Create sample users
            for i in range(10):
                user = User(
                    username=f"user{i+1}",
                    email=f"user{i+1}@mail.com",
                    password_hash="hash"
                )
                db.session.add(user)

            # Create sample products
            for i in range(10):
                product = Product(
                    product_name=f"Product {i+1}",
                    sku=f"P{i+1:03}",
                    mrp=random.randint(100, 1000),
                    offer_price=random.randint(50, 900),
                    in_stock=True,
                    stock_number=random.randint(1, 100)
                )
                db.session.add(product)

            db.session.commit()

            # Create sample orders
            users = User.query.all()
            products = Product.query.all()
            statuses = ["Pending", "Shipped", "Delivered", "Cancelled"]
            payments = ["Paid", "Pending", "Failed"]
            deliveries = ["Not Dispatched", "In Transit", "Delivered", "Returned"]

            for i in range(10):
                order = Order(
                    user=random.choice(users),
                    product=random.choice(products),
                    quantity=random.randint(1, 5),
                    status=random.choice(statuses),
                    price_paid=random.randint(100, 1000),
                    payment_status=random.choice(payments),
                    delivery_status=random.choice(deliveries)
                )
                db.session.add(order)

            db.session.commit()
            print("Database initialized with sample data")
        else:
            print("Database already contains data")
            
    except Exception as e:
        print(f"Database initialization error: {e}")
        db.session.rollback()

# Initialize database when app starts
with app.app_context():
    init_database()

# ------------------- ROUTES -------------------

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/orders")
def view_orders():
    try:
        orders = Order.query.order_by(Order.id.desc()).all()
        return render_template("orders.html", orders=orders[::-1])
    except Exception as e:
        # If tables don't exist, try to initialize database
        with app.app_context():
            init_database()
        orders = Order.query.order_by(Order.id.desc()).all()
        return render_template("orders.html", orders=orders[::-1])

@app.route("/order/<int:order_id>/update", methods=["POST"])
def update_order_status(order_id):
    new_status = request.form.get("status")
    order = Order.query.get_or_404(order_id)
    order.status = new_status
    db.session.commit()
    return redirect(url_for('view_orders'))

@app.route("/order/<int:order_id>/edit", methods=["GET", "POST"])
def edit_order(order_id):
    order = Order.query.get_or_404(order_id)
    if request.method == "POST":
        order.quantity = int(request.form.get("quantity", 1))
        order.status = request.form.get("status")
        order.price_paid = float(request.form.get("price_paid", 0))
        order.payment_status = request.form.get("payment_status")
        order.delivery_status = request.form.get("delivery_status")
        db.session.commit()
        return redirect(url_for("view_orders"))
    return render_template("edit_order.html", order=order)

@app.route("/init")
def generate_data():
    """Manual endpoint to reinitialize data if needed"""
    with app.app_context():
        init_database()
    return redirect(url_for('view_orders'))

@app.route("/health")
def health_check():
    """Health check endpoint for deployment"""
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        return {"status": "healthy", "database": "connected"}, 200
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500

# ------------------- ERROR HANDLERS -------------------

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return "Internal server error", 500

@app.errorhandler(404)
def not_found(error):
    return "Page not found", 404

# ------------------- MAIN -------------------

if __name__ == "__main__":
    app.run(debug=True)
