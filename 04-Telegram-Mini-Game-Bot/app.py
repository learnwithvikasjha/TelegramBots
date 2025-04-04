from flask import Flask, request, render_template
from flask import jsonify
import urllib.parse
import json
from dotenv import load_dotenv
import logging
import base64
import os
import requests

load_dotenv()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

@app.route('/')
def index():
    """Enhanced debug endpoint"""
    print("\n=== Full Incoming Request ===")
    print("Method:", request.method)
    print("URL:", request.url)
    
    print("\nHeaders:")
    for header, value in request.headers.items():
        print(f"{header}: {value}")
    
    print("\nQuery Parameters:")
    for arg, value in request.args.items():
        print(f"{arg}: {value}")
    
    print("\nForm Data:")
    print(request.form)
    
    print("\nRaw Query String:", request.query_string.decode())
    
    # Special handling for Telegram WebApp
    if 'org.telegram.messenger' in request.headers.get('User-Agent', ''):
        print("\nTelegram WebApp detected!")
        if not request.args:
            print("WARNING: No query parameters received from Telegram!")
        
        # Try alternative ways to get initData
        init_data = request.args.get('initData') or \
                   request.headers.get('X-Telegram-Init-Data') or \
                   request.form.get('initData')
        
        if init_data:
            print("Found initData:", init_data)
            # Parse the initData to extract user info
            try:
                parsed = dict(pair.split('=') for pair in init_data.split('&'))
                print("Parsed initData:", parsed)
                if 'user' in parsed:
                    user_data = urllib.parse.unquote(parsed['user'])
                    print("User data:", user_data)
            except Exception as e:
                print("Error parsing initData:", str(e))
    
    return render_template('game.html')

def send_telegram_message(user_id, message):
    """Send a message to a Telegram user."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": message
    }
    response = requests.post(url, json=payload)
    return response.json()
    
@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming score submissions."""
    data = request.get_json()

    if not data:
        logging.warning("Invalid or missing JSON data")
        return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400

    logging.info(f"Received data: {data}")

    # Validate required fields
    required_fields = {'action', 'username', 'score', 'platform', 'timestamp', 'initData'}
    if not required_fields.issubset(data.keys()):
        logging.warning("Missing required fields")
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    # Extract user ID from initData
    try:
        parsed_data = urllib.parse.parse_qs(data['initData'])
        user_data = json.loads(parsed_data['user'][0])
        user_id = user_data.get('id')
    except Exception as e:
        logging.error(f"Error extracting user ID: {e}")
        return jsonify({'status': 'error', 'message': 'Invalid initData'}), 400

    # Process the score
    username = data['username']
    score = data['score']
    logging.info(f"User {username} (ID: {user_id}) submitted a score of {score}")

    # Send the score back to the user on Telegram
    message = f"Hey {username}, your score of {score} has been recorded! 🎯"
    send_telegram_message(user_id, message)

    return jsonify({'status': 'success', 'message': 'Score recorded', 'user_id': user_id})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
