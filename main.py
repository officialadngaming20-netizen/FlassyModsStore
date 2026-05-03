import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from flask import Flask
from threading import Thread

# 1. Setup Environment
TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Simple Product Catalog
PRODUCTS = {
    'item_1': {'name': 'E-Book: Python Pro', 'price': 50, 'description': 'Master Python in 30 days.'},
    'item_2': {'name': 'Digital Art Pack', 'price': 100, 'description': 'High-res wallpapers.'}
}

@app.route('/')
def health_check():
    return "Bot is active!"

# 2. Bot Logic: Start Command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = InlineKeyboardMarkup()
    for pid, p in PRODUCTS.items():
        markup.add(InlineKeyboardButton(f"{p['name']} - {p['price']}⭐", callback_data=f"buy_{pid}"))
    
    bot.send_message(message.chat.id, "Welcome to our Shop! Choose a product:", reply_markup=markup)

# 3. Handle Payment
@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def handle_buy(call):
    pid = call.data.split('_')[1]
    product = PRODUCTS[pid]
    
    bot.send_invoice(
        call.message.chat.id,
        title=product['name'],
        description=product['description'],
        invoice_payload=pid,
        provider_token="", # Leave empty for Telegram Stars
        currency="XTR",   # Telegram Stars currency code
        prices=[LabeledPrice(label=product['name'], amount=product['price'])]
    )

# 4. Mandatory Pre-Checkout & Success Handlers
@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(query):
    bot.answer_pre_checkout_query(query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    bot.reply_to(message, "Payment Successful! Thank you for your purchase.")

# 5. Run Flask and Bot together
def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()
