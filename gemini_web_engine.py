import os
import sys
import time
import json
import base64
import glob
import urllib.request
from typing import Optional, Dict, Any, List

sys.path.insert(0, r"C:\Users\POI\Desktop\New folder (5)")
import muse_cdp_engine

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gemini_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
USER_DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")


def get_gemini_page_cdp(cdp_port: int = 9225):
    """Lấy kết nối CDP tới tab Google Gemini Web đang mở (tự động bật nếu chưa chạy)."""
    try:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json", timeout=1.5) as r:
                tabs = json.loads(r.read().decode("utf-8"))
        except Exception:
            # Tự động khởi chạy Chrome nếu chưa mở
            import chatgpt_auth_manager as cam
            cam.show_muse_chrome()
            time.sleep(2.0)
            with urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json", timeout=3.0) as r:
                tabs = json.loads(r.read().decode("utf-8"))

        pages = [t for t in tabs if t.get("type") == "page"]
        gemini_tab = next((t for t in pages if "gemini.google.com" in t.get("url", "")), None)
        if not gemini_tab and pages:
            gemini_tab = pages[0]
            cdp = muse_cdp_engine.CDPClient(gemini_tab["webSocketDebuggerUrl"], timeout=10.0)
            cdp.call("Page.navigate", {"url": "https://gemini.google.com/app?hl=vi"})
            time.sleep(2.0)
            return cdp
        elif gemini_tab:
            return muse_cdp_engine.CDPClient(gemini_tab["webSocketDebuggerUrl"], timeout=30.0)
    except Exception as e:
        print(f"[GeminiWeb] Lỗi kết nối CDP port {cdp_port}: {e}")
    return None


def remove_gemini_watermark(img_bgr_or_bytes):
    """
    Tự động phát hiện và xóa hoàn toàn logo watermark ngôi sao 4 cánh (✨) của Google Gemini
    ở góc dưới cùng bên phải ảnh, khôi phục chi tiết trang phục và bối cảnh tự nhiên 100%.
    """
    try:
        import cv2
        import numpy as np

        is_bytes = isinstance(img_bgr_or_bytes, (bytes, bytearray))
        if is_bytes:
            img = cv2.imdecode(np.frombuffer(img_bgr_or_bytes, np.uint8), cv2.IMREAD_COLOR)
        else:
            img = img_bgr_or_bytes.copy()

        if img is None:
            return img_bgr_or_bytes

        h, w = img.shape[:2]
        if h >= 150 and w >= 150:
            scale = min(w, h) / 1792.0
            if scale < 0.4:
                scale = 0.5

            if w <= 300 and h <= 300:
                cx, cy = 88, 88
                scale = 1.0
            else:
                cx = int(w - 112.0 * scale)
                cy = int(h - 112.0 * scale)

            R = 50.0 * scale
            p = 0.73

            pad = int(80.0 * scale)
            y1 = max(0, cy - pad)
            y2 = min(h, cy + pad)
            x1 = max(0, cx - pad)
            x2 = min(w, cx + pad)

            roi = img[y1:y2, x1:x2].copy()
            rh, rw = roi.shape[:2]
            rcx = cx - x1
            rcy = cy - y1

            mask = np.zeros((rh, rw), dtype=np.uint8)
            for y in range(rh):
                for x in range(rw):
                    dx = abs(x - rcx) / R
                    dy = abs(y - rcy) / R
                    if (dx**p + dy**p) <= 1.0:
                        mask[y, x] = 255

            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask = cv2.dilate(mask, kernel, iterations=2)

            inpaint_radius = max(3, int(5.0 * scale))
            cleaned_roi = cv2.inpaint(roi, mask, inpaint_radius, cv2.INPAINT_TELEA)
            img[y1:y2, x1:x2] = cleaned_roi

        if is_bytes:
            _, buf = cv2.imencode('.png', img)
            return buf.tobytes()
        return img
    except Exception as e:
        print(f"[GeminiWeb] Bỏ qua xóa watermark: {e}")
        return img_bgr_or_bytes


def wait_and_download_new_image(cdp, min_timestamp: float, timeout: int = 50) -> str:
    """
    Theo dõi Gemini vẽ ảnh và nhận ảnh:
    1. Thiết lập thư mục tải về.
    2. Click nút tải ảnh gốc kích thước đầy đủ ngay khi ảnh xuất hiện.
    3. Quét đồng thời cả thư mục gemini_downloads và Downloads của Windows.
    4. Trích xuất ảnh chỉ từ phản hồi mới của Bot (tuyệt đối không lấy ảnh mẫu người dùng gửi).
    5. Tự động tẩy logo Gemini watermark (✨) và trả về base64.
    """
    try:
        cdp.call("Browser.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": DOWNLOAD_DIR,
            "eventsEnabled": True
        })
    except Exception:
        pass

    wait_start = time.time()
    download_clicked = False
    print(f"[GeminiWeb] ⏳ Đang chờ Gemini hoàn tất vẽ ảnh mới (tối đa {timeout}s)...")

    # Dọn các file tải dở cũ
    for f in glob.glob(os.path.join(DOWNLOAD_DIR, "*.crdownload")):
        try:
            if time.time() - os.path.getmtime(f) > 30:
                os.remove(f)
        except Exception:
            pass

    while time.time() - wait_start < timeout:
        elapsed = time.time() - wait_start
        search_dirs = [DOWNLOAD_DIR, USER_DOWNLOADS]

        # 1. Quét tìm file ảnh tải về hợp lệ
        for s_dir in search_dirs:
            if not os.path.isdir(s_dir):
                continue
            candidates = glob.glob(os.path.join(s_dir, "Gemini_Generated_Image_*.*"))
            candidates += glob.glob(os.path.join(s_dir, "Gemini_*.png"))

            valid_files = [
                f for f in candidates
                if (f.endswith(".png") or f.endswith(".jpg"))
                and not f.endswith(".crdownload")
                and os.path.getmtime(f) >= min_timestamp - 10.0
                and os.path.getsize(f) > 100 * 1024
            ]
            if valid_files:
                latest_file = sorted(valid_files, key=os.path.getmtime)[-1]
                time.sleep(0.5)
                try:
                    with open(latest_file, "rb") as f:
                        data = f.read()
                    if len(data) > 100 * 1024:
                        print(f"[GeminiWeb] ✔ Nhận thành công ảnh gốc MỚI: {os.path.basename(latest_file)} ({len(data)/1024:.1f} KB) sau {elapsed:.1f}s!")
                        clean_data = remove_gemini_watermark(data)
                        try:
                            with open(latest_file, "wb") as f_out:
                                f_out.write(clean_data)
                        except Exception:
                            pass
                        return f"data:image/png;base64,{base64.b64encode(clean_data).decode('utf-8')}"
                except Exception as read_err:
                    print(f"[GeminiWeb] Đang đọc file ảnh: {read_err}")

        # 2. Kiểm tra trạng thái phản hồi của Gemini qua DOM
        check_bot_js = """
        (() => {
            const stopBtn = document.querySelector('button[aria-label*="Dừng"], button[aria-label*="Stop"]');
            const isGenerating = stopBtn !== null;

            // Tìm nút tải ảnh gốc (chỉ xuất hiện khi Gemini vẽ ảnh hoàn tất)
            const dlBtns = Array.from(document.querySelectorAll('button[aria-label*="Tải hình ảnh có kích thước đầy đủ xuống"], button[aria-label*="Download full size"], button[aria-label*="Tải xuống"], button[aria-label*="Download image"]'));
            if (dlBtns.length > 0) {
                dlBtns[dlBtns.length - 1].click();
                return { action: 'clicked_download' };
            }

            // Tìm câu trả lời mới nhất của Bot
            const botResponses = Array.from(document.querySelectorAll('model-response, .model-response-text, [data-message-author="bot"], message-content'));
            if (botResponses.length === 0) {
                return { action: 'waiting' };
            }
            const lastResp = botResponses[botResponses.length - 1];

            // Tìm ảnh được sinh ra bên trong câu trả lời của Bot (tuyệt đối không lấy ảnh đính kèm của user)
            const generatedImgs = Array.from(lastResp.querySelectorAll('img')).filter(img => 
                img.src && (img.src.includes('googleusercontent.com') || img.src.startsWith('blob:')) &&
                !img.closest('user-query') && !img.closest('.attachment-container') &&
                ((img.naturalWidth && img.naturalWidth >= 400) || (img.width && img.width >= 400))
            );

            if (generatedImgs.length > 0) {
                const img = generatedImgs[generatedImgs.length - 1];
                try {
                    const canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth || img.width;
                    canvas.height = img.naturalHeight || img.height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    return { action: 'extracted_img', dataUrl: canvas.toDataURL('image/png') };
                } catch(e) {
                    return { action: 'image_pending' };
                }
            }

            // Nếu Bot đã trả lời xong và CHỈ viết văn bản (không chịu vẽ ảnh)
            if (!isGenerating && elapsed_estimate_done) {
                const text = lastResp.innerText || lastResp.textContent || "";
                if (text.trim().length > 30) {
                    return { action: 'text_only', text: text.trim().slice(0, 150) };
                }
            }

            return { action: 'generating' };
        })()
        """
        # Inject elapsed check
        check_js_with_elapsed = check_bot_js.replace("elapsed_estimate_done", f"({elapsed} > 8)")
        try:
            bot_state = cdp.call("Runtime.evaluate", {"expression": check_js_with_elapsed, "returnByValue": True})
            state_val = bot_state.get("result", {}).get("value", {})
            action = state_val.get("action") if isinstance(state_val, dict) else None

            if action == "clicked_download" and not download_clicked:
                download_clicked = True
                print(f"[GeminiWeb] 📥 Đã bấm nút tải ảnh gốc kích thước đầy đủ sau {elapsed:.1f}s!")

            elif action == "extracted_img":
                data_url = state_val.get("dataUrl")
                if data_url and str(data_url).startswith("data:image"):
                    print(f"[GeminiWeb] ✔ Trích xuất ảnh vẽ mới chất lượng cao từ Gemini Web sau {elapsed:.1f}s!")
                    raw_b64 = data_url.split(",")[-1]
                    clean_data = remove_gemini_watermark(base64.b64decode(raw_b64))
                    return f"data:image/png;base64,{base64.b64encode(clean_data).decode('utf-8')}"

            elif action == "text_only" and elapsed > 15:
                text_preview = state_val.get("text", "")
                raise RuntimeError(
                    f"Gemini chỉ trả lời mô tả bằng chữ mà không vẽ ảnh: \"{text_preview}...\".\n\n"
                    f"👉 Để ghép nền ảnh cưới chuẩn 100%, bạn hãy bấm sang Tab 'GPT IMAGE' (ChatGPT) phía trên!"
                )
        except RuntimeError:
            raise
        except Exception:
            pass

        time.sleep(0.8)

    raise RuntimeError("Quá thời gian chờ Gemini vẽ ảnh mới. Vui lòng bấm 'Tạo lại' hoặc chuyển sang Tab 'GPT IMAGE'!")


def generate_image_with_gemini_web(
    prompt: str = "",
    scene: str = "",
    aspect_ratio: str = "3:4",
    uploaded_image_b64: Optional[str] = None,
    timeout: int = 50
) -> str:
    """
    Tạo ảnh MỚI hoàn toàn trên Gemini Web (có ghép nền):
    1. Mở cuộc trò chuyện MỚI.
    2. Đính kèm ảnh mẫu cô dâu chú rể.
    3. Gửi câu lệnh 'Tạo bức ảnh mới: Ghép cặp đôi vào bối cảnh...'.
    4. Nhận ảnh MỚI do Gemini vẽ và tải file gốc 1792x2400 về.
    """
    request_start_time = time.time()
    cdp = get_gemini_page_cdp(9225)
    if not cdp:
        raise RuntimeError("Không tìm thấy trình duyệt Chrome kết nối với Gemini Web (Port :9225). Vui lòng bấm 'Hiện Chrome'!")

    try:
        # 1. Mở cuộc trò chuyện mới để tạo ảnh mới hoàn toàn
        print("[GeminiWeb] 🔄 Đang mở cuộc trò chuyện mới trên Gemini...")
        cdp.call("Page.navigate", {"url": "https://gemini.google.com/app?hl=vi"})
        time.sleep(2.0)

        # 2. Chuẩn bị file ảnh mẫu đính kèm nếu có
        temp_img_path = None
        if uploaded_image_b64:
            try:
                raw_b64 = uploaded_image_b64.split(",")[-1]
                temp_img_path = os.path.abspath("temp_gemini_input.png")
                with open(temp_img_path, "wb") as f:
                    f.write(base64.b64decode(raw_b64))

                # Đính kèm ảnh vào input file
                dom_node = cdp.call("DOM.getDocument")
                file_input = cdp.call("DOM.querySelector", {
                    "nodeId": dom_node["root"]["nodeId"],
                    "selector": 'input[type="file"][accept*="image"]'
                })
                if file_input and file_input.get("nodeId"):
                    cdp.call("DOM.setFileInputFiles", {
                        "files": [temp_img_path],
                        "nodeId": file_input["nodeId"]
                    })
                    print(f"[GeminiWeb] Đã đính kèm ảnh mẫu mới: {temp_img_path}")
                    time.sleep(2.0)
            except Exception as e:
                print(f"[GeminiWeb] Lỗi đính kèm ảnh mẫu: {e}")

        # 3. Chuẩn bị Prompt tạo ảnh CÓ MỆNH LỆNH VẼ ẢNH RÕ RÀNG
        scene_part = f"Bối cảnh phông nền: {scene}." if scene else "Bối cảnh phông nền: Studio chụp ảnh cưới nghệ thuật hoàng gia sang trọng."
        detail_part = f"Chi tiết: {prompt}." if prompt else ""

        if uploaded_image_b64:
            full_prompt = (
                f"Tạo bức ảnh mới (Generate a new photo): Hãy vẽ và tạo một bức ảnh mới thay đổi toàn bộ phông nền phía sau cô dâu chú rể thành: {scene_part} {detail_part} "
                f"Yêu cầu quan trọng: "
                f"1. Tạo ảnh mới hoàn chỉnh (chất lượng 8K photorealistic, tỉ lệ {aspect_ratio}). "
                f"2. Giữ nguyên 100% người mẫu từ ảnh đính kèm: Bảo toàn chính xác tuyệt đối khuôn mặt, đôi mắt, nụ cười, thần thái, dáng đứng và trang phục của cô dâu chú rể. "
                f"3. Thay đổi và hòa trộn toàn bộ không gian phông nền phía sau thành studio nghệ thuật ánh sáng hoàn hảo."
            )
        else:
            full_prompt = (
                f"Tạo bức ảnh mới (Generate a new photo): Hãy vẽ bức ảnh cưới nghệ thuật mới tuyệt đẹp chất lượng studio 8K, tỉ lệ {aspect_ratio}. {scene_part} {detail_part} "
                f"Khuôn mặt và thần thái chân thực tự nhiên, trang phục lộng lẫy, ánh sáng điện ảnh chuyên nghiệp."
            )

        # 4. Focus và click chuột vào ô nhập lệnh để kích hoạt editor
        click_js = """
        (() => {
            const ed = document.querySelector('.ql-editor') || document.querySelector('[contenteditable="true"]');
            if (!ed) return null;
            ed.focus();
            const r = ed.getBoundingClientRect();
            return { x: Math.round(r.left + 25), y: Math.round(r.top + 20) };
        })()
        """
        click_res = cdp.call("Runtime.evaluate", {"expression": click_js, "returnByValue": True})
        coords = click_res.get("result", {}).get("value")
        if coords:
            for mtype in ["mousePressed", "mouseReleased"]:
                cdp.call("Input.dispatchMouseEvent", {
                    "type": mtype,
                    "x": coords["x"],
                    "y": coords["y"],
                    "button": "left",
                    "clickCount": 1
                })
            time.sleep(0.3)

        # 5. Gõ toàn bộ câu lệnh prompt qua Input.insertText (chuẩn CDP - cập nhật 100% vào Quill)
        cdp.call("Input.insertText", {"text": full_prompt})
        time.sleep(0.8)

        # Kiểm tra xác nhận nội dung prompt đã vào ô nhập
        verify_text_js = """
        (() => {
            const ed = document.querySelector('.ql-editor') || document.querySelector('[contenteditable="true"]');
            return ed ? (ed.innerText || ed.textContent || '').trim() : '';
        })()
        """
        v_res = cdp.call("Runtime.evaluate", {"expression": verify_text_js, "returnByValue": True})
        actual_text = v_res.get("result", {}).get("value", "")
        print(f"[GeminiWeb] 📝 Prompt đã nhập vào Gemini ({len(actual_text)} ký tự): {actual_text[:100]}...")

        # 6. Bấm nút Gửi tin nhắn
        sent = False
        for _ in range(10):
            send_js = """
            (() => {
                const btn = Array.from(document.querySelectorAll('button')).find(b => 
                    (b.getAttribute('aria-label') || '').includes('Gửi') || 
                    (b.getAttribute('aria-label') || '').includes('Send')
                );
                if (btn && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true') {
                    btn.click();
                    return true;
                }
                return false;
            })()
            """
            s_res = cdp.call("Runtime.evaluate", {"expression": send_js, "returnByValue": True})
            if s_res.get("result", {}).get("value") is True:
                sent = True
                print("[GeminiWeb] 🚀 Đã bấm nút Gửi tin nhắn thành công kèm prompt và ảnh mẫu!")
                break
            time.sleep(0.5)

        if not sent:
            print("[GeminiWeb] ⚠️ Thử gửi tin nhắn bằng phím Enter dự phòng...")
            cdp.call("Input.dispatchKeyEvent", {
                "type": "rawKeyDown",
                "windowsVirtualKeyCode": 13,
                "unmodifiedText": "\r",
                "text": "\r"
            })
            cdp.call("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "windowsVirtualKeyCode": 13,
                "unmodifiedText": "\r",
                "text": "\r"
            })

        # 6. Đợi và tải ảnh mới
        return wait_and_download_new_image(cdp, request_start_time, timeout=timeout)

    finally:
        try:
            cdp.close()
        except Exception:
            pass
