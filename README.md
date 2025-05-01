
# ياسمين AI - مساعدك الذكي العربي

تطبيق "ياسمين" هو مساعد صوتي وكتابي ذكي باللغة العربية، يجمع بين تقنيات الذكاء الاصطناعي وخدمات مقارنة الأجهزة وتحويل النصوص إلى صوت.  
حالياً في **مرحلة تجريبية أولى**، مفتوح للتطوير والتحسين خطوة بخطوة.

---

## الميزات

- **مساعد صوتي** باستخدام ElevenLabs وVoiceRSS.
- **محادثات ذكية** عبر OpenRouter (GPT-4 / Claude / Gemini).
- **مقارنة هواتف ذكية** مباشرة من API خارجي.
- **واجهة عربية متجاوبة وسهلة الاستخدام**.
- تخصيص المستخدم بالاسم والجلسة.

---

## المتطلبات (Dependencies)

- Python 3.9+
- Flask
- Flask-Session
- Flask-SQLAlchemy
- Flask-Login
- requests
- googletrans==4.0.0rc1 (للترجمة)

---

## التشغيل المحلي

```bash
# 1. إنشاء البيئة
python -m venv venv
source venv/bin/activate  # أو venv\Scripts\activate على ويندوز

# 2. تثبيت الحزم
pip install -r requirements.txt

# 3. إعداد المتغيرات البيئية (داخل .env أو مباشرة)
export OPENROUTER_API_KEY=your_key
export ELEVENLABS_API_KEY=your_key
export VOICERSS_API_KEY=your_key
export SESSION_SECRET=your_secret

# 4. تشغيل التطبيق
python app.py


---

المتغيرات البيئية المطلوبة


---

النشر على Render

اربط المشروع بمستودع Git الخاص بك.

عيّن المتغيرات البيئية في إعدادات Render.

تأكد من تحديد Build Command:

pip install -r requirements.txt

و Start Command:

python app.py



---

ملاحظات

المشروع لا يزال قيد التطوير والتجربة.

أي مساهمات أو ملاحظات مرحّب بها!

جميع الأكواد والواجهات مكتوبة باللغة العربية أو تدعم العربية بشكل كامل.



---

المؤلف

ياسمين AI - فكرة وتطوير: [اسمك هنا]
للتواصل: [بريدك الإلكتروني أو صفحتك]
