"""
Trà Thương Pro AI - Giao diện dòng lệnh (CLI)
Hỗ trợ tạo ảnh nhanh chóng qua terminal hoặc kịch bản tự động hóa.
"""

import os
import sys
import argparse
from tra_thuong_ai import (
    AppMode,
    Country,
    AspectRatio,
    ImageSize,
    GenerationConfig,
    PortraitBeautyConfig,
    RestoreOldConfig,
    build_prompt,
    generate_ai_images,
    load_env_api_key
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Trà Thương Pro AI - Studio tạo ảnh & phục hồi ảnh AI chuyên nghiệp"
    )

    parser.add_argument(
        "--mode",
        type=str,
        default="wedding",
        choices=[
            "portrait", "restore", "wedding", "birthday", 
            "family", "text2image", "remove_object", "copyskin"
        ],
        help="Chế độ xử lý ảnh (mặc định: wedding)"
    )

    parser.add_argument("--image", type=str, default=None, help="Đường dẫn ảnh đầu vào")
    parser.add_argument("--output", type=str, default="output.png", help="Đường dẫn lưu file ảnh đầu ra")
    parser.add_argument("--desc", type=str, default="", help="Mô tả bổ sung hoặc nội dung ảnh")
    parser.add_argument("--api-key", type=str, default=None, help="Google Gemini API Key")
    parser.add_argument("--country", type=str, default="VIETNAM", choices=["VIETNAM", "KHMER", "CHINA"], help="Phong cách quốc gia")
    parser.add_argument("--scene", type=str, default="Sân khấu đám cưới", help="Bối cảnh chụp")
    parser.add_argument("--lighting", type=str, default="Nắng nhẹ", help="Ánh sáng (Nắng nhẹ, Nắng gắt, Hoàng hôn, Ban đêm)")
    parser.add_argument("--foreground", type=str, default="Hoa", help="Tiền cảnh (Hoa, Lá xanh, v.v.)")
    parser.add_argument("--aspect", type=str, default="3:4", choices=["3:4", "1:1", "16:9", "9:16"], help="Tỷ lệ khung hình")
    parser.add_argument("--size", type=str, default="4K", choices=["1K", "2K", "4K", "6K"], help="Độ phân giải")
    parser.add_argument("--num-images", type=int, default=1, help="Số lượng ảnh cần tạo (1-4)")

    # Tham số làm đẹp chân dung
    parser.add_argument("--smooth-skin", type=int, default=30, help="Độ mịn da (0-100)")
    parser.add_argument("--whitening", type=int, default=20, help="Làm trắng da (0-100)")
    parser.add_argument("--detail", type=int, default=20, help="Tăng chi tiết (0-100)")
    parser.add_argument("--teeth-whitening", type=int, default=20, help="Làm trắng răng (0-100)")

    # Tham số phục hồi ảnh cũ
    parser.add_argument("--colorize", action="store_true", help="Tự động tô màu ảnh cũ")
    parser.add_argument("--high-quality", action="store_true", help="Nâng cao chất lượng ảnh phục hồi")
    parser.add_argument("--remove-wrinkles", action="store_true", help="Xóa nếp nhăn")
    parser.add_argument("--khmer-style", action="store_true", help="Áp dụng phong cách Khmer")

    return parser.parse_args()


def map_mode(mode_str: str) -> AppMode:
    mapping = {
        "portrait": AppMode.PORTRAIT_BEAUTY,
        "restore": AppMode.RESTORE_OLD,
        "wedding": AppMode.AI_WEDDING,
        "birthday": AppMode.AI_BIRTHDAY,
        "family": AppMode.AI_FAMILY,
        "text2image": AppMode.TEXT_TO_IMAGE,
        "remove_object": AppMode.REMOVE_OBJECT,
        "copyskin": AppMode.COPY_SKIN
    }
    return mapping.get(mode_str.lower(), AppMode.AI_WEDDING)


def main():
    args = parse_args()
    app_mode = map_mode(args.mode)

    print("=" * 60)
    print("        TRÀ THƯƠNG PRO AI - CHƯƠNG TRÌNH DÒNG LỆNH (CLI)")
    print("=" * 60)
    print(f"Chế độ: {app_mode.value}")

    # Kiểm tra API Key
    api_key = args.api_key or load_env_api_key()
    if not api_key:
        print("[LỖI] Chưa có API Key! Hãy thiết lập biến môi trường GEMINI_API_KEY hoặc dùng --api-key.")
        sys.exit(1)

    # Kiểm tra ảnh đầu vào đối với các chế độ cần ảnh
    if app_mode in [AppMode.PORTRAIT_BEAUTY, AppMode.RESTORE_OLD, AppMode.REMOVE_OBJECT, AppMode.COPY_SKIN]:
        if not args.image or not os.path.exists(args.image):
            print(f"[LỖI] Chế độ {app_mode.value} bắt buộc phải có ảnh đầu vào hợp lệ (--image <file>).")
            sys.exit(1)

    config = GenerationConfig(
        country=Country(args.country),
        scene=args.scene,
        description=args.desc,
        lighting=args.lighting,
        foreground=args.foreground,
        aspectRatio=AspectRatio(args.aspect),
        imageSize=ImageSize(args.size),
        numImages=args.num_images,
        uploadedImage=args.image
    )

    if app_mode == AppMode.PORTRAIT_BEAUTY:
        pb = PortraitBeautyConfig()
        pb.autoFix.smoothSkin = args.smooth_skin
        pb.autoFix.whitening = args.whitening
        pb.autoFix.detail = args.detail
        pb.details.teethWhitening = args.teeth_whitening
        config.portraitBeauty = pb

    elif app_mode == AppMode.RESTORE_OLD:
        ro = RestoreOldConfig()
        ro.colorize = args.colorize
        ro.highQuality = args.high_quality
        ro.removeWrinkles = args.remove_wrinkles
        ro.khmerStyle = args.khmer_style
        ro.advancedPrompt = args.desc
        config.restoreOld = ro

    prompt = build_prompt(config, app_mode, has_image=bool(args.image))
    print(f"\n[PROMPT ĐƯỢC TẠO]\n{prompt}\n")
    print(f"Đang gửi yêu cầu đến Gemini ({config.imageSize.value}, {config.aspectRatio.value})... Vui lòng chờ...")

    try:
        results = generate_ai_images(config, app_mode, api_key=api_key)
        print(f"\nĐã tạo thành công {len(results)} ảnh!")

        base_out, ext = os.path.splitext(args.output)
        if not ext:
            ext = ".png"

        for i, res in enumerate(results):
            if len(results) == 1:
                filename = f"{base_out}{ext}"
            else:
                filename = f"{base_out}_{i+1}{ext}"
            res.save(filename)
            print(f"-> Đã lưu ảnh tại: {os.path.abspath(filename)}")

    except Exception as e:
        print(f"\n[THẤT BẠI] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

