from flask import Flask, request, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta
import random
import os
import requests
import json

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

# Shiprocket configuration
SHIPROCKET_CONFIG = {
    'email': 'harshavardan423@gmail.com',
    'password': '00C6tsxxEqC2^!H4',
    'baseUrl': 'https://apiv2.shiprocket.in/v1/external',
    'token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOjc1MTQ3OTAsInNvdXJjZSI6InNyLWF1dGgtaW50IiwiZXhwIjoxNzU1OTQwNjEwLCJqdGkiOiJCWHdFb0RmU2VGS1gzSmphIiwiaWF0IjoxNzU1MDc2NjEwLCJpc3MiOiJodHRwczovL3NyLWF1dGguc2hpcHJvY2tldC5pbi9hdXRob3JpemUvdXNlciIsIm5iZiI6MTc1NTA3NjYxMCwiY2lkIjo3Mjc4NzQyLCJ0YyI6MzYwLCJ2ZXJib3NlIjpmYWxzZSwidmVuZG9yX2lkIjowLCJ2ZW5kb3JfY29kZSI6IiJ9.cbVV6TRyMeNhP1Fi7_527nemHWqfm1_9dNP2x1Ar6bY',
    'tokenExpiry': datetime(2025, 8, 21)
}

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
    
    # Customer details
    customer_name = db.Column(db.String(200))
    customer_phone = db.Column(db.String(20))
    customer_company = db.Column(db.String(200))
    gst_number = db.Column(db.String(20))
    
    # Address details
    billing_address = db.Column(db.Text)
    billing_city = db.Column(db.String(100))
    billing_state = db.Column(db.String(100))
    billing_pincode = db.Column(db.String(10))
    billing_country = db.Column(db.String(100))
    
    shipping_address = db.Column(db.Text)
    shipping_city = db.Column(db.String(100))
    shipping_state = db.Column(db.String(100))
    shipping_pincode = db.Column(db.String(10))
    shipping_country = db.Column(db.String(100))
    
    # Payment details
    payment_id = db.Column(db.String(100))
    
    # Shiprocket integration fields
    shiprocket_order_id = db.Column(db.String(100), nullable=True)
    shiprocket_shipment_id = db.Column(db.String(100), nullable=True)
    shiprocket_status = db.Column(db.String(100), nullable=True)
    shiprocket_tracking_url = db.Column(db.String(500), nullable=True)

    user = db.relationship('User', backref=db.backref('orders', lazy=True))
    product = db.relationship('Product', backref=db.backref('orders', lazy=True))

# ------------------- SHIPROCKET INTEGRATION -------------------

def get_shiprocket_token():
    """Get or refresh Shiprocket token"""
    try:
        # Check if token is still valid (with some buffer time)
        if datetime.now() < SHIPROCKET_CONFIG['tokenExpiry']:
            return SHIPROCKET_CONFIG['token']
        
        # If token is expired, get a new one
        auth_url = f"{SHIPROCKET_CONFIG['baseUrl']}/auth/login"
        auth_payload = {
            'email': SHIPROCKET_CONFIG['email'],
            'password': SHIPROCKET_CONFIG['password']
        }
        
        response = requests.post(auth_url, json=auth_payload)
        response.raise_for_status()
        
        auth_data = response.json()
        new_token = auth_data.get('token')
        
        if new_token:
            SHIPROCKET_CONFIG['token'] = new_token
            # Update token expiry (tokens typically last 10 days)
            SHIPROCKET_CONFIG['tokenExpiry'] = datetime.now().replace(hour=23, minute=59, second=59) + timedelta(days=9)
            return new_token
        else:
            raise Exception("No token in auth response")
            
    except Exception as e:
        print(f"Error getting Shiprocket token: {e}")
        return None

def check_shiprocket_account():
    """Check Shiprocket account setup and pickup locations"""
    try:
        token = get_shiprocket_token()
        if not token:
            return None, "Failed to get Shiprocket token"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        # Check pickup locations
        pickup_url = f"{SHIPROCKET_CONFIG['baseUrl']}/settings/company/pickup"
        response = requests.get(pickup_url, headers=headers)
        
        print(f"Pickup locations API response: {response.status_code}")
        print(f"Pickup locations data: {response.text}")
        
        if response.status_code == 200:
            pickup_data = response.json()
            return pickup_data, None
        else:
            return None, f"Failed to get pickup locations: {response.status_code} - {response.text}"
            
    except Exception as e:
        return None, f"Error checking Shiprocket account: {str(e)}"

def create_shiprocket_order(order_data):
    """Create order in Shiprocket"""
    try:
        token = get_shiprocket_token()
        if not token:
            return None, "Failed to get Shiprocket token"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        # First, check account setup
        pickup_data, pickup_error = check_shiprocket_account()
        if pickup_error:
            print(f"Pickup location check failed: {pickup_error}")
            # Continue anyway, but log the issue
        else:
            print(f"Available pickup locations: {pickup_data}")
        
        # Validate required address fields
        required_fields = ['billing_address', 'billing_city', 'billing_pincode', 'billing_state']
        for field in required_fields:
            if not order_data.get(field):
                return None, f"Missing required field: {field}"
        
        # Try different pickup location values
        pickup_locations_to_try = ["Primary", "primary", "Default", "default"]
        
        for pickup_location in pickup_locations_to_try:
            # Prepare Shiprocket order payload
            shiprocket_payload = {
                "order_id": f"ORDER-{order_data['order_id']}-{int(datetime.now().timestamp())}",
                "order_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "pickup_location": pickup_location,
                "billing_customer_name": order_data['customer_name'],
                "billing_last_name": "",
                "billing_address": order_data['billing_address'],
                "billing_city": order_data['billing_city'],
                "billing_pincode": str(order_data['billing_pincode']),
                "billing_state": order_data['billing_state'],
                "billing_country": order_data.get('billing_country', 'India'),
                "billing_email": order_data['customer_email'],
                "billing_phone": order_data.get('customer_phone', '0000000000'),
                "shipping_is_billing": True,
                "shipping_customer_name": order_data['customer_name'],
                "shipping_last_name": "",
                "shipping_address": order_data.get('shipping_address', order_data['billing_address']),
                "shipping_city": order_data.get('shipping_city', order_data['billing_city']),
                "shipping_pincode": str(order_data.get('shipping_pincode', order_data['billing_pincode'])),
                "shipping_country": order_data.get('shipping_country', order_data.get('billing_country', 'India')),
                "shipping_state": order_data.get('shipping_state', order_data['billing_state']),
                "shipping_email": order_data['customer_email'],
                "shipping_phone": order_data.get('customer_phone', '0000000000'),
                "order_items": [{
                    "name": order_data['product_name'],
                    "sku": order_data.get('sku', 'DEFAULT-SKU'),
                    "units": order_data['quantity'],
                    "selling_price": order_data['price_paid'] / order_data['quantity'],
                    "discount": 0,
                    "tax": 0,
                    "hsn": order_data.get('hsn', '000000')  # Default HSN code
                }],
                "payment_method": "Prepaid" if order_data.get('payment_status') == 'Paid' else "COD",
                "shipping_charges": 0,
                "giftwrap_charges": 0,
                "transaction_charges": 0,
                "total_discount": 0,
                "sub_total": order_data['price_paid'],
                "length": order_data.get('length', 10),
                "breadth": order_data.get('breadth', 10),
                "height": order_data.get('height', 10),
                "weight": order_data.get('weight', 0.5)
            }
            
            print(f"Trying pickup location: {pickup_location}")
            print(f"Shiprocket payload: {json.dumps(shiprocket_payload, indent=2)}")
            
            # Create order in Shiprocket
            create_url = f"{SHIPROCKET_CONFIG['baseUrl']}/orders/create/adhoc"
            response = requests.post(create_url, json=shiprocket_payload, headers=headers)
            
            print(f"Shiprocket response status: {response.status_code}")
            print(f"Shiprocket response: {response.text}")
            
            if response.status_code == 200:
                shiprocket_response = response.json()
                return shiprocket_response, None
            elif response.status_code != 400:
                # If it's not a 400 error, don't try other pickup locations
                error_message = f"Shiprocket API error: {response.status_code} - {response.text}"
                print(error_message)
                return None, error_message
            
            # If 400 error, try next pickup location
            print(f"400 error with pickup location '{pickup_location}', trying next...")
        
        # If all pickup locations failed
        error_message = f"All pickup locations failed. Last response: {response.status_code} - {response.text}"
        print(error_message)
        return None, error_message
            
    except Exception as e:
        error_message = f"Error creating Shiprocket order: {str(e)}"
        print(error_message)
        return None, error_message

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
                    delivery_status=random.choice(deliveries),
                    customer_name=f"Customer {i+1}",
                    customer_phone=f"9876543{i:03d}",
                    billing_address=f"Address {i+1}, Street {i+1}",
                    billing_city=f"City {i+1}",
                    billing_state=f"State {i+1}",
                    billing_pincode=f"{110001 + i}",
                    billing_country="India"
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

@app.route("/shiprocket/debug")
def debug_shiprocket():
    """Debug endpoint to check Shiprocket account setup"""
    pickup_data, error = check_shiprocket_account()
    if error:
        return {"error": error}, 400
    return {"pickup_locations": pickup_data}, 200

@app.route("/create-order", methods=["POST"])
def create_order():
    """API endpoint to create orders from frontend"""
    
    try:
        data = request.get_json()
        
        if not data:
            return {"error": "No data provided"}, 400
        
        print(f"Received order data: {json.dumps(data, indent=2)}")
        
        # Validate required fields
        required_fields = ['customer_name', 'customer_email', 'product_name', 'quantity', 'price_paid']
        for field in required_fields:
            if not data.get(field):
                return {"error": f"Missing required field: {field}"}, 400
        
        # Validate address fields
        address_fields = ['address', 'city', 'state', 'pincode']
        for field in address_fields:
            if not data.get(field):
                return {"error": f"Missing required address field: {field}"}, 400
        
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
                password_hash="web_order"  # Placeholder for web orders
            )
            db.session.add(user)
            db.session.flush()  # Get the user ID
        
        # Create or get product
        product_name = data['product_name']
        if data.get('variant_info'):
            product_name += f" - {data['variant_info']}"
            
        product = Product.query.filter_by(product_name=product_name).first()
        if not product:
            product = Product(
                product_name=product_name,
                sku=data.get('sku', f"WEB-{data.get('external_product_id', 'UNKNOWN')}"),
                mrp=data['price_paid'] / data['quantity'],  # Assuming price_paid is total
                offer_price=data['price_paid'] / data['quantity'],
                in_stock=True,
                stock_number=100  # Default stock
            )
            db.session.add(product)
            db.session.flush()  # Get the product ID
        
        # Create order with all details
        order = Order(
            user_id=user.id,
            product_id=product.id,
            quantity=data['quantity'],
            status='Pending',
            price_paid=data['price_paid'],
            payment_status=data.get('payment_status', 'Paid'),
            delivery_status=data.get('delivery_status', 'Not Dispatched'),
            # Customer details
            customer_name=data['customer_name'],
            customer_phone=data.get('phone', data.get('customer_phone', '0000000000')),
            customer_company=data.get('company', ''),
            gst_number=data.get('gstNumber', ''),
            # Billing address
            billing_address=data['address'],
            billing_city=data['city'],
            billing_state=data['state'],
            billing_pincode=str(data['pincode']),
            billing_country=data.get('country', 'India'),
            # Shipping address (same as billing by default)
            shipping_address=data.get('shipping_address', data['address']),
            shipping_city=data.get('shipping_city', data['city']),
            shipping_state=data.get('shipping_state', data['state']),
            shipping_pincode=str(data.get('shipping_pincode', data['pincode'])),
            shipping_country=data.get('shipping_country', data.get('country', 'India')),
            # Payment details
            payment_id=data.get('payment_id', '')
        )
        
        db.session.add(order)
        db.session.commit()
        
        # Prepare data for Shiprocket order creation
        shiprocket_order_data = {
            'order_id': order.id,
            'customer_name': data['customer_name'],
            'customer_email': data['customer_email'],
            'customer_phone': data.get('phone', data.get('customer_phone', '0000000000')),
            'product_name': product_name,
            'sku': product.sku,
            'quantity': data['quantity'],
            'price_paid': data['price_paid'],
            'payment_status': data.get('payment_status', 'Paid'),
            # Address fields from the order
            'billing_address': order.billing_address,
            'billing_city': order.billing_city,
            'billing_pincode': order.billing_pincode,
            'billing_state': order.billing_state,
            'billing_country': order.billing_country,
            'shipping_address': order.shipping_address,
            'shipping_city': order.shipping_city,
            'shipping_pincode': order.shipping_pincode,
            'shipping_state': order.shipping_state,
            'shipping_country': order.shipping_country,
            # Product dimensions and weight
            'length': data.get('length', 10),
            'breadth': data.get('breadth', 10),
            'height': data.get('height', 10),
            'weight': data.get('weight', 0.5),
            'hsn': data.get('hsn', '000000')
        }
        
        # Create Shiprocket order
        shiprocket_response, shiprocket_error = create_shiprocket_order(shiprocket_order_data)
        
        # Update order with Shiprocket details
        if shiprocket_response and 'order_id' in shiprocket_response:
            order.shiprocket_order_id = shiprocket_response.get('order_id')
            order.shiprocket_shipment_id = shiprocket_response.get('shipment_id')
            order.shiprocket_status = 'Created'
            if 'tracking_url' in shiprocket_response:
                order.shiprocket_tracking_url = shiprocket_response['tracking_url']
            db.session.commit()
            print(f"Shiprocket order created successfully: {shiprocket_response}")
        else:
            order.shiprocket_status = f'Failed: {shiprocket_error}'
            db.session.commit()
            print(f"Failed to create Shiprocket order: {shiprocket_error}")
        
        # Return order details
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
            "order_date": order.order_date.isoformat(),
            "shiprocket_order_id": order.shiprocket_order_id,
            "shiprocket_status": order.shiprocket_status,
            "shiprocket_tracking_url": order.shiprocket_tracking_url,
            "billing_address": {
                "address": order.billing_address,
                "city": order.billing_city,
                "state": order.billing_state,
                "pincode": order.billing_pincode,
                "country": order.billing_country
            }
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
        # Basic order information
        order.quantity = int(request.form.get("quantity", 1))
        order.status = request.form.get("status")
        order.price_paid = float(request.form.get("price_paid", 0))
        order.payment_status = request.form.get("payment_status")
        order.delivery_status = request.form.get("delivery_status")
        
        # Customer details
        order.customer_name = request.form.get("customer_name", "")
        order.customer_phone = request.form.get("customer_phone", "")
        order.customer_company = request.form.get("customer_company", "")
        order.gst_number = request.form.get("gst_number", "")
        
        # Billing address
        order.billing_address = request.form.get("billing_address", "")
        order.billing_city = request.form.get("billing_city", "")
        order.billing_state = request.form.get("billing_state", "")
        order.billing_pincode = request.form.get("billing_pincode", "")
        order.billing_country = request.form.get("billing_country", "")
        
        # Shipping address
        order.shipping_address = request.form.get("shipping_address", "")
        order.shipping_city = request.form.get("shipping_city", "")
        order.shipping_state = request.form.get("shipping_state", "")
        order.shipping_pincode = request.form.get("shipping_pincode", "")
        order.shipping_country = request.form.get("shipping_country", "")
        
        # Payment details
        order.payment_id = request.form.get("payment_id", "")
        
        try:
            db.session.commit()
            return redirect(url_for("view_orders"))
        except Exception as e:
            db.session.rollback()
            # You might want to add flash messaging here for error handling
            print(f"Error updating order: {e}")
            return redirect(url_for("edit_order", order_id=order_id))
            
    return render_template("edit_order.html", order=order)

@app.route("/shiprocket/sync/<int:order_id>", methods=["POST"])
def sync_shiprocket_order(order_id):
    """Manual sync of Shiprocket order status"""
    try:
        order = Order.query.get_or_404(order_id)
        
        if not order.shiprocket_order_id:
            return {"error": "No Shiprocket order ID found"}, 400
            
        token = get_shiprocket_token()
        if not token:
            return {"error": "Failed to get Shiprocket token"}, 500
            
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        # Get order details from Shiprocket
        track_url = f"{SHIPROCKET_CONFIG['baseUrl']}/orders/show/{order.shiprocket_order_id}"
        response = requests.get(track_url, headers=headers)
        
        if response.status_code == 200:
            shiprocket_data = response.json()
            
            # Update order with latest Shiprocket data
            if 'data' in shiprocket_data:
                order_data = shiprocket_data['data']
                order.shiprocket_status = order_data.get('status', order.shiprocket_status)
                
                # Update delivery status based on Shiprocket status
                shiprocket_status = order_data.get('status', '').lower()
                if 'delivered' in shiprocket_status:
                    order.delivery_status = 'Delivered'
                elif 'shipped' in shiprocket_status or 'transit' in shiprocket_status:
                    order.delivery_status = 'In Transit'
                elif 'dispatched' in shiprocket_status:
                    order.delivery_status = 'In Transit'
                    
                db.session.commit()
                
            return {"success": True, "data": shiprocket_data}, 200
        else:
            return {"error": f"Shiprocket API error: {response.status_code}"}, 400
            
    except Exception as e:
        return {"error": f"Sync failed: {str(e)}"}, 500

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
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

