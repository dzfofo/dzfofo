import os
import base64
import json
import logging
import requests
import time
from urllib.parse import quote
# Ensure googletrans is installed (pip install googletrans==4.0.0-rc1)
try:
    from googletrans import Translator
except ImportError:
    logging.warning("googletrans library not found. Translation feature will not work.")
    Translator = None # Set to None if import fails


# --- Setup Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- API Keys from environment variables ---
# These are loaded once when the module is imported
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
VOICERSS_API_KEY = os.environ.get("VOICERSS_API_KEY")
STABILITY_API_KEY = os.environ.get("STABILITY_API_KEY")

# --- Check if API keys are available ---
if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY not set. AI assistant functionality will be limited.")

if not ELEVENLABS_API_KEY:
    logger.warning("ELEVENLABS_API_KEY not set. Will use alternate TTS methods.")

if not VOICERSS_API_KEY:
    logger.warning("VOICERSS_API_KEY not set. VoiceRSS TTS will not be available.")

if not STABILITY_API_KEY:
    logger.warning("STABILITY_API_KEY not set. Image generation will not be available.")

# --- Translation Service ---
translator = None # Initialize translator instance globally or lazily

def get_translator():
    """Get or create a Google Translator instance."""
    global translator
    if Translator is None: # Check if the class was imported successfully
        return None
    if translator is None:
        try:
            translator = Translator()
        except Exception as e:
            logger.error(f"Failed to initialize Google Translator: {e}")
            translator = False # Set to False to indicate failure
    return translator if translator else None

def preprocess_arabic_text(text):
    """
    Preprocess Arabic text to improve pronunciation with TTS services.
    This helps improve the speech output quality for Arabic text.

    The preprocessing includes:
    1. Adding appropriate breaks for punctuation
    2. Handling special Arabic characters
    3. Optimizing for better pronunciation
    """
    if not text:
        return ""

    # Replace common punctuation with pauses (using SSML-like syntax or just spaces/newlines)
    # Simpler approach for general compatibility: just add spaces around punctuation
    # Note: This might need fine-tuning based on the specific TTS engine.
    text = text.replace('،', ' ، ')
    text = text.replace('؛', ' ؛ ')
    text = text.replace('؟', ' ؟ ')
    text = text.replace('!', ' ! ')
    text = text.replace('.', ' . ')
    text = text.replace(':', ' : ')
    text = text.replace('-', ' - ')

    # Add breaks at line returns for better phrasing
    text = text.replace('\n', '.\n') # Replace newline with period and newline for better sentence separation

    # Normalize Arabic characters (minimal normalization)
    # ElevenLabs multilingual model is generally good, over-normalization might hurt
    # text = text.replace('ة', 'ه') # Decide if this is needed based on testing
    # text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا') # Decide if this is needed based on testing

    # Remove excessive spaces
    text = ' '.join(text.split())

    return text

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

    # Preprocess Arabic text for better pronunciation with VoiceRSS
    processed_text = preprocess_arabic_text(text) # Use shared preprocessing

    try:
        # Build the VoiceRSS API URL
        encoded_text = quote(processed_text, safe='') # Use safe='' to encode all special chars
        url = f"https://api.voicerss.org/?key={VOICERSS_API_KEY}&hl={language}&src={encoded_text}&r=0&c=mp3&f=44khz_16bit_stereo"

        logger.info(f"Using VoiceRSS API with language {language} and voice {voice}")

        # VoiceRSS returns MP3 directly if successful
        # We can't use HEAD request as it doesn't confirm actual audio content
        # A GET request might consume quota even if we don't download the body immediately.
        # For simplicity and checking, just return the URL. The browser will handle GET.
        # Caveat: This doesn't confirm success, just URL construction.
        return url

    except Exception as e:
        logger.error(f"Error with VoiceRSS API: {e}")
        return None


def text_to_speech(text, voice_id="EXAVITQu4vr4xnSDxMaL", tts_service="elevenlabs"):
    """
    Convert text to speech using either ElevenLabs or VoiceRSS.
    Optimized for Arabic language with enhanced processing and error handling.

    Parameters:
    - text: The text to convert to speech
    - voice_id: The voice ID for ElevenLabs (ignored if not using ElevenLabs)
    - tts_service: Either "elevenlabs", "voicerss", or "browser". Defaults to "elevenlabs".

    Returns:
    - A dictionary {'type': 'base64', 'audio': base64_string} if successful with ElevenLabs.
    - A dictionary {'type': 'url', 'audio': url_string} if successful with VoiceRSS.
    - A dictionary {'type': 'browser', 'text': original_text} if using browser fallback or requested.
    - None if all API methods fail and browser fallback is not requested/available.
    """
    # Validate input
    if not text or not text.strip():
        logger.warning("Empty text provided to text_to_speech")
        return None

    processed_text = preprocess_arabic_text(text)

    # --- Try ElevenLabs (if requested or default) ---
    if (tts_service == "elevenlabs" or tts_service == "default") and ELEVENLABS_API_KEY:
        logger.info("Attempting TTS with ElevenLabs...")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }
        payload = {
            "text": processed_text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }
        try:
            max_timeout = 60 if len(processed_text) > 500 else 30
            response = requests.post(url, headers=headers, json=payload, timeout=max_timeout)
            if response.status_code == 200:
                logger.info("ElevenLabs API request successful")
                audio_base64 = base64.b64encode(response.content).decode('utf-8')
                return {'type': 'base64', 'audio': audio_base64}
            else:
                 logger.error(f"ElevenLabs API error: {response.status_code} - {response.text}")
                 # Fall through to next method
        except requests.exceptions.Timeout:
             logger.error("ElevenLabs API request timed out.")
             # Fall through to next method
        except Exception as e:
            logger.error(f"Error calling ElevenLabs API: {e}")
            # Fall through to next method

    # --- Try VoiceRSS (if requested or if ElevenLabs failed) ---
    if (tts_service == "voicerss" or (tts_service in ["elevenlabs", "default"] and not ELEVENLABS_API_KEY)) and VOICERSS_API_KEY:
        logger.info("Attempting TTS with VoiceRSS...")
        # Use original text for VoiceRSS for now, or adjust preprocessing if needed
        voicerss_url = voicerss_text_to_speech(text)
        if voicerss_url:
             logger.info("VoiceRSS TTS successful")
             return {'type': 'url', 'audio': voicerss_url}
        else:
             logger.warning("VoiceRSS TTS failed")
             # Fall through to next method

    # --- Fallback to Browser TTS (if requested or if APIs failed) ---
    if tts_service == "browser" or (not ELEVENLABS_API_KEY and not VOICERSS_API_KEY) or (tts_service != "browser" and tts_service != "voicerss" and tts_service != "elevenlabs"):
        logger.warning("Using browser TTS as no API is available, explicitly requested, or previous APIs failed.")
        # The browser will handle the text-to-speech
        return {'type': 'browser', 'text': text}

    # --- All methods failed ---
    logger.error("All requested/available TTS methods failed.")
    return None


def call_openrouter_api(messages, model="openai/gpt-3.5-turbo", temperature=0.7, max_tokens=1000, system_message=None):
    """
    Call the OpenRouter API to generate a response
    Support for Gemini 1.5, Gemini Pro, Claude and GPT-4 models

    Parameters:
    - messages: List of message objects (e.g., [{"role": "user", "content": "..."}]).
                Can also be a single string, which will be wrapped as a user message.
    - model: The model to use (e.g., "openai/gpt-4o", "anthropic/claude-3-opus")
    - temperature: Controls randomness (0.0 to 1.0)
    - max_tokens: Maximum number of tokens to generate
    - system_message: Optional system message(s) to set the behavior of the assistant (string or list of strings)

    Returns: The generated text response string, or a string indicating error on failure.
    """
    if not OPENROUTER_API_KEY:
        logger.warning("OpenRouter API key not found.")
        return "عذراً، لا يمكنني الوصول إلى واجهة الذكاء الاصطناعي حالياً. يرجى التأكد من مفتاح API الخاص بك في الإعدادات."

    # API endpoint
    url = "https://openrouter.ai/api/v1/chat/completions"

    # Headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://yasmin-ai.replit.app", # Update Referer for OpenRouter analytics
        "X-Title": "Yasmin AI Assistant"
    }

    # Prepare messages list starting with system message
    formatted_messages = []

    if system_message:
        if isinstance(system_message, str):
             formatted_messages.append({"role": "system", "content": system_message})
        elif isinstance(system_message, list):
             # Allow multiple system messages if the model supports it, or just join them
             formatted_messages.extend([{"role": "system", "content": msg} for msg in system_message])
        else:
             logger.warning(f"Invalid system_message type: {type(system_message)}. Must be string or list of strings.")


    # Add user/assistant messages from the input
    if isinstance(messages, list):
        # Ensure messages list doesn't contain system messages if we added one already
        user_assistant_messages = [msg for msg in messages if msg.get("role") in ["user", "assistant", "tool"]] # Add tool role if needed
        formatted_messages.extend(user_assistant_messages)
    elif isinstance(messages, str):
         # Wrap single string input as a user message
         formatted_messages.append({"role": "user", "content": messages})
    else:
        logger.error(f"Messages input must be a list of message objects or a string, got {type(messages)}")
        return "حدث خطأ داخلي في معالجة رسالة المستخدم."

    # Add a default system message if none was provided explicitly and none exists in input messages
    if not system_message and not any(msg.get("role") == "system" for msg in formatted_messages):
         formatted_messages.insert(0, { # Insert at the beginning
            "role": "system",
            "content": "أنت مساعد ذكي ومفيد باللغة العربية اسمه ياسمين. أجب دائماً باللغة العربية الفصحى ما لم يطلب المستخدم لغة أخرى. قدم معلومات دقيقة وشاملة. تجنب الإجابات الطويلة جداً. اليوم هو 1 مايو 2025."
         })


    # Data payload
    data = {
        "model": model,
        "messages": formatted_messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    try:
        logger.info(f"Calling OpenRouter API with model: {model}, messages count: {len(formatted_messages)}, temp: {temperature}, max_tokens: {max_tokens}")
        response = requests.post(url, headers=headers, json=data, timeout=90) # Increased timeout for potentially complex requests

        # Check for successful response
        if response.status_code == 200:
            response_data = response.json()
            # Extract and return the generated text
            if response_data and "choices" in response_data and len(response_data["choices"]) > 0 and "message" in response_data["choices"][0] and "content" in response_data["choices"][0]["message"]:
                 return response_data["choices"][0]["message"]["content"]
            else:
                 logger.error(f"OpenRouter API returned empty choices or invalid format: {response_data}")
                 return "تلقيت استجابة فارغة أو غير صالحة من نموذج الذكاء الاصطناعي."
        else:
            logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
            # Attempt to parse error message from API response
            try:
                 error_data = response.json()
                 if "message" in error_data:
                      logger.error(f"OpenRouter API error message: {error_data['message']}")
                      # Return specific error message from API if available
                      return f"حدث خطأ في الاتصال بخدمة الذكاء الاصطناعي: {error_data['message']}"
            except json.JSONDecodeError:
                 pass # Ignore if response is not JSON
            return f"حدث خطأ عام في الاتصال بخدمة الذكاء الاصطناعي. الحالة: {response.status_code}"

    except requests.exceptions.Timeout:
        logger.error("OpenRouter API request timed out.")
        return "استغرق الرد من الذكاء الاصطناعي وقتاً طويلاً وانتهت المهلة."
    except Exception as e:
        logger.error(f"Error calling OpenRouter API: {e}")
        return "حدث خطأ غير متوقع أثناء التواصل مع الذكاء الاصطناعي."


def translate_text(text, target_lang='ar'):
    """
    Translate text to target language using Google Translate
    """
    translator_instance = get_translator()

    if not translator_instance:
        logger.error("Google Translator not initialized. Is googletrans installed?")
        return None

    if not text or not text.strip():
        return ""

    try:
        # Auto-detect source language
        translation = translator_instance.translate(text, dest=target_lang)
        return translation.text
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return None # Return None on error


def generate_image(prompt, size=512):
    """
    Generate image using Stability AI

    Parameters:
    - prompt: The text description for the image to generate
    - size: Image size (e.g., 512, 768, 1024). Check Stability AI docs for supported sizes for the chosen engine.

    Returns: Base64 encoded image string if successful, None otherwise
    """
    if not STABILITY_API_KEY:
        logger.warning("STABILITY_API_KEY not set. Image generation will not work.")
        return None

    # Validate input
    if not prompt or not prompt.strip():
        logger.warning("Empty prompt provided to generate_image")
        return None

    # Determine engine based on desired capabilities or preference
    # Using v1-6 is common, SDXL is also available if needed and key supports it
    engine_id = "stable-diffusion-v1-6" # Or "stable-diffusion-xl-1024-v1-0" for higher res/quality with different pricing/model
    api_host = "https://api.stability.ai"

    # Check if requested size is supported by the chosen model
    supported_sizes = {
        "stable-diffusion-v1-6": [512, 768], # Add other supported sizes if known
        "stable-diffusion-xl-1024-v1-0": [1024]
        # Add other models and their sizes
    }
    if engine_id in supported_sizes and size not in supported_sizes[engine_id]:
         logger.warning(f"Requested size {size} not officially listed for {engine_id}. Using default size 512.")
         size = 512 # Fallback to a safe size if not supported

    # Basic prompt safety check (optional but recommended)
    # In a real app, use a moderation API

    try:
        logger.info(f"Calling Stability AI API with prompt: {prompt[:50]}..., size: {size}x{size}")
        response = requests.post(
            f"{api_host}/v1/generation/{engine_id}/text-to-image",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {STABILITY_API_KEY}"
            },
            json={
                "text_prompts": [
                    {
                        "text": prompt,
                        "weight": 1.0
                    }
                ],
                "cfg_scale": 7.0, # Classifier Free Guidance Scale
                "height": size,
                "width": size,
                "samples": 1, # Number of images to generate (1 for this use case)
                "steps": 30,  # Number of diffusion steps (higher = better quality, slower, more compute)
                "seed": 0 # Use a fixed seed for reproducibility or random
            },
            timeout=90 # Increased timeout for image generation
        )

        if response.status_code == 200:
            data = response.json()
            # Get base64 encoded image
            if data and "artifacts" in data and data["artifacts"]:
                logger.info("Stability API request successful, image generated.")
                return data["artifacts"][0]["base64"]
            else:
                logger.error("No image artifacts in Stability API response")
                return None
        else:
            logger.error(f"Stability API error: {response.status_code} - {response.text}")
            # Attempt to parse error message from API response
            try:
                 error_data = response.json()
                 if "message" in error_data:
                      logger.error(f"Stability API error message: {error_data['message']}")
                      # Return specific error message from API if available
                      return None # Or return error_data['message'] if you want to show it to user
            except json.JSONDecodeError:
                 pass # Ignore if response is not JSON
            return None

    except requests.exceptions.Timeout:
        logger.error("Stability API request timed out.")
        return None # Or return a timeout message
    except Exception as e:
        logger.error(f"Error with Stability API: {e}")
        return None
