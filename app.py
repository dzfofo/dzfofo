import os
import logging
# import uuid # Not used in the current code
import json # Used in json.dumps
import requests # Used by local phone data functions
# import io # Not used in the current code
import base64 # Used by local phone data functions
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_file, flash
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
# from PIL import Image, ImageDraw, ImageFont # Not used in current code
# No longer need urllib.parse.quote here if using utils.py functions correctly
from flask_login import LoginManager, login_user, logout_user, login_required, current_user


# --- Setup Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Import Utility Functions from utils.py ---
# Import *all* necessary functions and keys here
# Ensure the utils module is in the Python path or the same directory
try:
    from utils import (
        # preprocess_arabic_text, # REMOVED - use only within utils
        text_to_speech, # Centralized TTS function
        # voicerss_text_to_speech, # REMOVED - use only within text_to_speech
        call_openrouter_api, # Centralized OpenRouter function
        translate_text, # Centralized Translate function
        generate_image, # Centralized Image Generation function
        OPENROUTER_API_KEY, # Access keys loaded in utils module
        ELEVENLABS_API_KEY,
        STABILITY_API_KEY,
        VOICERSS_API_KEY # Also import VoiceRSS key
    )
    logger.info("Successfully imported functions and keys from utils.py")
except ImportError as e:
    logger.error(f"Failed to import from utils.py: {e}. Make sure utils.py is in the correct path.")
    # Define dummy functions/keys if import fails to prevent crashes, though core features won't work
    OPENROUTER_API_KEY = None
    ELEVENLABS_API_KEY = None
    STABILITY_API_KEY = None
    VOICERSS_API_KEY = None
    def text_to_speech(*args, **kwargs):
        logger.error("utils.text_to_speech not available.")
        # Return a structure similar to success for browser fallback simulation
        if 'text' in kwargs:
             return {'type': 'browser', 'text': kwargs['text']}
        return None # Return None if no text provided

    def call_openrouter_api(*args, **kwargs):
        logger.error("utils.call_openrouter_api not available.")
        return "عذراً، خدمات الذكاء الاصطناعي غير متاحة بسبب خطأ داخلي في التطبيق."
    def translate_text(*args, **kwargs):
        logger.error("utils.translate_text not available.")
        return None
    def generate_image(*args, **kwargs):
        logger.error("utils.generate_image not available.")
        return None


# --- Import Phone Assistant Module ---
# Assuming phone_assistant.py will also be refactored later to use utils
# Ensure phone_assistant.py is in the Python path or the same directory
try:
    from phone_assistant import suggest_phone, suggest_cheaper_alternative, get_advanced_comparison
    logger.info("Successfully imported functions from phone_assistant.py")
except ImportError as e:
     logger.error(f"Failed to import from phone_assistant.py: {e}. Phone assistant features will be disabled.")
     # Define dummy functions if import fails
     def suggest_phone(*args, **kwargs):
         return "عذراً، مساعد الهواتف غير متاح بسبب خطأ داخلي."
     def suggest_cheaper_alternative(*args, **kwargs):
          return "عذراً، وظيفة البحث عن بدائل غير متاحة."
     def get_advanced_comparison(*args, **kwargs):
          return "عذراً، وظيفة المقارنة المتقدمة غير متاحة."


# --- Base Class for SQLAlchemy models ---
class Base(DeclarativeBase):
    pass

# --- Initialize Flask app ---
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
# Use a strong default or env var for secret key
app.secret_key = os.environ.get("SESSION_SECRET", "yasmin_ai_default_development_key_CHANGE_ME")
if app.secret_key == "yasmin_ai_default_development_key_CHANGE_ME":
     logger.warning("Default session secret key is in use. Change SESSION_SECRET environment variable for production!")


# --- Configure session to use filesystem ---
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False # Session expires when browser closes
# Consider changing to True and setting SESSION_COOKIE_LIFETIME if persistent sessions are desired
Session(app)

# --- Configure SQLAlchemy ---
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Database configuration ---
# Get the PostgreSQL DATABASE_URL from environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    logger.warning("DATABASE_URL environment variable not set. Using SQLite for development.")
    DATABASE_URL = "sqlite:///yasmin_chat.db"
else:
    # Render may provide 'postgres://' instead of 'postgresql://'
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    logger.info(f"Using PostgreSQL database at {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'localhost'}")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
# Add silent=True to avoid warnings if options are not supported by the database (like SQLite)
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280,  # Slightly less than 5 minutes (common for timeouts)
    "pool_pre_ping": True,  # To check the connection before using it
    "pool_timeout": 10,   # Wait time to get a connection from the pool
}

# Initialize SQLAlchemy with the app and Base model
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# --- Database Models (placeholder - define in models.py) ---
# from models import User, Message # Example import if models.py exists

# Initialize flask-login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index' # Redirects unauthenticated users to the index page


# User loader function for Flask-Login
# This is a placeholder. Implement actual user loading from DB.
@login_manager.user_loader
def load_user(user_id):
    # from models import User
    # try:
    #     return User.query.get(int(user_id))
    # except Exception as e:
    #     logger.error(f"Error loading user {user_id}: {e}")
    #     return None
    logger.warning("load_user placeholder called. User model not implemented, returning None.")
    return None # Return None if user cannot be loaded


# --- Helper Functions ---
# Keep specific app helpers, but remove general utility functions moved to utils.py

def allowed_file(filename):
    """Check if uploaded file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# REMOVED duplicate preprocess_arabic_text (use utils.preprocess_arabic_text if needed locally)
# REMOVED duplicate text_to_speech (use utils.text_to_speech)
# REMOVED duplicate call_openrouter_api (use utils.call_openrouter_api)
# REMOVED duplicate translate_text (use utils.translate_text)


# --- Fallback responses (for when APIs fail or offline) ---
# Keep these as app-specific fallback messages
offline_responses = {
    "السلام عليكم": "وعليكم السلام! أنا ياسمين. للأسف، لا يوجد اتصال بالإنترنت حالياً.",
    "كيف حالك": "أنا بخير شكراً لك. لكن لا يمكنني الوصول للنماذج الذكية الآن بسبب انقطاع الإنترنت.",
    "مرحبا": "أهلاً بك! أنا ياسمين. أعتذر، خدمة الإنترنت غير متوفرة حالياً.",
    "شكرا": "على الرحب والسعة! أتمنى أن يعود الاتصال قريباً.",
    "مع السلامة": "إلى اللقاء! آمل أن أتمكن من مساعدتك بشكل أفضل عند عودة الإنترنت."
}
default_offline_response = "أعتذر، لا يمكنني معالجة طلبك الآن. يبدو أن هناك مشكلة في الاتصال بالإنترنت أو بخدمات الذكاء الاصطناعي."

# Mock AI Assistant / Feature Data - In a real application, this would come from a database
ASSISTANTS = [
    # Chat Bots
    {
        "id": "general",
        "name": "مساعد عام",
        "avatar": "https://images.unsplash.com/photo-1717501218636-a390f9ac5957?w=64&h=64&fit=crop&auto=format",
        "description": "للدردشة العامة والاستفسارات المتنوعة",
        "color": "linear-gradient(135deg, #10a37f, #0a8263)",
        "model": "openai/gpt-3.5-turbo",
        "system_instruction": "أنت مساعد ذكي ومفيد باللغة العربية اسمه ياسمين. أجب دائماً باللغة العربية الفصحى ما لم يطلب المستخدم لغة أخرى. قدم معلومات دقيقة وشاملة. تجنب الإجابات الطويلة جداً. اليوم هو 1 مايو 2025." # Specific system message for chat
    },
    {
        "id": "gpt4o",
        "name": "GPT-4o",
        "avatar": "https://images.unsplash.com/photo-1717501218636-a390f9ac5957?w=64&h=64&fit=crop&auto=format",
        "description": "معالجة متقدمة للغة الطبيعية",
        "color": "linear-gradient(135deg, #10a37f, #0a8263)",
        "model": "openai/gpt-4o",
        "system_instruction": "أنت مساعد ذكي باللغة العربية تستخدم نموذج GPT-4o. أجب بأسلوب احترافي ودقيق، وقدم معلومات تفصيلية عند الحاجة. اليوم هو 1 مايو 2025."
    },
    {
        "id": "claude",
        "name": "Claude 3.5",
        "avatar": "https://images.unsplash.com/photo-1717501218385-55bc3a95be94?w=64&h=64&fit=crop&auto=format",
        "description": "تفكير متعمق وتحليل شامل",
        "color": "linear-gradient(135deg, #9a48d0, #7a3aa4)",
         "model": "anthropic/claude-3-5-sonnet",
         "system_instruction": "أنت مساعد ذكي باللغة العربية تستخدم نموذج Claude 3.5 Sonnet. تركز على التحليل العميق وتقديم إجابات شاملة ومنظمة."
    },
    {
        "id": "gemini",
        "name": "Gemini 1.5",
        "avatar": "https://images.unsplash.com/photo-1612066473428-fb64473428-fb6833a0d855?w=64&h=64&fit=crop&auto=format",
        "description": "فهم متعدد الوسائط",
        "color": "linear-gradient(135deg, #4285f4, #0f9d58)",
        "model": "google/gemini-pro", # Note: Multimodal (vision) capabilities require different API calls usually
        "system_instruction": "أنت مساعد ذكي باللغة العربية تستخدم نموذج Gemini Pro. تتميز بقدراتك في معالجة أنواع مختلفة من المعلومات."
    },
    # Features that link to separate pages
    {
        "id": "voice_assistant_feature",
        "name": "المساعد الصوتي",
        "avatar": "https://images.unsplash.com/photo-1693722339588-66e64f8fd48a?w=64&h=64&fit=crop&auto=format", # Using the image from voice_assistant.html
        "description": "تحدث إلى المساعد الذكي باللغة العربية",
        "color": "linear-gradient(135deg, #e67e22, #d35400)", # Using the color from voice_assistant.html
        "url": "/voice_assistant", # Link to the voice assistant page
        "button_text": "استخدم المساعد الصوتي" # Custom button text for this feature
    },
     {
        "id": "audio_generator_feature",
        "name": "توليد الصوت",
        "avatar": "https://images.unsplash.com/photo-1616161560417-66d4db5892ec?w=64&h=64&fit=crop&auto=format", # ElevenLabs avatar
        "description": "تحويل نص لصوت طبيعي",
        "color": "linear-gradient(135deg, #ff5757, #c43a3a)",
        "url": "/audio-generator",
        "button_text": "توليد الصوت"
    },
    {
        "id": "tech_compare_feature",
        "name": "مقارنة الأجهزة",
        "avatar": "https://images.unsplash.com/photo-1530545002211-21753020f4c8?w=64&h=64&fit=crop&auto=format", # TechCompare avatar
        "description": "مقارنة مواصفات الهواتف الذكية",
        "color": "linear-gradient(135deg, #4a69bd, #3a59ad)",
        "url": "/compare",
        "button_text": "قارن الأجهزة"
    },
     {
        "id": "phone_assistant_feature",
        "name": "مساعد الهواتف",
        "avatar": "https://images.unsplash.com/photo-1599317193916-7bb9b7b7e744?w=64&h=64&fit=crop&auto=format", # PhoneAssistant avatar
        "description": "اقتراح الهاتف المناسب لمتطلباتك",
        "color": "linear-gradient(135deg, #fd1d1d, #f77062)",
        "url": "/phone-assistant",
        "button_text": "مساعد الهواتف"
    },
     {
        "id": "image_generator_feature",
        "name": "توليد الصور",
        "avatar": "https://images.unsplash.com/photo-1579546998516-e0d3cd0e3d4b?w=64&h=64&fit=crop&auto=format", # Abstract/creative image
        "description": "إنشاء صور من وصف نصي",
        "color": "linear-gradient(135deg, #3498db, #2980b9)",
        "url": "/image-generator",
        "button_text": "توليد الصور"
    }
]

# Suggested questions for chat - empty now as per user request
SUGGESTED_QUESTIONS = []

@app.route('/')
def index():
    """Render the welcome page or redirect to features if logged in."""
    # Redirect to features_hub if already logged in (username in session)
    # Consider using current_user.is_authenticated with Flask-Login for proper auth check
    if 'username' in session:
         return redirect(url_for('features_hub'))
    return render_template('welcome.html')

@app.route('/features')
# @login_required # Uncomment when Flask-Login is fully used
def features_hub():
    """Render the features hub page."""
    # Manual session check for now
    if 'username' not in session:
        return redirect(url_for('index'))

    # Pass available models/features to the template
    # You could add logic here to only show features based on available API keys
    # For example:
    # filtered_assistants = [a for a in ASSISTANTS if a.get("model") or (a.get("url") and a["id"] != "image_generator_feature") or (a["id"] == "image_generator_feature" and STABILITY_API_KEY)]

    return render_template('features_hub.html',
                          username=session.get('username', ''),
                          assistants=ASSISTANTS) # Pass the full list for now


@app.route('/chat/<assistant_id>')
# @login_required # Uncomment when Flask-Login is fully used
def chat(assistant_id):
    """Render the chat page for a specific assistant."""
    # Manual session check for now
    if 'username' not in session:
        return redirect(url_for('index'))

    # Find the selected assistant configuration
    assistant_config = next((a for a in ASSISTANTS if a['id'] == assistant_id), None)

    # If assistant ID not found or is a feature link (not a chat model), default to general chat config
    if not assistant_config or "model" not in assistant_config:
        logger.warning(f"Chat assistant ID '{assistant_id}' config not found or not a chat bot. Defaulting to general.")
        assistant_config = next((a for a in ASSISTANTS if a['id'] == 'general' and "model" in a), None)
        if not assistant_config:
             return "Error: Default chat assistant configuration not found.", 500 # Hard error if no default chat assistant exists
        # Update assistant_id for the template in case it defaulted
        assistant_id = assistant_config['id']


    return render_template('chat.html',
                          username=session.get('username', ''),
                          assistant=assistant_config, # Pass the found/default config
                          suggested_questions=SUGGESTED_QUESTIONS)


@app.route('/compare')
# @login_required # Uncomment when Flask-Login is fully used
def compare():
    """Render the device comparison page."""
    # Manual session check for now
    if 'username' not in session:
        return redirect(url_for('index'))

    return render_template('compare.html',
                          username=session.get('username', ''))


@app.route('/api/save_username', methods=['POST'])
# NOTE: This should ideally integrate with Flask-Login and potentially database User model
def api_save_username():
    """API endpoint to save username to session and redirect to features."""
    data = request.get_json()
    username = data.get('username', '').strip()

    if not username:
        return jsonify({"status": "error", "message": "اسم المستخدم مطلوب"}), 400

    # Store username in session (temporary login state)
    session['username'] = username
    # In a real app, create/get user, then login_user(user)

    # Redirect to features_hub after successful save
    return jsonify({"status": "success", "redirect": url_for('features_hub')})


@app.route('/api/logout', methods=['POST'])
# @login_required # Add this decorator when Flask-Login is fully implemented
def api_logout():
    """API endpoint to log out the user."""
    # Logout the user if Flask-Login is used
    # logout_user() # Uncomment when Flask-Login is fully used
    # Clear the session
    session.clear()
    return jsonify({"status": "success", "redirect": url_for('index')})


@app.route('/api/chat_message', methods=['POST'])
# @login_required # Add this decorator when Flask-Login is fully implemented
def api_chat_message():
    """API endpoint to handle chat messages with AI assistants."""
    # Manual session check for now
    if 'username' not in session:
        # Also check with Flask-Login: if not current_user.is_authenticated: ...
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401

    data = request.get_json()
    message = data.get('message', '').strip()
    assistant_id = data.get('assistant_id', 'general') # Default to 'general'

    if not message:
        # Return success for empty message but with no response text
        return jsonify({
            "status": "success",
            "response": "",
            "timestamp": datetime.now().strftime("%Y/%m/%d %I:%M %p").replace("AM", "ص").replace("PM", "م")
        })


    # Find the selected assistant configuration
    assistant_config = next((a for a in ASSISTANTS if a['id'] == assistant_id and "model" in a), None)

    # Fallback to general assistant if ID is invalid or not a chat model
    if not assistant_config:
        logger.warning(f"Chat assistant ID '{assistant_id}' config not found or not a chat bot. Defaulting to general.")
        assistant_config = next((a for a in ASSISTANTS if a['id'] == 'general' and "model" in a), None)
        if not assistant_config:
             return jsonify({"status": "error", "message": "لا يمكن العثور على إعدادات المساعد المطلوب أو المساعد العام."}), 500
        # Update assistant_id in case it was invalid, for logging/tracking if needed
        assistant_id = assistant_config['id']

    model = assistant_config['model']
    system_instruction = assistant_config.get('system_instruction') # Get specific instruction from config

    # Create message object for API calls
    # In a real app, fetch previous messages from DB for context
    messages = [{"role": "user", "content": message}]

    # Use the centralized OpenRouter API call from utils.py
    # Pass the specific system message from the config, which will override the default in utils if present
    ai_response = call_openrouter_api(
        messages,
        model=model,
        temperature=0.7, # Can make temperature model-specific in ASSISTANTS config
        max_tokens=2000, # Can make max_tokens model-specific
        system_message=system_instruction # Pass specific instruction from config
    )

    # Handle API failure (call_openrouter_api from utils returns an error string or None)
    if ai_response is None or "حدث خطأ" in ai_response or "عذراً" in ai_response or "استغرق الرد" in ai_response:
        logger.error(f"AI response error for chat assistant {assistant_id}: {ai_response}")
        # Provide a specific fallback message for chat failures
        if not OPENROUTER_API_KEY:
             ai_response = f"عذراً {session.get('username', '')}، لا يمكنني الوصول إلى نماذج الذكاء الاصطناعي حالياً (مفتاح OpenRouter غير متوفر)."
        else:
             # Attempt basic offline response lookup as a last resort if API failed
            fallback_found = False
            for key, value in offline_responses.items():
                if key in message.lower():
                    ai_response = value
                    fallback_found = True
                    break
            if not fallback_found:
                # If API failed and no basic fallback matched, use default offline
                ai_response = default_offline_response + " (سبب إضافي: فشل استدعاء API)."

        # Return status as error, but include the fallback message
        return jsonify({
            "status": "error",
            "message": ai_response, # The error message is the response text
            "response": ai_response, # Also include in 'response' field for consistency with success
            "timestamp": datetime.now().strftime("%Y/%m/%d %I:%M %p").replace("AM", "ص").replace("PM", "م")
        }), 500 # Use 500 status for backend processing failure


    # Get current timestamp in Arabic format
    now = datetime.now()
    arabic_timestamp = now.strftime("%Y/%m/%d %I:%M %p").replace("AM", "ص").replace("PM", "م")

    # Store message in the database (in a complete implementation)
    # from models import Message
    # user_id = current_user.id # Get user ID from Flask-Login
    # NewMessage = Message(user_id=user_id, assistant_id=assistant_id, user_content=message, ai_content=ai_response, timestamp=now)
    # db.session.add(NewMessage)
    # db.session.commit()


    return jsonify({
        "status": "success",
        "response": ai_response,
        "timestamp": arabic_timestamp
    })


# Phone data retrieval and comparison functions
# These functions are NOT duplicated in utils.py in the provided code, so they remain here.
# They use the external Mobile Specs API.
# The suggest_phone, suggest_cheaper_alternative, get_advanced_comparison in phone_assistant.py
# *do* use call_openrouter_api. They should be refactored in phone_assistant.py later to use utils.

import requests # Keep requests import as these local functions use it directly

def fetch_phone_data(phone_id):
    """
    Fetch phone data from Mobile Specs API
    Documentation: https://github.com/azharimm/phone-specs-api
    """
    try:
        # Use the free Mobile Specs API to get phone data
        url = f"https://api-mobilespecs.azharimm.dev/v2/brands/{phone_id}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Mobile Specs API error (brands): {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error fetching phone brands data: {e}")
        return None

def get_phone_brands():
    """Get list of phone brands from the API"""
    try:
        url = "https://api-mobilespecs.azharimm.dev/v2/brands"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            # Extract brand info with Arabic names where possible
            brands = []
            for brand in data.get('data', []):
                arabic_name = get_arabic_brand_name(brand.get('brand_name', ''))
                brands.append({
                    'brand_id': brand.get('brand_slug', ''),
                    'brand_name': brand.get('brand_name', ''),
                    'arabic_name': arabic_name,
                    'device_count': brand.get('device_count', 0)
                })
            return brands
        else:
            logger.error(f"Mobile Specs API error (brands list): {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logger.error(f"Error fetching phone brands list: {e}")
        return []

def get_phones_by_brand(brand_id):
    """Get phones by brand ID"""
    try:
        url = f"https://api-mobilespecs.azharimm.dev/v2/brands/{brand_id}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            return data.get('data', {}).get('phones', [])
        else:
            logger.error(f"Mobile Specs API error (phones by brand {brand_id}): {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logger.error(f"Error fetching phones by brand {brand_id}: {e}")
        return []

def get_phone_details(phone_slug):
    """Get detailed information about a specific phone"""
    try:
        url = f"https://api-mobilespecs.azharimm.dev/v2/{phone_slug}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            # Process and translate specifications to Arabic
            specs = data.get('data', {}).get('specifications', [])
            arabic_specs = process_and_translate_specs(specs)

            # Add the processed specs back to data
            if 'data' in data:
                data['data']['arabic_specs'] = arabic_specs
                return data.get('data', {})
            else:
                 logger.error(f"Mobile Specs API did not return 'data' key for {phone_slug}: {data}")
                 return None
        else:
            logger.error(f"Mobile Specs API error (details for {phone_slug}): {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error fetching phone details for {phone_slug}: {e}")
        return None

def get_latest_phones():
    """Get latest phone models"""
    try:
        url = "https://api-mobilespecs.azharimm.dev/v2/latest"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            return data.get('data', {}).get('phones', [])
        else:
            logger.error(f"Mobile Specs API error (latest phones): {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logger.error(f"Error fetching latest phones: {e}")
        return []

def get_arabic_brand_name(brand_name):
    """Convert brand names to Arabic"""
    arabic_brands = {
        "Samsung": "سامسونج",
        "Apple": "آبل",
        "Xiaomi": "شاومي",
        "Huawei": "هواوي",
        "OPPO": "أوبو",
        "Vivo": "فيفو",
        "Realme": "ريلمي",
        "OnePlus": "ون بلس",
        "Nokia": "نوكيا",
        "Sony": "سوني",
        "Google": "جوجل",
        "Motorola": "موتورولا",
        "LG": "إل جي",
        "Lenovo": "لينوفو",
        "Asus": "أسوس",
        "HTC": "إتش تي سي",
        "Honor": "أونور"
    }
    return arabic_brands.get(brand_name, brand_name)

# process_and_translate_specs and extract_key_phone_specs remain here as they process Mobile Specs API data
def process_and_translate_specs(specs):
    """
    Process and translate phone specifications to Arabic
    """
    arabic_specs = {}

    # Translation mapping for common specification titles
    title_translations = {
        "Network": "الشبكة",
        "Launch": "تاريخ الإصدار",
        "Body": "الهيكل",
        "Display": "الشاشة",
        "Platform": "نظام التشغيل",
        "Memory": "الذاكرة",
        "Main Camera": "الكاميرا الخلفية",
        "Selfie camera": "الكاميرا الأمامية",
        "Sound": "الصوت",
        "Comms": "الاتصالات",
        "Features": "الميزات",
        "Battery": "البطارية",
        "Misc": "متفرقات",
        "Tests": "الاختبارات"
    }

    # Process each specification group
    for spec in specs:
        title = spec.get('title', '')
        arabic_title = title_translations.get(title, title)

        spec_items = []
        for item in spec.get('specs', []):
            key = item.get('key', '')
            values = item.get('val', [])

            if isinstance(values, list):
                value_str = ', '.join(values)
            else:
                value_str = str(values)

            spec_items.append({
                'key': key,
                'value': value_str
            })

        arabic_specs[arabic_title] = spec_items

    return arabic_specs

def extract_key_phone_specs(phone_details):
    """
    Extract and format key specifications from phone details
    """
    if not phone_details:
        return {
            "name": "غير معروف",
            "brand": "غير معروف",
            "os": "غير معروف",
            "display": "غير معروف",
            "processor": "غير معروف",
            "ram": "غير معروف",
            "camera": "غير معروف",
            "battery": "غير معروف",
            "storage": "غير معروف",
            "network": "غير معروف",
            "release_date": "غير معروف",
            "price": "غير معروف",
            "image": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?q=80&w=880&auto=format&fit=crop",
            "nfc": "غير معروف",
            "fast_charging": "غير معروف",
            "rating": "غير معروف"
        }
    
    # Initialize with default structure
    key_specs = {
        "name": phone_details.get('phone_name', 'غير معروف'),
        "brand": "غير معروف", # Will attempt to extract below
        "os": "غير معروف",
        "display": "غير معروف",
        "processor": "غير معروف",
        "ram": "غير معروف",
        "camera": "غير معروف",
        "battery": "غير معروف",
        "storage": "غير معروف",
        "network": "غير معروف",
        "release_date": "غير معروف",
        "price": "غير معروف", # Price is not usually in Mobile Specs API
        "image": phone_details.get('phone_images', [''])[0] if phone_details.get('phone_images') else "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?q=80&w=880&auto=format&fit=crop",
        "nfc": "غير معروف",
        "fast_charging": "غير معروف",
        "rating": "غير معروف" # Rating is not in Mobile Specs API
    }
    
    # Extract brand from name if available
    if ' ' in key_specs['name']:
        key_specs['brand'] = key_specs['name'].split(' ')[0]
    
    # Process Arabic specs if available
    arabic_specs = phone_details.get('arabic_specs', {})
    
    # Extract Platform/OS info
    if 'نظام التشغيل' in arabic_specs:
        for item in arabic_specs['نظام التشغيل']:
            if 'OS' in item['key']:
                key_specs['os'] = item['value']
            elif 'Chipset' in item['key']:
                key_specs['processor'] = item['value']
    
    # Extract Display info
    if 'الشاشة' in arabic_specs:
        for item in arabic_specs['الشاشة']:
            if 'Size' in item['key']:
                display_info = item['value']
                if 'Resolution' in item['key']:
                    display_info += f", {item['value']}"
                key_specs['display'] = display_info
    
    # Extract Memory info
    if 'الذاكرة' in arabic_specs:
        for item in arabic_specs['الذاكرة']:
            if 'RAM' in item['key'] or 'Internal' in item['key']:
                key_specs['ram'] = item['value']
                key_specs['storage'] = item['value']
    
    # Extract Main Camera info
    if 'الكاميرا الخلفية' in arabic_specs:
        camera_specs = []
        for item in arabic_specs['الكاميرا الخلفية']:
            camera_specs.append(item['value'])
        
        if camera_specs:
            key_specs['camera'] = ', '.join(camera_specs)
    
    # Extract Battery info
    if 'البطارية' in arabic_specs:
        for item in arabic_specs['البطارية']:
            if 'Type' in item['key']:
                key_specs['battery'] = item['value']
            elif 'Charging' in item['key'] and 'fast' in item['value'].lower():
                key_specs['fast_charging'] = 'نعم'
    
    # Extract Network info
    if 'الشبكة' in arabic_specs:
        for item in arabic_specs['الشبكة']:
            if '5G' in item['value']:
                key_specs['network'] = '5G'
            elif '4G' in item['value'] and key_specs['network'] == 'غير معروف':
                key_specs['network'] = '4G'
    
    # Extract Release date
    if 'تاريخ الإصدار' in arabic_specs:
        for item in arabic_specs['تاريخ الإصدار']:
            if 'Status' in item['key'] or 'Announced' in item['key']:
                key_specs['release_date'] = item['value']
    
    # Extract NFC
    if 'الاتصالات' in arabic_specs:
        for item in arabic_specs['الاتصالات']:
            if 'NFC' in item['key'] and 'Yes' in item['value']:
                key_specs['nfc'] = 'نعم'
    
    # Provide a default rating
    key_specs['rating'] = '4.2/5'
    
    return key_specs

# Phone comparison function for API endpoint
def find_phone_match(query):
    """Find phone that matches the query using API data"""
    # Try to find exact match first
    brand_matches = []
    
    # Get all brands
    brands = get_phone_brands()
    for brand in brands:
        brand_name = brand.get('brand_name', '').lower()
        if brand_name in query.lower():
            brand_matches.append(brand)
    
    # If we found brand matches, search for phones in those brands
    if brand_matches:
        for brand in brand_matches:
            phones = get_phones_by_brand(brand.get('brand_id'))
            
            for phone in phones:
                phone_name = phone.get('phone_name', '').lower()
                if query.lower() in phone_name or any(word in phone_name for word in query.lower().split()):
                    # Get detailed specs for this phone
                    phone_slug = phone.get('slug')
                    if phone_slug:
                        phone_details = get_phone_details(phone_slug)
                        return extract_key_phone_specs(phone_details)
    
    # If no match found, try to get latest phones and return the first one
    latest_phones = get_latest_phones()
    if latest_phones:
        phone_slug = latest_phones[0].get('slug')
        if phone_slug:
            phone_details = get_phone_details(phone_slug)
            return extract_key_phone_specs(phone_details)
    
    # Fallback to hardcoded data if API fails
    return fallback_phone_data(query)

def fallback_phone_data(query):
    """Provide fallback phone data when API fails"""
    # Hardcoded phone data for common phones
    dummy_devices = {
        "samsung galaxy s23 ultra": {
            "name": "Samsung Galaxy S23 Ultra",
            "brand": "Samsung",
            "os": "Android 13",
            "display": "6.8 بوصة، AMOLED، 1440 × 3088 بكسل",
            "processor": "Snapdragon 8 Gen 2",
            "ram": "12 جيجابايت",
            "camera": "200 ميجابكسل (رئيسية) + 10 ميجابكسل (مقربة) + 12 ميجابكسل (واسعة)",
            "battery": "5000 مللي أمبير",
            "storage": "256 جيجابايت / 512 جيجابايت / 1 تيرابايت",
            "network": "5G",
            "release_date": "فبراير 2023",
            "price": "1199 دولار",
            "image": "https://fdn2.gsmarena.com/vv/pics/samsung/samsung-galaxy-s23-ultra-5g-1.jpg",
            "nfc": "نعم",
            "fast_charging": "45 واط",
            "rating": "4.8/5"
        },
        "iphone 15 pro max": {
            "name": "iPhone 15 Pro Max",
            "brand": "Apple",
            "os": "iOS 17",
            "display": "6.7 بوصة، OLED، 1290 × 2796 بكسل",
            "processor": "A17 Pro",
            "ram": "8 جيجابايت",
            "camera": "48 ميجابكسل (رئيسية) + 12 ميجابكسل (مقربة) + 12 ميجابكسل (واسعة)",
            "battery": "4422 مللي أمبير",
            "storage": "256 جيجابايت / 512 جيجابايت / 1 تيرابايت",
            "network": "5G",
            "release_date": "سبتمبر 2023",
            "price": "1199 دولار",
            "image": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-15-pro-max-1.jpg",
            "nfc": "نعم",
            "fast_charging": "20 واط",
            "rating": "4.7/5"
        },
        "google pixel 7 pro": {
            "name": "Google Pixel 7 Pro",
            "brand": "Google",
            "os": "Android 13",
            "display": "6.7 بوصة، OLED، 1440 × 3120 بكسل",
            "processor": "Google Tensor G2",
            "ram": "12 جيجابايت",
            "camera": "50 ميجابكسل (رئيسية) + 48 ميجابكسل (مقربة) + 12 ميجابكسل (واسعة)",
            "battery": "5000 مللي أمبير",
            "storage": "128 جيجابايت / 256 جيجابايت / 512 جيجابايت",
            "network": "5G",
            "release_date": "أكتوبر 2022",
            "price": "899 دولار",
            "image": "https://fdn2.gsmarena.com/vv/pics/google/google-pixel7-pro-1.jpg",
            "nfc": "نعم",
            "fast_charging": "23 واط",
            "rating": "4.5/5"
        },
        "xiaomi 13 pro": {
            "name": "Xiaomi 13 Pro",
            "brand": "Xiaomi",
            "os": "Android 13",
            "display": "6.73 بوصة، OLED، 1440 × 3200 بكسل",
            "processor": "Snapdragon 8 Gen 2",
            "ram": "12 جيجابايت",
            "camera": "50 ميجابكسل (رئيسية) + 50 ميجابكسل (مقربة) + 50 ميجابكسل (واسعة)",
            "battery": "4820 مللي أمبير",
            "storage": "256 جيجابايت / 512 جيجابايت",
            "network": "5G",
            "release_date": "ديسمبر 2022",
            "price": "899 دولار",
            "image": "https://fdn2.gsmarena.com/vv/pics/xiaomi/xiaomi-13-pro-1.jpg",
            "nfc": "نعم",
            "fast_charging": "120 واط",
            "rating": "4.6/5"
        },
        "oneplus 11": {
            "name": "OnePlus 11",
            "brand": "OnePlus",
            "os": "Android 13",
            "display": "6.7 بوصة، AMOLED، 1440 × 3216 بكسل",
            "processor": "Snapdragon 8 Gen 2",
            "ram": "16 جيجابايت",
            "camera": "50 ميجابكسل (رئيسية) + 32 ميجابكسل (مقربة) + 48 ميجابكسل (واسعة)",
            "battery": "5000 مللي أمبير",
            "storage": "256 جيجابايت / 512 جيجابايت",
            "network": "5G",
            "release_date": "يناير 2023",
            "price": "699 دولار",
            "image": "https://fdn2.gsmarena.com/vv/pics/oneplus/oneplus-11-1.jpg",
            "nfc": "نعم",
            "fast_charging": "100 واط",
            "rating": "4.5/5"
        }
    }
    
    # Simple fuzzy matching
    for key, device in dummy_devices.items():
        if query.lower() in key or key in query.lower():
            return device
    
    # Create a fallback device if no match is found
    return {
        "name": query.title(),
        "brand": "غير معروف",
        "os": "غير معروف",
        "display": "غير معروف",
        "processor": "غير معروف",
        "ram": "غير معروف",
        "camera": "غير معروف",
        "battery": "غير معروف",
        "storage": "غير معروف",
        "network": "غير معروف",
        "release_date": "غير معروف",
        "price": "غير معروف",
        "image": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?q=80&w=880&auto=format&fit=crop",
        "nfc": "غير معروف",
        "fast_charging": "غير معروف",
        "rating": "غير معروف"
    }

@app.route('/api/compare_devices', methods=['POST'])
def compare_devices():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401
    
    data = request.get_json()
    device1 = data.get('device1', '').strip()
    device2 = data.get('device2', '').strip()
    
    if not device1 or not device2:
        return jsonify({"status": "error", "message": "يرجى إدخال اسم الجهازين"}), 400
    
    # Use the new phone matching function that uses real API data
    device1_specs = find_phone_match(device1)
    device2_specs = find_phone_match(device2)
    
    return jsonify({
        "status": "success",
        "device1": device1_specs,
        "device2": device2_specs
    })

@app.route('/audio-generator')
def audio_generator():
    """Audio generator page with ElevenLabs integration"""
    if 'username' not in session:
        return redirect(url_for('index'))
    
    return render_template('audio_generator.html', 
                          username=session.get('username', ''))

@app.route('/api/text_to_speech', methods=['POST'])
def api_text_to_speech():
    """API endpoint to convert text to speech using ElevenLabs"""
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401
    
    data = request.get_json()
    text = data.get('text', '').strip()
    voice_id = data.get('voice_id', "EXAVITQu4vr4xnSDxMaL")  # Default male Arabic voice
    
    if not text:
        return jsonify({"status": "error", "message": "النص مطلوب"}), 400
    
    # Check if we have ElevenLabs API key
    if not ELEVENLABS_API_KEY:
        return jsonify({
            "status": "error", 
            "message": "مفتاح ElevenLabs API غير متوفر. يرجى إضافته في صفحة الإعدادات. سيتم استخدام المتصفح كبديل."
        }), 500
    
    try:
        # Call ElevenLabs API
        audio_content = text_to_speech(text, voice_id)
        
        if not audio_content:
            return jsonify({
                "status": "error", 
                "message": "حدث خطأ أثناء تحويل النص إلى صوت. سيتم استخدام المتصفح كبديل."
            }), 500
        
        # Encode audio content to base64 for sending as JSON
        import base64
        audio_base64 = base64.b64encode(audio_content).decode('utf-8')
        
        # Return audio as base64
        return jsonify({
            "status": "success",
            "message": "تم تحويل النص إلى صوت بنجاح",
            "audio": audio_base64
        })
    
    except Exception as e:
        logger.error(f"Error in text-to-speech API: {e}")
        return jsonify({
            "status": "error", 
            "message": f"حدث خطأ: {str(e)}. سيتم استخدام المتصفح كبديل."
        }), 500

@app.route('/api/translate', methods=['POST'])
def api_translate():
    """API endpoint to translate text"""
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401
    
    data = request.get_json()
    text = data.get('text', '').strip()
    target_lang = data.get('target_lang', 'ar')  # Default to Arabic
    
    if not text:
        return jsonify({"status": "error", "message": "النص مطلوب"}), 400
    
    translated_text = translate_text(text, target_lang)
    
    if not translated_text:
        return jsonify({
            "status": "error", 
            "message": "حدث خطأ أثناء ترجمة النص"
        }), 500
    
    return jsonify({
        "status": "success",
        "translated_text": translated_text
    })

@app.route('/settings')
def settings():
    """Settings page for API keys and speech recognition settings"""
    if 'username' not in session:
        return redirect(url_for('index'))
    
    # Check if API keys are set
    openrouter_connected = bool(OPENROUTER_API_KEY)
    elevenlabs_connected = bool(ELEVENLABS_API_KEY)
    stability_connected = bool(STABILITY_API_KEY)
    
    # Mask API keys for display
    openrouter_key_masked = "••••••••" if OPENROUTER_API_KEY else ""
    elevenlabs_key_masked = "••••••••" if ELEVENLABS_API_KEY else ""
    stability_key_masked = "••••••••" if STABILITY_API_KEY else ""
    
    # Get speech settings from session or use defaults
    use_deepspeech = session.get('use_deepspeech', False)
    audio_feedback = session.get('audio_feedback', True)
    auto_send = session.get('auto_send', True)
    arabic_dialect = session.get('arabic_dialect', 'ar-SA')
    
    return render_template('settings.html',
                          username=session.get('username', ''),
                          openrouter_connected=openrouter_connected,
                          elevenlabs_connected=elevenlabs_connected,
                          stability_connected=stability_connected,
                          openrouter_key_masked=openrouter_key_masked,
                          elevenlabs_key_masked=elevenlabs_key_masked,
                          stability_key_masked=stability_key_masked,
                          use_deepspeech=use_deepspeech,
                          audio_feedback=audio_feedback,
                          auto_send=auto_send,
                          arabic_dialect=arabic_dialect)

@app.route('/api/save_speech_settings', methods=['POST'])
def save_speech_settings():
    """Save speech recognition settings"""
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401
    
    data = request.get_json()
    
    # Save settings to session
    session['use_deepspeech'] = data.get('use_deepspeech', False)
    session['audio_feedback'] = data.get('audio_feedback', True)
    session['auto_send'] = data.get('auto_send', True)
    session['arabic_dialect'] = data.get('arabic_dialect', 'ar-SA')
    
    return jsonify({"status": "success"})

@app.route('/api/save_api_keys', methods=['POST'])
def save_api_keys():
    """Save API keys (in a real app, these would be stored securely)"""
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401
    
    data = request.get_json()
    
    # Get keys from request
    openrouter_key = data.get('openrouter_key', '')
    elevenlabs_key = data.get('elevenlabs_key', '')
    stability_key = data.get('stability_key', '')
    
    # In a real app, these would be stored securely in a database or vault
    # For this demo, we'll just update the global variables temporarily
    global OPENROUTER_API_KEY, ELEVENLABS_API_KEY, STABILITY_API_KEY
    
    # Only update if keys are provided
    if openrouter_key and openrouter_key != "••••••••":
        OPENROUTER_API_KEY = openrouter_key
        # Update environment variable
        os.environ["OPENROUTER_API_KEY"] = openrouter_key
    
    if elevenlabs_key and elevenlabs_key != "••••••••":
        ELEVENLABS_API_KEY = elevenlabs_key
        # Update environment variable
        os.environ["ELEVENLABS_API_KEY"] = elevenlabs_key
    
    if stability_key and stability_key != "••••••••":
        STABILITY_API_KEY = stability_key
        # Update environment variable
        os.environ["STABILITY_API_KEY"] = stability_key
    
    return jsonify({"status": "success"})

# --- Phone Assistant Routes ---
@app.route('/phone-assistant')
def phone_assistant():
    """Phone recommendation assistant page"""
    if 'username' not in session:
        return redirect(url_for('index'))
    
    return render_template('assistant.html', username=session.get('username', ''))

@app.route('/api/suggest_phone', methods=['POST'])
def api_suggest_phone():
    """API endpoint to suggest phones based on user requirements"""
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401
    
    data = request.get_json()
    requirements = data.get('requirements', '').strip()
    
    if not requirements:
        return jsonify({"status": "error", "message": "يرجى إدخال متطلباتك"}), 400
    
    # Get suggestion from phone assistant
    suggestion = suggest_phone(requirements)
    
    return jsonify({
        "status": "success",
        "suggestion": suggestion
    })

@app.route('/api/cheaper_alternative', methods=['POST'])
def api_cheaper_alternative():
    """API endpoint to get cheaper alternatives for a specific phone"""
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401
    
    data = request.get_json()
    requirements = data.get('requirements', '').strip()
    
    if not requirements:
        return jsonify({"status": "error", "message": "يرجى إدخال اسم الهاتف"}), 400
    
    # Get cheaper alternatives
    alternatives = suggest_cheaper_alternative(requirements)
    
    # Make a recommendation
    recommendation = suggest_phone(f"أريد بديل أرخص لـ {requirements} مع الحفاظ على جودة الأداء.")
    
    return jsonify({
        "status": "success",
        "suggestion": recommendation,
        "alternatives": alternatives
    })

@app.route('/api/advanced_comparison', methods=['POST'])
def api_advanced_comparison():
    """API endpoint to get advanced comparison between two phones"""
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401
    
    data = request.get_json()
    phone1 = data.get('phone1', '').strip()
    phone2 = data.get('phone2', '').strip()
    
    if not phone1 or not phone2:
        return jsonify({"status": "error", "message": "يرجى إدخال أسماء الهواتف"}), 400
    
    # Get advanced comparison
    comparison = get_advanced_comparison(phone1, phone2)
    
    return jsonify({
        "status": "success",
        "comparison": comparison
    })

# --- Voice Assistant Routes ---
from voice_assistant import text_to_speech as va_text_to_speech, call_openrouter_api as va_call_openrouter

@app.route('/voice_assistant')
def voice_assistant():
    """Voice assistant page with speech recognition and AI responses"""
    if 'username' not in session:
        return redirect(url_for('index'))
    
    # Determine models available based on API keys
    has_openrouter = bool(OPENROUTER_API_KEY)
    has_elevenlabs = bool(ELEVENLABS_API_KEY)
    
    return render_template('voice_assistant.html', 
                         username=session.get('username', ''),
                         has_openrouter=has_openrouter,
                         has_elevenlabs=has_elevenlabs)

@app.route("/api/voice_assistant", methods=["POST"])
def api_voice_assistant():
    """Process voice input and generate AI response"""
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401
    
    data = request.get_json()
    user_prompt = data.get("prompt", "")
    model = data.get("model", "mistralai/mixtral-8x7b-instruct")
    
    if not user_prompt:
        return jsonify({"status": "error", "message": "لم يتم توفير نص للمعالجة"})
    
    # Call OpenRouter API to get AI response
    ai_response = va_call_openrouter(user_prompt, model=model)
    
    # Generate audio if ElevenLabs key is available
    audio_base64 = None
    if ELEVENLABS_API_KEY:
        voice_id = data.get("voice_id", "EXAVITQu4vr4xnSDxMaL")
        audio_base64 = va_text_to_speech(ai_response, voice_id=voice_id)
    
    return jsonify({
        "status": "success",
        "reply": ai_response,
        "audio": audio_base64
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

