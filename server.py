"""
Trà Thương Pro AI - Python Web & Desktop Server
Phục vụ toàn bộ giao diện nguyên bản 100% (Tailwind CSS, React, Lucide Icons)
và kết nối xử lý API trực tiếp qua Python Google GenAI SDK.
"""

import os
import sys

# Đảm bảo UTF-8 cho console Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import json
import socket
import mimetypes
import subprocess
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

import tra_thuong_ai as tta
import license_manager as lm
import chatgpt_auth_manager as cam
import platform

_muse_server_instance = None

def ensure_muse_server():
    """Tự động kiểm tra và khởi chạy Muse Studio API Gateway (Port 18638) nếu chưa chạy."""
    global _muse_server_instance
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("127.0.0.1", 18638))
        s.close()
        return True
    except Exception:
        pass

    try:
        muse_dir = r"C:\Users\POI\Desktop\New folder (5)"
        if os.path.isdir(muse_dir):
            if muse_dir not in sys.path:
                sys.path.insert(0, muse_dir)
            import muse_api_server
            srv = muse_api_server.MuseApiServer(port=18638)
            srv.start()
            _muse_server_instance = srv
            print("[MUSE STUDIO] ✔ Đã tự động kích hoạt máy chủ Muse Studio tại http://127.0.0.1:18638!", flush=True)
            return True
    except Exception as e:
        print(f"[MUSE STUDIO] Lỗi khởi chạy Muse Server: {e}", flush=True)
        return False

def resize_image_to_dimensions(img_b64: str, target_w: int, target_h: int) -> str:
    """
    Tự động upscale/co giãn ảnh AI trả về sao cho TRÙNG KHỚP 100% kích thước pixel gốc của ảnh Photoshop.
    Giúp ảnh chèn vào Photoshop trùng khít 100% khung hình và vị trí gốc mà không bị lệch hay thụt lề!
    """
    if target_w <= 0 or target_h <= 0:
        return img_b64
    try:
        from PIL import Image
        import io
        import base64

        clean_b64 = img_b64.split("base64,")[-1] if "base64," in img_b64 else img_b64
        img_bytes = base64.b64decode(clean_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        cur_w, cur_h = img.size
        
        if cur_w == target_w and cur_h == target_h:
            return img_b64

        resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        out_buf = io.BytesIO()
        resized.save(out_buf, format="JPEG", quality=95)
        out_b64 = base64.b64encode(out_buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{out_b64}"
    except Exception as e:
        print(f"[RESIZE_DOC] Lỗi khi resize ảnh sang kích thước {target_w}x{target_h}: {e}")
        return img_b64

_cached_hardware = None

def get_system_hardware() -> dict:
    """Tự động phát hiện thông tin phần cứng GPU và VRAM của từng máy tính khác nhau (NVIDIA, AMD, Intel, etc.)"""
    global _cached_hardware
    if _cached_hardware is not None:
        return _cached_hardware

    gpu_name = "Generic GPU"
    vram_gb = None
    backend = "Vulkan / DirectX"
    has_cuda = False

    # 1. Thử nhận diện bằng nvidia-smi (chính xác tuyệt đối cho mọi dòng card NVIDIA trên mọi máy tính)
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            text=True, stderr=subprocess.DEVNULL, timeout=2
        ).strip()
        if out:
            line = out.splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            gpu_name = parts[0]
            if len(parts) > 1:
                vram_gb = round(float(parts[1]) / 1024.0, 1)
            backend = "CUDA / Tensor Core / Vulkan"
            has_cuda = True
    except Exception:
        pass

    # 2. Thử nhận diện bằng PyTorch CUDA (nếu nvidia-smi chưa có hoặc cần xác nhận thêm)
    if vram_gb is None:
        try:
            import torch
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 1)
                backend = "CUDA / Tensor Core / Vulkan"
                has_cuda = True
        except Exception:
            pass

    # 3. Thử nhận diện bằng PowerShell CIM / WMI (hoạt động 100% trên mọi máy tính Windows: AMD Radeon, Intel Arc, Intel Iris,...)
    if gpu_name == "Generic GPU" or vram_gb is None:
        try:
            cmd = "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Json"
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                text=True, encoding="utf-8", errors="ignore", timeout=3
            ).strip()
            if out:
                parsed = json.loads(out)
                items = parsed if isinstance(parsed, list) else [parsed]
                selected_item = None
                for it in items:
                    n = str(it.get("Name", "")).lower()
                    if any(k in n for k in ["rtx", "gtx", "geforce", "radeon rx", "radeon", "arc", "intel(r) arc"]):
                        selected_item = it
                        break
                if not selected_item and items:
                    selected_item = items[0]

                if selected_item:
                    detected_name = selected_item.get("Name", "")
                    if detected_name and gpu_name == "Generic GPU":
                        gpu_name = detected_name
                    raw_ram = selected_item.get("AdapterRAM")
                    if raw_ram and vram_gb is None:
                        calc_vram = round(float(raw_ram) / (1024**3), 1)
                        if calc_vram > 0.5:
                            vram_gb = calc_vram
        except Exception:
            pass

    # 4. Xác định backend tối ưu theo dòng card đồ họa của máy tính
    name_lower = gpu_name.lower()
    if has_cuda or any(k in name_lower for k in ["geforce", "rtx", "gtx", "quadro"]):
        backend = "CUDA / Tensor Core / Vulkan"
    elif any(k in name_lower for k in ["radeon", "amd"]):
        backend = "AMD ROCm / Vulkan"
    elif any(k in name_lower for k in ["arc", "intel"]):
        backend = "Intel OneAPI / Vulkan"
    else:
        backend = "Vulkan / DirectX"

    # Tên viết tắt ngắn gọn cho badge (ví dụ: 'RTX 3060', 'RTX 4070', 'RX 6700', 'Arc A770')
    gpu_short = gpu_name
    for prefix in ["NVIDIA GeForce ", "NVIDIA ", "AMD Radeon ", "Intel(R) Arc(TM) ", "Intel(R) "]:
        if gpu_short.startswith(prefix):
            gpu_short = gpu_short[len(prefix):]
            break

    _cached_hardware = {
        "gpu_name": gpu_name,
        "gpu_short": gpu_short,
        "vram_gb": vram_gb,
        "backend": backend,
        "has_cuda": has_cuda,
        "os": f"{platform.system()} {platform.release()}"
    }
    return _cached_hardware


PORT = 5000
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def save_key_to_env(api_key: str) -> str:
    """Lưu API key vào biến môi trường và file .env.local"""
    cleaned = tta.clean_api_key_string(api_key) or api_key.strip().strip('"\'')
    if not cleaned:
        return ""
    os.environ["GEMINI_API_KEY"] = cleaned
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local")
    try:
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(f"GEMINI_API_KEY={cleaned}\n")
    except Exception as e:
        print(f"[CẢNH BÁO] Không thể ghi .env.local: {e}")
    return cleaned


def remove_key_from_env():
    """Xóa API key khỏi biến môi trường và file .env.local khi người dùng đăng xuất."""
    os.environ.pop("GEMINI_API_KEY", None)
    os.environ.pop("API_KEY", None)
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local")
    try:
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("GEMINI_API_KEY=\n")
    except Exception as e:
        print(f"[CẢNH BÁO] Không thể xóa key khỏi .env.local: {e}")


class TraThuongHandler(BaseHTTPRequestHandler):
    def send_json(self, status_code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. API: Kiểm tra cấu hình API Key & Trạng thái Server
        if path in ["/api/config", "/api/status", "/api/api-key", "/api/get-key"]:
            key = tta.load_env_api_key()
            self.send_json(200, {
                "has_key": bool(key),
                "api_key": key or "",
                "status": "online",
                "backend": "python",
                "models": ["gemini-4-argon", "gemini-3.1-flash-image-preview", "gemini-2.5-flash-image"]
            })
            return

        # 1.1. API: Kiểm tra Bản quyền máy tính (Hardware ID) & Phần cứng GPU
        if path == "/api/license":
            status = lm.check_current_license()
            status["hardware"] = get_system_hardware()
            self.send_json(200, status)
            return

        # 1.2. API: Lấy thông tin phần cứng GPU động của máy tính hiện tại
        if path in ["/api/hardware", "/api/system_info"]:
            self.send_json(200, get_system_hardware())
            return

        # 1.3. API: Trạng thái tài khoản ChatGPT / Muse AI
        if path == "/api/engine-auth/status":
            mgr = cam.ChatGPTAuthManager.get_instance()
            self.send_json(200, mgr.get_status_dict())
            return

        # 1.4. API: Trạng thái Muse Studio & Chrome CDP (:9225 & :18638)
        if path == "/api/muse/status":
            self.send_json(200, cam.get_muse_status())
            return

        # 2. Phục vụ Static Files từ thư mục dist/
        req_file = path.lstrip('/')
        if not req_file or req_file == "":
            req_file = "index.html"

        file_path = os.path.join(DIST_DIR, req_file)

        # Hỗ trợ SPA routing: nếu không tìm thấy file, trả về index.html
        if not os.path.isfile(file_path):
            file_path = os.path.join(DIST_DIR, "index.html")

        if os.path.isfile(file_path):
            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                content_type = 'application/octet-stream'
            if file_path.endswith('.js'):
                content_type = 'application/javascript; charset=utf-8'
            elif file_path.endswith('.css'):
                content_type = 'text/css; charset=utf-8'
            elif file_path.endswith('.html'):
                content_type = 'text/html; charset=utf-8'

            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                self.send_json(500, {"error": f"Lỗi đọc file: {e}"})
                return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        try:
            req_json = json.loads(post_data.decode('utf-8')) if post_data else {}
        except Exception:
            self.send_json(400, {"error": "Dữ liệu JSON không hợp lệ"})
            return

        # 1. API: Lưu API Key
        if path in ["/api/save-key", "/api/api-key"]:
            api_key = req_json.get("api_key", "").strip()
            if api_key:
                save_key_to_env(api_key)
                print(f"[API] Đã cập nhật API Key thành công: {api_key[:8]}...")
                self.send_json(200, {"status": "ok", "message": "API Key đã được lưu.", "api_key": api_key})
            else:
                self.send_json(400, {"error": "API Key trống."})
            return

        # 1.1. API: Đăng xuất API Key (Xóa khỏi env và bộ nhớ)
        if path in ["/api/logout-key", "/api/delete-key"]:
            remove_key_from_env()
            print(f"[API] ✔ Đã đăng xuất Gemini API Key.")
            self.send_json(200, {"status": "ok", "message": "Đã đăng xuất Gemini API Key thành công."})
            return

        # 1.2. API: Admin tạo License Key theo ID PC
        if path == "/api/admin/generate-license":
            try:
                target_machine = req_json.get("machine_id", "").strip()
                duration = req_json.get("duration", "1M").strip()
                if not target_machine:
                    self.send_json(400, {"error": "Vui lòng nhập ID PC của khách hàng."})
                    return
                res = lm.generate_license_key(target_machine, duration)
                self.send_json(200, {
                    "status": "ok",
                    "license_key": res["license_key"],
                    "machine_id": res["machine_id"],
                    "duration_label": res["duration_label"],
                    "expiry_display": res["expiry_display"],
                    "status_message": res["status_message"]
                })
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        # 1.3. APIs: Quản lý Tài khoản ChatGPT & Grok (Kế thừa từ all-bum)
        if path.startswith("/api/engine-auth/"):
            mgr = cam.ChatGPTAuthManager.get_instance()

            if path == "/api/engine-auth/switch-engine":
                engine = req_json.get("engine", "gpt")
                if engine == "grok":
                    engine = "muse"
                mgr.active_engine = engine
                mgr.account_box_hidden = False  # Tự động mở khung tài khoản khi chuyển tab
                mgr.save_config()
                self.send_json(200, mgr.get_status_dict())
                return

            if path == "/api/engine-auth/toggle-box":
                if req_json and "hidden" in req_json:
                    mgr.account_box_hidden = bool(req_json["hidden"])
                else:
                    mgr.account_box_hidden = not mgr.account_box_hidden
                mgr.save_config()
                self.send_json(200, mgr.get_status_dict())
                return

            if path == "/api/engine-auth/chatgpt/switch-slot":
                slot = int(req_json.get("slot", 0))
                mgr.switch_account_slot(slot)
                self.send_json(200, mgr.get_status_dict())
                return

            if path == "/api/engine-auth/chatgpt/signin":
                ok, code, vurl, msg = mgr.request_device_code()
                self.send_json(200 if ok else 400, {
                    "status": "ok" if ok else "error",
                    "user_code": code,
                    "verification_url": vurl,
                    "message": msg,
                    "auth_state": mgr.get_status_dict()
                })
                return

            if path == "/api/engine-auth/chatgpt/cancel":
                mgr.cancel_polling()
                self.send_json(200, mgr.get_status_dict())
                return

            if path == "/api/engine-auth/chatgpt/signout":
                slot = int(req_json.get("slot", mgr.current_account_slot))
                mgr.signout_chatgpt(slot)
                self.send_json(200, mgr.get_status_dict())
                return

            if path == "/api/engine-auth/chatgpt/open-page":
                mgr.open_chatgpt_device_page()
                self.send_json(200, {"status": "ok"})
                return

            if path in ("/api/engine-auth/grok/switch-slot", "/api/engine-auth/muse/switch-slot"):
                slot = int(req_json.get("slot", 0))
                mgr.switch_grok_slot(slot)
                self.send_json(200, mgr.get_status_dict())
                return

            if path == "/api/engine-auth/grok/save":
                slot = int(req_json.get("slot", mgr.current_grok_slot))
                key = req_json.get("api_key", "").strip()
                name = req_json.get("name", "").strip()
                mgr.save_grok_key(slot, key, name)
                self.send_json(200, mgr.get_status_dict())
                return

            if path in ("/api/engine-auth/grok/clear", "/api/engine-auth/muse/signout"):
                slot = int(req_json.get("slot", mgr.current_grok_slot))
                mgr.signout_muse_slot(slot)
                self.send_json(200, mgr.get_status_dict())
                return

            if path == "/api/engine-auth/grok/open-page":
                mgr.open_grok_page()
                self.send_json(200, {"status": "ok"})
                return

        # 1.4. APIs: Muse AI / Muse Studio Controls (:18638 & :9225)
        if path.startswith("/api/muse/"):
            if path in ("/api/muse/chrome/show", "/api/muse/chrome/open"):
                cam.show_muse_chrome()
                self.send_json(200, {"status": "ok", "visible": True})
                return

            if path == "/api/muse/chrome/hide":
                cam.hide_muse_chrome()
                self.send_json(200, {"status": "ok", "visible": False})
                return

            if path == "/api/muse/open-page":
                cam.open_muse_page()
                self.send_json(200, {"status": "ok"})
                return

            if path == "/api/muse/sync-cookies":
                res = cam.sync_muse_cdp_cookies()
                self.send_json(200 if res.get("ok") else 400, res)
                return

            if path == "/api/muse/import-cookie":
                raw_cookie = req_json.get("cookies", "").strip()
                email = req_json.get("email", "").strip()
                res = cam.import_muse_cookie(raw_cookie, email)
                self.send_json(200 if res.get("ok") else 400, res)
                return

            if path == "/api/muse/open-extension-folder":
                folder = cam.open_extension_folder()
                self.send_json(200, {"status": "ok", "folder": folder})
                return

        # 1.5. API: Dịch thuật & chuyển đổi ngôn ngữ bằng Gemini 4 Argon
        if path == "/api/translate":
            try:
                text = req_json.get("text", "").strip()
                target_lang = req_json.get("target_lang", "KH")
                if not text:
                    self.send_json(200, {
                        "status": "ok",
                        "translated_text": "",
                        "target_lang": target_lang
                    })
                    return
                
                print(f"[Gemini-4-Argon] Bắt đầu dịch prompt sang '{target_lang}'...", flush=True)
                translated = tta.translate_with_gemini_4_argon(text, target_lang)
                print(f"[Gemini-4-Argon] ✔ Đã dịch thành công!", flush=True)
                self.send_json(200, {
                    "status": "ok",
                    "translated_text": translated,
                    "target_lang": target_lang,
                    "model": "gemini-4-argon"
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_json(500, {
                    "error": str(e)
                })
            return

        # 1.6. API: Kích hoạt bản quyền máy tính
        if path == "/api/license/activate":
            try:
                license_key = req_json.get("license_key", "").strip()
                machine_id = lm.get_machine_id()
                verification = lm.verify_license_key(machine_id, license_key)
                if verification["valid"]:
                    lm.save_license(license_key)
                    print(f"[LICENSE] ✔ Đã kích hoạt bản quyền máy {machine_id} thành công!")
                    self.send_json(200, {
                        "status": "ok",
                        "is_activated": True,
                        "machine_id": machine_id,
                        "message": verification["message"]
                    })
                else:
                    self.send_json(400, {
                        "status": "error",
                        "error": verification["message"],
                        "machine_id": machine_id
                    })
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        # 1.7. API: Đăng xuất / Hủy kích hoạt bản quyền máy tính
        if path in ["/api/license/deactivate", "/api/license/logout"]:
            try:
                lm.remove_license()
                print("[LICENSE] ✔ Đã đăng xuất bản quyền máy tính.")
                self.send_json(200, {
                    "status": "ok",
                    "is_activated": False,
                    "message": "Đã đăng xuất bản quyền trên máy tính này thành công."
                })
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        # 2. API: Tạo ảnh bằng Gemini qua Python Core
        if path == "/api/generate":
            try:
                # KIỂM TRA BẢN QUYỀN MÁY TÍNH
                lic = lm.check_current_license()
                if not lic["is_activated"]:
                    self.send_json(403, {
                        "error": f"Phần mềm chưa được kích hoạt bản quyền trên máy tính này!\nMã máy của bạn: {lic['machine_id']}\nVui lòng liên hệ Trà Thương để nhận mã kích hoạt."
                    })
                    return

                config_data = req_json.get("config", {})
                mode_str = str(req_json.get("mode", "")).strip().upper()
                if not mode_str:
                    mode_str = str(config_data.get("currentMode", tta.AppMode.AI_WEDDING.value)).strip().upper()

                is_upscale = ("UPSCALE" in mode_str)
                is_portrait_beauty = ("PORTRAIT_BEAUTY" in mode_str)

                # 1. Chế độ NÂNG CẤP ĐỘ PHÂN GIẢI (UPSCALE): Xử lý bằng SeedVR2 DiT AI Diffusion (RTX 3060 CUDA) - 100% OFFLINE
                if is_upscale or mode_str == tta.AppMode.UPSCALE.value:
                    uploaded_img = config_data.get("uploadedImage")
                    if not uploaded_img:
                        self.send_json(400, {"error": "Vui lòng tải ảnh lên để nâng cấp độ phân giải (Upscale)."})
                        return

                    import upscale_engine as ue
                    upscale_cfg = config_data.get("upscale", {})
                    upscale_mode = upscale_cfg.get("mode", "seedvr2_ai")
                    scale = upscale_cfg.get("scale", "4x")
                    target_res = upscale_cfg.get("targetRes", "4K")
                    sharpness = int(upscale_cfg.get("sharpness", 50))
                    denoise = int(upscale_cfg.get("denoise", 0))
                    enhance_face = bool(upscale_cfg.get("enhanceFace", True))

                    print(f"[PYTHON BACKEND] 🚀 Đang Upscale AI (Engine={upscale_mode}, Scale={scale}, Sharpness={sharpness}%, Denoise={denoise}%)...")
                    try:
                        res_b64, meta = ue.upscale_to_base64(
                            uploaded_img,
                            mode=upscale_mode,
                            scale=scale,
                            target_res=target_res,
                            sharpness=sharpness,
                            denoise=denoise,
                            enhance_face=enhance_face
                        )
                        print(f"[PYTHON BACKEND] ✔ Upscale thành công: {meta['original_width']}x{meta['original_height']} -> {meta['upscaled_width']}x{meta['upscaled_height']} ({meta['scale_factor']}) [{meta.get('engine', '')}]")

                        self.send_json(200, {
                            "status": "ok",
                            "images": [res_b64],
                            "metadata": meta
                        })
                    except Exception as exc:
                        import traceback
                        traceback.print_exc()
                        self.send_json(500, {
                            "error": f"Lỗi khi Upscale ảnh cục bộ: {str(exc)}"
                        })
                    return

                # 2. Chế độ LÀM ĐẸP CHÂN DUNG: Xử lý 100% CỤC BỘ (Offline - KHÔNG CẦN API)
                if is_portrait_beauty or mode_str == tta.AppMode.PORTRAIT_BEAUTY.value:
                    uploaded_img = config_data.get("uploadedImage")
                    if not uploaded_img:
                        self.send_json(400, {"error": "Vui lòng tải ảnh lên để làm đẹp chân dung."})
                        return

                    import portrait_engine as pe
                    print("[PYTHON BACKEND] ✨ Đang làm đẹp chân dung cục bộ (Offline - KHÔNG CẦN API)...")
                    try:
                        bgr = pe.load_bgr_from_data_url_or_path(uploaded_img)
                        pb_dict = config_data.get("portraitBeauty", {})
                        retouched_bgr = pe.retouch_portrait_local(bgr, pb_dict)
                        res_b64 = pe.bgr_to_base64_data_url(retouched_bgr, quality=95)
                        print("[PYTHON BACKEND] ✔ Hoàn tất làm đẹp chân dung cục bộ tức thì!")

                        self.send_json(200, {
                            "status": "ok",
                            "images": [res_b64]
                        })
                    except Exception as exc:
                        import traceback
                        traceback.print_exc()
                        self.send_json(500, {
                            "error": f"Lỗi làm đẹp chân dung cục bộ: {str(exc)}"
                        })
                    return

                # 3. KIỂM TRA ĐỘNG CƠ TẠO ẢNH: ChatGPT / Gemini Cloud
                auth_mgr = cam.ChatGPTAuthManager.get_instance()
                auth_mgr.load_config()
                active_engine = auth_mgr.active_engine
                active_cg = auth_mgr.chatgpt_accounts[auth_mgr.current_account_slot]
                valid_cg = next((a for a in auth_mgr.chatgpt_accounts if a.get("access_token")), active_cg)
                is_chatgpt_ready = bool(valid_cg.get("logged_in") and valid_cg.get("access_token"))

                desc_text = config_data.get("description", "")
                scene_text = config_data.get("scene", "Sân khấu đám cưới")
                doc_width = int(config_data.get("doc_width", 0))
                doc_height = int(config_data.get("doc_height", 0))
                raw_ratio = str(config_data.get("aspectRatio", "GỐC")).upper()
                if "16:9" in raw_ratio:
                    aspect_ratio_str = "16:9"
                elif "1:1" in raw_ratio:
                    aspect_ratio_str = "1:1"
                elif "9:16" in raw_ratio:
                    aspect_ratio_str = "9:16"
                elif "3:4" in raw_ratio:
                    aspect_ratio_str = "3:4"
                else:
                    aspect_ratio_str = "AUTO"

                num_images = max(1, min(4, int(config_data.get("numImages", 1))))
                uploaded_b64 = config_data.get("uploadedImage")
                background_b64 = config_data.get("backgroundImage")

                # 3.1. NẾU CHỌN TAB CHATGPT (GPT IMAGE)
                if active_engine == "gpt":
                    if is_chatgpt_ready:
                        print(f"[PYTHON BACKEND] 🚀 Đang tạo ảnh trực tiếp qua tài khoản ChatGPT ({valid_cg.get('email', 'aothunkhmer@gmail.com')}) - {num_images} ảnh...")
                        generated_list = []
                        for v_idx in range(num_images):
                            img_res = cam.generate_image_with_chatgpt(
                                prompt=desc_text,
                                scene=scene_text,
                                mode_str=mode_str,
                                aspect_ratio=aspect_ratio_str,
                                uploaded_image_b64=uploaded_b64,
                                background_image_b64=background_b64,
                                variation_index=v_idx
                            )
                            generated_list.append(img_res)
                        if doc_width > 0 and doc_height > 0:
                            print(f"[PYTHON BACKEND] 📐 Co giãn {len(generated_list)} ảnh AI sang kích thước canvas Photoshop: {doc_width}x{doc_height}...")
                            generated_list = [resize_image_to_dimensions(img, doc_width, doc_height) for img in generated_list]

                        print(f"[PYTHON BACKEND] ✔ Tạo hoàn tất {len(generated_list)} ảnh qua ChatGPT!")
                        self.send_json(200, {
                            "status": "ok",
                            "images": generated_list
                        })
                        return
                    else:
                        self.send_json(400, {
                            "error": "Tài khoản ChatGPT chưa được đăng nhập.\n\n👉 Vui lòng bấm nút 'Đăng nhập ChatGPT' phía trên để kết nối tài khoản trên ứng dụng!"
                        })
                        return

                # 3.2. NẾU CHỌN TAB GEMINI WEB (GEMINI WEB)
                elif active_engine in ["muse", "grok"]:
                    print(f"[PYTHON BACKEND] 🚀 Đang tạo ảnh tự động qua Gemini Web - {num_images} ảnh...")
                    try:
                        import gemini_web_engine
                        generated_list = []
                        for v_idx in range(num_images):
                            img_res = gemini_web_engine.generate_image_with_gemini_web(
                                prompt=desc_text,
                                scene=scene_text,
                                aspect_ratio=aspect_ratio_str,
                                uploaded_image_b64=uploaded_b64
                            )
                            generated_list.append(img_res)
                        if doc_width > 0 and doc_height > 0:
                            print(f"[PYTHON BACKEND] 📐 Co giãn {len(generated_list)} ảnh AI sang kích thước canvas Photoshop: {doc_width}x{doc_height}...")
                            generated_list = [resize_image_to_dimensions(img, doc_width, doc_height) for img in generated_list]

                        print(f"[PYTHON BACKEND] ✔ Tạo hoàn tất {len(generated_list)} ảnh qua Gemini Web!")
                        self.send_json(200, {
                            "status": "ok",
                            "images": generated_list
                        })
                        return
                    except Exception as gemini_err:
                        err_text = str(gemini_err)
                        print(f"[PYTHON BACKEND] ❌ Lỗi tạo ảnh Gemini Web: {err_text}")
                        if "chưa được đăng nhập" in err_text.lower() or "đăng nhập" in err_text.lower():
                            try:
                                cam.show_muse_chrome()
                            except Exception:
                                pass
                        self.send_json(400, {
                            "error": err_text
                        })
                        return

                # 3.3. NẾU CHỌN TAB CẤU HÌNH API (Google AI Studio Key)
                else:
                    api_key = tta.load_env_api_key()
                    if not api_key:
                        self.send_json(400, {
                            "error": "Bạn đang chọn chế độ 'CẤU HÌNH API' nhưng chưa có Google Gemini API Key.\n\n👉 Vui lòng bấm nút 'CẤU HÌNH API' trên thanh công cụ và dán mã API Key của bạn từ Google AI Studio!"
                        })
                        return

                try:
                    mode = tta.AppMode(mode_str)
                except ValueError:
                    mode = tta.AppMode.AI_WEDDING

                # Ánh xạ an toàn aspectRatio cho Gemini Cloud API
                raw_ar = str(config_data.get("aspectRatio", "")).upper()
                if "16:9" in raw_ar:
                    resolved_ar = tta.AspectRatio.LANDSCAPE
                elif "1:1" in raw_ar:
                    resolved_ar = tta.AspectRatio.SQUARE
                elif "9:16" in raw_ar:
                    resolved_ar = tta.AspectRatio.MOBILE
                elif "3:4" in raw_ar:
                    resolved_ar = tta.AspectRatio.PORTRAIT
                else:
                    if doc_width > 0 and doc_height > 0:
                        if doc_width > doc_height:
                            resolved_ar = tta.AspectRatio.LANDSCAPE
                        elif abs(doc_width - doc_height) < 10:
                            resolved_ar = tta.AspectRatio.SQUARE
                        elif doc_height / doc_width > 1.6:
                            resolved_ar = tta.AspectRatio.MOBILE
                        else:
                            resolved_ar = tta.AspectRatio.PORTRAIT
                    else:
                        resolved_ar = tta.AspectRatio.PORTRAIT

                # Ánh xạ an toàn imageSize (hỗ trợ cả 8K)
                raw_sz = str(config_data.get("imageSize", "4K")).upper()
                if "1K" in raw_sz:
                    resolved_sz = tta.ImageSize.SIZE_1K
                elif "2K" in raw_sz:
                    resolved_sz = tta.ImageSize.SIZE_2K
                elif "6K" in raw_sz or "8K" in raw_sz:
                    resolved_sz = tta.ImageSize.SIZE_6K
                else:
                    resolved_sz = tta.ImageSize.SIZE_4K

                # Ánh xạ an toàn country
                raw_country = str(config_data.get("country", tta.Country.VIETNAM.value))
                try:
                    resolved_country = tta.Country(raw_country)
                except Exception:
                    resolved_country = tta.Country.VIETNAM

                # Ánh xạ GenerationConfig cho các chế độ Gemini AI Cloud
                gen_config = tta.GenerationConfig(
                    country=resolved_country,
                    scene=config_data.get("scene", "Sân khấu đám cưới"),
                    description=config_data.get("description", ""),
                    lighting=config_data.get("lighting", "Nắng nhẹ"),
                    foreground=config_data.get("foreground", "Hoa"),
                    aspectRatio=resolved_ar,
                    imageSize=resolved_sz,
                    numImages=int(config_data.get("numImages", 1)),
                    uploadedImage=config_data.get("uploadedImage"),
                    backgroundImage=config_data.get("backgroundImage"),
                    keepOriginalClothing=bool(config_data.get("keepOriginalClothing", True)),
                    mode=config_data.get("mode", "CHUNG"),
                    removeObjectPrompt=config_data.get("removeObjectPrompt")
                )

                if "portraitBeauty" in config_data and config_data["portraitBeauty"]:
                    pb_data = config_data["portraitBeauty"]
                    pb = tta.PortraitBeautyConfig()
                    if "autoFix" in pb_data:
                        pb.autoFix = tta.PortraitBeautyAutoFix(**pb_data["autoFix"])
                    if "hair" in pb_data:
                        pb.hair = tta.PortraitBeautyHair(**pb_data["hair"])
                    if "details" in pb_data:
                        pb.details = tta.PortraitBeautyDetails(**pb_data["details"])
                    gen_config.portraitBeauty = pb

                if "restoreOld" in config_data and config_data["restoreOld"]:
                    gen_config.restoreOld = tta.RestoreOldConfig(**config_data["restoreOld"])

                try:
                    print(f"[PYTHON BACKEND] Bắt đầu tạo ảnh cho chế độ: {mode.value}")
                    results = tta.generate_ai_images(gen_config, mode)
                    images_b64 = [res.to_base64_data_url() for res in results]
                    if doc_width > 0 and doc_height > 0:
                        print(f"[PYTHON BACKEND] 📐 Co giãn {len(images_b64)} ảnh AI sang kích thước canvas Photoshop: {doc_width}x{doc_height}...")
                        images_b64 = [resize_image_to_dimensions(img, doc_width, doc_height) for img in images_b64]

                    print(f"[PYTHON BACKEND] Tạo thành công {len(images_b64)} ảnh.")

                    self.send_json(200, {
                        "status": "ok",
                        "images": images_b64
                    })
                except Exception as gemini_err:
                    err_msg = str(gemini_err)
                    print(f"[PYTHON BACKEND] ❌ Lỗi tạo ảnh Gemini API: {err_msg}")
                    self.send_json(400, {
                        "error": f"Lỗi tạo ảnh Google AI Studio (Gemini API):\n{err_msg}"
                    })
                    return
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_json(500, {
                    "error": str(e)
                })
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        # Giảm thiểu log rác trong console
        pass


def launch_app_window(url: str):
    """Mở ứng dụng dưới dạng cửa sổ Desktop độc lập hoặc trình duyệt."""
    browser_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    for p in browser_paths:
        if os.path.exists(p):
            try:
                # Chạy ở chế độ --app để tạo cửa sổ ứng dụng desktop đẹp không có thanh địa chỉ
                subprocess.Popen([p, f"--app={url}", "--window-size=1400,900", "--disable-features=Translate", "--disable-translate"])
                return
            except Exception:
                pass

    # Nếu không mở được bằng App mode, mở bằng trình duyệt mặc định
    webbrowser.open(url)


def run_server(port: int = PORT):
    # 1. Kiểm tra nếu cổng đã có máy chủ Trà Thương Pro AI đang chạy
    if is_port_in_use(port):
        try:
            import urllib.request
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/config", timeout=1) as r:
                if r.status == 200:
                    url = f"http://0.0.0.0:{port}"
                    print(f"[HỆ THỐNG] Máy chủ Trà Thương Pro AI đã đang chạy tại {url}!", flush=True)
                    print("-> Đang tự động mở lại cửa sổ ứng dụng...", flush=True)
                    # launch_app_window(url) [Cloud Docker Mode]
                    return
        except Exception:
            pass

        # Nếu bị xung đột với cổng khác, tự động nhảy sang cổng khả dụng
        orig_port = port
        while is_port_in_use(port) and port < orig_port + 10:
            port += 1
        if port != orig_port:
            print(f"[HỆ THỐNG] Cổng {orig_port} bận, tự động chuyển sang cổng: {port}", flush=True)

    # 2. Kiểm tra xem dist đã được build chưa
    if not os.path.isdir(DIST_DIR) or not os.path.isfile(os.path.join(DIST_DIR, "index.html")):
        print("[HỆ THỐNG] Đang biên dịch frontend ban đầu...", flush=True)
        # Skip npm on cloud

    port = int(os.environ.get('PORT', 7860))
    server_address = ('0.0.0.0', port)
    httpd = ThreadedHTTPServer(server_address, TraThuongHandler)
    url = f"http://0.0.0.0:{port}"

    print("=" * 65, flush=True)
    print("      TRÀ THƯƠNG PRO AI - PHIÊN BẢN GIAO DIỆN NGUYÊN BẢN", flush=True)
    print("=" * 65, flush=True)
    print(f"-> Máy chủ Python đang chạy tại: {url}", flush=True)
    print("-> Đang tự động mở cửa sổ giao diện Trà Thương Pro AI...", flush=True)
    print("-> Nhấn Ctrl + C để dừng máy chủ.", flush=True)
    print("=" * 65, flush=True)

    # Tự động kích hoạt Muse Studio Server (:18638) ngầm
    import threading
    threading.Thread(target=ensure_muse_server, daemon=True).start()

    # launch_app_window(url) [Cloud Docker Mode]

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nĐang tắt máy chủ...", flush=True)
        httpd.server_close()


if __name__ == "__main__":
    run_server()

