import os
import logging
import json
from flask import Flask, request, jsonify, redirect, url_for, render_template_string
from dotenv import load_dotenv
from paypal_payment import (
    CREDIT_PACKAGES, create_paypal_payment_link, verify_payment,
    handle_paypal_webhook, get_payment_info
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Flask app configuration
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24))
WEBHOOK_SECRET = os.getenv('PAYPAL_WEBHOOK_SECRET')

# Simple HTML template for payment success/failure pages
PAYMENT_SUCCESS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Pago Exitoso</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            text-align: center;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .success-icon {
            color: #4CAF50;
            font-size: 64px;
            margin-bottom: 20px;
        }
        .button {
            background-color: #4CAF50;
            color: white;
            padding: 12px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            text-decoration: none;
            display: inline-block;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✓</div>
        <h1>¡Pago Completado!</h1>
        <p>Tu pago ha sido procesado correctamente y los créditos han sido añadidos a tu cuenta.</p>
        <p>Detalles de la transacción:</p>
        <p><strong>Paquete:</strong> {{ package_name }}</p>
        <p><strong>Créditos:</strong> {{ credits }}</p>
        <p><strong>Monto:</strong> {{ amount }} {{ currency }}</p>
        <a href="https://t.me/CreaVisionBot" class="button">Volver al Bot</a>
    </div>
</body>
</html>
'''

PAYMENT_ERROR_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Error en el Pago</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            text-align: center;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .error-icon {
            color: #F44336;
            font-size: 64px;
            margin-bottom: 20px;
        }
        .button {
            background-color: #2196F3;
            color: white;
            padding: 12px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            text-decoration: none;
            display: inline-block;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="error-icon">✗</div>
        <h1>Error en el Pago</h1>
        <p>{{ error_message }}</p>
        <a href="https://t.me/CreaVisionBot" class="button">Volver al Bot</a>
    </div>
</body>
</html>
'''

@app.route('/payment/packages', methods=['GET'])
def get_packages():
    """Return available credit packages."""
    return jsonify(CREDIT_PACKAGES)

@app.route('/payment/create/<int:user_id>/<package_id>', methods=['GET'])
def create_payment(user_id, package_id):
    """Create a payment link for a user and package."""
    try:
        if package_id not in CREDIT_PACKAGES:
            return jsonify({
                'success': False,
                'error': 'Paquete no válido'
            }), 400
            
        payment_data = create_paypal_payment_link(user_id, package_id)
        
        if payment_data:
            return jsonify({
                'success': True,
                'payment_id': payment_data['payment_id'],
                'checkout_url': payment_data['checkout_url']
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Error al crear el enlace de pago'
            }), 500
    except Exception as e:
        logger.error(f"Error creating payment: {e}")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor'
        }), 500

@app.route('/payment/verify/<payment_id>', methods=['GET'])
def check_payment(payment_id):
    """Verify payment status."""
    try:
        payment_info = get_payment_info(payment_id)
        
        if not payment_info:
            return jsonify({
                'success': False,
                'error': 'ID de pago no válido'
            }), 404
            
        # Verify with PayPal
        is_paid = verify_payment(payment_id)
        
        return jsonify({
            'success': True,
            'payment_id': payment_id,
            'status': payment_info['status'],
            'is_paid': is_paid
        })
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        return jsonify({
            'success': False,
            'error': 'Error interno del servidor'
        }), 500

@app.route('/payment/success/<payment_id>', methods=['GET'])
def payment_success(payment_id):
    """Handle successful payment redirect."""
    try:
        payment_info = get_payment_info(payment_id)
        
        if not payment_info:
            return render_template_string(
                PAYMENT_ERROR_TEMPLATE,
                error_message="ID de pago no válido o expirado."
            )
        
        # Verify payment status
        is_paid = verify_payment(payment_id)
        
        if is_paid:
            # Get package information
            package_id = None
            for pid, package in CREDIT_PACKAGES.items():
                if package['credits'] == payment_info['credits'] and package['price'] == payment_info['amount']:
                    package_id = pid
                    break
            
            if package_id:
                package = CREDIT_PACKAGES[package_id]
                return render_template_string(
                    PAYMENT_SUCCESS_TEMPLATE,
                    package_name=package['name'],
                    credits=package['credits'],
                    amount=package['price'],
                    currency=package['currency']
                )
            else:
                return render_template_string(
                    PAYMENT_SUCCESS_TEMPLATE,
                    package_name="Paquete de créditos",
                    credits=payment_info['credits'],
                    amount=payment_info['amount'],
                    currency=payment_info['currency']
                )
        else:
            return render_template_string(
                PAYMENT_ERROR_TEMPLATE,
                error_message="El pago aún no ha sido completado. Por favor, verifica el estado de tu pago en el bot."
            )
    except Exception as e:
        logger.error(f"Error handling success page: {e}")
        return render_template_string(
            PAYMENT_ERROR_TEMPLATE,
            error_message="Error al procesar el pago. Por favor, contacta al soporte."
        )

@app.route('/payment/cancel/<payment_id>', methods=['GET'])
def payment_cancel(payment_id):
    """Handle cancelled payment redirect."""
    return render_template_string(
        PAYMENT_ERROR_TEMPLATE,
        error_message="El pago ha sido cancelado. Puedes intentarlo de nuevo desde el bot."
    )

@app.route('/webhook/paypal', methods=['POST'])
def paypal_webhook():
    """Handle PayPal webhook notifications."""
    try:
        # Verify webhook signature if webhook secret is configured
        if WEBHOOK_SECRET:
            # PayPal webhook verification would go here
            pass
        
        # Process the webhook payload
        webhook_data = request.json
        
        # Handle the webhook event
        success = handle_paypal_webhook(webhook_data)
        
        if success:
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'status': 'ignored'}), 200
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def start_payment_server(host='0.0.0.0', port=5000, debug=False):
    """Start the Flask server for payment processing."""
    try:
        app.run(host=host, port=port, debug=debug)
    except Exception as e:
        logger.error(f"Error starting payment server: {e}")