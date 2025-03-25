import os
import shutil
import subprocess
import logging
import time
import uuid
from pathlib import Path
from cryptography.fernet import Fernet
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("quantumveil_bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Replace with your actual values
API_TOKEN = "8041831914:AAEBmBIqZoX0PCNrscUIVkx0hC9srjvOuHw"  # Get from BotFather
TELEGRAM_USER_ID = 123456789  # Replace with your numeric Telegram ID
KEY_PATH = os.path.expanduser("~/my_keystore.jks")  # Path to your keystore
KEY_ALIAS = "my_key_alias"  # Alias for your key in the keystore
KEY_PASSWORD = "my_password"  # Password for your keystore

# Initialize Telegram bot
bot = Bot(API_TOKEN)

async def generate_key():
    """Generate an AES encryption key and save with timestamp."""
    key = Fernet.generate_key()
    key_path = Path(f"quantum_veil_{int(time.time())}.key")
    key_path.write_bytes(key)
    logger.info(f"Generated encryption key: {key_path}")
    return key

async def encrypt_payload(payload_path: str) -> str:
    """Encrypt the APK payload."""
    if not os.path.exists(payload_path):
        raise FileNotFoundError(f"Payload file not found: {payload_path}")

    key = await generate_key()
    cipher_suite = Fernet(key)

    with open(payload_path, "rb") as file:
        payload_data = file.read()

    encrypted_data = cipher_suite.encrypt(payload_data)
    encrypted_path = f"{payload_path}.encrypted"

    with open(encrypted_path, "wb") as enc_file:
        enc_file.write(encrypted_data)

    logger.info(f"Encrypted payload to {encrypted_path}")
    return encrypted_path

async def create_quantum_veil_apk(original_apk: str, encrypted_payload: str) -> str:
    """Create a new APK with the encrypted payload embedded."""
    if not os.path.exists(original_apk) or not os.path.exists("apktool_2.7.0.jar"):
        raise FileNotFoundError(f"Required files missing: {original_apk} or apktool_2.7.0.jar")

    unique_id = str(uuid.uuid4())
    output_dir = f"decompiled_apk_{unique_id}"
    apk_output = f"QuantumVeil_{unique_id}.apk"

    try:
        subprocess.run(["java", "-jar", "apktool_2.7.0.jar", "d", original_apk, "-o", output_dir, "-f"], check=True)

        payload_name = Path(encrypted_payload).name
        dest_path = f"{output_dir}/res/raw/{payload_name}"
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy(encrypted_payload, dest_path)

        subprocess.run(["java", "-jar", "apktool_2.7.0.jar", "b", output_dir, "-o", apk_output], check=True)
        logger.info(f"Created QuantumVeil APK: {apk_output}")
        return apk_output
    finally:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)

async def sign_apk(apk_path: str) -> str:
    """Sign the APK with the provided keystore using jarsigner from JDK 17."""
    if not os.path.exists(apk_path) or not os.path.exists(KEY_PATH):
        raise FileNotFoundError(f"APK or keystore not found: {apk_path}, {KEY_PATH}")

    signed_apk = f"signed_{os.path.basename(apk_path)}"
    cmd = [
        "jarsigner", "-verbose", "-keystore", KEY_PATH,
        "-signedjar", signed_apk, apk_path, KEY_ALIAS,
        "-storepass", KEY_PASSWORD
    ]
    subprocess.run(cmd, check=True)
    logger.info(f"Signed APK: {signed_apk}")
    return signed_apk

async def send_processed_apk(update: Update, context: CallbackContext, file_path: str):
    """Send the processed APK to the user."""
    user_id = update.message.from_user.id

    if user_id != TELEGRAM_USER_ID:
        await update.message.reply_text("❌ Sorry, only the admin can use this bot!")
        logger.warning(f"Unauthorized access by user {user_id}")
        return

    if not os.path.exists(file_path):
        await update.message.reply_text("⚠️ Error: Processed APK not found!")
        logger.error(f"File not found: {file_path}")
        return

    with open(file_path, "rb") as file:
        await context.bot.send_document(chat_id=user_id, document=file, caption="✅ Here's your QuantumVeil-protected APK!")

    os.remove(file_path)
    logger.info(f"Sent and removed {file_path}")

async def start(update: Update, context: CallbackContext):
    """Handle the /start command."""
    await update.message.reply_text("👋 Hi! Send me an APK, and I'll process it with QuantumVeil protection automatically.")

async def handle_apk(update: Update, context: CallbackContext):
    """Automatically process an incoming APK file."""
    file = update.message.document
    if not file.mime_type == "application/vnd.android.package-archive":
        await update.message.reply_text("⚠️ Please send a valid APK file!")
        return

    file_path = await file.get_file().download()

    if not os.path.exists(file_path):
        await update.message.reply_text("⚠️ Error: Failed to download APK!")
        logger.error(f"Download failed: {file_path}")
        return

    await update.message.reply_text("✅ Got your APK! Processing now...")
    logger.info(f"Received APK: {file_path}")

    try:
        await update.message.reply_text("🔐 Encrypting the APK...")
        encrypted_payload = await encrypt_payload(file_path)

        await update.message.reply_text("📦 Embedding into a new APK...")
        quantumveil_apk = await create_quantum_veil_apk(file_path, encrypted_payload)

        await update.message.reply_text("🔏 Signing the APK...")
        signed_apk = await sign_apk(quantumveil_apk)

        await update.message.reply_text("✅ All done! Sending you the protected APK...")
        await send_processed_apk(update, context, signed_apk)

    except Exception as e:
        await update.message.reply_text(f"❌ Oops, something went wrong: {e}")
        logger.error(f"Processing failed: {e}")

async def main():
    """Start the bot and keep it running."""
    app = Application.builder().token(API_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.MimeType("application/vnd.android.package-archive"), handle_apk))

    logger.info("🤖 Bot is now running!")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
