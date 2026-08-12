import os
import requests
import time
import re
import logging
import random
import glob
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
    if not title: return "Video Review"
    return title.strip()


def get_config_from_db():
    return DEFAULT_USER_AGENT

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

def post_to_facebook_scheduled(video_path, link_affiliate, page_token, session, scheduled_time):
    url = "https://graph-video.facebook.com/v21.0/me/videos"
    # Lấy dòng đầu tiên và tách lấy link (nếu có định dạng Tiêu đề|Link)
    first_line = link_affiliate.split('\n')[0].strip() if link_affiliate else ""
    if '|' in first_line:
        link = first_line.split('|')[1].strip()
    else:
        link = first_line if first_line else "Link ở bình luận"
    
    # Thêm 1 emoji ngẫu nhiên trước "Mua ngay"
    emoji = random.choice(["✨", "🔥", "✅", "💎", "📌", "🌈", "⭐", "🎀", "😍", "💯", "🚀", "⚡", "🌟", "👇", "📍", "🔗"])
    caption = f"{emoji} Mua ngay: {link}"
    
    try:
        with open(video_path, 'rb') as f:
            data = {
                'description': caption, 
                'title': caption,
                'access_token': page_token, 
                'published': 'false', 
                'scheduled_publish_time': int(scheduled_time.timestamp())
            }
            res = session.post(url, data=data, files={'source': f}, timeout=600).json()
            if 'id' in res: return res['id']
            
            logger.error(f"❌ Lỗi Meta: {res}")
            # Detect Spam Block (Error 368)
            if res.get('error', {}).get('code') == 368:
                return "ERR_BLOCK_368"
    except: logger.error(traceback.format_exc())
    return None

def get_next_schedule_time(page_id, page_index):
    try:
        res = safe_execute(supabase.table("lich_su_video").select("thoi_gian_dang").eq("id_page", str(page_id)).in_("trang_thai", ["posted", "scheduled"]).order("thoi_gian_dang", desc=True).limit(1))
        now = datetime.now(timezone.utc)
        
        # Mốc thời gian sớm nhất có thể đặt (Meta yêu cầu cách hiện tại ít nhất 20p)
        min_allowable = now + timedelta(minutes=20)
        
        if res.data:
            last_time = datetime.fromisoformat(res.data[0]['thoi_gian_dang'].replace('Z', '+00:00'))
            # Phải cách video trước ít nhất 30p để tránh spam
            min_allowable = max(min_allowable, last_time + timedelta(minutes=30))
        
        # Bắt đầu quét từ ngày hiện tại của mốc min_allowable
        search_date = min_allowable.replace(hour=0, minute=0, second=0, microsecond=0)

        for i in range(100):
            for hour in [0, 11]: # Khung 7h sáng và 18h chiều VN (UTC+7)
                # Tính offset giãn cách giữa các page để không đăng trùng giây/phút
                # Mỗi page cách nhau 15 phút, cộng thêm 0-5 phút ngẫu nhiên
                offset_mins = (page_index * 15) + random.randint(0, 5)

                pot = search_date + timedelta(hours=hour, minutes=offset_mins)
                
                # Nếu slot này nằm sau mốc thời gian cho phép thì lấy
                if pot >= min_allowable:
                    return pot
            # Nếu ngày hiện tại không còn slot nào phù hợp, sang ngày tiếp theo
            search_date += timedelta(days=1)
    except Exception as e:
        logger.error(f"⚠️ Lỗi tính lịch đăng: {e}")
    
    # Fallback: Nếu có lỗi hoặc không tìm thấy slot, đặt lịch sau 2 tiếng
    return datetime.now(timezone.utc) + timedelta(hours=2)

def get_scheduled_info(page_id):
    """Trả về (số lượng video scheduled, số ngày tương ứng, thời gian của bài cuối)"""
    try:
        # 1. Lấy số lượng thực tế đang ở trạng thái scheduled (chờ đăng)
        res_count = safe_execute(supabase.table("lich_su_video")
                                 .select("id", count="exact")
                                 .eq("id_page", str(page_id))
                                 .eq("trang_thai", "scheduled"))
        count = res_count.count if res_count.count is not None else 0
        
        # 2. Tính số ngày dựa trên số lượng (Yêu cầu: 2 video/ngày)
        days = count // 2
        
        # 3. Lấy thời điểm bài cuối để làm priority phụ (nếu cùng số lượng video)
        res_last = safe_execute(supabase.table("lich_su_video")
                                .select("thoi_gian_dang")
                                .eq("id_page", str(page_id))
                                .in_("trang_thai", ["scheduled", "posted"])
                                .order("thoi_gian_dang", desc=True)
                                .limit(1))
        
        last_ts = 0
        if res_last.data and res_last.data[0].get('thoi_gian_dang'):
            last_dt = datetime.fromisoformat(res_last.data[0]['thoi_gian_dang'].replace('Z', '+00:00'))
            last_ts = last_dt.timestamp()
            
        return count, days, last_ts
    except Exception as e:
        logger.error(f"⚠️ Lỗi lấy thông tin Page {page_id}: {e}")
        return 0, 0, 0

def run_page_cycle(shared_session, ua):
    """Xử lý 1 page: Đặt lịch 1 video + Cào video thô trong 30 phút"""
    start_cycle = time.time()
    # Deadline cho việc cào video của lượt này (phút thứ 27 của chu kỳ 30p)
    cycle_deadline = start_cycle + 1620
    
    # 1. Lấy thông tin toàn bộ Page để tìm thằng ưu tiên nhất
    pages_res = safe_execute(supabase.table("cau_hinh_page").select("*"))
    pages_raw = pages_res.data if pages_res.data else []
    
    if not pages_raw:
        logger.warning("⚠️ Không tìm thấy cấu hình Page nào trong DB.")
        return False

    pages = []
    for p in pages_raw:
        tid = str(p['id_page_dich'])
        count, days, last_ts = get_scheduled_info(tid)
        
        last_run_str = p.get('last_run_at') or '1970-01-01T00:00:00+00:00'
        try:
            last_run_dt = datetime.fromisoformat(last_run_str.replace('Z', '+00:00'))
            last_run_ts = last_run_dt.timestamp()
        except:
            last_run_ts = 0
            
        p.update({
            'scheduled_actual_count': count,
            'days_scheduled_count': days,
            'last_post_timestamp': last_ts,
            'last_run_ts': last_run_ts
        })
        pages.append(p)
    
    # Thuật toán "Cuốn chiếu": 
    # 1. Ưu tiên thằng nào có thời gian nghỉ lâu nhất (last_run_ts nhỏ nhất) để đảm bảo xoay vòng (Round Robin).
    # 2. Nếu các thằng có cùng thời gian nghỉ (ví dụ mới chạy bot), ưu tiên thằng ít lịch nhất.
    pages.sort(key=lambda x: (x['last_run_ts'], x['days_scheduled_count']))
    
    config = pages[0]
    tid = str(config['id_page_dich'])
    ten_page = config.get('ten_page', 'Không tên')

    logger.info(f"🎯 Lượt này xử lý Page: {ten_page} (Lịch hiện tại: {config['days_scheduled_count']} ngày)")

    # Cập nhật last_run_at ngay để lượt sau (30p nữa) nó xuống cuối hàng chờ nếu các page khác có cùng số ngày
    safe_execute(supabase.table("cau_hinh_page").update({
        "last_run_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", config['id']))

    # BƯỚC 1: ĐĂNG 1 VIDEO
    if config['days_scheduled_count'] >= 30:
        logger.info(f"✅ [Page: {ten_page}] Đã đủ lịch 30 ngày. Bỏ qua đăng bài.")
    else:
        res = safe_execute(supabase.rpc("lay_video_pending", {"p_id_page": tid}))
        if res.data:
            item = res.data[0]
            path = download_video(item['id_video'])
            if path:
                st = get_next_schedule_time(tid, 0)
                fbid = post_to_facebook_scheduled(path, item.get('link_affiliate', ''), config['token_fb'], shared_session, st)
                
                if fbid == "ERR_BLOCK_368":
                    safe_execute(supabase.table("lich_su_video").update({"trang_thai": "pending"}).eq("id", item['id']))
                elif fbid: 
                    update_scheduled_status(item['id_video'], tid, fbid, st.isoformat())
                    logger.info(f"   ✅ Thành công đặt lịch 1 video cho {ten_page}")
                else:
                    safe_execute(supabase.table("lich_su_video").update({"trang_thai": "pending"}).eq("id", item['id']))
                
                if os.path.exists(path): os.remove(path)
        else:
            logger.info(f"   ℹ️ [Page: {ten_page}] Không có video 'pending' để đặt lịch.")

    # BƯỚC 2: CÀO VIDEO THÔ (Dành phần thời gian còn lại của 30p)
    r_raw = safe_execute(supabase.table("lich_su_video").select("id", count="exact").eq("id_page", tid).eq("trang_thai", "raw"))
    raw_c = r_raw.count if r_raw.count is not None else 0
    total_stock = config['scheduled_actual_count'] + raw_c
    
    if total_stock < 300:
        needed = min(50, 300 - total_stock)
        logger.info(f"📡 Page {ten_page} đang cào video thô bổ sung (Deadline lượt: 27 phút)...")
        crawl_youtube_for_page(config, ua, shared_session, check_video_exists, save_pending_video, clean_title, target_goal=needed, stop_time=cycle_deadline)
    
    return True

def main():
    logger.info("--- 🚀 BẮT ĐẦU CHU TRÌNH BOT (XỬ LÝ CUỐN CHIẾU) ---")
    cleanup_temp_files()
    ua = get_config_from_db()
    
    # Lấy cấu hình chạy 1 lần hay 12 lần từ môi trường (mặc định 12 để chạy local cũ)
    single_run = os.getenv("SINGLE_RUN", "False").lower() == "true"
    iterations = 1 if single_run else 12
    
    if single_run:
        logger.info("Mode: SINGLE_RUN (Chạy 1 lượt rồi thoát)")
    else:
        logger.info("Mode: MULTI_RUN (Chạy 12 lượt x 30p)")

    for i in range(iterations):
        loop_start = time.time()
        if not single_run:
            logger.info(f"\n⏰ === BẮT ĐẦU LƯỢT THỨ {i+1}/12 === ⏰")
        
        with requests.Session() as shared_session:
            try:
                run_page_cycle(shared_session, ua)
            except Exception as e:
                logger.error(f"❌ Lỗi trong lượt {i+1}: {e}")
                logger.error(traceback.format_exc())

        # Tính toán thời gian cần nghỉ để đúng chu kỳ 30p
        elapsed = time.time() - loop_start
        wait_time = 1800 - elapsed
        
        if wait_time > 0:
            if single_run:
                logger.info(f"😴 Đợi {wait_time/60:.1f} phút cho đủ chu kỳ 30p để đổi IP tiếp theo...")
            else:
                logger.info(f"😴 Lượt xong sớm. Nghỉ {wait_time/60:.1f} phút để chuẩn bị cho page tiếp theo...")
            time.sleep(wait_time)
        elif not single_run:
            logger.warning(f"⚠️ Lượt {i+1} chạy quá 30p ({elapsed/60:.1f}p). Sang page tiếp theo ngay.")

        if single_run:
            break

    logger.info("✅ HOÀN THÀNH TOÀN BỘ CHU TRÌNH 6 TIẾNG.")

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
