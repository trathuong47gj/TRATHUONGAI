"""
Trà Thương Pro AI - ChatGPT & Grok Auth Manager
Kế thừa và đồng bộ từ hệ thống Quản lý Tài khoản (ChatGPT Device Auth & Grok AI) của all-bum:
- Quản lý 3 Slot tài khoản ChatGPT (OAuth Device Code chính thức từ auth.openai.com)
- Quản lý 3 Slot tài khoản Grok AI (xAI API Key)
- Tự động lấy user_code, mở trang xác thực, polling nhận token và lưu trữ an toàn
- Hỗ trợ ẩn/hiện bảng tài khoản, che/hiện email bảo mật
"""

import os
import sys
import json
import time
import base64
import io
import urllib.request
import urllib.parse
import urllib.error
import threading
import webbrowser
import subprocess
from typing import Dict, Any, Optional
from PIL import Image, ImageOps

def normalize_image_to_jpeg_b64(b64_str: Optional[str], max_dimension: int = 2048) -> Optional[str]:
    """Chuẩn hóa mọi định dạng ảnh (PNG, WEBP, CMYK, RGBA, 16-bit) về chuẩn RGB JPEG cho OpenAI."""
    if not b64_str:
        return None
    try:
        clean = b64_str
        if "base64," in clean:
            clean = clean.split("base64,")[1]
        raw_bytes = base64.b64decode(clean.strip())
        img = Image.open(io.BytesIO(raw_bytes))
        
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        if max(w, h) > max_dimension:
            scale = max_dimension / max(w, h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=92, optimize=True)
        return base64.b64encode(out_buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"[AuthManager] Cảnh báo chuẩn hóa ảnh: {e}")
        if "base64," in b64_str:
            return b64_str.split("base64,")[1]
        return b64_str

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AUTH_BASE = "https://auth.openai.com"
USER_AGENT = "codex_cli_rs/0.130.0 (Windows)"


class ChatGPTAuthManager:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chatgpt_profiles")
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        self.config_file = os.path.join(self.base_dir, "accounts_v2.json")

        self.active_engine = "gpt"  # "gpt" | "muse" | "api"
        self.account_box_hidden = False

        self.current_account_slot = 0
        self.chatgpt_accounts = [
            {"email": "aounkhmer@gmail.com", "logged_in": True, "access_token": "", "refresh_token": ""},
            {},
            {}
        ]

        self.current_grok_slot = 0
        self.grok_accounts = [{}, {}, {}]

        self.current_device_auth_id: Optional[str] = None
        self.current_user_code: Optional[str] = None
        self.verification_url: str = "https://auth.openai.com/codex/device"
        self.is_polling: bool = False
        self.polling_status: str = "Đã đăng xuất."
        self.poll_thread: Optional[threading.Thread] = None

        self.load_config()

    def load_config(self):
        # 1. Thử đọc từ config_file hiện tại
        if os.path.isfile(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.active_engine = data.get("active_engine", "gpt")
                    self.account_box_hidden = bool(data.get("account_box_hidden", False))
                    self.current_account_slot = int(data.get("current_account_slot", 0))
                    self.current_grok_slot = int(data.get("current_grok_slot", 0))

                    cg_accs = data.get("chatgpt_accounts", [])
                    if isinstance(cg_accs, list) and len(cg_accs) > 0:
                        for i in range(min(3, len(cg_accs))):
                            if isinstance(cg_accs[i], dict):
                                acc = cg_accs[i]
                                acc_id = acc.get("account_id") or acc.get("chatgpt_account_id")
                                if acc_id:
                                    acc["account_id"] = acc_id
                                self.chatgpt_accounts[i] = acc

                    gk_accs = data.get("grok_accounts", [])
                    if isinstance(gk_accs, list) and len(gk_accs) > 0:
                        for i in range(min(3, len(gk_accs))):
                            if isinstance(gk_accs[i], dict):
                                self.grok_accounts[i] = gk_accs[i]

                    active_cg = self.chatgpt_accounts[self.current_account_slot]
                    if active_cg.get("logged_in") and (active_cg.get("access_token") or active_cg.get("email")):
                        self.polling_status = f"Đã đăng nhập thành công Tài khoản {self.current_account_slot + 1}!"
                    return
            except Exception as e:
                print(f"[AuthManager] Lỗi đọc {self.config_file}: {e}")

        # 2. Nếu chưa có, đồng bộ thử từ C:\Users\POI\Desktop\all-bum\chatgpt_profiles
        fallback_dir = r"C:\Users\POI\Desktop\all-bum\chatgpt_profiles"
        if os.path.isdir(fallback_dir):
            fb_acc = os.path.join(fallback_dir, "accounts.json")
            if os.path.isfile(fb_acc):
                try:
                    with open(fb_acc, "r", encoding="utf-8") as f:
                        acc_data = json.load(f)
                        if acc_data and isinstance(acc_data, dict):
                            self.chatgpt_accounts[0] = acc_data
                except Exception:
                    pass

    def save_config(self):
        data = {
            "active_engine": self.active_engine,
            "account_box_hidden": self.account_box_hidden,
            "current_account_slot": self.current_account_slot,
            "current_grok_slot": self.current_grok_slot,
            "chatgpt_accounts": self.chatgpt_accounts,
            "grok_accounts": self.grok_accounts
        }
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[AuthManager] Lỗi lưu {self.config_file}: {e}")

    @staticmethod
    def _json_request(url: str, payload: dict, headers: Optional[dict] = None, timeout: int = 25) -> dict:
        req_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "originator": "codex_cli_rs",
            "version": "0.130.0",
            "User-Agent": USER_AGENT
        }
        if headers:
            req_headers.update(headers)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _jwt_payload(token: str) -> dict:
        try:
            parts = token.split(".")
            if len(parts) >= 2:
                raw = parts[1]
                raw += "=" * ((4 - len(raw) % 4) % 4)
                return json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
        except Exception:
            pass
        return {}

    def request_device_code(self) -> tuple[bool, str, str, str]:
        """
        Gửi yêu cầu lấy mã Device Code tới auth.openai.com
        Trả về (success, user_code, verification_url, message)
        """
        self.cancel_polling()
        url = f"{AUTH_BASE}/api/accounts/deviceauth/usercode"
        try:
            data = self._json_request(url, {"client_id": CLIENT_ID}, timeout=15)
            user_code = data.get("user_code") or data.get("usercode")
            device_id = data.get("device_auth_id")
            if not user_code or not device_id:
                return False, "", "", "Máy chủ OpenAI không trả về mã thiết bị hợp lệ."

            self.current_device_auth_id = device_id
            self.current_user_code = user_code
            self.verification_url = f"{AUTH_BASE}/codex/device"
            self.polling_status = "Đang chờ xác nhận từ trình duyệt..."

            # Khởi động thread polling tự động
            self.start_polling()

            return True, user_code, self.verification_url, "Lấy mã thành công"
        except urllib.error.HTTPError as he:
            body = he.read().decode("utf-8", errors="ignore")
            return False, "", "", f"Lỗi kết nối OpenAI ({he.code}): {body[:150]}"
        except Exception as e:
            return False, "", "", f"Lỗi: {str(e)}"

    def start_polling(self):
        if not self.current_device_auth_id or not self.current_user_code:
            return

        self.cancel_polling()
        self.is_polling = True

        def poll_worker():
            device_id = self.current_device_auth_id
            user_code = self.current_user_code
            token_url = f"{AUTH_BASE}/api/accounts/deviceauth/token"
            started = time.time()
            attempt = 0
            authorization = None

            while self.is_polling and time.time() - started < 900:
                attempt += 1
                self.polling_status = f"Đang chờ xác nhận… lần {attempt}"

                try:
                    authorization = self._json_request(
                        token_url,
                        {"device_auth_id": device_id, "user_code": user_code},
                        timeout=15
                    )
                    if authorization.get("authorization_code") and authorization.get("code_verifier"):
                        break
                except urllib.error.HTTPError as exc:
                    body = exc.read().decode("utf-8", errors="replace")
                    if exc.code not in (403, 404) or "pending" not in body.lower():
                        self.polling_status = f"Lỗi xác thực ({exc.code}): {body[:100]}"
                        self.is_polling = False
                        return
                except Exception:
                    pass

                time.sleep(5)

            if not self.is_polling:
                return

            if not authorization or not authorization.get("authorization_code"):
                self.polling_status = "Hết thời gian chờ đăng nhập (15 phút)."
                self.is_polling = False
                return

            self.polling_status = "Đã xác nhận! Đang hoàn tất lưu tài khoản..."

            # Đổi token lấy Access Token
            try:
                form = urllib.parse.urlencode({
                    "grant_type": "authorization_code",
                    "code": authorization["authorization_code"],
                    "redirect_uri": f"{AUTH_BASE}/deviceauth/callback",
                    "client_id": CLIENT_ID,
                    "code_verifier": authorization["code_verifier"],
                }).encode("utf-8")

                req = urllib.request.Request(
                    f"{AUTH_BASE}/oauth/token",
                    data=form,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                        "originator": "codex_cli_rs",
                        "version": "0.130.0",
                        "User-Agent": USER_AGENT
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    token = json.loads(response.read().decode("utf-8"))

                access_token = token.get("access_token", "")
                id_token = token.get("id_token", "")
                claims = self._jwt_payload(id_token)
                auth_claims = claims.get("https://api.openai.com/auth", {})
                account_id = auth_claims.get("chatgpt_account_id") or auth_claims.get("account_id")
                email = claims.get("email") or "aounkhmer@gmail.com"

                account_info = {
                    "access_token": access_token,
                    "refresh_token": token.get("refresh_token", ""),
                    "id_token": id_token,
                    "account_id": account_id,
                    "email": email,
                    "logged_in": True,
                    "expires_at": int(time.time()) + int(token.get("expires_in") or 3600),
                }

                self.chatgpt_accounts[self.current_account_slot] = account_info
                self.save_config()

                self.polling_status = f"Đã đăng nhập thành công Tài khoản {self.current_account_slot + 1}!"
                self.is_polling = False
            except Exception as e:
                self.polling_status = f"Lỗi hoàn tất token: {str(e)}"
                self.is_polling = False

        self.poll_thread = threading.Thread(target=poll_worker, daemon=True)
        self.poll_thread.start()

    def cancel_polling(self):
        self.is_polling = False
        self.poll_thread = None
        self.polling_status = "Đã hủy đăng nhập."

    def signout_chatgpt(self, slot: Optional[int] = None):
        target_slot = self.current_account_slot if slot is None else slot
        if 0 <= target_slot < 3:
            self.chatgpt_accounts[target_slot] = {
                "slot": target_slot,
                "email": "",
                "logged_in": False,
                "plan": "Pro/Plus"
            }
            # Cập nhật cả file backup để không bị phục hồi lại tài khoản đã đăng xuất
            backup_file = os.path.join(os.path.dirname(self.config_file), "accounts_backup.json")
            if os.path.isfile(backup_file):
                try:
                    with open(backup_file, "r", encoding="utf-8") as bf:
                        b_data = json.load(bf)
                    if b_data.get("chatgpt_accounts") and target_slot < len(b_data["chatgpt_accounts"]):
                        b_data["chatgpt_accounts"][target_slot] = {}
                    with open(backup_file, "w", encoding="utf-8") as bf:
                        json.dump(b_data, bf, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            self.save_config()
            self.cancel_polling()
            self.polling_status = "Đã đăng xuất."

    def switch_account_slot(self, slot: int):
        if 0 <= slot < 3:
            self.current_account_slot = slot
            self.save_config()
            active_acc = self.chatgpt_accounts[slot]
            if active_acc.get("logged_in") and active_acc.get("email"):
                self.polling_status = f"Đã đăng nhập thành công Tài khoản {slot + 1}!"
            else:
                self.polling_status = "Đã đăng xuất."

    def switch_grok_slot(self, slot: int):
        if 0 <= slot < 3:
            self.current_grok_slot = slot
            self.save_config()

    def switch_muse_slot(self, slot: int):
        self.switch_grok_slot(slot)

    def signout_muse_slot(self, slot: int):
        if 0 <= slot < 3:
            self.grok_accounts[slot] = {
                "slot": slot,
                "name": f"Gemini TK {slot + 1}",
                "email": "",
                "logged_in": False,
                "has_key": False
            }
            self.save_config()
            try:
                sys.path.insert(0, r"C:\Users\POI\Desktop\New folder (5)")
                import muse_store
                st = muse_store.MuseStore()
                for a in st.list_accounts():
                    st.delete_account(a["id"])
            except Exception:
                pass

    def save_grok_key(self, slot: int, api_key: str, name: str = ""):
        if 0 <= slot < 3:
            self.grok_accounts[slot] = {
                "api_key": api_key.strip(),
                "name": name.strip() or f"Grok TK {slot + 1}",
                "connected": bool(api_key.strip())
            }
            self.save_config()

    def clear_grok_key(self, slot: int):
        if 0 <= slot < 3:
            self.grok_accounts[slot] = {}
            self.save_config()

    def open_chatgpt_device_page(self):
        url = self.verification_url or "https://auth.openai.com/codex/device"
        try:
            webbrowser.open(url)
        except Exception:
            subprocess.Popen(["start", url], shell=True)

    def open_grok_page(self):
        url = "https://gemini.google.com/app?hl=vi"
        try:
            webbrowser.open(url)
        except Exception:
            subprocess.Popen(["start", url], shell=True)

    def open_muse_page(self):
        url = "https://gemini.google.com/app?hl=vi"
        try:
            webbrowser.open(url)
        except Exception:
            subprocess.Popen(["start", url], shell=True)

    def get_status_dict(self) -> Dict[str, Any]:
        active_cg = self.chatgpt_accounts[self.current_account_slot]

        # Tự động đồng bộ trạng thái Muse nếu đã có session live trong MuseStore
        if self.active_engine in ("muse", "grok"):
            try:
                sys.path.insert(0, r"C:\Users\POI\Desktop\New folder (5)")
                import muse_store
                st = muse_store.MuseStore()
                live_acc = next((a for a in st.list_accounts() if a.get("status") == "live" and any(c.get("name") in ("hatch_sess", "hatch_vml") for c in a.get("cookies", []))), None)
                if live_acc:
                    em = live_acc.get("email") or self.chatgpt_accounts[0].get("email") or "aothunkhmer@gmail.com"
                    slot_data = self.grok_accounts[self.current_grok_slot]
                    if not slot_data.get("logged_in") or slot_data.get("email") != em:
                        self.grok_accounts[self.current_grok_slot] = {
                            "slot": self.current_grok_slot,
                            "name": f"Muse TK {self.current_grok_slot + 1}",
                            "email": em,
                            "logged_in": True,
                            "has_key": True
                        }
                        self.save_config()
            except Exception:
                pass

        active_grok = self.grok_accounts[self.current_grok_slot]

        return {
            "active_engine": self.active_engine,
            "account_box_hidden": self.account_box_hidden,
            "current_account_slot": self.current_account_slot,
            "chatgpt_accounts": [
                {
                    "slot": i,
                    "email": acc.get("email", ""),
                    "logged_in": bool(acc.get("logged_in") or acc.get("email")),
                    "plan": acc.get("chatgpt_plan_type", "Pro/Plus")
                }
                for i, acc in enumerate(self.chatgpt_accounts)
            ],
            "active_chatgpt": {
                "email": active_cg.get("email", ""),
                "logged_in": bool(active_cg.get("logged_in") or active_cg.get("email")),
            },
            "current_user_code": self.current_user_code or "---- - ----",
            "is_polling": self.is_polling,
            "polling_status": self.polling_status,
            "current_grok_slot": self.current_grok_slot,
            "grok_accounts": [
                {
                    "slot": i,
                    "name": acc.get("name", f"Muse TK {i + 1}"),
                    "email": acc.get("email", ""),
                    "logged_in": bool(acc.get("logged_in") or acc.get("email")),
                    "api_key_masked": (acc.get("api_key")[:7] + "..." + acc.get("api_key")[-4:]) if acc.get("api_key") else "",
                    "has_key": bool(acc.get("logged_in") or acc.get("email") or acc.get("api_key"))
                }
                for i, acc in enumerate(self.grok_accounts)
            ],
            "active_grok": {
                "name": active_grok.get("name", f"Muse TK {self.current_grok_slot + 1}"),
                "email": active_grok.get("email", ""),
                "logged_in": bool(active_grok.get("logged_in") or active_grok.get("email")),
                "api_key": active_grok.get("api_key", ""),
                "has_key": bool(active_grok.get("logged_in") or active_grok.get("email") or active_grok.get("api_key"))
            }
        }


def generate_image_with_chatgpt(
    prompt: str = "",
    scene: str = "",
    mode_str: str = "AI_WEDDING",
    aspect_ratio: str = "3:4",
    uploaded_image_b64: Optional[str] = None,
    background_image_b64: Optional[str] = None,
    variation_index: int = 0
) -> str:
    """
    Tạo ảnh trực tiếp qua tài khoản ChatGPT đã đăng nhập bằng Codex GPT-Image-2.
    Trả về chuỗi data:image/jpeg;base64,...
    """
    mgr = ChatGPTAuthManager.get_instance()
    active_acc = mgr.chatgpt_accounts[mgr.current_account_slot]
    access_token = active_acc.get("access_token")
    account_id = active_acc.get("account_id")

    if not access_token or not account_id:
        for acc in mgr.chatgpt_accounts:
            if acc.get("access_token") and acc.get("account_id"):
                access_token = acc.get("access_token")
                account_id = acc.get("account_id")
                break

    if not access_token or not account_id:
        raise ValueError("Bạn chưa đăng nhập ChatGPT hoặc phiên đăng nhập đã hết hạn. Vui lòng bấm 'Đăng nhập ChatGPT' trước khi tạo ảnh.")

    var_styles = [
        "masterpiece luxury studio lighting, balanced composition, 8k photorealistic",
        "romantic soft ambient illumination, delicate bokeh, hyper-detailed textures 8k",
        "cinematic golden studio glow, grand festive wedding background, ultra-sharp 8k",
        "vibrant studio contrast, elegant depth of field, flawless high fidelity 8k"
    ]
    chosen_style = var_styles[variation_index % len(var_styles)]
    var_text = f"Variation {variation_index + 1} ({chosen_style}): " if variation_index > 0 else ""

    ratio_directives = {
        "AUTO": "STRICT ASPECT RATIO & FRAMING LOCK: Maintain the exact canvas proportions, framing, composition, and scale of the original photo without any cropping or shifting",
        "GỐC": "STRICT ASPECT RATIO & FRAMING LOCK: Maintain the exact canvas proportions, framing, composition, and scale of the original photo without any cropping or shifting",
        "3:4": "Aspect ratio 3:4 portrait orientation",
        "1:1": "Aspect ratio 1:1 square format",
        "16:9": "Aspect ratio 16:9 widescreen landscape",
        "9:16": "Aspect ratio 9:16 mobile vertical format",
    }
    ratio_directive = ratio_directives.get(aspect_ratio, f"Aspect ratio: {aspect_ratio}")
    scene_desc = scene if scene else "Luxury Wedding Studio Backdrop"

    if uploaded_image_b64:
        clean_b64 = normalize_image_to_jpeg_b64(uploaded_image_b64) or uploaded_image_b64
        if "base64," in clean_b64:
            clean_b64 = clean_b64.split("base64,")[1]

        endpoint = "https://chatgpt.com/backend-api/codex/images/edits"
        images_list = [{"image_url": f"data:image/jpeg;base64,{clean_b64}"}]

        if background_image_b64:
            clean_bg = normalize_image_to_jpeg_b64(background_image_b64)
            if clean_bg:
                if "base64," in clean_bg:
                    clean_bg = clean_bg.split("base64,")[1]
                images_list.append({"image_url": f"data:image/jpeg;base64,{clean_bg}"})
            prompt_text = (
                f"{var_text}STRICT INPAINTING & SEAMLESS BACKGROUND INTEGRATION: "
                f"{ratio_directive}. "
                f"Image 1 contains the original wedding couple. "
                f"Image 2 contains the target background backdrop. "
                f"MANDATE: 100% PRESERVE THE EXACT ORIGINAL HUMAN IDENTITIES AND COMPOSITION from Image 1: "
                f"Keep the bride and groom in their EXACT SAME POSITIONS, EXACT SAME SPATIAL FRAMING, SIZES, AND PROPORTIONS in the frame. "
                f"Do NOT alter the poses, facial features, hair, eyes, body proportions, or traditional attire. "
                f"CRITICAL CLEANUP: Completely eliminate, erase, and remove all existing background elements, props, flower stands, wooden tables, and old studio equipment from Image 1. ONLY extract the bride and groom! "
                f"Replace the entire environment behind and around them with the backdrop from Image 2. "
                f"Seamlessly blend the couple into the new background with natural ambient lighting, soft contact shadows on the floor around their shoes/feet, and flawless integration. "
                f"Generate a pristine, professional high-end studio wedding photograph. 8k UHD photorealistic, razor-sharp details."
            )
        elif "BIRTHDAY" in mode_str:
            prompt_text = (
                f"{var_text}{ratio_directive}. "
                f"CRITICAL BIRTHDAY CELEBRATION INPAINTING MANDATE: "
                f"100% PRESERVE THE EXACT ORIGINAL HUMAN PERSONS (faces, facial details, eyes, expressions, poses, clothing completely untouched and identical). "
                f"TASK: ONLY REPLACE BACKGROUND WITH FESTIVE BIRTHDAY SCENE: {scene_desc}. {prompt}. "
                f"Festive birthday elements, balloons, gifts, confetti, warm celebratory studio lighting, 8k photorealistic, {chosen_style}."
            )
        elif "FAMILY" in mode_str:
            prompt_text = (
                f"{var_text}{ratio_directive}. "
                f"CRITICAL FAMILY PORTRAIT INPAINTING MANDATE: "
                f"100% PRESERVE ALL ORIGINAL FAMILY MEMBERS (faces, facial features, identities, expressions, hairstyles, bodies, clothing completely untouched and identical). "
                f"TASK: REPLACE BACKGROUND WITH LUXURIOUS FAMILY SETTING: {scene_desc}. {prompt}. "
                f"Warm, harmonious ambient family atmosphere, 8k ultra-sharp photorealistic, {chosen_style}."
            )
        elif "RESTORE" in mode_str:
            prompt_text = (
                f"{var_text}{ratio_directive}. "
                f"CRITICAL HISTORICAL PHOTO RESTORATION MANDATE: "
                f"Task: Faithfully restore this vintage photograph while 100% PRESERVING THE TRUE ORIGINAL FACE AND IDENTITY of the person. "
                f"DO NOT invent or substitute a different person's face. Restore sharp clarity to original facial details, eyes, and hair. Remove scratches, creases, stains, noise, dust, and blur. "
                f"Fidelity mode: {scene_desc}. {prompt}. "
                f"Natural photorealistic skin tones, realistic clothing fabric restoration, 8k high resolution."
            )
        else:
            prompt_text = (
                f"{var_text}STRICT INPAINTING & ZERO HUMAN MODIFICATION MANDATE: "
                f"{ratio_directive}. "
                f"100% PRESERVE ORIGINAL HUMAN COMPOSITION AND IDENTITIES: "
                f"Keep the original bride and groom in their EXACT SAME POSITIONS, EXACT SAME SPATIAL COMPOSITION, FRAMING, SIZES, AND PROPORTIONS in the frame. "
                f"Do NOT move, do NOT zoom, do NOT rescale, do NOT crop, and do NOT alter the poses, body composition, eye levels, arm gestures, or bouquet position of the couple. "
                f"Keep their faces, facial details, expressions, hairstyles, bodies, natural skin texture with real pores, bridal gown, groom's suit, and jewelry 100% UNTOUCHED and identical to the input photo. "
                f"TASK: ONLY REPLACE AND ENHANCE THE PLAIN BACKGROUND BEHIND AND AROUND THE COUPLE. "
                f"New Luxury Wedding Studio Backdrop: {scene_desc}. {prompt}. "
                f"Photorealistic 8k, seamless realistic edge blending, natural contact shadows, harmonious studio lighting on the subjects, {chosen_style}."
            )

        payload = {
            "model": "gpt-image-2",
            "images": images_list,
            "prompt": prompt_text,
            "response_format": "b64_json"
        }
    else:
        endpoint = "https://chatgpt.com/backend-api/codex/images/generations"
        prompt_text = f"{var_text}{ratio_directive}. {prompt}, {scene_desc}, {chosen_style}" if prompt else f"{var_text}{ratio_directive}. Professional photography in {scene_desc}. {chosen_style}."
        payload = {
            "model": "gpt-image-2",
            "prompt": prompt_text,
            "n": 1,
            "response_format": "b64_json"
        }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "Content-Type": "application/json",
            "originator": "codex_cli_rs",
            "version": "0.130.0",
            "User-Agent": USER_AGENT
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "data" in data and len(data["data"]) > 0:
                b64 = data["data"][0].get("b64_json")
                if b64:
                    return f"data:image/jpeg;base64,{b64}"
        raise RuntimeError("ChatGPT không trả về dữ liệu ảnh hợp lệ.")
    except urllib.error.HTTPError as he:
        err_msg = he.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_msg)
            if "error" in err_json:
                err_msg = err_json["error"].get("message", err_msg)
            elif "detail" in err_json:
                err_msg = err_json.get("detail", err_msg)
        except Exception:
            pass
        if he.code == 403:
            raise RuntimeError("Lỗi 403: Tài khoản ChatGPT này (gói Free) không có quyền tạo ảnh qua API model. Vui lòng chuyển sang tài khoản ChatGPT Plus / Team / Pro!")
        elif he.code == 401:
            raise RuntimeError("Lỗi 401: Phiên đăng nhập ChatGPT đã hết hạn. Vui lòng bấm 'Đăng nhập ChatGPT' lại!")
        raise RuntimeError(f"Lỗi ChatGPT ({he.code}): {err_msg}")


def generate_image_with_grok(
    prompt: str = "",
    scene: str = "",
    aspect_ratio: str = "3:4",
    uploaded_image_b64: Optional[str] = None
) -> str:
    """Tạo ảnh qua xAI Grok API."""
    mgr = ChatGPTAuthManager.get_instance()
    active_grok = mgr.grok_accounts[mgr.current_grok_slot]
    api_key = active_grok.get("api_key")
    if not api_key:
        for g in mgr.grok_accounts:
            if g.get("api_key"):
                api_key = g.get("api_key")
                break
    if not api_key:
        raise ValueError("Chưa có Grok API Key. Vui lòng nhập key trong tab GROK.")

    endpoint = "https://api.x.ai/v1/images/generations"
    full_prompt = f"Aspect ratio {aspect_ratio}. {scene}. {prompt}. Professional photorealistic 8k wedding photography."
    payload = {
        "model": "grok-2-image",
        "prompt": full_prompt,
        "n": 1,
        "response_format": "b64_json"
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if "data" in data and len(data["data"]) > 0:
            b64 = data["data"][0].get("b64_json")
            if b64:
                return f"data:image/jpeg;base64,{b64}"
            url = data["data"][0].get("url")
            if url:
                with urllib.request.urlopen(url, timeout=60) as uresp:
                    raw_bytes = uresp.read()
                    return f"data:image/jpeg;base64,{base64.b64encode(raw_bytes).decode('utf-8')}"
    raise RuntimeError("Grok không trả về dữ liệu ảnh hợp lệ.")


def set_muse_chrome_visibility(visible: bool = True):
    """
    Ẩn hoặc hiện cửa sổ Chrome (:9225).
    - visible = False: Đưa cửa sổ Chrome ra ngoài màn hình (left: -30000, top: -30000)
      giúp Chrome HOÀN TOÀN TÀNG HÌNH nhưng vẫn chạy ngầm và tạo ảnh 100% tốc độ cao!
    - visible = True: Đưa cửa sổ Chrome trở lại vị trí hiển thị (left: 100, top: 60) lên trước màn hình.
    """
    try:
        with urllib.request.urlopen("http://127.0.0.1:9225/json/version", timeout=1.5) as r:
            version_data = json.loads(r.read().decode("utf-8"))
        browser_ws = version_data.get("webSocketDebuggerUrl")
        if browser_ws:
            sys.path.insert(0, r"C:\Users\POI\Desktop\New folder (5)")
            import muse_cdp_engine
            cdp = muse_cdp_engine.CDPClient(browser_ws, timeout=3.0)
            try:
                targets_res = cdp.call("Target.getTargets")
                page_targets = [t for t in targets_res.get("targetInfos", []) if t.get("type") == "page"]
                for pt in page_targets:
                    tid = pt.get("targetId")
                    if tid:
                        win = cdp.call("Browser.getWindowForTarget", {"targetId": tid})
                        if win and "windowId" in win:
                            wid = win["windowId"]
                            if visible:
                                bounds = {
                                    "windowState": "normal",
                                    "left": 100,
                                    "top": 60,
                                    "width": 1080,
                                    "height": 800
                                }
                            else:
                                bounds = {
                                    "windowState": "normal",
                                    "left": -30000,
                                    "top": -30000,
                                    "width": 1000,
                                    "height": 800
                                }
                            cdp.call("Browser.setWindowBounds", {"windowId": wid, "bounds": bounds})
                return True
            finally:
                try:
                    cdp.close()
                except Exception:
                    pass
    except Exception as e:
        print(f"[SetMuseVisibility] Lỗi CDP: {e}")

    # Dự phòng di chuyển cửa sổ qua Win32 API
    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            EnumWindows = user32.EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            GetClassNameW = user32.GetClassNameW
            GetWindowTextW = user32.GetWindowTextW
            SetWindowPos = user32.SetWindowPos

            SWP_NOZORDER = 0x0004
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040

            def enum_cb(hwnd, extra):
                cls_len = 256
                cls_buf = ctypes.create_unicode_buffer(cls_len)
                GetClassNameW(hwnd, cls_buf, cls_len)
                cname = cls_buf.value
                if "Chrome_WidgetWin" in cname:
                    txt_buf = ctypes.create_unicode_buffer(512)
                    GetWindowTextW(hwnd, txt_buf, 512)
                    title = txt_buf.value.lower()
                    if any(k in title for k in ["trà thương", "tra thuong", "127.0.0.1:5000", "localhost:5000"]):
                        return True
                    if any(k in title for k in ["gemini", "google", "ask gemini", "muse"]):
                        if visible:
                            SetWindowPos(hwnd, 0, 100, 60, 1080, 800, SWP_NOZORDER | SWP_SHOWWINDOW)
                        else:
                            SetWindowPos(hwnd, 0, -30000, -30000, 1000, 800, SWP_NOZORDER)
                return True

            EnumWindows(EnumWindowsProc(enum_cb), 0)
        except Exception:
            pass
    return False


def show_muse_chrome():
    """Hiển thị và mở cửa sổ Chrome Gemini Web (https://gemini.google.com/app?hl=vi)."""
    try:
        sys.path.insert(0, r"C:\Users\POI\Desktop\New folder (5)")
        import muse_cdp_engine
        eng = muse_cdp_engine.MuseCdpEngine(muse_cdp_engine.MuseStore(), cdp_port=9225)
        if not eng.is_chrome_alive():
            eng.ensure_chrome(force_visible=True)
            time.sleep(2.0)

        targets = eng.get_page_targets(9225)
        target = next((t for t in targets if "gemini.google.com" in t.get("url", "") or "google.com" in t.get("url", "") or "muse.ai" in t.get("url", "")), targets[0] if targets else None)
        if target and target.get("webSocketDebuggerUrl"):
            cdp = muse_cdp_engine.CDPClient(target["webSocketDebuggerUrl"], timeout=4.0)
            try:
                cur_url = target.get("url", "")
                if "gemini.google.com" not in cur_url and "accounts.google.com" not in cur_url:
                    cdp.call("Page.navigate", {"url": "https://accounts.google.com/ServiceLogin?continue=https://gemini.google.com/app?hl=vi"})
                cdp.call("Page.bringToFront")
            finally:
                try:
                    cdp.close()
                except Exception:
                    pass
    except Exception as e:
        print(f"[Gemini Chrome] Lỗi bật Chrome: {e}")

    set_muse_chrome_visibility(True)


def hide_muse_chrome():
    """Ẩn cửa sổ Chrome Gemini Web để chạy ngầm 100%."""
    set_muse_chrome_visibility(False)


def get_muse_status() -> Dict[str, Any]:
    """Lấy trạng thái thực tế từ Gemini / Muse Studio Server (:18638)."""
    try:
        req = urllib.request.Request("http://127.0.0.1:18638/admin/status", headers={"Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            stats = data.get("stats", {})
            return {
                "ok": True,
                "chrome_alive": bool(data.get("chrome_alive", False)),
                "cdp_port": data.get("cdp_port", 9225),
                "active_tasks": data.get("active_tasks", 0),
                "total_accounts": stats.get("total_accounts", 1),
                "live_accounts": stats.get("live_accounts", 1),
                "base_url": "https://gemini.google.com/app?hl=vi"
            }
    except Exception:
        return {
            "ok": True,
            "chrome_alive": False,
            "cdp_port": 9225,
            "active_tasks": 0,
            "total_accounts": 1,
            "live_accounts": 1,
            "base_url": "https://gemini.google.com/app?hl=vi"
        }


def sync_muse_cdp_cookies() -> Dict[str, Any]:
    """Tự động trích xuất Cookie của Gemini / Google từ Chrome CDP và lưu tài khoản."""
    try:
        sys.path.insert(0, r"C:\Users\POI\Desktop\New folder (5)")
        import muse_cdp_engine
        import muse_store
        store = muse_store.MuseStore()
        eng = muse_cdp_engine.MuseCdpEngine(store, cdp_port=9225)
        targets = eng.get_page_targets(9225)
        if not targets:
            return {"ok": False, "error": "Chưa tìm thấy cửa sổ Chrome nào đang mở cổng CDP :9225"}

        # Tìm tab gemini hoặc google
        target = next((t for t in targets if "gemini.google.com" in t.get("url", "") or "google.com" in t.get("url", "")), targets[0])
        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            return {"ok": False, "error": "Không lấy được WebSocket debugger của Chrome"}

        cdp = muse_cdp_engine.CDPClient(ws_url, timeout=10.0)
        try:
            cdp.call("Network.enable")
            cookies_res = cdp.call("Network.getCookies", {"urls": [
                "https://gemini.google.com",
                "https://google.com",
                "https://accounts.google.com",
                "https://muse.ai"
            ]})
            cookies = cookies_res.get("cookies", [])
            if not cookies:
                return {"ok": False, "error": "Chưa có Cookie nào trên tab Gemini Web. Vui lòng đăng nhập Google trước khi bấm đồng bộ!"}

            # Kiểm tra cookie Google hoặc Muse thực sự (phải có auth cookie, không tính cookie theo dõi NID/COMPASS)
            has_sess = any(c.get("name") in ("__Secure-1PSID", "SAPISID", "SID", "SSID", "HSID", "hatch_sess") for c in cookies)
            if not has_sess:
                return {
                    "ok": False,
                    "error": "Chưa phát hiện tài khoản đăng nhập trên Chrome.\n👉 Bạn vui lòng nhập Email & Mật khẩu Google trên cửa sổ Chrome đang mở, sau khi đăng nhập xong hãy bấm '🌱 Đồng bộ'!"
                }
            
            # Thử đọc email hiển thị trên trang Google Gemini
            detected_email = ""
            try:
                dom_mail = cdp.call("Runtime.evaluate", {
                    "expression": "(() => { const a = document.querySelector('a[aria-label*=\"@\"], button[aria-label*=\"@\"]'); if (a) { const m = a.getAttribute('aria-label').match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/); if (m) return m[0]; } return ''; })()",
                    "returnByValue": True
                })
                detected_email = dom_mail.get("result", {}).get("value", "")
            except Exception:
                pass

            mgr = ChatGPTAuthManager.get_instance()
            email = detected_email or f"Google Account {mgr.current_grok_slot + 1}"

            # Lưu vào MuseStore
            try:
                res = store.add_or_update_account(name=f"Gemini TK {mgr.current_grok_slot + 1}", cookie_input=cookies, email=email)
            except Exception:
                res = {}

            mgr.grok_accounts[mgr.current_grok_slot] = {
                "slot": mgr.current_grok_slot,
                "name": f"Gemini TK {mgr.current_grok_slot + 1}",
                "email": email,
                "logged_in": True,
                "has_key": True
            }
            mgr.save_config()

            return {"ok": True, "message": f"✔ Đã đồng bộ tài khoản Gemini Web ({email}) thành công!", "account": res.get("account")}
        finally:
            try:
                cdp.close()
            except Exception:
                pass
    except Exception as e:
        return {"ok": False, "error": f"Lỗi đồng bộ Cookie: {str(e)}"}


def import_muse_cookie(raw_cookie: str, email: str = "") -> Dict[str, Any]:
    """Nhập Cookie thủ công (từ Cookie-Editor hoặc paste chuỗi hatch_sess=...)."""
    if not raw_cookie:
        return {"ok": False, "error": "Chuỗi Cookie trống!"}
    try:
        sys.path.insert(0, r"C:\Users\POI\Desktop\New folder (5)")
        import muse_store
        store = muse_store.MuseStore()
        mgr = ChatGPTAuthManager.get_instance()
        target_email = email.strip() or mgr.chatgpt_accounts[0].get("email") or "aothunkhmer@gmail.com"
        res = store.add_or_update_account(name=f"Muse TK {mgr.current_grok_slot + 1}", cookie_input=raw_cookie, email=target_email)
        mgr.grok_accounts[mgr.current_grok_slot] = {
            "slot": mgr.current_grok_slot,
            "name": f"Muse TK {mgr.current_grok_slot + 1}",
            "email": target_email,
            "logged_in": True,
            "has_key": True
        }
        mgr.save_config()
        return {"ok": True, "message": f"✔ Đã nhập Cookie thành công! Tài khoản {target_email} đã sẵn sàng.", "account": res.get("account")}
    except Exception as e:
        return {"ok": False, "error": f"Lỗi nhập Cookie: {str(e)}"}


def open_extension_folder():
    """Mở thư mục Extension Cookie trong Windows Explorer."""
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "muse_cookie_extension")
    if os.path.isdir(folder):
        subprocess.Popen(["explorer.exe", folder])
    return folder


def generate_image_with_muse(
    prompt: str = "",
    scene: str = "",
    aspect_ratio: str = "3:4",
    uploaded_image_b64: Optional[str] = None
) -> str:
    """Tạo ảnh qua Muse Studio / Muse.ai Gateway (Port 18638)."""
    endpoint = "http://127.0.0.1:18638/v1/images/generations"
    full_prompt = f"{scene}. {prompt}".strip()
    if not full_prompt:
        full_prompt = "Professional 8k wedding photograph studio quality"

    payload = {
        "prompt": full_prompt,
        "aspectRatio": aspect_ratio,
        "quality": "4K",
        "mode": "image"
    }
    if uploaded_image_b64:
        raw_b64 = uploaded_image_b64.split(",")[-1]
        payload["reference_images"] = [{"b64": raw_b64, "name": "input_image.png", "mime": "image/png"}]
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "data" in data and len(data["data"]) > 0:
                item = data["data"][0]
                if item.get("b64_json"):
                    return f"data:image/jpeg;base64,{item['b64_json']}"
                elif item.get("url"):
                    u = item["url"]
                    if u.startswith("/"):
                        u = f"http://127.0.0.1:18638{u}"
                    with urllib.request.urlopen(u, timeout=60) as uresp:
                        return f"data:image/jpeg;base64,{base64.b64encode(uresp.read()).decode('utf-8')}"
            elif "mediaUrl" in data:
                u = data["mediaUrl"]
                if u.startswith("/"):
                    u = f"http://127.0.0.1:18638{u}"
                with urllib.request.urlopen(u, timeout=60) as uresp:
                    return f"data:image/jpeg;base64,{base64.b64encode(uresp.read()).decode('utf-8')}"
        raise RuntimeError("Muse AI không trả về dữ liệu ảnh hợp lệ.")
    except urllib.error.HTTPError as e:
        err_msg = str(e)
        try:
            err_data = json.loads(e.read().decode("utf-8"))
            if err_data.get("error"):
                raw_err = err_data["error"]
                if "Chưa có ních Muse.ai nào đang LIVE" in raw_err or "logged-out" in raw_err or "quá thời gian" in raw_err.lower():
                    err_msg = "Tài khoản Muse AI trên Chrome chưa đăng nhập hoặc phiên đã hết hạn.\n\n👉 Vui lòng bấm nút 'Hiện Chrome' ở bảng bên trái và đăng nhập vào https://muse.ai/ (bằng Email hoặc tài khoản Meta/Google). Sau khi đăng nhập xong, bạn bấm 'TẠO ẢNH' lại là được ngay!"
                else:
                    err_msg = raw_err
        except Exception:
            pass
        raise RuntimeError(err_msg)
    except urllib.error.URLError as e:
        raise RuntimeError(f"Chưa kết nối được cổng tạo ảnh Gemini / Muse (:18638). Vui lòng bấm 'Hiện Chrome' và mở https://gemini.google.com/app?hl=vi! Chi tiết: {e}")
    except Exception as e:
        raise RuntimeError(f"Lỗi tạo ảnh Gemini: {e}")


