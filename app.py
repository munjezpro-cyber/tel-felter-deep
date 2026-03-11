from flask import Flask, render_template, request, redirect, url_for, flash, session
from telethon import TelegramClient, events, errors
import asyncio
import os
import sqlite3
import json
import aiohttp
import threading
import time
import re
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "simple-secret-key-change-this")

# -------------------------------------------------------------------
# 1. قاعدة البيانات (SQLite بسيطة)
# -------------------------------------------------------------------
DB_PATH = "radar.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # جدول الحسابات
    c.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            phone TEXT PRIMARY KEY,
            api_id INTEGER NOT NULL,
            api_hash TEXT NOT NULL,
            alert_group TEXT,
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # جدول الكلمات المفتاحية
    c.execute('''
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL
        )
    ''')
    # جدول الإعدادات
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # -----------------------------------------------------------------
    # إدراج الكلمات المفتاحية الافتراضية (القائمة الضخمة)
    # -----------------------------------------------------------------
    c.execute("SELECT COUNT(*) FROM keywords")
    if c.fetchone()[0] == 0:
        default_keywords = [
            # طلبات المساعدة العامة
            'مساعدة', 'ساعدوني', 'ساعدني', 'أبي أحد', 'أبي حد', 'أبي مساعدة', 'محتاج', 'محتاجة', 'ضروري', 'مستعجل', 'أرجوكم', 'لو سمحتم',
            'الرجاء المساعدة', 'تحتاج مساعدة', 'نحتاج مساعدة', 'يحتاج مساعدة', 'تحتاج مساعدة',
            
            # الواجبات والتكاليف
            'واجب', 'واجبات', 'تكليف', 'تكاليف', 'حل', 'يحل', 'اسايمنت', 'assignment', 'homework', 'تكليفات', 'واجبي', 'واجباتي', 'أسايمنت',
            'حل واجب', 'حل الواجب', 'حل التكليف', 'حل التكاليف', 'حل أسايمنت', 'حل assignment',
            
            # البحوث والتقارير
            'بحث', 'بحوث', 'تقرير', 'تقارير', 'ريبورت', 'report', 'research', 'بحثي', 'تقريري', 'دراسة', 'دراسة حالة', 'case study', 'رسالة', 'رسائل',
            'إعداد بحث', 'كتابة بحث', 'عمل بحث', 'عمل تقرير', 'إعداد تقرير', 'كتابة تقرير', 'تحضير بحث', 'تحضير تقرير',
            
            # المشاريع
            'مشروع', 'مشاريع', 'بروجكت', 'project', 'بروجيكت', 'مشروع تخرج', 'مشاريع تخرج', 'مشروعي', 'بروجكتي', 'خطة مشروع', 'مشروع نهائي',
            'مشروع تخرجي', 'مشروع الجامعة', 'مشروع الكلية', 'مشروع التخرج', 'مشاريع التخرج',
            
            # العروض التقديمية والتصاميم
            'برزنتيشن', 'presentation', 'بوربوينت', 'powerpoint', 'عرض', 'عروض', 'تصميم', 'تصاميم', 'بوستر', 'poster', 'برشور', 'brochure', 'انفوجرافيك', 'infographic', 'خريطة ذهنية', 'mind map',
            'عرض تقديمي', 'عروض تقديمية', 'تصميم بوربوينت', 'تصميم عرض', 'تصميم بوستر', 'تصميم برشور', 'تصميم انفوجرافيك',
            
            # الفيديوهات والوسائط
            'فيديو', 'فيديوهات', 'مونتاج', 'مقطع', 'تصوير', 'تحرير', 'انميشن', 'animation', 'موشن جرافيك', 'motion graphic',
            'مونتاج فيديو', 'تحرير فيديو', 'تصميم فيديو', 'تصوير فيديو', 'مقاطع فيديو',
            
            # الاختبارات
            'اختبار', 'اختبارات', 'كويز', 'كويزات', 'فاينل', 'ميد', 'امتحان', 'امتحانات', 'اختبار نهائي', 'اختبار منتصف', 'كويزات',
            'اختبارات نهائية', 'اختبارات منتصف', 'امتحان نهائي', 'امتحان منتصف', 'حل اختبار', 'حل امتحان', 'حل كويز',
            
            # الشرح والمساعدة
            'شرح', 'يشرح', 'درس', 'دروس', 'ملخص', 'ملخصات', 'مذكرة', 'مذكرات', 'أساسيات', 'تمارين', 'تدريبات', 'فهم', 'استيعاب', 'تبسيط',
            'شرح درس', 'شرح مادة', 'شرح موضوع', 'دروس خصوصية', 'دروس تقوية', 'ملخصات مواد', 'تلخيص مادة', 'تلخيص كتاب',
            
            # التخصصات
            'رياضيات', 'فيزياء', 'كيمياء', 'أحياء', 'إنجليزي', 'عربي', 'تاريخ', 'جغرافيا', 'فلسفة', 'منطق', 'قانون', 'محاسبة', 'اقتصاد', 'إدارة', 'تسويق', 'برمجة', 'علوم حاسب', 'هندسة', 'طب', 'صيدلة', 'تمريض', 'حقوق', 'علوم سياسية', 'إعلام',
            'رياضيات بحتة', 'رياضيات تطبيقية', 'فيزياء عامة', 'فيزياء نووية', 'كيمياء عضوية', 'كيمياء تحليلية', 'أحياء دقيقة', 'أحياء جزيئية',
            
            # طلب مدرس خصوصي
            'دكتور خصوصي', 'مدرس خصوصي', 'معلم خصوصي', 'مدرسة خصوصية', 'دروس خصوصية', 'تدريس خصوصي', 'شرح خصوصي', 'يشرح خصوصي', 'معيد', 'متخصص',
            'أستاذ خصوصي', 'مدرس خصوصي رياضيات', 'مدرس خصوصي فيزياء', 'مدرس خصوصي كيمياء', 'مدرس خصوصي إنجليزي',
            
            # استفسارات عن موارد
            'تعرفون أحد', 'تعرفون حد', 'من يعرف', 'من تعرف', 'أحد يعرف', 'حد يعرف', 'وين ألقى', 'كيف ألقى', 'كيف أحصل', 'مصدر', 'مرجع',
            'عندكم فكرة', 'أحد عنده خبرة', 'من جرب', 'تجربة', 'نصيحة', 'توجيه', 'إرشاد',
            
            # خدمات متنوعة
            'ترجمة', 'تلخيص', 'تدقيق', 'صياغة', 'كتابة', 'إعداد', 'تنفيذ', 'استشارة', 'توجيه', 'إرشاد', 'مراجعة', 'تصحيح',
            'ترجمة نص', 'تلخيص كتاب', 'تدقيق لغوي', 'صياغة قانونية', 'كتابة مقال', 'إعداد خطة', 'تنفيذ مشروع',
            
            # كلمات إضافية
            'مراجعة', 'ليالي الامتحان', 'أسئلة', 'إجابات', 'نماذج', 'تجميعات', 'شروحات', 'تبسيط', 'حفظ', 'تذكر',
            'مراجعة ليلة الامتحان', 'أسئلة سنوات سابقة', 'نماذج اختبارات', 'تجميعات أسئلة', 'شروحات فيديو',
            
            # رسائل أكاديمية عليا
            'رسالة ماجستير', 'رسالة دكتوراه', 'أطروحة', 'بحث علمي', 'نشر', 'ورقة بحثية', 'مؤتمر', 'مجلة علمية', 'تحكيم', 'نشر علمي',
            'إعداد رسالة ماجستير', 'كتابة أطروحة', 'نشر بحث', 'مؤتمر علمي', 'مجلة محكمة',
            
            # برمجة وتقنية
            'برمجة', 'كود', 'برنامج', 'تطبيق', 'موقع', 'نظام', 'قاعدة بيانات', 'خوارزمية', 'هيكل بيانات', 'واجهة', 'تصميم', 'اختبار', 'debug', 'troubleshooting',
            'برمجة بايثون', 'برمجة جافا', 'برمجة سي', 'تطوير موقع', 'تصميم واجهات', 'اختبار برمجيات',
            
            # هندسة وتصميم
            'رسم', 'أوتوكاد', 'سوليدوركس', 'ريفيت', 'ديزاين', 'تصميم معماري', 'إنشائي', 'ميكانيكي', 'كهربائي', 'civil', 'mechanical', 'electrical',
            'رسومات هندسية', 'تصميم معماري', 'تصميم داخلي', 'مخططات هندسية', 'خرائط',
            
            # جرافيك وتصميم
            'فوتوشوب', 'إليستريتور', 'ان ديزاين', 'جرافيك', 'graphic design', 'تصميم جرافيكي', 'شعار', 'logo', 'هوية', 'identity', 'براند', 'brand',
            'تصميم شعار', 'هوية بصرية', 'براندينغ', 'تصميم إعلانات',
            
            # ترجمة وتحرير
            'ترجمة لغة', 'ترجمة إنجليزي', 'ترجمة عربي', 'ترجمة علمية', 'ترجمة أدبية', 'تلخيص كتاب', 'تلخيص مقال', 'تحرير نص', 'تدقيق لغوي',
            'ترجمة وثائق', 'ترجمة أبحاث', 'تدقيق نحوي', 'تحرير أكاديمي',
            
            # صيغ طلب المساعدة
            'أحد يساعد', 'أحد يحل', 'أحد يشرح', 'أحد يعمل', 'أحد يسوي', 'أحد يصمم', 'أحد يبرمج', 'أحد يترجم', 'أحد يلخص', 'أحد يدقق', 'أحد يراجع',
            'اللي عنده خبرة', 'اللي يقدر يساعد', 'اللي يعرف', 'اللي عنده فكرة',
            
            # كلمات خليجية إضافية
            'ابي احد', 'ابي حد', 'تعرفون احد', 'تعرفون حد', 'من يعرف احد', 'من يعرف حد', 'احد عنده', 'حد عنده',
            'عندكم', 'فيكم', 'تقدرون', 'تكفون', 'يا جماعة', 'يا شباب', 'يا بنات',
            
            # كلمات إنجليزية شائعة
            'help', 'need help', 'urgent', 'please help', 'assignment help', 'homework help', 'research help', 'project help',
            'essay', 'paper', 'thesis', 'dissertation', 'case study', 'lab report', 'coding help', 'programming help',
            
            # كلمات فارسية (قد تظهر)
            'کمک', 'راهنمایی', 'پروژه', 'تکلیف', 'تحقیق',
            
            # كلمات أردية (قد تظهر)
            'مدد', 'کام', 'پروجیکٹ', 'اسائنمنٹ',
            
            # كلمات متفرقة
            'عاجل', 'هام', 'ضروري جدا', 'الله يجزاكم خير', 'بيض الله وجهكم', 'مشكورين', 'يعطيكم العافية',
            'نبي', 'نبغى', 'تبي', 'تبغى', 'يبي', 'يبغى'
        ]
        for kw in default_keywords:
            c.execute("INSERT OR IGNORE INTO keywords (keyword) VALUES (?)", (kw,))
    
    # إعدادات الذكاء الاصطناعي
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('openrouter_key', ''))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('ai_enabled', '0'))
    
    conn.commit()
    conn.close()

init_db()

# دوال قاعدة البيانات (كما في السابق)
def db_get_keywords():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT keyword FROM keywords")
    keywords = [row[0] for row in c.fetchall()]
    conn.close()
    return keywords

def db_add_keyword(keyword):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO keywords (keyword) VALUES (?)", (keyword,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def db_delete_keyword(keyword):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM keywords WHERE keyword = ?", (keyword,))
    conn.commit()
    conn.close()

def db_get_accounts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT phone, api_id, api_hash, alert_group FROM accounts WHERE enabled = 1")
    accounts = [{'phone': r[0], 'api_id': r[1], 'api_hash': r[2], 'alert_group': r[3]} for r in c.fetchall()]
    conn.close()
    return accounts

def db_add_account(phone, api_id, api_hash, alert_group):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO accounts (phone, api_id, api_hash, alert_group) VALUES (?, ?, ?, ?)",
                  (phone, api_id, api_hash, alert_group))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def db_delete_account(phone):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM accounts WHERE phone = ?", (phone,))
    conn.commit()
    conn.close()

def db_get_setting(key, default=''):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def db_set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

# -------------------------------------------------------------------
# 2. تخزين مؤقت للجلسات (كما في النموذج البسيط)
# -------------------------------------------------------------------
active_users = {}  # phone -> {client, phone, api_id, api_hash, status, alert_group}

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# -------------------------------------------------------------------
# 3. الذكاء الاصطناعي (OpenRouter)
# -------------------------------------------------------------------
async def classify_message(text, api_key):
    if not api_key:
        return {"type": "seeker", "confidence": 100, "reason": "AI disabled"}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    prompt = f"""
    أنت مساعد متخصص في تصنيف الرسائل. حدد ما إذا كان المرسل طالباً يطلب مساعدة (seeker) أم معلناً يروج لخدمات (marketer).
    أعد JSON: {{"type": "seeker" أو "marketer", "confidence": 0-100, "reason": "السبب"}}
    الرسالة: {text}
    """
    payload = {
        "model": "qwen/qwen-2.5-72b-instruct",
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data['choices'][0]['message']['content']
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
    except:
        pass
    return {"type": "seeker", "confidence": 0, "reason": "AI error"}

# -------------------------------------------------------------------
# 4. محرك الرصد (بسيط، يعمل في الخلفية)
# -------------------------------------------------------------------
class RadarEngine:
    def __init__(self):
        self.clients = {}  # phone -> client
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start_loop, daemon=True)
        self.thread.start()

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _monitor_account(self, acc):
        phone = acc['phone']
        session_path = f"session_{phone}"
        client = TelegramClient(session_path, int(acc['api_id']), acc['api_hash'])
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return
            self.clients[phone] = client
            @client.on(events.NewMessage)
            async def handler(event):
                if event.is_private or event.out:
                    return
                keywords = db_get_keywords()
                if not any(kw in event.raw_text.lower() for kw in keywords):
                    return
                # تصنيف بالذكاء الاصطناعي
                ai_enabled = db_get_setting('ai_enabled') == '1'
                api_key = db_get_setting('openrouter_key')
                if ai_enabled and api_key:
                    result = await classify_message(event.raw_text, api_key)
                    if result.get('type') == 'marketer' and int(result.get('confidence', 0)) > 60:
                        return  # تجاهل المعلن
                # إرسال إلى المجموعة المحددة
                if acc.get('alert_group'):
                    try:
                        dest = acc['alert_group']
                        await client.forward_messages(dest, event.message)
                    except:
                        await client.send_message(dest, f"{event.raw_text}\n\n(تم إرسال نسخة)")
            await client.run_until_disconnected()
        except:
            pass
        finally:
            if phone in self.clients:
                del self.clients[phone]

    def start_all(self):
        accounts = db_get_accounts()
        for acc in accounts:
            asyncio.run_coroutine_threadsafe(self._monitor_account(acc), self.loop)

    def stop_all(self):
        for client in self.clients.values():
            asyncio.run_coroutine_threadsafe(client.disconnect(), self.loop)

radar = RadarEngine()
radar.start_all()  # بدء الرصد التلقائي

# -------------------------------------------------------------------
# 5. مسارات Flask (على نمط النموذج البسيط)
# -------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login_step1():
    api_id = request.form['api_id']
    api_hash = request.form['api_hash']
    phone = request.form['phone']
    alert_group = request.form.get('alert_group', '')

    client = TelegramClient('temp_session', int(api_id), api_hash)
    try:
        run_async(client.connect())
        run_async(client.send_code_request(phone))
        session_id = phone.replace('+', '').replace(' ', '')
        active_users[session_id] = {
            'client': client,
            'phone': phone,
            'api_id': api_id,
            'api_hash': api_hash,
            'alert_group': alert_group,
            'status': 'waiting_code'
        }
        session['session_id'] = session_id
        return redirect(url_for('code_page'))
    except errors.PhoneNumberInvalidError:
        flash('رقم الهاتف غير صالح', 'danger')
        return redirect(url_for('index'))
    except errors.ApiIdInvalidError:
        flash('بيانات API غير صحيحة', 'danger')
        return redirect(url_for('index'))
    except Exception as e:
        flash(str(e), 'danger')
        return redirect(url_for('index'))

@app.route('/code')
def code_page():
    return render_template('code.html')

@app.route('/verify-code', methods=['POST'])
def verify_code():
    code = request.form['code']
    session_id = session.get('session_id')
    if not session_id or session_id not in active_users:
        flash('انتهت الجلسة، أعد المحاولة', 'danger')
        return redirect(url_for('index'))
    user = active_users[session_id]
    client = user['client']
    try:
        run_async(client.sign_in(phone=user['phone'], code=code))
        user['status'] = 'logged_in'
        db_add_account(user['phone'], user['api_id'], user['api_hash'], user['alert_group'])
        asyncio.run_coroutine_threadsafe(radar._monitor_account({
            'phone': user['phone'],
            'api_id': user['api_id'],
            'api_hash': user['api_hash'],
            'alert_group': user['alert_group']
        }), radar.loop)
        return redirect(url_for('dashboard'))
    except errors.SessionPasswordNeededError:
        user['status'] = 'waiting_2fa'
        return redirect(url_for('twofa_page'))
    except errors.PhoneCodeInvalidError:
        flash('الرمز غير صحيح', 'danger')
        return redirect(url_for('code_page'))
    except Exception as e:
        flash(str(e), 'danger')
        return redirect(url_for('code_page'))

@app.route('/twofa')
def twofa_page():
    return render_template('twofa.html')

@app.route('/verify-2fa', methods=['POST'])
def verify_2fa():
    password = request.form['password']
    session_id = session.get('session_id')
    if not session_id or session_id not in active_users:
        flash('انتهت الجلسة', 'danger')
        return redirect(url_for('index'))
    user = active_users[session_id]
    client = user['client']
    try:
        run_async(client.sign_in(password=password))
        user['status'] = 'logged_in'
        db_add_account(user['phone'], user['api_id'], user['api_hash'], user['alert_group'])
        asyncio.run_coroutine_threadsafe(radar._monitor_account({
            'phone': user['phone'],
            'api_id': user['api_id'],
            'api_hash': user['api_hash'],
            'alert_group': user['alert_group']
        }), radar.loop)
        return redirect(url_for('dashboard'))
    except errors.PasswordHashInvalidError:
        flash('كلمة المرور خاطئة', 'danger')
        return redirect(url_for('twofa_page'))
    except Exception as e:
        flash(str(e), 'danger')
        return redirect(url_for('twofa_page'))

@app.route('/dashboard')
def dashboard():
    session_id = session.get('session_id')
    if not session_id or session_id not in active_users or active_users[session_id]['status'] != 'logged_in':
        return redirect(url_for('index'))
    accounts = db_get_accounts()
    keywords = db_get_keywords()
    ai_enabled = db_get_setting('ai_enabled')
    openrouter_key = db_get_setting('openrouter_key')
    return render_template('dashboard.html', accounts=accounts, keywords=keywords,
                           ai_enabled=ai_enabled, openrouter_key=openrouter_key)

@app.route('/add-keyword', methods=['POST'])
def add_keyword():
    keyword = request.form['keyword']
    if keyword:
        db_add_keyword(keyword)
    return redirect(url_for('dashboard'))

@app.route('/delete-keyword/<keyword>')
def delete_keyword(keyword):
    db_delete_keyword(keyword)
    return redirect(url_for('dashboard'))

@app.route('/save-ai-settings', methods=['POST'])
def save_ai_settings():
    ai_enabled = '1' if request.form.get('ai_enabled') else '0'
    api_key = request.form['openrouter_key']
    db_set_setting('ai_enabled', ai_enabled)
    db_set_setting('openrouter_key', api_key)
    return redirect(url_for('dashboard'))

@app.route('/delete-account/<phone>')
def delete_account(phone):
    db_delete_account(phone)
    if phone in radar.clients:
        asyncio.run_coroutine_threadsafe(radar.clients[phone].disconnect(), radar.loop)
        del radar.clients[phone]
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session_id = session.pop('session_id', None)
    if session_id in active_users:
        # محاولة قطع اتصال العميل المؤقت
        client = active_users[session_id].get('client')
        if client:
            try:
                run_async(client.disconnect())
            except:
                pass
        del active_users[session_id]
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
