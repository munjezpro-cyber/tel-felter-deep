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
# 1. حلقة الأحداث الموحدة (asyncio)
# -------------------------------------------------------------------
# إنشاء حلقة في خيط منفصل لتشغيل Telethon
loop = asyncio.new_event_loop()

def start_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

thread = threading.Thread(target=start_loop, daemon=True)
thread.start()

# دالة لتشغيل async من Flask (بدون إنشاء حلقة جديدة)
def run_async(coro):
    """تشغيل async في الحلقة الموحدة"""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=30)

# -------------------------------------------------------------------
# 2. قاعدة البيانات (SQLite)
# -------------------------------------------------------------------
DB_PATH = "radar.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # إدراج الكلمات المفتاحية الافتراضية (يمكنك وضع القائمة الكبيرة هنا)
    c.execute("SELECT COUNT(*) FROM keywords")
    if c.fetchone()[0] == 0:
        default_keywords = [
            'مساعدة', 'ساعدوني', 'ساعدني', 'أبي أحد', 'أبي حد', 'أبي مساعدة', 'محتاج', 'ضروري',
            'واجب', 'واجبات', 'تكليف', 'تكاليف', 'حل', 'يحل', 'اسايمنت', 'assignment', 'homework',
            'بحث', 'بحوث', 'تقرير', 'تقارير', 'ريبورت', 'report', 'research',
            'مشروع', 'مشاريع', 'بروجكت', 'project', 'مشروع تخرج',
            'برزنتيشن', 'presentation', 'بوربوينت', 'powerpoint', 'عرض', 'تصميم', 'بوستر', 'poster',
            'اختبار', 'اختبارات', 'كويز', 'كويزات', 'فاينل', 'ميد', 'امتحان',
            'شرح', 'يشرح', 'درس', 'دروس', 'ملخص', 'ملخصات',
            'رياضيات', 'فيزياء', 'كيمياء', 'أحياء', 'إنجليزي', 'برمجة', 'هندسة',
            'دكتور خصوصي', 'مدرس خصوصي', 'دروس خصوصية',
            'تعرفون أحد', 'تعرفون حد', 'من يعرف', 'من تعرف', 'أحد يعرف', 'حد يعرف', 'وين ألقى',
            'ترجمة', 'تلخيص', 'تدقيق', 'صياغة', 'كتابة', 'إعداد',
            'مراجعة', 'ليالي الامتحان', 'أسئلة', 'إجابات', 'نماذج', 'تجميعات',
            'رسالة ماجستير', 'رسالة دكتوراه', 'أطروحة', 'بحث علمي',
            'أحد يساعد', 'أحد يحل', 'أحد يشرح', 'أحد يسوي'
        ]
        for kw in default_keywords:
            c.execute("INSERT OR IGNORE INTO keywords (keyword) VALUES (?)", (kw,))
    
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('openrouter_key', ''))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", ('ai_enabled', '0'))
    conn.commit()
    conn.close()

init_db()

# دوال قاعدة البيانات
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
    except:
        pass
    return {"type": "seeker", "confidence": 0, "reason": "AI error"}

# -------------------------------------------------------------------
# 5. محرك الرصد (يعمل في الحلقة الموحدة)
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
                return
            self.clients[phone] = client
            @client.on(events.NewMessage)
            async def handler(event):
                if event.is_private or event.out:
                    return
                keywords = db_get_keywords()
                if not any(kw in event.raw_text.lower() for kw in keywords):
                    return
                # تصنيف ذكي
                ai_enabled = db_get_setting('ai_enabled') == '1'
                api_key = db_get_setting('openrouter_key')
                if ai_enabled and api_key:
                    result = await classify_message(event.raw_text, api_key)
                    if result.get('type') == 'marketer' and int(result.get('confidence', 0)) > 60:
                        return
                # إرسال
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
            asyncio.run_coroutine_threadsafe(self._monitor_account(acc), loop)

    def stop_all(self):
        for client in self.clients.values():
            asyncio.run_coroutine_threadsafe(client.disconnect(), loop)

radar = RadarEngine()
# بدء الرصد بعد ثانية لضمان اكتمال التهيئة
loop.call_later(1, lambda: asyncio.create_task(radar.start_all()))

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
        # إضافة إلى محرك الرصد
        asyncio.run_coroutine_threadsafe(radar._monitor_account({
            'phone': user['phone'],
            'api_id': user['api_id'],
            'api_hash': user['api_hash'],
            'alert_group': user['alert_group']
        }), loop)
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
        }), loop)
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
        asyncio.run_coroutine_threadsafe(radar.clients[phone].disconnect(), loop)
        del radar.clients[phone]
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
