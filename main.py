import os
import sqlite3
import telebot
from telebot import types
from flask import Flask
from threading import Thread

# --- কনফিগারেশন ---
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0)) # আপনার আইডি
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# পেমেন্ট নাম্বার (আপনার নাম্বার দিয়ে পরিবর্তন করুন)
PAYMENT_NUMBERS = {
    "Bikash": "01806407976",
    "Nagad": "01806407976",
    "Rocket": "01806407976"
}

# --- ডাটাবেস সেটআপ ---
conn = sqlite3.connect('shop.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)')
cursor.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price REAL)')
conn.commit()

# ডিফল্ট কিছু প্রোডাক্ট যোগ করা (যদি ডাটাবেস খালি থাকে)
cursor.execute('SELECT COUNT(*) FROM products')
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO products (name, price) VALUES ('Product 1', 100), ('Product 2', 200), ('Product 3', 500)")
    conn.commit()

# --- ওয়েব সার্ভার (Render এর জন্য) ---
@app.route('/')
def health(): return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- ইউজার ব্যালেন্স ফাংশন ---
def get_balance(user_id):
    cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
    res = cursor.fetchone()
    if res: return res[0]
    cursor.execute('INSERT INTO users (id, balance) VALUES (?, 0)', (user_id,))
    conn.commit()
    return 0

# --- মেইন মেনু ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🛍 Buy Panel", "💰 Add Money", "👨‍💼 Admin Panel")
    return markup

@bot.message_handler(commands=['start'])
def welcome(message):
    balance = get_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"👋 স্বাগতম!\n\nআপনার বর্তমান ব্যালেন্স: {balance} টাকা", reply_markup=main_menu())

# --- ADD MONEY SYSTEM ---
@bot.message_handler(func=lambda m: m.text == "💰 Add Money")
def add_money(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("বিকাশ (Bikash)", callback_data="pay_Bikash"))
    markup.add(types.InlineKeyboardButton("নগদ (Nagad)", callback_data="pay_Nagad"))
    markup.add(types.InlineKeyboardButton("রকেট (Rocket)", callback_data="pay_Rocket"))
    bot.send_message(message.chat.id, "নিচের কোন মাধ্যমে টাকা পাঠাতে চান?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay_info(call):
    method = call.data.split("_")[1]
    number = PAYMENT_NUMBERS.get(method)
    msg = f"💳 মাধ্যম: {method}\n📱 নাম্বার: `{number}`\n\nটাকা পাঠানোর পর ট্রানজেকশন আইডি (TrxID) বা স্ক্রিনশট এখানে পাঠান।"
    sent_msg = bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
    bot.register_next_step_handler(sent_msg, process_payment_proof, method)

def process_payment_proof(message, method):
    # পেমেন্ট প্রুফ অ্যাডমিনের কাছে পাঠানো
    bot.send_message(message.chat.id, "⏳ আপনার পেমেন্ট প্রুফ জমা হয়েছে। অ্যাডমিন চেক করে অ্যাপ্রুভ করবে।")
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"apprv_{message.from_user.id}"))
    
    bot.send_message(ADMIN_ID, f"🔔 **নতুন পেমেন্ট রিকোয়েস্ট!**\nইউজার আইডি: {message.from_user.id}\nমাধ্যম: {method}\nতথ্য: {message.text if message.text else 'ছবি পাঠানো হয়েছে'}", reply_markup=markup)

# --- BUY PANEL SYSTEM ---
@bot.message_handler(func=lambda m: m.text == "🛍 Buy Panel")
def buy_panel(message):
    cursor.execute('SELECT * FROM products')
    products = cursor.fetchall()
    markup = types.InlineKeyboardMarkup()
    for p in products:
        markup.add(types.InlineKeyboardButton(f"{p[1]} - {p[2]} TK", callback_data=f"buy_{p[0]}"))
    bot.send_message(message.chat.id, "🛒 আমাদের প্রোডাক্টগুলো দেখুন:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_buy(call):
    p_id = call.data.split("_")[1]
    cursor.execute('SELECT name, price FROM products WHERE id = ?', (p_id,))
    product = cursor.fetchone()
    user_id = call.from_user.id
    balance = get_balance(user_id)

    if balance >= product[1]:
        new_balance = balance - product[1]
        cursor.execute('UPDATE users SET balance = ? WHERE id = ?', (new_balance, user_id))
        conn.commit()
        bot.answer_callback_query(call.id, f"✅ সফলভাবে কেনা হয়েছে: {product[0]}", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "❌ আপনার যথেষ্ট টাকা নেই। দয়া করে Add Money করুন।", show_alert=True)

# --- ADMIN ACTIONS ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("apprv_"))
def approve_money(call):
    u_id = int(call.data.split("_")[1])
    msg = bot.send_message(ADMIN_ID, "কত টাকা অ্যাড করতে চান? (শুধুমাত্র সংখ্যা লিখুন)")
    bot.register_next_step_handler(msg, finalize_approval, u_id)

def finalize_approval(message, u_id):
    try:
        amount = float(message.text)
        cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, u_id))
        conn.commit()
        bot.send_message(ADMIN_ID, f"✅ {amount} টাকা অ্যাড করা হয়েছে।")
        bot.send_message(u_id, f"🎉 অভিনন্দন! আপনার ওয়ালেটে {amount} টাকা যোগ করা হয়েছে।")
    except:
        bot.send_message(ADMIN_ID, "❌ ভুল ইনপুট।")

@bot.message_handler(func=lambda m: m.text == "👨‍💼 Admin Panel")
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📝 প্রোডাক্টের নাম/দাম পরিবর্তন", callback_data="edit_pro"))
    bot.send_message(message.chat.id, "অ্যাডমিন প্যানেল:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "edit_pro")
def edit_product_list(call):
    cursor.execute('SELECT * FROM products')
    products = cursor.fetchall()
    for p in products:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("সম্পাদনা করুন", callback_data=f"edititem_{p[0]}"))
        bot.send_message(call.message.chat.id, f"প্রোডাক্ট: {p[1]}\nদাম: {p[2]}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("edititem_"))
def edit_item_step1(call):
    item_id = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id, "নতুন নাম এবং দাম পাঠান। ফরম্যাট: `নাম, দাম` (যেমন: Netflix, 250)")
    bot.register_next_step_handler(msg, edit_item_step2, item_id)

def edit_item_step2(message, item_id):
    try:
        name, price = message.text.split(',')
        cursor.execute('UPDATE products SET name = ?, price = ? WHERE id = ?', (name.strip(), float(price), item_id))
        conn.commit()
        bot.send_message(message.chat.id, "✅ আপডেট সফল!")
    except:
        bot.send_message(message.chat.id, "❌ ফরম্যাট ভুল ছিল।")

# --- শুরু করুন ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("Bot is polling...")
    bot.infinity_polling()
