from flask import Flask, request, render_template, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import random
import os
import razorpay
import requests

app = Flask(__name__)

# CORS configuration to allow requests from Webflow
CORS(app, 
     origins=["*"],  # In production, replace with your actual domain
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"],
     supports_credentials=False)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///orders.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Razorpay configuration
RAZORPAY_KEY_ID = 'rzp_test_w4GkDfNyQpZEXV'  # Replace with your actual key
RAZORPAY_KEY_SECRET = 'your_razorpay_secret_key'  # Replace with your actual secret
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# EmailJS configuration
EMAILJS_SERVICE_ID = 'service_qaw6x5d'
EMAILJS_TEMPLATE_ID = 'template_ju538la'
EMAILJS_PUBLIC_KEY = '43Xt0_HcajWF6jN7k'

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
    payment_status = db.Column(db.String(50), default='Pending')
    delivery_status = db.Column(db.String(50), default='Not Dispatched')
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_id = db.Column(db.String(100))  # Store Razorpay payment ID
    razorpay_order_id = db.Column(db.String(100))  # Store Razorpay order ID

    user = db.relationship('User', backref=db.backref('orders', lazy=True))
    product = db.relationship('Product', backref=db.backref('orders', lazy=True))

# ------------------- HELPER FUNCTIONS -------------------

def send_email_confirmation(customer_details, order_items, payment_id, total_amount):
    """Send email confirmation using EmailJS API"""
    try:
        # Prepare order items for email
        order_items_text = '\n'.join([
            f"{item['name']}{' (' + item['variant'] + ')' if item.get('variant') else ''} - Qty: {item['quantity']} - ₹{item['price']}"
            for item in order_items
        ])
        
        email_data = {
            'service_id': EMAILJS_SERVICE_ID,
            'template_id': EMAILJS_TEMPLATE_ID,
            'user_id': EMAILJS_PUBLIC_KEY,
            'template_params': {
                'to_name': customer_details['name'],
                'to_email': customer_details['email'],
                'customer_name': customer_details['name'],
                'customer_email': customer_details['email'],
                'customer_phone': customer_details['phone'],
                'customer_address': f"{customer_details['address']}, {customer_details['city']}, {customer_details['state']} - {customer_details['pincode']}",
                'payment_id': payment_id,
                'total_amount': f"{total_amount:.2f}",
                'order_items': order_items_text,
                'order_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        
        # Send email via EmailJS REST API
        response = requests.post(
            'https://api.emailjs.com/api/v1.0/email/send',
            json=email_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            print("Email sent successfully")
            return True
        else:
            print(f"Failed to send email: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False

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

# ------------------- RAZORPAY ROUTES -------------------

@app.route("/create-razorpay-order", methods=["POST"])
def create_razorpay_order():
    """Create a Razorpay order"""
    try:
        data = request.get_json()
        
        if not data:
            return {"error": "No data provided"}, 400
        
        # Validate required fields
        required_fields = ['amount', 'currency', 'customer_details', 'cart_items']
        for field in required_fields:
            if field not in data:
                return {"error": f"Missing required field: {field}"}, 400
        
        # Create Razorpay order
        order_data = {
            'amount': int(data['amount'] * 100),  # Amount in paise
            'currency': data.get('currency', 'INR'),
            'receipt': f"order_rcptid_{random.randint(1000, 9999)}",
            'notes': {
                'customer_name': data['customer_details']['name'],
                'customer_email': data['customer_details']['email'],
                'customer_phone': data['customer_details']['phone']
            }
        }
        
        razorpay_order = client.order.create(data=order_data)
        
        return {
            'success': True,
            'order_id': razorpay_order['id'],
            'amount': razorpay_order['amount'],
            'currency': razorpay_order['currency'],
            'key': RAZORPAY_KEY_ID
        }, 200
        
    except Exception as e:
        print(f"Error creating Razorpay order: {str(e)}")
        return {"error": f"Failed to create payment order: {str(e)}"}, 500

@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    """Verify Razorpay payment and create orders"""
    try:
        data = request.get_json()
        
        if not data:
            return {"error": "No data provided"}, 400
        
        # Verify payment signature
        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': data['razorpay_order_id'],
                'razorpay_payment_id': data['razorpay_payment_id'],
                'razorpay_signature': data['razorpay_signature']
            })
        except razorpay.errors.SignatureVerificationError:
            return {"error": "Payment verification failed"}, 400
        
        # Extract data
        customer_details = data['customer_details']
        cart_items = data['cart_items']
        payment_id = data['razorpay_payment_id']
        order_id = data['razorpay_order_id']
        
        # Create orders for each cart item
        created_orders = []
        total_amount = 0
        
        for item in cart_items:
            # Create or get user
            user = User.query.filter_by(email=customer_details['email']).first()
            if not user:
                # Generate unique username
                base_username = customer_details['name'].replace(' ', '').lower()
                username = base_username
                counter = 1
                while User.query.filter_by(username=username).first():
                    username = f"{base_username}{counter}"
                    counter += 1
                    
                user = User(
                    username=username,
                    email=customer_details['email'],
                    password_hash="web_order"
                )
                db.session.add(user)
                db.session.flush()
            
            # Create or get product
            product_name = item['name']
            if item.get('selectedVariant'):
                product_name += f" - {item['selectedVariant']['name']}"
                
            product = Product.query.filter_by(product_name=product_name).first()
            if not product:
                product = Product(
                    product_name=product_name,
                    sku=item.get('selectedVariant', {}).get('sku', f"WEB-{item['id']}"),
                    mrp=item['price'],
                    offer_price=item['price'],
                    in_stock=True,
                    stock_number=100
                )
                db.session.add(product)
                db.session.flush()
            
            # Create order
            item_total = item['price'] * item['quantity']
            total_amount += item_total
            
            order = Order(
                user_id=user.id,
                product_id=product.id,
                quantity=item['quantity'],
                status='Pending',
                price_paid=item_total,
                payment_status='Paid',
                delivery_status='Not Dispatched',
                payment_id=payment_id,
                razorpay_order_id=order_id
            )
            
            db.session.add(order)
            db.session.flush()
            
            created_orders.append({
                'order_id': order.id,
                'product_name': product_name,
                'variant_info': item.get('selectedVariant', {}).get('name') if item.get('selectedVariant') else None,
                'quantity': item['quantity'],
                'price_paid': item_total
            })
        
        db.session.commit()
        
        # Send email confirmation
        email_items = []
        for item in cart_items:
            email_items.append({
                'name': item['name'],
                'variant': item.get('selectedVariant', {}).get('name') if item.get('selectedVariant') else None,
                'quantity': item['quantity'],
                'price': item['price'] * item['quantity']
            })
        
        try:
            send_email_confirmation(customer_details, email_items, payment_id, total_amount)
        except Exception as email_error:
            print(f"Failed to send confirmation email: {email_error}")
            # Don't fail the order creation if email fails
        
        return {
            'success': True,
            'payment_id': payment_id,
            'orders': created_orders,
            'total_amount': total_amount,
            'message': 'Orders created successfully'
        }, 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error verifying payment: {str(e)}")
        return {"error": f"Failed to process payment: {str(e)}"}, 500

@app.route("/get-razorpay-key", methods=["GET"])
def get_razorpay_key():
    """Get Razorpay public key"""
    return {
        'key': RAZORPAY_KEY_ID
    }, 200

# ------------------- EXISTING ROUTES -------------------

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/create-order", methods=["POST"])
def create_order():
    """API endpoint to create orders from frontend (legacy endpoint)"""
    
    try:
        data = request.get_json()
        
        if not data:
            return {"error": "No data provided"}, 400
        
        # Validate required fields
        required_fields = ['customer_name', 'customer_email', 'product_name', 'quantity', 'price_paid']
        for field in required_fields:
            if not data.get(field):
                return {"error": f"Missing required field: {field}"}, 400
        
        # Create or get user
        user = User.query.filter_by(email=data['customer_email']).first()
        if not user:
            # Generate unique username
            base_username = data['customer_name'].replace(' ', '').lower()
            username = base_username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1
                
            user = User(
                username=username,
                email=data['customer_email'],
                password_hash="web_order"
            )
            db.session.add(user)
            db.session.flush()
        
        # Create or get product
        product_name = data['product_name']
        if data.get('variant_info'):
            product_name += f" - {data['variant_info']}"
            
        product = Product.query.filter_by(product_name=product_name).first()
        if not product:
            product = Product(
                product_name=product_name,
                sku=data.get('sku', f"WEB-{data.get('external_product_id', 'UNKNOWN')}"),
                mrp=data['price_paid'] / data['quantity'],
                offer_price=data['price_paid'] / data['quantity'],
                in_stock=True,
                stock_number=100
            )
            db.session.add(product)
            db.session.flush()
        
        # Create order
        order = Order(
            user_id=user.id,
            product_id=product.id,
            quantity=data['quantity'],
            status='Pending',
            price_paid=data['price_paid'],
            payment_status=data.get('payment_status', 'Paid'),
            delivery_status=data.get('delivery_status', 'Not Dispatched'),
            payment_id=data.get('payment_id')
        )
        
        db.session.add(order)
        db.session.commit()
        
        response_data = {
            "success": True,
            "order_id": order.id,
            "customer_name": data['customer_name'],
            "customer_email": data['customer_email'],
            "product_name": product_name,
            "variant_info": data.get('variant_info'),
            "quantity": data['quantity'],
            "price_paid": data['price_paid'],
            "payment_id": data.get('payment_id'),
            "payment_status": order.payment_status,
            "delivery_status": order.delivery_status,
            "order_date": order.order_date.isoformat()
        }
        
        return response_data, 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating order: {str(e)}")
        return {"error": f"Failed to create order: {str(e)}"}, 500

@app.route("/orders")
def view_orders():
    try:
        orders = Order.query.order_by(Order.id.desc()).all()
        return render_template("orders.html", orders=orders[::-1])
    except Exception as e:
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
