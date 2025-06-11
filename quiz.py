# -*- coding: utf-8 -*-
"""
Quiz Telegram Bot
Bot Name: QuizBot
Developer: yazbekw
"""

import os
import time
import json
import random
from datetime import datetime

# Import libraries
import sqlite3
import telebot
from threading import Thread
from telebot import types
from difflib import SequenceMatcher
from apscheduler.schedulers.background import BackgroundScheduler
import pyarabic.araby as araby
from dotenv import load_dotenv
from flask import Flask, request
from flask import render_template_string


# Load environment variables FIRST
load_dotenv()

# Get bot token and admin ID from .env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", 0))



# Validate token
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("⚠️ TELEGRAM_BOT_TOKEN غير موجود في ملف .env")

# Initialize bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

bot.current_questions = {}


# Print debug info
print("✅ البوت جاهز للتشغيل")
print("📁 مسار التشغيل:", os.getcwd())
print("📄 الملفات في المسار:", os.listdir())
print("🔐 التوكن محمل:", TELEGRAM_BOT_TOKEN[:10] + "..." if TELEGRAM_BOT_TOKEN else None)


# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()


    
with open('questions_full.json', 'r', encoding='utf-8') as f:
    questions = json.load(f)
    print(f"Debug: Loaded {len(questions)} questions")  # طباعة عدد الأسئلة المحملة

# إضافة جداول جديدة في init_db()
def init_db():
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    # إنشاء الجداول الأساسية
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        register_date TEXT NOT NULL,
        last_active TEXT NOT NULL,
        score INTEGER DEFAULT 0,
        attempts INTEGER DEFAULT 0,
        selected_topic TEXT
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS questions (
        id TEXT PRIMARY KEY,
        question TEXT NOT NULL,
        topic TEXT,
        page TEXT,
        type TEXT NOT NULL,
        choices TEXT,  
        correct_indices TEXT,  
        answer TEXT,
        answer_keywords TEXT,  
        explanation TEXT,
        hint TEXT,
        reference TEXT,
        difficulty INTEGER DEFAULT 1
    )''')
    
    # إضافة جدول الدعوات
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_invites (
        chat_id INTEGER,
        invite_code TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        uses INTEGER DEFAULT 0,
        FOREIGN KEY (chat_id) REFERENCES users (chat_id)
    )''')
    
    # إضافة جدول الملاحظات
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        feedback_text TEXT NOT NULL,
        rating INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES users (chat_id)
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_answered (
        chat_id INTEGER,
        question_id TEXT,
        PRIMARY KEY (chat_id, question_id),
        FOREIGN KEY (chat_id) REFERENCES users (chat_id)
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_topics (
        chat_id INTEGER,
        topic TEXT,
        correct INTEGER DEFAULT 0,
        attempts INTEGER DEFAULT 0,
        PRIMARY KEY (chat_id, topic)
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS hard_questions (
        chat_id INTEGER,
        question_id TEXT,
        PRIMARY KEY (chat_id, question_id)
    )''')
    # جدول جلسات المستخدم
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_sessions (
        session_id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        start_time TEXT,
        end_time TEXT,
        questions_answered INTEGER,
        FOREIGN KEY (chat_id) REFERENCES users (chat_id)
    )''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_mistakes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER,
        question_id TEXT,
        wrong_answer TEXT,
        count INTEGER DEFAULT 1,
        accuracy REAL,
        last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES users (chat_id),
        UNIQUE(chat_id, question_id, wrong_answer)
    )''')
    
    # جدول تحليل الأخطاء
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS error_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id TEXT,
        wrong_answer TEXT,
        count INTEGER DEFAULT 1,
        common_mistakes TEXT,
        FOREIGN KEY (question_id) REFERENCES questions (id)
    )''')
    
    # إضافة فهارس لتحسين الأداء
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_chat_id ON users (chat_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_topics_chat_id ON user_topics (chat_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_chat_id ON user_sessions (chat_id)')
    
    conn.commit()
    conn.close()
    
init_db()

print("Bot initialized:", bot.get_me())


# Arabic text processing
def preprocess_arabic(text):
    text = araby.strip_tashkeel(text)
    text = araby.normalize_hamza(text)
    text = araby.strip_tatweel(text)
    text = araby.normalize_ligature(text)  # إضافة هذه السطر
    text = text.replace("،", "").replace(".", "").strip()  # إزالة علامات الترقيم
    return text

# Error handling decorator
def handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            message = args[0]
            if hasattr(message, 'chat'):
                bot.send_message(message.chat.id, "⚠️ حدث خطأ غير متوقع. يرجى المحاولة لاحقاً.")
            
            # تسجيل مفصل للخطأ
            error_msg = f"Error in {func.__name__}: {str(e)}"
            print(error_msg)
            
            # إرسال الخطأ للمطور
            if ADMIN_CHAT_ID:
                bot.send_message(ADMIN_CHAT_ID, error_msg)
    return wrapper

def get_explanation(q):
    """Generate explanation text from question dictionary"""
    explanation = "📚 الشرح:\n"
    
    if 'explanation' in q and q['explanation']:
        explanation += q['explanation']
    elif 'answer_example' in q:
        explanation += q['answer_example']
    else:
        explanation += "لا يوجد شرح متوفر حالياً"
    
    if 'answer_keywords' in q:
        explanation += "\n\n🔑 الكلمات المفتاحية المطلوبة:\n- " + "\n- ".join(q['answer_keywords'])
    
    if 'reference' in q:
        explanation += f"\n\n📖 المرجع: {q['reference']}"
    
    return explanation
    
@bot.message_handler(commands=['explain'])
@handle_errors
def explain_command_handler(message):
    chat_id = message.chat.id
    q_id = bot.current_questions.get(chat_id)
    
    if not q_id:
        bot.send_message(chat_id, "⚠️ لا يوجد سؤال نشط حالياً")
        return
        
    q = next((q for q in questions if q['id'] == q_id), None)
    
    if not q:
        bot.send_message(chat_id, "⚠️ عذراً، حدث خطأ في تحميل السؤال")
        return
    
    bot.send_message(chat_id, get_explanation(q))
    

# User management functions
def get_user(chat_id):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE chat_id = ?', (chat_id,))
    user = cursor.fetchone()
    conn.close()
    return user
    
@bot.callback_query_handler(func=lambda call: call.data == 'random_question')
@handle_errors
def handle_random_question(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    send_question(call.message)

def init_user(chat_id):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    cursor.execute('''
    INSERT OR IGNORE INTO users (chat_id, register_date, last_active)
    VALUES (?, ?, ?)
    ''', (chat_id, now, now))
    
    conn.commit()
    conn.close()

def update_user_last_active(chat_id):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE users SET last_active = ? WHERE chat_id = ?
    ''', (datetime.now().isoformat(), chat_id))
    conn.commit()
    conn.close()

def get_question_for_user(chat_id):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    # 1. التحقق من وجود أسئلة صعبة (30% فرصة)
    if random.random() < 0.3:
        cursor.execute('''
        SELECT question_id FROM hard_questions 
        WHERE chat_id = ? ORDER BY RANDOM() LIMIT 1
        ''', (chat_id,))
        hard_q = cursor.fetchone()
        if hard_q:
            q = next((q for q in questions if q['id'] == hard_q[0]), None)
            if q:
                conn.close()
                return q
    
    # 2. الحصول على الموضوع المحدد من قبل المستخدم
    cursor.execute('SELECT selected_topic FROM users WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    selected_topic = result[0] if result else None
    
    # 3. الحصول على الأسئلة التي لم يتم عرضها بعد في هذا الموضوع
    if selected_topic:
        cursor.execute('''
        SELECT question_id FROM user_answered
        WHERE chat_id = ?
        ''', (chat_id,))
        answered_questions = [row[0] for row in cursor.fetchall()]
        
        # تصفية الأسئلة بناء على الموضوع والأسئلة المجابة
        available_questions = [
            q for q in questions 
            if q.get('topic', 'عام') == selected_topic 
            and q['id'] not in answered_questions
        ]
    else:
        cursor.execute('''
        SELECT question_id FROM user_answered
        WHERE chat_id = ?
        ''', (chat_id,))
        answered_questions = [row[0] for row in cursor.fetchall()]
        
        available_questions = [
            q for q in questions 
            if q['id'] not in answered_questions
        ]
    
    if available_questions:
        conn.close()
        return random.choice(available_questions)
    
    # 4. إذا أجاب على جميع الأسئلة، نعيد تعيين السجل ونختار سؤال عشوائي
    cursor.execute('DELETE FROM user_answered WHERE chat_id = ?', (chat_id,))
    conn.commit()
    
    # 5. اختيار سؤال عشوائي من الموضوع المحدد أو جميع الأسئلة
    available_questions = [q for q in questions if q.get('topic', 'عام') == selected_topic] if selected_topic else questions
    if not available_questions:
        print(f"تحذير: لا توجد أسئلة للموضوع {selected_topic} - استخدام أسئلة عامة")
        available_questions = [q for q in questions if q.get('topic', 'عام') == 'عام']
    
    conn.close()
    return random.choice(available_questions) if available_questions else None

def record_question_rating(chat_id, question_id, rating):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO question_ratings (chat_id, question_id, rating)
    VALUES (?, ?, ?)
    ''', (chat_id, question_id, rating))
    
    if rating == 'hard':
        cursor.execute('''
        INSERT OR IGNORE INTO hard_questions (chat_id, question_id)
        VALUES (?, ?)
        ''', (chat_id, question_id))
    
    conn.commit()
    conn.close()
    
@bot.message_handler(commands=['invite'])
@handle_errors
def invite_command(message):
    invite_link = generate_invite_link(message.chat.id)
    response = f"""📩 دعوة الأصدقاء:
    
شارك هذا الرابط مع أصدقائك لتحصل على 5 نقاط لكل صديق ينضم عبر رابطك!

🎁 المكافآت:
- 5 نقاط لكل صديق ينضم
- 10 نقاط عند وصول 5 أصدقاء
- 20 نقطة عند وصول 10 أصدقاء

رابط الدعوة الخاص بك:
{invite_link}"""
    
    bot.reply_to(message, response)

@bot.message_handler(commands=['feedback'])
@handle_errors
def feedback_command(message):
    markup = types.ForceReply(selective=True)
    msg = bot.send_message(
        message.chat.id,
        "📝 نرحب بملاحظاتك وآرائك!\n\n"
        "يرجى كتابة ملاحظتك وسنقوم بقراءتها وتحسين البوت بناءً عليها:",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_feedback)

def process_feedback(message):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO user_feedback (chat_id, feedback_text)
    VALUES (?, ?)
    ''', (message.chat.id, message.text))
    
    conn.commit()
    conn.close()
    
    bot.reply_to(message, "شكراً لك على ملاحظتك القيمة! سنعمل على تحسين البوت بناءً على آرائكم.")
    
    # إرسال الملاحظة للمسؤول
    if ADMIN_CHAT_ID:
        bot.send_message(
            ADMIN_CHAT_ID,
            f"📩 ملاحظة جديدة من المستخدم {message.chat.id}:\n\n{message.text}"
        )

@bot.callback_query_handler(func=lambda call: call.data == 'invite_friends')
def handle_invite_button(call):
    invite_command(call.message)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'feedback')
def handle_feedback_button(call):
    feedback_command(call.message)
    bot.answer_callback_query(call.id)

def update_user_score(chat_id, is_correct, topic):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    # Update overall score
    if is_correct:
        cursor.execute('''
        UPDATE users SET score = score + 1, attempts = attempts + 1 
        WHERE chat_id = ?
        ''', (chat_id,))
    else:
        cursor.execute('''
        UPDATE users SET attempts = attempts + 1 
        WHERE chat_id = ?
        ''', (chat_id,))
    
    # Update topic stats
    cursor.execute('''
    INSERT OR IGNORE INTO user_topics (chat_id, topic, correct, attempts)
    VALUES (?, ?, 0, 0)
    ''', (chat_id, topic))
    
    if is_correct:
        cursor.execute('''
        UPDATE user_topics SET correct = correct + 1, attempts = attempts + 1
        WHERE chat_id = ? AND topic = ?
        ''', (chat_id, topic))
    else:
        cursor.execute('''
        UPDATE user_topics SET attempts = attempts + 1
        WHERE chat_id = ? AND topic = ?
        ''', (chat_id, topic))
    
    conn.commit()
    conn.close()
    

        
@bot.callback_query_handler(func=lambda call: call.data == 'hint')
@handle_errors
def get_hint(call):
    chat_id = call.message.chat.id
    q_id = bot.current_questions.get(chat_id)
    
    if not q_id:
        bot.answer_callback_query(call.id, "انتهت صلاحية السؤال.")
        return
    
    q = next((q for q in questions if q['id'] == q_id), None)
    if not q:
        bot.answer_callback_query(call.id, "حدث خطأ في تحميل السؤال.")
        return
    
    hint_text = ""
    
    if 'hint' in q:
        hint_text = q['hint']
    elif 'answer_keywords' in q:
        hint_text = f"💡 ركز على هذه المفاهيم: {', '.join(q['answer_keywords'][:3])}..."
    else:
        hint_text = "💡 حاول التفكير في المفاهيم الأساسية المتعلقة بالسؤال"
    
    bot.answer_callback_query(call.id)
    bot.send_message(chat_id, hint_text)
    
# إضافة هذه الدوال لبدء وإنهاء الجلسة
def start_user_session(chat_id):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO user_sessions (chat_id, start_time, questions_answered)
    VALUES (?, ?, 0)''', (chat_id, datetime.now().isoformat()))
    conn.commit()
    return cursor.lastrowid

def end_user_session(session_id):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE user_sessions 
    SET end_time = ?
    WHERE session_id = ?''', (datetime.now().isoformat(), session_id))
    conn.commit()

def record_question_answered(session_id):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE user_sessions 
    SET questions_answered = questions_answered + 1
    WHERE session_id = ?''', (session_id,))
    conn.commit()
    
@bot.message_handler(commands=['stats'])
@handle_errors
def show_stats(message):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    # إحصائيات عامة
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(questions_answered) FROM user_sessions')
    total_questions = cursor.fetchone()[0] or 0
    
    # إحصائيات الوقت
    cursor.execute('''
    SELECT strftime('%H', start_time) as hour, COUNT(*) 
    FROM user_sessions 
    GROUP BY hour
    ORDER BY COUNT(*) DESC LIMIT 3''')
    peak_hours = cursor.fetchall()
    
    # تحليل الأخطاء الشائعة
    cursor.execute('''
    SELECT q.question, e.wrong_answer, e.count 
    FROM error_analysis e
    JOIN questions q ON e.question_id = q.id
    ORDER BY e.count DESC LIMIT 5''')
    common_errors = cursor.fetchall()
    
    conn.close()
    
    # بناء التقرير
    response = f"📊 إحصائيات البوت:\n\n"
    response += f"👥 عدد المستخدمين: {total_users}\n"
    response += f"❓ إجمالي الأسئلة المجابة: {total_questions}\n\n"
    response += "⏰ أوقات الذروة:\n"
    for hour, count in peak_hours:
        response += f"- الساعة {hour}:00 ({count} جلسة)\n"
    
    response += "\n🚨 الأخطاء الشائعة:\n"
    for question, wrong_answer, count in common_errors:
        response += f"- السؤال: {question[:30]}...\n"
        response += f"  الخطأ: {wrong_answer[:20]}... (تكرار {count} مرة)\n\n"
    
    bot.reply_to(message, response)
    
@bot.message_handler(commands=['admin_stats'], func=lambda m: m.chat.id == ADMIN_CHAT_ID)
def admin_stats(message):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    # إحصائيات النمو
    cursor.execute('''
    SELECT date(register_date), COUNT(*) 
    FROM users 
    GROUP BY date(register_date) 
    ORDER BY date(register_date) DESC LIMIT 7''')
    growth = cursor.fetchall()
    
    # نشاط المستخدمين
    cursor.execute('''
    SELECT date(last_active), COUNT(*) 
    FROM users 
    GROUP BY date(last_active) 
    ORDER BY date(last_active) DESC LIMIT 7''')
    activity = cursor.fetchall()
    
    # تقرير مفصل
    report = "📈 تقرير المسؤول:\n\n"
    report += "📅 نمو المستخدمين (آخر 7 أيام):\n"
    for date, count in growth:
        report += f"- {date}: {count} مستخدم\n"
    
    report += "\n🔥 نشاط المستخدمين:\n"
    for date, count in activity:
        report += f"- {date}: {count} مستخدم نشط\n"
    
    conn.close()
    bot.reply_to(message, report)

def show_question_followup(chat_id, question_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("سهل 👍", callback_data=f"rate_easy_{question_id}"),
        types.InlineKeyboardButton("صعب 👎", callback_data=f"rate_hard_{question_id}")
    )
    markup.row(
        types.InlineKeyboardButton("سؤال آخر ➡️", callback_data="next_question")
    )
    bot.send_message(chat_id, "كيف تقيم هذا السؤال؟", reply_markup=markup)
    
# إضافة هذه الدوال لإدارة نظام الإحالة
def generate_invite_link(chat_id):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    # إنشاء رمز دعوة فريد
    invite_code = f"INV_{chat_id}_{int(time.time())}"
    
    # حفظه في قاعدة البيانات
    cursor.execute('''
    INSERT OR REPLACE INTO user_invites 
    (chat_id, invite_code, created_at, uses) 
    VALUES (?, ?, datetime('now'), 0)
    ''', (chat_id, invite_code))
    
    conn.commit()
    conn.close()
    
    return f"https://t.me/{bot.get_me().username}?start={invite_code}"

def record_invite_use(invite_code, new_user_id):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    # تحديث عدد الاستخدامات
    cursor.execute('''
    UPDATE user_invites SET uses = uses + 1 
    WHERE invite_code = ?
    ''', (invite_code,))
    
    # منح نقاط للمستخدم الذي قام بالدعوة
    cursor.execute('''
    UPDATE users SET score = score + 5 
    WHERE chat_id = (SELECT chat_id FROM user_invites WHERE invite_code = ?)
    ''', (invite_code,))
    
    conn.commit()
    conn.close()
    
@bot.message_handler(commands=['view_feedback'], func=lambda m: m.chat.id == ADMIN_CHAT_ID)
def view_feedback(message):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT chat_id, feedback_text, created_at 
    FROM user_feedback 
    ORDER BY created_at DESC LIMIT 10
    ''')
    feedbacks = cursor.fetchall()
    conn.close()
    
    if not feedbacks:
        bot.reply_to(message, "لا توجد ملاحظات حتى الآن.")
        return
    
    response = "📝 آخر 10 ملاحظات من المستخدمين:\n\n"
    for idx, (chat_id, text, date) in enumerate(feedbacks, 1):
        response += f"{idx}. من {chat_id} في {date}:\n{text[:100]}...\n\n"
    
    bot.reply_to(message, response)

@bot.callback_query_handler(func=lambda call: call.data == 'my_stats')
@handle_errors
def handle_my_stats(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    show_score(call.message)
    
@bot.callback_query_handler(func=lambda call: call.data == 'explain')
@handle_errors
def handle_explain_callback(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    explain_command_handler(call.message)  # Reuse your existing explain function

@bot.callback_query_handler(func=lambda call: call.data == 'new_question')
@handle_errors
def handle_new_question(call):
    bot.answer_callback_query(call.id)
    send_question(call.message)

@bot.callback_query_handler(func=lambda call: call.data == 'topics_list')
@handle_errors
def handle_topics_list(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    list_topics(call.message)  # نستخدم نفس دالة عرض المواضيع المستخدمة في الأمر /topics
    
@bot.callback_query_handler(func=lambda call: call.data == 'select_topic')
@handle_errors
def handle_select_topic(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    
    # عرض قائمة المواضيع مع أزرار للاختيار
    all_topics = sorted(list(set(q.get('topic', 'عام') for q in questions)))
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [types.InlineKeyboardButton(topic, callback_data=f"select_{topic}") 
               for topic in all_topics[:10]]  # عرض أول 10 مواضيع كأزرار
    markup.add(*buttons)
    
    bot.send_message(
        chat_id,
        "📚 اختر موضوعاً من القائمة أدناه:",
        reply_markup=markup
    )

@bot.message_handler(commands=['feedback_stats'], func=lambda m: m.chat.id == ADMIN_CHAT_ID)
def feedback_stats(message):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM user_feedback')
    total = cursor.fetchone()[0]
    
    cursor.execute('''
    SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) 
    FROM user_feedback 
    GROUP BY month 
    ORDER BY month DESC LIMIT 6
    ''')
    monthly = cursor.fetchall()
    
    conn.close()
    
    response = f"📊 إحصائيات الملاحظات:\n\nإجمالي الملاحظات: {total}\n\n"
    response += "📅 التوزيع الشهري (آخر 6 أشهر):\n"
    for month, count in monthly:
        response += f"- {month}: {count} ملاحظة\n"
    
    bot.reply_to(message, response)

# Command handlers
@bot.message_handler(commands=['start', 'help'])
@handle_errors
def send_welcome(message):
    # معالجة روابط الدعوة
    if len(message.text.split()) > 1:
        invite_code = message.text.split()[1]
        if invite_code.startswith('INV_'):
            record_invite_use(invite_code, message.chat.id)
            
    init_user(message.chat.id)
    update_user_last_active(message.chat.id)

    # رسالة الترحيب
    response = """👋 مرحبًا بك في بوت أسئلة العلوم للصف التاسع!

🎯 هدفي هو مساعدتك في فهم الدروس وتعزيز مهاراتك من خلال أسئلة تفاعلية."""

    # إنشاء لوحة أزرار تفاعلية
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton('🧪 سؤال جديد', callback_data='new_question'),
        types.InlineKeyboardButton('📊 إحصائياتي', callback_data='my_stats'),
        types.InlineKeyboardButton('📚 المواضيع', callback_data='topics_list'),
        types.InlineKeyboardButton('📌 اختيار موضوع', callback_data='select_topic'),
        types.InlineKeyboardButton('📩 دعوة الأصدقاء', callback_data='invite_friends'),
        types.InlineKeyboardButton('💬 آراء واقتراحات', callback_data='feedback')
    )

    try:
        with open('logo.jpg', 'rb') as photo:
            bot.send_photo(
                chat_id=message.chat.id,
                photo=photo,
                caption=response,
                reply_markup=markup
            )
    except Exception as e:
        print(f"فشل في إرسال الصورة: {e}")
        bot.send_message(message.chat.id, response, reply_markup=markup)
    
@bot.message_handler(commands=['question'])
@handle_errors
def send_question(message):
    init_user(message.chat.id)
    update_user_last_active(message.chat.id)
    
    q = get_question_for_user(message.chat.id)
    if not q:
        bot.reply_to(message, "لا توجد أسئلة متاحة حالياً.")
        return
    
    # بناء نص السؤال
    question_text = f"📚 *السؤال* (موضوع: {q.get('topic', 'عام')} - ص {q.get('page', '?')})\n"
    question_text += q['question']
    
    # حفظ السؤال الحالي
    bot.current_questions[message.chat.id] = q['id']
    
    # إرسال السؤال مع الخيارات إن وجدت
    if q['type'] == 'mcq':
        markup = types.InlineKeyboardMarkup()
        for i, choice in enumerate(q['choices']):
            btn = types.InlineKeyboardButton(text=choice, callback_data=f"mcq_{i}")
            markup.add(btn)
        bot.send_message(message.chat.id, question_text, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, question_text, parse_mode="Markdown")
    
    # إضافة أزرار المساعدة
    action_markup = types.InlineKeyboardMarkup(row_width=2)
    
    if 'hint' in q or 'answer_keywords' in q:
        action_markup.add(types.InlineKeyboardButton("تلميح 💡", callback_data="hint"))
    
    if 'explanation' in q or 'answer_example' in q or 'answer' in q:
        action_markup.add(types.InlineKeyboardButton("شرح 📖", callback_data="explain"))
    
    if action_markup.to_dict().get('inline_keyboard'):
        bot.send_message(
            message.chat.id,
            "يمكنك استخدام الخيارات التالية للمساعدة:",
            reply_markup=action_markup
        )

@bot.message_handler(commands=['score'])
@handle_errors
def show_score(message):
    init_user(message.chat.id)
    update_user_last_active(message.chat.id)
    
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    # Get overall stats
    cursor.execute('SELECT score, attempts FROM users WHERE chat_id = ?', (message.chat.id,))
    result = cursor.fetchone()
    
    if not result:
        bot.reply_to(message, "لا توجد بيانات متاحة.")
        return
    
    score, attempts = result
    percentage = (score / attempts * 100) if attempts > 0 else 0
    
    # Get topic-wise stats
    cursor.execute('''
    SELECT topic, correct, attempts 
    FROM user_topics 
    WHERE chat_id = ? 
    ORDER BY attempts DESC
    LIMIT 5
    ''', (message.chat.id,))
    topics = cursor.fetchall()
    
    conn.close()
    
    response = f"🎯 نتيجتك: {score} / {attempts}\nالنسبة المئوية: {percentage:.1f}%\n\n"
    response += "📊 إحصائيات المواضيع:\n"
    
    for topic, correct, topic_attempts in topics:
        topic_percentage = (correct / topic_attempts * 100) if topic_attempts > 0 else 0
        response += f"- {topic}: {correct}/{topic_attempts} ({topic_percentage:.1f}%)\n"
    
    bot.reply_to(message, response)

@bot.message_handler(commands=['topics'])
@handle_errors
def list_topics(message):
    # تحميل معلومات المواضيع
    with open('topics_info.json', 'r', encoding='utf-8') as f:
        topics_info = json.load(f)
    
    # الحصول على جميع المواضيع الفريدة من الأسئلة
    all_topics = sorted(list(set(q.get('topic', 'عام') for q in questions)))
    
    # التأكد من أن "التكاثر" موجود في القائمة
    if 'التكاثر' not in all_topics:
        print("تحذير: موضوع 'التكاثر' غير موجود في الأسئلة!")
    
    response = "📚 المواضيع المتاحة:\n\n"
    for topic in all_topics:
        info = topics_info.get(topic, {})
        desc = info.get('description', 'لا يوجد وصف متاح')
        pages = info.get('pages', 'غير محدد')
        response += f"🔹 *{topic}*\n"
        response += f"📖 الصفحات: {pages}\n"
        response += f"ℹ️ الوصف: {desc}\n\n"
    
    # إرسال القائمة
    bot.send_message(message.chat.id, response, parse_mode="Markdown")
    
@bot.message_handler(commands=['select_topic'])
@handle_errors
def select_topic_command(message):
    # Load topics info
    with open('topics_info.json', 'r', encoding='utf-8') as f:
        topics_info = json.load(f)
    
    # Get all unique topics from questions
    all_topics = sorted(list(set(q.get('topic', 'عام') for q in questions)))
    
    # Create a keyboard with topics
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    buttons = [types.KeyboardButton(topic) for topic in all_topics]
    markup.add(*buttons)
    
    bot.send_message(message.chat.id, 
                    "اختر موضوعاً من القائمة أدناه أو اكتب اسم الموضوع:",
                    reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in [q.get('topic', 'عام') for q in questions])
@handle_errors
def handle_topic_selection(message):
    chat_id = message.chat.id
    selected_topic = message.text
    
    # Load topics info for description
    with open('topics_info.json', 'r', encoding='utf-8') as f:
        topics_info = json.load(f)
    
    # Update user's selected topic in database
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET selected_topic = ? WHERE chat_id = ?', 
                  (selected_topic, chat_id))
    conn.commit()
    conn.close()
    
    # Get topic info
    topic_info = topics_info.get(selected_topic, {})
    desc = topic_info.get('description', 'لا يوجد وصف متاح')
    pages = topic_info.get('pages', 'غير محدد')
    
    response = f"✅ تم اختيار موضوع: *{selected_topic}*\n\n"
    response += f"📖 الصفحات: {pages}\n"
    response += f"ℹ️ الوصف: {desc}\n\n"
    response += "استخدم /question للحصول على سؤال من هذا الموضوع."
    
    bot.send_message(chat_id, response, parse_mode="Markdown")
    
@bot.callback_query_handler(func=lambda call: call.data.startswith('select_'))
@handle_errors
def handle_topic_button(call):
    chat_id = call.message.chat.id
    selected_topic = call.data[7:]  # Remove 'select_' prefix
    
    # Update user's selected topic in database
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET selected_topic = ? WHERE chat_id = ?', 
                  (selected_topic, chat_id))
    conn.commit()
    conn.close()
    
    # Load topics info for description
    with open('topics_info.json', 'r', encoding='utf-8') as f:
        topics_info = json.load(f)
    
    topic_info = topics_info.get(selected_topic, {})
    desc = topic_info.get('description', 'لا يوجد وصف متاح')
    pages = topic_info.get('pages', 'غير محدد')
    
    response = f"✅ تم اختيار موضوع: *{selected_topic}*\n\n"
    response += f"📖 الصفحات: {pages}\n"
    response += f"ℹ️ الوصف: {desc}\n\n"
    response += "استخدم /question للحصول على سؤال من هذا الموضوع."
    
    bot.answer_callback_query(call.id)
    bot.send_message(chat_id, response, parse_mode="Markdown")
    
# Daily reminder job
def send_daily_reminders():
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM users')
    users = cursor.fetchall()
    conn.close()
    
    for user in users:
        try:
            bot.send_message(user[0], "⏰ حان وقت المذاكرة! استخدم /question لبدء جلسة اليوم.")
        except Exception as e:
            print(f"Failed to send reminder to {user[0]}: {e}")

# Schedule daily reminder at 6 PM
scheduler.add_job(send_daily_reminders, 'cron', hour=18)


@bot.message_handler(func=lambda message: True)
@handle_errors
def handle_text_answer(message):
    chat_id = message.chat.id
    q_id = bot.current_questions.get(chat_id)
    if not q_id:
        return  # لا يوجد سؤال نشط

    q = next((q for q in questions if q['id'] == q_id), None)
    if not q:
        bot.send_message(chat_id, "⚠️ حدث خطأ في تحميل السؤال.")
        return

    user_answer = preprocess_arabic(message.text.strip())
    topic = q.get('topic', 'عام')
    is_correct = False
    explanation = ""
    accuracy_percentage = 0

    # تحليل نوع الإجابة
    if q['type'] == 'mcq':
        correct_answers = [preprocess_arabic(q['choices'][i]) for i in q.get('correct_indices', [])]
        is_correct = any(user_answer == preprocess_arabic(ans) for ans in correct_answers)
        explanation = get_explanation(q)
        accuracy_percentage = 100 if is_correct else 0

    elif 'answer_keywords' in q:
        required_keywords = [preprocess_arabic(kw) for kw in q['answer_keywords']]
        user_answer_processed = preprocess_arabic(user_answer)
        matched_keywords = [kw for kw in required_keywords if kw in user_answer_processed]
        accuracy_percentage = (len(matched_keywords) / len(required_keywords)) * 100
        is_correct = accuracy_percentage >= 70
        explanation = f"🔑 *الكلمات المطلوبة:* {', '.join(q['answer_keywords'])}\n\n"
        explanation += f"📊 *نسبة الدقة:* {accuracy_percentage:.1f}%"

    elif 'answer' in q:
        correct_answer = preprocess_arabic(q['answer'])
        similarity = SequenceMatcher(None, user_answer, correct_answer).ratio()
        accuracy_percentage = similarity * 100
        is_correct = accuracy_percentage > 60
        explanation = get_explanation(q)
        explanation += f"\n\n📊 *نسبة التطابق:* {accuracy_percentage:.1f}%"
    
    else:
        explanation = "⚠️ لا توجد إجابة مرجعية لهذا السؤال."

    # تحديث النقاط وتحليل الأخطاء
    update_user_score(chat_id, is_correct, topic)
    record_answer_analysis(chat_id, q_id, user_answer, is_correct, accuracy_percentage)

    # بناء الرسالة النهائية للمستخدم
    if is_correct:
        response = f"✅ *إجابة صحيحة!* ({accuracy_percentage:.1f}%)\n\n{explanation}"
    else:
        correct_answer = q.get('answer_example', q.get('answer', 'لا توجد إجابة'))
        personalized_feedback = generate_feedback(chat_id, q_id, user_answer)
        response = (
            f"❌ *إجابة غير صحيحة!* ({accuracy_percentage:.1f}%)\n\n"
            f"📘 *الإجابة النموذجية:* {correct_answer}\n\n"
            f"{explanation}\n\n"
            f"{personalized_feedback}"
        )

    bot.send_message(chat_id, response, parse_mode="Markdown")

    # عرض الخيارات للمتابعة
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("➡️ سؤال جديد", callback_data="next_question")
    )
    bot.send_message(chat_id, "✨ هل تريد محاولة أخرى؟", reply_markup=markup)
    
    # بعد التأكد من صحة الإجابة
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO user_answered VALUES (?, ?)', (chat_id, q_id))
    conn.commit()
    conn.close()
    
def generate_feedback(chat_id, question_id, user_answer):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    # 1. تحليل الأخطاء الشائعة لهذا السؤال
    cursor.execute('''
    SELECT wrong_answer, count 
    FROM error_analysis 
    WHERE question_id = ? 
    ORDER BY count DESC LIMIT 3''', (question_id,))
    common_errors = cursor.fetchall()
    
    # 2. أداء المستخدم في الموضوع
    # الحصول على موضوع السؤال من قائمة الأسئلة بدلاً من قاعدة البيانات
    q = next((q for q in questions if q['id'] == question_id), None)
    topic = q.get('topic', 'عام') if q else 'عام'
    
    cursor.execute('''
    SELECT correct, attempts 
    FROM user_topics 
    WHERE chat_id = ? AND topic = ?''', (chat_id, topic))
    topic_stats = cursor.fetchone()
    
    # 3. الأخطاء المتكررة للمستخدم
    cursor.execute('''
    SELECT question_id, wrong_answer, count 
    FROM user_mistakes 
    WHERE chat_id = ? AND question_id = ?
    ORDER BY count DESC LIMIT 1''', (chat_id, question_id))
    user_common_mistake = cursor.fetchone()
    
    conn.close()
    
    # بناء التغذية الراجعة
    feedback_parts = []
    
    if common_errors:
        feedback_parts.append("⚠️ انتبه لهذه الأخطاء الشائعة:")
        for error, count in common_errors:
            feedback_parts.append(f"- {error[:30]}... (تكرار {count} مرة)")
    
    if user_common_mistake:
        _, mistake, count = user_common_mistake
        feedback_parts.append(f"\n🔍 لقد أخطأت في هذا السؤال {count} مرة بإجابة مشابهة لـ: {mistake[:30]}...")
    
    if topic_stats:
        correct, attempts = topic_stats
        accuracy = (correct / attempts * 100) if attempts > 0 else 0
        feedback_parts.append(f"\n📊 دقتك في هذا الموضوع: {accuracy:.1f}%")
        
        if accuracy < 50:
            feedback_parts.append("\n💡 ننصحك بمراجعة هذا الموضوع قبل المتابعة!")
    
    return "\n".join(feedback_parts) if feedback_parts else "حاول مراجعة الإجابة النموذجية للتعلم من أخطائك."
    
def record_answer_analysis(chat_id, question_id, user_answer, is_correct, accuracy):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    
    # تسجيل في جدول تحليل الأخطاء
    if not is_correct:
        # البحث عن الخطأ المسجل مسبقاً
        cursor.execute('''
        SELECT id, count FROM error_analysis 
        WHERE question_id = ? AND wrong_answer = ?''',
        (question_id, user_answer))
        
        error_record = cursor.fetchone()
        
        if error_record:
            # تحديث العداد إذا كان الخطأ مسجلاً
            error_id, count = error_record
            cursor.execute('UPDATE error_analysis SET count = count + 1 WHERE id = ?', (error_id,))
        else:
            # تسجيل خطأ جديد
            cursor.execute('''
            INSERT INTO error_analysis (question_id, wrong_answer)
            VALUES (?, ?)''', (question_id, user_answer))
    
    # تسجيل في جدول أخطاء المستخدم
    if not is_correct:
        cursor.execute('''
        INSERT INTO user_mistakes (chat_id, question_id, wrong_answer, accuracy)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chat_id, question_id, wrong_answer) 
        DO UPDATE SET count = count + 1, accuracy = MIN(accuracy, ?)''',
        (chat_id, question_id, user_answer, accuracy, accuracy))
    
    conn.commit()
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('mcq_'))
@handle_errors
def handle_choice(call):
    chat_id = call.message.chat.id
    selected_index = int(call.data.split('_')[1])
    q_id = bot.current_questions.get(chat_id)
    if not q_id:
        bot.answer_callback_query(call.id, "انتهت صلاحية السؤال.")
        return
    q = next((q for q in questions if q['id'] == q_id), None)
    if not q:
        bot.answer_callback_query(call.id, "حدث خطأ في تحميل السؤال.")
        return

    correct_indices = q.get('correct_indices', [])
    is_correct = selected_index in correct_indices
    update_user_score(chat_id, is_correct, q.get('topic', 'عام'))

    explanation = get_explanation(q)
    accuracy = 100 if is_correct else 0

    if is_correct:
        response = f"✅ *إجابة صحيحة!* ({accuracy}%)\n\n{explanation}"
    else:
        correct_answers = ", ".join([q['choices'][i] for i in correct_indices])
        response = f"❌ *خطأ!* ({accuracy}%)\n\nالإجابة الصحيحة هي: {correct_answers}\n\n{explanation}"

    bot.send_message(chat_id, response, parse_mode="Markdown")
    
    # زر سؤال جديد
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➡️ سؤال جديد", callback_data="next_question"))
    bot.send_message(chat_id, "✨ هل تريد سؤالًا جديدًا؟", reply_markup=markup)
    
    # بعد التأكد من صحة الإجابة
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO user_answered VALUES (?, ?)', (chat_id, q_id))
    conn.commit()
    conn.close()

@bot.message_handler(commands=['monthly_stats'])
@handle_errors
def monthly_stats(message):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    chat_id = message.chat.id

    cursor.execute('''
    SELECT strftime('%Y-%m', register_date) AS month, COUNT(*) 
    FROM users 
    GROUP BY month
    ORDER BY month DESC LIMIT 6
    ''')
    user_growth = cursor.fetchall()

    cursor.execute('''
    SELECT strftime('%Y-%m', start_time) AS month, SUM(questions_answered)
    FROM user_sessions
    GROUP BY month
    ORDER BY month DESC LIMIT 6
    ''')
    questions_answered = cursor.fetchall()

    conn.close()

    response = "📅 *إحصائيات شهرية*:\n\n"

    response += "👥 *نمو المستخدمين*\n"
    for month, count in user_growth:
        response += f"- {month}: {count} مستخدم\n"

    response += "\n❓ *عدد الأسئلة المجابة*\n"
    for month, count in questions_answered:
        response += f"- {month}: {count} سؤال\n"

    bot.reply_to(message, response, parse_mode="Markdown")
    
@bot.message_handler(commands=['yearly_stats'])
@handle_errors
def yearly_stats(message):
    conn = sqlite3.connect('science_bot.db')
    cursor = conn.cursor()
    chat_id = message.chat.id

    cursor.execute('''
    SELECT strftime('%Y', register_date) AS year, COUNT(*) 
    FROM users 
    GROUP BY year
    ORDER BY year DESC LIMIT 5
    ''')
    user_growth = cursor.fetchall()

    cursor.execute('''
    SELECT strftime('%Y', start_time) AS year, SUM(questions_answered)
    FROM user_sessions
    GROUP BY year
    ORDER BY year DESC LIMIT 5
    ''')
    questions_answered = cursor.fetchall()

    conn.close()

    response = "📆 *إحصائيات سنوية*:\n\n"

    response += "👥 *نمو المستخدمين*\n"
    for year, count in user_growth:
        response += f"- {year}: {count} مستخدم\n"

    response += "\n❓ *عدد الأسئلة المجابة*\n"
    for year, count in questions_answered:
        response += f"- {year}: {count} سؤال\n"

    bot.reply_to(message, response, parse_mode="Markdown")
    
@bot.callback_query_handler(func=lambda call: call.data in ['hint', 'explain'])
@handle_errors
def handle_question_actions(call):
    chat_id = call.message.chat.id
    q_id = bot.current_questions.get(chat_id)
    
    if not q_id:
        bot.answer_callback_query(call.id, "انتهت صلاحية السؤال.")
        return
    
    q = next((q for q in questions if q['id'] == q_id), None)
    if not q:
        bot.answer_callback_query(call.id, "حدث خطأ في تحميل السؤال.")
        return
    
    if call.data == 'hint':
        if 'hint' in q:
            bot.answer_callback_query(call.id)
            bot.send_message(chat_id, f"💡 تلميح: {q['hint']}")
        else:
            bot.answer_callback_query(call.id, "لا يوجد تلميح لهذا السؤال.")
    elif call.data == 'explain':
        bot.answer_callback_query(call.id)
        explanation = get_explanation(q)  # استخدم الدالة الجديدة
        bot.send_message(chat_id, f"📚 شرح الإجابة:\n{explanation}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('rate_'))
@handle_errors
def handle_rating(call):
    chat_id = call.message.chat.id
    _, rating, q_id = call.data.split('_')
    
    record_question_rating(chat_id, q_id, rating)
    bot.answer_callback_query(call.id, "شكراً لتقييمك!")
    
    if rating == 'hard':
        bot.send_message(chat_id, "سنعيد هذا السؤال لاحقاً لمساعدتك في فهمه بشكل أفضل.")
    
    show_question_followup(chat_id, q_id)

@bot.callback_query_handler(func=lambda call: call.data == 'next_question')
@handle_errors
def handle_next_question(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    send_question(call.message)  # Reuse the message object

import time
from requests.exceptions import ReadTimeout, ConnectionError


@bot.callback_query_handler(func=lambda call: True)
def handle_unknown_callback(call):
    # Log the unhandled callback for debugging
    print(f"Unhandled callback: {call.data}")
    bot.answer_callback_query(call.id, "⚠️ هذا الزر لم يتم تعريفه بعد", show_alert=True)

if __name__ == '__main__':
    try:
        # حاول استيراد Flask فقط عند الحاجة
        from flask import Flask, request
        
        print("Setting up webhook...")
        bot.remove_webhook()
        time.sleep(2)
        
        # تحقق من وجود متغير WEBHOOK_DOMAIN
        webhook_domain = os.getenv('WEBHOOK_DOMAIN')
        if not webhook_domain:
            raise ValueError("WEBHOOK_DOMAIN غير معرّف في ملف .env")
            
        webhook_url = f"https://{webhook_domain}/{TELEGRAM_BOT_TOKEN}"
        bot.set_webhook(url=webhook_url)
        print(f"Webhook set to: {webhook_url}")
        
        app = Flask(__name__)

        @app.route('/admin/dashboard')
        def admin_dashboard():
            if not ADMIN_CHAT_ID:
                return "غير مسموح بالوصول", 403
            
            conn = sqlite3.connect('science_bot.db')
            cursor = conn.cursor()
            
            # 1. إجمالي عدد المستخدمين
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            # 2. المستخدمين النشطين حالياً (خلال آخر 30 دقيقة)
            cursor.execute('''
            SELECT COUNT(*) FROM users 
            WHERE datetime(last_active) > datetime('now', '-30 minutes')
            ''')
            active_users = cursor.fetchone()[0]
            
            # 3. الملاحظات الواردة من المستخدمين
            cursor.execute('''
            SELECT chat_id, feedback_text, created_at 
            FROM user_feedback 
            ORDER BY created_at DESC LIMIT 10
            ''')
            feedbacks = cursor.fetchall()
            
            conn.close()
            
            # HTML template للواجهة
            template = """
            <!DOCTYPE html>
            <html dir="rtl" lang="ar">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>لوحة التحكم - QuizBot</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background-color: #f5f5f5;
                    }
                    .container {
                        max-width: 1000px;
                        margin: 0 auto;
                    }
                    .header {
                        background-color: #4CAF50;
                        color: white;
                        padding: 15px;
                        border-radius: 5px;
                        margin-bottom: 20px;
                        text-align: center;
                    }
                    .stats-container {
                        display: flex;
                        justify-content: space-between;
                        margin-bottom: 20px;
                    }
                    .stat-card {
                        background: white;
                        border-radius: 5px;
                        padding: 15px;
                        width: 30%;
                        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                        text-align: center;
                    }
                    .stat-card h3 {
                        margin-top: 0;
                        color: #333;
                    }
                    .stat-card .value {
                        font-size: 24px;
                        font-weight: bold;
                        color: #4CAF50;
                    }
                    .feedback-card {
                        background: white;
                        border-radius: 5px;
                        padding: 15px;
                        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                    }
                    .feedback-item {
                        border-bottom: 1px solid #eee;
                        padding: 10px 0;
                    }
                    .feedback-item:last-child {
                        border-bottom: none;
                    }
                    .feedback-user {
                        font-weight: bold;
                        color: #4CAF50;
                    }
                    .feedback-date {
                        color: #888;
                        font-size: 12px;
                    }
                    .feedback-text {
                        margin-top: 5px;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>لوحة تحكم QuizBot</h1>
                    </div>
                    
                    <div class="stats-container">
                        <div class="stat-card">
                            <h3>إجمالي المستخدمين</h3>
                            <div class="value">{{ total_users }}</div>
                        </div>
                        
                        <div class="stat-card">
                            <h3>المستخدمين النشطين</h3>
                            <div class="value">{{ active_users }}</div>
                        </div>
                        
                        <div class="stat-card">
                            <h3>الملاحظات الجديدة</h3>
                            <div class="value">{{ feedbacks|length }}</div>
                        </div>
                    </div>
                    
                    <div class="feedback-card">
                        <h2>آخر الملاحظات من المستخدمين</h2>
                        
                        {% for feedback in feedbacks %}
                        <div class="feedback-item">
                            <div>
                                <span class="feedback-user">مستخدم #{{ feedback[0] }}</span>
                                <span class="feedback-date">{{ feedback[2] }}</span>
                            </div>
                            <div class="feedback-text">{{ feedback[1] }}</div>
                        </div>
                        {% else %}
                        <p>لا توجد ملاحظات حتى الآن</p>
                        {% endfor %}
                    </div>
                </div>
            </body>
            </html>
            """
            
            return render_template_string(template, 
                                       total_users=total_users,
                                       active_users=active_users,
                                       feedbacks=feedbacks)

        @app.route('/' + TELEGRAM_BOT_TOKEN, methods=['POST'])
        def webhook():
            if request.headers.get('content-type') == 'application/json':
                json_string = request.get_data().decode('utf-8')
                update = telebot.types.Update.de_json(json_string)
                bot.process_new_updates([update])
                return 'OK', 200
            return 'Bad Request', 400

        @app.route('/')
        def index():
            return 'Bot is running!', 200

        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)

    except Exception as e:
        print(f"Webhook error: {e}")
        print("Falling back to polling...")
        bot.remove_webhook()
        time.sleep(2)
        while True:
            try:
                bot.infinity_polling()
            except (ReadTimeout, ConnectionError) as e:
                print(f"Connection error: {e}, retrying in 5 seconds...")
                time.sleep(5)
            except Exception as e:
                print(f"Unexpected error: {e}, restarting in 10 seconds...")
                time.sleep(10)
