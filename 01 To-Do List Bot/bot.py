from flask import Flask, request, jsonify
import requests
import config
import json
import os

app = Flask(__name__)

# Telegram Bot Token
TOKEN = config.TELEGRAM_BOT_TOKEN
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/"

# File to store tasks
TASKS_FILE = "tasks.json"

# Helper Functions
def load_tasks():
    """Load tasks from the JSON file."""
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tasks(tasks):
    """Save tasks to the JSON file."""
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f)

def send_message(chat_id, text):
    """Send a message to a Telegram user."""
    url = TELEGRAM_API_URL + "sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def set_webhook():
    """Set the Telegram webhook."""
    webhook_url = f"{config.WEBHOOK_URL}/{TOKEN}"
    response = requests.post(
        TELEGRAM_API_URL + "setWebhook",
        json={"url": webhook_url}
    )
    if response.status_code == 200:
        print("Webhook set successfully!")
    else:
        print("Failed to set webhook:", response.text)

# Command Handlers
@app.route(f"/{TOKEN}", methods=["POST"])
def telegram_webhook():
    """Handle Telegram updates."""
    update = request.json
    tasks = load_tasks()  # Load tasks at the start of each update
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "").strip()

        if text.startswith("/start") or text.startswith("/help"):
            send_message(
                chat_id,
                "Welcome to the To-Do List Bot!\n\n"
                "Commands:\n"
                "/add [task] - Add a task\n"
                "/list - List all tasks\n"
                "/delete [task number] - Delete a task"
            )

        elif text.startswith("/add"):
            task = text[5:].strip()
            if not task:
                send_message(chat_id, "Please specify a task to add.")
            else:
                if str(chat_id) not in tasks:
                    tasks[str(chat_id)] = []
                tasks[str(chat_id)].append(task)
                save_tasks(tasks)  # Save tasks after adding
                send_message(chat_id, f"Task added: {task}")

        elif text.startswith("/list"):
            user_tasks = tasks.get(str(chat_id), [])
            if not user_tasks:
                send_message(chat_id, "You have no tasks.")
            else:
                task_list = "\n".join(f"{i+1}. {task}" for i, task in enumerate(user_tasks))
                send_message(chat_id, f"Your tasks:\n{task_list}")

        elif text.startswith("/delete"):
            try:
                task_number = int(text[8:].strip())
                user_tasks = tasks.get(str(chat_id), [])
                if task_number < 1 or task_number > len(user_tasks):
                    raise ValueError
                removed_task = user_tasks.pop(task_number - 1)
                save_tasks(tasks)  # Save tasks after deletion
                send_message(chat_id, f"Deleted task: {removed_task}")
            except (ValueError, IndexError):
                send_message(chat_id, "Invalid task number. Use /list to see task numbers.")

        else:
            send_message(chat_id, "Invalid command. Use /help to see available commands.")
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    # Ensure tasks.json exists
    if not os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "w") as f:
            json.dump({}, f)

    # Set webhook before starting the server
    set_webhook()

    # Run Flask app
    app.run(host="127.0.0.1", port=8000, debug=True)
