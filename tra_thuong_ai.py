"""
Trà Thương Pro AI - Python Core Library
Phục hồi ảnh cũ, Làm đẹp chân dung, Ảnh cưới AI, Sinh nhật AI, Gia đình AI.
Tương thích với Google GenAI SDK (gemini-3.1-flash-image-preview & gemini-2.5-flash-image).
"""

import os
import re
import io
import base64
from enum import Enum
from typing import List, Optional, Union
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel, Field
from PIL import Image

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


# ==========================================================
# CẤU HÌNH ENUMS VÀ DATA MODELS
# ==========================================================

class AppMode(str, Enum):
    PORTRAIT_BEAUTY = 'PORTRAIT_BEAUTY'  # Làm đẹp chân dung
    RESTORE_OLD = 'RESTORE_OLD'          # Khôi phục ảnh cũ
    AI_WEDDING = 'AI_WEDDING'            # Ảnh cưới AI
    AI_BIRTHDAY = 'AI_BIRTHDAY'          # Sinh nhật AI
    AI_FAMILY = 'AI_FAMILY'              # Tạo ảnh gia đình AI
    COPY_SKIN = 'COPY_SKIN'              # Copy tông da AI
    TEXT_TO_IMAGE = 'TEXT_TO_IMAGE'      # Văn bản thành ảnh
    IMAGE_TO_PROMPT = 'IMAGE_TO_PROMPT'  # Hình ảnh sang prompt
    REMOVE_OBJECT = 'REMOVE_OBJECT'      # Xóa vật thể
    UPSCALE = 'UPSCALE'                  # Nâng cấp độ phân giải (SeedVR2 AI 4K/6K)


class Country(str, Enum):
    KHMER = 'KHMER'
    VIETNAM = 'VIETNAM'
    CHINA = 'CHINA'


class AspectRatio(str, Enum):
    PORTRAIT = '3:4'     # Khổ dọc chân dung
    SQUARE = '1:1'       # Vuông
    LANDSCAPE = '16:9'   # Ngang
    MOBILE = '9:16'      # Điện thoại


class ImageSize(str, Enum):
    SIZE_1K = '1K'
    SIZE_2K = '2K'
    SIZE_4K = '4K'
    SIZE_6K = '6K'


class PortraitBeautyAutoFix(BaseModel):
    smoothSkin: int = 0
    detail: int = 0
    evenSkin: int = 0
    evenFace: int = 0
    evenBody: int = 0
    whitening: int = 0
    lighting: int = 0
    features: int = 0
    grayBalance: int = 0


class PortraitBeautyHair(BaseModel):
    thickness: int = 0
    babyHair: int = 0
    smoothness: int = 0
    grayHair: int = 0
    color: int = 0


class PortraitBeautyDetails(BaseModel):
    teethWhitening: int = 0
    blemishRemoval: int = 0
    foreheadWrinkles: int = 0
    eyeWrinkles: int = 0
    eyeBags: int = 0
    smileLines: int = 0


class PortraitBeautyConfig(BaseModel):
    autoFix: PortraitBeautyAutoFix = Field(default_factory=PortraitBeautyAutoFix)
    hair: PortraitBeautyHair = Field(default_factory=PortraitBeautyHair)
    details: PortraitBeautyDetails = Field(default_factory=PortraitBeautyDetails)


class RestoreOldConfig(BaseModel):
    colorize: bool = False
    highQuality: bool = False
    keepHair: bool = False
    smoothSkin: bool = False
    darkenHair: bool = False
    keepFeatures: bool = False
    removeWrinkles: bool = False
    khmerStyle: bool = False
    upscale: bool = False
    repaintClothes: bool = False
    whitening: bool = False
    numPeople: str = '1'
    gender: str = 'Tự động'
    age: str = 'Tự động'
    smile: str = 'Tự động'
    advancedPrompt: str = ''
    background: str = 'Đen'
    numResults: int = 1


class UpscaleConfig(BaseModel):
    scale: str = '4x'
    targetRes: str = '4K'
    sharpness: int = 50
    denoise: int = 0
    enhanceFace: bool = True


class GenerationConfig(BaseModel):
    country: Country = Country.VIETNAM
    scene: str = 'Sân khấu đám cưới'
    description: str = ''
    lighting: str = 'Nắng nhẹ'
    foreground: str = 'Hoa'
    aspectRatio: AspectRatio = AspectRatio.PORTRAIT
    imageSize: ImageSize = ImageSize.SIZE_4K
    numImages: int = 1
    uploadedImage: Optional[str] = None  # Đường dẫn file, base64 hoặc None
    uploadedImages: List[str] = Field(default_factory=list)  # Dùng cho ghép gia đình
    mergeImages: bool = False
    keepOriginalClothing: bool = True  # Giữ 100% trang phục, dây chuyền và hoa văn thêu gốc
    mode: str = 'CHUNG'  # 'CHUNG' | 'TRE_EM' | 'NGUOI_LON' (dành cho sinh nhật)
    portraitBeauty: Optional[PortraitBeautyConfig] = Field(default_factory=PortraitBeautyConfig)
    restoreOld: Optional[RestoreOldConfig] = Field(default_factory=RestoreOldConfig)
    upscale: Optional[UpscaleConfig] = Field(default_factory=UpscaleConfig)
    removeObjectPrompt: Optional[str] = None


# ==========================================================
# CÁC BỐ CẢNH MẪU (SCENES PRESETS)
# ==========================================================

WEDDING_SCENES = {
    Country.VIETNAM: [
        {
            "id": "skdc",
            "label": "Sân khấu đám cưới",
            "prompt": "Khung cảnh lễ đường đám cưới sang trọng và lãng mạn nhất. Ở trung tâm là một cổng hoa tròn bằng gỗ được trang trí dày đặc bởi những đóa hoa cẩm tú cầu trắng, hoa hồng và lá xanh tươi tốt. Phía sau là rèm lụa màu kem rủ xuống mềm mại. Hai bên cổng là hai cột trụ La Mã màu trắng với bình hoa lớn bên trên. Sàn nhà rải đầy cánh hoa trắng và nhiều nến trụ trong cốc thủy tinh tỏa ánh sáng vàng ấm áp. Ánh sáng tự nhiên chiếu xuyên qua rèm từ phía sau tạo nên không khí mộng mơ. Độ phân giải 8k, chân thực, bố cục thanh lịch."
        },
        {
            "id": "nt",
            "label": "Ngoài trời",
            "prompt": "Tạo dựng một khung cảnh đám cưới tuyệt đẹp ngoài trời trong một khu vườn xanh mát. Sân khấu được trang trí chủ đạo bằng hoa lan trắng và hoa sen, kết hợp với ánh sáng tự nhiên rực rỡ, mang lại cảm giác thanh bình, tươi mát và đầy lãng mạn."
        },
        {
            "id": "pcss",
            "label": "Phòng cưới sang trọng",
            "prompt": "Ảnh khổ dọc của một căn phòng phong cách tối giản (minimalist) nhưng cực kỳ sang trọng. Tường màu trắng tinh khiết với các đường phào chỉ cổ điển kiểu Châu Âu. Bên phải là một chiếc bàn gỗ tối màu, chân cong cổ điển. Trên bàn đặt một tráp vàng (hoặc phan) có hoa văn Khmer/Thái tinh xảo với nắp nhọn cao. Bên cạnh là lọ hoa nhỏ cắm hoa bi trắng (baby's breath). Ánh sáng tự nhiên tràn ngập, mềm mại và thanh tịnh. Độ phân giải 8K, siêu thực."
        },
        {
            "id": "pshh",
            "label": "Phòng Studio Hoa Hồng",
            "prompt": "Thiết kế sân khấu sự kiện lãng mạn và xa hoa. Trung tâm là rèm nhung đỏ thẫm được buộc nếp sóng nghệ thuật. Phía trước là lối đi trải thảm đỏ sang trọng. Điểm nhấn là rừng hoa hồng đỏ rực rỡ mọc từ dưới sàn lan lên hai bên tường trắng có phào chỉ cổ điển. Ánh sáng điện ảnh (cinematic lighting) mềm mại làm nổi bật chi tiết từng cánh hoa. Phong cách Hyper-realistic, 8K, cực kỳ chi tiết."
        },
        {
            "id": "stcc",
            "label": "Sảnh tiệc cao cấp",
            "prompt": "Hình ảnh kỹ thuật số 8K của một sảnh tiệc cưới hoặc hội nghị siêu sang trọng với tông màu trắng chủ đạo. Kiến trúc Tân cổ điển (Neoclassical) với các cột lớn chạm khắc và mái vòm. Trung tâm là cầu thang lớn dẫn lên tầng trên. Cửa sổ kính lớn đón ánh sáng tự nhiên. Các cột trụ được trang trí bằng hoa hồng trắng và hồng nhạt cùng lá xanh. Sàn đá cẩm thạch trắng bóng loáng như gương phản chiếu không gian. Ánh sáng lung linh, bầu không khí lãng mạn và thoáng đãng."
        },
        {
            "id": "skch",
            "label": "Sân khấu chữ Hỷ 囍",
            "prompt": "Phông nền (Backdrop) đám cưới phong cách Trung Hoa hiện đại và cao cấp. Tâm điểm là chữ Hỷ 'Song Hỷ' (囍) khổng lồ được làm từ vải đỏ xếp ly tạo khối 3D. Khung chữ được trang trí bởi các cụm hoa tươi (hoa hồng đỏ/hồng, hoa ly vàng, hoa nhỏ tím và lá cọ xanh). Trên sàn nhà trắng tinh khôi có rải rác cánh hoa hồng đỏ. Ánh sáng studio sắc nét, màu sắc rực rỡ, độ phân giải 8K, siêu thực."
        }
    ],
    Country.KHMER: [
        {
            "id": "skdc_kh",
            "label": "ឆាកអាពាហ៍ពិពាហ៍ (Sân khấu đám cưới)",
            "prompt": "រូបភាពអាសនៈអាពាហ៍ពិពាហ៍ដ៏ប្រណីត និងមានលក្ខណៈរ៉ូមែនទិកបំផុត។ នៅចំកណ្តាលមានក្លោងទ្វារឈើរាងមូលដែលតុបតែងដោយបាច់ផ្កាពណ៌សធំៗ (ផ្កាកុលាប និងផ្កាអាយដ្រូសឺ) រួមជាមួយស្លឹកឈើពណ៌បៃតងយ៉ាងស្រស់ស្អាត។ ផ្ទៃខាងក្រោយគឺជាវាំងននសូត្រពណ៌ក្រែម (cream) ឬពណ៌បន៍ត្នោតខ្ចី ដែលទម្លាក់ចុះយ៉ាងទន់ភ្លន់។ នៅសងខាងក្លោងទ្វារមានសសររ៉ូម៉ាំងពណ៌សចំនួនពីរ ដែលមានថូផ្កាធំៗនៅពីលើ។ នៅលើឥដ្ឋមានរាយប៉ាយនូវស្រទាប់ផ្កាពណ៌ស និងមានទៀនក្នុងកែវថ្លាជាច្រើនកំពុងឆេះបញ្ចេញពន្លឺពណ៌លឿងទុំកក់ក្តៅ។ គុណភាព 8k resolution, photorealistic."
        },
        {
            "id": "nt_kh",
            "label": "ទេសភាពក្រៅ (Ngoài trời)",
            "prompt": "បង្កើតឆាកអាពាហ៍ពិពាហ៍ដ៏ស្រស់ស្អាតមួយនៅខាងក្រៅ ក្នុងសួនបៃតងស្រស់។ ឆាកនេះតុបតែងដោយផ្កាអ័រគីដេពណ៌ស និងផ្កាឈូកជាច្រើន រួមផ្សំជាមួយពន្លឺថ្ងៃធម្មជាតិដ៏ស្រស់បំព្រង បរិយាកាសត្រជាក់ភ្នែក និងរ៉ូមែនទិក។"
        }
    ],
    Country.CHINA: [
        {
            "id": "skdc_cn",
            "label": "Wedding Stage",
            "prompt": "A luxurious and romantic wedding altar setup. In the center, a circular wooden arch heavily decorated with lush white hydrangeas, roses, and green foliage. The background features elegant, flowing cream-colored silk drapes. Two white fluted Roman columns stand on either side, topped with grand floral arrangements. High resolution, 8k, photorealistic, cinematic lighting, elegant composition."
        },
        {
            "id": "skch_cn",
            "label": "Double Happiness Stage (囍)",
            "prompt": "Modern luxury Chinese wedding backdrop. Centerpiece is a large 'Double Happiness' (囍) symbol structure made of pleated deep red fabric. The frame is adorned with lush floral arrangements including red and pink roses, yellow lilies, purple fillers, and green palm leaves. Clean white floor with scattered red rose petals. Studio lighting, vibrant colors, sharp details, 8k, photorealistic."
        }
    ]
}


# ==========================================================
# CÁC TIỆN ÍCH XỬ LÝ ẢNH VÀ ENV
# ==========================================================

def clean_api_key_string(raw: str) -> str:
    """Làm sạch chuỗi API Key từ nhiều định dạng copy (header, URL parameter, ngoặc kép)."""
    if not raw:
        return ""
    import re
    s = raw.strip()
    m1 = re.search(r'(?:X-goog-api-key:\s*|key=)([\w\.\-]+)', s, re.I)
    if m1:
        return m1.group(1).strip()
    m2 = re.search(r'(AIzaSy[\w\-]+|AQ\.[\w\-]+)', s)
    if m2:
        return m2.group(1).strip()
    return s.strip('"\'')


def load_env_api_key() -> Optional[str]:
    """Tìm API Key từ biến môi trường hoặc file .env.local / .env."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
    if key and key != "PLACEHOLDER_API_KEY":
        return key

    for env_file in [".env.local", ".env"]:
        if os.path.exists(env_file):
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#") or not line:
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k in ["GEMINI_API_KEY", "API_KEY"] and v and v != "PLACEHOLDER_API_KEY":
                                return v
            except Exception:
                pass
    return None


def image_to_base64_and_bytes(image_input: Union[str, bytes, Image.Image]):
    """Chuyển đổi input ảnh (file path, base64, bytes, PIL.Image) thành (bytes, mime_type, raw_base64)."""
    if isinstance(image_input, Image.Image):
        buf = io.BytesIO()
        image_input.save(buf, format="JPEG")
        img_bytes = buf.getvalue()
        b64_str = base64.b64encode(img_bytes).decode("utf-8")
        return img_bytes, "image/jpeg", b64_str

    if isinstance(image_input, bytes):
        img_bytes = image_input
        mime_type = "image/png" if img_bytes.startswith(b'\x89PNG') else "image/jpeg"
        b64_str = base64.b64encode(img_bytes).decode("utf-8")
        return img_bytes, mime_type, b64_str

    if isinstance(image_input, str):
        # Kiểm tra nếu là file tồn tại trên ổ cứng
        if os.path.isfile(image_input):
            with open(image_input, "rb") as f:
                img_bytes = f.read()
            mime_type = "image/png" if image_input.lower().endswith(".png") else "image/jpeg"
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            return img_bytes, mime_type, b64_str

        # Nếu là chuỗi data URL base64
        if image_input.startswith("data:image"):
            match = re.match(r"^data:(image/\w+);base64,(.+)$", image_input)
            if match:
                mime_type = match.group(1)
                b64_data = match.group(2)
                img_bytes = base64.b64decode(b64_data)
                return img_bytes, mime_type, b64_data

        # Nếu là raw base64
        try:
            img_bytes = base64.b64decode(image_input)
            mime_type = "image/jpeg"
            return img_bytes, mime_type, image_input
        except Exception:
            raise ValueError("Định dạng ảnh không hợp lệ (không phải đường dẫn file hoặc base64 hợp lệ).")

    raise ValueError(f"Không hỗ trợ định dạng ảnh loại {type(image_input)}")


# ==========================================================
# BỘ TẠO PROMPT CHUẨN TRÀ THƯƠNG PRO AI
# ==========================================================

def build_prompt(config: GenerationConfig, mode: AppMode, variation_index: int = 0, has_image: bool = False) -> str:
    """Tạo prompt chi tiết tương ứng với từng chế độ của Trà Thương Pro AI."""
    resolved_size = '4K' if config.imageSize == ImageSize.SIZE_6K else config.imageSize.value
    variation_seed = f"Variation {variation_index}: " if variation_index > 0 else ""

    if mode == AppMode.PORTRAIT_BEAUTY:
        pb = config.portraitBeauty or PortraitBeautyConfig()
        af = pb.autoFix
        h = pb.hair
        dt = pb.details

        adjustments = []
        if af.smoothSkin > 0: adjustments.append(f"smooth skin texture {af.smoothSkin}% (preserve natural skin texture and real pores, do not make it blurry or plastic)")
        if af.detail > 0: adjustments.append(f"increase fine facial details {af.detail}%")
        if af.evenSkin > 0: adjustments.append(f"even out skin tone {af.evenSkin}%")
        if af.evenFace > 0: adjustments.append(f"even facial tone {af.evenFace}%")
        if af.evenBody > 0: adjustments.append(f"even neck and body skin tone {af.evenBody}%")
        if af.whitening > 0: adjustments.append(f"brighten and lighten skin tone {af.whitening}%")
        if af.lighting > 0: adjustments.append(f"studio dimensional lighting and specular highlights {af.lighting}%")
        if af.features > 0: adjustments.append(f"sharpen facial features {af.features}%")

        if h.thickness > 0: adjustments.append(f"increase hair volume and thickness {h.thickness}%")
        if h.babyHair > 0: adjustments.append(f"clean up stray and messy baby hairs {h.babyHair}%")
        if h.smoothness > 0: adjustments.append(f"silky smooth hair finish {h.smoothness}%")

        if dt.teethWhitening > 0: adjustments.append(f"natural teeth whitening {dt.teethWhitening}%")
        if dt.blemishRemoval > 0: adjustments.append(f"blemish, acne and spot removal {dt.blemishRemoval}%")
        if dt.foreheadWrinkles > 0: adjustments.append(f"reduce forehead wrinkles {dt.foreheadWrinkles}%")
        if dt.eyeWrinkles > 0: adjustments.append(f"smooth out eye wrinkles and crow's feet {dt.eyeWrinkles}%")
        if dt.eyeBags > 0: adjustments.append(f"remove dark circles and under-eye bags {dt.eyeBags}%")
        if dt.smileLines > 0: adjustments.append(f"soften nasolabial smile lines {dt.smileLines}%")

        if not adjustments:
            enhancements_str = "Natural studio retouching: smooth skin 50% with preserved real skin pores, gentle whitening 30%, blemish and dark circle removal, natural teeth whitening, silky hair finish."
        else:
            enhancements_str = "Specific retouching settings: " + ", ".join(adjustments) + "."

        custom_desc = f" User instructions: {config.description}." if config.description else ""

        return (
            f"{variation_seed}High-end professional portrait retouching and beauty enhancement. "
            f"{enhancements_str}{custom_desc} "
            f"CRITICAL MANDATORY RULES: "
            f"1. 100% PRESERVE AND MAINTAIN THE ORIGINAL FACIAL FEATURES, EYES, NOSE, MOUTH, AND IDENTITY OF EVERY PERSON IN THE PHOTO EXACTLY AS THEY ARE. "
            f"2. DO NOT ALTER IDENTITY OR FACIAL BONE STRUCTURE. "
            f"3. Retain realistic skin texture and pores; avoid blurry, over-smoothed plastic effects. "
            f"4. High-end fashion editorial magazine cover quality, masterfully retouched, {resolved_size} ultra-high resolution."
        )

    elif mode == AppMode.RESTORE_OLD:
        ro = config.restoreOld or RestoreOldConfig()
        return (
            f"{variation_seed}Professional photo restoration. "
            f"Tasks: Colorize: {ro.colorize}, High quality: {ro.highQuality}, "
            f"Smooth skin: {ro.smoothSkin}, Remove wrinkles: {ro.removeWrinkles}. "
            f"Style: {'Khmer traditional' if ro.khmerStyle else 'Natural'}. "
            f"Background: {ro.background}. "
            f"Subject: {ro.numPeople} people, {ro.gender}, {ro.age}, {ro.smile} smile. "
            f"Advanced: {ro.advancedPrompt}. "
            f"MANDATORY: 100% PRESERVE THE ORIGINAL FACIAL FEATURES AND IDENTITY EXACTLY AS THEY ARE. "
            f"Restore clarity, fix scratches, and enhance resolution without changing the person's face, {resolved_size} resolution."
        )

    elif mode == AppMode.AI_WEDDING:
        if has_image:
            keep_clothing = getattr(config, 'keepOriginalClothing', True)
            if keep_clothing:
                preserve_rule = (
                    "CRITICAL STRICT PRESERVATION MANDATE (MANDATORY):\n"
                    "1. PRESERVE 100% ORIGINAL CLOTHING, FABRIC & JEWELRY: The traditional wedding attire, gold necklace, pendant, intricate embroidery patterns, fabric texture, and traditional accessories of both the bride and groom MUST BE 100% PRESERVED EXACTLY AS SHOWN IN THE REFERENCE IMAGE. DO NOT CHANGE, DO NOT SIMPLIFY, AND DO NOT BLUR THE EMBROIDERY OR JEWELRY.\n"
                    "2. PRESERVE 100% ORIGINAL EYES, EYELIDS & FACIAL IDENTITY: The eyes, eyelid creases, pupil shape, gaze, expression, and facial structure of both the bride and groom MUST REMAIN 100% UNCHANGED. DO NOT REDRAW OR ALTER THE EYES.\n"
                    "3. ONLY REPLACE THE BACKGROUND: Seamlessly cut out the bride and groom together with their authentic clothes, hair, and jewelry, and place them into the new wedding studio background with matching ambient light and shadow.\n"
                )
            else:
                preserve_rule = (
                    "CRITICAL FACIAL PRESERVATION: 100% PRESERVE THE ORIGINAL FACE, EYES, EYELIDS, AND FACIAL IDENTITY EXACTLY AS THEY ARE. "
                    "DO NOT ALTER THE EYES OR FACE SHAPE. You may replace the clothing and background to fit the wedding theme.\n"
                )
        else:
            preserve_rule = ""

        return (
            f"{variation_seed}Professional wedding photography in {config.country.value} style. "
            f"Scene: {config.scene}. Lighting: {config.lighting}. Foreground: {config.foreground}. "
            f"Description: {config.description}. "
            f"{preserve_rule}Cinematic, romantic, high-end wedding studio quality, {resolved_size} resolution, "
            f"ultra-clear, sharp details, RAW photo, uncompressed, masterpiece, extreme micro-details, highest quality possible."
        )

    elif mode == AppMode.AI_BIRTHDAY:
        preserve_rule = (
            "MANDATORY: 100% PRESERVE THE ORIGINAL FACE, FACIAL FEATURES, AND IDENTITY EXACTLY AS THEY ARE. "
            "DO NOT MODIFY THE FACE. ONLY REPLACE BACKGROUND AND CLOTHING. " if has_image else ""
        )
        return (
            f"{variation_seed}Professional birthday photography. "
            f"Category: {config.mode}. Country style: {config.country.value}. "
            f"Lighting: {config.lighting}. Foreground: {config.foreground}. "
            f"Description: {config.description}. "
            f"{preserve_rule}Festive, joyful, high-end studio setup with balloons and decorations, {resolved_size} resolution, "
            f"ultra-clear, sharp details, RAW photo, uncompressed, masterpiece, extreme micro-details, highest quality possible."
        )

    elif mode == AppMode.AI_FAMILY:
        preserve_rule = (
            "MANDATORY: 100% PRESERVE ALL ORIGINAL FACES, FACIAL FEATURES, AND IDENTITIES EXACTLY AS THEY ARE. "
            "DO NOT MODIFY THE FACES. " if has_image else ""
        )
        return (
            f"{variation_seed}Professional family portrait. "
            f"Description: {config.description}. "
            f"{preserve_rule}Combine subjects into a harmonious family photo. High-end studio lighting, "
            f"warm atmosphere, photorealistic, {resolved_size} resolution, ultra-clear, sharp details, "
            f"RAW photo, uncompressed, masterpiece, extreme micro-details, highest quality possible."
        )

    elif mode == AppMode.TEXT_TO_IMAGE:
        return (
            f"{variation_seed}Professional studio photography, {config.description}. "
            f"Style: {config.country.value}. Lighting: {config.lighting}. Foreground elements: {config.foreground}. "
            f"Ultra-high definition {resolved_size} resolution, cinematic lighting, photorealistic, ultra-clear, "
            f"sharp details, RAW photo, uncompressed, masterpiece, extreme micro-details, highest quality possible."
        )

    elif mode == AppMode.REMOVE_OBJECT:
        prompt_desc = config.removeObjectPrompt or config.description
        return (
            f"{variation_seed}Image editing: Remove objects. "
            f"Instruction: {prompt_desc}. "
            f"Seamlessly remove the specified objects and fill the background naturally."
        )

    elif mode == AppMode.COPY_SKIN:
        return (
            f"{variation_seed}Professional skin tone retouching. "
            f"Match the skin tone and texture perfectly while 100% preserving original facial identity and clarity. "
            f"{resolved_size} resolution, high-end photography."
        )

    else:
        return (
            f"{variation_seed}{mode.value} photography. {config.description}. "
            f"Photorealistic, {resolved_size} quality."
        )


# ==========================================================
# LỚP KẾT QUẢ TẠO ẢNH
# ==========================================================

class GeneratedImageResult:
    def __init__(self, index: int, image_bytes: bytes, mime_type: str = "image/png", prompt_used: str = ""):
        self.index = index
        self.image_bytes = image_bytes
        self.mime_type = mime_type
        self.prompt_used = prompt_used

    def to_pil(self) -> Image.Image:
        """Chuyển đổi thành PIL Image."""
        return Image.open(io.BytesIO(self.image_bytes))

    def to_base64_data_url(self) -> str:
        """Chuyển đổi thành data:image/...;base64 URL."""
        b64 = base64.b64encode(self.image_bytes).decode("utf-8")
        return f"data:{self.mime_type};base64,{b64}"

    def save(self, filepath: str):
        """Lưu ảnh ra đường dẫn chỉ định."""
        dir_name = os.path.dirname(filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(self.image_bytes)
        return filepath


# ==========================================================
# HÀM GỌI API GEMINI (PYTHON GOOGLE-GENAI SDK)
# ==========================================================

def get_gemini_client(api_key: Optional[str] = None):
    """Khởi tạo Google GenAI Client."""
    if genai is None:
        raise ImportError(
            "Chưa cài đặt thư viện google-genai. Vui lòng chạy lệnh:\n"
            "pip install google-genai"
        )

    resolved_key = api_key or load_env_api_key()
    if not resolved_key:
        raise ValueError(
            "Không tìm thấy Google Gemini API Key!\n"
            "Vui lòng thiết lập biến môi trường GEMINI_API_KEY hoặc truyền tham số api_key."
        )
    return genai.Client(api_key=resolved_key)


def generate_single_image(
    client,
    config: GenerationConfig,
    mode: AppMode,
    variation_index: int = 0
) -> GeneratedImageResult:
    """Tạo 1 ảnh đơn lẻ với cơ chế fallback model."""
    img_bytes = None
    mime_type = "image/jpeg"
    has_image = bool(config.uploadedImage)

    if has_image:
        img_bytes, mime_type, _ = image_to_base64_and_bytes(config.uploadedImage)

    prompt = build_prompt(config, mode, variation_index, has_image=has_image)
    resolved_image_size = '4K' if config.imageSize == ImageSize.SIZE_6K else config.imageSize.value

    def attempt_gen(model_name: str, supports_high_res: bool) -> GeneratedImageResult:
        contents = []
        if has_image and img_bytes:
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))
        contents.append(prompt)

        # Cấu hình ảnh
        img_cfg_args = {"aspect_ratio": config.aspectRatio.value}
        if supports_high_res:
            img_cfg_args["image_size"] = resolved_image_size

        image_config = types.ImageConfig(**img_cfg_args)
        gen_content_config = types.GenerateContentConfig(image_config=image_config)

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=gen_content_config
        )

        # Lấy dữ liệu ảnh trả về
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if getattr(part, 'inline_data', None) is not None:
                    raw_data = part.inline_data.data
                    out_mime = getattr(part.inline_data, 'mime_type', 'image/png')
                    # Nếu là string base64
                    if isinstance(raw_data, str):
                        raw_bytes = base64.b64decode(raw_data)
                    else:
                        raw_bytes = raw_data
                    return GeneratedImageResult(
                        index=variation_index,
                        image_bytes=raw_bytes,
                        mime_type=out_mime,
                        prompt_used=prompt
                    )

        raise RuntimeError(f"Model {model_name} không trả về dữ liệu ảnh hợp lệ.")

    # Thử gemini-3.1-flash-image-preview trước, nếu lỗi thì chuyển sang gemini-2.5-flash-image
    try:
        return attempt_gen('gemini-3.1-flash-image-preview', supports_high_res=True)
    except Exception as first_error:
        try:
            return attempt_gen('gemini-2.5-flash-image', supports_high_res=False)
        except Exception as second_error:
            raise RuntimeError(
                f"Lỗi tạo ảnh:\n"
                f"- Thử nghiệm gemini-3.1-flash: {first_error}\n"
                f"- Thử nghiệm gemini-2.5-flash: {second_error}"
            )


def generate_ai_images(
    config: GenerationConfig,
    mode: AppMode,
    api_key: Optional[str] = None,
    max_workers: int = 4
) -> List[GeneratedImageResult]:
    """
    Hàm tạo ảnh chính của Trà Thương Pro AI (hỗ trợ tạo nhiều ảnh song song).
    - Hỗ trợ chế độ UPSCALE bằng SeedVR2 DiT AI Diffusion (ComfyUI-SeedVR2_VideoUpscaler-main).
    - Hỗ trợ chế độ PORTRAIT_BEAUTY làm đẹp chân dung cục bộ.
    - Hỗ trợ các chế độ Gemini AI Cloud (Ảnh cưới, Sinh nhật, Gia đình, Phục hồi ảnh cũ...).
    """
    # 1. Chế độ Nâng độ phân giải (Upscale SeedVR2 DiT AI Diffusion)
    if mode == AppMode.UPSCALE:
        import upscale_engine as ue
        import cv2
        if not config.uploadedImage:
            raise ValueError("Vui lòng tải ảnh lên để nâng cấp độ phân giải (Upscale).")
        upscale_cfg = getattr(config, "upscale", None)
        if isinstance(upscale_cfg, dict):
            scale = upscale_cfg.get("scale", "4x")
            target_res = upscale_cfg.get("targetRes", "4K")
            sharpness = int(upscale_cfg.get("sharpness", 50))
            denoise = int(upscale_cfg.get("denoise", 0))
            enhance_face = bool(upscale_cfg.get("enhanceFace", True))
        elif upscale_cfg is not None:
            scale = getattr(upscale_cfg, "scale", "4x")
            target_res = getattr(upscale_cfg, "targetRes", "4K")
            sharpness = int(getattr(upscale_cfg, "sharpness", 50))
            denoise = int(getattr(upscale_cfg, "denoise", 0))
            enhance_face = bool(getattr(upscale_cfg, "enhanceFace", True))
        else:
            scale = "4x"
            target_res = "4K"
            sharpness = 50
            denoise = 0
            enhance_face = True

        bgr, meta = ue.upscale_image(
            config.uploadedImage,
            mode="seedvr2_ai",
            scale=scale,
            target_res=target_res,
            sharpness=sharpness,
            denoise=denoise,
            enhance_face=enhance_face
        )
        _, buf = cv2.imencode('.jpg', bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 98])
        raw_bytes = buf.tobytes()
        return [GeneratedImageResult(
            index=0,
            image_bytes=raw_bytes,
            mime_type="image/jpeg",
            prompt_used=f"Upscale SeedVR2 DiT AI ({meta.get('engine', '')}, Scale={scale})"
        )]

    # 2. Chế độ Làm đẹp chân dung cục bộ
    if mode == AppMode.PORTRAIT_BEAUTY:
        import portrait_engine as pe
        import cv2
        if not config.uploadedImage:
            raise ValueError("Vui lòng tải ảnh lên để làm đẹp chân dung.")
        bgr = pe.load_bgr_from_data_url_or_path(config.uploadedImage)
        pb_dict = config.portraitBeauty.dict() if hasattr(config.portraitBeauty, "dict") else (config.portraitBeauty or {})
        retouched_bgr = pe.retouch_portrait_local(bgr, pb_dict)
        _, buf = cv2.imencode('.jpg', retouched_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        raw_bytes = buf.tobytes()
        return [GeneratedImageResult(
            index=0,
            image_bytes=raw_bytes,
            mime_type="image/jpeg",
            prompt_used="Làm đẹp chân dung cục bộ"
        )]

    client = get_gemini_client(api_key)
    num_images = max(1, min(config.numImages, 4))

    if num_images == 1:
        return [generate_single_image(client, config, mode, 0)]

    results: List[Optional[GeneratedImageResult]] = [None] * num_images
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(generate_single_image, client, config, mode, i): i
            for i in range(num_images)
        }
        for future in futures:
            idx = futures[future]
            results[idx] = future.result()

    return [r for r in results if r is not None]


def upscale_image_seedvr2(
    image_input,
    scale: str = "4x",
    target_res: str = "4K",
    sharpness: int = 50,
    denoise: int = 0,
    enhance_face: bool = True
):
    """
    Hàm tiện ích nâng độ phân giải trực tiếp sử dụng mã nguồn SeedVR2 DiT AI từ:
    C:\\Users\\POI\\Desktop\\remix_-trà-thương-pro-ai\\ComfyUI-SeedVR2_VideoUpscaler-main
    """
    import upscale_engine as ue
    return ue.upscale_image(
        image_input,
        mode="seedvr2_ai",
        scale=scale,
        target_res=target_res,
        sharpness=sharpness,
        denoise=denoise,
        enhance_face=enhance_face
    )


if __name__ == "__main__":
    import sys
    print("=" * 65)
    print("      TRÀ THƯƠNG PRO AI - HỆ THỐNG XỬ LÝ ẢNH CHUYÊN NGHIỆP")
    print("=" * 65)

    # Nếu người dùng truyền tham số dòng lệnh CLI (ví dụ --mode, --image, ...)
    if len(sys.argv) > 1 and any(arg.startswith("-") for arg in sys.argv[1:]):
        from cli import main as cli_main
        cli_main()
    else:
        # Mặc định khởi chạy giao diện GUI Desktop
        print("\n[THÔNG BÁO] Đang tự động mở Giao diện Trà Thương Pro AI...")
        print("💡 Bạn cũng có thể khởi chạy trực tiếp bằng lệnh:")
        print("   python app_gui.py   (hoặc python run.py)\n")
        try:
            from server import run_server
            run_server()
        except Exception as e:
            print(f"[LỖI] Không thể khởi chạy máy chủ giao diện: {e}")


