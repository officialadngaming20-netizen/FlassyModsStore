import os
import sqlite3
import telebot
from telebot import types
from flask import Flask
from threading import Thread

# --- CONFIG & INIT ---
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0)) # Your Telegram ID
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- DATABASE SETUP ---
def get_db():
    conn = sqlite3.connect('shop_data.db', check_same_thread=False)
    return conn

db = get_db()
cursor = db.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price REAL, stock INTEGER)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_name TEXT, amount REAL)''')
db.commit()

# --- WEB SERVER FOR RENDER ---
@app.route('/')
def health(): return "Bot is Online"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- HELPER FUNCTIONS ---
def get_user_balance(user_id):
    cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
    res = cursor.fetchone()
    if res: return res[0]
    cursor.execute('INSERT INTO users (id, balance) VALUES (?, ?)', (user_id, 0.0))
    db.commit()
    return 0.0

# --- BOT COMMANDS ---
@bot.message_handler(commands=['start'])
def main_menu(message):
    balance = get_user_balance(message.from_user.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("🛍 Shop", "💰 Wallet", "📦 My Orders", "👨‍💼 Admin")
    bot.send_message(message.chat.id, f"Welcome! \n\nYour Balance: **{balance} USD**", 
                     reply_markup=markup, parse_mode="Markdown")

# --- WALLET SYSTEM ---
@bot.message_handler(func=lambda m: m.text == "💰 Wallet")
def wallet(message):
    balance = get_user_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"💳 **Wallet Details**\n\nBalance: {balance} USD\n\nTo add funds, contact @Admin.", parse_mode="Markdown")

# --- SHOP SYSTEM ---
@bot.message_handler(func=lambda m: m.text == "🛍 Shop")
def shop(message):
    cursor.execute('SELECT * FROM products WHERE stock > 0')
    items = cursor.fetchall()
    if not items:
        return bot.send_message(message.chat.id, "The shop is currently empty.")
    
    markup = types.InlineKeyboardMarkup()
    for item in items:
        markup.add(types.InlineKeyboardButton(f"{item[1]} - ${item[2]}", callback_data=f"buy_{item[0]}"))
    bot.send_message(message.chat.id, "Select an item to buy:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_purchase(call):
    item_id = call.data.split('_')[1]
    user_id = call.from_user.id
    
    cursor.execute('SELECT name, price, stock FROM products WHERE id = ?', (item_id,))
    item = cursor.fetchone()
    balance = get_user_balance(user_id)
    
    if item and balance >= item[1]:
        # Update Database
        new_balance = balance - item[1]
        cursor.execute('UPDATE users SET balance = ? WHERE id = ?', (new_balance, user_id))
        cursor.execute('UPDATE products SET stock = stock - 1 WHERE id = ?', (item_id,))
        cursor.execute('INSERT INTO orders (user_id, item_name, amount) VALUES (?, ?, ?)', (user_id, item[0], item[1]))
        db.commit()
        
        bot.answer_callback_query(call.id, "✅ Purchase Successful!")
        bot.send_message(call.message.chat.id, f"Success! You bought **{item[0]}**.")
    else:
        bot.answer_callback_query(call.id, "❌ Insufficient Balance!", show_alert=True)

# --- ORDERS SYSTEM ---
@bot.message_handler(func=lambda m: m.text == "📦 My Orders")
def my_orders(message):
    cursor.execute('SELECT item_name, amount FROM orders WHERE user_id = ?', (message.from_user.id,))
    orders = cursor.fetchall()
    if not orders:
        return bot.send_message(message.chat.id, "You haven't ordered anything yet.")
    
    msg = "📜 **Your Order History:**\n"
    for o in orders:
        msg += f"• {o[0]} - ${o[1]}\n"
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# --- ADMIN PANEL ---
@bot.message_handler(func=lambda m: m.text == "👨‍💼 Admin")
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return bot.send_message(message.chat.id, "❌ Access Denied.")
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ Add Product", callback_data="admin_add"))
    bot.send_message(message.chat.id, "Admin Control Panel:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_add")
def admin_add_start(call):
    msg = bot.send_message(call.message.chat.id, "Send product details in format:\n`Name, Price, Stock`\nExample: `Netflix Acc, 5, 10`")
    bot.register_next_step_handler(msg, process_add_product)

def process_add_product(message):
    try:
        name, price, stock = message.text.split(',')
        cursor.execute('INSERT INTO products (name, price, stock) VALUES (?, ?, ?)', (name.strip(), float(price), int(stock)))
        db.commit()
        bot.send_message(message.chat.id, "✅ Product Added!")
    except:
        bot.send_message(message.chat.id, "❌ Invalid format. Use: Name, Price, Stock")

# --- START ---
if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("Bot is running...")
    bot.infinity_polling()
