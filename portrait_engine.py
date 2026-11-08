"""
Trà Thương Pro AI - Local Portrait Beauty Retouching Engine
Chạy 100% cục bộ (Offline - Không cần API) bằng OpenCV, NumPy và Pillow.
Hỗ trợ:
- Mịn da tách tần số (Frequency Separation - FS)
- Làm trắng da tự nhiên (Skin Whitening in LAB)
- Đều màu da (Even Skin Tone)
- Tăng chi tiết sắc nét (Detail Enhancement / Unsharp Mask)
- Khối & Sáng (Dodge & Burn / S-curve Lighting)
- Cân bằng xám (Gray-World Auto White Balance)
- Trắng răng & Xóa khuyết điểm
- Mượt tóc & Dày tóc
"""

import io
import base64
import cv2
import numpy as np
from PIL import Image


def load_bgr_from_data_url_or_path(img_input: str) -> np.ndarray:
    """Tải ảnh BGR từ data URL (base64) hoặc đường dẫn file."""
    if img_input.startswith("data:image"):
        header, b64 = img_input.split(",", 1)
        img_bytes = base64.b64decode(b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img_bgr
    else:
        # Đường dẫn file
        img = Image.open(img_input).convert("RGB")
        img_rgb = np.array(img)
        return cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)


def bgr_to_base64_data_url(bgr: np.ndarray, quality: int = 95) -> str:
    """Chuyển ảnh BGR sang chuỗi base64 data URL."""
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, buffer = cv2.imencode(".jpg", bgr, encode_params)
    if not success:
        raise ValueError("Không thể mã hóa ảnh BGR sang JPEG.")
    b64_str = base64.b64encode(buffer).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_str}"


def get_skin_mask(bgr: np.ndarray) -> np.ndarray:
    """Tạo mặt nạ nhận diện vùng da mềm mại bằng YCrCb và HSV."""
    h, w = bgr.shape[:2]
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    cr = ycrcb[:, :, 1]
    cb = ycrcb[:, :, 2]
    
    # Khoảng giá trị Cr & Cb chuẩn cho tông da người châu Á & quốc tế
    skin_ycrcb = (cr >= 130) & (cr <= 175) & (cb >= 75) & (cb <= 135)

    # Kết hợp HSV để loại bỏ các vùng quá tối hoặc quá cháy sáng
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h_channel = hsv[:, :, 0]
    s_channel = hsv[:, :, 1]
    v_channel = hsv[:, :, 2]
    skin_hsv = ((h_channel <= 25) | (h_channel >= 165)) & (s_channel >= 20) & (v_channel >= 40)

    combined_mask = (skin_ycrcb & skin_hsv).astype(np.float32)

    # Làm mềm biên mặt nạ (feathering) bằng Gaussian Blur để chuyển màu mượt mà
    ksize = max(9, int((min(h, w) * 0.015) // 2 * 2 + 1))
    feathered_mask = cv2.GaussianBlur(combined_mask, (ksize, ksize), 0)
    return feathered_mask


def retouch_portrait_local(bgr: np.ndarray, pb_dict: dict) -> np.ndarray:
    """
    Xử lý làm đẹp chân dung hoàn toàn cục bộ 100% bằng thuật toán xử lý ảnh chuyên sâu.
    """
    auto_fix = pb_dict.get("autoFix", {})
    hair = pb_dict.get("hair", {})
    details = pb_dict.get("details", {})

    smooth_skin = auto_fix.get("smoothSkin", 0)
    detail = auto_fix.get("detail", 0)
    even_skin = auto_fix.get("evenSkin", 0)
    even_face = auto_fix.get("evenFace", 0)
    even_body = auto_fix.get("evenBody", 0)
    whitening = auto_fix.get("whitening", 0)
    lighting = auto_fix.get("lighting", 0)
    features = auto_fix.get("features", 0)
    gray_balance = auto_fix.get("grayBalance", 0)

    hair_thickness = hair.get("thickness", 0)
    hair_smoothness = hair.get("smoothness", 0)
    baby_hair = hair.get("babyHair", 0)

    teeth_whitening = details.get("teethWhitening", 0)
    blemish_removal = details.get("blemishRemoval", 0)
    forehead_wrinkles = details.get("foreheadWrinkles", 0)
    eye_wrinkles = details.get("eyeWrinkles", 0)
    eye_bags = details.get("eyeBags", 0)
    smile_lines = details.get("smileLines", 0)

    # Nếu tất cả thanh trượt đều = 0, tự động áp dụng cấu hình làm đẹp tự nhiên chuẩn Studio
    total_val = sum([
        smooth_skin, detail, even_skin, whitening, lighting, features, gray_balance,
        hair_smoothness, teeth_whitening, blemish_removal, eye_bags
    ])
    if total_val == 0:
        smooth_skin = 50
        whitening = 35
        detail = 45
        even_skin = 35
        lighting = 30
        teeth_whitening = 40
        blemish_removal = 50
        hair_smoothness = 35

    h, w = bgr.shape[:2]
    out = bgr.copy()

    # 1. CÂN BẰNG XÁM (Gray-World White Balance)
    if gray_balance > 0:
        factor = gray_balance / 100.0
        b_avg = np.mean(out[:, :, 0])
        g_avg = np.mean(out[:, :, 1])
        r_avg = np.mean(out[:, :, 2])
        k = (b_avg + g_avg + r_avg) / 3.0
        if b_avg > 0 and g_avg > 0 and r_avg > 0:
            b_gain = 1.0 + ((k / b_avg) - 1.0) * factor
            g_gain = 1.0 + ((k / g_avg) - 1.0) * factor
            r_gain = 1.0 + ((k / r_avg) - 1.0) * factor
            out[:, :, 0] = np.clip(out[:, :, 0] * b_gain, 0, 255).astype(np.uint8)
            out[:, :, 1] = np.clip(out[:, :, 1] * g_gain, 0, 255).astype(np.uint8)
            out[:, :, 2] = np.clip(out[:, :, 2] * r_gain, 0, 255).astype(np.uint8)

    # Lấy mặt nạ vùng da
    skin_mask = get_skin_mask(out)
    skin_mask_3c = np.stack([skin_mask] * 3, axis=2)

    # 2. MỊN DA TÁCH TẦN SỐ (Frequency Separation - FS) + XÓA KHUYẾT ĐIỂM
    effective_smooth = max(smooth_skin, blemish_removal)
    if effective_smooth > 0:
        strength = (effective_smooth / 100.0)
        # Bán kính lọc tỷ lệ theo độ phân giải ảnh
        d_val = max(5, int((min(h, w) * 0.01) // 2 * 2 + 1))
        sigma_c = 40 + strength * 60
        sigma_s = 40 + strength * 60

        # Tách tần số thấp (màu sắc, mảng khối)
        low_freq = cv2.bilateralFilter(out, d=d_val, sigmaColor=sigma_c, sigmaSpace=sigma_s)
        # Tần số cao (vân da, lỗ chân lông, độ nét thật)
        high_freq = cv2.subtract(out, low_freq)

        # Làm mịn thêm tần số thấp ở những vùng có khuyết điểm
        low_smooth = cv2.bilateralFilter(low_freq, d=d_val * 2, sigmaColor=sigma_c * 1.2, sigmaSpace=sigma_s * 1.2)
        
        # Tái hợp tần số: giữ nguyên chi tiết vân da từ high_freq
        recombined = cv2.add(low_smooth, high_freq)

        # Trộn mượt mà chỉ trên vùng da (không làm mờ viền áo, tóc hay background)
        blend_factor = skin_mask_3c * strength
        out = (out.astype(np.float32) * (1.0 - blend_factor) + recombined.astype(np.float32) * blend_factor)
        out = np.clip(out, 0, 255).astype(np.uint8)

    # 3. LÀM TRẮNG DA & ĐỀU MÀU DA TRONG KHÔNG GIAN LAB
    if whitening > 0 or even_skin > 0 or even_face > 0 or even_body > 0:
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB).astype(np.float32)
        L = lab[:, :, 0]
        A = lab[:, :, 1]
        B = lab[:, :, 2]

        # Làm trắng da: nâng độ sáng L mượt mà không bị cháy sáng
        if whitening > 0:
            w_strength = (whitening / 100.0)
            # Đường cong làm sáng tự nhiên cho vùng da (lift midtones & shadow tones)
            lift = 25.0 * w_strength * (1.0 - L / 255.0) * (L / 255.0) * 3.5
            L = L + lift * skin_mask

        # Đều màu da: làm dịu các vùng quá đỏ (A) hoặc quá vàng (B)
        effective_even = max(even_skin, even_face, even_body)
        if effective_even > 0:
            e_strength = (effective_even / 100.0) * 0.4
            skin_pixels = skin_mask > 0.4
            if np.any(skin_pixels):
                target_a = np.mean(A[skin_pixels])
                target_b = np.mean(B[skin_pixels])
                A = A * (1.0 - skin_mask * e_strength) + (A * (1.0 - e_strength) + target_a * e_strength) * (skin_mask * e_strength)
                B = B * (1.0 - skin_mask * e_strength) + (B * (1.0 - e_strength) + target_b * e_strength) * (skin_mask * e_strength)

        lab[:, :, 0] = np.clip(L, 0, 255)
        lab[:, :, 1] = np.clip(A, 0, 255)
        lab[:, :, 2] = np.clip(B, 0, 255)
        out = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)

    # 4. TRẮNG RĂNG (Teeth Whitening)
    if teeth_whitening > 0:
        tw_strength = teeth_whitening / 100.0
        hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
        H_hsv, S_hsv, V_hsv = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        
        # Nhận diện vùng răng (vùng sáng V > 140, bão hòa thấp/vừa S < 90)
        teeth_candidate = (V_hsv > 130) & (S_hsv < 85) & (skin_mask > 0.2)
        if np.any(teeth_candidate):
            # Giảm vàng/bão hòa và tăng sáng
            S_hsv[teeth_candidate] = S_hsv[teeth_candidate] * (1.0 - 0.5 * tw_strength)
            V_hsv[teeth_candidate] = np.clip(V_hsv[teeth_candidate] * (1.0 + 0.25 * tw_strength), 0, 255)
            hsv[:, :, 1] = S_hsv
            hsv[:, :, 2] = V_hsv
            out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 5. MƯỢT TÓC (Hair Smoothing & Clean-up)
    effective_hair = max(hair_smoothness, baby_hair, hair_thickness)
    if effective_hair > 0:
        h_strength = effective_hair / 100.0
        # Nhận diện vùng tóc (vùng tối V < 80 và không phải da)
        gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
        hair_mask = (gray < 85) & (skin_mask < 0.2)
        hair_mask_f = cv2.GaussianBlur(hair_mask.astype(np.float32), (9, 9), 0)
        hair_mask_3c = np.stack([hair_mask_f] * 3, axis=2)

        hair_smooth = cv2.bilateralFilter(out, d=7, sigmaColor=50 * h_strength, sigmaSpace=50 * h_strength)
        out = (out.astype(np.float32) * (1.0 - hair_mask_3c * h_strength * 0.7) + hair_smooth.astype(np.float32) * (hair_mask_3c * h_strength * 0.7))
        out = np.clip(out, 0, 255).astype(np.uint8)

    # 6. KHỐI & SÁNG (Lighting / Specular Highlights / Contrast S-Curve)
    if lighting > 0:
        l_strength = lighting / 100.0
        # Áp dụng đường cong tương phản S-curve nhẹ
        lut = np.arange(256, dtype=np.float32)
        # S-curve: x' = 255 * (1 / (1 + exp(-k*(x-128))))
        k = 0.015 * l_strength
        lut = 255.0 / (1.0 + np.exp(-k * (lut - 128.0)))
        lut = np.clip(lut, 0, 255).astype(np.uint8)
        out = cv2.LUT(out, lut)

    # 7. TĂNG CHI TIẾT SẮC NÉT (Detail Enhancement / Unsharp Mask / Nét mặt)
    effective_detail = max(detail, features)
    if effective_detail > 0:
        d_strength = (effective_detail / 100.0) * 0.75
        gaussian = cv2.GaussianBlur(out, (0, 0), 2.0)
        sharpened = cv2.addWeighted(out, 1.0 + d_strength, gaussian, -d_strength, 0)
        out = sharpened

    return out

