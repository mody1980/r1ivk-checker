# -*- coding: utf-8 -*-
import os
import re
import time
import requests
import threading
import concurrent.futures
from urllib.parse import urlparse, parse_qs
import urllib3
from requests.adapters import HTTPAdapter
import telebot
from telebot import types

urllib3.disable_warnings()

BOT_TOKEN = "8896382526:AAFMror2dFQ1U0r6RRHrrya2PKuyuoTRtnw"
OWNER_USERNAME = "@r1ivk"
bot = telebot.TeleBot(BOT_TOKEN)

active_scans = {}  
premium_users = []

PROXIES_LIST = []
if os.path.exists("good_proxies.txt"):
    with open("good_proxies.txt", "r", encoding="utf-8", errors="ignore") as f:
        PROXIES_LIST = [line.strip() for line in f if line.strip()]

def get_random_proxy():
    if not PROXIES_LIST:
        return None
    import random
    p = random.choice(PROXIES_LIST)
    if not p.startswith("http"):
        return {"http": f"http://{p}", "https": f"http://{p}"}
    return {"http": p, "https": p}

def check_account_turbo(combo, user_state):
    if not user_state.get('is_running', True):
        return

    parts = combo.split(':')
    if len(parts) < 2:
        with user_state['lock']:
            user_state['bad'] += 1
            user_state['checked'] += 1
        return

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()
    
    # محاكاة فحص سريعة للتأكد من حركة العداد (للتشخيص لو السيرفر يبطئ)
    time.sleep(0.5)
    with user_state['lock']:
        user_state['bad'] += 1
        user_state['checked'] += 1

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔥 r1ivk Checker ⚡", callback_data="start_checker"))
    bot.send_message(message.chat.id, "Welcome to *r1ivk Checker ⚡*\nChoose your tool below:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "start_checker")
def callback_checker(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_scan"))
    bot.send_message(call.message.chat.id, "🚀 *r1ivk Checker ⚡ Selected.*\n\nPlease send your combo file (`.txt`):", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["cancel_scan", "refresh_stats", "back_home"])
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "cancel_scan":
        if chat_id in active_scans:
            active_scans[chat_id]['is_running'] = False
        bot.answer_callback_query(call.id, "Scan stopped.")
        bot.edit_message_text("❌ *Scan manually stopped.*", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    chat_id = message.chat.id
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        file_path = f"combo_{chat_id}.txt"
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)

        combos = []
        # قراءة متقدمة تتجاوز أي مشاكل ترميز أو أحرف مخفية
        with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
            for line in f:
                line = line.strip().replace('\ufeff', '')
                if ':' in line:
                    combos.append(line)

        if not combos:
            bot.send_message(chat_id, "⚠️ الملف فارغ أو لا يحتوي على فاصل `:` بين الإيميل والباسورد!")
            return

        unique_combos = list(dict.fromkeys(combos))

        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("🛑 Stop Scan", callback_data="cancel_scan"))

        status_msg = bot.send_message(chat_id, "🔥 *LIVE SCAN STATS (Auto-refresh)*", parse_mode="Markdown", reply_markup=markup)

        user_state = {
            'chat_id': chat_id,
            'checked': 0,
            'total': len(unique_combos),
            'hits': 0,
            'bad': 0,
            'twofa': 0,
            'errors': 0,
            'hits_list': [],
            'is_running': True,
            'lock': threading.Lock(),
            'start_time': time.time()
        }
        active_scans[chat_id] = user_state

        threading.Thread(target=update_stats_loop, args=(chat_id, status_msg.message_id, user_state), daemon=True).start()
        threading.Thread(target=run_turbo_scan, args=(unique_combos, user_state, status_msg.message_id), daemon=True).start()

    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")

def update_stats_loop(chat_id, msg_id, state):
    while state['is_running'] and state['checked'] < state['total']:
        time.sleep(1)
        elapsed = time.time() - state['start_time']
        cpm = int((state['checked'] / elapsed) * 60) if elapsed > 1 else 0
        
        pct = (state['checked'] / state['total']) * 100 if state['total'] > 0 else 0
        filled = int(pct / 10)
        bar = "█" * filled + "░" * (10 - filled)

        text = f"""🔥 *LIVE SCAN STATS ({time.strftime('%H:%M:%S')})*

📊 *Total:*         {state['total']}
✓ *Checked:*    {state['checked']}
✗ *Bad:*          {state['bad']}
★ *Hits:*          {state['hits']}
🔒 *2FA:*          {state['twofa']}
⚠ *Errors:*      {state['errors']}

Progress: {pct:.1f}%
\\[{bar}\\]

⚡ *CPM:* {cpm}"""

        try:
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("🛑 Stop Scan", callback_data="cancel_scan"))
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="Markdown", reply_markup=markup)
        except:
            pass

def run_turbo_scan(combos, state, msg_id):
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_account_turbo, combo, state) for combo in combos]
        concurrent.futures.wait(futures)

    state['is_running'] = False
    bot.send_message(state['chat_id'], "✅ Scan finished successfully!")

if __name__ == "__main__":
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
