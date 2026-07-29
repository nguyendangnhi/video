import os
import re
import time
import random
import logging
import yt_dlp
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- LOGGING ---
logger = logging.getLogger(__name__)

YT_UA = os.getenv("YT_UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
YT_COOKIES = os.getenv("YT_COOKIES", "")

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.2478.51',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 13; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 OPR/109.0.0.0'
]

def get_random_ua():
    return random.choice(USER_AGENTS)

def download_video(video_id):
    """Tải video chất lượng tốt nhất dùng yt-dlp với cơ chế retry và giả lập client"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    path = f"temp_video_{video_id}.mp4"

    client_combos = [['android', 'web'], ['ios', 'mweb'], ['tv', 'web']]
    
    for i, clients in enumerate(client_combos):
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': path,
            'quiet': True,
            'user_agent': get_random_ua(), # Sử dụng UA ngẫu nhiên
            'http_headers': {'Cookie': YT_COOKIES},
            'nocheckcertificate': True,
            'retry_sleep': 20,
            'n_retries': 5,
            'fragment_retries': 10,
            'extractor_args': {'youtube': {'player_client': clients}}
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                if os.path.exists(path):
                    return path
        except Exception as e:
            if "Sign in to confirm you're not a bot" in str(e):
                logger.warning(f"⚠️ YouTube chặn bot (Lần {i+1}). Đang thử đổi client...")
                time.sleep(random.uniform(5, 10))
            else:
                logger.error(f"❌ Lỗi tải video {video_id}: {e}")
                break
    return None

def crawl_youtube_for_page(config, ma_affiliate, ua_string, session, check_exists_fn, save_video_fn, clean_title_fn, target_goal=90, shopee_page=None):
    """Cào video từ YouTube, lấy link thô để sau này xử lý Excel"""
    target_page_id = config['id_page_dich']
    nguon_raw = config.get('link_nguon', '').strip()
    if not nguon_raw: return False
    
    keywords = [k.strip() for k in nguon_raw.split(',')]
    random.shuffle(keywords)
    
    shopee_regex = r'(https?://(?:shope\.ee|s\.shopee\.vn|shopee\.vn|vn\.shp\.ee|affiliate\.shopee\.vn|mycollection\.shop)/[a-zA-Z0-9.\-_]+)'
    found_count = 0

    for selected in keywords:
        if found_count >= target_goal: break
        logger.info(f"🔍 Đang cào từ khóa: '{selected}' (Mục tiêu: {found_count}/{target_goal})")

        max_pages = 8
        page_size = random.randint(30, 50)
        is_yt_blocked = False

        for page in range(max_pages):
            if found_count >= target_goal or is_yt_blocked: break

            start_idx = page * page_size + 1
            end_idx = start_idx + page_size - 1

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'user_agent': get_random_ua(), # Sử dụng UA ngẫu nhiên
                'http_headers': {'Cookie': YT_COOKIES},
                'nocheckcertificate': True,
            }

            try:
                search_query = selected if "youtube.com" in selected else f"ytsearch{end_idx}:{selected} #shorts"
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    search_results = ydl.extract_info(search_query, download=False)
                    entries = search_results.get('entries', [])
                    if not entries: break

                    current_entries = entries[start_idx-1:] if not "youtube.com" in selected else entries

                    for entry in current_entries:
                        if not entry or found_count >= target_goal or is_yt_blocked: continue
                        v_id = entry['id']
                        if check_exists_fn(v_id, target_page_id): continue

                        try:
                            # 1. Trích xuất thông tin
                            video_info = ydl.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
                            v_desc = video_info.get('description') or ''
                            all_text = v_desc

                            # 2. Check comments
                            if not re.search(shopee_regex, all_text):
                                cmt_opts = ydl_opts.copy()
                                cmt_opts.update({'getcomments': True, 'max_comments': 10})
                                with yt_dlp.YoutubeDL(cmt_opts) as ydl_cmt:
                                    video_info_cmt = ydl_cmt.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
                                    v_comments = video_info_cmt.get('comments') or []
                                    all_text += "\n" + "\n".join([c.get('text', '') for c in v_comments if c.get('text')])

                            # 3. Phân tích link thô
                            found_pairs = []
                            seen_links = set()
                            for line in all_text.split('\n'):
                                m = re.search(shopee_regex, line)
                                if m:
                                    link = m.group(1)
                                    if link in seen_links or "an_redir" in link: continue
                                    title_part = re.sub(r'^[\d\.\-\s]+', '', line.split(link)[0].strip()).strip(':- ').strip()
                                    found_pairs.append({'title': title_part or "Sản phẩm review", 'url': link})
                                    seen_links.add(link)
                                    if len(found_pairs) >= 7: break

                            if not found_pairs:
                                logger.info(f"      ⏭️ Bỏ qua {v_id}: Không tìm thấy link Shopee.")
                                save_video_fn(v_id, target_page_id, "Không có link Shopee", "BLACKLIST")
                                continue

                            # 4. Lưu link thô (Gom lại thành string Tiêu đề|Link)
                            aff_list = [f"{p['title']}|{p['url']}" for p in found_pairs]

                            # 5. Lưu video vào trạng thái raw để chờ Excel
                            save_video_fn(v_id, target_page_id, clean_title_fn(video_info.get('title', '')), "\n".join(aff_list))
                            found_count += 1
                            logger.info(f"      ✅ Đã nạp thành công: {v_id} (Tổng cộng: {found_count})")
                            time.sleep(random.uniform(5, 10))

                        except Exception as e:
                            err = str(e)
                            if any(msg in err for msg in ["age-restricted", "private video", "removed by the uploader"]):
                                save_video_fn(v_id, target_page_id, "Video không khả dụng", "BLACKLIST")
                            elif "Sign in to confirm you're not a bot" in err:
                                is_yt_blocked = True; break
                            else: continue

            except Exception as e:
                logger.error(f"⚠️ Lỗi YouTube: {e}")
                break

    return found_count > 0
