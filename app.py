import os
import requests
import time
import re
import json
import random
import string
import logging
import glob
import subprocess
import traceback
import sys
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from supabase import create_client
from dotenv import load_dotenv
from scraper import get_random_ua, crawl_youtube_for_page, download_video

# --- CẤU HÌNH LOGGING ---
def vnz_formatter(record, datefmt=None):
    dt = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone(timezone(timedelta(hours=7)))
    return dt.strftime(datefmt if datefmt else '%Y-%m-%d %H:%M:%S')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
# Tắt log rác từ các thư viện bên ngoài
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("supabase").setLevel(logging.WARNING)
logging.getLogger("postgrest").setLevel(logging.WARNING)

old_formatTime = logging.Formatter.formatTime
def fixed_formatTime(self, record, datefmt=None):
    return vnz_formatter(record, datefmt)
logging.Formatter.formatTime = fixed_formatTime
logger = logging.getLogger(__name__)

# --- CẤU HÌNH & KHỞI TẠO ---
load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DEFAULT_USER_AGENT = get_random_ua()

# --- CÁC HÀM TIỆN ÍCH ---
def cleanup_temp_files():
    patterns = ["temp_video_*.mp4", "*.part", "*.temp", "*.ytdl", "logo_*.txt", "shopee_input.xlsx"]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try: os.remove(f)
            except: pass

def safe_execute(query, max_retries=3):
    for attempt in range(max_retries):
        try: return query.execute()
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 3
                time.sleep(wait)
            else: raise e

def clean_title(title):
    if not title: title = "Video Review"
    
    # 1. Xóa các đoạn trong ngoặc (ví dụ: (Full), [Review]...)
    title = re.sub(r'[\(\[][^()]*[\)\]]', '', title)
    
    # 2. Cập nhật năm cũ thành năm hiện tại
    now = datetime.now()
    current_year = now.year
    title = re.sub(r'\b20\d{2}\b', lambda m: str(current_year) if int(m.group(0)) < current_year else m.group(0), title)
    
    # 3. Xóa hashtag cũ của YouTube và từ khóa rác
    title = re.sub(r'#\S+', '', title)
    bad_words = ['shorts', 'video', 'nha', 'đây', 'tại đây', 'clip']
    for word in bad_words:
        title = re.sub(f'(?i)\\b{word}\\b', '', title)

    title = re.sub(r'\s+', ' ', title).strip().strip('-_ ')
    title = title.capitalize()

    # 4. SPINNING: Thêm tiền tố ngẫu nhiên
    prefixes = ["Wow!", "Góc review:", "Siêu phẩm", "Đỉnh thật sự", "Cái này lạ nè", "Review tâm huyết:", "Must-have item:", "Xịn xò chưa", "Gom lúa thôi", "Tin được không?"]
    prefix = random.choice(prefixes) if random.random() > 0.4 else ""

    # 5. SPINNING: Trộn Hashtag ngẫu nhiên từ pool lớn
    all_hashtags = ["#review", "#shopeehaul", "#muataishopee", "#xuhuong", "#trending", "#reviewlamdep", "#gocreview", "#shopeevn", "#unbox", "#reviewthongminh", "#dogiadung", "#tienich", "#shopeecheck", "#sale", "#muasắm", "#fyp", "#meovat", "#ReviewThucTe", "#hot"]
    chosen_hashtags = random.sample(all_hashtags, k=random.randint(4, 6))
    
    # 6. SPINNING: Thêm Emoji ngẫu nhiên vào cuối tiêu đề
    random_emos = "".join(random.choices(["✨", "🔥", "✅", "💎", "📌", "🌈", "⭐", "🎀"], k=2))

    final_title = f"{prefix} {title} {random_emos} {' '.join(chosen_hashtags)}".strip()
    
    # 7. ANTI-SPAM: Chèn một ký tự vô hình ngẫu nhiên vào cuối để Hash text luôn khác nhau
    invisible_chars = ['\u200b', '\u200c', '\u200d']
    return final_title + random.choice(invisible_chars)

def process_video_spinning(input_path, page_name="Review Pro"):
    """Phân loại 3 loại video và xử lý lách bản quyền thông minh theo đúng yêu cầu"""
    output_path = input_path.replace(".mp4", "_processed.mp4")
    text_file = None
    try:
        # 1. Kiểm tra thông số video và sự tồn tại của audio stream
        cmd_probe = ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height', '-of', 'json', input_path]
        probe_res = subprocess.run(cmd_probe, capture_output=True, text=True, timeout=15)
        probe_data = json.loads(probe_res.stdout)
        
        has_audio = any(s['codec_type'] == 'audio' for s in probe_data['streams'])
        video_stream = next(s for s in probe_data['streams'] if s['codec_type'] == 'video')
        w = int(video_stream['width'])
        h = int(video_stream['height'])

        # 2. Thông số lách bản quyền chung
        speed = random.uniform(1.03, 1.06)
        pts = 1 / speed
        r_rot = round(random.uniform(-0.25, 0.25), 2)  # Xoay cực nhẹ, mắt thường không thấy
        r_pitch = round(random.uniform(0.99, 1.01), 3) # Đổi tone cực nhẹ
        r_cb = round(random.uniform(-0.02, 0.02), 2) # Cân bằng màu cực nhẹ
        junk_data = ''.join(random.choices(string.ascii_letters + string.digits, k=128))
        
        text_file = f"logo_{random.getrandbits(32)}.txt"
        with open(text_file, "w", encoding="utf-8") as f: f.write(page_name)
        
        # Ngẫu nhiên hóa màu sắc và vị trí logo (Linh hoạt y: 30-50)
        br = random.uniform(0.01, 0.03)
        sa = random.uniform(1.02, 1.10)
        co = random.uniform(1.01, 1.05)
        logo_x = random.choice(["35", "w-text_w-35"]) 
        logo_y = str(random.randint(30, 50)) 
        
        # Chỉ định đường dẫn font trực tiếp để tránh lỗi Fontconfig
        if os.name == 'nt':
            font_cfg = "fontfile='C\\:/Windows/Fonts/arial.ttf'"
        else:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(font_path):
                font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
            font_cfg = f"fontfile='{font_path}'"

        # Bộ lọc lách bản quyền nâng cao (Dùng biểu thức động để đổi Hash liên tục)
        zoom = random.uniform(1.02, 1.04)
        start_trim = random.uniform(0.1, 0.4)
        end_trim_offset = random.uniform(0.2, 0.5) # Cắt đuôi nhẹ
        eq_filter = f"eq=brightness='{br}+0.01*sin(t)':saturation='{sa}+0.02*cos(t)':contrast='{co}+0.01*sin(t/2)'"
        cb_filter = f"colorbalance=rm={r_cb}:gm={r_cb}:bm={r_cb}"
        spin_filters = f"rotate={r_rot}*PI/180:ow=iw:oh=ih:fillcolor=black,scale=iw*{zoom}:-2,crop=iw:ih,noise=alls=1:allf=t,{eq_filter},{cb_filter},unsharp=3:3:0.8,vignette=PI/4,setpts={pts}*PTS"

        # 3. PHÂN LOẠI VÀ CHỌN BỘ LỌC TỐI ƯU
        if h > w:
            # --- LOẠI 1: VIDEO DỌC CHUẨN ---
            logger.info(f"   📱 Loại 1 (Dọc chuẩn): {w}x{h}. Chuẩn hóa 9:16 và chèn logo phù hợp.")
            lx = random.choice(["60", "w-text_w-60"])
            ly = str(random.randint(30, 80)) # Nâng lên sát góc trên
            logo_f = f"drawtext={font_cfg}:textfile='{text_file}':x={lx}:y={ly}:fontsize=45:fontcolor=white@0.7:borderw=2:bordercolor=black@0.4"
            vf = f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,{spin_filters},{logo_f}"
            filter_complex = f"[0:v]{vf}[v]"
        else:
            # Kiểm tra xem là Ngang Full (Loại 2) hay Dọc-trong-Ngang (Loại 3)
            logger.info(f"   🖥️ Video Ngang: {w}x{h}. Đang phân tích nội dung...")
            vf_detect = "edgedetect=low=0.1:high=0.2,cropdetect=24:16:0"
            cmd_detect = ['ffmpeg', '-ss', '00:00:10', '-i', input_path, '-t', '5', '-vf', vf_detect, '-f', 'null', '-']
            detect_res = subprocess.run(cmd_detect, capture_output=True, text=True, timeout=45)
            crops = re.findall(r'crop=(-?\d+):(-?\d+):(-?\d+):(-?\d+)', detect_res.stderr)
            
            is_type_3 = False
            if crops:
                last_crop = crops[-1]
                d_w, d_h = abs(int(last_crop[0])), abs(int(last_crop[1]))
                if d_h > d_w: is_type_3 = True
                elif w / h > 1.5: is_type_3 = True

            if is_type_3:
                # --- LOẠI 3: DỌC TRONG KHUNG NGANG (GIỮ NGUYÊN KHUNG HÌNH) ---
                logger.info("   🎯 Loại 3 (Dọc trong ngang): Logo to rõ ở góc.")
                lx = random.choice(["35", "w-text_w-35"])
                ly = str(random.randint(30, 60))
                # Nâng size lên 32 cho video Loại 3 để nhìn rõ trên mọi độ phân giải
                logo_f = f"drawtext={font_cfg}:textfile='{text_file}':x={lx}:y={ly}:fontsize=30:fontcolor=white@0.8:borderw=2:bordercolor=black@0.4"
                vf = f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',{spin_filters},{logo_f}"
                filter_complex = f"[0:v]{vf}[v]"
            else:
                # --- LOẠI 2: NGANG FULL MÀN HÌNH ---
                logger.info("   📺 Loại 2 (Ngang Full): Logo lớn trên nền mờ.")
                logo_f = f"drawtext={font_cfg}:textfile='{text_file}':x=(w-text_w)/2:y=120:fontsize=30:fontcolor=white@0.8:borderw=2.5:bordercolor=black@0.5"
                filter_complex = (
                    f"[0:v]scale=405:720:force_original_aspect_ratio=increase,crop=405:720,boxblur=20:5,scale=720:1280[bg];"
                    f"[0:v]scale=720:1280:force_original_aspect_ratio=decrease[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{logo_f},{spin_filters}[v]"
                )

        # 4. Thực thi FFmpeg với các flag tối ưu
        # Tính toán thời lượng mới để cắt đuôi (phòng trường hợp video quá ngắn)
        duration_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_path]
        dur_res = subprocess.run(duration_cmd, capture_output=True, text=True)
        try:
            total_dur = float(dur_res.stdout.strip())
            new_dur = max(1.0, (total_dur - start_trim - end_trim_offset) / speed)
        except:
            new_dur = None

        cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(start_trim), '-i', input_path]
        if new_dur: cmd.extend(['-t', str(round(new_dur, 2))])
        
        cmd.extend(['-filter_complex', filter_complex, '-map', '[v]'])
        
        if has_audio:
            # Lách âm thanh: Đổi Pitch, swap kênh trái phải, và thay đổi tốc độ
            audio_filter = f"asetrate=44100*{r_pitch},aresample=44100,pan=stereo|c0=c1|c1=c0,atempo={speed/r_pitch},volume=1.02,treble=g=0.2,aformat=channel_layouts=stereo"
            cmd.extend(['-map', '0:a', '-af', audio_filter, '-c:a', 'aac', '-b:a', '128k'])
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cmd.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                    '-pix_fmt', 'yuv420p', '-r', '30', 
                    '-metadata', f"comment={junk_data}", 
                    '-metadata', f"creation_time={now_str}",
                    '-map_metadata', '-1', '-movflags', '+faststart',
                    output_path])
        
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=2000)
        
        if res.returncode != 0:
            logger.error(f"❌ FFmpeg thất bại (Exit {res.returncode}):\n{res.stderr}")
            return False

        if os.path.exists(output_path):
            os.remove(input_path); os.rename(output_path, input_path)
            return True
    except subprocess.TimeoutExpired:
        logger.error(f"❌ FFmpeg quá thời gian xử lý (Timeout 2000s) cho video: {input_path}")
    except Exception as e:
        logger.error(f"⚠️ Lỗi xử lý video {input_path}: {e}")
    finally:
        if text_file and os.path.exists(text_file): 
            try: os.remove(text_file)
            except: pass
    return False

def get_config_from_db():
    try:
        res = safe_execute(supabase.table("cau_hinh_bot").select("ma_shopee").limit(1))
        if res.data: return str(res.data[0].get('ma_shopee', '17394180064')).strip(), DEFAULT_USER_AGENT
    except: pass
    return "17394180064", DEFAULT_USER_AGENT

def check_video_exists(video_id, page_id):
    try:
        if safe_execute(supabase.table("video_blacklist").select("id_video").eq("id_video", str(video_id))).data: return True
        return len(safe_execute(supabase.table("lich_su_video").select("id").eq("id_video", str(video_id)).eq("id_page", str(page_id))).data) > 0
    except: return False

def save_pending_video(video_id, page_id, tieu_de, link_aff):
    try:
        if link_aff == "BLACKLIST":
            safe_execute(supabase.table("video_blacklist").upsert({"id_video": str(video_id), "ly_do": tieu_de}))
            return
        safe_execute(supabase.table("lich_su_video").insert({"id_video": str(video_id), "id_page": str(page_id), "tieu_de": str(tieu_de), "trang_thai": "raw", "link_affiliate": link_aff}))
    except Exception as e:
        if "duplicate key" not in str(e).lower(): logger.error(f"⚠️ Lỗi lưu video: {e}")

def update_scheduled_status(video_id, page_id, video_fb_id, scheduled_time_iso):
    try:
        safe_execute(supabase.table("lich_su_video").update({"trang_thai": "scheduled", "video_fb_id": video_fb_id, "thoi_gian_dang": scheduled_time_iso}).eq("id_video", str(video_id)).eq("id_page", str(page_id)))
    except: pass

def get_random_cta():
    p = random.choice(["👇", "📍", "🔗", "✨", "🔥", "👉", "✅", "📌"])
    v = random.choice(["Xem", "Lấy", "Check ngay", "Mua tại", "Sắm ngay"])
    o = random.choice(["link sản phẩm", "món này", "đồ", "món mình review"])
    l = random.choice(["ở dưới bình luận", "trong phần comment", "dưới cmt", "tại bình luận"])
    return f"{p} {v} {o} {l} nha cả nhà {random.choice(['✨', '🔥', '🌈', '⭐'])}"

def get_random_filler():
    f = random.choice(["Mê mẩn luôn á", "Cái này không mua phí nha", "Chân ái luôn", "Xịn xò thực sự", "Đáng đồng tiền lắm"])
    return f"{f} {random.choice(['😍', '🥰', '✨', '🔥', '💯'])}"

def post_to_facebook_scheduled(video_path, title, page_token, session, scheduled_time):
    url = "https://graph-video.facebook.com/v21.0/me/videos"
    caption = f"{title}\n\n{get_random_filler()}\n\n{get_random_cta()}"
    try:
        with open(video_path, 'rb') as f:
            data = {'description': caption, 'access_token': page_token, 'published': 'false', 'scheduled_publish_time': int(scheduled_time.timestamp())}
            res = session.post(url, data=data, files={'source': f}, timeout=600).json()
            if 'id' in res: return res['id']
            logger.error(f"❌ Lỗi Meta: {res}")
    except: logger.error(traceback.format_exc())
    return None

def get_next_schedule_time(page_id, page_index):
    try:
        res = safe_execute(supabase.table("lich_su_video").select("thoi_gian_dang").eq("id_page", str(page_id)).in_("trang_thai", ["posted", "scheduled"]).order("thoi_gian_dang", desc=True).limit(1))
        now = datetime.now(timezone.utc)
        start_search = datetime.fromisoformat(res.data[0]['thoi_gian_dang'].replace('Z', '+00:00')) + timedelta(minutes=30) if res.data else now + timedelta(minutes=15)
        for i in range(100):
            for hour in [0, 12]:
                pot = start_search.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(minutes=page_index*10)
                if pot > start_search and pot > now + timedelta(minutes=20): return pot
            start_search += timedelta(days=1)
    except: pass
    return datetime.now(timezone.utc) + timedelta(hours=2)

def get_scheduled_info(page_id):
    try:
        res = safe_execute(supabase.table("lich_su_video").select("thoi_gian_dang").eq("id_page", str(page_id)).in_("trang_thai", ["scheduled", "posted"]).order("thoi_gian_dang", desc=True).limit(1))
        if not res.data: return 0, 60
        last = datetime.fromisoformat(res.data[0]['thoi_gian_dang'].replace('Z', '+00:00'))
        return max(0, (last - datetime.now(timezone.utc)).days), 0
    except: return 0, 0

def main():
    logger.info("--- 🚀 BẮT ĐẦU CHU TRÌNH BOT ---")
    cleanup_temp_files()
    ma_aff, ua = get_config_from_db()
    pages = safe_execute(supabase.table("cau_hinh_page").select("*").order("id")).data
    
    with requests.Session() as shared_session:
        # BƯỚC 1: ĐẶT LỊCH ĐĂNG (Ưu tiên làm trước để có bài đăng ngay)
        logger.info("🎬 Đang kiểm tra và đặt lịch đăng bài (PENDING)...")
        any_pending = False
        for _ in range(50):
            processed = False
            for idx, config in enumerate(pages):
                tid = config['id_page_dich']
                ten_page = config.get('ten_page', 'Không tên')
                if get_scheduled_info(tid)[0] >= 30: continue
                
                res = safe_execute(supabase.rpc("lay_video_pending", {"p_id_page": str(tid)}))
                if not res.data: continue
                
                any_pending = True
                processed = True
                item = res.data[0]
                
                logger.info(f"📥 [Page: {ten_page}] Phát hiện video mới: {item['id_video']}. Bắt đầu xử lý...")
                
                logger.info(f"   ⏳ [1/3] Đang tải video từ YouTube ({item['id_video']})...")
                path = download_video(item['id_video'])
                
                if path:
                    logger.info(f"   🎨 [2/3] Đang chỉnh sửa & Spin video (FFmpeg)...")
                    if process_video_spinning(path, ten_page):
                        st = get_next_schedule_time(tid, idx)
                        logger.info(f"   🚀 [3/3] Đang đẩy video lên Meta API (Đặt lịch: {st})...")
                        fbid = post_to_facebook_scheduled(path, item['tieu_de'], config['token_fb'], shared_session, st)
                        
                        if fbid: 
                            update_scheduled_status(item['id_video'], tid, fbid, st.isoformat())
                            logger.info(f"   ✅ THÀNH CÔNG: [Page: {ten_page}] Đã đặt lịch video {item['id_video']} lúc {st}")
                        else: 
                            logger.error(f"   ❌ THẤT BẠI: Lỗi Meta API cho video {item['id_video']}.")
                            safe_execute(supabase.table("lich_su_video").update({"trang_thai": "pending"}).eq("id", item['id']))
                    else:
                        logger.error(f"   ❌ THẤT BẠI: Lỗi trong quá trình chỉnh sửa video (Spinning).")
                else:
                    logger.error(f"   ❌ THẤT BẠI: Không thể tải video từ YouTube.")
                
                if path and os.path.exists(path): 
                    os.remove(path)
                    logger.info(f"   🧹 Đã dọn dẹp file tạm cho video {item['id_video']}.")
                
                logger.info(f"⏳ Nghỉ {random.uniform(30, 60):.1f}s để đảm bảo an toàn cho Page...")
                time.sleep(random.uniform(30, 60))
            if not processed: break

        if not any_pending:
            res_raw = safe_execute(supabase.table("lich_su_video").select("id", count="exact").eq("trang_thai", "raw"))
            raw_count = res_raw.count if res_raw.count else 0
            if raw_count > 0:
                logger.warning(f"⚠️ KHO SẴN SÀNG TRỐNG! Đang có {raw_count} video 'raw' cần bạn chuyển link bằng shopee_link_tool.py")
        
        # BƯỚC 2: CÀO LINK THÔ (Làm sau để tích lũy kho dữ liệu)
        logger.info("🔍 Đang kiểm tra kho dữ liệu để cào thêm...")
        for config in pages:
            tid = config['id_page_dich']
            days, _ = get_scheduled_info(tid)
            
            # Đếm riêng video RAW và PENDING để log cho rõ
            res_raw = safe_execute(supabase.table("lich_su_video").select("id", count="exact").eq("id_page", str(tid)).eq("trang_thai", "raw"))
            raw_in_db = res_raw.count if res_raw.count is not None else 0
            
            res_pending = safe_execute(supabase.table("lich_su_video").select("id", count="exact").eq("id_page", str(tid)).eq("trang_thai", "pending"))
            pending_in_db = res_pending.count if res_pending.count is not None else 0
            
            logger.info(f"📊 [Status Page {tid}]: {days} ngày đã đặt lịch | {pending_in_db} video sẵn sàng | {raw_in_db} video thô.")
            
            # Nếu tổng dự trữ < 300 thì cào thêm một đợt tối đa 40 video mỗi lần chạy
            total_stock = days * 2 + raw_in_db + pending_in_db
            if total_stock < 300:
                needed = min(40, 300 - total_stock)
                logger.info(f"📡 Page {tid} đang thiếu hàng. Mục tiêu cào thêm đợt này: {needed} video.")
                crawl_youtube_for_page(config, ma_aff, ua, shared_session, check_video_exists, save_pending_video, clean_title, target_goal=needed)
            else:
                logger.info(f"✅ Page {tid} đã đủ định mức dự trữ (300).")

if __name__ == "__main__":
    # Đảm bảo console hiển thị được tiếng Việt trên Windows
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except:
            pass

    try: 
        main()
    except Exception: 
        logger.critical(traceback.format_exc())
    finally:
        print("\n" + "="*50)
        # Chỉ yêu cầu nhấn Enter nếu chạy ở chế độ tương tác (máy cá nhân)
        # Trên GitHub Actions (non-interactive), bot sẽ tự thoát
        if sys.stdin.isatty():
            input("🔔 TOOL ĐÃ DỪNG. Vui lòng nhấn Enter để thoát...")
        else:
            logger.info("🔔 TOOL ĐÃ HOÀN THÀNH CHU TRÌNH TỰ ĐỘNG.")
