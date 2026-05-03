import os
import sqlite3
import telebot
from telebot import types
from flask import Flask
from threading import Thread

# --- কনফিগারেশন ---
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0)) 
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

PAYMENT_NUMBERS = {
    "Bikash": "01806407976",
    "Nagad": "01806407976",
    "Rocket": "01806407976"
}

# --- ডাটাবেস সেটআপ ---
conn = sqlite3.connect('shop_v2.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)')
cursor.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price REAL)')
conn.commit()

@app.route('/')
def health(): return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def get_balance(user_id):
    cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
    res = cursor.fetchone()
    if res: return res[0]
    cursor.execute('INSERT INTO users (id, balance) VALUES (?, 0)', (user_id,))
    conn.commit()
    return 0

# --- মেনু সিস্টেম (অ্যাডমিন ছাড়া কেউ অ্যাডমিন বাটন দেখবে না) ---
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("🛍 Buy Panel")
    btn2 = types.KeyboardButton("💰 Add Money")
    markup.add(btn1, btn2)
    
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("👨‍💼 Admin Panel"))
    return markup

@bot.message_handler(commands=['start'])
def welcome(message):
    balance = get_balance(message.from_user.id)
    bot.send_message(
        message.chat.id, 
        f"👋 স্বাগতম!\n\nআপনার বর্তমান ব্যালেন্স: {balance} টাকা", 
        reply_markup=main_menu(message.from_user.id)
    )

# --- ADD MONEY & PAYMENT CANCEL SYSTEM ---
@bot.message_handler(func=lambda m: m.text == "💰 Add Money")
def add_money(message):
    markup = types.InlineKeyboardMarkup()
    for method in PAYMENT_NUMBERS.keys():
        markup.add(types.InlineKeyboardButton(f"{method}", callback_data=f"pay_{method}"))
    bot.send_message(message.chat.id, "পেমেন্ট মাধ্যম সিলেক্ট করুন:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay_info(call):
    method = call.data.split("_")[1]
    number = PAYMENT_NUMBERS.get(method)
    msg = f"💳 মাধ্যম: {method}\n📱 নাম্বার: `{number}` (Personal)\n\nটাকা পাঠিয়ে TrxID বা স্ক্রিনশট পাঠান।"
    sent_msg = bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
    bot.register_next_step_handler(sent_msg, process_payment_proof, method)

def process_payment_proof(message, method):
    bot.send_message(message.chat.id, "⏳ পেমেন্ট প্রুফ জমা হয়েছে। অপেক্ষা করুন...")
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f"apprv_{message.from_user.id}"),
        types.InlineKeyboardButton("❌ Cancel", callback_data=f"cancl_{message.from_user.id}")
    )
    
    info = message.text if message.text else "ছবি পাঠানো হয়েছে"
    bot.send_message(ADMIN_ID, f"🔔 **নতুন রিকোয়েস্ট!**\nইউজার: {message.from_user.id}\nমাধ্যম: {method}\nতথ্য: {info}", reply_markup=markup)

# --- APPROVE & CANCEL LOGIC ---
@bot.callback_query_handler(func=lambda call: call.data.startswith(("apprv_", "cancl_")))
def handle_admin_decision(call):
    action, u_id = call.data.split("_")
    u_id = int(u_id)

    if action == "apprv":
        msg = bot.send_message(ADMIN_ID, "কত টাকা অ্যাড করতে চান? (সংখ্যা লিখুন)")
        bot.register_next_step_handler(msg, finalize_approval, u_id)
    else:
        bot.send_message(u_id, "❌ আপনার পেমেন্ট রিকোয়েস্টটি বাতিল করা হয়েছে। সঠিক তথ্য দিয়ে আবার চেষ্টা করুন।")
        bot.send_message(ADMIN_ID, f"🚫 ইউজার {u_id}-এর পেমেন্ট বাতিল করা হয়েছে।")
    bot.delete_message(call.message.chat.id, call.message.message_id)

def finalize_approval(message, u_id):
    try:
        amount = float(message.text)
        cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, u_id))
        conn.commit()
        bot.send_message(u_id, f"🎉 অভিনন্দন! {amount} টাকা আপনার ওয়ালেটে যোগ হয়েছে।")
        bot.send_message(ADMIN_ID, "✅ পেমেন্ট অ্যাপ্রুভ করা হয়েছে।")
    except:
        bot.send_message(ADMIN_ID, "❌ ভুল সংখ্যা। আবার ট্রাই করুন।")

# --- BUY PANEL ---
@bot.message_handler(func=lambda m: m.text == "🛍 Buy Panel")
def buy_panel(message):
    cursor.execute('SELECT * FROM products')
    products = cursor.fetchall()
    markup = types.InlineKeyboardMarkup()
    for p in products:
        markup.add(types.InlineKeyboardButton(f"{p[1]} - {p[2]} TK", callback_data=f"buy_{p[0]}"))
    bot.send_message(message.chat.id, "🛒 প্রোডাক্ট লিস্ট:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_buy(call):
    p_id = call.data.split("_")[1]
    cursor.execute('SELECT name, price FROM products WHERE id = ?', (p_id,))
    product = cursor.fetchone()
    balance = get_balance(call.from_user.id)

    if balance >= product[1]:
        cursor.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (product[1], call.from_user.id))
        conn.commit()
        bot.answer_callback_query(call.id, f"✅ কেনা সফল: {product[0]}", show_alert=True)
        bot.send_message(ADMIN_ID, f"📦 **বিক্রি হয়েছে!**\nইউজার: {call.from_user.id}\nপণ্য: {product[0]}\nমূল্য: {product[1]}")
    else:
        bot.answer_callback_query(call.id, "❌ পর্যাপ্ত ব্যালেন্স নেই!", show_alert=True)

# --- ADVANCED ADMIN PANEL ---
@bot.message_handler(func=lambda m: m.text == "👨‍💼 Admin Panel")
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📝 Edit Products", callback_data="edit_pro"),
        types.InlineKeyboardButton("🔍 Check User Balance", callback_data="check_bal"),
        types.InlineKeyboardButton("📢 Broadcast Message", callback_data="broadcast")
    )
    bot.send_message(message.chat.id, "🛠 অ্যাডমিন কন্ট্রোল প্যানেল:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "check_bal")
def check_user_bal_step1(call):
    msg = bot.send_message(ADMIN_ID, "ইউজারের আইডি (Telegram ID) দিন:")
    bot.register_next_step_handler(msg, check_user_bal_step2)

def check_user_bal_step2(message):
    try:
        u_id = int(message.text)
        cursor.execute('SELECT balance FROM users WHERE id = ?', (u_id,))
        res = cursor.fetchone()
        if res: bot.send_message(ADMIN_ID, f"👤 ইউজার: {u_id}\n💰 ব্যালেন্স: {res[0]} টাকা")
        else: bot.send_message(ADMIN_ID, "❌ ইউজার খুঁজে পাওয়া যায়নি।")
    except: bot.send_message(ADMIN_ID, "❌ আইডি ভুল।")

@bot.callback_query_handler(func=lambda call: call.data == "broadcast")
def broadcast_step1(call):
    msg = bot.send_message(ADMIN_ID, "সব ইউজারকে কি মেসেজ পাঠাতে চান?")
    bot.register_next_step_handler(msg, broadcast_step2)

def broadcast_step2(message):
    cursor.execute('SELECT id FROM users')
    users = cursor.fetchall()
    count = 0
    for u in users:
        try:
            bot.send_message(u[0], f"📢 **নোটিশ:**\n\n{message.text}")
            count += 1
        except: pass
    bot.send_message(ADMIN_ID, f"✅ {count} জন ইউজারকে মেসেজ পাঠানো হয়েছে।")

# --- (পুরানো কোডের মতো Edit Product অংশ এখানে থাকবে) ---
@bot.callback_query_handler(func=lambda call: call.data == "edit_pro")
def edit_list(call):
    cursor.execute('SELECT * FROM products')
    for p in cursor.fetchall():
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Edit", callback_data=f"edititem_{p[0]}"))
        bot.send_message(ADMIN_ID, f"ID: {p[0]} | {p[1]} | {p[2]} TK", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("edititem_"))
def edit_start(call):
    i_id = call.data.split("_")[1]
    msg = bot.send_message(ADMIN_ID, "ফরম্যাট: `নাম, দাম` (যেমন: Netflix, 200)")
    bot.register_next_step_handler(msg, edit_finish, i_id)

def edit_finish(message, i_id):
    try:
        n, p = message.text.split(',')
        cursor.execute('UPDATE products SET name=?, price=? WHERE id=?', (n.strip(), float(p), i_id))
        conn.commit()
        bot.send_message(ADMIN_ID, "✅ আপডেট হয়েছে।")
    except: bot.send_message(ADMIN_ID, "❌ ভুল ফরম্যাট।")

if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.infinity_polling()
