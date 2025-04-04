import json
import boto3
from boto3.dynamodb.conditions import Attr
from pip._vendor import requests
import os
from datetime import datetime
import urllib.parse

# Initialize AWS services
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

# Load environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")

# Validate environment variables
if not TELEGRAM_BOT_TOKEN or not S3_BUCKET_NAME or not DYNAMODB_TABLE_NAME:
    raise ValueError("Missing required environment variables")

def lambda_handler(event, context):
    print("Received event:", json.dumps(event))  # Log entire event

    # Validate event structure
    if "body" not in event:
        print("Error: Missing 'body' in event")
        return {"statusCode": 200, "body": "Invalid request"}

    try:
        body = json.loads(event["body"])
        print("Parsed body:", body)
    except json.JSONDecodeError:
        print("Error: Failed to parse JSON body")
        return {"statusCode": 200, "body": "Invalid JSON format"}

    # Check if it's a search command
    message = body.get("message", {})
    message_id = message.get("message_id")
    user_id = message.get("from", {}).get("id")
    text = message.get("text", "")

    if text and text.startswith("/search"):
        print("Received /search command")
        search_query = text.split("/search", 1)[1].strip()
        if search_query:
            result = search_and_send_files(search_query, user_id, message_id)
            return result if result else {"statusCode": 200, "body": "Search completed with fallback"}
        else:
            try:
                send_telegram_message(user_id, "Please provide a search term after /search", message_id)
            except Exception as e:
                print(f"Failed to send message: {e}")
            return {"statusCode": 200, "body": "Search term missing"}


    # Original audio processing logic
    if "audio" not in message:
        print("Error: No 'audio' found in the request")
        return {"statusCode": 200, "body": "No audio found in the request"}

    audio = message.get("audio", {})
    caption = message.get("caption", "")
    duration = audio.get("duration", 0)
    filename = audio.get("file_name", "")

    if not user_id or "file_id" not in audio:
        print("Error: Missing 'user_id' or 'file_id'")
        return {"statusCode": 200, "body": "Invalid audio request"}

    file_id = audio["file_id"]
    print(f"User ID: {user_id}, File ID: {file_id}, Caption: {caption}")

    # Get Telegram file info
    file_info = get_telegram_file_info(file_id)
    if not file_info or "file_path" not in file_info:
        print("Error: Failed to retrieve file info from Telegram")
        return {"statusCode": 200, "body": "Failed to get audio file from Telegram"}

    file_path = file_info["file_path"]
    file_extension = os.path.splitext(file_path)[1] or ".ogg"  # Default to .ogg
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    s3_key = f"user_{user_id}/{file_id}{file_extension}"

    print(f"File URL: {file_url}, S3 Key: {s3_key}")

    # Upload file to S3
    upload_success = upload_to_s3(file_url, s3_key)
    if not upload_success:
        print("Error: Failed to upload audio to S3")
        return {"statusCode": 200, "body": "Failed to upload audio to S3"}

    s3_url = f"s3://{S3_BUCKET_NAME}/{s3_key}"
    print(f"File successfully uploaded to S3: {s3_url}")

    # Store metadata in DynamoDB
    metadata_saved = store_metadata_in_dynamodb(user_id, file_id, s3_url, caption, duration, filename)
    if not metadata_saved:
        print("Error: Failed to save metadata in DynamoDB")
        return {"statusCode": 200, "body": "Failed to save metadata"}

    print("Audio uploaded successfully and metadata stored")
    return {"statusCode": 200, "body": "Audio uploaded successfully"}

def get_telegram_file_info(file_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
    print(f"Fetching file info from Telegram: {url}")

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        print("Telegram API Response:", json.dumps(data, indent=2))

        if "result" not in data:
            print("Error: 'result' key missing in Telegram response")
            return None

        return data["result"]

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error: {e}")
        print(f"Response Content: {response.text}")
    except requests.RequestException as e:
        print(f"Request Error: {e}")

    return None

def upload_to_s3(file_url, s3_key):
    print(f"Downloading audio from {file_url}")

    try:
        response = requests.get(file_url, stream=True)
        response.raise_for_status()
        print(f"Uploading to S3: {S3_BUCKET_NAME}/{s3_key}")
        s3.upload_fileobj(response.raw, S3_BUCKET_NAME, s3_key)
        print("Upload to S3 successful")
        return True
    except requests.RequestException as e:
        print(f"Error downloading audio: {e}")
    except Exception as e:
        print(f"Error uploading to S3: {e}")
    
    return False

def store_metadata_in_dynamodb(user_id, file_id, s3_url, caption, duration, filename):
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)
    metadata = {
        "id": f"{user_id}_{file_id}",
        "file_id": file_id,
        "s3_url": s3_url,
        "caption": caption,
        "timestamp": datetime.utcnow().isoformat(),
        "duration": duration,
        "filename": filename
    }

    print(f"Storing metadata in DynamoDB: {metadata}")

    try:
        table.put_item(Item=metadata)
        print("Metadata stored successfully in DynamoDB")
        return True
    except Exception as e:
        print(f"Error storing metadata in DynamoDB: {e}")
        return False

def search_and_send_files(search_query, user_id, message_id):
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)
    print(f"Searching for: '{search_query}' in captions and filenames for user {user_id}")

    try:
        # Search in both filename and caption
        response = table.scan(
            FilterExpression=(
                (Attr("filename").contains(search_query) | Attr("caption").contains(search_query)) &
                Attr("id").begins_with(str(user_id))
            )
        )
        items = response.get("Items", [])
        print(f"Found {len(items)} matching items")

        if not items:
            send_telegram_message(user_id, f"No files found matching '{search_query}'", message_id)
            return {"statusCode": 200, "body": "No matches found"}

        # Send each matching file to the user
        for item in items:
            s3_url = item.get("s3_url", "")
            if not s3_url:
                continue

            # Extract S3 key from the URL
            s3_path = s3_url.replace(f"s3://{S3_BUCKET_NAME}/", "")
            filename = os.path.basename(s3_path)
            
            try:
                # Generate a presigned URL for the file
                presigned_url = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': S3_BUCKET_NAME, 'Key': s3_path},
                    ExpiresIn=3600
                )
                
                # Send the file to the user
                send_telegram_document(user_id, presigned_url, filename, item.get("caption", ""), message_id)
                return {"statusCode": 200, "body": "Search completed"}
            except Exception as e:
                print(f"Error sending file {filename}: {e}")
                send_telegram_message(user_id, f"Error sending file {filename}", message_id)
                return {"statusCode": 200, "body": "Search error"}
        return {"statusCode": 200, "body": "Search completed"}

    except Exception as e:
        print(f"Error searching metadata: {e}")
        send_telegram_message(user_id, "Error searching files")
        return {"statusCode": 200, "body": "Search error"}

def send_telegram_message(chat_id, text, message_id=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }

    if message_id:
        payload["reply_to_message_id"] = message_id
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Error sending Telegram message: {e}")
        return False

def send_telegram_document(chat_id, document_url, filename, caption="", message_id=None):

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    
    # Download the file from the presigned URL
    try:
        with requests.get(document_url, stream=True) as file_response:
            file_response.raise_for_status()
            
            # Prepare the file to send
            files = {
                'document': (filename, file_response.raw)
            }
            data = {
                'chat_id': chat_id,
                'caption': caption[:1024]  # Telegram caption limit
            }

            # Add reply_to_message_id if provided
            if message_id:
                data['reply_to_message_id'] = message_id
            
            # Send the file
            response = requests.post(url, files=files, data=data)
            response.raise_for_status()
            return True
            
    except requests.RequestException as e:
        print(f"Error sending document to Telegram: {e}")
        return False
