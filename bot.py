# -*- coding: utf-8 -*-
"""
r1livk Checker ⚡ - Telegram Bot (Device Token & Pro Inventory Mode)
"""

import os
import re
import time
import threading
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import requests
import urllib3
from urllib.parse import urlparse, parse_qs
from requests.adapters import HTTPAdapter
import telebot
from telebot import types

urllib3.disable_warnings()

TOKEN = "8896382526:AAFMror2dFQ1U0r6RRHrrya2PKuyuoTRtnw"
OWNER_ID = 123456789  # <--- ضع الـ ID الخاص بك هنا (تأكد من كتابته بشكل صحيح)
bot = telebot.TeleBot(TOKEN)

REQUEST_TIMEOUT = 25
MAX_THREADS = 10

active_scans = {}
user_usage = {}  
DAILY_LIMIT = 2500

def check_daily_limit(chat_id, new_lines_count):
    # صلاحية الأونر (Unlimited)
    if chat_id == OWNER_ID:
        return True, new_lines_count
        
    today = date.today()
    if chat_id not in user_usage or user_usage[chat_id]["date"] != today:
        user_usage[chat_id] = {"date": today, "count": 0}
    
    current_used = user_usage[chat_id]["count"]
    if current_used >= DAILY_LIMIT:
        return False, 0
    
    allowed_lines = min(new_lines_count, DAILY_LIMIT - current_used)
    return True, allowed_lines

def update_usage(chat_id, count):
    if chat_id == OWNER_ID: return # الأونر لا يستهلك من الكوتا
    today = date.today()
    if chat_id in user_usage and user_usage[chat_id]["date"] == today:
        user_usage[chat_id]["count"] += count

# --- (باقي دوال الفحص والـ Extracts بقيت كما هي تماماً بدون أي تغيير) ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_start = types.InlineKeyboardButton("⚡ Start Checker", callback_data="start_checker")
    btn_premium = types.InlineKeyboardButton("💎 Buy Premium ($15/Month)", callback_data="buy_premium")
    btn_account = types.InlineKeyboardButton("👤 My Account", callback_data="my_account")
    markup.add(btn_start, btn_premium, btn_account)

    chat_id = message.chat.id
    today = date.today()
    
    if chat_id == OWNER_ID:
        status_text = "👑 Owner (Unlimited)"
    else:
        used = user_usage.get(chat_id, {}).get("count", 0) if user_usage.get(chat_id, {}).get("date") == today else 0
        status_text = f"👤 Free ({used}/2500 lines today)"

    text = (
        "⚡ **r1livk Checker Pro (Catalog Mode)** ⚡\n\n"
        "Welcome to the ultimate account checking bot.\n"
        f"Your Status: {status_text}\n\n"
        "Features:\n"
        "• Xbox Game Pass & Subscriptions\n"
        "• DisplayCatalog & Inventory Games List\n"
        "• Gamertag & Gamerscore\n"
        "• Minecraft Entitlements\n"
        "• Anti-2FA Browser Headers\n\n"
        "Click the button below to start checking your combo files!"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if call.data == "start_checker":
        # ... (نفس الكود السابق للـ start_checker) ...
        pass
    
    elif call.data == "buy_premium":
        bot.answer_callback_query(call.id, "💎 Premium Plan: $15/Month\nBenefits: Unlimited checking 24/7!\nContact: @r1livk", show_alert=True)

    elif call.data == "my_account":
        today = date.today()
        if chat_id == OWNER_ID:
            bot.answer_callback_query(call.id, "Status: Owner (Unlimited Access)", show_alert=True)
        else:
            used = user_usage.get(chat_id, {}).get("count", 0) if user_usage.get(chat_id, {}).get("date") == today else 0
            bot.answer_callback_query(call.id, f"Current Status: Free\nUsed Today: {used}/2500 lines", show_alert=True)
