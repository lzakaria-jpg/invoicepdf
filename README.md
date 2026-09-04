# أداة استخراج بيانات الفواتير إلى Excel

أداة ويب لاستخراج بيانات الفواتير/العروض/الإيصالات (PDF وصور) تلقائياً
إلى ملف Excel، تعمل مع 70+ تصميم مختلف وبدون أي تصميم محدد مسبقاً.

## المتطلبات على جهاز التثبيت

1. **Python 3.9+** من https://www.python.org/downloads/
   - أثناء التثبيت فعّل خيار **"Add Python to PATH"**.
2. **Tesseract OCR** (لقراءة أسماء العملاء من الصور/المسح):
   - ويندوز: https://github.com/UB-Mannheim/tesseract/wiki (ثبّت النسخة مع خيار اللغة؛
     عند الطلب فعّل **Arabic** في قائمة لغات التثبيت).
   - أهم خطوة: بعد التثبيت فتح ملف:
     `C:\Program Files\Tesseract-OCR\tessdata` (أو Corbomite) — وفي حال عدم وجود
     ملف اللغة العربية `ara.traineddata` حمّله من:
     https://github.com/tesseract-ocr/tessdata_best/raw/main/ara.traineddata
     وضعه داخل مجلد `tessdata`.

## طريقة التشغيل (ويندوز)

1. افتح المجلد وضع ملفاتك الجاهزة (لا شيء يحتاج تعديل — الواجهة تختار المجلد).
2. شغّل ملف **`تشغيل الأداة.bat`** (أو يدوياً):
   ```
   pip install -r requirements.txt
   python server.py
   ```
3. افتح المتصفح على: `http://localhost:5000`
4. في الواجهة: ضع مسار المجلد الذي فيه الفواتير → ابدأ المعالجة → نزّل ملف Excel.

## لكي يعمل على Linux/Mac (اختياري)

```
sudo apt install tesseract-ocr tesseract-ocr-ara
pip install -r requirements.txt
python server.py
```

## مشاركة مع زميل

- نفس الشبكة: افتح `http://<IP-جهازك>:5000` (رابط الأداة يعرضه في الجهاز).
- ريبو جيت هب: ينسخ الزميل المشروع ويشغّل كما بالأعلى على جهازه.