import base64
import google.generativeai as genai
from PIL import Image, ImageDraw
from io import BytesIO
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import uuid
import json

# Set up Gemini API key
genai.configure(api_key="AIzaSyB87qoLuXGgFPJqgZWRTISypDYk-zT3nRc")

# Replace with your actual Telegram bot token
TELEGRAM_BOT_TOKEN = "7936586304:AAHHk0GTqJLJuHveDArAMu71LQbNznequMM"

# Set up Gemini model
model = genai.GenerativeModel(model_name="gemini-1.5-pro")

def draw_circles_on_image(image_bytes, objects):
    image = Image.open(BytesIO(image_bytes))
    draw = ImageDraw.Draw(image)
    for obj in objects:
        x1, y1, x2, y2 = obj.get('bbox', [0, 0, 0, 0])
        center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
        radius = max((x2 - x1) // 2, (y2 - y1) // 2)
        draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), outline="red", width=3)
        draw.text((x1, y1), obj.get('label', 'unknown'), fill="red")
    output = BytesIO()
    image.save(output, format="JPEG")
    output.seek(0)
    return output

async def generate_image_title(image_bytes: bytes) -> str:
    try:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        prompt = "Generate a concise title for this image, focusing on the main elements. Be descriptive long(max 15 lines."
        response = model.generate_content([
            {'mime_type': 'image/jpeg', 'data': base64_image},
            prompt
        ])
        return response.text.strip().replace('\n', '').replace('"', '')
    except Exception as e:
        return f"Error generating title: {e}"

async def analyze_image(image_bytes: bytes) -> str:
    try:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        prompt = (
            "Analyze the following image in detail. Describe the key elements in the image, including but not limited to: "
            "describe about image in 15 lines "
            "how many objects and categories each "
            "describe 1 to 2 lines objects, people, animals, background, colors, clothing, any actions or interactions happening, in "
            "describe 1 to 2 lines objects Also, mention if any objects or people are not able or appear in the foreground, background, or middle ground. "
            "highlight the main elements"
        )
        response = model.generate_content([
            {'mime_type': 'image/jpeg', 'data': base64_image},
            prompt
        ])
        return response.text
    except Exception as e:
        return f"An error occurred: {e}"

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Hi! Send me an image, and I'll analyze it for you.")

async def detect_objects(image_bytes):
    try:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        prompt = (
            "Identify the key objects in the image. Provide a list of objects with a label for each object. "
            "if there are some objects which you cannot identify provide with label name unknown. "
            "Give the answer in a json format with label and bbox with x1,y1,x2,y2"
        )
        response = model.generate_content([
            {'mime_type': 'image/jpeg', 'data': base64_image},
            prompt
        ])
        try:
            objects = json.loads(response.text)
        except json.JSONDecodeError:
            print(f"Json Error {response.text}")
            objects = []
        return objects
    except Exception as e:
        print(f"Error during object detection: {e}")
        return []

async def handle_photo(update: Update, context: CallbackContext) -> None:
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    objects = await detect_objects(image_bytes)
    if not isinstance(objects, list):
        objects = []
    circled_image = draw_circles_on_image(image_bytes, objects)
    title = await generate_image_title(image_bytes)
    if title.startswith("Error generating title"):
        title = "Untitled Image"
    analysis = await analyze_image(image_bytes)
    detected_objects_text = "\n".join([f"- {obj.get('label', 'unknown')} (Bounding Box: {obj.get('bbox', [0, 0, 0, 0])})" for obj in objects])
    await update.message.reply_photo(photo=circled_image, caption=f"Title: {title}\nDetected Objects:")
    await update.message.reply_text(f"Detected Objects:\n{detected_objects_text}")
    await update.message.reply_text(f"Image Analysis:\n{analysis}")

async def history(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("History feature has been disabled.")

def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.run_polling()

if __name__ == "__main__":
    main()
