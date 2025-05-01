import os
import json
import logging
import base64
import requests
from flask import Flask, render_template, request, jsonify, send_file, Response
from urllib.parse import quote

# --- Setup Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Initialize Flask app ---
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "yasmin_voice_assistant")

# --- API Keys from environment variables ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICERSS_API_KEY = os.environ.get("VOICERSS_API_KEY")

# --- Check if API keys are available ---
if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY not set. Voice assistant functionality will be limited.")
    
if not ELEVENLABS_API_KEY:
    logger.warning("ELEVENLABS_API_KEY not set. Will use alternate TTS methods.")

if not VOICERSS_API_KEY:
    logger.warning("VOICERSS_API_KEY not set. VoiceRSS TTS will not be available.")

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

def voicerss_text_to_speech(text, language="ar-sa", voice="Leila"):
    """
    Convert text to speech using VoiceRSS API.
    Optimized for Arabic language.
    
    Returns audio URL if successful, None otherwise.
    """
    if not VOICERSS_API_KEY:
        logger.warning("VOICERSS_API_KEY environment variable is not set. VoiceRSS TTS functionality won't work.")
        return None

    # Validate input
    if not text or not text.strip():
        logger.warning("Empty text provided to voicerss_text_to_speech")
        return None

    # Preprocess Arabic text for better pronunciation
    processed_text = preprocess_arabic_text(text)
    
    try:
        # Build the VoiceRSS API URL
        encoded_text = quote(processed_text)
        url = f"https://api.voicerss.org/?key={VOICERSS_API_KEY}&hl={language}&src={encoded_text}&r=0&c=mp3&f=44khz_16bit_stereo"
        
        logger.info(f"Using VoiceRSS API with language {language} and voice {voice}")
        
        # Test if the URL is valid by making a head request
        response = requests.head(url, timeout=10)
        if response.status_code == 200:
            logger.info("VoiceRSS API request successful")
            return url
        else:
            logger.error(f"VoiceRSS API error: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Error with VoiceRSS API: {e}")
        return None


def text_to_speech(text, voice_id="EXAVITQu4vr4xnSDxMaL", tts_service="elevenlabs"):
    """
    Convert text to speech using either ElevenLabs or VoiceRSS.
    Optimized for Arabic language with enhanced processing and error handling.
    
    Parameters:
    - text: The text to convert to speech
    - voice_id: The voice ID for ElevenLabs
    - tts_service: Either "elevenlabs" or "voicerss"
    
    Returns base64 encoded audio data if successful with ElevenLabs,
    or audio URL if successful with VoiceRSS, None otherwise.
    """
    # Validate input
    if not text or not text.strip():
        logger.warning("Empty text provided to text_to_speech")
        return None

    # Try VoiceRSS if requested
    if tts_service == "voicerss" and VOICERSS_API_KEY:
        return voicerss_text_to_speech(text)
    
    # Otherwise use ElevenLabs (default)
    if not ELEVENLABS_API_KEY:
        # Fall back to VoiceRSS if ElevenLabs isn't available
        if VOICERSS_API_KEY:
            logger.info("Falling back to VoiceRSS as ElevenLabs API key is missing")
            return voicerss_text_to_speech(text)
        logger.warning("No TTS API keys available. Text-to-speech functionality won't work.")
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
            # Encode audio content to base64 for sending to browser
            audio_base64 = base64.b64encode(response.content).decode('utf-8')
            return audio_base64
        else:
            logger.error(f"ElevenLabs API error: {response.status_code} - {response.text}")
            
            # Try one more time with different model if first attempt failed
            if "model_id" in payload and payload["model_id"] == "eleven_multilingual_v2":
                logger.info("Retrying with eleven_turbo model...")
                payload["model_id"] = "eleven_turbo"
                response = requests.post(url, headers=headers, json=payload, timeout=max_timeout)
                
                if response.status_code == 200:
                    logger.info("ElevenLabs API retry successful with eleven_turbo model")
                    audio_base64 = base64.b64encode(response.content).decode('utf-8')
                    return audio_base64
            
            # Try VoiceRSS as fallback if ElevenLabs fails
            if VOICERSS_API_KEY:
                logger.info("Falling back to VoiceRSS as ElevenLabs failed")
                return voicerss_text_to_speech(text)
            
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
                    audio_base64 = base64.b64encode(response.content).decode('utf-8')
                    return audio_base64
                else:
                    logger.error(f"Retry failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"Error in retry attempt: {e}")
                
        # Try VoiceRSS as fallback if ElevenLabs times out
        if VOICERSS_API_KEY:
            logger.info("Falling back to VoiceRSS as ElevenLabs timed out")
            return voicerss_text_to_speech(text)
            
        return None
        
    except Exception as e:
        logger.error(f"Error calling ElevenLabs API: {e}")
        
        # Try VoiceRSS as fallback if ElevenLabs throws an exception
        if VOICERSS_API_KEY:
            logger.info("Falling back to VoiceRSS due to ElevenLabs error")
            return voicerss_text_to_speech(text)
            
        return None

def call_openrouter_api(prompt, model="openai/gpt-3.5-turbo", temperature=0.7, max_tokens=1000):
    """
    Call the OpenRouter API to generate a response
    Support for Gemini 1.5, Gemini Pro, Claude and GPT-4 models
    """
    if not OPENROUTER_API_KEY:
        logger.warning("OpenRouter API key not found, returning fallback response")
        return "عذراً، لا يمكنني الوصول إلى واجهة الذكاء الاصطناعي حالياً. يرجى التأكد من مفتاح API الخاص بك."

    # API endpoint
    url = "https://openrouter.ai/api/v1/chat/completions"

    # Build system message for better Arabic responses
    system_message = {
        "role": "system",
        "content": "أنت مساعد ذكي ومفيد باللغة العربية. أجب دائماً باللغة العربية الفصحى ما لم يطلب المستخدم لغة أخرى. قدم معلومات دقيقة وشاملة. تجنب الإجابات الطويلة جداً."
    }
    
    user_message = {
        "role": "user",
        "content": prompt
    }
    
    # Add the messages
    messages = [system_message, user_message]

    # Special handling for Gemini models
    is_gemini = "gemini" in model.lower()

    # Build the request payload
    payload = {
        "model": model,
        "messages": messages,
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
        "HTTP-Referer": "https://yasmin-voice-assistant.app",
        "X-Title": "Yasmin Voice Assistant"
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
                return "عذراً، تلقيت استجابة غير صالحة من الخادم. يرجى المحاولة مرة أخرى."
        else:
            logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
            return "حدث خطأ في الاتصال بخدمة الذكاء الاصطناعي. يرجى التحقق من المفتاح والاتصال بالإنترنت."

    except Exception as e:
        logger.error(f"Error calling OpenRouter API: {e}")
        return "حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى لاحقاً."

# --- Routes ---

@app.route('/')
def index():
    # Determine models available based on API keys
    has_openrouter = bool(OPENROUTER_API_KEY)
    has_elevenlabs = bool(ELEVENLABS_API_KEY)
    has_voicerss = bool(VOICERSS_API_KEY)
    
    return render_template('voice_assistant.html', 
                          has_openrouter=has_openrouter,
                          has_elevenlabs=has_elevenlabs,
                          has_voicerss=has_voicerss)

@app.route("/api/voice_assistant", methods=["POST"])
def voice_assistant():
    """Process voice input and generate AI response"""
    data = request.get_json()
    user_prompt = data.get("prompt", "")
    model = data.get("model", "mistralai/mixtral-8x7b-instruct")
    tts_service = data.get("tts_service", "elevenlabs")  # Default to ElevenLabs but allow override
    
    if not user_prompt:
        return jsonify({"status": "error", "message": "لم يتم توفير نص للمعالجة"})
    
    # Call OpenRouter API to get AI response
    ai_response = call_openrouter_api(user_prompt, model=model)
    
    # Generate audio using the requested TTS service
    voice_id = data.get("voice_id", "EXAVITQu4vr4xnSDxMaL")
    audio_result = text_to_speech(ai_response, voice_id=voice_id, tts_service=tts_service)
    
    # Determine if we got back a URL (VoiceRSS) or base64 data (ElevenLabs)
    audio_type = "url" if audio_result and not audio_result.startswith("data:") and not audio_result.startswith("UklGR") else "base64"
    
    return jsonify({
        "status": "success",
        "reply": ai_response,
        "audio": audio_result,
        "audio_type": audio_type
    })

if __name__ == "__main__":
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)