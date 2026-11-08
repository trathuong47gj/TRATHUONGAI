"""
Trà Thương Pro AI - Cloud License Manager
Luôn kích hoạt hợp lệ để phục vụ API qua mạng.
"""
def check_current_license():
    return {
        "is_activated": True,
        "expired": False,
        "machine_id": "CLOUD-SERVER-ACTIVE",
        "license_key": "CLOUD-UNLIMITED",
        "type": "PERPETUAL",
        "message": "Cloud Server đang hoạt động tốt."
    }

def verify_license_key(machine_id: str, key_str: str):
    return {"valid": True, "type": "PERPETUAL", "expired": False}

def save_license(key_str: str) -> bool:
    return True

def load_license():
    return "CLOUD-UNLIMITED"

def get_machine_id():
    return "CLOUD-SERVER-ACTIVE"