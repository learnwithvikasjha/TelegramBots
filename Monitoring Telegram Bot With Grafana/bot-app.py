from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import Json
import os
import json
import logging
import requests

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# PostgreSQL connection details
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'grafana')
DB_USER = os.getenv('DB_USER', 'grafana')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'grafana')

# Load configuration from file
try:
    with open('config.json', 'r') as config_file:
        config = json.load(config_file)
        BOT_TOKEN = config.get("bot_token")
        WEBHOOK_URL = config.get("webhook_url")
except Exception as e:
    logging.critical("Failed to load configuration file: %s", e)
    raise

# Validate config values
if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Missing bot token or webhook URL in configuration file.")

# Function to connect to PostgreSQL
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        logging.error("Failed to connect to PostgreSQL: %s", e)
        raise

# Function to drop and recreate the table
def recreate_table():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Drop the table if it exists
                cursor.execute("DROP TABLE IF EXISTS telegram_payloads;")
                logging.info("Dropped existing table 'telegram_payloads'.")

                # Create the table
                cursor.execute("""
                    CREATE TABLE telegram_payloads (
                        id SERIAL PRIMARY KEY,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
                logging.info("Table 'telegram_payloads' created successfully.")
    except Exception as e:
        logging.error("Failed to recreate table: %s", e)
        raise

# Function to set the Telegram bot webhook
def set_telegram_webhook():
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
        response = requests.post(url, json={"url": WEBHOOK_URL})
        if response.status_code == 200 and response.json().get("ok"):
            logging.info("Telegram webhook set successfully.")
        else:
            logging.error("Failed to set Telegram webhook: %s", response.text)
            raise Exception("Failed to set webhook.")
    except Exception as e:
        logging.critical("Error setting Telegram webhook: %s", e)
        raise

@app.route('/', methods=['POST'])
def webhook():
    logging.info("Received a webhook request.")
    try:
        payload = request.json  # Telegram's bot payload
        if not payload:
            logging.warning("Invalid or empty payload received.")
            return jsonify({"error": "Invalid payload"}), 400

        # Insert JSON payload directly into the database
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO telegram_payloads (payload) VALUES (%s)",
                    (Json(payload),)
                )
                conn.commit()

        logging.info("Payload saved successfully.")
        return jsonify({"message": "Payload saved successfully"}), 200

    except Exception as e:
        logging.error("Error saving payload: %s", e)
        return jsonify({"error": "Failed to save payload"}), 500

if __name__ == '__main__':
    try:
        # Drop and recreate the table before starting the server
        recreate_table()

        # Set the Telegram webhook
        set_telegram_webhook()

        logging.info("Starting Flask server...")
        app.run(debug=True, host='127.0.0.1', port=8000)
    except Exception as e:
        logging.critical("Application startup failed: %s", e)
