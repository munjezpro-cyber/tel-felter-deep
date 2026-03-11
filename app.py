# -*- coding: utf-8 -*-
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
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-key-change-this")

# -------------------------------------------------------------------
# 1. حلقة الأحداث الموحدة (asyncio loop)
# -------------------------------------------------------------------
loop = asyncio.new_event_loop()

def start_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

thread = threading.Thread(target=start_loop, daemon=True)
thread.start()

def run_async(coro):
    """تشغيل async في الحلقة الموحدة"""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=30)

# -------------------------------------------------------------------
# 2. قاعدة البيانات SQLite
# -------------------------------------------------------------------
DB_PATH = "radar.db"

def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_db()
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
    # جدول السجلات
    c.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # إدراج الكلمات المفتاحية الافتراضية
    c.execute("SELECT COUNT(*) FROM keywords")
    if c.fetchone()[0] == 0:
        default_keywords = [
            'مساعدة', 'ساعدوني', 'ساعدني', 'أبي أحد', 'أبي حد', 'أبي مساعدة', 'محتاج', 'محتاجة', 'ضروري', 'مستعجل', 'أرجوكم', 'لو سمحتم',
            'الرجاء المساعدة', 'تحتاج مساعدة', 'نحتاج مساعدة', 'يحتاج مساعدة', 'تحتاج مساعدة',
            'واجب', 'واجبات', 'تكليف', 'تكاليف', 'حل', 'يحل', 'اسايمنت', 'assignment', 'homework', 'تكليفات', 'واجبي', 'واجباتي', 'أسايمنت',
            'بحث', 'بحوث', 'تقرير', 'تقارير', 'ريبورت', 'report', 'research', 'بحثي', 'تقريري', 'دراسة', 'دراسة حالة', 'case study', 'رسالة', 'رسائل',
            'مشروع', 'مشاريع', 'بروجكت', 'project', 'بروجيكت', 'مشروع تخرج', 'مشاريع تخرج', 'مشروعي', 'بروجكتي', 'خطة مشروع', 'مشروع نهائي',
            'برزنتيشن', 'presentation', 'بوربوينت', 'powerpoint', 'عرض', 'عروض', 'تصميم', 'تصاميم', 'بوستر', 'poster', 'برشور', 'brochure',
            'فيديو', 'فيديوهات', 'مونتاج', 'مقطع', 'تصوير', 'تحرير', 'انميشن', 'animation', 'موشن جرافيك',
            'اختبار', 'اختبارات', 'كويز', 'كويزات', 'فاينل', 'ميد', 'امتحان', 'امتحانات', 'اختبار نهائي', 'اختبار منتصف',
            'شرح', 'يشرح', 'درس', 'دروس', 'ملخص', 'ملخصات', 'مذكرة', 'مذكرات', 'أساسيات', 'تمارين', 'تدريبات', 'فهم', 'استيعاب', 'تبسيط',
            'رياضيات', 'فيزياء', 'كيمياء', 'أحياء', 'إنجليزي', 'عربي', 'تاريخ', 'جغرافيا', 'فلسفة', 'منطق', 'قانون', 'محاسبة', 'اقتصاد', 'إدارة', 'تسويق', 'برمجة', 'هندسة', 'طب', 'صيدلة', 'تمريض', 'حقوق',
            'دكتور خصوصي', 'مدرس خصوصي', 'معلم خصوصي', 'مدرسة خصوصية', 'دروس خصوصية', 'تدريس خصوصي', 'شرح خصوصي', 'يشرح خصوصي',
            'تعرفون أحد', 'تعرفون حد', 'من يعرف', 'من تعرف', 'أحد يعرف', 'حد يعرف', 'وين ألقى', 'كيف ألقى', 'كيف أحصل', 'مصدر', 'مرجع',
            'ترجمة', 'تلخيص', 'تدقيق', 'صياغة', 'كتابة', 'إعداد', 'تنفيذ', 'استشارة', 'توجيه', 'إرشاد', 'مراجعة', 'تصحيح',
            'مراجعة', 'ليالي الامتحان', 'أسئلة', 'إجابات', 'نماذج', 'تجميعات', 'شروحات',
            'رسالة ماجستير', 'رسالة دكتوراه', 'أطروحة', 'بحث علمي', 'نشر', 'ورقة بحثية', 'مؤتمر',
            'برمجة', 'كود', 'برنامج', 'تطبيق', 'موقع', 'نظام', 'قاعدة بيانات', 'خوارزمية',
            'رسم', 'أوتوكاد', 'سوليدوركس', 'ريفيت', 'ديزاين', 'تصميم معماري', 'إنشائي', 'ميكانيكي', 'كهربائي',
            'فوتوشوب', 'إليستريتور', 'ان ديزاين', 'جرافيك', 'تصميم جرافيكي', 'شعار', 'logo', 'هوية', 'براند',
            'أحد يساعد', 'أحد يحل', 'أحد يشرح', 'أحد يعمل', 'أحد يسوي', 'أحد يصمم', 'أحد يبرمج', 'أحد يترجم', 'أحد يلخص',
            'help', 'need help', 'urgent', 'assignment help', 'homework help', 'project help'
        ]
        for kw in default_keywords:
            try:
                c.execute("INSERT INTO keywords (keyword) VALUES (?)", (kw,))
            except:
                pass
    
    # إعدادات افتراضية
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('openrouter_key', ''))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('ai_enabled', '0'))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('admin_email', 'admin@radar.com'))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('admin_password', generate_password_hash('admin123')))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('radar_status', '1'))
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully")

init_db()

# دوال مساعدة لقاعدة البيانات
def db_get_keywords():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT keyword FROM keywords")
    keywords = [row[0] for row in c.fetchall()]
    conn.close()
    return keywords

def db_get_accounts():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT phone, api_id, api_hash, alert_group, enabled FROM accounts WHERE enabled = 1")
    accounts = [{'phone': r[0], 'api_id': r[1], 'api_hash': r[2], 'alert_group': r[3], 'enabled': r[4]} for r in c.fetchall()]
    conn.close()
    return accounts

def db_get_all_accounts():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT phone, api_id, api_hash, alert_group, enabled FROM accounts")
    accounts = [{'phone': r[0], 'api_id': r[1], 'api_hash': r[2], 'alert_group': r[3], 'enabled': r[4]} for r in c.fetchall()]
    conn.close()
    return accounts

def db_add_account(phone, api_id, api_hash, alert_group):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO accounts (phone, api_id, api_hash, alert_group) VALUES (?, ?, ?, ?)",
                  (phone, api_id, api_hash, alert_group))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def db_delete_account(phone):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM accounts WHERE phone = ?", (phone,))
    conn.commit()
    conn.close()

def db_update_account_enabled(phone, enabled):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE accounts SET enabled = ? WHERE phone = ?", (enabled, phone))
    conn.commit()
    conn.close()

def db_get_setting(key, default=''):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def db_set_setting(key, value):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def db_log_event(content):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO logs (content) VALUES (?)", (content,))
    conn.commit()
    conn.close()
    print(content)

# -------------------------------------------------------------------
# 3. تخزين مؤقت للجلسات
# -------------------------------------------------------------------
active_users = {}  # phone -> {client, phone, api_id, api_hash, status, alert_group}

# -------------------------------------------------------------------
# 4. الذكاء الاصطناعي (OpenRouter)
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
    except Exception as e:
        print(f"AI error: {e}")
    return {"type": "seeker", "confidence": 0, "reason": "AI error"}

# -------------------------------------------------------------------
# 5. محرك الرصد
# -------------------------------------------------------------------
class RadarEngine:
    def __init__(self):
        self.clients = {}  # phone -> client

    async def _monitor_account(self, acc):
        phone = acc['phone']
        session_path = f"session_{phone}"
        client = TelegramClient(session_path, int(acc['api_id']), acc['api_hash'], loop=loop)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                print(f"⚠️ حساب {phone} غير مصرح به")
                return
            self.clients[phone] = client
            print(f"✅ حساب {phone} متصل ويرصد")
            @client.on(events.NewMessage)
            async def handler(event):
                if event.is_private or event.out:
                    return
                keywords = db_get_keywords()
                if not any(kw in event.raw_text.lower() for kw in keywords):
                    return
                ai_enabled = db_get_setting('ai_enabled') == '1'
                api_key = db_get_setting('openrouter_key')
                if ai_enabled and api_key:
                    result = await classify_message(event.raw_text, api_key)
                    if result.get('type') == 'marketer' and int(result.get('confidence', 0)) > 60:
                        db_log_event(f"🚫 تجاهل رسالة معلن من {phone}")
                        return
                if acc.get('alert_group'):
                    try:
                        dest = acc['alert_group']
                        await client.forward_messages(dest, event.message)
                        db_log_event(f"📤 تم إرسال رسالة من {phone}")
                    except Exception as e:
                        try:
                            await client.send_message(dest, f"{event.raw_text}\n\n(تم إرسال نسخة)")
                            db_log_event(f"📤 تم إرسال نسخة من {phone}")
                        except:
                            db_log_event(f"❌ فشل إرسال من {phone}: {e}")
            await client.run_until_disconnected()
        except Exception as e:
            print(f"❌ خطأ في حساب {phone}: {e}")
        finally:
            if phone in self.clients:
                del self.clients[phone]

    def start_all(self):
        accounts = db_get_accounts()
        for acc in accounts:
            asyncio.run_coroutine_threadsafe(self._monitor_account(acc), loop)

    def stop_all(self):
        for phone, client in list(self.clients.items()):
            asyncio.run_coroutine_threadsafe(client.disconnect(), loop)
        self.clients.clear()

radar = RadarEngine()

# متغير حالة الرادار
radar_status = db_get_setting('radar_status') == '1'
if radar_status:
    loop.call_later(2, lambda: asyncio.create_task(radar.start_all()))

# -------------------------------------------------------------------
# 6. مسارات Flask
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

    client = TelegramClient('temp_session', int(api_id), api_hash, loop=loop)
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
        if db_get_setting('radar_status') == '1':
            asyncio.run_coroutine_threadsafe(radar._monitor_account({
                'phone': user['phone'],
                'api_id': user['api_id'],
                'api_hash': user['api_hash'],
                'alert_group': user['alert_group']
            }), loop)
        db_log_event(f"✅ تم إضافة حساب {user['phone']}")
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
        if db_get_setting('radar_status') == '1':
            asyncio.run_coroutine_threadsafe(radar._monitor_account({
                'phone': user['phone'],
                'api_id': user['api_id'],
                'api_hash': user['api_hash'],
                'alert_group': user['alert_group']
            }), loop)
        db_log_event(f"✅ تم إضافة حساب {user['phone']} (مع 2FA)")
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
    accounts = db_get_all_accounts()
    keywords = db_get_keywords()
    keywords_text = '\n'.join(keywords)
    ai_enabled = db_get_setting('ai_enabled') == '1'
    openrouter_key = db_get_setting('openrouter_key')
    radar_status = db_get_setting('radar_status') == '1'
    # قراءة آخر 50 حدث
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT content FROM logs ORDER BY created_at DESC LIMIT 50")
    logs = [row[0] for row in c.fetchall()]
    conn.close()
    return render_template('dashboard.html', 
                           accounts=accounts,
                           keywords_text=keywords_text,
                           ai_enabled=ai_enabled,
                           openrouter_key=openrouter_key,
                           radar_status=radar_status,
                           logs=logs)

@app.route('/toggle-radar', methods=['POST'])
def toggle_radar():
    session_id = session.get('session_id')
    if not session_id or session_id not in active_users or active_users[session_id]['status'] != 'logged_in':
        return redirect(url_for('index'))
    new_status = not (db_get_setting('radar_status') == '1')
    db_set_setting('radar_status', '1' if new_status else '0')
    if new_status:
        radar.start_all()
        db_log_event("▶️ تم تشغيل الرادار")
        flash('تم تشغيل الرادار', 'success')
    else:
        radar.stop_all()
        db_log_event("⏹️ تم إيقاف الرادار")
        flash('تم إيقاف الرادار', 'success')
    return redirect(url_for('dashboard'))

@app.route('/toggle-account/<phone>', methods=['POST'])
def toggle_account(phone):
    session_id = session.get('session_id')
    if not session_id or session_id not in active_users or active_users[session_id]['status'] != 'logged_in':
        return redirect(url_for('index'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT enabled FROM accounts WHERE phone = ?", (phone,))
    enabled = c.fetchone()[0]
    c.execute("UPDATE accounts SET enabled = ? WHERE phone = ?", (not enabled, phone))
    conn.commit()
    conn.close()
    if enabled:
        if phone in radar.clients:
            asyncio.run_coroutine_threadsafe(radar.clients[phone].disconnect(), loop)
            del radar.clients[phone]
        db_log_event(f"⏸️ تم إيقاف حساب {phone}")
    else:
        c = conn.cursor()
        c.execute("SELECT api_id, api_hash, alert_group FROM accounts WHERE phone = ?", (phone,))
        row = c.fetchone()
        if row:
            asyncio.run_coroutine_threadsafe(radar._monitor_account({
                'phone': phone,
                'api_id': row[0],
                'api_hash': row[1],
                'alert_group': row[2]
            }), loop)
            db_log_event(f"▶️ تم تشغيل حساب {phone}")
    flash('تم تغيير حالة الحساب', 'success')
    return redirect(url_for('dashboard'))

@app.route('/add-account', methods=['POST'])
def add_account_from_dashboard():
    return login_step1()

@app.route('/save-keywords', methods=['POST'])
def save_keywords():
    session_id = session.get('session_id')
    if not session_id or session_id not in active_users or active_users[session_id]['status'] != 'logged_in':
        return redirect(url_for('index'))
    keywords_text = request.form['keywords']
    keywords_list = [k.strip() for k in keywords_text.split('\n') if k.strip()]
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM keywords")
    for kw in keywords_list:
        c.execute("INSERT INTO keywords (keyword) VALUES (?)", (kw,))
    conn.commit()
    conn.close()
    db_log_event("📝 تم تحديث الكلمات المفتاحية")
    flash('تم حفظ الكلمات المفتاحية', 'success')
    return redirect(url_for('dashboard'))

@app.route('/save-ai-settings', methods=['POST'])
def save_ai_settings():
    session_id = session.get('session_id')
    if not session_id or session_id not in active_users or active_users[session_id]['status'] != 'logged_in':
        return redirect(url_for('index'))
    ai_enabled = '1' if request.form.get('ai_enabled') else '0'
    api_key = request.form['openrouter_key']
    db_set_setting('ai_enabled', ai_enabled)
    db_set_setting('openrouter_key', api_key)
    db_log_event("⚙️ تم تحديث إعدادات الذكاء الاصطناعي")
    flash('تم حفظ الإعدادات', 'success')
    return redirect(url_for('dashboard'))

@app.route('/delete-account/<phone>')
def delete_account(phone):
    session_id = session.get('session_id')
    if not session_id or session_id not in active_users or active_users[session_id]['status'] != 'logged_in':
        return redirect(url_for('index'))
    db_delete_account(phone)
    if phone in radar.clients:
        asyncio.run_coroutine_threadsafe(radar.clients[phone].disconnect(), loop)
        del radar.clients[phone]
    db_log_event(f"🗑️ تم حذف حساب {phone}")
    flash('تم حذف الحساب', 'success')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session_id = session.pop('session_id', None)
    if session_id in active_users:
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
