import os
import re
import time
import random
import logging
import yt_dlp
import requests
from urllib.parse import quote
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- LOGGING ---
logger = logging.getLogger(__name__)

YT_PO_TOKEN = os.getenv("YT_PO_TOKEN", "")

# Danh sách User-Agent đồ sộ phân loại theo thiết bị để tàng hình
UA_POOL = {
    'web': [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 OPR/110.0.0.0'
    ],
    'ios': [
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 15_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.7.1 Mobile/15E148 Safari/604.1'
    ],
    'android': [
        'Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.52 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.52 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.179 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.40 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 11; SM-A515F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.119 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36'
    ]
}

def get_smart_ua(client_type):
    if client_type in UA_POOL:
        return random.choice(UA_POOL[client_type])
    return random.choice(UA_POOL['web'])

def get_random_ua():
    """Hàm bổ trợ để tương thích với app.py"""
    return get_smart_ua('web')

def download_video(video_id):
    """Tải video chất lượng tốt nhất với cơ chế tàng hình tối thượng"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    path = f"temp_video_{video_id}.mp4"

    # Xoay vòng client chuyên sâu - Thêm nhiều combo để tăng tỉ lệ thành công
    client_combos = [
        {'clients': ['ios', 'android_embedded'], 'ua_type': 'ios'},
        {'clients': ['android', 'web'], 'ua_type': 'android'},
        {'clients': ['tv', 'web'], 'ua_type': 'web'},
        {'clients': ['web', 'mweb'], 'ua_type': 'web'}
    ]
    
    for i, combo in enumerate(client_combos):
        clients = combo['clients']
        
        # Cấu hình YouTube Extractor
        yt_args = {'player_client': clients}
        if YT_PO_TOKEN:
            yt_args['po_token'] = [f'{clients[0]}+{YT_PO_TOKEN}']

        ydl_opts = {
            # Linh hoạt: Lấy video tốt nhất + audio tốt nhất, không quan tâm định dạng gốc là gì
            'format': 'bestvideo*+bestaudio/best',
            # Sau khi tải xong, tự động gộp (remux) vào file .mp4 để Meta hỗ trợ tốt nhất
            'merge_output_format': 'mp4',
            'outtmpl': path,
            'quiet': True,
            'no_warnings': True,
            'user_agent': get_smart_ua(combo['ua_type']),
            'referer': 'https://www.google.com/',
            'nocheckcertificate': True,
            'retry_sleep': 5,
            'n_retries': 3,
            'fragment_retries': 5,
            'ignore_no_formats_error': True, # Bỏ qua lỗi định dạng để thử combo tiếp theo
            'extractor_args': {'youtube': yt_args},
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        }

        try:
            logger.info(f"   📥 Thử tải {video_id} (Client: {clients}) - IP Gốc")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                if os.path.exists(path):
                    # Kiểm tra file có dung lượng không (tránh file 0 byte)
                    if os.path.getsize(path) > 1000:
                        return path
                    else:
                        try: os.remove(path)
                        except: pass
        except Exception as e:
            err_msg = str(e)
            if any(m in err_msg for m in ["Sign in", "DRM protected", "403", "No video formats", "Requested format"]):
                logger.warning(f"⚠️ YouTube chặn Bot (Lần {i+1}). Đang đổi Client...")
                time.sleep(random.uniform(2, 5))
            else:
                logger.error(f"❌ Lỗi tải video {video_id}: {err_msg[:100]}...")
                continue
    return None

def crawl_youtube_for_page(config, ua_string, session, check_exists_fn, save_video_fn, clean_title_fn, target_goal=90, shopee_page=None, stop_time=None):
    """Cào video từ YouTube dùng IP Gốc và tàng hình"""
    target_page_id = config['id_page_dich']
    nguon_raw = config.get('link_nguon', '').strip()
    if not nguon_raw: return False
    
    keywords = [k.strip() for k in nguon_raw.split(',')]
    random.shuffle(keywords)
    
    shopee_regex = r'(https?://(?:shope\.ee|s\.shopee\.vn|shopee\.vn|vn\.shp\.ee|affiliate\.shopee\.vn|mycollection\.shop)/[a-zA-Z0-9.\-_]+)'
    found_count = 0

    for selected in keywords:
        if found_count >= target_goal or (stop_time and time.time() > stop_time): break
        logger.info(f"🔍 Nguồn: '{selected}' (Mục tiêu: {found_count}/{target_goal})")

        is_url = "youtube.com" in selected or "youtu.be" in selected
        max_pages = 1 if is_url else 5
        is_yt_blocked = False

        for page in range(max_pages):
            if found_count >= target_goal or is_yt_blocked or (stop_time and time.time() > stop_time): break

            yt_args = {'player_client': ['web']}
            if YT_PO_TOKEN:
                yt_args['po_token'] = [f'web+{YT_PO_TOKEN}']

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'user_agent': get_smart_ua('web'),
                'referer': 'https://www.google.com/',
                'nocheckcertificate': True,
                'extractor_args': {'youtube': yt_args}
            }

            try:
                search_query = selected if is_url else f"ytsearch50:{selected} #shorts"
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    search_results = ydl.extract_info(search_query, download=False)
                    if not search_results: break
                    entries = search_results.get('entries', []) if 'entries' in search_results else [search_results]

                    for entry in entries:
                        if not entry or found_count >= target_goal or is_yt_blocked or (stop_time and time.time() > stop_time): continue
                        v_id = entry.get('id')
                        if not v_id or check_exists_fn(v_id, target_page_id): continue

                        # Thử lấy chi tiết bằng nhiều client nếu một cái lỗi
                        detail_success = False
                        # Thứ tự ưu tiên: ios (thường bypass tốt), android, web
                        metadata_clients = [
                            {'name': ['ios'], 'ua': 'ios'},
                            {'name': ['android'], 'ua': 'android'},
                            {'name': ['web'], 'ua': 'web'}
                        ]

                        for m_client in metadata_clients:
                            try:
                                m_yt_args = {'player_client': m_client['name']}
                                if YT_PO_TOKEN:
                                    m_yt_args['po_token'] = [f"{m_client['name'][0]}+{YT_PO_TOKEN}"]

                                detail_opts = {
                                    'quiet': True,
                                    'no_warnings': True,
                                    'extract_flat': False, 
                                    'getcomments': True, 
                                    'max_comments': 10,
                                    'user_agent': get_smart_ua(m_client['ua']),
                                    'extractor_args': {'youtube': m_yt_args},
                                    'referer': f"https://www.youtube.com/results?search_query={quote(selected)}",
                                    'nocheckcertificate': True,
                                    # Cào metadata: Dùng tham số linh hoạt nhất và bỏ qua lỗi định dạng
                                    'format': 'bestvideo*+bestaudio/best',
                                    'ignore_no_formats_error': True
                                }

                                with yt_dlp.YoutubeDL(detail_opts) as ydl_detail:
                                    video_info = ydl_detail.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
                                    v_desc = video_info.get('description') or ''
                                    v_comments = video_info.get('comments') or []
                                    all_text = v_desc + "\n" + "\n".join([c.get('text', '') for c in v_comments if c.get('text')])
                                    
                                    # Tìm link Shopee
                                    found_pairs = []
                                    seen_links = set()
                                    for line in all_text.split('\n'):
                                        m = re.search(shopee_regex, line)
                                        if m:
                                            link = m.group(1)
                                            if link in seen_links or "an_redir" in link: continue
                                            title_part = re.sub(r'^[\d\.\-\s]+', '', line.split(link)[0].strip()).strip(':- ').strip()
                                            found_pairs.append({'title': title_part or "Sản phẩm", 'url': link})
                                            seen_links.add(link)
                                            if len(found_pairs) >= 5: break

                                    if not found_pairs:
                                        save_video_fn(v_id, target_page_id, "Không có link Shopee", "BLACKLIST")
                                    else:
                                        save_video_fn(v_id, target_page_id, clean_title_fn(video_info.get('title', '')), "\n".join([f"{p['title']}|{p['url']}" for p in found_pairs]))
                                        found_count += 1
                                        logger.info(f"      ✅ Đã nạp: {v_id} ({found_count})")
                                        time.sleep(random.uniform(6, 10))
                                    
                                    detail_success = True
                                    break # Thoát vòng lặp client nếu thành công

                            except Exception as e:
                                err_str = str(e)
                                if "Sign in" in err_str:
                                    is_yt_blocked = True
                                    break
                                logger.warning(f"      ⚠️ Lỗi metadata video {v_id} với client {m_client['name']}: {err_str[:100]}...")
                                continue
                        
                        if is_yt_blocked: break
            except Exception as e:
                logger.error(f"⚠️ Lỗi cào: {e}")
                break
    return found_count > 0
