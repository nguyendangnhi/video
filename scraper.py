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
    """Chuyển đổi link Shopee sang link Affiliate Redirection (an_redir) chuẩn và kiểm tra link sống"""
    try:
        time.sleep(random.uniform(1.0, 3.0))
        headers = {'User-Agent': get_random_ua()}
        res = session.get(url_goc, headers=headers, allow_redirects=True, timeout=15)
        
        if res.status_code == 429:
            logger.error("   ⛔ Shopee phát hiện Bot (429)! Đang nghỉ 60s...")
            time.sleep(60)
            return None
        
        if res.status_code != 200:
            logger.warning(f"   ❌ Link không truy cập được (HTTP {res.status_code}): {url_goc}")
            return None
            
        final_url = res.url
        if final_url.split('?')[0].strip('/') == "https://shopee.vn":
            logger.warning(f"   ❌ Link đã chết hoặc hết hạn (Bị redirect về trang chủ): {url_goc}")
            return None

        if "mycollection.shop" in final_url:
            return final_url

        match = (re.search(r'i\.(\d+)\.(\d+)', final_url) or 
                 re.search(r'product/(\d+)/(\d+)', final_url) or 
                 re.search(r'shopee\.vn/[^/]+/(\d+)/(\d+)', final_url))
        
        if match:
            s_id, i_id = match.groups()
            base_url = f"https://shopee.vn/product/{s_id}/{i_id}"
            encoded_url = quote(base_url)
            return f"https://s.shopee.vn/an_redir?origin_link={encoded_url}&affiliate_id={ma_affiliate}&sub_id=fb_reels"
        else:
            logger.warning(f"   ❌ Không tìm thấy ID sản phẩm (Link không hợp lệ): {final_url}")
            return None
    except Exception as e:
        logger.error(f"   ⚠️ Lỗi khi kiểm tra link {url_goc}: {e}")
    return None

def download_video(video_id):
    """Tải video chất lượng tốt nhất dùng yt-dlp với cơ chế retry và giả lập client"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    path = f"temp_video_{video_id}.mp4"
    
    client_combos = [
        ['android', 'web'],
        ['ios', 'mweb'],
        ['tv', 'web']
    ]
    
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

def crawl_youtube_for_page(config, ma_affiliate, ua_string, session, check_exists_fn, save_video_fn, clean_title_fn, target_goal=90):
    """Cào video mới nhất từ YouTube dựa trên danh sách từ khóa (nguon_raw)"""
    target_page_id = config['id_page_dich']
    nguon_raw = config.get('link_nguon', '').strip()
    if not nguon_raw: return False
    
    # Tách danh sách từ khóa bằng dấu phẩy và xáo trộn ngẫu nhiên
    keywords = [k.strip() for k in nguon_raw.split(',')]
    random.shuffle(keywords)
    
    shopee_regex = r'(https?://(?:shope\.ee|s\.shopee\.vn|shopee\.vn|vn\.shp\.ee|affiliate\.shopee\.vn|mycollection\.shop)/[a-zA-Z0-9.\-_]+)'
    found_count = 0

    for selected in keywords:
        if found_count >= target_goal: break
        
        logger.info(f"🔍 Đang cào từ khóa: '{selected}' (Mục tiêu: {found_count}/{target_goal})")
        
        max_pages = 8 # Giảm số trang mỗi từ khóa để đa dạng hóa nguồn
        # Ngẫu nhiên hóa số lượng kết quả mỗi trang để tránh bị phát hiện quy luật
        page_size = random.randint(30, 50)

        for page in range(max_pages):
            if found_count >= target_goal: break
            
            start_idx = (page * page_size) + 1
            end_idx = start_idx + page_size - 1
            
            logger.info(f"   📡 Trang {page+1}: Quét video từ {start_idx} đến {end_idx}...")
            
            # Xoay vòng User Agent mới cho mỗi trang quét để chống bị YouTube soi
            current_ua = get_random_ua()
            search_query = selected if "youtube.com" in selected else f"ytsearch{end_idx}:{selected} #shorts"
            
            ydl_opts = {
                'extract_flat': 'in_playlist',
                'playliststart': start_idx,
                'playlistend': end_idx,
                'quiet': True,
                'no_warnings': True,
                'user_agent': current_ua,
                'getcomments': False,
                'sleep_interval': 5,
                'max_sleep_interval': 12,
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
                        logger.warning("      ⚠️ Không còn video nào để quét cho từ khóa này.")
                        break

                    new_videos_in_page = 0
                    for entry in entries:
                        if not entry: continue
                        
                        v_id = entry['id']
                        if check_exists_fn(v_id, target_page_id): 
                            continue

                        new_videos_in_page += 1
                        try:
                            # 1. Lấy thông tin video
                            video_info = ydl.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
                            v_desc = video_info.get('description') or ''
                            
                            # 2. Check comment nếu desc không có link
                            all_text = v_desc
                            if not re.search(shopee_regex, all_text):
                                cmt_opts = ydl_opts.copy()
                                cmt_opts.update({'getcomments': True, 'max_comments': 10})
                                with yt_dlp.YoutubeDL(cmt_opts) as ydl_cmt:
                                    video_info_cmt = ydl_cmt.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
                                    v_comments = video_info_cmt.get('comments') or []
                                    all_text += "\n" + "\n".join([c.get('text', '') for c in v_comments if c.get('text')])

                            # 3. Trích xuất tiêu đề và link
                            # Tách theo dòng để lấy tiêu đề đứng trước link
                            lines = all_text.split('\n')
                            found_pairs = []
                            seen_links = set()

                            for line in lines:
                                m = re.search(shopee_regex, line)
                                if m:
                                    link = m.group(1)
                                    if link in seen_links: continue
                                    
                                    # Lấy phần text trước link làm tiêu đề, xóa số thứ tự cũ, icon thừa
                                    title_part = line.split(link)[0].strip()
                                    title_part = re.sub(r'^[\d\.\-\s]+', '', title_part) # Xóa "1.", "2-", ...
                                    title_part = title_part.strip(':- ').strip()
                                    
                                    if not title_part: title_part = "Sản phẩm review"
                                    
                                    found_pairs.append({'title': title_part, 'url': link})
                                    seen_links.add(link)
                                    if len(found_pairs) >= 7: break # Lấy tối đa 7 link

                            if found_pairs:
                                aff_list = []
                                for pair in found_pairs:
                                    aff_link = tao_link_affiliate_moi(pair['url'], ma_affiliate, session)
                                    if aff_link:
                                        # Lưu dạng "Tiêu đề|Link" để SQL xử lý
                                        aff_list.append(f"{pair['title']}|{aff_link}")
                                
                                if not aff_list: continue

                                all_links_str = "\n".join(aff_list)
                                cleaned_tieu_de = clean_title_fn(video_info.get('title', ''))
                                save_video_fn(v_id, target_page_id, cleaned_tieu_de, all_links_str)
                                
                                found_count += 1
                                logger.info(f"      ✅ Đã nạp mới: {v_id} (Tổng: {found_count})")
                                # Tăng delay lên 5-10s để hành vi giống người dùng thật hơn
                                time.sleep(random.uniform(5, 10))

                                if found_count >= target_goal: break
                        except Exception as e:
                            logger.warning(f"      ⚠️ Lỗi video {v_id}: {e}")
                            continue

                    if new_videos_in_page == 0 and page > 0:
                        logger.info(f"   ⏭️ Từ khóa '{selected}' hết video mới ở trang {page+1}. Chuyển từ khóa tiếp theo...")
                        break
                        
            except Exception as e:
                logger.error(f"⚠️ Lỗi cào trang {page+1}: {e}")
                break

    return found_count > 0
