
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
from groq import Groq

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
# LUNA AI — Groq openai/gpt-oss-20b
# =========================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
DEEPSEEK_API_KEY = GROQ_API_KEY

DEEPSEEK_BASE_URL = os.environ.get(
    "DEEPSEEK_BASE_URL",
    "https://api.groq.com/openai/v1"
).rstrip("/")

DEEPSEEK_MODEL = os.environ.get(
    "DEEPSEEK_MODEL",
    "qwen/qwen3.6-27b"
)

# Prioritas: GROQ_MODEL > DEEPSEEK_MODEL
GROQ_MODEL = os.environ.get("GROQ_MODEL", "").strip() or "qwen/qwen3.6-27b"

AI_PROVIDER = "groq"
AI_API_KEY = GROQ_API_KEY
AI_BASE_URL = DEEPSEEK_BASE_URL
AI_MODEL = GROQ_MODEL
ai_ready = bool(GROQ_API_KEY)

if ai_ready:
    print("[LUNA] Groq siap. Model:", AI_MODEL)
    print("[LUNA] Endpoint:", AI_BASE_URL)
else:
    print("[LUNA] GROQ_API_KEY kosong — pakai template saja.")

groq_client = None



LUNA_SYSTEM_PROMPT = """
Kamu LUNA, komentator balap live yang kocak, cerewet, dan overreact.
Bahasa: Indonesia gaul keninian, kayak temen nonton bareng di chat.
Boleh pakai: anjay, gas, gila, buset, mantap, waduh, auto, kepleset, ngebut, santuy, gokil, parah, beneran, wkwk (jangan kasar berat / SARA / penghinaan).
Gaya: guyon, nyambung, energik, jangan kaku, jangan formal, jangan seperti robot.
Aturan ketat:
- Bahasa Indonesia gaul
- Maksimal 1 kalimat, maksimal 14 kata
- Kalau balas chat: sebut nama singkat, langsung lucu
- Jangan bilang kamu AI/bot/model
- Jangan menghina penonton
- Jangan jelasin panjang, jangan thinking
- Langsung jawaban final saja
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

CHAT_COOLDOWN = 2.0

last_chat_response = {}

# Untuk pilih chat random saat rame
recent_chat_times = []
CHAT_BUSY_WINDOW = 20.0   # detik
CHAT_BUSY_THRESHOLD = 6   # jumlah chat dalam window = rame
CHAT_REPLY_CHANCE_BUSY = 0.28
CHAT_REPLY_CHANCE_NORMAL = 0.75

# =========================================================
# LUNA SMART FILTER + QUEUE + PRIORITY
# =========================================================
LUNA_GAP_MIN = 2.0
LUNA_GAP_MAX = 3.5
last_luna_speak_at = 0.0
chat_priority_queue = []
CHAT_QUEUE_MAX = 40
last_seen_msgs = {}
TOPIC_BUCKETS = {}

SIMPLE_CHAT_RE = re.compile(
    r"^(hai|halo|hi|hello|wkwk+|wk+|lol|haha+|gas+|mantap+|ok|oke|sip|gg|ez|nice|bang|bro|kak)+[\s!.,]*$",
    re.I,
)
EMOJI_ONLY_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)
LUNA_MENTION_RE = re.compile(r"\b(luna|lunaa)\b", re.I)
RACE_Q_RE = re.compile(
    r"(siapa\s+(yang\s+)?(menang|juara|depan|p1)|posisi|klasemen|overtake|nyalip|finish|balapan|mobil|lap\b)",
    re.I,
)
QUESTION_RE = re.compile(r"\?|^(apa|siapa|kenapa|kok|gimana|bagaimana|kapan|dimana|berapa)\b", re.I)


def normalize_chat(text):
    t = str(text or "").lower().strip()
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"@\w+", "", t)
    t = re.sub(r"(.)\1{2,}", r"\1\1", t)
    t = re.sub(r"[^\w\s\?]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_spam_or_dup(user, text):
    global last_seen_msgs
    now = time.time()
    for k in list(last_seen_msgs.keys()):
        if now - last_seen_msgs[k] > 20:
            del last_seen_msgs[k]
    norm = normalize_chat(text)
    if not norm or len(norm) < 2:
        return True
    if len(re.sub(r"\W", "", text, flags=re.UNICODE)) == 0:
        return True
    key = norm
    ukey = user.lower() + "|" + norm
    if key in last_seen_msgs and (now - last_seen_msgs[key]) < 8:
        return True
    if ukey in last_seen_msgs and (now - last_seen_msgs[ukey]) < 12:
        return True
    last_seen_msgs[key] = now
    last_seen_msgs[ukey] = now
    return False


def topic_key(text):
    norm = normalize_chat(text)
    words = [w for w in norm.split() if len(w) > 2][:4]
    return " ".join(words) if words else norm[:24]


def score_chat(user, text):
    t = text.strip()
    norm = normalize_chat(t)
    score = 0
    if LUNA_MENTION_RE.search(t):
        score += 50
    if QUESTION_RE.search(t) or "?" in t:
        score += 35
    if RACE_Q_RE.search(t):
        score += 40
    if SIMPLE_CHAT_RE.match(norm):
        score -= 30
    if 8 <= len(norm) <= 120:
        score += 10
    if len(norm) > 160:
        score -= 20
    return score


def needs_ai(text, score):
    if score >= 15:
        return True
    if LUNA_MENTION_RE.search(text):
        return True
    if QUESTION_RE.search(text) or "?" in text:
        return True
    if RACE_Q_RE.search(text):
        return True
    if score >= 5 and random.random() < 0.35:
        return True
    return False


def simple_template_reply(user, text):
    name = str(user).split()[0][:12]
    norm = normalize_chat(text)
    if SIMPLE_CHAT_RE.match(norm):
        return random.choice([
            f"Gas {name}, tetap di sini ya!",
            f"Halo {name}, balapan lagi panas!",
            f"Siap {name}, nonton bareng yuk!",
        ])
    return random.choice([
        f"Mantap {name}, komentarnya nyampe!",
        f"Oke {name}, Luna catat!",
        f"Gas terus {name}!",
    ])


def enqueue_chat(user, text):
    global chat_priority_queue, TOPIC_BUCKETS
    now = time.time()
    for k in list(TOPIC_BUCKETS.keys()):
        if now - TOPIC_BUCKETS[k]["ts"] > 60:
            del TOPIC_BUCKETS[k]
    sc = score_chat(user, text)
    tk = topic_key(text)
    if tk in TOPIC_BUCKETS:
        b = TOPIC_BUCKETS[tk]
        b["count"] += 1
        b["score"] = min(100, max(b["score"], sc) + 3)
        b["ts"] = now
        return
    TOPIC_BUCKETS[tk] = {
        "count": 1,
        "sample_user": user,
        "sample_text": text.strip()[:180],
        "score": sc,
        "ts": now,
    }
    chat_priority_queue.append({
        "user": user,
        "text": text.strip()[:180],
        "score": sc,
        "ts": now,
        "topic": tk,
    })
    chat_priority_queue.sort(key=lambda x: (-x["score"], x["ts"]))
    if len(chat_priority_queue) > CHAT_QUEUE_MAX:
        chat_priority_queue[:] = chat_priority_queue[:CHAT_QUEUE_MAX]


def pop_best_chat():
    global chat_priority_queue
    if not chat_priority_queue:
        return None
    chat_priority_queue.sort(key=lambda x: (-x["score"], x["ts"]))
    return chat_priority_queue.pop(0)


def luna_can_speak():
    return (time.time() - last_luna_speak_at) >= LUNA_GAP_MIN


def mark_luna_spoke():
    global last_luna_speak_at
    last_luna_speak_at = time.time() + random.uniform(0, LUNA_GAP_MAX - LUNA_GAP_MIN)


def process_chat_queue_once(race_state_hint=""):
    if not luna_can_speak():
        return
    item = pop_best_chat()
    if not item:
        return
    user = item["user"]
    msg = item["text"]
    sc = item["score"]
    meta = TOPIC_BUCKETS.get(item.get("topic"), {})
    count = int(meta.get("count", 1))
    if not needs_ai(msg, sc):
        reply = simple_template_reply(user, msg)
        print(f"[LUNA TEMPLATE] {user}: {msg} -> {reply}")
        speak(reply)
        mark_luna_spoke()
        return
    context_line = race_state_hint.strip() or "Balapan sedang berlangsung."
    prompt_msg = f"(x{count} penonton sejenis) {msg}" if count > 1 else msg
    reply = ask_luna(user, f"[{context_line}] {prompt_msg}", "chat")
    if not reply:
        reply = simple_template_reply(user, msg)
        print("[LUNA] AI gagal, fallback template")
    print(f"[LUNA AI] score={sc} {user}: {msg} -> {reply}")
    speak(reply)
    mark_luna_spoke()



ENGAGEMENT_INTERVAL = 240

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

        sink = env.get("PULSE_SINK", "stream_sink")
        # Selalu pakai device eksplisit biar masuk ke stream_sink.monitor
        result = subprocess.run(
            ["paplay", f"--device={sink}", str(wav_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
            env=env
        )

        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")[-1000:]
            print("[PAPLAY ERROR]", err)
            # Fallback tanpa device
            result2 = subprocess.run(
                ["paplay", str(wav_path)],
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


def ask_luna(user_name, message, context="chat"):
    if not ai_ready:
        print("[LUNA ERROR] AI lokal tidak siap")
        return None
    try:
        if context == "chat":
            prompt = (
                "Penonton " + str(user_name) + " bilang: " + str(message) + ". "
                "Balas kocak pakai bahasa gaul keninian (boleh anjay/gas/buset). "
                "Maksimal 14 kata, 1 kalimat."
            )
        elif context == "commentary":
            prompt = (
                "Kasih 1 kalimat komentar balap singkat, maksimal 14 kata."
            )
        else:
            prompt = str(message)

        print("[LUNA] panggil", AI_PROVIDER, "model=" + str(AI_MODEL))

        payload = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": LUNA_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "max_tokens": 80,
            "reasoning_effort": "none",
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                AI_BASE_URL + "/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {AI_API_KEY}",
                },
                json=payload,
            )
        if resp.status_code >= 400:
            print("[LUNA ERROR] HTTP", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        msg_obj = data["choices"][0]["message"]
        raw = msg_obj.get("content")
        if not raw or not str(raw).strip():
            raw = msg_obj.get("reasoning") or msg_obj.get("reasoning_content")
        if (not raw or not str(raw).strip()) and isinstance(msg_obj, dict):
            raw = msg_obj.get("text")
        print("[LUNA RAW] " + repr(raw)[:500])
        if not raw or not str(raw).strip():
            print("[LUNA ERROR] response content kosong")
            return None
        text_out = clean_tts_text(strip_model_thinking(str(raw)))
        text_out = " ".join(text_out.split())
        words = text_out.split()
        if len(words) > 14:
            text_out = " ".join(words[:14])
        if len(text_out) > 160:
            text_out = text_out[:160].rsplit(" ", 1)[0]
        if not text_out:
            print("[LUNA ERROR] text kosong setelah clean")
            return None
        print("[LUNA CLEAN] " + text_out)
        return text_out
    except Exception as e:
        print("[LUNA ERROR] " + type(e).__name__ + ": " + str(e))
        return None



LIKE_PROMOS = [
    "Kalau balapannya seru, bantu Luna tekan laik, subs kreb, dan share ya!",
    "Suka balapannya? Gas laik, subs kreb, lalu share ke teman kalian!",
    "Jangan pelit laik! Subs kreb juga, terus share biar makin ramai!",
    "Bantu bikin lintasan ini makin ramai, laik, subs kreb, dan share!",
    "Kalau deg-degannya terasa, traktir Luna satu laik dan jangan lupa subs kreb!"
]


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

            # Jangan saingi balasan chat (prioritas Luna chat)
            if time.time() - last_luna_speak_at < 12:
                print("[ENGAGEMENT] skip — Luna baru bicara")
                continue

            text = pick_engagement_line()

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
    u = str(user).strip()
    if u.startswith("@"):
        u = u[1:]
    return u


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



def commentate_race(event, detail=""):
    """Komentar singkat untuk event balapan."""
    event = str(event or "").lower().strip()
    detail = str(detail or "").strip()

    # Template cadangan kalau Groq gagal
    fallbacks = {
        "start": [
            "Gas! Lampu hijau, semuanya ngebut dari start!",
            "Start brutal, roda langsung mengamuk!",
        ],
        "overtake": [
            f"Woy ada nyalip! {detail} menyerobot tikungan!" if detail else "Ada aksi nyalip gila di tikungan!",
            f"Buset, {detail} nyalip dingin aja!" if detail else "Nyalip dingin, penonton pada stand up!",
        ],
        "finish": [
            f"Finish! {detail} menyeberang garis akhir!" if detail else "Ada yang finish dulu, gila pol!",
            f"Auto finish buat {detail}, mantap jiwa!" if detail else "Garis finish dilindas, balapan mengeras!",
        ],
        "winner": [
            f"Juara! {detail} menguasai lintasan hari ini!" if detail else "Juara hari ini sudah lahir!",
        ],
    }

    prompt_map = {
        "start": "Balapan baru start. Komentari start-nya singkat dan seru.",
        "overtake": f"Ada aksi nyalip. Detail: {detail or 'pembalap di tikungan'}. Komentari singkat.",
        "finish": f"Ada pembalap finish. Detail: {detail or 'seseorang'}. Komentari singkat.",
        "winner": f"Pemenang balapan: {detail or 'juara'}. Rayakan singkat.",
    }

    # 30% chance pakai AI untuk event balapan
    use_ai = False  # race = template only, hemat + tidak kosong
    reply = None
    if use_ai:
        prompt = prompt_map.get(event, f"Event balapan: {event}. {detail}")
        reply = ask_luna("LINTASAN", prompt, "race")
    if not reply:
        pool = fallbacks.get(event, ["Balapan makin seru, gas terus!"])
        # event mid-race generik
        if event in ("mid", "pulse", "action"):
            pool = [
                f"{detail} masih ngegas di depan!" if detail else "Paketan masih ketat, gas terus!",
                f"Woy {detail} jaga jarak!" if detail else "Tikungan basah, jangan kepleset!",
                "Buset, lintasan panas banget sekarang!",
                "Siapa yang bakal nyalip duluan? Deg-degan!",
                f"Auto fokus ke {detail}, roda masih putar gila!" if detail else "Roda masih putar gila di lintasan!",
            ]
        reply = random.choice(pool)

    print(f"[LUNA RACE] event={event} ai={use_ai} detail={detail} -> {reply}")
    speak(reply)
    return reply


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

        if self.path not in ("/race-result", "/race-event"):

            self.send_response(404)

            self.send_cors_headers()

            self.end_headers()

            return

        # Event komentator: start / overtake / finish / winner
        if self.path == "/race-event":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                data = json.loads(body.decode("utf-8") or "{}")
                event = str(data.get("event", "")).strip()
                detail = str(data.get("detail", "")).strip()
                if event:
                    commentate_race(event, detail)
                self.send_response(200)
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b"ok")
            except Exception as e:
                print(f"[RACE-EVENT ERROR] {e}")
                self.send_response(500)
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

                # Komentator saat ada yang keluar / finish last
                try:
                    commentate_race("finish", eliminated)
                except Exception as e:
                    print(f"[LUNA RACE ERROR] {e}")

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


def fetch_chat_items(chat):
    """Kompatibel pytchat: get() bisa object ATAU list."""
    try:
        raw = chat.get()
    except Exception as e:
        print(f"[CHAT] get() error: {e}")
        return None
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if hasattr(raw, "sync_items"):
        try:
            return raw.sync_items() or []
        except Exception as e:
            print(f"[CHAT] sync_items error: {e}")
            return None
    return []



def drain_chat_buffer(chat, rounds=8, pause=0.35):
    """Buang histori/buffer pytchat tanpa join/AI."""
    dumped = 0
    for _ in range(rounds):
        try:
            raw = chat.get()
            if raw is None:
                items = []
            elif isinstance(raw, list):
                items = raw
            elif hasattr(raw, "sync_items"):
                items = raw.sync_items() or []
            else:
                items = list(raw) if raw else []
            dumped += len(items or [])
        except Exception:
            pass
        time.sleep(pause)
    print(f"[CHAT] Buffer histori dibuang: {dumped} pesan")
    return dumped


def start_bot():

    global VIDEO_ID

    print("====================================")
    print(
        " LUNA CHAT + COMMENTATOR ONLINE"
    )
    print(" Groq + Piper TTS")
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

            found_id = get_live_video_id()

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

    # Reset slot pembalap tiap start stream
    # biar nama lama (mis. tanidong) tidak nempel tanpa join
    state = {
        "active": [],
        "queue": [],
        "lastUpdate": 0
    }
    save_state(state)
    print("[JOIN] Slot dikosongkan. Tunggu penonton ketik join.")

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

    # Buang histori live sebelumnya / buffer awal pytchat
    drain_chat_buffer(chat, rounds=10, pause=0.3)

    speak("Luna siap. Ketik join untuk ikut balapan.")
    chat_listen_after = time.time()

    print("====================================")

    # ===== Chat loop gaya syc (sederhana + stabil) =====
    # ===== Chat loop gaya syc (sederhana + get aman) =====
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
                drain_chat_buffer(chat, rounds=6, pause=0.25)
                continue

            items = fetch_chat_items(chat)
            if items is None:
                time.sleep(2)
                continue

            for c in items:

                user = normalize_user(
                    c.author.name
                )

                raw_msg = str(
                    c.message
                ).strip()

                msg = raw_msg.lower().strip()

                # =========================================
                # JOIN — sama seperti syc
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

                    continue

                # =========================================
                # CHAT → LUNA (alur syc)
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

                        if len(raw_msg) <= 180:

                            print(
                                f"[CHAT IN] {user}: {raw_msg}"
                            )

                            reply = None

                            try:
                                if ai_ready:
                                    reply = ask_luna(
                                        user,
                                        raw_msg,
                                        "chat"
                                    )
                            except NameError:
                                reply = ask_luna(
                                    user,
                                    raw_msg,
                                    "chat"
                                )

                            if not reply:
                                reply = random.choice([
                                    f"Woy {user}, gas terus komentarnya!",
                                    f"{user} nyolot di komentar, LUNA denger nih!",
                                    f"Mantap {user}, komentarnya nambah seru!",
                                    f"Siap {user}, LUNA catat di kepala!",
                                    f"Kocak {user}, jangan berhenti komen!",
                                ])
                                print("[LUNA] fallback template")

                            print(f"[LUNA CHAT] {user}: {raw_msg}")
                            print(f"[LUNA] {reply}")
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
