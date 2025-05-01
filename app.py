import os
import logging
import uuid
import json
import requests
import io
import base64
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_file, flash
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

# --- Setup Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Import Phone Assistant Module ---
from phone_assistant import suggest_phone, suggest_cheaper_alternative, get_advanced_comparison

# --- Base Class for SQLAlchemy models ---
class Base(DeclarativeBase):
    pass

# --- Initialize Flask app ---
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.environ.get("SESSION_SECRET", "yasmain_ai_development_key")

# --- Configure session to use filesystem ---
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
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
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280,  # Slightly less than 5 minutes (common for timeouts)
    "pool_pre_ping": True,  # To check the connection before using it
    "pool_timeout": 10,   # Wait time to get a connection from the pool
}

# Initialize SQLAlchemy with the app and Base model
db = SQLAlchemy(model_class=Base)
db.init_app(app)

# --- Load API Keys ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
STABILITY_API_KEY = os.environ.get("STABILITY_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

# Initialize flask-login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# --- Helper Functions ---
def allowed_file(filename):
    """Check if uploaded file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def translate_text(text, target_lang):
    """Translate text to target language using Google Translate"""
    try:
        from googletrans import Translator
        translator = Translator()
        result = translator.translate(text, dest=target_lang)
        return result.text
    except Exception as e:
        logger.error(f"Error translating text: {e}")
        return None

def preprocess_arabic_text(text):
    """
    Preprocess Arabic text to improve pronunciation with ElevenLabs.
    This helps improve the speech output quality for Arabic text.
    
    The preprocessing includes:
    1. Adding appropriate breaks for punctuation
    2. Handling special Arabic characters
    3. Optimizing for better pronunciation
    """
    if not text or not text.strip():
        return text
    
    # Add breaks after common punctuation marks to improve pacing
    punctuation_marks = ['.', '؟', '!', ':', ';', '،']
    for mark in punctuation_marks:
        text = text.replace(mark, mark + '\n')
    
    # Split text into sentences (now split by newlines)
    sentences = text.split('\n')
    processed = []
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # For very long sentences, add additional pauses at commas for better pacing
        if len(sentence) > 100:
            parts = sentence.split('،')
            formatted_parts = []
            for part in parts:
                part = part.strip()
                if part:
                    formatted_parts.append(part)
            sentence = '،\n'.join(formatted_parts)
        
        processed.append(sentence)
    
    # Join processed sentences
    return '\n'.join(processed)

def text_to_speech(text, voice_id="EXAVITQu4vr4xnSDxMaL"):
    """
    Convert text to speech using ElevenLabs API.
    Optimized for Arabic language with enhanced processing and error handling.
    """
    if not ELEVENLABS_API_KEY:
        logger.warning("ELEVENLABS_API_KEY environment variable is not set. Text-to-speech functionality won't work.")
        return None

    # Validate input
    if not text or not text.strip():
        logger.warning("Empty text provided to text_to_speech")
        return None

    # Preprocess Arabic text to improve pronunciation
    processed_text = preprocess_arabic_text(text)
    
    # Log the processed text for debugging
    logger.info(f"Processed text for TTS: {processed_text[:100]}..." if len(processed_text) > 100 else processed_text)

    # ElevenLabs API endpoint
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    # Set the headers with API key
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }

    # Build the request payload with optimized settings for Arabic
    payload = {
        "text": processed_text,
        "model_id": "eleven_multilingual_v2",  # Use the multilingual model for better language support
        "voice_settings": {
            "stability": 0.8,            # Increased stability for clearer Arabic pronunciation
            "similarity_boost": 0.8,     # Increased similarity for more consistent voice
            "style": 0.45,               # Slightly reduced style interpolation for Arabic
            "use_speaker_boost": True    # Enhance speaker clarity
        }
    }

    try:
        # Make the API request with increased timeout for longer texts
        max_timeout = 60 if len(processed_text) > 500 else 30
        logger.info(f"Calling ElevenLabs API with voice {voice_id}, timeout {max_timeout}s")
        
        response = requests.post(url, headers=headers, json=payload, timeout=max_timeout)

        if response.status_code == 200:
            logger.info("ElevenLabs API request successful")
            return response.content
        else:
            logger.error(f"ElevenLabs API error: {response.status_code} - {response.text}")
            
            # Try one more time with different model if first attempt failed
            if "model_id" in payload and payload["model_id"] == "eleven_multilingual_v2":
                logger.info("Retrying with eleven_turbo model...")
                payload["model_id"] = "eleven_turbo"
                response = requests.post(url, headers=headers, json=payload, timeout=max_timeout)
                
                if response.status_code == 200:
                    logger.info("ElevenLabs API retry successful with eleven_turbo model")
                    return response.content
            
            return None

    except requests.exceptions.Timeout:
        logger.error("ElevenLabs API request timed out. Text might be too long.")
        # Try with shorter text
        if len(processed_text) > 300:
            shorter_text = processed_text[:300] + "..."
            logger.info(f"Retrying with shorter text: {shorter_text[:50]}...")
            payload["text"] = shorter_text
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                if response.status_code == 200:
                    return response.content
                else:
                    logger.error(f"Retry failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Error in retry attempt: {e}")
        return None
        
    except Exception as e:
        logger.error(f"Error calling ElevenLabs API: {e}")
        return None

def call_openrouter_api(messages, model="openai/gpt-3.5-turbo", temperature=0.7, max_tokens=1000):
    """
    Call the OpenRouter API to generate a response
    Support for Gemini 1.5, Gemini Pro, Claude and GPT-4 models
    """
    if not OPENROUTER_API_KEY:
        logger.warning("OpenRouter API key not found, returning fallback response")
        return None

    # API endpoint
    url = "https://openrouter.ai/api/v1/chat/completions"

    # Convert our messages to the correct format
    formatted_messages = []

    # Add system instruction optimized for Arabic responses if not present
    has_system_message = any(msg.get("role") == "system" for msg in messages)
    if not has_system_message:
        formatted_messages.append({
            "role": "system",
            "content": "أنت مساعد ذكي ومفيد باللغة العربية اسمه ياسمين. أجب دائماً باللغة العربية الفصحى ما لم يطلب المستخدم لغة أخرى. قدم معلومات دقيقة وشاملة. تجنب الإجابات الطويلة جداً. اليوم هو 30 أبريل 2025."
        })

    # Add the user messages
    for msg in messages:
        # Ensure roles are correctly formatted for OpenRouter
        role = msg["role"]
        formatted_messages.append({
            "role": role,
            "content": msg["content"]
        })

    # Special handling for Gemini models
    is_gemini = "gemini" in model.lower()

    # Build the request payload
    payload = {
        "model": model,
        "messages": formatted_messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    # Add Gemini specific parameters if using a Gemini model
    if is_gemini:
        payload["top_p"] = 0.95
        payload["top_k"] = 40

    # Set the headers with API key
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://yasmin-chat.app",
        "X-Title": "Yasmin Chat App"
    }

    try:
        # Make the API request
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)

        if response.status_code == 200:
            # Parse the response JSON
            response_data = response.json()

            # Extract the generated text
            if "choices" in response_data and len(response_data["choices"]) > 0:
                return response_data["choices"][0]["message"]["content"]
            else:
                logger.error(f"Invalid response format from OpenRouter: {response_data}")
                return None
        else:
            logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error calling OpenRouter API: {e}")
        return None

# --- Fallback responses (for when APIs fail) ---
offline_responses = {
    "السلام عليكم": "وعليكم السلام! أنا ياسمين. للأسف، لا يوجد اتصال بالإنترنت حالياً.",
    "كيف حالك": "أنا بخير شكراً لك. لكن لا يمكنني الوصول للنماذج الذكية الآن بسبب انقطاع الإنترنت.",
    "مرحبا": "أهلاً بك! أنا ياسمين. أعتذر، خدمة الإنترنت غير متوفرة حالياً.",
    "شكرا": "على الرحب والسعة! أتمنى أن يعود الاتصال قريباً.",
    "مع السلامة": "إلى اللقاء! آمل أن أتمكن من مساعدتك بشكل أفضل عند عودة الإنترنت."
}
default_offline_response = "أعتذر، لا يمكنني معالجة طلبك الآن. يبدو أن هناك مشكلة في الاتصال بالإنترنت أو بخدمات الذكاء الاصطناعي."

# Mock AI Assistant Data - In a real application, this would come from a database
ASSISTANTS = [
    {
        "id": "gpt4o",
        "name": "GPT-4o",
        "avatar": "https://images.unsplash.com/photo-1717501218636-a390f9ac5957",
        "description": "معالجة متقدمة للغة الطبيعية",
        "color": "linear-gradient(135deg, #10a37f, #0a8263)"
    },
    {
        "id": "claude",
        "name": "Claude 3.5",
        "avatar": "https://images.unsplash.com/photo-1717501218385-55bc3a95be94",
        "description": "تفكير متعمق وتحليل شامل",
        "color": "linear-gradient(135deg, #9a48d0, #7a3aa4)"
    },
    {
        "id": "gemini",
        "name": "Gemini 1.5",
        "avatar": "https://images.unsplash.com/photo-1612066473428-fb6833a0d855",
        "description": "فهم متعدد الوسائط",
        "color": "linear-gradient(135deg, #4285f4, #0f9d58)"
    },
    {
        "id": "elevenlabs",
        "name": "ElevenLabs",
        "avatar": "https://images.unsplash.com/photo-1616161560417-66d4db5892ec",
        "description": "تحويل نص لصوت طبيعي",
        "color": "linear-gradient(135deg, #ff5757, #c43a3a)"
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "avatar": "https://images.unsplash.com/photo-1655393001768-d946c97d6fd1",
        "description": "توجيه ذكي للنماذج المختلفة",
        "color": "linear-gradient(135deg, #ff9e00, #d9840c)"
    },
    {
        "id": "techcompare",
        "name": "TechCompare",
        "avatar": "https://images.unsplash.com/photo-1530545002211-21753020f4c8",
        "description": "مقارنة الأجهزة التقنية",
        "color": "linear-gradient(135deg, #4a69bd, #3a59ad)"
    },
    {
        "id": "phoneassistant",
        "name": "مساعد الهواتف",
        "avatar": "https://images.unsplash.com/photo-1599317193916-7bb9b7b7e744",
        "description": "اقتراح الهاتف المناسب لمتطلباتك",
        "color": "linear-gradient(135deg, #fd1d1d, #f77062)"
    }
]

# Suggested questions for chat - empty now as per user request
SUGGESTED_QUESTIONS = []

@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/features')
def features_hub():
    # Check if user has a name stored in session
    if 'username' not in session:
        return redirect(url_for('index'))
    
    return render_template('features_hub.html', 
                          username=session.get('username', ''),
                          assistants=ASSISTANTS)

@app.route('/chat/<assistant_id>')
def chat(assistant_id):
    if 'username' not in session:
        return redirect(url_for('index'))
    
    # Find the selected assistant
    assistant = next((a for a in ASSISTANTS if a['id'] == assistant_id), ASSISTANTS[0])
    
    return render_template('chat.html', 
                          username=session.get('username', ''),
                          assistant=assistant,
                          suggested_questions=SUGGESTED_QUESTIONS)

@app.route('/compare')
def compare():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    return render_template('compare.html', 
                          username=session.get('username', ''))

@app.route('/api/save_username', methods=['POST'])
def save_username():
    data = request.get_json()
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({"status": "error", "message": "اسم المستخدم مطلوب"}), 400
    
    # Store username in session
    session['username'] = username
    return jsonify({"status": "success", "redirect": url_for('features_hub')})

@app.route('/api/logout', methods=['POST'])
def logout():
    # Clear the session
    session.clear()
    return jsonify({"status": "success", "redirect": url_for('index')})

@app.route('/api/chat_message', methods=['POST'])
def chat_message():
    if 'username' not in session:
        return jsonify({"status": "error", "message": "جلسة غير صالحة"}), 401
    
    data = request.get_json()
    message = data.get('message', '').strip()
    assistant_id = data.get('assistant_id', '')
    
    if not message:
        return jsonify({"status": "error", "message": "الرسالة مطلوبة"}), 400
    
    # Find the selected assistant
    assistant = next((a for a in ASSISTANTS if a['id'] == assistant_id), ASSISTANTS[0])
    
    # Create message object for API calls
    messages = [{"role": "user", "content": message}]
    
    # Get AI response based on assistant type
    if assistant_id == "gpt4o":
        # Use OpenRouter with GPT-4o model
        if OPENROUTER_API_KEY:
            ai_response = call_openrouter_api(
                messages, 
                model="openai/gpt-4o", 
                temperature=0.7, 
                max_tokens=2000
            )
        else:
            ai_response = f"مرحباً {session['username']}! أنا GPT-4o. للأسف، لا يمكنني الوصول إلى OpenRouter API حالياً. يمكنك تقديم مفتاح API لتفعيل الخدمة الكاملة."
    
    elif assistant_id == "claude":
        # Use OpenRouter with Claude model
        if OPENROUTER_API_KEY:
            ai_response = call_openrouter_api(
                messages, 
                model="anthropic/claude-3-opus", 
                temperature=0.7, 
                max_tokens=2000
            )
        else:
            ai_response = f"أهلاً {session['username']}، أنا Claude 3.5. للأسف، لا يمكنني الوصول إلى OpenRouter API حالياً. يمكنك تقديم مفتاح API لتفعيل الخدمة الكاملة."
    
    elif assistant_id == "gemini":
        # Use OpenRouter with Gemini model (via Claude as fallback)
        if OPENROUTER_API_KEY:
            ai_response = call_openrouter_api(
                messages, 
                model="anthropic/claude-3-opus", 
                temperature=0.7, 
                max_tokens=2000
            )
        else:
            ai_response = f"مرحباً {session['username']}! Gemini 1.5 هنا. للأسف، لا يمكنني الوصول إلى OpenRouter API حالياً. يمكنك تقديم مفتاح API لتفعيل الخدمة الكاملة."
    
    elif assistant_id == "elevenlabs":
        # Special handler for text-to-speech requests
        if ELEVENLABS_API_KEY:
            # For demonstration we're returning a descriptive response
            ai_response = f"أهلاً {session['username']}، هذا ElevenLabs. تم استلام نصك: '{message}'. يمكنني تحويل هذا النص إلى صوت عربي طبيعي."
            
            # In a full implementation, we would generate audio and return a URL or audio data
            # audio_content = text_to_speech(message)
            # Then store it or return it directly
        else:
            ai_response = f"أهلاً {session['username']}، هذا ElevenLabs. للأسف، لا يمكنني الوصول إلى ElevenLabs API حالياً. يمكنك تقديم مفتاح API لتفعيل خدمة تحويل النص إلى صوت."
    
    else:  # Default for openrouter or other assistants
        if OPENROUTER_API_KEY:
            ai_response = call_openrouter_api(
                messages, 
                model="openai/gpt-3.5-turbo", 
                temperature=0.7, 
                max_tokens=1000
            )
        else:
            # Use a simple fallback if no API key available
            for key, value in offline_responses.items():
                if key in message.lower():
                    ai_response = value
                    break
            else:
                ai_response = default_offline_response
    
    # Get current timestamp in Arabic format
    now = datetime.now()
    arabic_timestamp = now.strftime("%Y/%m/%d %I:%M %p").replace("AM", "ص").replace("PM", "م")
    
    # Store message in the database (in a complete implementation)
    # In this demo, we'll skip the actual DB storage
    
    return jsonify({
        "status": "success", 
        "response": ai_response,
        "timestamp": arabic_timestamp
    })

# Phone data retrieval and comparison
import requests

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
            logger.error(f"API error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error fetching phone data: {e}")
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
            logger.error(f"API error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logger.error(f"Error fetching phone brands: {e}")
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
            logger.error(f"API error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logger.error(f"Error fetching phones by brand: {e}")
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
            data['data']['arabic_specs'] = arabic_specs
            return data.get('data', {})
        else:
            logger.error(f"API error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error fetching phone details: {e}")
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
            logger.error(f"API error: {response.status_code} - {response.text}")
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
        "image": phone_details.get('phone_images', [''])[0] if phone_details.get('phone_images') else "",
        "nfc": "غير معروف",
        "fast_charging": "غير معروف",
        "rating": "غير معروف"
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
