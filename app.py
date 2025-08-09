from flask import Flask, request, render_template, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import random
import os
import razorpay
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# CORS configuration to allow requests from Webflow
CORS(app, 
     origins=["*"],  # In production, replace with your actual domain
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"],
     supports_credentials=False)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///orders.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Razorpay Configuration
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID', 'rzp_test_w4GkDfNyQpZEXV')  # Your test key
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', 'your_secret_key_here')  # Set this in environment

# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Email Configuration (Optional - for order confirmations)
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')

db = SQLAlchemy(app)

# ------------------- MODELS -------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    phone = db.Column(db.String(15))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    pincode = db.Column(db.String(10))
    country = db.Column(db.String(50), default='India')
    company = db.Column(db.String(200))
    gst_number = db.Column(db.String(15))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(200))
    sku = db.Column(db.String(50))
    mrp = db.Column(db.Float)
    offer_price = db.Column(db.Float)
    in_stock = db.Column(db.Boolean, default=True)
    stock_number = db.Column(db.Integer)
    external_product_id = db.Column(db.String(50))  # For Webflow CMS ID

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    status = db.Column(db.String(50), default='Pending')
    price_paid = db.Column(db.Float, default=0.0)
    payment_status = db.Column(db.String(50), default='Pending')  # Paid, Pending, Failed
    delivery_status = db.Column(db.String(50), default='Not Dispatched')  # Not Dispatched, In Transit, Delivered, Returned
    payment_id = db.Column(db.String(100))  # Razorpay payment ID
    razorpay_order_id = db.Column(db.String(100))  # Razorpay order ID
    variant_info = db.Column(db.String(200))  # Product variant information
    order_date = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('orders', lazy=True))
    product = db.relationship('Product', backref=db.backref('orders', lazy=True))

# ------------------- HELPER FUNCTIONS -------------------

def send_order_confirmation_email(customer_details, orders, payment_id):
    """Send order confirmation email to customer"""
    try:
        if not SMTP_USERNAME or not SMTP_PASSWORD:
            print("Email configuration not set, skipping email")
            return
            
        msg = MIMEMultipart()
        msg['From'] = SMTP_USERNAME
        msg['To'] = customer_details['email']
        msg['Subject'] = f"Order Confirmation - Payment ID: {payment_id}"
        
        # Create email body
        total_amount = sum(order.price_paid for order in orders)
        order_items = "\n".join([
            f"- {order.product.product_name}" + 
            (f" ({order.variant_info})" if order.variant_info else "") + 
            f" - Qty: {order.quantity} - ₹{order.price_paid}"
            for order in orders
        ])
        
        body = f"""
Dear {customer_details['name']},

Thank you for your order! Here are the details:

Order Details:
{order_items}

Total Amount: ₹{total_amount}
Payment ID: {payment_id}
Order Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Delivery Address:
{customer_details['address']}
{customer_details['city']}, {customer_details['state']} - {customer_details['pincode']}

We will contact you within 24 hours with further details.

Thank you for your business!

Best regards,
Your Store Team
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        text = msg.as_string()
        server.sendmail(SMTP_USERNAME, customer_details['email'], text)
        server.quit()
        
        print(f"Order confirmation email sent to {customer_details['email']}")
        
    except Exception as e:
        print(f"Failed to send email: {str(e)}")

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
                    password_hash="hash",
                    phone=f"90000{i:05d}",
                    address=f"Address {i+1}",
                    city="Mumbai",
                    state="Maharashtra",
                    pincode="400001"
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
                    stock_number=random.randint(1, 100),
                    external_product_id=f"webflow_{i+1}"
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
    """Create Razorpay order for payment"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Validate required fields
        required_fields = ['amount', 'currency', 'customer_details', 'cart_items']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        amount = int(data['amount'] * 100)  # Convert to paise
        currency = data['currency']
        customer_details = data['customer_details']
        cart_items = data['cart_items']
        
        # Create Razorpay order
        razorpay_order = razorpay_client.order.create({
            'amount': amount,
            'currency': currency,
            'payment_capture': 1,  # Auto capture
            'notes': {
                'customer_name': customer_details.get('name', ''),
                'customer_email': customer_details.get('email', ''),
                'customer_phone': customer_details.get('phone', ''),
                'items_count': len(cart_items)
            }
        })
        
        return jsonify({
            'success': True,
            'order_id': razorpay_order['id'],
            'amount': razorpay_order['amount'],
            'currency': razorpay_order['currency'],
            'key': RAZORPAY_KEY_ID
        }), 200
        
    except Exception as e:
        print(f"Error creating Razorpay order: {str(e)}")
        return jsonify({"error": f"Failed to create payment order: {str(e)}"}), 500

@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    """Verify Razorpay payment and create orders"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Verify payment signature
        payment_id = data.get('razorpay_payment_id')
        order_id = data.get('razorpay_order_id')
        signature = data.get('razorpay_signature')
        customer_details = data.get('customer_details')
        cart_items = data.get('cart_items')
        
        if not all([payment_id, order_id, signature, customer_details, cart_items]):
            return jsonify({"error": "Missing payment verification data"}), 400
        
        # Verify signature
        try:
            razorpay_client.utility.verify_payment_signature({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature
            })
        except Exception as e:
            print(f"Payment verification failed: {str(e)}")
            return jsonify({"error": "Payment verification failed"}), 400
        
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
                password_hash="web_order",
                phone=customer_details.get('phone', ''),
                address=customer_details.get('address', ''),
                city=customer_details.get('city', ''),
                state=customer_details.get('state', ''),
                pincode=customer_details.get('pincode', ''),
                country=customer_details.get('country', 'India'),
                company=customer_details.get('company', ''),
                gst_number=customer_details.get('gstNumber', '')
            )
            db.session.add(user)
            db.session.flush()  # Get the user ID
        else:
            # Update user details
            user.phone = customer_details.get('phone', user.phone)
            user.address = customer_details.get('address', user.address)
            user.city = customer_details.get('city', user.city)
            user.state = customer_details.get('state', user.state)
            user.pincode = customer_details.get('pincode', user.pincode)
            user.country = customer_details.get('country', user.country)
            user.company = customer_details.get('company', user.company)
            user.gst_number = customer_details.get('gstNumber', user.gst_number)
        
        created_orders = []
        
        # Create orders for each cart item
        for item in cart_items:
            # Create or get product
            product_name = item['name']
            if item.get('selectedVariant'):
                product_name += f" - {item['selectedVariant']['name']}"
                
            product = Product.query.filter_by(
                product_name=product_name,
                external_product_id=str(item['id'])
            ).first()
            
            if not product:
                product = Product(
                    product_name=product_name,
                    sku=item.get('selectedVariant', {}).get('sku', f"WEB-{item['id']}"),
                    mrp=item['price'],
                    offer_price=item['price'],
                    in_stock=True,
                    stock_number=100,
                    external_product_id=str(item['id'])
                )
                db.session.add(product)
                db.session.flush()
            
            # Create order
            order = Order(
                user_id=user.id,
                product_id=product.id,
                quantity=item['quantity'],
                status='Pending',
                price_paid=item['price'] * item['quantity'],
                payment_status='Paid',
                delivery_status='Not Dispatched',
                payment_id=payment_id,
                razorpay_order_id=order_id,
                variant_info=item.get('selectedVariant', {}).get('name', None)
            )
            
            db.session.add(order)
            created_orders.append(order)
        
        db.session.commit()
        
        # Send confirmation email
        try:
            send_order_confirmation_email(customer_details, created_orders, payment_id)
        except Exception as email_error:
            print(f"Email sending failed: {str(email_error)}")
            # Don't fail the entire process if email fails
        
        # Prepare response
        order_results = []
        for order in created_orders:
            order_results.append({
                "order_id": order.id,
                "product_name": order.product.product_name,
                "variant_info": order.variant_info,
                "quantity": order.quantity,
                "price_paid": order.price_paid,
                "payment_status": order.payment_status,
                "delivery_status": order.delivery_status
            })
        
        return jsonify({
            "success": True,
            "payment_id": payment_id,
            "orders": order_results,
            "customer_name": customer_details['name'],
            "customer_email": customer_details['email']
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error verifying payment: {str(e)}")
        return jsonify({"error": f"Failed to verify payment: {str(e)}"}), 500

# ------------------- EXISTING ROUTES -------------------

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/create-order", methods=["POST"])
def create_order():
    """API endpoint to create orders from frontend (Legacy support)"""
    
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
            payment_id=data.get('payment_id'),
            variant_info=data.get('variant_info')
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
