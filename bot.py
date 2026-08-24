
def fetch_live_id_via_https(channel_id):
    if not channel_id:
        print("[AUTO LIVE ERROR] CHANNEL_ID tidak ditemukan!")
        return None
    url = f"https://www.youtube.com/channel/{channel_id}/live"
    print(f"[AUTO LIVE] Memeriksa stream live di: {url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        with httpx.Client(follow_redirects=True, timeout=15.0, headers=headers) as client:
            resp = client.get(url)
            m = re.search(r"v=([a-zA-Z0-9_-]{11})", str(resp.url))
            if m:
                print(f"[AUTO LIVE SUCCESS] Video ID ditemukan: {m.group(1)}")
                return m.group(1)
            m_html = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
            if m_html:
                print(f"[AUTO LIVE SUCCESS] Video ID ditemukan (HTML): {m_html.group(1)}")
                return m_html.group(1)
    except Exception as e:
        print(f"[AUTO LIVE ERROR] Gagal request HTTP: {e}")
    return None



def get_live_video_id(channel_id=None):
    env_id = os.environ.get("YOUTUBE_LIVE_ID", "").strip()
    if env_id:
        print(f"[AUTO LIVE] Menggunakan YOUTUBE_LIVE_ID dari Secret: {env_id}")
        return env_id

    cid = channel_id or os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()
    if not cid:
        print("[AUTO LIVE ERROR] YOUTUBE_CHANNEL_ID tidak ditemukan.")
        return None

    url = f"https://www.youtube.com/channel/{cid}/live"
    print(f"[AUTO LIVE] Mencari Live ID otomatis untuk Channel: {cid}...")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        with httpx.Client(follow_redirects=True, timeout=15.0, headers=headers) as client:
            resp = client.get(url)
            match = re.search(r"v=([a-zA-Z0-9_-]{11})", str(resp.url))
            if match:
                video_id = match.group(1)
                print(f"[AUTO LIVE SUCCESS] Live ID ditemukan dari redirect: {video_id}")
                return video_id

            match_html = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
            if match_html:
                video_id = match_html.group(1)
                print(f"[AUTO LIVE SUCCESS] Live ID ditemukan dari HTML: {video_id}")
                return video_id
    except Exception as e:
        print(f"[AUTO LIVE ERROR] Gagal deteksi otomatis: {e}")

    return None


import pytchat
import time
import os
import json
import tempfile
import threading
import re
import subprocess
import random
import queue
import httpx

from urllib.parse import quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from googleapiclient.discovery import build
# =========================================================
# PATCH pytchat — ambil channel ID lewat oEmbed
# =========================================================

import pytchat.util as pytchat_util
from pytchat.exceptions import InvalidVideoIdException


def _get_channelid_via_oembed(video_id: str):
    url = (
        "https://www.youtube.com/oembed?"
        f"url=https://www.youtube.com/watch?v={quote(video_id)}&format=json"
    )

    try:
        with httpx.Client(
            timeout=12,
            headers={
                "User-Agent":
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
        ) as client:

            r = client.get(url)

            if r.status_code != 200:
                print(f"[PATCH] oEmbed status: {r.status_code}")
                return None

            data = r.json()
            author_url = data.get("author_url", "")

            print(f"[PATCH] author_url: {author_url}")

            m = re.search(
                r"/channel/(UC[0-9A-Za-z_-]{22})",
                author_url
            )

            if m:
                return m.group(1)

            if "/@" in author_url:
                r2 = client.get(author_url, follow_redirects=True)

                m2 = re.search(
                    r'"externalId":"(UC[0-9A-Za-z_-]{22})"',
                    r2.text
                )

                if m2:
                    return m2.group(1)

                m3 = re.search(
                    r'"channelId":"(UC[0-9A-Za-z_-]{22})"',
                    r2.text
                )

                if m3:
                    return m3.group(1)

    except Exception as e:
        print(f"[PATCH] oEmbed gagal: {e}")

    return None


def robust_get_channelid(client, video_id):

    uc = _get_channelid_via_oembed(video_id)

    if uc:
        print(f"[PATCH] Channel ID dari oEmbed: {uc}")
        return uc

    print("[PATCH] oEmbed gagal, coba cara lama pytchat...")

    try:
        return pytchat_util.get_channelid_2nd(client, video_id)

    except Exception as e:
        print(f"[PATCH] Cara lama juga gagal: {e}")

        raise InvalidVideoIdException(
            f"Cannot find channel id for video id:{video_id}."
        )


pytchat_util.get_channelid = robust_get_channelid

print("[PATCH] pytchat get_channelid sudah di-patch (oEmbed)")


# =========================================================
# KONFIGURASI
# =========================================================

CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()
VIDEO_ID = ""  # deteksi di start_bot() setelah stream sempat live
API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()

STATE_FILE = Path("chat_state.json")

MAX_PLAYERS = 5
ROTATION_PORT = 8765

last_processed_race = None


# =========================================================
# LUNA AI
# =========================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

GROQ_MODEL = os.environ.get(
    "GROQ_MODEL",
    "qwen/qwen3.6-27b"
)

LUNA_SYSTEM_PROMPT = """
Kamu LUNA, komentator balap live yang cerewet, kocak, dan asal ngomong.
Bahasa: Indonesia gaul, tidak baku, kayak temen nonton balap bareng.
Boleh pakai: woy, gas, gila, buset, mantap, waduh, anjay (jangan kasar berlebih), auto, kepleset, ngebut.
Gaya: komentator overreact, bikin seru, jangan kaku, jangan formal.
Aturan:
- Selalu bahasa Indonesia santai
- Maksimal 1 kalimat pendek (max 16 kata)
- Jangan bilang kamu AI/bot/model
- Jangan menghina penonton
- Kalau balas chat: sebut nama singkat, langsung lucu
- Kalau komentar balap: seolah lihat mobil ngebut di lintasan
- PENTING: Jangan keluarkan thinking process terlalu panjang. Langsung jawab 1 kalimat pendek saja.
"""




# =========================================================
# TTS
# =========================================================

PIPER_BIN = os.environ.get("PIPER_BIN", "piper")

PIPER_MODEL = os.environ.get(
    "PIPER_MODEL",
    "models/id_ID-news_tts-medium.onnx"
)

tts_queue = queue.Queue()

tts_lock = threading.Lock()

last_tts_time = 0.0

CHAT_COOLDOWN = 4.0

last_chat_response = {}

ENGAGEMENT_INTERVAL = 90

last_engagement_time = time.time() - 10000

engagement_index = 0


ENGAGE_PROMOS = [
    "Woy jangan lupa laik-nya, biar balapannya nambah gila!",
    "Klik subs kreb dong, biar kagak ketinggalan balapan berikutnya!",
    "Komen di kolom komentar, LUNA baca kok, jangan diem aja!",
    "Laik, subs kreb, trus ketik join kalau berani turun lintasan!",
    "Yang baru datang: laik dulu, subs kreb, baru nonton sambil ngegas!",
    "Komen gas di kolom komentar, biar suasana langsung panas!",
    "Subs kreb-nya jangan pelit, balapan ini butuh dukungan kalian!",
    "Pencet laik biar algoritma gak tidur, balapan tetap ramai!",
]

JOIN_PROMOS = [
    "Mau turun ke lintasan? Ketik join di komentar, nama kalian jadi pembalap!",
    "Berani balapan? Ketik join, nanti nama kalian ikut ngegas!",
    "Jangan cuma nonton! Ketik join dan siap-siap jadi pembalap!",
    "Pengen balapan? Ketik join di komentar, siapa tahu mobil kalian paling brutal!",
    "Ketik join kalau berani! Nama kalian bisa muncul di lintasan!",
]



def clean_tts_text(text):

    text = str(text or "").strip()

    text = re.sub(
        r"https?://\S+",
        "",
        text
    )

    text = text.replace(
        "\n",
        " "
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text[:400].strip()


def run_piper(text):

    text = clean_tts_text(text)

    if not text:
        return False

    model_path = Path(PIPER_MODEL)
    if not model_path.exists():
        print(f"[TTS ERROR] Model tidak ditemukan: {model_path}")
        return False

    wav_path = Path(
        tempfile.mktemp(
            prefix="luna_",
            suffix=".wav"
        )
    )

    try:
        print(f"[TTS] {text}")
        print(f"[TTS] model={model_path}")
        print(f"[TTS] PULSE_SINK={os.environ.get('PULSE_SINK', '')}")

        process = subprocess.run(
            [
                PIPER_BIN,
                "--model",
                str(model_path),
                "--output_file",
                str(wav_path)
            ],
            input=(text + "\n").encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )

        if process.returncode != 0:
            print(
                "[TTS ERROR]",
                process.stderr.decode("utf-8", errors="replace")[-1000:]
            )
            return False

        if not wav_path.exists() or wav_path.stat().st_size < 100:
            print("[TTS ERROR] File WAV kosong / tidak dibuat")
            return False

        print(f"[TTS] WAV size={wav_path.stat().st_size} bytes")

        # Pastikan main ke stream_sink
        env = os.environ.copy()
        env["PULSE_SINK"] = env.get("PULSE_SINK", "stream_sink")

        # Set default sink (abaikan error jika sudah)
        subprocess.run(
            ["pactl", "set-default-sink", env["PULSE_SINK"]],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        result = subprocess.run(
            ["paplay", str(wav_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
            env=env
        )

        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")[-1000:]
            print("[PAPLAY ERROR]", err)

            # Fallback: coba device eksplisit
            result2 = subprocess.run(
                ["paplay", f"--device={env['PULSE_SINK']}", str(wav_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=45,
                env=env
            )
            if result2.returncode != 0:
                print(
                    "[PAPLAY ERROR2]",
                    result2.stderr.decode("utf-8", errors="replace")[-1000:]
                )
                return False

        print("[TTS] Playback OK")
        return True

    except Exception as e:
        print(f"[TTS ERROR] {e}")
        return False

    finally:
        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass


def tts_worker():

    global last_tts_time

    while True:

        text = tts_queue.get()

        if text is None:
            break

        try:

            with tts_lock:

                now = time.time()

                elapsed = now - last_tts_time

                if elapsed < 1.0:
                    time.sleep(
                        1.0 - elapsed
                    )

                if run_piper(text):
                    last_tts_time = time.time()

        except Exception as e:

            print(f"[TTS WORKER ERROR] {e}")

        finally:
            tts_queue.task_done()


threading.Thread(
    target=tts_worker,
    daemon=True
).start()



def pick_engagement_line():
    global engagement_index
    engagement_index += 1
    # 2x ajakan sosmed, 1x ajakan join
    if engagement_index % 3 == 0:
        return random.choice(JOIN_PROMOS)
    return random.choice(ENGAGE_PROMOS)

def speak(text):

    text = clean_tts_text(text)

    if not text:
        return

    if len(text) > 180:
        text = text[:177] + "..."

    try:
        tts_queue.put_nowait(text)
    except queue.Full:
        print("[TTS] Queue penuh, ucapan dilewati.")


# =========================================================
# GROQ RESPONSE
# =========================================================








def strip_model_thinking(text):
    """Buang chain-of-thought + ambil jawaban final atau draft."""
    text = str(text or "")

    # 1. Kalau ada </think>, ambil bagian setelahnya
    if re.search(r"</think>", text, flags=re.I):
        parts = re.split(r"</think>", text, flags=re.I)
        final = parts[-1].strip()
        if final:
            final = re.sub(r"</?think>", "", final, flags=re.I)
            final = re.sub(r"\s+", " ", final).strip()
            if final:
                return final

    # 2. Coba ambil draft yang biasa ditulis model di dalam thinking
    #    Contoh: - "Woy Tanidong, pagi-pagi udah gaspol..."
    draft_patterns = [
        r'[-•*]\s*"([^"]{10,120})"',
        r'Draft[^:]*:\s*"([^"]{10,120})"',
        r'jawaban[^:]*:\s*"([^"]{10,120})"',
        r'reply[^:]*:\s*"([^"]{10,120})"',
        r'"([A-Z][^"]{15,100})"',
    ]
    for pat in draft_patterns:
        m = re.search(pat, text, flags=re.I | re.DOTALL)
        if m:
            candidate = m.group(1).strip()
            # Pastikan kelihatan seperti kalimat Indonesia
            if any(w in candidate.lower() for w in ["woy", "gas", "mantap", "pagi", "bro", "gila", "buset", "anjay", "lintasan", "balap", "nonton"]):
                return candidate

    # 3. Kalau masih ada <think> dan tidak ketemu draft → kosong
    if re.search(r"<think>", text, flags=re.I):
        return ""

    # 4. Fallback: bersihkan tag saja
    text = re.sub(r"</?think>", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def engagement_loop():

    global last_engagement_time
    global engagement_index

    print("[ENGAGEMENT] Thread aktif.")

    while True:

        try:

            time.sleep(5)

            now = time.time()

            if now - last_engagement_time < ENGAGEMENT_INTERVAL:
                continue

            last_engagement_time = now

            # Bergantian:
            # 0 = like/subscribe/share
            # 1 = join

            text = pick_engagement_line()
            # engagement_index di dalam helper

            print(
                f"[ENGAGEMENT] {text}"
            )

            speak(text)

        except Exception as e:

            print(
                f"[ENGAGEMENT ERROR] {e}"
            )

            time.sleep(5)


threading.Thread(
    target=engagement_loop,
    daemon=True
).start()


# =========================================================
# YOUTUBE LIVE DETECTION
# =========================================================

def find_live_video_id():

    if not API_KEY or not CHANNEL_ID:

        print(
            "[AUTO] YOUTUBE_API_KEY atau "
            "YOUTUBE_CHANNEL_ID belum diisi."
        )

        return None

    try:

        youtube = build(
            "youtube",
            "v3",
            developerKey=API_KEY
        )

        request = youtube.search().list(

            part="snippet",

            channelId=CHANNEL_ID,

            eventType="live",

            type="video",

            maxResults=1
        )

        response = request.execute()

        items = response.get(
            "items",
            []
        )

        if not items:

            print(
                "[AUTO] Tidak ditemukan live stream aktif."
            )

            return None

        video_id = (
            items[0]["id"]["videoId"]
        )

        title = (
            items[0]["snippet"]["title"]
        )

        print(
            f"[AUTO] Ditemukan live: {title}"
        )

        print(
            f"[AUTO] Video ID : {video_id}"
        )

        return video_id

    except Exception as e:

        print(
            f"[AUTO ERROR] {e}"
        )

        return None


# =========================================================
# JOIN SYSTEM — TIDAK DIUBAH
# =========================================================

def load_state():

    if not STATE_FILE.exists():

        return {
            "active": [],
            "queue": [],
            "lastUpdate": 0
        }

    try:

        with STATE_FILE.open(
            "r",
            encoding="utf-8"
        ) as f:

            state = json.load(f)

        state.setdefault(
            "active",
            []
        )

        state.setdefault(
            "queue",
            []
        )

        state.setdefault(
            "lastUpdate",
            0
        )

        return state

    except Exception as e:

        print(
            f"[STATE ERROR] {e}"
        )

        return {
            "active": [],
            "queue": [],
            "lastUpdate": 0
        }


def save_state(state):

    state["lastUpdate"] = time.time()

    fd, temp_path = tempfile.mkstemp(
        prefix="chat_state_",
        suffix=".tmp",
        dir="."
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                state,
                f,
                ensure_ascii=False,
                indent=2
            )

            f.flush()

            os.fsync(
                f.fileno()
            )

        os.replace(
            temp_path,
            STATE_FILE
        )

    except Exception:

        try:
            os.unlink(
                temp_path
            )
        except Exception:
            pass

        raise


def normalize_user(user):
    return str(user).strip()


def already_joined(state, user):

    active_names = {
        p["user"].lower()
        for p in state["active"]
    }

    queue_names = {
        p["user"].lower()
        for p in state["queue"]
    }

    return (
        user.lower() in active_names
        or
        user.lower() in queue_names
    )


def add_player(state, user):

    if already_joined(state, user):
        return "already"

    player = {
        "user": user,
        "name": user,
        "joinedAt": time.time()
    }

    if len(state["active"]) < MAX_PLAYERS:

        state["active"].append(player)

        return "active"

    state["queue"].append(player)

    return "queue"


def rotate_after_race(eliminated_name):

    global last_processed_race

    state = load_state()

    eliminated_index = None

    for i, player in enumerate(
        state["active"]
    ):

        name = str(
            player.get(
                "name",
                player.get("user", "")
            )
        )

        user = str(
            player.get(
                "user",
                ""
            )
        )

        if (
            name.lower()
            ==
            str(eliminated_name).lower()
            or
            user.lower()
            ==
            str(eliminated_name).lower()
        ):

            eliminated_index = i

            break

    if eliminated_index is None:

        print(
            f"[ROTATE] Pemain tidak ditemukan: "
            f"{eliminated_name}"
        )

        return False

    eliminated = state["active"].pop(
        eliminated_index
    )

    incoming = None

    if (
        state["queue"]
        and
        len(state["active"]) < MAX_PLAYERS
    ):

        incoming = state["queue"].pop(0)

        state["active"].append(
            incoming
        )

    save_state(state)

    print("====================================")

    print(
        f"[ROTATE] KELUAR : "
        f"{eliminated.get('name', eliminated.get('user'))}"
    )

    if incoming:

        print(
            f"[ROTATE] MASUK  : "
            f"{incoming.get('name', incoming.get('user'))}"
        )

    else:

        print(
            "[ROTATE] MASUK  : TIDAK ADA "
            "(ANTREAN KOSONG)"
        )

    print(
        f"[ROTATE] AKTIF  : "
        f"{[p.get('name', p.get('user')) for p in state['active']]}"
    )

    print(
        f"[ROTATE] QUEUE  : "
        f"{[p.get('name', p.get('user')) for p in state['queue']]}"
    )

    print("====================================")

    return True


# =========================================================
# RACE RESULT SERVER — TIDAK DIUBAH
# =========================================================

class RaceResultHandler(
    BaseHTTPRequestHandler
):

    def send_cors_headers(self):

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "POST, OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )

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

            length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            body = self.rfile.read(
                length
            )

            data = json.loads(
                body.decode("utf-8")
            )

            race_id = str(
                data.get(
                    "raceId",
                    ""
                )
            ).strip()

            eliminated = str(
                data.get(
                    "eliminated",
                    ""
                )
            ).strip()

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

                self.wfile.write(
                    b"already processed"
                )

                return

            if rotate_after_race(
                eliminated
            ):

                last_processed_race = race_id

                self.send_response(200)

                self.send_cors_headers()

                self.end_headers()

                self.wfile.write(
                    b"rotation ok"
                )

            else:

                self.send_response(404)

                self.send_cors_headers()

                self.end_headers()

                self.wfile.write(
                    b"player not found"
                )

        except Exception as e:

            print(
                f"[ROTATION ERROR] {e}"
            )

            self.send_response(500)

            self.send_cors_headers()

            self.end_headers()

    def log_message(
        self,
        format,
        *args
    ):
        return


def start_rotation_server():

    server = ThreadingHTTPServer(
        (
            "127.0.0.1",
            ROTATION_PORT
        ),
        RaceResultHandler
    )

    print(
        f"[ROTATION SERVER] "
        f"http://127.0.0.1:{ROTATION_PORT}"
    )

    server.serve_forever()



# =========================================================
# TEMPLATE CHAT — TANPA AI
# =========================================================

CHAT_TEMPLATES = {}

def load_chat_templates():
    CHAT_TEMPLATES.clear()

    template_dir = Path("templates")

    if not template_dir.exists():
        print("[TEMPLATE] folder templates belum ada")
        return

    for path in sorted(template_dir.glob("*.txt")):
        try:
            lines = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            if lines:
                CHAT_TEMPLATES[path.stem] = lines

        except Exception as e:
            print(f"[TEMPLATE ERROR] {path}: {e}")

    total = sum(len(v) for v in CHAT_TEMPLATES.values())

    print(
        f"[TEMPLATE] {len(CHAT_TEMPLATES)} kategori, "
        f"{total} template dimuat"
    )


def template_category(text):
    t = str(text or "").lower().strip()

    if "?" in t or any(
        w in t.split()
        for w in [
            "apa", "siapa", "kenapa", "kok",
            "gimana", "bagaimana", "kapan",
            "dimana", "berapa"
        ]
    ):
        return "question"

    if any(
        w in t.split()
        for w in [
            "join", "ikut", "main", "turun",
            "daftar", "gabung"
        ]
    ):
        return "join"

    if any(
        w in t
        for w in ["wkwk", "haha", "hehe", "lol"]
    ):
        return "laugh"

    if any(
        w in t
        for w in [
            "balap", "balapan", "race", "lap",
            "mobil", "overtake", "nyalip",
            "finish", "p1", "p2", "p3"
        ]
    ):
        return "racing"

    if any(
        w in t
        for w in [
            "halo", "hai", "hi", "hello",
            "pagi", "siang", "malam"
        ]
    ):
        return "greeting"

    if any(
        w in t
        for w in [
            "gila", "buset", "anjay",
            "waduh", "wow", "wih", "wah"
        ]
    ):
        return "reaction"

    if any(
        w in t
        for w in [
            "mantap", "keren", "bagus",
            "gokil", "gas", "semangat",
            "support", "dukung"
        ]
    ):
        return "support"

    return "generic"


def template_reply(user, text):
    category = template_category(text)

    choices = CHAT_TEMPLATES.get(category)

    if not choices:
        choices = CHAT_TEMPLATES.get("generic", [])

    name = str(user or "bro").strip().split()[0][:12]

    if not choices:
        return f"Gas {name}, lanjut nonton!"

    reply = random.choice(choices)

    reply = reply.replace("{name}", name)
    reply = re.sub(r"\s+", " ", reply).strip()

    return reply[:180]


load_chat_templates()


# =========================================================
# PYTCHAT
# =========================================================

def create_chat_with_retry(
    video_id,
    max_retries=10,
    delay=6
):

    for attempt in range(
        1,
        max_retries + 1
    ):

        try:

            print(
                f"[CHAT] Mencoba koneksi pytchat... "
                f"({attempt}/{max_retries})"
            )

            chat = pytchat.create(
                video_id=video_id,
                interruptable=False
            )

            if chat.is_alive():

                print(
                    f"[CHAT] Koneksi berhasil "
                    f"pada percobaan {attempt}"
                )

                return chat

            try:
                chat.terminate()
            except Exception:
                pass

        except Exception as e:

            print(
                f"[CHAT] Gagal percobaan "
                f"{attempt}: {e}"
            )

        if attempt < max_retries:

            print(
                f"[CHAT] Tunggu {delay} detik..."
            )

            time.sleep(delay)

    return None


# =========================================================
# MAIN BOT
# =========================================================

def start_bot():

    global VIDEO_ID

    print("====================================")
    print(
        " LUNA CHAT + COMMENTATOR ONLINE"
    )
    print(" Template Chat + Piper TTS")
    print("====================================")

    if VIDEO_ID:

        print(
            f"[MANUAL] Menggunakan "
            f"YOUTUBE_LIVE_ID: {VIDEO_ID}"
        )

    else:

        print(
            "[AUTO] Mencari live aktif..."
        )

        for attempt in range(
            1,
            16
        ):

            print(
                f"[AUTO] Percobaan {attempt}/15..."
            )

            found_id = find_live_video_id()

            if found_id:

                VIDEO_ID = found_id

                break

            time.sleep(5)

        if not VIDEO_ID:

            print(
                "ERROR: Tidak menemukan "
                "live stream aktif."
            )

            return

    print(
        f"[BOT] Live ID: {VIDEO_ID}"
    )

    print(
        f"[BOT] Max aktif: {MAX_PLAYERS}"
    )

    print("====================================")

    state = load_state()

    save_state(state)

    # Rotation server lama tetap hidup.
    threading.Thread(
        target=start_rotation_server,
        daemon=True
    ).start()

    print(
        "[CHAT] Menunggu chat siap..."
    )

    time.sleep(8)

    chat = create_chat_with_retry(
        VIDEO_ID,
        max_retries=10,
        delay=6
    )

    if chat is None:

        print(
            "ERROR: Gagal konek ke live chat "
            "setelah banyak percobaan."
        )

        return

    print(
        f"Bot mendengarkan live chat: "
        f"{VIDEO_ID}"
    )

    print(
        "Siap menerima perintah: join"
    )

    print(
        "LUNA siap membalas komentar."
    )

    speak("Luna siap. Ketik join untuk ikut balapan.")

    print("====================================")

    while True:

        try:

            if not chat.is_alive():

                print(
                    "[CHAT] Koneksi terputus. "
                    "Reconnect..."
                )

                time.sleep(5)

                chat = create_chat_with_retry(
                    VIDEO_ID,
                    max_retries=5,
                    delay=5
                )

                if chat is None:

                    print(
                        "[CHAT] Reconnect gagal. "
                        "Bot berhenti."
                    )

                    break

                print(
                    "[CHAT] Reconnect berhasil."
                )

                continue

            for c in chat.get().sync_items():

                user = normalize_user(
                    c.author.name
                )

                raw_msg = str(
                    c.message
                ).strip()

                msg = raw_msg.lower()

                # =========================================
                # JOIN — HARUS DIPROSES SEBELUM AI
                # =========================================

                if (
                    msg == "join"
                    or
                    msg.startswith("join ")
                ):

                    result = add_player(
                        state,
                        user
                    )

                    if result == "active":

                        print(
                            f"[JOIN] {user} -> "
                            f"PEMBALAP AKTIF "
                            f"({len(state['active'])}/"
                            f"{MAX_PLAYERS})"
                        )

                        save_state(state)

                        print(
                            f"[STATE] active: "
                            f"{[p['user'] for p in state['active']]}"
                        )

                        speak(
                            f"Woy {user} masuk lintasan, gas pol!"
                        )

                    elif result == "queue":

                        position = len(
                            state["queue"]
                        )

                        print(
                            f"[QUEUE] {user} -> "
                            f"ANTREAN #{position}"
                        )

                        save_state(state)

                        speak(
                            f"{user} antri dulu ya, bentar lagi gas!"
                        )

                    else:

                        print(
                            f"[IGNORE] {user} "
                            f"sudah terdaftar"
                        )

                    # Jangan kirim JOIN ke LUNA.
                    continue

                # =========================================
                # CHAT → LUNA
                # =========================================

                if raw_msg:

                    now = time.time()

                    last_user_time = (
                        last_chat_response
                        .get(user.lower(), 0)
                    )

                    if (
                        now - last_user_time
                        >= CHAT_COOLDOWN
                    ):

                        # Abaikan chat terlalu panjang
                        if len(raw_msg) <= 180:

                            print(
                                f"[CHAT IN] {user}: {raw_msg}"
                            )

                            category = template_category(raw_msg)

                            reply = template_reply(

                                user,

                                raw_msg

                            )


                            print(

                                f"[LUNA TEMPLATE] category={category} "

                                f"{user}: {raw_msg} -> {reply}"

                            )

                            print(f"[CHAT TEMPLATE] {user}: {raw_msg}")
                            print(f"[TEMPLATE REPLY] {reply}")
                            speak(reply)

                            last_chat_response[
                                user.lower()
                            ] = now

        except Exception as e:

            print(
                f"[CHAT ERROR] {e}"
            )

            time.sleep(2)

        time.sleep(0.25)


if __name__ == "__main__":

    start_bot()
