import os
import logging
import threading
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from dotenv import load_dotenv
from paypal_payment import CREDIT_PACKAGES, create_paypal_payment_link, verify_payment, get_payment_info
from paypal_routes import start_payment_server
from database import get_user_credits

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Payment server configuration
PAYMENT_SERVER_HOST = os.getenv('PAYMENT_SERVER_HOST', '0.0.0.0')
PAYMENT_SERVER_PORT = int(os.getenv('PAYMENT_SERVER_PORT', '5000'))
PAYMENT_SERVER_URL = os.getenv('PAYMENT_SERVER_URL', f'http://localhost:{PAYMENT_SERVER_PORT}')

# Start payment server in a separate thread
def start_payment_server_thread():
    """Start the payment server in a background thread."""
    thread = threading.Thread(
        target=start_payment_server,
        kwargs={
            'host': PAYMENT_SERVER_HOST,
            'port': PAYMENT_SERVER_PORT,
            'debug': False
        },
        daemon=True
    )
    thread.start()
    logger.info(f"Payment server started on {PAYMENT_SERVER_HOST}:{PAYMENT_SERVER_PORT}")
    return thread

# Command handlers for Telegram bot
def comprar_command(update: Update, context: CallbackContext) -> None:
    """Show available credit packages for purchase."""
    user = update.effective_user
    
    # Create keyboard with package buttons
    keyboard = []
    for package_id, package in CREDIT_PACKAGES.items():
        keyboard.append([InlineKeyboardButton(
            f"{package['name']} - {package['credits']} créditos ({package['price']} {package['currency']})",
            callback_data=f"buy_package_{package_id}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"💰 Compra de Créditos\n\n"\
                  f"Créditos actuales: {get_user_credits(user.id)}\n\n"\
                  f"Selecciona un paquete para comprar:"
    
    # Check if this is called from a callback query or a direct command
    if update.callback_query:
        # Called from a button callback
        update.callback_query.edit_message_text(
            text=message_text,
            reply_markup=reply_markup
        )
    else:
        # Called directly from a command
        update.message.reply_text(
            text=message_text,
            reply_markup=reply_markup
        )

def handle_payment_callback(update: Update, context: CallbackContext) -> None:
    """Handle payment-related button callbacks."""
    query = update.callback_query
    user = query.from_user
    
    # Always answer the callback query to remove the loading state
    query.answer()
    
    # Handle package selection
    if query.data.startswith("buy_package_"):
        package_id = query.data.replace("buy_package_", "")
        
        if package_id in CREDIT_PACKAGES:
            package = CREDIT_PACKAGES[package_id]
            
            # Create payment link
            payment_data = create_paypal_payment_link(user.id, package_id)
            
            if payment_data:
                # Create keyboard with payment link
                keyboard = [
                    [InlineKeyboardButton("Realizar Pago", url=payment_data['checkout_url'])],
                    [InlineKeyboardButton("Verificar Pago", callback_data=f"verify_payment_{payment_data['payment_id']}")]
                ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                query.edit_message_text(
                    f"🛒 Detalles de la Compra\n\n"
                    f"Paquete: {package['name']}\n"
                    f"Créditos: {package['credits']}\n"
                    f"Precio: {package['price']} {package['currency']}\n\n"
                    f"Haz clic en el botón 'Realizar Pago' para completar tu compra directamente.\n"
                    f"No necesitas iniciar sesión en PayPal, puedes pagar como invitado con tarjeta.\n"
                    f"Una vez completado el pago, haz clic en 'Verificar Pago' para actualizar tus créditos.",
                    reply_markup=reply_markup
                )
            else:
                query.edit_message_text(
                    "❌ Error al crear el enlace de pago. Por favor, intenta de nuevo más tarde."
                )
        else:
            query.edit_message_text("❌ Paquete no válido. Usa /comprar para ver los paquetes disponibles.")
    
    # Handle payment verification
    elif query.data.startswith("verify_payment_"):
        payment_id = query.data.replace("verify_payment_", "")
        
        # Get current payment info to check status
        payment_info = get_payment_info(payment_id)
        current_status = payment_info.get('status') if payment_info else 'unknown'
        
        # Verify payment with PayPal
        is_paid = verify_payment(payment_id)
        
        if is_paid:
            # Get updated credits
            credits = get_user_credits(user.id)
            
            query.edit_message_text(
                f"✅ ¡Pago completado!\n\n"
                f"Los créditos han sido añadidos a tu cuenta.\n"
                f"Créditos actuales: {credits}\n\n"
                f"Usa /creditos para ver tu saldo actual."
            )
        else:
            # Create keyboard to retry verification
            keyboard = [
                [InlineKeyboardButton("Verificar de nuevo", callback_data=f"verify_payment_{payment_id}")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Add timestamp to message to avoid 'Message is not modified' error
            current_time = datetime.now().strftime("%H:%M:%S")
            
            try:
                query.edit_message_text(
                    f"⏳ El pago aún no ha sido completado o verificado. (Última verificación: {current_time})\n\n"
                    f"Estado actual: {current_status}\n\n"
                    "Si ya realizaste el pago, espera unos momentos y haz clic en 'Verificar de nuevo'.\n"
                    "Si aún no has realizado el pago, completa el proceso de pago primero.",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Error al actualizar mensaje de verificación: {e}")
                # Si falla la edición, podemos enviar un nuevo mensaje
                context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"⏳ El pago aún no ha sido completado. (Verificado a las {current_time})\n\nEstado: {current_status}",
                    reply_markup=reply_markup
                )

# Function to register payment-related handlers to the bot
def register_payment_handlers(dispatcher):
    """Register payment-related command and callback handlers."""
    # Add command handlers
    dispatcher.add_handler(CommandHandler("comprar", comprar_command))
    
    # Add callback query handler for payment-related callbacks
    dispatcher.add_handler(CallbackQueryHandler(
        handle_payment_callback,
        pattern=r'^(buy_package_|verify_payment_)'
    ))
    
    # Start payment server
    start_payment_server_thread()
    
    logger.info("Payment handlers registered successfully")

# Handle deep linking for payment verification
def handle_deep_link_start(update: Update, context: CallbackContext) -> None:
    """Handle deep linking for payment verification."""
    user = update.effective_user
    args = context.args
    
    if args and args[0].startswith("payment_"):
        payment_id = args[0].replace("payment_", "")
        
        # Verify payment with PayPal
        is_paid = verify_payment(payment_id)
        
        if is_paid:
            # Get updated credits
            credits = get_user_credits(user.id)
            
            update.message.reply_text(
                f"✅ ¡Pago completado!\n\n"
                f"Los créditos han sido añadidos a tu cuenta.\n"
                f"Créditos actuales: {credits}\n\n"
                f"Usa /creditos para ver tu saldo actual."
            )
        else:
            # Create keyboard to retry verification
            keyboard = [
                [InlineKeyboardButton("Verificar de nuevo", callback_data=f"verify_payment_{payment_id}")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(
                "⏳ El pago aún no ha sido completado o verificado.\n\n"
                "Si ya realizaste el pago, espera unos momentos y haz clic en 'Verificar de nuevo'.\n"
                "Si aún no has realizado el pago, completa el proceso de pago primero.",
                reply_markup=reply_markup
            )
    elif args and args[0].startswith("cancel_"):
        payment_id = args[0].replace("cancel_", "")
        update.message.reply_text(
            "❌ Pago cancelado.\n\n"
            "Puedes intentar de nuevo usando el comando /comprar."
        )
    else:
        # Normal start command behavior
        return None  # Let the regular start handler take over