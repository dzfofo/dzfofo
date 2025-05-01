import os
import logging
import json
import requests
import time
from datetime import datetime, timezone

# --- Setup Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- API Keys ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# --- Simple Cache System ---
# Use a simple dictionary to cache responses and reduce API calls
suggestion_cache = {}
alternatives_cache = {}
comparison_cache = {}

# Cache expiration time (24 hours in seconds)
CACHE_EXPIRY = 24 * 60 * 60

def call_openrouter_api(messages, model="openai/gpt-3.5-turbo", temperature=0.7, max_tokens=1000):
    """
    استخدام OpenRouter API للحصول على اقتراحات من نماذج متعددة (GPT-4, Claude, Gemini, إلخ)
    """
    if not OPENROUTER_API_KEY:
        logger.warning("OpenRouter API key not found, returning fallback response")
        return None

    # API endpoint
    url = "https://openrouter.ai/api/v1/chat/completions"

    # Add system instruction optimized for phone recommendations
    system_message = {
        "role": "system",
        "content": (
            "أنت مساعد ذكي متخصص في تكنولوجيا الهواتف الذكية وتقديم توصيات مناسبة. "
            "استخدم معرفتك الواسعة بالهواتف الحديثة لعام 2025 (أحدث الإصدارات من سامسونج، آبل، شاومي، هواوي، نوكيا، إلخ). "
            "قدم إجابات شاملة تتضمن مواصفات محددة، وأسعار تقريبية، ونقاط القوة والضعف لمساعدة المستخدم في اتخاذ قرار مستنير. "
            "تأكد من تغطية المكونات الرئيسية (المعالج، الكاميرا، البطارية، الشاشة، الذاكرة). "
            "دائماً اكتب بالعربية الفصحى مع استخدام المصطلحات التقنية بشكل دقيق. "
            "قدم رأيك المهني مع التبرير."
        )
    }

    # Format messages
    formatted_messages = [system_message]
    for msg in messages:
        formatted_messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    # Build the request payload
    payload = {
        "model": model,
        "messages": formatted_messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    # Set the headers with API key
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://yasmin-chat.app",
        "X-Title": "Yasmin Chat App - Phone Assistant"
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

def suggest_phone(user_requirements):
    """
    اقتراح هاتف بناءً على متطلبات المستخدم
    يستخدم OpenRouter للوصول إلى نموذج GPT-4 أو ما شابه
    """
    # Check if we have cached result for this exact requirements
    cache_key = user_requirements.lower().strip()
    current_time = time.time()
    
    if cache_key in suggestion_cache:
        # Check if cache is still valid
        cached_time, cached_result = suggestion_cache[cache_key]
        if current_time - cached_time < CACHE_EXPIRY:
            logger.info(f"Using cached phone suggestion for: {cache_key[:30]}...")
            return cached_result
    
    # Prepare the user message
    messages = [{
        "role": "user",
        "content": (
            f"أحتاج مساعدتك في اختيار هاتف ذكي مناسب. متطلباتي هي: {user_requirements}\n\n"
            "أرجو أن تقدم لي التوصيات التالية:\n"
            "1. أفضل هاتف يناسب احتياجاتي\n"
            "2. أبرز مواصفاته (المعالج، الكاميرا، البطارية، الشاشة، الذاكرة، المميزات الخاصة)\n"
            "3. سعره التقريبي\n"
            "4. لماذا يناسبني هذا الهاتف استناداً إلى متطلباتي؟\n\n"
            "قدم إجابة منظمة ومختصرة."
        )
    }]
    
    if OPENROUTER_API_KEY:
        # Use GPT-4o or Claude for high-quality suggestions
        response = call_openrouter_api(
            messages, 
            model="openai/gpt-4o", 
            temperature=0.7, 
            max_tokens=1500
        )
        
        # If API call failed, try a different model
        if not response:
            response = call_openrouter_api(
                messages, 
                model="anthropic/claude-3-opus", 
                temperature=0.7, 
                max_tokens=1500
            )
        
        # Cache the result
        if response:
            suggestion_cache[cache_key] = (current_time, response)
            return response
    
    # Fallback response if API is not available
    fallback = (
        "عذراً، لا يمكنني تقديم توصيات بالهواتف في الوقت الحالي بسبب عدم توفر اتصال بالخدمة. "
        "يرجى التحقق من توفر مفتاح API لـ OpenRouter في إعدادات التطبيق، أو المحاولة لاحقاً."
    )
    return fallback

def suggest_cheaper_alternative(phone_name):
    """
    اقتراح بديل أرخص للهاتف المحدد
    استخدام التخزين المؤقت (cache) لتحسين الأداء
    """
    # Check if we have cached result for this phone
    cache_key = phone_name.lower().strip()
    current_time = time.time()
    
    if cache_key in alternatives_cache:
        # Check if cache is still valid
        cached_time, cached_result = alternatives_cache[cache_key]
        if current_time - cached_time < CACHE_EXPIRY:
            logger.info(f"Using cached alternatives for: {cache_key}")
            return cached_result
    
    # Prepare the user message
    messages = [{
        "role": "user",
        "content": (
            f"أنا مهتم بهاتف {phone_name} لكن سعره مرتفع بالنسبة لي. "
            "أريد معرفة بدائل أرخص مع مواصفات مماثلة قدر الإمكان.\n\n"
            "أرجو ترشيح 2-3 بدائل أرخص مع ذكر:\n"
            "1. اسم الهاتف البديل\n"
            "2. نسبة التوفير المتوقعة (كم يمكنني أن أوفر بالتقريب)\n"
            "3. المواصفات التي تم المحافظة عليها والمواصفات التي تم تخفيضها\n"
            "4. سبب اختيار هذا البديل\n\n"
            "قدم الإجابة في نقاط منظمة ومفيدة."
        )
    }]
    
    if OPENROUTER_API_KEY:
        # Use GPT-4o or Claude for high-quality alternatives
        response = call_openrouter_api(
            messages, 
            model="openai/gpt-4o", 
            temperature=0.7, 
            max_tokens=1500
        )
        
        # If API call failed, try a different model
        if not response:
            response = call_openrouter_api(
                messages, 
                model="anthropic/claude-3-opus", 
                temperature=0.7, 
                max_tokens=1500
            )
        
        # Cache the result
        if response:
            alternatives_cache[cache_key] = (current_time, response)
            return response
    
    # Fallback response if API is not available
    fallback = (
        "عذراً، لا يمكنني تقديم بدائل أرخص في الوقت الحالي بسبب عدم توفر اتصال بالخدمة. "
        "يرجى التحقق من توفر مفتاح API لـ OpenRouter في إعدادات التطبيق، أو المحاولة لاحقاً."
    )
    return fallback

def get_advanced_comparison(phone1, phone2):
    """
    إنشاء مقارنة متقدمة بين هاتفين محددين باستخدام AI
    """
    # Create a cache key from both phone names (sorted to ensure same key regardless of order)
    phones = sorted([phone1.lower().strip(), phone2.lower().strip()])
    cache_key = f"{phones[0]}__VS__{phones[1]}"
    current_time = time.time()
    
    if cache_key in comparison_cache:
        # Check if cache is still valid
        cached_time, cached_result = comparison_cache[cache_key]
        if current_time - cached_time < CACHE_EXPIRY:
            logger.info(f"Using cached comparison for: {cache_key}")
            return cached_result
    
    # Prepare the user message
    messages = [{
        "role": "user",
        "content": (
            f"أريد مقارنة متعمقة بين هاتفين: {phone1} و {phone2}.\n\n"
            "أرجو تقديم مقارنة شاملة تغطي الجوانب التالية:\n"
            "1. المعالج وأداء النظام\n"
            "2. الكاميرا وقدرات التصوير\n"
            "3. الشاشة (النوع، الدقة، معدل التحديث)\n"
            "4. البطارية وسرعة الشحن\n"
            "5. نظام التشغيل والواجهة\n"
            "6. التصميم والبناء\n"
            "7. الميزات الخاصة والفريدة لكل هاتف\n"
            "8. فارق السعر وأيهما يقدم قيمة أفضل مقابل المال\n\n"
            "في نهاية المقارنة، أريد توصية واضحة حول أي منهما الأفضل لحالات الاستخدام المختلفة: "
            "للتصوير، للألعاب، للاستخدام اليومي، للبطارية، للاستخدام المتقدم، إلخ.\n\n"
            "استخدم جداول أو نقاط منظمة لتسهيل المقارنة."
        )
    }]
    
    if OPENROUTER_API_KEY:
        # Use GPT-4o for detailed comparisons
        response = call_openrouter_api(
            messages, 
            model="openai/gpt-4o", 
            temperature=0.7, 
            max_tokens=2000
        )
        
        # If API call failed, try a different model
        if not response:
            response = call_openrouter_api(
                messages, 
                model="anthropic/claude-3-opus", 
                temperature=0.7, 
                max_tokens=2000
            )
        
        # Cache the result
        if response:
            comparison_cache[cache_key] = (current_time, response)
            return response
    
    # Fallback response if API is not available
    fallback = (
        "عذراً، لا يمكنني تقديم مقارنة متقدمة في الوقت الحالي بسبب عدم توفر اتصال بالخدمة. "
        "يرجى التحقق من توفر مفتاح API لـ OpenRouter في إعدادات التطبيق، أو المحاولة لاحقاً."
    )
    return fallback