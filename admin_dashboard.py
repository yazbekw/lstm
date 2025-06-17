# -*- coding: utf-8 -*-
from flask import Flask, render_template, request
import sqlite3
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # هذا السطر مهم لتجنب مشاكل الخيوط

app = Flask(__name__)

# تكوين قاعدة البيانات
DATABASE = 'science_bot.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def generate_plot(data, x, y, title, xlabel, ylabel, plot_type='bar', figsize=(10, 5)):
    plt.figure(figsize=figsize)
    
    if plot_type == 'bar':
        plt.bar(data[x], data[y])
    elif plot_type == 'line':
        plt.plot(data[x], data[y], marker='o')
    elif plot_type == 'pie':
        plt.pie(data[y], labels=data[x], autopct='%1.1f%%')
    
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.xticks(rotation=45)
    plt.grid(True, linestyle='--', alpha=0.7)
    
    img = BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight', dpi=100)
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode('utf8')
    plt.close()
    
    return plot_url

@app.route('/')
def dashboard():
    conn = get_db_connection()
    
    # إحصائيات المستخدمين
    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    active_today = conn.execute("""
        SELECT COUNT(*) FROM users 
        WHERE date(last_active) = date('now')
    """).fetchone()[0]
    new_today = conn.execute("""
        SELECT COUNT(*) FROM users 
        WHERE date(register_date) = date('now')
    """).fetchone()[0]
    
    # إحصائيات النشاط
    total_questions_answered = conn.execute("""
        SELECT SUM(questions_answered) FROM user_sessions
    """).fetchone()[0] or 0
    
    avg_questions_per_user = round(total_questions_answered / total_users, 1) if total_users > 0 else 0
    
    # إحصائيات الجلسات
    active_sessions = conn.execute("""
        SELECT COUNT(*) FROM user_sessions 
        WHERE end_time IS NULL
    """).fetchone()[0]
    
    avg_session_duration = conn.execute("""
        SELECT AVG((julianday(end_time) - julianday(start_time)) * 24 * 60) 
        FROM user_sessions WHERE end_time IS NOT NULL
    """).fetchone()[0] or 0
    
    # الملاحظات الحديثة
    recent_feedback = conn.execute("""
        SELECT chat_id, feedback_text, created_at 
        FROM user_feedback 
        ORDER BY created_at DESC LIMIT 5
    """).fetchall()
    
    # الأخطاء الشائعة
    common_errors = conn.execute("""
        SELECT question_id, wrong_answer, count 
        FROM error_analysis 
        ORDER BY count DESC LIMIT 5
    """).fetchall()
    
    # نمو المستخدمين (آخر 7 أيام)
    user_growth = conn.execute("""
        SELECT date(register_date) as day, COUNT(*) as count 
        FROM users 
        WHERE date(register_date) >= date('now', '-7 days')
        GROUP BY day 
        ORDER BY day
    """).fetchall()
    
    # نشاط المستخدمين (آخر 7 أيام)
    user_activity = conn.execute("""
        SELECT date(last_active) as day, COUNT(*) as count 
        FROM users 
        WHERE date(last_active) >= date('now', '-7 days')
        GROUP BY day 
        ORDER BY day
    """).fetchall()
    
    # توزيع المواضيع
    topic_distribution = conn.execute("""
        SELECT selected_topic as topic, COUNT(*) as count 
        FROM users 
        WHERE selected_topic IS NOT NULL
        GROUP BY selected_topic 
        ORDER BY count DESC LIMIT 5
    """).fetchall()
    
    # جلسات المستخدمين حسب الوقت
    session_hours = conn.execute("""
        SELECT strftime('%H', start_time) as hour, COUNT(*) as count
        FROM user_sessions
        GROUP BY hour
        ORDER BY hour
    """).fetchall()
    
    conn.close()
    
    # تحضير البيانات للرسوم البيانية
    growth_df = pd.DataFrame(user_growth, columns=['day', 'count'])
    activity_df = pd.DataFrame(user_activity, columns=['day', 'count'])
    topics_df = pd.DataFrame(topic_distribution, columns=['topic', 'count'])
    hours_df = pd.DataFrame(session_hours, columns=['hour', 'count'])
    
    # إنشاء الرسوم البيانية
    growth_plot = generate_plot(growth_df, 'day', 'count', 
                              'نمو المستخدمين في آخر 7 أيام', 'التاريخ', 'عدد المستخدمين', 'line')
    
    activity_plot = generate_plot(activity_df, 'day', 'count',
                                'نشاط المستخدمين في آخر 7 أيام', 'التاريخ', 'مستخدمين نشطين', 'line')
    
    topics_plot = generate_plot(topics_df, 'topic', 'count',
                              'توزيع المواضيع المفضلة', 'الموضوع', 'عدد المستخدمين', 'pie', (8, 8))
    
    hours_plot = generate_plot(hours_df, 'hour', 'count',
                             'توزيع الجلسات خلال اليوم', 'الساعة', 'عدد الجلسات', 'bar')
    
    return render_template('dashboard.html',
                         total_users=total_users,
                         active_today=active_today,
                         new_today=new_today,
                         total_questions=total_questions_answered,
                         avg_questions=avg_questions_per_user,
                         active_sessions=active_sessions,
                         avg_session_duration=round(avg_session_duration, 1),
                         feedbacks=recent_feedback,
                         errors=common_errors,
                         growth_plot=growth_plot,
                         activity_plot=activity_plot,
                         topics_plot=topics_plot,
                         hours_plot=hours_plot)

@app.route('/feedback')
def view_feedback():
    conn = get_db_connection()
    
    # جلب جميع الملاحظات مع إمكانية التصفية
    search_query = request.args.get('search', '')
    rating_filter = request.args.get('rating', '')
    
    query = """
        SELECT u.chat_id, uf.feedback_text, uf.rating, uf.created_at 
        FROM user_feedback uf
        LEFT JOIN users u ON uf.chat_id = u.chat_id
        WHERE 1=1
    """
    params = []
    
    if search_query:
        query += " AND feedback_text LIKE ?"
        params.append('%'+search_query+'%')
    
    if rating_filter:
        query += " AND rating = ?"
        params.append(rating_filter)
    
    query += " ORDER BY uf.created_at DESC"
    
    feedbacks = conn.execute(query, params).fetchall()
    
    # إحصائيات الملاحظات
    feedback_stats = conn.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN rating = 5 THEN 1 ELSE 0 END) as excellent,
            SUM(CASE WHEN rating = 4 THEN 1 ELSE 0 END) as good,
            SUM(CASE WHEN rating = 3 THEN 1 ELSE 0 END) as average,
            SUM(CASE WHEN rating = 2 THEN 1 ELSE 0 END) as poor,
            SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as bad
        FROM user_feedback
    """).fetchone()
    
    conn.close()
    return render_template('feedback.html', 
                         feedbacks=feedbacks,
                         feedback_stats=feedback_stats,
                         search_query=search_query,
                         rating_filter=rating_filter)

@app.route('/users')
def view_users():
    conn = get_db_connection()
    
    # جلب بيانات المستخدمين مع إحصائياتهم
    users = conn.execute("""
        SELECT 
            u.chat_id, 
            u.register_date, 
            u.last_active, 
            u.score, 
            u.attempts,
            (SELECT COUNT(*) FROM user_sessions WHERE chat_id = u.chat_id) as sessions,
            (SELECT SUM(questions_answered) FROM user_sessions WHERE chat_id = u.chat_id) as questions_answered,
            (SELECT COUNT(*) FROM user_feedback WHERE chat_id = u.chat_id) as feedback_count,
            (SELECT COUNT(*) FROM user_invites WHERE chat_id = u.chat_id AND uses > 0) as invites
        FROM users u
        ORDER BY u.last_active DESC
        LIMIT 100
    """).fetchall()
    
    # إحصائيات المستخدمين
    user_stats = conn.execute("""
        SELECT 
            COUNT(*) as total,
            AVG(score) as avg_score,
            AVG(attempts) as avg_attempts,
            SUM(CASE WHEN date(last_active) = date('now') THEN 1 ELSE 0 END) as active_today,
            SUM(CASE WHEN date(register_date) = date('now') THEN 1 ELSE 0 END) as new_today
        FROM users
    """).fetchone()
    
    conn.close()
    return render_template('users.html', 
                         users=users,
                         user_stats=user_stats)

@app.route('/questions')
def view_questions():
    conn = get_db_connection()
    
    # جلب الأسئلة مع إحصائياتها
    questions = conn.execute("""
        SELECT 
            q.id,
            q.question,
            q.topic,
            q.difficulty,
            COUNT(DISTINCT ua.chat_id) as users_answered,
            COUNT(DISTINCT um.chat_id) as users_mistakes,
            (SELECT COUNT(*) FROM error_analysis WHERE question_id = q.id) as total_errors
        FROM questions q
        LEFT JOIN user_answered ua ON q.id = ua.question_id
        LEFT JOIN user_mistakes um ON q.id = um.question_id
        GROUP BY q.id
        ORDER BY total_errors DESC
        LIMIT 50
    """).fetchall()
    
    # إحصائيات الأسئلة
    question_stats = conn.execute("""
        SELECT 
            COUNT(*) as total,
            AVG(difficulty) as avg_difficulty,
            COUNT(DISTINCT topic) as topics_count,
            (SELECT COUNT(*) FROM error_analysis) as total_errors
        FROM questions
    """).fetchone()
    
    conn.close()
    return render_template('questions.html',
                         questions=questions,
                         question_stats=question_stats)

if __name__ == '__main__':
    app.run(debug=True, port=5001)