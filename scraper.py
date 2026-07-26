import os
import re
import time
import random
import logging
import yt_dlp
from urllib.parse import quote

# --- LOGGING ---
logger = logging.getLogger(__name__)

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

def tao_link_affiliate_moi(url_goc, ma_affiliate, session):
    """
    Chuyển đổi link Shopee và kiểm tra link sống.
    Trả về: (link_aff, status_code)
    """
    try:
        # Tăng độ trễ nhẹ và giả lập header đầy đủ để tránh bị chặn
        time.sleep(random.uniform(1.2, 2.5))
        headers = {
            'User-Agent': get_random_ua(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,webp,*/*;q=0.8',
            'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.facebook.com/',
            'Cache-Control': 'no-cache'
        }
        
        res = session.get(url_goc, headers=headers, allow_redirects=True, timeout=20)
        
        if res.status_code == 429:
            return None, 429
        
        if res.status_code != 200:
            return None, res.status_code
            
        final_url = res.url
        base_path = final_url.split('?')[0].strip('/')
        
        # 1. Kiểm tra nếu bị đá về trang chủ hoặc trang tìm kiếm (Link đã chết)
        if base_path in ["https://shopee.vn", "https://shopee.vn/search", "https://shopee.vn/all_categories"]:
            return None, 404

        # 2. Kiểm tra nội dung trang để phát hiện sản phẩm bị xóa/ẩn (Chính xác nhất)
        # Chỉ lấy 15kb đầu tiên để tối ưu tốc độ
        content_low = res.text[:15000].lower()
        dead_indicators = [
            "sản phẩm không tồn tại", "sp_not_found", "sản phẩm đã bị xóa", 
            "đã bị ẩn", "không tìm thấy sản phẩm", "hết hàng", 
            "ngừng kinh doanh", "không còn bán", "đã bán hết",
            "out of stock", "sold_out", "item_not_exist"
        ]
        if any(ind in content_low for ind in dead_indicators):
            return None, 404

        # 3. Giữ nguyên chức năng cho link MyCollection
        if "mycollection.shop" in final_url:
            return final_url, 200

        # 4. Trích xuất ID với regex cải tiến
        # Thử các mẫu đường dẫn truyền thống trước
        match_ids = (re.search(r'i\.(\d+)\.(\d+)', final_url) or 
                     re.search(r'product/(\d+)/(\d+)', final_url) or 
                     re.search(r'shopee\.vn/[^/]+/(\d+)/(\d+)', final_url))
        
        s_id, i_id = None, None
        if match_ids:
            s_id, i_id = match_ids.groups()
        else:
            # Thử tìm theo tham số query (dành cho link từ App hoặc link quảng cáo)
            m_s = re.search(r'shopid=(\d+)', final_url)
            m_i = re.search(r'itemid=(\d+)', final_url)
            if m_s and m_i:
                s_id, i_id = m_s.group(1), m_i.group(1)
        
        if s_id and i_id:
            base_url = f"https://shopee.vn/product/{s_id}/{i_id}"
            encoded_url = quote(base_url)
            # Giữ nguyên cấu trúc link affiliate của bạn
            aff_url = f"https://s.shopee.vn/an_redir?origin_link={encoded_url}&affiliate_id={ma_affiliate}&sub_id=fb_reels"
            return aff_url, 200
        
        return None, 400
    except Exception as e:
        logger.error(f"   ⚠️ Lỗi network khi check link {url_goc}: {e}")
        return None, 500

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
            'user_agent': get_random_ua(),
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

def crawl_youtube_for_page(config, ma_affiliate, ua_string, session, check_exists_fn, save_video_fn, clean_title_fn, target_goal=90):
    """Cào video từ YouTube, phân biệt lỗi tạm thời và lỗi vĩnh viễn để Blacklist chuẩn"""
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
            start_idx = (page * page_size) + 1
            end_idx = start_idx + page_size - 1
            
            ydl_opts = {
                'extract_flat': 'in_playlist',
                'playliststart': start_idx,
                'playlistend': end_idx,
                'quiet': True,
                'no_warnings': True,
                'user_agent': get_random_ua(),
                'getcomments': False,
                'sleep_interval': 3,
                'max_sleep_interval': 8,
                'match_filter': lambda info, *, incomplete: 'Video too long' if info.get('duration') and info.get('duration') > 600 else None,
                'extractor_args': {'youtube': {'player_client': ['android', 'ios', 'web']}}
            }

            try:
                search_query = selected if "youtube.com" in selected else f"ytsearch{end_idx}:{selected} #shorts"
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    search_results = ydl.extract_info(search_query, download=False)
                    entries = search_results.get('entries', [])
                    if not entries: break

                    for entry in entries:
                        if not entry or found_count >= target_goal or is_yt_blocked: continue
                        v_id = entry['id']
                        if check_exists_fn(v_id, target_page_id): continue
                        
                        try:
                            # 1. Trích xuất thông tin chi tiết
                            video_info = ydl.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
                            v_desc = video_info.get('description') or ''
                            all_text = v_desc
                            
                            # 2. Check comments nếu desc không có link
                            if not re.search(shopee_regex, all_text):
                                cmt_opts = ydl_opts.copy()
                                cmt_opts.update({'getcomments': True, 'max_comments': 10})
                                with yt_dlp.YoutubeDL(cmt_opts) as ydl_cmt:
                                    video_info_cmt = ydl_cmt.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
                                    v_comments = video_info_cmt.get('comments') or []
                                    all_text += "\n" + "\n".join([c.get('text', '') for c in v_comments if c.get('text')])

                            # 3. Phân tích link
                            found_pairs = []
                            seen_links = set()
                            for line in all_text.split('\n'):
                                m = re.search(shopee_regex, line)
                                if m:
                                    link = m.group(1)
                                    if link in seen_links: continue
                                    title_part = re.sub(r'^[\d\.\-\s]+', '', line.split(link)[0].strip()).strip(':- ').strip()
                                    found_pairs.append({'title': title_part or "Sản phẩm review", 'url': link})
                                    seen_links.add(link)
                                    if len(found_pairs) >= 7: break

                            if not found_pairs:
                                logger.info(f"      ⏭️ Blacklist {v_id}: Không thấy link Shopee.")
                                save_video_fn(v_id, target_page_id, "Không có link Shopee", "BLACKLIST")
                                continue

                            # 4. Chuyển đổi link
                            aff_list = []
                            is_sh_blocked = False
                            for pair in found_pairs:
                                aff_link, status = tao_link_affiliate_moi(pair['url'], ma_affiliate, session)
                                if status == 429: is_sh_blocked = True; break
                                if aff_link: aff_list.append(f"{pair['title']}|{aff_link}")
                            
                            if is_sh_blocked:
                                logger.warning(f"      ⛔ Tạm bỏ qua {v_id}: Shopee chặn Bot.")
                                continue 

                            if not aff_list:
                                logger.info(f"      ⏭️ Blacklist {v_id}: Link chết/hết hạn.")
                                save_video_fn(v_id, target_page_id, "Link Shopee không hợp lệ", "BLACKLIST")
                                continue

                            # 5. Lưu video
                            save_video_fn(v_id, target_page_id, clean_title_fn(video_info.get('title', '')), "\n".join(aff_list))
                            found_count += 1
                            logger.info(f"      ✅ Đã nạp: {v_id} (Tổng: {found_count})")
                            time.sleep(random.uniform(3, 7))

                        except Exception as e:
                            err = str(e)
                            if any(msg in err for msg in ["age-restricted", "private video", "removed by the uploader"]):
                                save_video_fn(v_id, target_page_id, "Video không khả dụng", "BLACKLIST")
                            elif "Sign in to confirm you're not a bot" in err:
                                is_yt_blocked = True; break
                            else: continue

            except Exception as e:
                logger.error(f"⚠️ Lỗi cào trang {page+1}: {e}")
                break

    return found_count > 0
