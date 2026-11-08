import subprocess, os

chrome_bin = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile_dir = r"C:\Users\POI\AppData\Roaming\em-bong-ai-muse-studio\data\chrome-visible-profile"
os.makedirs(profile_dir, exist_ok=True)

# Clean locks
for f in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
    p = os.path.join(profile_dir, f)
    if os.path.exists(p):
        try: os.unlink(p)
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

# Detached process so it stays alive forever
DETACHED_PROCESS = 0x00000008
p = subprocess.Popen(cmd, creationflags=DETACHED_PROCESS, close_fds=True)
print("Spawned Chrome with PID:", p.pid)

