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
from scraper import get_random_ua, crawl_youtube_for_page, download_video

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

DEFAULT_USER_AGENT = get_random_ua()

# --- CÁC HÀM TIỆN ÍCH ---
def cleanup_temp_files():
    """Dọn dẹp các file video tạm và file rác từ yt-dlp"""
    patterns = ["temp_video_*.mp4", "*.part", "*.temp", "*.ytdl", "logo_*.txt"]
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

HASHTAG_POOLS = [
    "✨ #review #shopeehaul #muataishopee #xuhuong",
    "🔥 #reviewlamdep #gocreview #shopeevn #trending",
    "🎁 #unbox #reviewthongminh #dogiadung #tienich",
    "🛍️ #shopeecheck #sale #muasắm #fyp",
    "✅ #meovat #cuocsong #ReviewThucTe #hot"
]

def clean_title(title):
    """Làm sạch và spin tiêu đề để tránh bị Facebook quét trùng lặp/spam"""
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
        text_file = f"logo_{random.getrandbits(32)}.txt"
        with open(text_file, "w", encoding="utf-8") as f: f.write(page_name)
        
        # Ngẫu nhiên hóa màu sắc và vị trí logo (Linh hoạt y: 30-50)
        br = random.uniform(0.02, 0.05)
        sa = random.uniform(1.1, 1.3)
        co = random.uniform(1.03, 1.08)
        logo_x = random.choice(["35", "w-text_w-35"]) # Đã thay tw bằng text_w
        logo_y = str(random.randint(30, 50)) 
        
        font_cfg = "font='Arial'" if os.name == 'nt' else "fontfile='/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'"
        logo_filter = f"drawtext={font_cfg}:textfile='{text_file}':x={logo_x}:y={logo_y}:fontsize=32:fontcolor=white:borderw=2.5:bordercolor=black@0.8"
        
        # Bộ lọc lách bản quyền nâng cao (Dùng biểu thức động để đổi Hash liên tục)
        zoom = random.uniform(1.02, 1.04)
        start_trim = random.uniform(0.1, 0.4)
        # Dynamic EQ: Thay đổi nhẹ độ sáng/tương phản theo thời gian t để lách Fingerprint AI
        eq_filter = f"eq=brightness='{br}+0.01*sin(t)':saturation='{sa}+0.02*cos(t)':contrast='{co}+0.01*sin(t/2)'"
        spin_filters = f"scale=iw*{zoom}:-2,crop=iw:ih,noise=alls=1:allf=t,{eq_filter},unsharp=5:5:1.0:5:5:0.0,vignette=PI/20,{logo_filter},setpts={pts}*PTS"

        # 3. PHÂN LOẠI VÀ CHỌN BỘ LỌC TỐI ƯU
        if h > w:
            # --- LOẠI 1: VIDEO DỌC CHUẨN ---
            logger.info(f"   📱 Loại 1 (Dọc chuẩn): {w}x{h}. Chuẩn hóa 9:16 (1080p) và lách bản quyền.")
            vf = f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,{spin_filters}"
            filter_complex = f"[0:v]{vf}[v]"
        else:
            # Kiểm tra xem là Ngang Full (Loại 2) hay Dọc-trong-Ngang (Loại 3)
            logger.info(f"   🖥️ Video Ngang: {w}x{h}. Đang phân tích nội dung...")
            # Sử dụng edgedetect để bỏ qua vùng nền mờ/tĩnh, chỉ lấy vùng nội dung sắc nét
            vf_detect = "edgedetect=low=0.1:high=0.2,cropdetect=40:16:0"
            cmd_detect = ['ffmpeg', '-ss', '00:00:10', '-i', input_path, '-t', '10', '-vf', vf_detect, '-f', 'null', '-']
            detect_res = subprocess.run(cmd_detect, capture_output=True, text=True, timeout=45)
            # Sử dụng regex linh hoạt để bắt cả số âm (một số bản ffmpeg trả về h âm khi detect từ dưới lên)
            crops = re.findall(r'crop=(-?\d+):(-?\d+):(-?\d+):(-?\d+)', detect_res.stderr)
            
            is_type_3 = False
            if crops:
                last_crop = crops[-1]
                d_w = abs(int(last_crop[0]))
                d_h = abs(int(last_crop[1]))
                logger.info(f"      🔍 Vùng nội dung phát hiện: {d_w}x{d_h} (Khung gốc: {w}x{h})")
                
                # CHỈ phân loại là Loại 3 nếu vùng nội dung có tỉ lệ DỌC (H > W) 
                # và chiếm ít nhất 70% chiều cao khung hình (tránh bắt nhầm thanh taskbar/sub)
                if d_h > d_w and d_h > h * 0.7:
                    is_type_3 = True
                    logger.info("      🎯 Xác nhận: Video Dọc trong khung Ngang.")
                else:
                    logger.info("      📺 Xác nhận: Video Ngang chuẩn (hoặc không rõ ràng) -> Chuyển về Loại 2.")

            if is_type_3:
                # --- LOẠI 3: DỌC TRONG KHUNG NGANG (HOẶC VIDEO CÓ LỀ) ---
                logger.info("   🎯 Loại 3 (Có lề/Dọc trong ngang): Giữ nguyên khung hình, chỉ lách bản quyền.")
                filter_complex = f"[0:v]scale='trunc(iw/2)*2':'trunc(ih/2)*2',{spin_filters}[v]"
            else:
                # --- LOẠI 2: NGANG FULL MÀN HÌNH ---
                logger.info("   📺 Loại 2 (Ngang Full): Thêm nền mờ để biến thành khung dọc 9:16 (720p Optimized).")
                # Chuyển từ gblur sang boxblur để tăng tốc độ render gấp 2-3 lần
                filter_complex = (
                    f"[0:v]scale=405:720:force_original_aspect_ratio=increase,crop=405:720,boxblur=20:5,scale=720:1280[bg];"
                    f"[0:v]scale=720:1280:force_original_aspect_ratio=decrease[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{spin_filters}[v]"
                )

        # 4. Thực thi FFmpeg với các flag tối ưu: FPS 30, xóa metadata, faststart
        cmd = ['ffmpeg', '-y', '-ss', str(start_trim), '-i', input_path,
               '-filter_complex', filter_complex, '-map', '[v]']
        
        # Chỉ map audio và spin âm thanh để lách bản quyền AI
        if has_audio:
            # atempo: đổi tốc độ, volume: đổi biên độ, treble: đổi tần số nhẹ (lách fingerprint cực tốt)
            # aformat: ép chuẩn stereo để tránh lỗi "0 channels"
            audio_filter = f"atempo={speed},volume=1.02,treble=g=0.2,aformat=sample_rates=44100:channel_layouts=stereo"
            cmd.extend(['-map', '0:a', '-af', audio_filter, '-c:a', 'aac', '-b:a', '128k'])
        
        cmd.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                    '-pix_fmt', 'yuv420p', '-r', '30', '-map_metadata', '-1', '-movflags', '+faststart',
                    output_path])
        
        logger.info(f"   🎬 Đang xử lý video: {os.path.basename(input_path)}")
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
    """Kiểm tra video đã được xử lý hoặc nằm trong blacklist chưa"""
    try:
        # 1. Kiểm tra blacklist toàn cục
        res_bl = safe_execute(supabase.table("video_blacklist").select("id_video").eq("id_video", str(video_id)))
        if res_bl.data: return True
        
        # 2. Kiểm tra lịch sử page
        res = safe_execute(supabase.table("lich_su_video").select("id").eq("id_video", str(video_id)).eq("id_page", str(page_id)))
        return len(res.data) > 0
    except: return False

def save_pending_video(video_id, page_id, tieu_de, link_aff):
    """Lưu video vào hàng đợi hoặc blacklist nếu link_aff='BLACKLIST'"""
    try:
        if link_aff == "BLACKLIST":
            safe_execute(supabase.table("video_blacklist").upsert({"id_video": str(video_id), "ly_do": tieu_de}))
            return

        data = {
            "id_video": str(video_id),
            "id_page": str(page_id),
            "tieu_de": str(tieu_de),
            "trang_thai": "pending",
            "link_affiliate": link_aff
        }
        safe_execute(supabase.table("lich_su_video").insert(data))
    except Exception as e:
        if "duplicate key" not in str(e).lower():
            logger.error(f"⚠️ Lỗi lưu video {video_id}: {e}")

def update_scheduled_status(video_id, page_id, video_fb_id, scheduled_time_iso):
    """Cập nhật trạng thái sau khi đã đặt lịch đăng thành công"""
    try:
        data = {
            "trang_thai": "scheduled",
            "video_fb_id": video_fb_id,
            "thoi_gian_dang": scheduled_time_iso
        }
        safe_execute(supabase.table("lich_su_video").update(data)\
            .eq("id_video", str(video_id))\
            .eq("id_page", str(page_id)))
    except Exception as e:
        logger.error(f"⚠️ Lỗi cập nhật status hẹn giờ cho video {video_id}: {e}")

def get_random_cta():
    """Tạo câu kêu gọi hành động ngẫu nhiên để tránh bị Facebook quét spam"""
    prefixes = ["👇", "📍", "🔗", "✨", "🔥", "👉", "✅", "💎", "📌", "🎬"]
    verbs = ["Xem", "Lấy", "Check ngay", "Mua tại", "Sắm ngay", "Link", "Món này", "Sở hữu ngay", "Đặt mua"]
    objects = ["link sản phẩm", "món này", "link mua hàng", "em nó", "đồ", "món mình review", "siêu phẩm này", "item cực hot"]
    locations = ["ở dưới bình luận", "trong phần comment", "dưới cmt", "tại bình luận", "phía dưới nhé", "ở ngay cmt đầu"]
    suffixes = ["nhé", "nha", "nhen", "ạ", "cả nhà", "nè", "nha quý vị", "nha mọi người", "nha các bác"]

    p = random.choice(prefixes)
    v = random.choice(verbs)
    o = random.choice(objects)
    l = random.choice(locations)
    s = random.choice(suffixes)

    # Thêm yếu tố ngẫu nhiên cực cao (Random Entropy)
    decor = "".join(random.choices(["✨", "🔥", "🌈", "⭐", "🎀", "🎈", "🍀", "💎"], k=random.randint(1, 3)))
    
    patterns = [
        f"{p} {v} {o} {l} {s} {decor}",
        f"{decor} {v} {o} {l} {p}",
        f"{v} {o} {l} {s} {p} {decor}",
        f"{p} {v} {o} {l} {decor}"
    ]
    return random.choice(patterns)

def get_random_filler():
    """Tạo các câu cảm thán ngẫu nhiên cực kỳ đa dạng để lách AI Facebook"""
    # Danh sách các câu cảm thán theo nhiều sắc thái
    fillers = [
        "Mê mẩn từ cái nhìn đầu tiên luôn á",
        "Cái này mà không mua thì hơi phí nha",
        "Đúng là chân ái cho hội chị em mình luôn",
        "Nhìn thôi đã thấy xịn xò rồi đúng không nào?",
        "Chất lượng thực sự vượt mong đợi luôn",
        "Tiền nào của nấy, đáng đồng tiền bát gạo lắm",
        "Review chân thực cho cả nhà cùng tham khảo nè",
        "Món này đang hot rần rần trên mạng luôn đó",
        "Giao hàng nhanh mà đóng gói cũng kỹ càng nữa",
        "Shop này uy tín cực kỳ, mình mua mấy lần rồi",
        "Không nghĩ là nó lại đẹp đến mức này luôn",
        "Một món đồ cực kỳ nên có trong nhà nhé",
        "Tiện lợi dã man, dùng rồi mới thấy xứng đáng",
        "Gom lúa hốt ngay em nó về thôi mọi người ơi",
        "Nhỏ mà có võ, công dụng bất ngờ luôn",
        "Cái màu này nhìn sang xịn mịn thực sự",
        "Bác nào còn phân vân thì quất luôn đi, không hối hận đâu",
        "Thiết kế thông minh, giải quyết được bao nhiêu vấn đề",
        "Vừa rẻ vừa đẹp, tội gì mà không thử nhỉ",
        "Đây chính là thứ mình tìm kiếm bấy lâu nay",
        "Đỉnh của chóp luôn, 10 điểm không có nhưng",
        "Đóng gói siêu chắc chắn, sờ vào là thấy xịn rồi",
        "Món này làm quà tặng cũng hợp lý lắm luôn",
        "Thêm ngay vào giỏ hàng kẻo hết là tiếc lắm",
        "Dùng bền mà lại còn thời trang nữa chứ",
        "Hội yêu bếp/yêu nhà không nên bỏ qua em này",
        "Trải nghiệm thực tế thấy cực kỳ hài lòng",
        "Lên video nhìn đẹp 1 thì ở ngoài đẹp 10 luôn",
        "Đáng đồng tiền thực sự, mua đi không phí đâu",
        "Cực kỳ hài lòng với chất lượng của shop này"
    ]
    
    # Các từ đệm cuối câu để tạo sự khác biệt
    endings = ["", "!", " nè.", " luôn á.", " luôn.", " ạ.", " nhé!", " nha.", " quá trời.", " ghê."]
    
    # Các emoji ngẫu nhiên
    emojis = ["😍", "🥰", "✨", "🔥", "💯", "👏", "😎", "💎", "💸", "📦", "🌟", "🌈", "❤️", "👍", "🙌", "🤩"]
    
    base = random.choice(fillers)
    end = random.choice(endings)
    emo = "".join(random.choices(emojis, k=random.randint(1, 3)))
    
    return f"{base}{end} {emo}"

def post_to_facebook_scheduled(video_path, title, page_token, session, scheduled_time):
    """Tải video lên Facebook ở chế độ Hẹn giờ (Scheduled)"""
    url = "https://graph-video.facebook.com/v21.0/me/videos"
    
    # Caption đa dạng hóa tối đa để lách Spam
    random_emoji = "".join(random.choices(["❤️", "🔥", "✨", "😍", "🥰", "👍", "🙌"], k=random.randint(2, 4)))
    filler = get_random_filler()
    cta = get_random_cta()
    
    # Cấu trúc caption: Tiêu đề + Filler + Emoji + CTA
    caption = f"{title}\n\n{filler} {random_emoji}\n\n{cta}"
    
    timestamp = int(scheduled_time.timestamp())

    try:
        logger.info(f"   📤 Đang tải video lên Facebook (Hẹn giờ: {scheduled_time.strftime('%H:%M %d/%m')})...")
        with open(video_path, 'rb') as f:
            files = {'source': f}
            data = {
                'description': caption,
                'access_token': page_token,
                'published': 'false',
                'scheduled_publish_time': timestamp
            }
            response = session.post(url, data=data, files=files, timeout=600)
            
            if not response.text: return None
            try:
                res = response.json()
            except: return None

        if 'id' in res:
            v_fb_id = res['id']
            logger.info(f"✅ Đã tải và đặt lịch thành công (ID: {v_fb_id})")
            return v_fb_id
        else:
            logger.error(f"❌ Lỗi Meta API: {res}")
    except Exception as e:
        logger.error(f"⚠️ Lỗi nghiêm trọng khi đặt lịch: {e}")
    return None

def get_next_schedule_time(page_id, page_index):
    """Tính toán thời gian đăng bài: 2 bài/ngày (7h, 19h) và so le 10p giữa các page"""
    try:
        # 1. Lấy bài gần nhất
        res = safe_execute(supabase.table("lich_su_video")
                           .select("thoi_gian_dang")
                           .eq("id_page", str(page_id))
                           .in_("trang_thai", ["posted", "scheduled"])
                           .order("thoi_gian_dang", desc=True)
                           .limit(1))
        
        now = datetime.now(timezone.utc)
        slots = [0, 12]  # Giờ UTC tương ứng với 7h, 19h Việt Nam (UTC+7)
        offset_minutes = page_index * 10  # So le 10 phút mỗi page
        
        if res.data and res.data[0]['thoi_gian_dang']:
            last_time = datetime.fromisoformat(res.data[0]['thoi_gian_dang'].replace('Z', '+00:00'))
            start_search = last_time + timedelta(minutes=30) # Tìm khung giờ tiếp theo sau bài cuối ít nhất 30p
        else:
            start_search = now + timedelta(minutes=15)

        # 2. Tìm slot thời gian phù hợp tiếp theo
        current_check = start_search
        for _ in range(100): # Tìm trong vòng 100 slot tiếp theo
            for hour in slots:
                # Tạo thời điểm tiềm năng: Ngày hiện tại/kế tiếp + Hour + Offset
                potential_time = current_check.replace(hour=hour, minute=0, second=0, microsecond=0)
                potential_time += timedelta(minutes=offset_minutes)
                
                if potential_time > start_search:
                    # Đảm bảo không đặt lịch quá gần hiện tại (Meta yêu cầu ít nhất 20p)
                    if potential_time < now + timedelta(minutes=20):
                        continue
                    return potential_time
            
            # Nếu không tìm thấy trong ngày này, nhảy sang ngày mai
            current_check += timedelta(days=1)
            current_check = current_check.replace(hour=0, minute=0)
            
        return now + timedelta(hours=2) # Fallback
    except Exception as e:
        logger.error(f"⚠️ Lỗi tính thời gian đăng: {e}")
        return datetime.now(timezone.utc) + timedelta(hours=1)

def get_scheduled_info(page_id):
    """Kiểm tra xem page đã được đặt lịch đến bao nhiêu ngày tới (Dựa trên 2 bài/ngày)"""
    try:
        res = safe_execute(supabase.table("lich_su_video")
                           .select("thoi_gian_dang")
                           .eq("id_page", str(page_id))
                           .in_("trang_thai", ["scheduled", "posted"])
                           .order("thoi_gian_dang", desc=True)
                           .limit(1))
        
        now = datetime.now(timezone.utc)
        if not res.data or not res.data[0]['thoi_gian_dang']:
            return 0, 60  # 30 ngày * 2 bài = 60
            
        last_time = datetime.fromisoformat(res.data[0]['thoi_gian_dang'].replace('Z', '+00:00'))
        if last_time < now: return 0, 60
            
        delta = last_time - now
        days_covered = delta.days
        total_needed = max(0, (30 - days_covered) * 2)
        
        return days_covered, total_needed
    except Exception as e:
        logger.error(f"⚠️ Lỗi tính toán lịch: {e}")
        return 0, 0

# --- LUỒNG CHÍNH ---
def main():
    logger.info(f"--- BOT BẮT ĐẦU CHẠY: {datetime.now().strftime('%H:%M:%S')} ---")
    cleanup_temp_files()
    ma_aff, ua = get_config_from_db()

    with requests.Session() as shared_session:
        # Lấy danh sách Page cấu hình
        pages = safe_execute(supabase.table("cau_hinh_page").select("*").order("id")).data

        # BƯỚC 1: KIỂM TRA KHO VÀ CÀO THÊM
        logger.info("🧐 Đang kiểm tra trạng thái lịch đăng của các Page...")
        for config in pages:
            target_id = config['id_page_dich']
            ten_p = config.get('ten_page')
            
            days_covered, needed_to_full = get_scheduled_info(target_id)
            
            # Kiểm tra xem trong kho pending có bao nhiêu bài
            res_pending = safe_execute(supabase.table("lich_su_video")
                               .select("id", count="exact")
                               .eq("id_page", str(target_id))
                               .eq("trang_thai", "pending"))
            pending_count = res_pending.count if res_pending.count is not None else 0

            logger.info(f"📊 Page [{ten_p}]: Đã có lịch {days_covered} ngày. Kho pending: {pending_count} video.")

            # Nếu tổng (đã đặt lịch + pending) < 30 ngày (60 bài) -> Cào thêm đúng số lượng còn thiếu
            total_current = (days_covered * 2 + pending_count)
            if total_current < 60:
                needed_now = 60 - total_current
                logger.info(f"   🚀 Thiếu hụt nội dung! Cần thêm {needed_now} video cho {ten_p}...")
                crawl_youtube_for_page(config, ma_aff, ua, shared_session, check_video_exists, save_pending_video, clean_title, target_goal=needed_now)
                # Nghỉ một chút giữa các Page để tránh bị YouTube/Shopee soi IP
                time.sleep(random.uniform(60, 120))
            else:
                logger.info(f"   ✅ Page {ten_p} đã đủ nội dung dự trữ.")

        # BƯỚC 2: TIẾN HÀNH ĐẶT LỊCH ĐĂNG (KIỂU CUỐN CHIẾU)
        logger.info("🎬 Bắt đầu luồng đặt lịch đăng bài cuốn chiếu (Round Robin)...")
        
        total_scheduled_session = 0
        MAX_TOTAL_VIDEOS = 50 # Giới hạn tổng để tránh timeout GitHub
        
        while total_scheduled_session < MAX_TOTAL_VIDEOS:
            processed_anything = False
            
            for idx, config in enumerate(pages):
                if total_scheduled_session >= MAX_TOTAL_VIDEOS: break
                
                target_id = config['id_page_dich']
                ten_page = config.get('ten_page') or "Không tên"
                token = config.get('token_fb')
                if not token: continue

                # 1. Kiểm tra page này đã đủ 30 ngày chưa
                current_days, _ = get_scheduled_info(target_id)
                if current_days >= 30:
                    continue

                # 2. Lấy 1 video pending cho page này
                res = safe_execute(supabase.rpc("lay_video_pending", {"p_id_page": str(target_id)}))
                if not res.data:
                    continue

                processed_anything = True
                item = res.data[0]
                vid_id = item['id_video']
                tieu_de_sach = item.get('tieu_de', 'Video Review')
                retry_count = item.get('so_lan_loi', 0)
                
                # Tính toán thời điểm đăng tiếp theo
                sched_time = get_next_schedule_time(target_id, idx)

                logger.info(f"🚀 Page [{ten_page}]: Đang xử lý 1 video gối đầu (Lần thử: {retry_count + 1})...")
                path = None
                try:
                    path = download_video(vid_id)
                    if path and process_video_spinning(path, ten_page):
                        v_fb_id = post_to_facebook_scheduled(path, tieu_de_sach, token, shared_session, sched_time)
                        if v_fb_id:
                            update_scheduled_status(vid_id, target_id, v_fb_id, sched_time.isoformat())
                            total_scheduled_session += 1
                            logger.info(f"   ✅ Lên lịch thành công: {vid_id} -> {sched_time.strftime('%Y-%m-%d %H:%M')}")
                            time.sleep(random.uniform(30, 60))
                        else:
                            raise Exception("Lỗi upload Facebook API")
                    else:
                        raise Exception("Lỗi download hoặc xử lý FFmpeg")

                except Exception as e:
                    new_retry = retry_count + 1
                    logger.error(f"   ⚠️ Lỗi xử lý {vid_id} ({new_retry}/3): {e}")
                    
                    if new_retry >= 3:
                        logger.warning(f"   🚫 Video {vid_id} lỗi quá 3 lần. Tự động đưa vào Blacklist.")
                        save_pending_video(vid_id, target_id, tieu_de_sach, "BLACKLIST")
                        safe_execute(supabase.table("lich_su_video").update({
                            "trang_thai": "blacklisted", 
                            "so_lan_loi": new_retry
                        }).eq("id", item['id']))
                    else:
                        # Vẫn để trạng thái failed hoặc chuyển về pending tùy chiến lược retry
                        # Ở đây mình để lại pending để lần sau bot có thể thử lại
                        safe_execute(supabase.table("lich_su_video").update({
                            "trang_thai": "pending", 
                            "so_lan_loi": new_retry
                        }).eq("id", item['id']))
                finally:
                    if path and os.path.exists(path): os.remove(path)

            if not processed_anything:
                logger.info("🎯 Tất cả các page đã đủ lịch 30 ngày hoặc hết video trong kho.")
                break


if __name__ == "__main__":
    main()
