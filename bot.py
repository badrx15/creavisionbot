import os
import logging
import json
import re
import yaml
import sqlite3
import threading
import time
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
import openai
import tiktoken
from database import (
    init_database, register_user, get_user_credits, update_user_credits,
    record_usage, get_all_users, set_admin_status, is_admin,
    save_conversation_context, get_conversation_context, clear_conversation_context,
    clear_inactive_conversations, DATABASE_PATH
)
from paypal_bot_integration import register_payment_handlers, handle_deep_link_start

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', '0'))  # Default admin user ID
NOTIFICATION_CHANNEL = 'https://t.me/trabajadoreswriteai'  # Canal para notificaciones

# Configure OpenAI
openai.api_key = OPENAI_API_KEY

# Constants
DEFAULT_CREDITS_PER_MESSAGE = 1
DEFAULT_MODEL = "gpt-3.5-turbo"
CONVERSATION_TIMEOUT_MINUTES = 30  # Tiempo de inactividad antes de reiniciar una conversación

# Variable global para almacenar la referencia al bot
bot_instance = None

# Initialize the database
init_database()

# Set initial admin if provided
if ADMIN_USER_ID > 0:
    set_admin_status(ADMIN_USER_ID, True)
    logger.info(f"Set user {ADMIN_USER_ID} as admin")

# Load AI models from file
def load_models():
    try:
        with open("modelos.json", "r", encoding="utf-8") as file:
            models_data = json.load(file)
            return models_data
    except Exception as e:
        logger.error(f"Error loading models: {e}")
        return {}

AI_MODELS = load_models()

def count_tokens(text, model=DEFAULT_MODEL):
    """Count the number of tokens in a text."""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception as e:
        logger.error(f"Error counting tokens: {e}")
        return len(text) // 4  # Rough estimate

def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued and reset conversation context."""
    user = update.effective_user
    
    # Check if user exists before registering
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,))
    existing_user = cursor.fetchone()
    conn.close()
    
    # Register user
    register_user(
        user.id,
        user.username,
        user.first_name,
        user.last_name
    )
    
    # If this is a new user, send notification to admin channel
    if not existing_user:
        new_user_info = f"<b>🆕 NUEVO USUARIO REGISTRADO</b>\n"
        new_user_info += f"<b>ID:</b> {user.id}\n"
        new_user_info += f"<b>Username:</b> @{user.username or 'No disponible'}\n"
        new_user_info += f"<b>Nombre:</b> {user.first_name or ''} {user.last_name or ''}\n"
        new_user_info += f"<b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        send_admin_notification(new_user_info)
    
    # Clear previous conversation context
    clear_conversation_context(user.id)
    
    update.message.reply_text(
        f'👋 ¡Hola {user.first_name}! 👋\n\n'
        f'🤖 Soy tu asistente virtual con IA avanzado. Puedes preguntarme cualquier cosa y te responderé con la última tecnología de inteligencia artificial.\n\n'
        f'💰 Créditos disponibles: {get_user_credits(user.id)}\n\n'
        f'📌 Comandos disponibles:\n'
        f'🔹 /start - Iniciar conversación y ver créditos\n'
        f'🔹 /help - Mostrar menú de ayuda\n'
        f'🔹 /creditos - Ver tu saldo actual\n'
        f'🔹 /comprar - Comprar más créditos\n'
        f'🔹 /modelos - Ver modelos de IA disponibles\n'
        f'🔹 /reset - Reiniciar la conversación actual\n\n'
        f'📝 Escribe tu pregunta para comenzar.'
    )

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text(
        "🔍 <b>GUÍA COMPLETA DEL ASISTENTE IA</b> 🔍\n\n"
        "<b>📋 COMANDOS PRINCIPALES:</b>\n"
        "/start - Iniciar o reiniciar conversación y ver créditos\n"
        "/help - Mostrar esta guía completa\n"
        "/creditos - Consultar tu saldo de créditos actual\n"
        "/comprar - Adquirir más créditos (PayPal)\n"
        "/modelos - Explorar y seleccionar diferentes modelos de IA\n"
        "/reset - Borrar el historial de la conversación actual\n\n"
        "<b>💰 SISTEMA DE CRÉDITOS:</b>\n"
        "• Cada nuevo usuario recibe 5 créditos gratuitos\n"
        "• Cada mensaje enviado consume 1 crédito\n"
        "• Puedes comprar paquetes adicionales:\n"
        "  - Paquete Básico: 50 créditos (5 USD)\n"
        "  - Paquete Estándar: 150 créditos (10 USD)\n"
        "  - Paquete Premium: 500 créditos (25 USD)\n\n"
        "<b>🤖 MODELOS DE IA DISPONIBLES:</b>\n"
        "• 👩🏼‍🎓 Asistente General - Para consultas generales\n"
        "• 👩🏼‍💻 Asistente de Código - Ayuda con programación\n"
        "• 👩‍🎨 Artista - Genera descripciones artísticas\n"
        "• 🇬🇧 Tutor de Inglés - Aprende y practica inglés\n"
        "• 📝 Mejorador de Textos - Corrige y mejora tus escritos\n"
        "• 💡 Generador de Ideas - Para proyectos y startups\n"
        "• Y muchos más modelos especializados...\n\n"
        "<b>💬 CÓMO USAR EL BOT:</b>\n"
        "1. Selecciona un modelo con /modelos según tu necesidad\n"
        "2. Escribe tu pregunta o solicitud directamente\n"
        "3. El bot mantiene el contexto de la conversación\n"
        "4. Si deseas cambiar de tema, usa /reset\n\n"
        "<b>⏱️ INFORMACIÓN ADICIONAL:</b>\n"
        "• Las conversaciones inactivas se reinician después de 30 minutos\n"
        "• El bot utiliza tecnología avanzada de OpenAI\n"
        "• Para problemas o sugerencias, contacta al administrador\n\n"
        "<b>🔐 PRIVACIDAD:</b>\n"
        "Tus conversaciones son privadas y no se comparten con terceros.",
        parse_mode=ParseMode.HTML
    )

def credits_command(update: Update, context: CallbackContext) -> None:
    """Show user credits."""
    user = update.effective_user
    credits = get_user_credits(user.id)
    
    # Crear botón para comprar más créditos
    keyboard = [
        [InlineKeyboardButton("Comprar más créditos", callback_data="buy_credits")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f'Tienes {credits} créditos disponibles.\n\n'
        f'Cada mensaje consume {DEFAULT_CREDITS_PER_MESSAGE} crédito.\n'
        f'Todos los usuarios tienen 5 créditos gratuitos que se gastan con cada mensaje.\n\n'
        f'Usa el comando /comprar para adquirir más créditos.',
        reply_markup=reply_markup
    )

def models_command(update: Update, context: CallbackContext) -> None:
    """Show available AI models with inline buttons."""
    keyboard = []
    
    for model_key, model_data in AI_MODELS.items():
        if model_key != "assistant":  # Skip the default assistant
            keyboard.append([InlineKeyboardButton(
                model_data.get('name', model_key),
                callback_data=f"select_model_{model_key}"
            )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "🤖 Selecciona un modelo de IA:\n\n"
        "Pulsa un botón para elegir el modelo que deseas utilizar.",
        reply_markup=reply_markup
    )

def select_model_command(update: Update, context: CallbackContext) -> None:
    """Select a specific AI model (legacy command)."""
    update.message.reply_text(
        "Por favor, usa el comando /modelos para seleccionar un modelo mediante botones."
    )

def handle_button_callback(update: Update, context: CallbackContext) -> None:
    """Handle button callbacks for model selection and other actions."""
    query = update.callback_query
    user = query.from_user
    
    # Always answer the callback query to remove the loading state
    query.answer()
    
    # Handle model selection button from timeout message
    if query.data == "select_model":
        # Redirigir al comando de modelos
        models_command(update, context)
        return
    # Handle specific model selection
    elif query.data.startswith("select_model_"):
        model_key = query.data.replace("select_model_", "")
        
        if model_key in AI_MODELS:
            # Store user preference
            try:
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO user_preferences (user_id, preference_key, preference_value) VALUES (?, ?, ?)",
                    (user.id, "model", model_key)
                )
                conn.commit()
                
                # Get welcome message if available
                welcome_message = AI_MODELS[model_key].get('welcome_message', '')
                model_name = AI_MODELS[model_key].get('name', model_key)
                
                # Edit the message to show the selection
                query.edit_message_text(
                    f"✅ Has seleccionado el modelo: {model_name}\n\n"
                    f"{welcome_message}"
                )
                
                logger.info(f"User {user.id} selected model: {model_key}")
                conn.close()
            except Exception as e:
                logger.error(f"Error setting model preference: {e}")
                query.edit_message_text("❌ Error al seleccionar el modelo. Por favor, intenta de nuevo.")
        else:
            query.edit_message_text("❌ Modelo no encontrado. Usa /modelos para ver los modelos disponibles.")
    # Handle delete user button
    elif query.data.startswith("delete_user_"):
        if not is_admin(user.id):
            query.edit_message_text("No tienes permisos para realizar esta acción.")
            return
            
        target_user_id = int(query.data.replace("delete_user_", ""))
        
        # Create confirmation buttons
        keyboard = [
            [InlineKeyboardButton("✅ Confirmar eliminación", callback_data=f"confirm_delete_{target_user_id}")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_delete")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text(
            f"⚠️ ¿Estás seguro de que deseas eliminar al usuario con ID {target_user_id}?\n\n"
            "Esta acción no se puede deshacer.",
            reply_markup=reply_markup
        )
    # Handle delete confirmation
    elif query.data.startswith("confirm_delete_"):
        if not is_admin(user.id):
            query.edit_message_text("No tienes permisos para realizar esta acción.")
            return
            
        target_user_id = int(query.data.replace("confirm_delete_", ""))
        
        try:
            # Eliminar usuario de la base de datos
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Eliminar registros relacionados primero
            cursor.execute("DELETE FROM conversation_context WHERE user_id = ?", (target_user_id,))
            cursor.execute("DELETE FROM user_preferences WHERE user_id = ?", (target_user_id,))
            cursor.execute("DELETE FROM usage_history WHERE user_id = ?", (target_user_id,))
            
            # Finalmente eliminar el usuario
            cursor.execute("DELETE FROM users WHERE user_id = ?", (target_user_id,))
            
            conn.commit()
            conn.close()
            
            query.edit_message_text(f"✅ Usuario con ID {target_user_id} eliminado correctamente.")
            logger.info(f"Admin {user.id} deleted user {target_user_id}")
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            query.edit_message_text(f"❌ Error al eliminar usuario: {e}")
    # Handle cancel delete
    elif query.data == "cancel_delete":
        query.edit_message_text("Operación cancelada. No se ha eliminado ningún usuario.")
    # Handle buy credits button
    elif query.data == "buy_credits":
        # Redirect to comprar command
        from paypal_bot_integration import comprar_command
        comprar_command(update, context)
    # Handle other callback types here if needed

def admin_command(update: Update, context: CallbackContext) -> None:
    """Admin command to manage users."""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("No tienes permisos para usar este comando.")
        return
    
    # Get all users from database
    users = get_all_users()
    
    # Create keyboard with user buttons
    keyboard = []
    for user_data in users:
        user_id = user_data[0]
        username = user_data[1] or "Sin nombre"
        keyboard.append([InlineKeyboardButton(
            f"ID: {user_id} | @{username}",
            callback_data=f"admin_user_{user_id}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "🔧 Panel de Administración\n\n"
        "Selecciona un usuario para administrar:",
        reply_markup=reply_markup
    )

def eliminar_command(update: Update, context: CallbackContext) -> None:
    """Admin command to delete users (hidden from help menu)."""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("No tienes permisos para usar este comando.")
        return
    
    # Check if an ID was provided as an argument
    if context.args and len(context.args) > 0:
        try:
            target_user_id = int(context.args[0])
            
            # Verificar que el usuario existe
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (target_user_id,))
            user_exists = cursor.fetchone()
            
            if not user_exists:
                update.message.reply_text(f"❌ No se encontró ningún usuario con ID {target_user_id}.")
                conn.close()
                return
                
            # Eliminar registros relacionados primero
            cursor.execute("DELETE FROM conversation_context WHERE user_id = ?", (target_user_id,))
            cursor.execute("DELETE FROM user_preferences WHERE user_id = ?", (target_user_id,))
            cursor.execute("DELETE FROM usage_history WHERE user_id = ?", (target_user_id,))
            
            # Finalmente eliminar el usuario
            cursor.execute("DELETE FROM users WHERE user_id = ?", (target_user_id,))
            
            conn.commit()
            conn.close()
            
            update.message.reply_text(f"✅ Usuario con ID {target_user_id} eliminado correctamente.")
            logger.info(f"Admin {user.id} deleted user {target_user_id} using direct command")
            return
        except ValueError:
            update.message.reply_text("❌ El ID de usuario debe ser un número entero.")
            return
        except Exception as e:
            update.message.reply_text(f"❌ Error al eliminar el usuario: {str(e)}")
            logger.error(f"Error deleting user: {e}")
            return
    
    # If no ID provided, show the list of users as before
    # Get all users from database
    users = get_all_users()
    
    # Create keyboard with user buttons
    keyboard = []
    for user_data in users:
        user_id = user_data[0]
        username = user_data[1] or "Sin nombre"
        first_name = user_data[2] or ""
        last_name = user_data[3] or ""
        display_name = f"{first_name} {last_name}".strip() or "Sin nombre"
        
        keyboard.append([InlineKeyboardButton(
            f"ID: {user_id} | @{username} | {display_name}",
            callback_data=f"delete_user_{user_id}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        "🗑️ Eliminar Usuario\n\n"
        "Selecciona un usuario para eliminar del sistema:",
        reply_markup=reply_markup
    )

def generate_ai_response(user_id, message_text, model_key="assistant"):
    """Generate a response using OpenAI API based on the selected model and conversation context."""
    try:
        # Get model configuration
        model_data = AI_MODELS.get(model_key, AI_MODELS.get("assistant", {}))
        system_prompt = model_data.get("prompt_start", "You are a helpful assistant.")
        parse_mode = model_data.get("parse_mode", "html")
        
        # Get conversation context
        conversation = get_conversation_context(user_id)
        
        # Prepare messages for API call
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add conversation history (limited to last 10 messages to avoid token limits)
        for msg in conversation[-10:]:
            messages.append(msg)
            
        # Add current user message
        messages.append({"role": "user", "content": message_text})
        
        # Use OpenAI API
        response = openai.ChatCompletion.create(
            model=DEFAULT_MODEL,
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        
        # Get the assistant's response
        assistant_response = response.choices[0].message.content.strip()
        
        # Update conversation context
        conversation.append({"role": "user", "content": message_text})
        conversation.append({"role": "assistant", "content": assistant_response})
        save_conversation_context(user_id, conversation)
        
        return assistant_response, parse_mode
    except Exception as e:
        logger.error(f"Error in OpenAI API call: {e}")
        return "Lo siento, tuve un problema al procesar tu solicitud. Por favor, intenta de nuevo más tarde.", "html"

# Función para enviar notificaciones al canal de administrador
def send_admin_notification(message):
    """Send notification to admin channel."""
    global bot_instance
    try:
        if bot_instance:
            # Extraer el nombre del canal de la URL
            channel_name = NOTIFICATION_CHANNEL.split('/')[-1]
            # Enviar mensaje al canal
            bot_instance.send_message(chat_id=f"@{channel_name}", text=message, parse_mode=ParseMode.HTML)
            logger.info(f"Notification sent to admin channel: {message}")
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")

def handle_message(update: Update, context: CallbackContext) -> None:
    """Handle user messages and generate AI responses with context."""
    user = update.effective_user
    user_message = update.message.text
    
    # Register user if not already registered
    register_user(
        user.id,
        user.username,
        user.first_name,
        user.last_name
    )
    
    # Get user preferences
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT preference_value FROM user_preferences WHERE user_id = ? AND preference_key = ?",
            (user.id, "model")
        )
        result = cursor.fetchone()
        selected_model = result[0] if result else "assistant"
        model_name = AI_MODELS.get(selected_model, {}).get('name', 'Asistente General')
        conn.close()
    except Exception as e:
        logger.error(f"Error getting user preferences: {e}")
        selected_model = "assistant"
        model_name = AI_MODELS.get(selected_model, {}).get('name', 'Asistente General')
    
    # Check if user has enough credits
    user_credits = get_user_credits(user.id)
    
    if user_credits < DEFAULT_CREDITS_PER_MESSAGE:
        update.message.reply_text(
            "❌ No tienes suficientes créditos para usar el asistente. Cada usuario dispone de 5 créditos gratuitos que se gastan con cada mensaje."
        )
        return
    
    # Let the user know the bot is processing
    processing_message = update.message.reply_text("Procesando tu mensaje...")
    
    try:
        # Notificar al administrador sobre el uso del bot
        usage_info = f"<b>🔄 ACTIVIDAD DE USUARIO</b>\n"
        usage_info += f"<b>ID:</b> {user.id}\n"
        usage_info += f"<b>Username:</b> @{user.username or 'No disponible'}\n"
        usage_info += f"<b>Nombre:</b> {user.first_name or ''} {user.last_name or ''}\n"
        usage_info += f"<b>Modelo:</b> {model_name}\n"
        usage_info += f"<b>Mensaje:</b> {user_message[:100]}{'...' if len(user_message) > 100 else ''}\n"
        usage_info += f"<b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        send_admin_notification(usage_info)
        
        # Generate AI response with selected model and conversation context
        ai_response, parse_mode = generate_ai_response(user.id, user_message, selected_model)
        
        # Calculate tokens used (approximate)
        tokens_used = count_tokens(user_message) + count_tokens(ai_response)
        
        # Only deduct credits if message was processed successfully
        update_user_credits(user.id, -DEFAULT_CREDITS_PER_MESSAGE, "message", "AI response")
        record_usage(user.id, user_message, tokens_used, DEFAULT_CREDITS_PER_MESSAGE)
        
        # Delete processing message and send the response
        processing_message.delete()
        
        # Send the response back to the user with appropriate parse mode
        if parse_mode.lower() == "markdown":
            update.message.reply_text(ai_response, parse_mode=ParseMode.MARKDOWN)
        else:  # Default to HTML
            update.message.reply_text(ai_response, parse_mode=ParseMode.HTML)
        
        # Inform about remaining credits
        remaining_credits = get_user_credits(user.id)
        update.message.reply_text(f"Créditos restantes: {remaining_credits}")
    except Exception as e:
        # If there's an error, don't deduct credits
        logger.error(f"Error processing message: {e}")
        processing_message.delete()
        update.message.reply_text(
            "Lo siento, ocurrió un error al procesar tu mensaje. No se han descontado créditos. "
            "Por favor, intenta de nuevo más tarde."
        )

def reset_command(update: Update, context: CallbackContext) -> None:
    """Reset the conversation context for a user."""
    user = update.effective_user
    clear_conversation_context(user.id)
    update.message.reply_text(
        "🔄 Conversación reiniciada. Puedes comenzar una nueva conversación ahora."
    )

# Función para limpiar conversaciones inactivas periódicamente
def cleanup_inactive_conversations():
    """Periodically clean up inactive conversations and notify users."""
    # Variable global para almacenar la referencia al bot
    global bot_instance
    
    while True:
        try:
            # Primero esperar el tiempo especificado antes de realizar cualquier limpieza
            # Esto evita que se eliminen conversaciones inmediatamente al iniciar el bot
            logger.info(f"Programando próxima limpieza de conversaciones para dentro de {CONVERSATION_TIMEOUT_MINUTES} minutos")
            time.sleep(CONVERSATION_TIMEOUT_MINUTES * 60)
            
            # Limpiar conversaciones inactivas después de esperar y obtener los IDs de usuarios afectados
            inactive_users = clear_inactive_conversations(CONVERSATION_TIMEOUT_MINUTES)
            logger.info(f"Limpieza programada: {len(inactive_users)} conversaciones inactivas eliminadas")
            
            # Verificar si tenemos acceso al bot
            if bot_instance:
                # Enviar mensaje a cada usuario con conversación inactiva
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                for user_id in inactive_users:
                    try:
                        # Crear botón para ir a modelos
                        keyboard = [
                            [InlineKeyboardButton("Seleccionar modelo", callback_data="select_model")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        # Enviar mensaje de notificación
                        bot_instance.send_message(
                            chat_id=user_id,
                            text="⏰ *Conversación cerrada por inactividad* ⏰\n\n"
                                 "Tu conversación ha sido cerrada automáticamente después de "
                                 f"{CONVERSATION_TIMEOUT_MINUTES} minutos de inactividad.\n\n"
                                 "Para iniciar una nueva conversación, puedes:\n"
                                 "• Usar el comando /modelos para seleccionar un modelo\n"
                                 "• Usar el comando /reset para reiniciar la conversación\n"
                                 "• Pulsar el botón de abajo para seleccionar un modelo",
                            parse_mode="Markdown",
                            reply_markup=reply_markup
                        )
                        logger.info(f"Mensaje de cierre enviado al usuario {user_id}")
                    except Exception as e:
                        logger.error(f"Error al enviar mensaje de cierre al usuario {user_id}: {e}")
            else:
                logger.error("No se pudo enviar mensajes de cierre: referencia al bot no disponible")
        except Exception as e:
            logger.error(f"Error en la limpieza programada: {e}")
            # Esperar un poco antes de intentar de nuevo en caso de error
            time.sleep(60)

def main() -> None:
    """Start the bot."""
    # Check if token is available
    if not TELEGRAM_TOKEN:
        logger.error("No se encontró el token de Telegram. Por favor, configura la variable de entorno TELEGRAM_TOKEN.")
        return
    
    if not OPENAI_API_KEY:
        logger.error("No se encontró la clave API de OpenAI. Por favor, configura la variable de entorno OPENAI_API_KEY.")
        return
        
    # Declarar acceso a la variable global
    global bot_instance

    # Create the Updater and pass it your bot's token
    updater = Updater(TELEGRAM_TOKEN)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    
    # Guardar referencia global al bot para enviar notificaciones
    bot_instance = updater.bot

    # Register command handlers
    # Modificar el manejador de start para soportar deep linking
    dispatcher.add_handler(CommandHandler("start", lambda update, context: 
                                         handle_deep_link_start(update, context) or start(update, context), 
                                         pass_args=True))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("creditos", credits_command))
    dispatcher.add_handler(CommandHandler("modelos", models_command))
    dispatcher.add_handler(CommandHandler("modelo", select_model_command))
    dispatcher.add_handler(CommandHandler("admin", admin_command))
    dispatcher.add_handler(CommandHandler("reset", reset_command))
    dispatcher.add_handler(CommandHandler("eliminar", eliminar_command))
    
    # Add callback query handler for non-payment related callbacks
    dispatcher.add_handler(CallbackQueryHandler(handle_button_callback, pattern=r'^(?!buy_package_|verify_payment_)'))
    
    # Asegurar que el callback 'select_model' también sea manejado
    dispatcher.add_handler(CallbackQueryHandler(handle_button_callback, pattern=r'^select_model$'))
    
    # Register payment handlers
    register_payment_handlers(dispatcher)
    
    # Register message handler
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    # Start background thread for cleaning up inactive conversations
    cleanup_thread = threading.Thread(target=cleanup_inactive_conversations, daemon=True)
    cleanup_thread.start()
    logger.info("Iniciado hilo de limpieza de conversaciones inactivas")

    # Start the Bot
    updater.start_polling()
    logger.info("Bot started successfully!")
    
    # Guardar referencia al bot para usar en el hilo de limpieza
    bot_instance = updater.bot

    # Run the bot until you press Ctrl-C
    updater.idle()

if __name__ == '__main__':
    main()