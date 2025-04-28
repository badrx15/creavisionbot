import sqlite3
import os
import logging
import uuid
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DATABASE_PATH = 'bot_database.db'

def init_database():
    """Initialize the database with required tables."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Create users table (simplified)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            credits INTEGER DEFAULT 5,
            is_admin INTEGER DEFAULT 0,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create usage history table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS usage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message_text TEXT,
            tokens_used INTEGER,
            credits_used INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        
        # Create user preferences table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER,
            preference_key TEXT,
            preference_value TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, preference_key),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        
        # Create conversation context table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversation_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            messages TEXT,
            last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

def get_user(user_id):
    """Get user information from database."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        return user
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        return None
    finally:
        if conn:
            conn.close()

def register_user(user_id, username, first_name, last_name):
    """Register a new user or update existing user information."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if user:
            # Just update basic info
            cursor.execute(
                "UPDATE users SET username = ?, first_name = ?, last_name = ? WHERE user_id = ?",
                (username, first_name, last_name, user_id)
            )
            logger.info(f"Updated user information for user_id: {user_id}")
        else:
            # Create new user with default credits
            cursor.execute(
                "INSERT INTO users (user_id, username, first_name, last_name, credits) VALUES (?, ?, ?, ?, 5)",
                (user_id, username, first_name, last_name)
            )
            logger.info(f"Registered new user with user_id: {user_id}")
            
            # Save new user ID to text file
            try:
                with open('new_users.txt', 'a', encoding='utf-8') as f:
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    username_str = username if username else "No username"
                    name_str = f"{first_name or ''} {last_name or ''}".strip() or "No name"
                    f.write(f"{user_id} | {username_str} | {name_str} | {current_time}\n")
                logger.info(f"Saved new user ID {user_id} to new_users.txt")
            except Exception as e:
                logger.error(f"Error saving user ID to text file: {e}")
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_user_credits(user_id):
    """Get the number of credits for a user from the database."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 5  # Return actual credits or default 5 if user not found
    except Exception as e:
        logger.error(f"Error getting user credits: {e}")
        return 5  # Return default credits on error
    finally:
        if conn:
            conn.close()

def update_user_credits(user_id, credits_change, transaction_type="message", description=""):
    """Update user credits in the database."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Get current credits
        cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result:
            current_credits = result[0]
            new_credits = max(0, current_credits + credits_change)  # Ensure credits don't go below 0
            
            # Update credits in database
            cursor.execute(
                "UPDATE users SET credits = ? WHERE user_id = ?",
                (new_credits, user_id)
            )
        
        # Log the transaction for record-keeping
        cursor.execute(
            "INSERT INTO usage_history (user_id, message_text, tokens_used, credits_used) VALUES (?, ?, ?, ?)",
            (user_id, description, 0, abs(credits_change))
        )
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error updating user credits: {e}")
        return False
    finally:
        if conn:
            conn.close()

def record_usage(user_id, message_text, tokens_used, credits_used):
    """Record usage history for a user."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO usage_history (user_id, message_text, tokens_used, credits_used) VALUES (?, ?, ?, ?)",
            (user_id, message_text, tokens_used, credits_used)
        )
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error recording usage: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_all_users():
    """Get all users from database."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, first_name, last_name FROM users")
        users = cursor.fetchall()
        return users
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []
    finally:
        if conn:
            conn.close()

def set_admin_status(user_id, is_admin_status):
    """Set admin status for a user."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if user:
            cursor.execute(
                "UPDATE users SET is_admin = ? WHERE user_id = ?",
                (1 if is_admin_status else 0, user_id)
            )
        else:
            cursor.execute(
                "INSERT INTO users (user_id, is_admin, credits) VALUES (?, ?, 5)",
                (user_id, 1 if is_admin_status else 0)
            )
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error setting admin status: {e}")
        return False
    finally:
        if conn:
            conn.close()

# Conversation context management functions
def save_conversation_context(user_id, messages):
    """Save conversation context for a user."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Convert messages list to JSON string
        import json
        messages_json = json.dumps(messages)
        
        # Check if user already has a context
        cursor.execute("SELECT id FROM conversation_context WHERE user_id = ?", (user_id,))
        context = cursor.fetchone()
        
        if context:
            # Update existing context - asegurarse de actualizar el timestamp
            cursor.execute(
                "UPDATE conversation_context SET messages = ?, last_interaction = CURRENT_TIMESTAMP WHERE user_id = ?",
                (messages_json, user_id)
            )
            logger.info(f"Updated conversation context and refreshed timestamp for user_id: {user_id}")
        else:
            # Create new context
            cursor.execute(
                "INSERT INTO conversation_context (user_id, messages) VALUES (?, ?)",
                (user_id, messages_json)
            )
            logger.info(f"Created new conversation context for user_id: {user_id}")
        
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving conversation context: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_conversation_context(user_id):
    """Get conversation context for a user."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT messages FROM conversation_context WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result:
            import json
            return json.loads(result[0])
        else:
            return []
    except Exception as e:
        logger.error(f"Error getting conversation context: {e}")
        return []
    finally:
        if conn:
            conn.close()

def clear_conversation_context(user_id):
    """Clear conversation context for a user."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM conversation_context WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error clearing conversation context: {e}")
        return False
    finally:
        if conn:
            conn.close()

def clear_inactive_conversations(timeout_minutes=30):
    """Clear conversation contexts for users who have been inactive for the specified time.
    Returns a list of user IDs whose conversations were cleared."""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Calculate the cutoff time
        cutoff_time = datetime.now() - timedelta(minutes=timeout_minutes)
        cutoff_time_str = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')
        
        # First get the user IDs of inactive conversations
        cursor.execute("SELECT user_id FROM conversation_context WHERE last_interaction < ?", (cutoff_time_str,))
        inactive_users = [row[0] for row in cursor.fetchall()]
        
        # Then delete contexts older than the cutoff time
        cursor.execute("DELETE FROM conversation_context WHERE last_interaction < ?", (cutoff_time_str,))
        deleted_count = cursor.rowcount
        
        conn.commit()
        logger.info(f"Cleared {deleted_count} inactive conversation contexts")
        return inactive_users
    except Exception as e:
        logger.error(f"Error clearing inactive conversations: {e}")
        return 0
    finally:
        if conn:
            conn.close()

def is_admin(user_id):
    """Check if a user is an admin."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result and result[0] == 1
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False
    finally:
        if conn:
            conn.close()