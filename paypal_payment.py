import os
import logging
import uuid
import json
from datetime import datetime
import requests
from dotenv import load_dotenv
from database import update_user_credits, get_user_credits

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# PayPal API credentials
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_CLIENT_SECRET = os.getenv('PAYPAL_CLIENT_SECRET')
PAYPAL_ENVIRONMENT = os.getenv('PAYPAL_MODE', 'live')  # 'sandbox' or 'live'

# PayPal API URLs
if PAYPAL_ENVIRONMENT == 'sandbox':
    PAYPAL_API_BASE = 'https://api-m.sandbox.paypal.com'
else:
    PAYPAL_API_BASE = 'https://api-m.paypal.com'

# Credit packages available for purchase
CREDIT_PACKAGES = {
    'basic': {'credits': 50, 'price': 5.00, 'currency': 'USD', 'name': 'Paquete Básico'},
    'standard': {'credits': 150, 'price': 10.00, 'currency': 'USD', 'name': 'Paquete Estándar'},
    'premium': {'credits': 500, 'price': 25.00, 'currency': 'USD', 'name': 'Paquete Premium'}
}

# Database functions for payment tracking
def init_payment_database():
    """Initialize payment-related database tables."""
    try:
        import sqlite3
        from database import DATABASE_PATH
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Create payments table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            currency TEXT,
            credits INTEGER,
            status TEXT,
            paypal_order_id TEXT,
            paypal_payment_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        
        conn.commit()
        logger.info("Payment database tables initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing payment database: {e}")

def create_payment_record(user_id, package_id, payment_id=None):
    """Create a payment record in the database."""
    try:
        import sqlite3
        from database import DATABASE_PATH
        
        if package_id not in CREDIT_PACKAGES:
            logger.error(f"Invalid package ID: {package_id}")
            return None
            
        package = CREDIT_PACKAGES[package_id]
        payment_id = payment_id or str(uuid.uuid4())
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO payments (payment_id, user_id, amount, currency, credits, status) VALUES (?, ?, ?, ?, ?, ?)",
            (payment_id, user_id, package['price'], package['currency'], package['credits'], 'pending')
        )
        
        conn.commit()
        logger.info(f"Created payment record {payment_id} for user {user_id}")
        return payment_id
    except Exception as e:
        logger.error(f"Error creating payment record: {e}")
        return None

def update_payment_status(payment_id, status, paypal_order_id=None, paypal_payment_id=None):
    """Update payment status in the database."""
    try:
        import sqlite3
        from database import DATABASE_PATH
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        update_fields = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [status]
        
        if paypal_order_id:
            update_fields.append("paypal_order_id = ?")
            params.append(paypal_order_id)
            
        if paypal_payment_id:
            update_fields.append("paypal_payment_id = ?")
            params.append(paypal_payment_id)
            
        params.append(payment_id)
        
        cursor.execute(
            f"UPDATE payments SET {', '.join(update_fields)} WHERE payment_id = ?",
            params
        )
        
        conn.commit()
        logger.info(f"Updated payment {payment_id} status to {status}")
        return True
    except Exception as e:
        logger.error(f"Error updating payment status: {e}")
        return False

def get_payment_info(payment_id):
    """Get payment information from the database."""
    try:
        import sqlite3
        from database import DATABASE_PATH
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,))
        payment = cursor.fetchone()
        
        if payment:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, payment))
        return None
    except Exception as e:
        logger.error(f"Error getting payment info: {e}")
        return None

# PayPal API functions
def get_paypal_access_token():
    """Get PayPal OAuth access token."""
    try:
        url = f"{PAYPAL_API_BASE}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US"
        }
        data = {"grant_type": "client_credentials"}
        
        response = requests.post(
            url, 
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            headers=headers,
            data=data
        )
        
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            logger.error(f"Error getting PayPal access token: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Exception getting PayPal access token: {e}")
        return None

def create_paypal_payment_link(user_id, package_id):
    """Create a PayPal payment link for a credit package."""
    try:
        if package_id not in CREDIT_PACKAGES:
            logger.error(f"Invalid package ID: {package_id}")
            return None
            
        package = CREDIT_PACKAGES[package_id]
        payment_id = create_payment_record(user_id, package_id)
        
        if not payment_id:
            return None
            
        # Get PayPal access token
        access_token = get_paypal_access_token()
        if not access_token:
            return None
        
        # Create PayPal order
        url = f"{PAYPAL_API_BASE}/v2/checkout/orders"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": payment_id,
                    "description": f"{package['name']} - {package['credits']} créditos para CreaVisionBot",
                    "custom_id": f"{user_id}:{payment_id}:{package_id}:{package['credits']}",
                    "amount": {
                        "currency_code": package['currency'],
                        "value": str(package['price'])
                    }
                }
            ],
            "application_context": {
                "brand_name": "CreaVisionBot",
                "landing_page": "BILLING",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "PAY_NOW",
                "return_url": f"https://t.me/CreaVisionBot?start=payment_{payment_id}",
                "cancel_url": f"https://t.me/CreaVisionBot?start=cancel_{payment_id}",
                "payment_method": {
                    "payer_selected": "PAYPAL",
                    "payee_preferred": "IMMEDIATE_PAYMENT_REQUIRED"
                }
            }
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            order_data = response.json()
            order_id = order_data.get("id")
            
            # Update payment record with PayPal order ID
            update_payment_status(payment_id, 'order_created', paypal_order_id=order_id)
            
            # Find the approve link
            checkout_url = None
            for link in order_data.get("links", []):
                if link.get("rel") == "approve":
                    checkout_url = link.get("href")
                    break
            
            if checkout_url:
                logger.info(f"Created PayPal payment link for user {user_id}, payment {payment_id}")
                return {
                    "payment_id": payment_id,
                    "checkout_url": checkout_url,
                    "order_id": order_id
                }
        
        logger.error(f"Error creating PayPal order: {response.text}")
        return None
    except Exception as e:
        logger.error(f"Error creating PayPal payment link: {e}")
        return None

def verify_payment(payment_id):
    """Verify payment status with PayPal API."""
    try:
        payment_info = get_payment_info(payment_id)
        
        if not payment_info or not payment_info.get('paypal_order_id'):
            logger.error(f"Invalid payment ID or missing PayPal order ID: {payment_id}")
            return False
            
        # Get PayPal access token
        access_token = get_paypal_access_token()
        if not access_token:
            return False
        
        # Get order information from PayPal
        order_id = payment_info['paypal_order_id']
        url = f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            order_data = response.json()
            status = order_data.get("status")
            
            # Check if the order has been completed
            if status == "COMPLETED":
                # Update payment status
                update_payment_status(payment_id, 'completed')
                
                # Add credits to user account
                user_id = payment_info['user_id']
                credits = payment_info['credits']
                update_user_credits(
                    user_id, 
                    credits, 
                    transaction_type="purchase", 
                    description=f"Compra de {credits} créditos"
                )
                
                logger.info(f"Payment {payment_id} verified and {credits} credits added to user {user_id}")
                return True
            elif status == "APPROVED":
                # Order is approved but not yet captured, try to capture it
                return capture_paypal_payment(payment_id, order_id, access_token)
            else:
                logger.info(f"Payment {payment_id} not yet completed. Current status: {status}")
        else:
            logger.error(f"Error retrieving PayPal order: {response.text}")
            
        return False
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        return False

def capture_paypal_payment(payment_id, order_id, access_token=None):
    """Capture an approved PayPal payment."""
    try:
        if not access_token:
            access_token = get_paypal_access_token()
            if not access_token:
                return False
        
        url = f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        response = requests.post(url, headers=headers)
        
        if response.status_code in [200, 201]:
            capture_data = response.json()
            status = capture_data.get("status")
            
            if status == "COMPLETED":
                # Get capture ID
                capture_id = None
                purchase_units = capture_data.get("purchase_units", [])
                if purchase_units and "payments" in purchase_units[0]:
                    captures = purchase_units[0]["payments"].get("captures", [])
                    if captures:
                        capture_id = captures[0].get("id")
                
                # Update payment status
                update_payment_status(
                    payment_id, 
                    'completed', 
                    paypal_payment_id=capture_id
                )
                
                # Get payment info
                payment_info = get_payment_info(payment_id)
                
                # Add credits to user account
                user_id = payment_info['user_id']
                credits = payment_info['credits']
                update_user_credits(
                    user_id, 
                    credits, 
                    transaction_type="purchase", 
                    description=f"Compra de {credits} créditos"
                )
                
                logger.info(f"Payment {payment_id} captured and {credits} credits added to user {user_id}")
                return True
            else:
                logger.error(f"Payment capture not completed. Status: {status}")
                return False
        else:
            logger.error(f"Error capturing payment: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error capturing payment: {e}")
        return False

# Webhook handler for PayPal payment notifications
def handle_paypal_webhook(request_data):
    """Handle PayPal webhook notifications."""
    try:
        event_type = request_data.get('event_type')
        logger.info(f"Received PayPal webhook event: {event_type}")
        
        # Handle PAYMENT.CAPTURE.COMPLETED events
        if event_type == 'PAYMENT.CAPTURE.COMPLETED':
            resource = request_data.get('resource', {})
            capture_id = resource.get('id')
            
            # Get the custom_id from the payment which contains our payment info
            custom_id = None
            links = resource.get('links', [])
            for link in links:
                if link.get('rel') == 'up':
                    # Get the order details to find our custom_id
                    order_url = link.get('href')
                    if order_url:
                        access_token = get_paypal_access_token()
                        if access_token:
                            headers = {"Authorization": f"Bearer {access_token}"}
                            order_response = requests.get(order_url, headers=headers)
                            if order_response.status_code == 200:
                                order_data = order_response.json()
                                purchase_units = order_data.get('purchase_units', [])
                                if purchase_units:
                                    custom_id = purchase_units[0].get('custom_id')
            
            if custom_id:
                # Parse the custom_id to get our payment information
                # Format: user_id:payment_id:package_id:credits
                parts = custom_id.split(':')
                if len(parts) == 4:
                    user_id = int(parts[0])
                    payment_id = parts[1]
                    credits = int(parts[3])
                    
                    # Update payment status
                    update_payment_status(
                        payment_id, 
                        'completed', 
                        paypal_payment_id=capture_id
                    )
                    
                    # Add credits to user account
                    update_user_credits(
                        user_id, 
                        credits, 
                        transaction_type="purchase", 
                        description=f"Compra de {credits} créditos"
                    )
                    
                    logger.info(f"Webhook: Added {credits} credits to user {user_id} for payment {payment_id}")
                    return True
                else:
                    logger.error(f"Webhook: Invalid custom_id format: {custom_id}")
            else:
                logger.error(f"Webhook: Could not find custom_id for capture {capture_id}")
        else:
            logger.info(f"Webhook: Ignoring event type {event_type}")
            
        return False
    except Exception as e:
        logger.error(f"Error handling PayPal webhook: {e}")
        return False

# Initialize payment database tables
init_payment_database()