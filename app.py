import base64
import google.generativeai as genai
from PIL import Image, ImageDraw
from io import BytesIO
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import os
import uuid
import json

# Set up Gemini API key
genai.configure(api_key="AIzaSyBsXtDOrg3CjmC-3vHod5pZNanM9TXaKU8")

# Replace with your actual Telegram bot token
TELEGRAM_BOT_TOKEN = "7936586304:AAHHk0GTqJLJuHveDArAMu71LQbNznequMM"

# Set up Gemini model
model = genai.GenerativeModel(model_name="gemini-1.5-pro")

# Directory to save images and data
IMAGE_SAVE_DIR = "saved_images"
DATA_SAVE_DIR = "saved_data"
if not os.path.exists(IMAGE_SAVE_DIR):
    os.makedirs(IMAGE_SAVE_DIR)
if not os.path.exists(DATA_SAVE_DIR):
    os.makedirs(DATA_SAVE_DIR)

def draw_circles_on_image(image_bytes, objects):
    image = Image.open(BytesIO(image_bytes))
    draw = ImageDraw.Draw(image)
    for obj in objects:
        x1, y1, x2, y2 = obj.get('bbox', [0,0,0,0])
        center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
        radius = max((x2 - x1) // 2, (y2 - y1) // 2)
        draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), outline="red", width=3)
        draw.text((x1, y1), obj.get('label','unknown'), fill="red")
    output = BytesIO()
    image.save(output, format="JPEG")
    output.seek(0)
    return output

async def generate_image_title(image_bytes: bytes) -> str:
    try:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        prompt = "Generate a concise title for this image, focusing on the main elements. Be descriptive but short (max 7 words)."
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
            "discribe about image in 2 lines"
            "how many object and categaries eatch"
            "bullet point in 1 line objects, people, animals, background, colors, clothing, any actions or interactions happening, in "
            "bullet point in 1 line objects Also, mention if any objects or people are not able or appear in the foreground, background, or middle ground."
            "bold  the main elements"
        )
        response = model.generate_content([{
            'mime_type': 'image/jpeg',
            'data': base64_image
        }, prompt])
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
            "if there are some objects which you cannnot identify provide with label name unknown."
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

def save_image(image_bytes, title):
    file_name = f"{uuid.uuid4()}_{title.replace(' ', '_')}.jpg"
    file_path = os.path.join(IMAGE_SAVE_DIR, file_name)
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    return file_path

def save_data(data, title):
    file_name = f"{uuid.uuid4()}_{title.replace(' ', '_')}.json"
    file_path = os.path.join(DATA_SAVE_DIR, file_name)
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)
    return file_path


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
    image_path = save_image(image_bytes, title)
    analysis = await analyze_image(image_bytes)
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    data = {
        "image_bytes_base64": base64_image,
        "analysis_result": analysis,
        "detected_objects": objects,
        "image_path": image_path,
        "title": title
    }
    data_path = save_data(data,title)
    detected_objects_text = "\n".join([f"- {obj.get('label','unknown')} (Bounding Box: {obj.get('bbox',[0,0,0,0])})" for obj in objects])
    await update.message.reply_photo(photo=circled_image, caption=f"Title: {title}\nDetected Objects:")
    await update.message.reply_text(f"Detected Objects:\n{detected_objects_text}")
    await update.message.reply_text(f"Image Analysis:\n{analysis}")

async def search_image(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("Please provide search keywords after the /search command.")
        return
    keywords = " ".join(context.args).lower()
    found_images = []
    for filename in os.listdir(DATA_SAVE_DIR):
        if filename.endswith(".json"):
            file_path = os.path.join(DATA_SAVE_DIR, filename)
            with open(file_path, 'r') as f:
              try:
                data = json.load(f)
                if 'detected_objects' in data and isinstance(data['detected_objects'], list):
                   for obj in data['detected_objects']:
                     if 'label' in obj and keywords in obj['label'].lower():
                         found_images.append(data)
                         break
              except json.JSONDecodeError:
                print(f"could not decode {filename}")

    if not found_images:
        await update.message.reply_text("No images found matching those object labels.")
        return
    for data in found_images:
        image_path = data.get('image_path')
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as image_file:
                await update.message.reply_photo(photo=image_file, caption=f"Title: {data.get('title')}\nDescription: {data.get('analysis_result', 'No description')[:200]}...")
        else:
            await update.message.reply_text("Image not found")


async def history(update: Update, context: CallbackContext) -> None:
     history_text = "Analysis History:\n"
     for filename in os.listdir(DATA_SAVE_DIR):
        if filename.endswith(".json"):
            file_path = os.path.join(DATA_SAVE_DIR, filename)
            with open(file_path, 'r') as f:
              try:
                data = json.load(f)
                analysis_result = data.get('analysis_result', 'No analysis available')
                history_text += f"- Title: {data.get('title', 'No title')} - Description: {analysis_result[:100]}...\n"
                history_text += "-" * 20 + "\n"
              except json.JSONDecodeError:
                 print(f"could not decode {filename}")
     if "Description" not in history_text:
          await update.message.reply_text("No analysis history available.")
     else:
          await update.message.reply_text(history_text)


def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("search", search_image))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.run_polling()

if __name__ == "__main__":
    main()