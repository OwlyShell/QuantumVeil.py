import os
import shutil
import subprocess
import logging
import time
import uuid
from pathlib import Path
from cryptography.fernet import Fernet
from telegram import Bot, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('quantumveil_bot.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Replace with your actual values from environment variables
API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')  # Get from BotFather
TELEGRAM_USER_ID = os.getenv('TELEGRAM_USER_ID')  # Get from @userinfobot
KEY_PATH = os.path.expanduser(os.getenv('KEYSTORE_PATH'))  # Path to your keystore
KEY_ALIAS = os.getenv('KEY_ALIAS')  # Alias for your key in the keystore
KEY_PASSWORD = os.getenv('KEY_PASSWORD')  # Password for your keystore

# Initialize Telegram bot
bot = Bot(API_TOKEN)

def generate_key():
    """Generate an AES encryption key and save with timestamp."""
    key = Fernet.generate_key()
    key_path = Path(f'quantum_veil_{int(time.time())}.key')
    key_path.write_bytes(key)
    logger.info(f"Generated encryption key: {key_path}")
    return key

def encrypt_payload(payload_path: str) -> str:
    """Encrypt the APK payload."""
    if not os.path.exists(payload_path):
        raise FileNotFoundError(f"Payload file not found: {payload_path}")
    key = generate_key()
    cipher_suite = Fernet(key)
    with open(payload_path, 'rb') as file:
        payload_data = file.read()
    encrypted_data = cipher_suite.encrypt(payload_data)
    encrypted_path = f"{payload_path}.encrypted"
    with open(encrypted_path, 'wb') as enc_file:
        enc_file.write(encrypted_data)
    logger.info(f"Encrypted payload to {encrypted_path}")
    return encrypted_path

def create_quantum_veil_apk(original_apk: str, encrypted_payload: str) -> str:
    """Create a new APK with the encrypted payload embedded."""
    if not os.path.exists(original_apk) or not os.path.exists('apktool_2.7.0.jar'):
        raise FileNotFoundError(f"Required files missing: {original_apk} or apktool_2.7.0.jar")
    unique_id = str(uuid.uuid4())
    output_dir = f'decompiled_apk_{unique_id}'
    apk_output = f'QuantumVeil_{unique_id}.apk'
    try:
        subprocess.run(['java', '-jar', 'apktool_2.7.0.jar', 'd', original_apk, '-o', output_dir, '-f'], check=True)
        payload_name = Path(encrypted_payload).name
        dest_path = f'{output_dir}/res/raw/{payload_name}'
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy(encrypted_payload, dest_path)
        subprocess.run(['java', '-jar', 'apktool_2.7.0.jar', 'b', output_dir, '-o', apk_output], check=True)
        logger.info(f"Created QuantumVeil APK: {apk_output}")
        return apk_output
    finally:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)

def sign_apk(apk_path: str) -> str:
    """Sign the APK with the provided keystore using jarsigner from JDK 17."""
    if not os.path.exists(apk_path) or not os.path.exists(KEY_PATH):
        raise FileNotFoundError(f"APK or keystore not found: {apk_path}, {KEY_PATH}")
    signed_apk = f'signed_{os.path.basename(apk_path)}'
    cmd = [
        'jarsigner', '-verbose', '-keystore', KEY_PATH,
        '-signedjar', signed_apk, apk_path, KEY_ALIAS,
        '-storepass', KEY_PASSWORD
    ]
    subprocess.run(cmd, check=True)
    logger.info(f"Signed APK: {signed_apk}")
    return signed_apk

def send_processed_apk(update: Update, context: CallbackContext, file_path: str):
    """Send the processed APK to the user."""
    user_id = update.message.from_user.id
    if str(user_id) != TELEGRAM_USER_ID:
        update.message.reply_text("Sorry, only the admin can use this bot!")
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        return

    if not os.path.exists(file_path):
        update.message.reply_text("Error: Processed APK not found!")
        logger.error(f"File not found: {file_path}")
        return

    try:
        with open(file_path, 'rb') as file:
            bot.send_document(chat_id=user_id, document=file, caption="Here’s your QuantumVeil-protected APK!")
        logger.info(f"Sent and removed {file_path}")
    except Exception as e:
        update.message.reply_text("Error sending the APK. Please try again later.")
        logger.error(f"Failed to send APK: {e}")
    finally:
        os.remove(file_path)

def start(update: Update, context: CallbackContext):
    """Handle the /start command."""
    update.message.reply_text("Hi! Send me an APK, and I’ll process it with QuantumVeil protection automatically.")

def handle_apk(update: Update, context: CallbackContext):
    """Automatically process an incoming APK file."""
    file = update.message.document
    if file.mime_type != "application/vnd.android.package-archive":
        update.message.reply_text("Please send a valid APK file!")
        return

    file_path = file.get_file().download()
    if not os.path.exists(file_path):
        update.message.reply_text("Error: Failed to download APK!")
        logger.error(f"Download failed: {file_path}")
        return

    update.message.reply_text("Got your APK! Processing now...")
    logger.info(f"Received APK: {file_path}")
    encrypted_payload = None
    quantumveil_apk = None
    signed_apk = None

    try:
        update.message.reply_text("Encrypting the APK...")
        encrypted_payload = encrypt_payload(file_path)
        update.message.reply_text("Embedding into a new APK...")
        quantumveil_apk = create_quantum_veil_apk(file_path, encrypted_payload)
        update.message.reply_text("Signing the APK...")
        signed_apk = sign_apk(quantumveil_apk)
        update.message.reply_text("All done! Sending you the protected APK...")
        send_processed_apk(update, context, signed_apk)
    except Exception as e:
        update.message.reply_text(f"Oops, something went wrong: {e}")
        logger.error(f"Processing failed: {e}")
    finally:
        for temp_file in [file_path, encrypted_payload, quantumveil_apk]:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
                logger.info(f"Removed temporary file: {temp_file}")

def main():
    """Start the bot and keep it running."""
    updater = Updater(API_TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(MessageHandler(Filters.document.mime_type("application/vnd.android.package-archive"), handle_apk))
    updater.start_polling()
    logger.info("Bot is now running!")
    updater.idle()

if __name__ == '__main__':
    main()
