import os
import base64
import json
import logging
import requests
from urllib.parse import quote

# --- Setup Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- API Keys from environment variables ---
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
        
    # Replace common punctuation with pauses
    text = text.replace('،', ', ')
    text = text.replace('؛', '; ')
    text = text.replace('؟', '? ')
    text = text.replace('!', '! ')
    
    # Add breaks at line returns for better phrasing
    text = text.replace('\n', '\n')
    
    # Normalize Arabic characters for better pronunciation
    text = text.replace('ة', 'ه')
    
    # Add spaces around certain characters for better pronunciation
    punctuation = ['،', '؛', '؟', '!', '.', ':', '-']
    for p in punctuation:
        text = text.replace(p, f' {p} ')
    
    # Remove excessive spaces
    text = ' '.join(text.split())
    
    return text

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
    
    # Log the processed text for debugging (truncate if too long)
    logger.info(f"Processed text for TTS: {processed_text[:100]}..." if len(processed_text) > 100 else processed_text)
    
    # ElevenLabs API endpoint
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    
    # Request headers
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    
    # Request payload
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
        logger.info(f"Calling ElevenLabs API with voice {voice_id}, timeout 30s")
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            logger.info("ElevenLabs API request successful")
            # Return base64 encoded audio
            audio_base64 = base64.b64encode(response.content).decode('utf-8')
            return audio_base64
        else:
            logger.error(f"ElevenLabs API error: {response.status_code} - {response.text}")
            
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

def call_openrouter_api(messages, model="openai/gpt-3.5-turbo", temperature=0.7, max_tokens=1000, system_message=None):
    """
    Call the OpenRouter API to generate a response
    Support for Gemini 1.5, Gemini Pro, Claude and GPT-4 models
    
    Parameters:
    - messages: List of message objects or a single string prompt
    - model: The model to use (e.g., "openai/gpt-4o", "anthropic/claude-3-opus")
    - temperature: Controls randomness (0.0 to 1.0)
    - max_tokens: Maximum number of tokens to generate
    - system_message: Optional system message to set the behavior of the assistant
    
    Returns: The generated text response
    """
    if not OPENROUTER_API_KEY:
        logger.warning("OpenRouter API key not found, returning fallback response")
        return "عذراً، لا يمكنني الوصول إلى واجهة الذكاء الاصطناعي حالياً. يرجى التأكد من مفتاح API الخاص بك."

    # API endpoint
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    # Headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://yasmin-ai.replit.app",
        "X-Title": "Yasmin AI Assistant"
    }
    
    # Prepare messages according to the input type
    formatted_messages = []
    
    # Add system message if provided
    if system_message:
        formatted_messages.append({"role": "system", "content": system_message})
    
    # Handle string input by converting to a user message
    if isinstance(messages, str):
        formatted_messages.append({"role": "user", "content": messages})
    # Handle array of message objects
    elif isinstance(messages, list):
        formatted_messages.extend(messages)
    
    # Data payload
    data = {
        "model": model,
        "messages": formatted_messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    try:
        # Make the API call
        response = requests.post(url, headers=headers, json=data)
        
        # Check for successful response
        if response.status_code == 200:
            response_data = response.json()
            # Extract and return the generated text
            return response_data["choices"][0]["message"]["content"]
        else:
            logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
            return f"حدث خطأ في الاتصال بخدمة الذكاء الاصطناعي.\nيرجى التحقق من المفتاح والاتصال بالإنترنت."

    except Exception as e:
        logger.error(f"Error calling OpenRouter API: {e}")
        return "حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى لاحقاً."

def translate_text(text, target_lang):
    """
    Translate text to target language using Google Translate
    """
    from googletrans import Translator
    
    if not text or not text.strip():
        return ""
        
    try:
        translator = Translator()
        translation = translator.translate(text, dest=target_lang)
        return translation.text
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return text  # Return original text on error

def generate_image(prompt, size=512):
    """
    Generate image using Stability AI
    
    Parameters:
    - prompt: The text description for the image to generate
    - size: Image size (512, 768, etc.)
    
    Returns: Base64 encoded image if successful, None otherwise
    """
    if not STABILITY_API_KEY:
        logger.warning("STABILITY_API_KEY not set. Image generation will not work.")
        return None
        
    # Validate input
    if not prompt or not prompt.strip():
        logger.warning("Empty prompt provided to generate_image")
        return None

    engine_id = "stable-diffusion-v1-6"
    api_host = "https://api.stability.ai"
    
    try:
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
                "cfg_scale": 7.0,
                "height": size,
                "width": size,
                "samples": 1,
                "steps": 30,
            },
        )

        if response.status_code == 200:
            data = response.json()
            # Get base64 encoded image
            if data["artifacts"]:
                return data["artifacts"][0]["base64"]
            else:
                logger.error("No image generated in response")
                return None
        else:
            logger.error(f"Stability API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error with Stability API: {e}")
        return None
