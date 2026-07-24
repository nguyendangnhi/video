import os
import requests
import time
import re
import json
import random
import logging
import glob
import subprocess
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from supabase import create_client
from dotenv import load_dotenv

# --- CẤU HÌNH LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- CẤU HÌNH & KHỞI TẠO ---
load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPad; CPU OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 13; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 OPR/105.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Vivaldi/6.5.3206.63',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0'
]

def get_random_ua():
    return random.choice(USER_AGENTS)

DEFAULT_USER_AGENT = get_random_ua()

# --- CÁC HÀM TIỆN ÍCH ---
def cleanup_temp_files():
    """Dọn dẹp các file video tạm và file rác từ yt-dlp"""
    patterns = ["temp_video_*.mp4", "*.part", "*.temp", "*.ytdl"]
    for pattern in patterns:
        files = glob.glob(pattern)
        for f in files:
            try:
                os.remove(f)
                logger.info(f"🗑️ Đã xóa file tạm: {f}")
            except Exception as e:
                logger.error(f"⚠️ Không thể xóa {f}: {e}")

def safe_execute(query, max_retries=3):
    """Thực thi query Supabase với cơ chế retry khi gặp lỗi mạng"""
    for attempt in range(max_retries):
        try:
            return query.execute()
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 3
                logger.warning(f"⚠️ Lỗi Supabase (Lần {attempt+1}): {e}. Thử lại sau {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"❌ Thất bại sau {max_retries} lần thử.")
                raise e

def spin(text):
    """Hàm xử lý Spintax: {A|B|C} -> Chọn ngẫu nhiên A hoặc B hoặc C"""
    while "{" in text and "}" in text:
        start = text.rfind("{")
        end = text.find("}", start)
        if end == -1: break
        content = text[start + 1:end]
        chosen = random.choice(content.split("|"))
        text = text[:start] + chosen + text[end + 1:]
    return text

HASHTAG_POOLS = [
    "✨ #review #shopeehaul #muataishopee #xuhuong",
    "🔥 #reviewlamdep #gocreview #shopeevn #trending",
    "🎁 #unbox #reviewthongminh #dogiadung #tienich",
    "🛍️ #shopeecheck #sale #muasắm #fyp",
    "✅ #meovat #cuocsong #ReviewThucTe #hot"
]

def clean_title(title):
    """Làm sạch tiêu đề: Xóa ngoặc, cập nhật năm, thêm hashtag xoay vòng"""
    if not title: return f"Video Review {random.choice(HASHTAG_POOLS)}"
    
    # 1. Xóa các đoạn trong ngoặc (ví dụ: (Full), [Review]...)
    title = re.sub(r'[\(\[][^()]*[\)\]]', '', title)
    
    # 2. Cập nhật các năm cũ thành năm hiện tại
    now = datetime.now()
    current_year = now.year
    title = re.sub(r'\b20\d{2}\b', lambda m: str(current_year) if int(m.group(0)) < current_year else m.group(0), title)
    
    # 3. Xóa hashtag cũ của YouTube
    title = re.sub(r'#\S+', '', title)
    
    # 4. Xóa các từ khóa YouTube phổ biến/thừa
    bad_words = ['shorts', 'video', 'nha', 'đây', 'tại đây']
    for word in bad_words:
        title = re.sub(f'(?i)\\b{word}\\b', '', title)

    # 5. Dọn dẹp khoảng trắng thừa
    title = re.sub(r'\s+', ' ', title).strip()
    title = title.strip('-_ ')
    
    # 6. Thêm bộ hashtag xoay vòng
    hashtags = random.choice(HASHTAG_POOLS)
    return f"{title.capitalize()} {hashtags}"

def process_video_spinning(input_path, page_name="Review Pro"):
    """Sử dụng ffmpeg để 'phẫu thuật' video: Bỏ sạch nền mờ, ép về Full màn hình 9:16 chuẩn Reels"""
    output_path = input_path.replace(".mp4", "_processed.mp4")
    text_file = None
    try:
        # 1. Phân tích kích thước gốc
        cmd_probe = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'json', input_path]
        probe_res = subprocess.run(cmd_probe, capture_output=True, text=True, timeout=15)
        probe_data = json.loads(probe_res.stdout)
        width = int(probe_data['streams'][0]['width'])
        height = int(probe_data['streams'][0]['height'])
        
        logger.info(f"   📊 File gốc: {width}x{height}")

        # 2. Quét tìm lõi nội dung thực tế (Bỏ qua các lớp nền mờ/rác biên)
        # Tăng limit lên 90 để lọc sạch mọi loại padding
        logger.info("   🔍 Đang quét tìm lõi video (Lọc sạch nền mờ/rác)...")
        vf_detect = "edgedetect=low=0.1:high=0.2,cropdetect=90:16:0"
        cmd_detect = ['ffmpeg', '-i', input_path, '-t', '15', '-vf', vf_detect, '-f', 'null', '-']
        detect_res = subprocess.run(cmd_detect, capture_output=True, text=True, timeout=45)
        crops = re.findall(r'crop=(\d+):(\d+):(\d+):(\d+)', detect_res.stderr)
        
        d_w, d_h, d_x, d_y = width, height, 0, 0
        if crops:
            d_w, d_h, d_x, d_y = map(int, crops[-1])
            logger.info(f"   📏 Lõi nội dung: {d_w}x{d_h} tại ({d_x},{d_y})")

        # 3. Thông số lách bản quyền
        speed = random.uniform(1.03, 1.05)
        pts = 1 / speed
        text_file = f"logo_{random.getrandbits(32)}.txt"
        with open(text_file, "w", encoding="utf-8") as f: f.write(page_name)
        font_cfg = "font='Arial'" if os.name == 'nt' else "fontfile='/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'"
        logo_filter = f"drawtext={font_cfg}:textfile='{text_file}':x=w-tw-35:y=35:fontsize=32:fontcolor=white:borderw=2.5:bordercolor=black@0.9"

        # 4. THỰC THI PHẪU THUẬT: ÉP BUỘC FULL MÀN HÌNH 9:16
        # Bước 1: Cắt lấy lõi đã quét được (loại bỏ nền mờ gốc)
        # Bước 2: Phóng lớn (scale) để lấp đầy 1080x1920 (không để lại bất kỳ khoảng trống nào)
        # Bước 3: Crop lại đúng 1080x1920 để loại bỏ phần thừa nếu lõi là khung ngang
        logger.info("   🎯 Chế độ: ÉP BUỘC FULL MÀN HÌNH (Bỏ sạch nền mờ)")
        vf_filters = (
            f"crop={d_w}:{d_h}:{d_x}:{d_y},"
            f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"noise=alls=1:allf=t,eq=brightness=0.03:saturation=1.15:contrast=1.05,"
            f"unsharp=5:5:1.0:5:5:0.0,{logo_filter},setpts={pts}*PTS"
        )

        # 5. Thực thi FFmpeg
        cmd = ['ffmpeg', '-y', '-i', input_path, '-vf', vf_filters, '-af', f"atempo={speed}",
               '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '26', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-b:a', '128k', output_path]
        subprocess.run(cmd, capture_output=True, check=True, timeout=2000)

        if os.path.exists(text_file): os.remove(text_file)
        if os.path.exists(output_path):
            os.remove(input_path); os.rename(output_path, input_path)
            return True
    except Exception as e:
        logger.error(f"⚠️ Lỗi xử lý video: {e}")
        if text_file and os.path.exists(text_file): os.remove(text_file)
    return False

# --- LOGIC CẤU HÌNH & DB ---
def get_config_from_db():
    """Lấy cấu hình bot từ Supabase"""
    try:
        res = safe_execute(supabase.table("cau_hinh_bot").select("ma_shopee").limit(1))
        if res.data:
            conf = res.data[0]
            ma_aff = str(conf.get('ma_shopee', '17394180064')).strip()
            return ma_aff, DEFAULT_USER_AGENT
    except Exception as e:
        logger.error(f"⚠️ Lỗi đọc DB: {e}")
    return "17394180064", DEFAULT_USER_AGENT

def check_video_exists(video_id, page_id):
    """Kiểm tra video đã được xử lý cho Page này chưa"""
    try:
        res = safe_execute(supabase.table("lich_su_video").select("id").eq("id_video", str(video_id)).eq("id_page", str(page_id)))
        return len(res.data) > 0
    except: return False

def save_pending_video(video_id, page_id, tieu_de, link_aff):
    """Lưu video vào hàng đợi để đăng sau"""
    try:
        data = {
            "id_video": str(video_id),
            "id_page": str(page_id),
            "tieu_de": str(tieu_de),
            "trang_thai": "pending",
            "link_affiliate": link_aff
        }
        safe_execute(supabase.table("lich_su_video").insert(data))
    except Exception as e:
        logger.error(f"⚠️ Lỗi lưu video {video_id}: {e}")

def update_posted_status(video_id, page_id, video_fb_id):
    """Cập nhật trạng thái sau khi đã đăng bài thành công"""
    try:
        data = {
            "trang_thai": "posted",
            "video_fb_id": video_fb_id,
            "thoi_gian_dang": datetime.now(timezone.utc).isoformat()
        }
        safe_execute(supabase.table("lich_su_video").update(data)\
            .eq("id_video", str(video_id))\
            .eq("id_page", str(page_id)))
    except Exception as e:
        logger.error(f"⚠️ Lỗi cập nhật status cho video {video_id}: {e}")

# --- LOGIC AFFILIATE ---
def tao_link_affiliate_moi(url_goc, ma_affiliate, session):
    """Chuyển đổi link Shopee sang link Affiliate Redirection (an_redir) chuẩn và kiểm tra link sống"""
    try:
        # 1. Delay ngẫu nhiên: Tránh việc gửi yêu cầu quá đều đặn như máy
        time.sleep(random.uniform(3.0, 6.0))
        
        # 2. Xoay User-Agent: Mỗi lần check dùng một trình duyệt khác nhau để tránh bị nhận diện bot
        headers = {'User-Agent': get_random_ua()}
        
        res = session.get(url_goc, headers=headers, allow_redirects=True, timeout=15)
        
        # 3. Kiểm tra mã trạng thái HTTP (Nếu bị 403/429 là đã bị Shopee soi)
        if res.status_code == 429:
            logger.error("   ⛔ Shopee phát hiện Bot (429)! Đang nghỉ 30s...")
            time.sleep(30)
            return None
        
        if res.status_code != 200:
            logger.warning(f"   ❌ Link không truy cập được (HTTP {res.status_code}): {url_goc}")
            return None
            
        final_url = res.url

        # 4. Kiểm tra nếu bị redirect về trang chủ (sản phẩm đã chết)
        if final_url.split('?')[0].strip('/') == "https://shopee.vn":
            logger.warning(f"   ❌ Link đã chết hoặc hết hạn (Bị redirect về trang chủ): {url_goc}")
            return None

        # 3. Xử lý link MyCollection (nếu có)
        if "mycollection.shop" in final_url:
            return final_url

        # 4. Tìm ID sản phẩm để xác nhận đây là link sản phẩm hợp lệ
        match = (re.search(r'i\.(\d+)\.(\d+)', final_url) or 
                 re.search(r'product/(\d+)/(\d+)', final_url) or 
                 re.search(r'shopee\.vn/[^/]+/(\d+)/(\d+)', final_url))
        
        if match:
            s_id, i_id = match.groups()
            base_url = f"https://shopee.vn/product/{s_id}/{i_id}"
            encoded_url = quote(base_url)
            # Trả về link affiliate
            return f"https://s.shopee.vn/an_redir?origin_link={encoded_url}&affiliate_id={ma_affiliate}&sub_id=fb_reels"
        else:
            logger.warning(f"   ❌ Không tìm thấy ID sản phẩm (Link không hợp lệ): {final_url}")
            return None
    except Exception as e:
        logger.error(f"   ⚠️ Lỗi khi kiểm tra link {url_goc}: {e}")
    return None

# --- LOGIC CÀO YOUTUBE ---
def crawl_youtube_for_page(config, ma_aff, ua_string, session):
    """Cào video mới nhất từ YouTube với cơ chế tự động nhảy trang (Pagination)"""
    target_page_id = config['id_page_dich']
    nguon_raw = config.get('link_nguon', '').strip()
    if not nguon_raw: return False
    
    keywords = [k.strip() for k in nguon_raw.split(',')]
    selected = random.choice(keywords)
    
    shopee_regex = r'(https?://(?:shope\.ee|s\.shopee\.vn|shopee\.vn|vn\.shp\.ee|affiliate\.shopee\.vn|mycollection\.shop)/[a-zA-Z0-9.\-_]+)'
    found_count = 0
    max_pages = 10 # Tối đa nhảy 10 trang (mỗi trang 20 video) -> Tổng 200 video
    page_size = 20

    import yt_dlp
    
    for page in range(max_pages):
        start_idx = (page * page_size) + 1
        end_idx = start_idx + page_size - 1
        
        logger.info(f"📡 Trang {page+1}: Quét video từ {start_idx} đến {end_idx} cho {selected}...")
        
        search_query = selected if "youtube.com" in selected else f"ytsearch{end_idx}:{selected} #shorts"
        
        ydl_opts = {
            'extract_flat': 'in_playlist',
            'playliststart': start_idx,
            'playlistend': end_idx,
            'quiet': True,
            'no_warnings': True,
            'user_agent': ua_string,
            'getcomments': True,
            'max_comments': 15,
            'sleep_interval': 3,
            'max_sleep_interval': 8,
            'match_filter': lambda info, *, incomplete: 'Video too long' if info.get('duration') and info.get('duration') > 600 else None,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web'],
                }
            }
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_results = ydl.extract_info(search_query, download=False)
                entries = search_results.get('entries', [])
                
                if not entries:
                    logger.warning("   ⚠️ Không còn video nào để quét.")
                    break

                new_videos_in_page = 0
                for entry in entries:
                    if not entry: continue
                    
                    v_id = entry['id']
                    if check_video_exists(v_id, target_page_id): 
                        continue

                    new_videos_in_page += 1
                    try:
                        video_info = ydl.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
                        v_desc = video_info.get('description') or ''
                        v_comments = video_info.get('comments') or []
                        
                        comment_text = " ".join([c.get('text', '') for c in v_comments if c.get('text')])
                        combined_content = v_desc + " " + comment_text
                        raw_links = re.findall(shopee_regex, combined_content)
                        
                        if raw_links:
                            unique_links = []
                            for l in raw_links:
                                if l not in unique_links: unique_links.append(l)

                            aff_list = []
                            for l in unique_links[:5]:
                                aff_link = tao_link_affiliate_moi(l, ma_aff, session)
                                if aff_link: aff_list.append(aff_link)
                            
                            if not aff_list: continue

                            all_links_str = "\n".join(aff_list)
                            cleaned_tieu_de = clean_title(video_info.get('title', ''))
                            save_pending_video(v_id, target_page_id, cleaned_tieu_de, all_links_str)
                            
                            found_count += 1
                            logger.info(f"   ✅ Đã nạp mới: {v_id}")
                            
                            if found_count >= 10: return True
                    except Exception as e:
                        logger.warning(f"   ⚠️ Lỗi video {v_id}: {e}")
                        continue

                if new_videos_in_page == 0:
                    wait_page = random.uniform(5, 10)
                    logger.info(f"   ⏭️ Trang {page+1} toàn video cũ. Nghỉ {wait_page:.1f}s trước khi sang trang {page+2}...")
                    time.sleep(wait_page)
                    
        except Exception as e:
            logger.error(f"⚠️ Lỗi cào trang {page+1}: {e}")
            break

    return found_count > 0

# --- TẢI & ĐĂNG VIDEO ---
def download_video(video_id, ua_string):
    """Tải video chất lượng tốt nhất dùng yt-dlp với cơ chế retry và giả lập client"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    path = f"temp_video_{video_id}.mp4"
    
    # Danh sách các tổ hợp client để thử nếu gặp lỗi bot
    client_combos = [
        ['android', 'web'],
        ['ios', 'mweb'],
        ['tv', 'web']
    ]
    
    import yt_dlp
    for i, clients in enumerate(client_combos):
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': path,
            'quiet': True,
            'user_agent': get_random_ua(), # Xoay UA mỗi lần thử
            'nocheckcertificate': True,
            'retry_sleep': 20,
            'n_retries': 5,
            'fragment_retries': 10,
            'concurrent_fragment_downloads': 1,
            'extractor_args': {
                'youtube': {
                    'player_client': clients,
                }
            }
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                if os.path.exists(path):
                    return path
        except Exception as e:
            error_msg = str(e)
            if "Sign in to confirm you're not a bot" in error_msg:
                logger.warning(f"⚠️ YouTube chặn bot (Lần {i+1}). Đang thử đổi client...")
                time.sleep(random.uniform(5, 10))
            else:
                logger.error(f"❌ Lỗi tải video {video_id}: {e}")
                break
    return None

def post_to_facebook(video_path, title, l_aff_str, page_token, session):
    """Đăng video lên Facebook Reels sử dụng Direct Upload (tải lên 1 lần duy nhất)"""
    url = "https://graph-video.facebook.com/v21.0/me/videos"
    caption = f"{title}\n\n👇 Xem link mua sản phẩm ở phần bình luận nhé!"

    try:
        logger.info(f"   📤 Đang tải video lên Facebook (Direct Upload)...")
        with open(video_path, 'rb') as f:
            files = {'source': f}
            data = {
                'description': caption,
                'access_token': page_token
            }
            # Sử dụng timeout lớn vì file có thể nặng
            response = session.post(url, data=data, files=files, timeout=600)
            res = response.json()

        if 'id' in res:
            v_fb_id = res['id']
            logger.info(f"✅ Đã tải video lên FB thành công (ID: {v_fb_id})")
            
            # 4. Nghỉ một chút để FB xử lý video rồi đăng bình luận
            # Tôi để 45-60s để đảm bảo video kịp "live" trên server FB, tránh lỗi comment khi video chưa sẵn sàng.
            wait_time = random.uniform(45, 60)
            logger.info(f"⏳ Đợi {wait_time:.1f}s để FB xử lý video rồi đăng bình luận...")
            time.sleep(wait_time)
            
            # 5. Đăng bình luận với cơ chế retry
            links = l_aff_str.split('\n')
            msg_header = spin("{✨|🔥|✅|🎯|💎} {Link mua|Sản phẩm|Món này|Link các món} {ở đây|tại đây} {nha|nhé cả nhà|nè}:\n\n")
            msg_body = "\n".join([f"{spin('{🔗|📍|👉|🏷️|📌}')} Món {i+1}: {l}" for i, l in enumerate(links)])
            msg_footer = spin("\n\n{🛍️|🛒|🎁|🎀|✨} {Ghé|Vào} shop {xem|tham khảo} thêm {nhiều mẫu|các món|đồ} {xinh|hot|đẹp|xịn} {nha|nhé|nè}! {💖|🌟|🔥|🌈}")
            
            final_msg = msg_header + msg_body + msg_footer
            
            comment_success = False
            for attempt in range(3):
                c_res = session.post(f"https://graph.facebook.com/v21.0/{v_fb_id}/comments",
                                     data={'message': final_msg, 'access_token': page_token})
                if c_res.status_code == 200:
                    logger.info(f"💬 Đã đăng bình luận thành công (Lần {attempt+1}).")
                    comment_success = True
                    break
                else:
                    logger.warning(f"⚠️ Thử lại đăng bình luận ({attempt+1}/3)... Lỗi: {c_res.text}")
                    time.sleep(15) # Đợi 15s trước khi thử lại
            
            if not comment_success:
                logger.error(f"❌ Thất bại hoàn toàn khi đăng bình luận cho video {v_fb_id}")
            
            return v_fb_id
        else:
            logger.error(f"❌ Lỗi tải video lên FB: {res}")
    except Exception as e:
        logger.error(f"⚠️ Lỗi nghiêm trọng khi đăng Facebook: {e}")
    return None

# --- LUỒNG CHÍNH ---
def main():
    logger.info(f"--- BOT BẮT ĐẦU CHẠY: {datetime.now().strftime('%H:%M:%S')} ---")
    cleanup_temp_files()
    ma_aff, ua = get_config_from_db()
    
    with requests.Session() as shared_session:
        # Lấy danh sách Page cấu hình
        pages = safe_execute(supabase.table("cau_hinh_page").select("*").order("id")).data

        # BƯỚC 1: KIỂM TRA KHO (Nạp thêm video nếu thiếu)
        logger.info("🧐 Đang kiểm tra kho video của các Page...")
        crawls_done = 0
        for config in pages:
            # Giới hạn chỉ cào tối đa cho 2 Page mỗi phiên để tránh YouTube soi
            if crawls_done >= 2:
                break
                
            target_id = config['id_page_dich']
            # Kiểm tra xem còn video pending không
            res = safe_execute(supabase.table("lich_su_video")
                               .select("id", count="exact")
                               .eq("id_page", str(target_id))
                               .eq("trang_thai", "pending")
                               .limit(1))
            
            pending_count = res.count if res.count is not None else 0
            
            if pending_count == 0:
                logger.info(f"   ℹ️ Page {config.get('ten_page')} hết video. Đang đi cào nạp kho...")
                if crawl_youtube_for_page(config, ma_aff, ua, shared_session):
                    crawls_done += 1
            else:
                logger.info(f"   ✅ Page {config.get('ten_page')} vẫn còn {pending_count} video chờ.")

        # BƯỚC 2: TIẾN HÀNH ĐĂNG BÀI (Chỉ đăng tối đa 2 video mỗi phiên để an toàn)
        posts_done = 0
        logger.info("🎬 Bắt đầu luồng đăng bài...")
        
        for config in pages:
            if posts_done >= 2: 
                logger.info("🏁 Đã hoàn thành hạn mức đăng bài của phiên này (2 bài).")
                break
            
            target_id = config['id_page_dich']
            ten_page = config.get('ten_page') or "Không tên"
            token = config.get('token_fb')
            if not token: continue

            # Kiểm tra thời gian nghỉ giữa 2 bài đăng (tránh spam - ít nhất 6 tiếng)
            try:
                last = safe_execute(supabase.table("lich_su_video").select("thoi_gian_dang").eq("id_page", target_id).eq("trang_thai", "posted").order("thoi_gian_dang", desc=True).limit(1)).data
                if last and last[0]['thoi_gian_dang']:
                    l_time = datetime.fromisoformat(last[0]['thoi_gian_dang'].replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) - l_time < timedelta(hours=6):
                        logger.info(f"   ⏳ Page {ten_page} đang trong thời gian nghỉ (Chưa đủ 6 tiếng).")
                        continue
            except: pass

            logger.info(f"🚀 Đang xử lý đăng bài cho Page: {ten_page}")
            
            # Lấy 1 video pending để đăng
            res = safe_execute(supabase.rpc("lay_video_pending", {"p_id_page": str(target_id)}))
            
            if res.data:
                item = res.data[0]
                vid_id = item['id_video']
                l_aff = item['link_affiliate']
                tieu_de_sach = item.get('tieu_de', 'Video Review')
                
                path = None
                try:
                    # 3. Tải video
                    path = download_video(vid_id, ua)
                    if path:
                        # 4. Spin video để lách bản quyền & chuyển sang dọc nếu cần
                        success = process_video_spinning(path, ten_page)

                        if success:
                            # 5. Đăng Facebook
                            v_fb_id = post_to_facebook(path, tieu_de_sach, l_aff, token, shared_session)
                            if v_fb_id:
                                update_posted_status(vid_id, target_id, v_fb_id)
                                posts_done += 1
                                logger.info(f"✅ Hoàn tất đăng video {vid_id}")
                                
                                if posts_done < 2:
                                    wait = random.uniform(40, 70)
                                    logger.info(f"⏳ Nghỉ {wait:.1f}s trước khi sang Page tiếp theo...")
                                    time.sleep(wait)
                            else:
                                # Lỗi khi đăng (có thể do token hoặc FB chặn tạm thời)
                                logger.error(f"❌ Lỗi khi đăng video {vid_id} lên FB. Chuyển sang pending.")
                                safe_execute(supabase.table("lich_su_video").update({"trang_thai": "pending"}).eq("id", item['id']))
                        else:
                            logger.error(f"❌ Xử lý video {vid_id} thất bại (Timeout/Lỗi FFmpeg). Bỏ qua.")
                            safe_execute(supabase.table("lich_su_video").update({"trang_thai": "pending"}).eq("id", item['id']))
                    else:
                        # Lỗi khi tải (thường là do YouTube chặn hoặc video bị xóa) -> Đánh dấu thất bại vĩnh viễn
                        logger.error(f"❌ Không thể tải video {vid_id}. Đánh dấu thất bại vĩnh viễn.")
                        safe_execute(supabase.table("lich_su_video").update({"trang_thai": "failed"}).eq("id", item['id']))
                except Exception as e:
                    logger.error(f"⚠️ Lỗi nghiêm trọng khi xử lý video {vid_id}: {e}")
                    safe_execute(supabase.table("lich_su_video").update({"trang_thai": "pending"}).eq("id", item['id']))
                finally:
                    if path and os.path.exists(path):
                        os.remove(path)

if __name__ == "__main__":
    main()
