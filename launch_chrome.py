import sys, subprocess, os
sys.path.insert(0, r"C:\Users\POI\Desktop\New folder (5)")
import muse_cdp_engine, muse_store

store = muse_store.MuseStore()
eng = muse_cdp_engine.MuseCdpEngine(store, cdp_port=9225)
chrome_bin = muse_cdp_engine.find_chrome_binary("")
profile_dir = os.path.join(store.data_dir, "chrome-visible-profile")
os.makedirs(profile_dir, exist_ok=True)

# Remove locks
for lock in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
    lp = os.path.join(profile_dir, lock)
    if os.path.exists(lp):
        try: os.unlink(lp)
        except: pass

cmd = [
    chrome_bin,
    "--remote-debugging-port=9225",
    "--remote-allow-origins=*",
    f"--user-data-dir={profile_dir}",
    "--no-first-run",
    "--no-default-browser-check",
    "https://accounts.google.com/ServiceLogin?continue=https://gemini.google.com/app?hl=vi"
]
print("Launching:", cmd)
proc = subprocess.Popen(cmd)
print("PID:", proc.pid)

