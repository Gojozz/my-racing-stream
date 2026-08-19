import pytchat
import time
import os
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from googleapiclient.discovery import build

# =========================================================
# KONFIGURASI
# =========================================================
VIDEO_ID = os.environ.get("YOUTUBE_LIVE_ID", "").strip()
API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()

STATE_FILE = Path("chat_state.json")
MAX_PLAYERS = 5
ROTATION_PORT = 8765
last_processed_race = None


def find_live_video_id():
    """Cari Video ID live yang sedang aktif di channel."""
    if not API_KEY or not CHANNEL_ID:
        print("[AUTO] YOUTUBE_API_KEY atau YOUTUBE_CHANNEL_ID belum diisi.")
        return None

    try:
        youtube = build("youtube", "v3", developerKey=API_KEY)
        request = youtube.search().list(
            part="snippet",
            channelId=CHANNEL_ID,
            eventType="live",
            type="video",
            maxResults=1
        )
        response = request.execute()
        items = response.get("items", [])
        if not items:
            print("[AUTO] Tidak ditemukan live stream aktif di channel ini.")
            return None

        video_id = items[0]["id"]["videoId"]
        title = items[0]["snippet"]["title"]
        print(f"[AUTO] Ditemukan live: {title}")
        print(f"[AUTO] Video ID : {video_id}")
        return video_id

    except Exception as e:
        print(f"[AUTO ERROR] Gagal mencari live: {e}")
        return None


def load_state():
    if not STATE_FILE.exists():
        return {"active": [], "queue": [], "lastUpdate": 0}
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            state = json.load(f)
        state.setdefault("active", [])
        state.setdefault("queue", [])
        state.setdefault("lastUpdate", 0)
        return state
    except Exception as e:
        print(f"[STATE ERROR] {e}")
        return {"active": [], "queue": [], "lastUpdate": 0}


def save_state(state):
    state["lastUpdate"] = time.time()
    fd, temp_path = tempfile.mkstemp(prefix="chat_state_", suffix=".tmp", dir=".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, STATE_FILE)
    except Exception:
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        raise


def normalize_user(user):
    return str(user).strip()


def rotate_after_race(eliminated_name):
    global last_processed_race
    state = load_state()
    eliminated_index = None

    for i, player in enumerate(state["active"]):
        name = str(player.get("name", player.get("user", "")))
        user = str(player.get("user", ""))
        if name.lower() == str(eliminated_name).lower() or user.lower() == str(eliminated_name).lower():
            eliminated_index = i
            break

    if eliminated_index is None:
        print(f"[ROTATE] Pemain tidak ditemukan: {eliminated_name}")
        return False

    eliminated = state["active"].pop(eliminated_index)
    incoming = None
    if state["queue"] and len(state["active"]) < MAX_PLAYERS:
        incoming = state["queue"].pop(0)
        state["active"].append(incoming)

    save_state(state)

    print("====================================")
    print(f"[ROTATE] KELUAR : {eliminated.get('name', eliminated.get('user'))}")
    if incoming:
        print(f"[ROTATE] MASUK  : {incoming.get('name', incoming.get('user'))}")
    else:
        print("[ROTATE] MASUK  : TIDAK ADA (ANTREAN KOSONG)")
    print(f"[ROTATE] AKTIF  : {[p.get('name', p.get('user')) for p in state['active']]}")
    print(f"[ROTATE] QUEUE  : {[p.get('name', p.get('user')) for p in state['queue']]}")
    print("====================================")
    return True


class RaceResultHandler(BaseHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path != "/race-result":
            self.send_response(404)
            self.send_cors_headers()
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))
            race_id = str(data.get("raceId", "")).strip()
            eliminated = str(data.get("eliminated", "")).strip()

            if not race_id or not eliminated:
                self.send_response(400)
                self.send_cors_headers()
                self.end_headers()
                return

            global last_processed_race
            if race_id == last_processed_race:
                self.send_response(200)
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b"already processed")
                return

            if rotate_after_race(eliminated):
                last_processed_race = race_id
                self.send_response(200)
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b"rotation ok")
            else:
                self.send_response(404)
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b"player not found")
        except Exception as e:
            print(f"[ROTATION ERROR] {e}")
            self.send_response(500)
            self.send_cors_headers()
            self.end_headers()

    def log_message(self, format, *args):
        return


def start_rotation_server():
    server = ThreadingHTTPServer(("127.0.0.1", ROTATION_PORT), RaceResultHandler)
    print(f"[ROTATION SERVER] http://127.0.0.1:{ROTATION_PORT}")
    server.serve_forever()


def already_joined(state, user):
    active_names = {p["user"].lower() for p in state["active"]}
    queue_names = {p["user"].lower() for p in state["queue"]}
    return user.lower() in active_names or user.lower() in queue_names


def add_player(state, user):
    if already_joined(state, user):
        return "already"
    player = {"user": user, "name": user, "joinedAt": time.time()}
    if len(state["active"]) < MAX_PLAYERS:
        state["active"].append(player)
        return "active"
    state["queue"].append(player)
    return "queue"


def create_chat_with_retry(video_id, max_retries=12, delay=8):
    """
    Coba buat koneksi pytchat berkali-kali.
    Live baru sering belum siap dibaca chat-nya.
    """
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[CHAT] Mencoba koneksi chat... ({attempt}/{max_retries})")
            chat = pytchat.create(video_id=video_id)
            # Cek cepat apakah chat hidup
            if chat.is_alive():
                print(f"[CHAT] Koneksi berhasil pada percobaan {attempt}")
                return chat
            else:
                print(f"[CHAT] Chat object dibuat tapi belum alive, coba lagi...")
                try:
                    chat.terminate()
                except Exception:
                    pass
        except Exception as e:
            print(f"[CHAT] Gagal percobaan {attempt}: {e}")

        if attempt < max_retries:
            print(f"[CHAT] Tunggu {delay} detik sebelum coba lagi...")
            time.sleep(delay)

    return None


def start_bot():
    global VIDEO_ID

    print("====================================")
    print(" CHAT JOIN SYSTEM ONLINE")
    print("====================================")

    # 1. Dapatkan Video ID
    if VIDEO_ID:
        print(f"[MANUAL] Menggunakan YOUTUBE_LIVE_ID: {VIDEO_ID}")
    else:
        print("[AUTO] YOUTUBE_LIVE_ID kosong, mencari live aktif...")
        for attempt in range(1, 16):
            print(f"[AUTO] Percobaan {attempt}/15 mencari live...")
            found_id = find_live_video_id()
            if found_id:
                VIDEO_ID = found_id
                break
            time.sleep(5)

        if not VIDEO_ID:
            print("ERROR: Tidak berhasil menemukan live stream aktif.")
            print("Pastikan stream sudah LIVE dan secret API sudah benar.")
            return

    print(f"[BOT] Live ID yang dipakai: {VIDEO_ID}")
    print(f"[BOT] Max aktif: {MAX_PLAYERS}")
    print("====================================")

    # 2. Inisialisasi state
    state = load_state()
    save_state(state)

    # 3. Server rotasi
    threading.Thread(target=start_rotation_server, daemon=True).start()

    # 4. Koneksi chat dengan retry
    print("[CHAT] Menunggu chat siap (live baru sering butuh waktu)...")
    time.sleep(10)  # jeda awal setelah live terdeteksi

    chat = create_chat_with_retry(VIDEO_ID, max_retries=12, delay=8)

    if chat is None:
        print("ERROR: Gagal konek ke live chat setelah banyak percobaan.")
        print("Kemungkinan:")
        print("  - Live chat belum aktif / dimatikan")
        print("  - Video ID tidak valid untuk pytchat")
        print("  - Masalah sementara dari YouTube")
        return

    print(f"Bot mendengarkan live chat ID: {VIDEO_ID}")
    print("Siap menerima perintah: join")

    # 5. Loop baca chat
    while True:
        try:
            if not chat.is_alive():
                print("[CHAT] Koneksi chat berhenti. Mencoba reconnect...")
                time.sleep(5)
                chat = create_chat_with_retry(VIDEO_ID, max_retries=5, delay=5)
                if chat is None:
                    print("[CHAT] Reconnect gagal total. Bot berhenti.")
                    break
                print("[CHAT] Reconnect berhasil.")
                continue

            for c in chat.get().sync_items():
                user = normalize_user(c.author.name)
                msg = c.message.lower().strip()

                if msg == "join" or msg.startswith("join "):
                    result = add_player(state, user)

                    if result == "active":
                        print(f"[JOIN] {user} -> PEMBALAP AKTIF ({len(state['active'])}/{MAX_PLAYERS})")
                        save_state(state)
                        print(f"[STATE] active: {[p['user'] for p in state['active']]}")
                    elif result == "queue":
                        position = len(state["queue"])
                        print(f"[QUEUE] {user} -> ANTREAN #{position}")
                        save_state(state)
                    else:
                        print(f"[IGNORE] {user} sudah terdaftar")

        except Exception as e:
            print(f"[CHAT ERROR] {e}")
            time.sleep(2)

        time.sleep(0.2)


if __name__ == "__main__":
    start_bot()
