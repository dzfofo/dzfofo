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
        "avatar": "https://images.unsplash.com/photo-1612066473428-fb6833a0d855?w=64&h=64&fit=crop&auto=format",
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

# --- FIX: Uncomment this route ---
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

    # --- FIX: url_for('features_hub') should now work after uncommenting the route ---
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
    # This is heuristic and might not always work perfectly
    name_parts = key_specs['name'].split(' ')
    if name_parts:
        # Try to match the first word(s) with known brands
        brands = get_phone_brands() # Get full list for matching
        brand_names = {b['brand_name'].lower() for b in brands}
        current_brand_guess = ""
        for part in name_parts:
             test_guess = (current_brand_guess + " " + part).strip()
             if test_guess.lower() in brand_names:
                  current_brand_guess = test_guess
             else:
                  # If adding the next part doesn't make a known brand, stop
                  if current_brand_guess: # Use the last valid guess
                       key_specs['brand'] = current_brand_guess
                       break # Stop processing name parts
                  # If no guess yet, check the current part itself
                  elif part.lower() in brand_names:
                       key_specs['brand'] = part
                       break
                  else:
                       break # Stop if current part is not a brand start

        if key_specs['brand'] == 'غير معروف' and name_parts:
             # Default to the first word if no brand matched
             key_specs['brand'] = name_parts[0]

    # Process Arabic specs if available
    arabic_specs = phone_details.get('arabic_specs', {})

    # Extract Platform/OS info
    platform_specs = arabic_specs.get('نظام التشغيل', [])
    for item in platform_specs:
        if 'OS' in item['key']:
            key_specs['os'] = item['value']
        elif 'Chipset' in item['key']:
            key_specs['processor'] = item['value']

    # Extract Display info
    display_specs = arabic_specs.get('الشاشة', [])
    display_info_parts = []
    for item in display_specs:
         if 'Size' in item['key']:
              display_info_parts.append(item['value'])
         elif 'Resolution' in item['key']:
              display_info_parts.append(item['value'])
         elif 'Type' in item['key']:
              display_info_parts.append(item['value'])

    if display_info_parts:
         key_specs['display'] = ', '.join(display_info_parts)


    # Extract Memory info
    memory_specs = arabic_specs.get('الذاكرة', [])
    ram_info = []
    storage_info = []
    for item in memory_specs:
        if 'RAM' in item['key']:
            ram_info.append(item['value'])
        if 'Internal' in item['key']:
            storage_info.append(item['value'])

    if ram_info:
         key_specs['ram'] = ', '.join(ram_info)
    if storage_info:
         key_specs['storage'] = ', '.join(storage_info)


    # Extract Main Camera info
    camera_specs_list = arabic_specs.get('الكاميرا الخلفية', [])
    camera_info_parts = [item['value'] for item in camera_specs_list if item.get('value')]
    if camera_info_parts:
        key_specs['camera'] = ', '.join(camera_info_parts)

    # Extract Battery info
    battery_specs = arabic_specs.get('البطارية', [])
    battery_info_parts = []
    for item in battery_specs:
        if 'Type' in item['key']:
            battery_info_parts.append(item['value'])
        elif 'Charging' in item['key']:
            charging_value = item['value']
            battery_info_parts.append(f"شحن: {charging_value}")
            if 'fast' in charging_value.lower() or 'watt' in charging_value.lower():
                 key_specs['fast_charging'] = 'نعم'

    if battery_info_parts:
         key_specs['battery'] = ', '.join(battery_info_parts)


    # Extract Network info
    network_specs = arabic_specs.get('الشبكة', [])
    network_types = []
    for item in network_specs:
        if 'Technology' in item['key']:
            network_types = item['value'].split(', ')
            break # Assuming Technology key lists major types

    if '5G' in network_types:
        key_specs['network'] = '5G'
    elif 'LTE' in network_types or '4G' in network_types:
        key_specs['network'] = '4G'
    elif '3G' in network_types:
         key_specs['network'] = '3G'
    else:
         key_specs['network'] = 'غير معروف'


    # Extract Release date
    launch_specs = arabic_specs.get('تاريخ الإصدار', [])
    for item in launch_specs:
        if 'Status' in item['key']:
            key_specs['release_date'] = item['value']
            break # Assuming Status has the most relevant date

    # Extract NFC
    comms_specs = arabic_specs.get('الاتصالات', [])
    for item in comms_specs:
        if 'NFC' in item['key'] and 'Yes' in item['value']:
            key_specs['nfc'] = 'نعم'
            break

    # Provide a default rating (as API doesn't provide it)
    key_specs['rating'] = '4.2/5 (تقييم افتراضي)' # Indicate it's default


    # Clean up image URL if it's empty after extraction
    if not key_specs['image']:
         key_specs['image'] = "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?q=80&w=880&auto=format&fit=crop"


    return key_specs

# Phone comparison function for API endpoint
def find_phone_match(query):
    """Find phone that matches the query using API data"""
    # Try to find exact match first
    # This logic is kept as is, it relies on the Mobile Specs API
    brand_matches = []

    # Get all brands
    brands = get_phone_brands()
    brand_slug_map = {b['brand_slug']: b['brand_name'] for b in brands}

    # Simple search by brand slug or name in query
    query_lower = query.lower()
    potential_brand_slugs = []

    for brand in brands:
        brand_name_lower = brand.get('brand_name', '').lower()
        brand_slug_lower = brand.get('brand_slug', '').lower()

        # Check for brand name or slug as a full word or partial
        if brand_slug_lower in query_lower.split() or brand_name_lower in query_lower:
             potential_brand_slugs.append(brand.get('brand_slug'))
             # Limit to a few brands to avoid excessive API calls if query is generic
             if len(potential_brand_slugs) > 3: break


    found_phone_slug = None
    found_phone_name = None

    # If we found potential brands, search for phones within those brands
    if potential_brand_slugs:
        for brand_slug in potential_brand_slugs:
            phones = get_phones_by_brand(brand_slug)

            if phones:
                # Sort phones by likelihood of matching the query (e.g., exact match first)
                # This is a simple heuristic, could be improved
                sorted_phones = sorted(phones, key=lambda p: (
                    p.get('phone_name', '').lower() == query_lower, # Exact match
                    query_lower in p.get('phone_name', '').lower(), # Substring match
                    -len(p.get('phone_name', '')) # Prefer shorter names if partial match? (less likely needed)
                ), reverse=True) # Put better matches first

                for phone in sorted_phones:
                    phone_name = phone.get('phone_name', '')
                    phone_slug = phone.get('slug')

                    # Simple check if query (or parts of query) are in the phone name
                    if query_lower in phone_name.lower() or any(word in phone_name.lower() for word in query_lower.split() if len(word) > 2):
                         found_phone_slug = phone_slug
                         found_phone_name = phone_name
                         break # Found a good match in this brand

            if found_phone_slug: break # Found a match in any brand, stop searching brands


    # If no match found via brand search, try searching latest phones
    if not found_phone_slug:
        latest_phones = get_latest_phones()
        if latest_phones:
             # Search in latest phones list
             sorted_latest = sorted(latest_phones, key=lambda p: (
                 p.get('phone_name', '').lower() == query_lower,
                 query_lower in p.get('phone_name', '').lower()
             ), reverse=True)
             for phone in sorted_latest:
                 phone_name = phone.get('phone_name', '')
                 phone_slug = phone.get('slug')
                 if query_lower in phone_name.lower() or any(word in phone_name.lower() for word in query_lower.split() if len(word) > 2):
                     found_phone_slug = phone_slug
                     found_phone_name = phone_name
                     break


    # If a phone slug was found, fetch detailed specs
    if found_phone_slug:
        phone_details = get_phone_details(found_phone_slug)
        if phone_details:
             return extract_key_phone_specs(phone_details)
        else:
             logger.warning(f"Could not fetch details for slug: {found_phone_slug}")
             # Fallback to dummy data if details fetch fails
             return fallback_phone_data(query)


    # Fallback to hardcoded data if API lookup failed to find a phone
    logger.warning(f"Could not find phone '{query}' via API. Falling back to dummy data.")
    return fallback_phone_data(query)

def fallback_phone_data(query):
    """Provide fallback phone data when API fails or no match is found"""
    # Hardcoded phone data for common phones (keep this as a last resort)
    dummy_devices = {
        "samsung galaxy s23 ultra": {
            "name": "Samsung Galaxy S23 Ultra",
            "brand": "سامسونج", "os": "Android 13", "display": "6.8 بوصة، AMOLED، 1440 × 3088 بكسل",
            "processor": "Snapdragon 8 Gen 2", "ram": "12 جيجابايت",
            "camera": "200 ميجابكسل (رئيسية) + 10 ميجابكسل (مقربة) + 12 ميجابكسل (واسعة)",
            "battery": "5000 مللي أمبير، شحن 45 واط", "storage": "256/512 جيجابايت / 1 تيرابايت",
            "network": "5G", "release_date": "فبراير 2023", "price": "~1199 دولار",
            "image": "https://fdn2.gsmarena.com/vv/pics/samsung/samsung-galaxy-s23-ultra-5g-1.jpg",
            "nfc": "نعم", "fast_charging": "نعم (45 واط)", "rating": "4.8/5"
        },
        "iphone 15 pro max": {
            "name": "iPhone 15 Pro Max",
            "brand": "آبل", "os": "iOS 17", "display": "6.7 بوصة، OLED، 1290 × 2796 بكسل",
            "processor": "A17 Pro", "ram": "8 جيجابايت",
            "camera": "48 ميجابكسل (رئيسية) + 12 ميجابكسل (مقربة) + 12 ميجابكسل (واسعة)",
            "battery": "4422 مللي أمبير، شحن 20 واط", "storage": "256/512 جيجابايت / 1 تيرابايت",
            "network": "5G", "release_date": "سبتمبر 2023", "price": "~1199 دولار",
            "image": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-15-pro-max-1.jpg",
            "nfc": "نعم", "fast_charging": "نعم (20 واط)", "rating": "4.7/5"
        },
        "google pixel 7 pro": {
            "name": "Google Pixel 7 Pro",
            "brand": "جوجل", "os": "Android 13", "display": "6.7 بوصة، OLED، 1440 × 3120 بكسل",
            "processor": "Google Tensor G2", "ram": "12 جيجابايت",
            "camera": "50 ميجابكسل (رئيسية) + 48 ميجابكسل (مقربة) + 12 ميجابكسل (واسعة)",
            "battery": "5000 مللي أمبير، شحن 23 واط", "storage": "128/256/512 جيجابايت",
            "network": "5G", "release_date": "أكتوبر 2022", "price": "~899 دولار",
            "image": "https://fdn2.gsmarena.com/vv/pics/google/google-pixel7-pro-1.jpg",
            "nfc": "نعم", "fast_charging": "نعم (23 واط)", "rating": "4.5/5"
        },
        "xiaomi 13 pro": {
            "name": "Xiaomi 13 Pro",
            "brand": "شاومي", "os": "Android 13", "display": "6.73 بوصة، OLED، 1440 × 3200 بكسل",
            "processor": "Snapdragon 8 Gen 2", "ram": "12 جيجابايت",
            "camera": "50 ميجابكسل (رئيسية) + 50 ميجابكسل (مقربة) + 50 ميجابكسل (واسعة)",
            "battery": "4820 مللي أمبير، شحن 120 واط", "storage": "256/512 جيجابايت",
            "network": "5G", "release_date": "ديسمبر 2022", "price": "~899 دولار",
            "image": "https://fdn2.gsmarena.com/vv/pics/xiaomi/xiaomi-13-pro-1.jpg",
            "nfc": "نعم", "fast_charging": "نعم (120 واط)", "rating": "4.6/5"
        },
        "oneplus 11": {
            "name": "OnePlus 11",
            "brand": "ون بلس", "os": "Android 13", "display": "6.7 بوصة، AMOLED، 1440 × 3216 بكسل",
            "processor": "Snapdragon 8 Gen 2", "ram": "16 جيجابايت",
            "camera": "50 ميجابكسل (رئيسية) + 32 ميجابكسل (مقربة) + 48 ميجابكسل (واسعة)",
            "battery": "5000 مللي أمبير، شحن 100 واط", "storage": "256/512 جيجابايت",
            "network": "5G", "release_date": "يناير 2023", "price": "~699 دولار",
            "image": "https://fdn2.gsmarena.com/vv/pics/oneplus/oneplus-11-1.jpg",
            "nfc": "نعم", "fast_charging": "نعم (100 واط)", "rating": "4.5/5"
        }
    }

    # Simple fuzzy matching
    query_lower = query.lower().strip()
    for key, device in dummy_devices.items():
        # Check if query is in key OR if any word from key is in query
        if query_lower in key or any(word in query_lower for word in key.split()):
            # Return a copy to avoid modifying the original dummy data
            return device.copy()

    # Create a fallback device if no match is found
    return {
        "name": query.title(), # Use the query as the name
        "brand": "غير معروف", "os": "غير معروف", "display": "غير معروف",
        "processor": "غير معروف", "ram": "غير معروف", "camera": "غير معروف",
        "battery": "غير معروف", "storage": "غير معروف", "network": "غير معروف",
        "release_date": "غير معروف", "price": "غير معروف",
        "image": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?q=80&w=880&auto=format&fit=crop", # Default generic image
        "nfc": "غير معروف", "fast_charging": "غير معروف", "rating": "غير معروف"
    }


@app.route('/api/compare_devices', methods=['POST'])
# @login_required # Uncomment when Flask-Login is fully used
def api_compare_devices():
    """API endpoint to compare specs of two devices."""
    # Manual session check for now
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401

    data = request.get_json()
    device1_name = data.get('device1', '').strip()
    device2_name = data.get('device2', '').strip()

    if not device1_name or not device2_name:
        return jsonify({"status": "error", "message": "يرجى إدخال اسم الجهازين"}), 400

    # Use the phone matching function that uses real API data or fallback
    device1_specs = find_phone_match(device1_name)
    device2_specs = find_phone_match(device2_name)

    # Determine overall status and message
    message = "تم العثور على الجهازين."
    status = "success"

    # Check if find_phone_match returned fallback data (name is query.title() or "غير معروف")
    # Or if it returned a dictionary but the name doesn't match the input query well (more complex)
    # A simpler check is if the returned name is the default "غير معروف" or exactly the queried name's title case (which fallback_phone_data does)
    device1_found = not (device1_specs.get("name") == "غير معروف" or device1_specs.get("name") == device1_name.title())
    device2_found = not (device2_specs.get("name") == "غير معروف" or device2_specs.get("name") == device2_name.title())

    # Ensure we always return a dictionary for device specs even if not found, for consistent frontend handling
    if not device1_found:
         device1_specs = fallback_phone_data(device1_name)
    if not device2_found:
         device2_specs = fallback_phone_data(device2_name)


    if not device1_found and not device2_found:
         message = f"لم يتم العثور على معلومات كافية عن الجهازين '{device1_name}' و '{device2_name}'. تم عرض معلومات افتراضية."
         status = "error" # Use error status when no real data is found for either
    elif not device1_found:
         message = f"لم يتم العثور على معلومات كافية عن الجهاز '{device1_name}'. تم عرض معلومات الجهاز الثاني فقط ومعلومات افتراضية للأول."
         status = "partial_success"
    elif not device2_found:
         message = f"لم يتم العثور على معلومات كافية عن الجهاز '{device2_name}'. تم عرض معلومات الجهاز الأول فقط ومعلومات افتراضية للثاني."
         status = "partial_success"


    return jsonify({
        "status": status,
        "message": message,
        "device1": device1_specs,
        "device2": device2_specs
    })


@app.route('/audio-generator')
# @login_required # Uncomment when Flask-Login is fully used
def audio_generator():
    """Render the Audio generator page with TTS integration."""
    # Manual session check for now
    if 'username' not in session:
        return redirect(url_for('index'))

    # Pass API key status imported from utils to the template for conditional rendering
    has_elevenlabs = bool(ELEVENLABS_API_KEY)
    has_voicerss = bool(VOICERSS_API_KEY)
    # Get preferred TTS service from session for default selection
    preferred_tts_service = session.get('preferred_tts_service', 'elevenlabs')


    return render_template('audio_generator.html',
                          username=session.get('username', ''),
                          has_elevenlabs=has_elevenlabs,
                          has_voicerss=has_voicerss,
                          preferred_tts_service=preferred_tts_service)


@app.route('/api/text_to_speech', methods=['POST'])
# @login_required # Uncomment when Flask-Login is fully used
def api_text_to_speech():
    """API endpoint to convert text to speech using TTS services."""
    # Manual session check for now
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401

    data = request.get_json()
    text = data.get('text', '').strip()
    voice_id = data.get('voice_id', "EXAVITQu4vr4xnSDxMaL")  # Default voice ID for ElevenLabs
    tts_service = data.get('tts_service', session.get('preferred_tts_service', 'elevenlabs')) # Preferred service from frontend or session

    if not text:
        # Even for empty text, return success but indicate no audio/use browser
        return jsonify({
             "status": "success",
             "message": "النص المطلوب فارغ. لا يوجد صوت لتوليده.",
             "audio": None,
             "audio_type": None, # Or 'browser' with empty text
             "text_for_browser": ""
        })

    # Use the centralized text_to_speech function from utils.py
    # This function handles choosing the service and fallbacks internally
    tts_result = text_to_speech(text, voice_id=voice_id, tts_service=tts_service)

    # --- FIX: Handle case where text_to_speech returns None explicitly ---
    # utils.text_to_speech is designed to always return a browser fallback
    # unless all APIs are off AND browser is explicitly excluded (not the case here).
    # If tts_result is None, it indicates a complete failure including browser fallback.
    if tts_result is None:
         logger.error(f"Final TTS failure after all attempts for text: {text[:50]}...")
         # Return an error response indicating TTS failure
         return jsonify({
              "status": "error", # Indicate backend error status
              "message": "فشل توليد الصوت باستخدام جميع الخدمات المتاحة. يرجى التحقق من مفاتيح API لخدمات تحويل النص إلى كلام (ElevenLabs, VoiceRSS) أو إعدادات المتصفح.",
              "audio": None,
              "audio_type": None,
              "text_for_browser": None
         }), 500 # Use 500 status for backend processing failure

    # Return the result structure provided by utils.text_to_speech
    return jsonify({
        "status": "success", # Even if using browser, it's a 'successful' fallback
        "message": "تم تحويل النص إلى صوت بنجاح." if tts_result['type'] != 'browser' else "سيتم استخدام النطق المدمج في المتصفح كبديل.",
        "audio": tts_result.get('audio'), # audio content (base64 string or url)
        "audio_type": tts_result.get('type'), # 'base64', 'url', or 'browser'
        "text_for_browser": tts_result.get('text') # Only present if audio_type is 'browser'
    })


@app.route('/api/translate', methods=['POST'])
# @login_required # Uncomment when Flask-Login is fully used
def api_translate():
    """API endpoint to translate text using Google Translate."""
    # Manual session check for now
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401

    data = request.get_json()
    text = data.get('text', '').strip()
    target_lang = data.get('target_lang', 'ar')  # Default to Arabic

    if not text:
        return jsonify({"status": "success", "translated_text": ""}), 200 # Return empty translated text for empty input

    # Use the centralized translate function from utils.py
    translated_text = translate_text(text, target_lang)

    # utils.translate_text returns None on error
    if translated_text is None:
        logger.error(f"Translation failed for text: {text[:50]}...")
        return jsonify({
            "status": "error",
            "message": "حدث خطأ أثناء ترجمة النص. يرجى التأكد من تثبيت googletrans والمحاولة لاحقاً."
        }), 500

    # If translation was successful but returned empty (e.g., input was just whitespace),
    # return the original text or a specific message. utils handles empty input.
    # No need for the check here as utils handles empty and returns "" or None.


    return jsonify({
        "status": "success",
        "translated_text": translated_text
    })


@app.route('/settings')
# @login_required # Uncomment when Flask-Login is fully used
def settings():
    """Settings page for API keys and speech recognition settings."""
    # Manual session check for now
    if 'username' not in session:
        return redirect(url_for('index'))

    # Check if API keys are set by accessing the values imported from utils
    openrouter_connected = bool(OPENROUTER_API_KEY)
    elevenlabs_connected = bool(ELEVENLABS_API_KEY)
    stability_connected = bool(STABILITY_API_KEY)
    voicerss_connected = bool(VOICERSS_API_KEY)


    # Mask API keys for display (do NOT send actual keys to frontend)
    openrouter_key_masked = "••••••••" if OPENROUTER_API_KEY else ""
    elevenlabs_key_masked = "••••••••" if ELEVENLABS_API_KEY else ""
    stability_key_masked = "••••••••" if STABILITY_API_KEY else ""
    voicerss_key_masked = "••••••••" if VOICERSS_API_KEY else ""


    # Get speech settings from session or use defaults
    # Note: DeepSpeech implementation is missing in the provided code, this is a placeholder setting.
    use_deepspeech = session.get('use_deepspeech', False)
    audio_feedback = session.get('audio_feedback', True)
    auto_send = session.get('auto_send', True)
    arabic_dialect = session.get('arabic_dialect', 'ar-SA') # Used by browser STT/TTS
    preferred_tts_service = session.get('preferred_tts_service', 'elevenlabs') # Preferred TTS service


    return render_template('settings.html',
                          username=session.get('username', ''),
                          openrouter_connected=openrouter_connected,
                          elevenlabs_connected=elevenlabs_connected,
                          stability_connected=stability_connected,
                          voicerss_connected=voicerss_connected, # Pass VoiceRSS status
                          openrouter_key_masked=openrouter_key_masked,
                          elevenlabs_key_masked=elevenlabs_key_masked,
                          stability_key_masked=stability_key_masked,
                          voicerss_key_masked=voicerss_key_masked, # Pass VoiceRSS masked key
                          use_deepspeech=use_deepspeech,
                          audio_feedback=audio_feedback,
                          auto_send=auto_send,
                          arabic_dialect=arabic_dialect,
                          preferred_tts_service=preferred_tts_service # Pass preferred TTS service
                          )


@app.route('/api/save_speech_settings', methods=['POST'])
# @login_required # Uncomment when Flask-Login is fully used
def api_save_speech_settings():
    """Save speech recognition and TTS settings to session."""
    # Manual session check for now
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401

    data = request.get_json()

    # Save settings to session
    session['use_deepspeech'] = data.get('use_deepspeech', False)
    session['audio_feedback'] = data.get('audio_feedback', True)
    session['auto_send'] = data.get('auto_send', True)
    session['arabic_dialect'] = data.get('arabic_dialect', 'ar-SA')
    session['preferred_tts_service'] = data.get('preferred_tts_service', 'elevenlabs')


    logger.info(f"Speech settings saved for {session.get('username', 'N/A')}: use_deepspeech={session.get('use_deepspeech')}, audio_feedback={session.get('audio_feedback')}, auto_send={session.get('auto_send')}, arabic_dialect={session.get('arabic_dialect')}, preferred_tts_service={session.get('preferred_tts_service')}")

    return jsonify({"status": "success", "message": "تم حفظ الإعدادات بنجاح."})


@app.route('/api/save_api_keys', methods=['POST'])
# @login_required # Uncomment when Flask-Login is fully used
def api_save_api_keys():
    """
    Save API keys to environment variables (temporary for this demo).
    In a real app, store securely in DB or vault per user.
    """
    # Manual session check for now
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401

    data = request.get_json()

    # Get keys from request - assume empty string if not provided
    # Only update if the value is provided and is not the masked placeholder
    openrouter_key = data.get('openrouter_key', '').strip()
    elevenlabs_key = data.get('elevenlabs_key', '').strip()
    stability_key = data.get('stability_key', '').strip()
    voicerss_key = data.get('voicerss_key', '').strip()

    # Update environment variables AND the module-level variables in utils.py
    # This approach is for demonstrating dynamic updates in this simple demo structure.
    # It does NOT provide persistence across process restarts or guarantee consistency in scaled deployments.
    updated_keys = []
    # Check against masked placeholder AND handle explicit clearing (empty string submitted)
    if openrouter_key and openrouter_key != "••••••••":
        os.environ["OPENROUTER_API_KEY"] = openrouter_key
        utils.OPENROUTER_API_KEY = openrouter_key # Update module variable
        updated_keys.append("OpenRouter")
    elif data.get('openrouter_key') == "": # Explicitly cleared
        os.environ.pop("OPENROUTER_API_KEY", None)
        utils.OPENROUTER_API_KEY = None
        updated_keys.append("OpenRouter (Cleared)")


    if elevenlabs_key and elevenlabs_key != "••••••••":
        os.environ["ELEVENLABS_API_KEY"] = elevenlabs_key
        utils.ELEVENLABS_API_KEY = elevenlabs_key
        updated_keys.append("ElevenLabs")
    elif data.get('elevenlabs_key') == "": # Explicitly cleared
        os.environ.pop("ELEVENLABS_API_KEY", None)
        utils.ELEVENLABS_API_KEY = None
        updated_keys.append("ElevenLabs (Cleared)")


    if stability_key and stability_key != "••••••••":
        os.environ["STABILITY_API_KEY"] = stability_key
        utils.STABILITY_API_KEY = stability_key
        updated_keys.append("Stability")
    elif data.get('stability_key') == "": # Explicitly cleared
        os.environ.pop("STABILITY_API_KEY", None)
        utils.STABILITY_API_KEY = None
        updated_keys.append("Stability (Cleared)")


    if voicerss_key and voicerss_key != "••••••••":
        os.environ["VOICERSS_API_KEY"] = voicerss_key
        utils.VOICERSS_API_KEY = voicerss_key
        updated_keys.append("VoiceRSS")
    elif data.get('voicerss_key') == "": # Explicitly cleared
        os.environ.pop("VOICERSS_API_KEY", None)
        utils.VOICERSS_API_KEY = None
        updated_keys.append("VoiceRSS (Cleared)")


    message = "تم حفظ المفاتيح بنجاح: " + ", ".join(updated_keys) if updated_keys else "لم يتم تحديث أي مفاتيح."
    # Refine message if user submitted non-empty but masked values
    if not updated_keys and (openrouter_key or elevenlabs_key or stability_key or voicerss_key) and \
       any(v == "••••••••" for v in [data.get('openrouter_key'), data.get('elevenlabs_key'), data.get('stability_key'), data.get('voicerss_key')] if v is not None):
        message = "لم يتم تحديث أي مفاتيح (تم إدخال القيم المخفية)."


    logger.info(f"API key save attempt: {message}")


    # Note: To make keys persistent, you'd save them to the database here.
    # The application should ideally load keys from the DB at startup or from a secure vault.


    return jsonify({"status": "success", "message": message})


# --- Phone Assistant Routes ---
# These routes use functions from phone_assistant.py.
# phone_assistant.py currently has its own call_openrouter_api function.
# In a future refactoring, phone_assistant.py should be updated to import
# and use the call_openrouter_api from utils.py.

@app.route('/phone-assistant')
# @login_required # Uncomment when Flask-Login is fully used
def phone_assistant():
    """Render the Phone recommendation assistant page."""
    # Manual session check for now
    if 'username' not in session:
        return redirect(url_for('index'))

    return render_template('assistant.html', username=session.get('username', ''))

@app.route('/api/suggest_phone', methods=['POST'])
# @login_required # Uncomment when Flask-Login is fully used
def api_suggest_phone():
    """API endpoint to suggest phones based on user requirements."""
    # Manual session check for now
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401

    data = request.get_json()
    requirements = data.get('requirements', '').strip()

    if not requirements:
        return jsonify({"status": "error", "message": "يرجى إدخال متطلباتك للهاتف."}), 400

    # Get suggestion from phone assistant (uses phone_assistant.py's internal logic)
    # Note: This should eventually use a refactored phone_assistant that uses utils.call_openrouter_api
    suggestion = suggest_phone(requirements)

    if suggestion is None: # Handle potential failure from phone_assistant/its API calls
         suggestion = "عذراً، لم أتمكن من تقديم اقتراح هاتف بناءً على متطلباتك في الوقت الحالي."

    return jsonify({
        "status": "success", # Still success even with a fallback message
        "suggestion": suggestion
    })

@app.route('/api/cheaper_alternative', methods=['POST'])
# @login_required # Uncomment when Flask-Login is fully used
def api_cheaper_alternative():
    """API endpoint to get cheaper alternatives for a specific phone."""
    # Manual session check for now
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401

    data = request.get_json()
    phone_name = data.get('requirements', '').strip() # The frontend sends the phone name in 'requirements'

    if not phone_name:
        return jsonify({"status": "error", "message": "يرجى إدخال اسم الهاتف الذي تريد بديلاً له."}), 400

    # Get cheaper alternatives (uses phone_assistant.py's internal logic)
    # Note: This should eventually use a refactored phone_assistant
    alternatives = suggest_cheaper_alternative(phone_name)

    # Make a recommendation based on the requirements (uses phone_assistant.py's internal logic)
    # Note: This should eventually use a refactored phone_assistant
    recommendation = suggest_phone(f"أريد بديل أرخص لـ {phone_name} مع الحفاظ على جودة الأداء قدر الإمكان.")

    # Determine overall status and message
    status = "success"
    message = "تم العثور على بدائل مقترحة."
    if alternatives is None and recommendation is None:
         status = "error"
         message = "عذراً، لم أتمكن من العثور على بدائل أرخص أو تقديم توصية في الوقت الحالي."
    elif alternatives is None:
         status = "partial_success"
         message = "تم تقديم توصية لهاتف بناءً على طلبك، لكن لم أتمكن من العثور على بدائل أرخص محددة."
    elif recommendation is None:
         status = "partial_success"
         message = "تم العثور على بدائل أرخص محددة، لكن لم أتمكن من تقديم توصية واضحة بناءً على طلبك."


    return jsonify({
        "status": status,
        "message": message,
        "suggestion": recommendation, # Could be None
        "alternatives": alternatives # Could be None
    })

# @app.route('/api/advanced_comparison', methods=['POST'])
# @login_required
def api_advanced_comparison():
    """API endpoint to get advanced comparison between two phones using AI."""
    # Manual session check for now
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401

    data = request.get_json()
    phone1 = data.get('phone1', '').strip()
    phone2 = data.get('phone2', '').strip()

    if not phone1 or not phone2:
        return jsonify({"status": "error", "message": "يرجى إدخال أسماء الهاتفين للمقارنة."}), 400

    # Get advanced comparison (uses phone_assistant.py's internal logic)
    # Note: This should eventually use a refactored phone_assistant that uses utils.call_openrouter_api
    comparison = get_advanced_comparison(phone1, phone2)

    if comparison is None:
        comparison = "عذراً، لم أتمكن من إجراء مقارنة متقدمة بين الهاتفين المطلوبين في الوقت الحالي."
        status = "error"
    else:
        status = "success"


    return jsonify({
        "status": status,
        "comparison": comparison
    })


# --- Voice Assistant Routes (Integrated into app.py) ---

@app.route('/voice_assistant')
# @login_required # Uncomment when Flask-Login is fully used
def voice_assistant():
    """Render the Voice assistant page with speech recognition and AI responses."""
    # Manual session check for now
    if 'username' not in session:
        return redirect(url_for('index'))

    # Determine models and TTS services available based on API keys imported from utils
    has_openrouter = bool(OPENROUTER_API_KEY)
    has_elevenlabs = bool(ELEVENLABS_API_KEY)
    has_voicerss = bool(VOICERS_API_KEY) # Use the key imported from utils

    # Get preferred TTS service from session or default
    preferred_tts_service = session.get('preferred_tts_service', 'elevenlabs')

    # Determine which models are actually available to pass to the template
    available_models = [
        {"id": "mistralai/mixtral-8x7b-instruct", "name": "Mixtral 8x7B (مجاني)"},
        {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku (مجاني/رخيص)"}
    ]
    if has_openrouter:
        # Add OpenRouter specific models if key is available
        # Filter models based on your preference or cost concerns
        available_models.append({"id": "openai/gpt-3.5-turbo", "name": "GPT-3.5 Turbo"})
        available_models.append({"id": "google/gemini-pro", "name": "Gemini Pro"})
        available_models.append({"id": "openai/gpt-4o", "name": "GPT-4o (الأفضل)"})


    return render_template('voice_assistant.html',
                         username=session.get('username', ''),
                         has_openrouter=has_openrouter,
                         has_elevenlabs=has_elevenlabs,
                         has_voicerss=has_voicerss,
                         preferred_tts_service=preferred_tts_service,
                         available_models=available_models # Pass the list of available models
                         )


@app.route("/api/voice_assistant", methods=["POST"])
# @login_required # Uncomment when Flask-Login is fully used
def api_voice_assistant():
    """Process voice input and generate AI response, return text and audio details."""
    # Manual session check for now
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401

    data = request.get_json()
    user_prompt = data.get("prompt", "").strip()
    model = data.get("model", "mistralai/mixtral-8x7b-instruct") # Default model if not provided
    tts_service = data.get("tts_service", session.get('preferred_tts_service', 'elevenlabs')) # Preferred TTS service from frontend or session
    voice_id = data.get("voice_id", "EXAVITQu4vr4xnSDxMaL") # Preferred voice ID from frontend

    if not user_prompt:
        # Even for empty input, attempt a simple response
         ai_response = "لم أستمع إلى شيء. هل يمكنك التحدث مرة أخرى؟"
         # Proceed to TTS for this fallback response

    else:
        # Define the system message specifically for the voice assistant context
        voice_assistant_system_message = (
            "أنت مساعد صوتي ذكي باللغة العربية اسمه ياسمين. "
            "أجب بإجابات مختصرة ومفيدة ومباشرة. "
            "كن ودودًا ولكن لا تطيل في الردود لتكون الإجابة مناسبة للنطق الصوتي السريع (مثلاً، حاول ألا تتجاوز فقرتين قصيرتين). "
            "اليوم هو 1 مايو 2025."
        )

        # Prepare messages list
        # In a real app, load recent history for context
        messages = [
            {"role": "user", "content": user_prompt}
        ]

        # Use the centralized call_openrouter_api from utils.py
        # Pass the specific system message as a parameter
        ai_response = call_openrouter_api(
            messages,
            model=model,
            temperature=0.8, # Slightly higher temp for potentially more natural voice response
            max_tokens=500, # Keep responses concise for voice
            system_message=voice_assistant_system_message
        )

        # Handle OpenRouter API failure (call_openrouter_api from utils returns an error string or None)
        if ai_response is None or "حدث خطأ" in ai_response or "عذراً" in ai_response or "استغرق الرد" in ai_response:
            logger.error(f"AI response error for voice assistant prompt '{user_prompt[:50]}...': {ai_response}")
            # Provide a specific fallback message for voice assistant failures
            if not OPENROUTER_API_KEY:
                 ai_response = "عذراً، لا يمكنني معالجة طلبك الصوتي الآن بسبب عدم توفر اتصال بخدمة الذكاء الاصطناعي (مفتاح OpenRouter مفقود)."
            else:
                 ai_response = "عذراً، حدث خطأ أثناء معالجة طلبك الصوتي. يرجى المحاولة مرة أخرى لاحقاً." # Generic error


    # Use the centralized text_to_speech function from utils.py
    # This function handles service selection (ElevenLabs/VoiceRSS) and fallback to browser internally
    tts_result = text_to_speech(ai_response, voice_id=voice_id, tts_service=tts_service)

    # --- FIX: Handle case where text_to_speech returns None explicitly ---
    # Although utils.text_to_speech is designed to always return a browser fallback
    # unless all APIs are off AND browser is explicitly excluded (not the case here),
    # adding this check is safer against unexpected issues.
    if tts_result is None:
         logger.error(f"Final TTS failure after all attempts for AI response: {ai_response[:50]}...")
         # Return an error response indicating TTS failure
         return jsonify({
              "status": "error", # Indicate backend error status
              "message": "فشل توليد الصوت للرد. يرجى التحقق من مفاتيح API لخدمات تحويل النص إلى كلام (ElevenLabs, VoiceRSS) أو إعدادات المتصفح.",
              "reply": ai_response, # Still return the AI text response
              "audio": None,
              "audio_type": None,
              "text_for_browser": None
         }), 500 # Use 500 status for backend processing failure

    # Return the AI text response and the audio result details from utils.text_to_speech
    return jsonify({
        "status": "success", # Indicate success for the request processing
        "message": "تم تحويل النص إلى صوت بنجاح." if tts_result['type'] != 'browser' else "سيتم استخدام النطق المدمج في المتصفح كبديل.",
        "reply": ai_response, # Return AI text response
        "audio": tts_result.get('audio'), # Base64 string or URL
        "audio_type": tts_result.get('type'), # 'base64', 'url', or 'browser'
        "text_for_browser": tts_result.get('text') # Only present if audio_type is 'browser'
    })


# --- Image Generation Route ---
@app.route('/image-generator')
# @login_required # Uncomment when Flask-Login is fully used
def image_generator():
    """Render the Image generator page with Stability AI integration."""
    # Manual session check for now
    if 'username' not in session:
        return redirect(url_for('index'))

    # Check if Stability API key is available via the variable imported from utils
    has_stability = bool(STABILITY_API_KEY)

    return render_template('image_generator.html',
                           username=session.get('username', ''),
                           has_stability=has_stability)


@app.route('/api/generate_image', methods=['POST'])
# @login_required # Uncomment when Flask-Login is fully used
def api_generate_image():
    """API endpoint to generate an image from text using Stability AI"""
    # Manual session check for now
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401

    data = request.get_json()
    prompt = data.get('prompt', '').strip()
    size = data.get('size', 512) # Get size from request, default to 512. Frontend should validate/suggest sizes.
    # Convert size to integer in case it came as string
    try:
        size = int(size)
    except (ValueError, TypeError):
        size = 512 # Default if invalid

    if not prompt:
        return jsonify({"status": "error", "message": "الرجاء إدخال وصف للصورة."}), 400

    # Check for API key availability using the variable imported from utils
    if not STABILITY_API_KEY:
         return jsonify({"status": "error", "message": "مفتاح Stability API غير متوفر. يرجى إضافته في صفحة الإعدادات لتمكين هذه الميزة."}), 500

    # Use the centralized generate_image function from utils.py
    image_base64 = generate_image(prompt, size=size)

    if image_base64:
        return jsonify({
            "status": "success",
            "message": "تم توليد الصورة بنجاح.",
            "image_base64": image_base64
        })
    else:
        # generate_image in utils handles logging API errors and returns None on failure
        # Return a specific error message
        error_message = "فشل توليد الصورة. قد يكون الوصف غير مناسب أو حدث خطأ في خدمة توليد الصور."
        # You could potentially try to get a more specific error message from utils.generate_image
        # if it was modified to return strings instead of just None on failure.
        # For now, log the failure in utils and return a generic message here.
        return jsonify({"status": "error", "message": error_message}), 500 # Use 500 for backend failure


if __name__ == "__main__":
    # Optional: Create database tables if they don't exist (useful for first run)
    # from models import User, Message # Import models here for creation
    # with app.app_context():
    #     db.create_all()
    #     logger.info("Database tables checked/created.")
    # Note: Running create_all() repeatedly is safe, it won't recreate existing tables.

    # In a production environment, set debug=False
    app.run(host="0.0.0.0", port=5000, debug=True)
