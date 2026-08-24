from pathlib import Path

p = Path("bot.py")
s = p.read_text(encoding="utf-8")

old = '''def template_reply(user, text):
    category = template_category(text)

    choices = CHAT_TEMPLATES.get(category)

    if not choices:
        choices = CHAT_TEMPLATES.get("generic", [])

    name = str(user or "bro").strip().split()[0][:12]

    if not choices:
        return f"Gas {name}, lanjut nonton!"

    reply = random.choice(choices)

    reply = reply.replace("{name}", name)
    reply = re.sub(r"\\s+", " ", reply).strip()

    return reply[:180]
'''

new = '''# =========================================================
# COMBINATORIAL CHAT ENGINE — TANPA AI
# =========================================================

COMBO_PARTS = {
    "greeting": {
        "open": [
            "Yo", "Woy", "Halo", "Hai", "Nah", "Akhirnya nongol"
        ],
        "middle": [
            "balapannya lagi panas",
            "lintasan lagi rame",
            "kita gas nonton",
            "aksi lagi brutal",
            "suasana makin pecah"
        ],
        "end": [
            "gas terus!",
            "jangan kedip!",
            "pantengin sampai finish!",
            "siap-siap kaget!",
            "mantul!"
        ],
    },

    "reaction": {
        "open": [
            "Waduh", "Buset", "Gila", "Anjay", "Wih", "Edan", "Njir"
        ],
        "middle": [
            "itu manuvernya brutal",
            "duelnya makin panas",
            "mobilnya makin ngaco",
            "tadi nyaris tabrakan",
            "posisinya berubah terus",
            "aksi depannya gak santai"
        ],
        "end": [
            "jangan kedip!",
            "gokil sih!",
            "auto tegang!",
            "parah banget!",
            "ini baru racing!"
        ],
    },

    "racing": {
        "open": [
            "Gas", "Woy", "Nah", "Gila", "Buset", "Mantap"
        ],
        "middle": [
            "duel depan makin panas",
            "overtake tadi bersih banget",
            "posisi masih bisa berubah",
            "lap berikutnya bakal brutal",
            "mobil belakang mulai ngancem",
            "jaraknya makin tipis"
        ],
        "end": [
            "jangan kedip!",
            "pantengin terus!",
            "gas sampai finish!",
            "ini belum kelar!",
            "siapa yang bakal P1?"
        ],
    },

    "laugh": {
        "open": [
            "Wkwkwk", "Hahaha", "Wkwk", "Hehe", "Kocak"
        ],
        "middle": [
            "chat lu bikin rame",
            "komentar lu pecah banget",
            "lu bisa aja",
            "suasana makin ngakak",
            "LUNA ikut ketawa"
        ],
        "end": [
            "lanjut terus!",
            "jangan berhenti komen!",
            "gas lagi!",
            "mantap!",
            "wkwkwk!"
        ],
    },

    "support": {
        "open": [
            "Mantap", "Gas", "Nah gitu", "Keren", "Gokil", "Sip"
        ],
        "middle": [
            "support kalian bikin rame",
            "komentarnya makin seru",
            "semangatnya kerasa",
            "live makin hidup",
            "dukungan kalian mantul"
        ],
        "end": [
            "lanjut terus!",
            "jangan pergi!",
            "gas sampai finish!",
            "makasih!",
            "tetap ramaikan!"
        ],
    },

    "join": {
        "open": [
            "Gas", "Woy", "Ayo", "Nah", "Berani?",
            "Siap-siap"
        ],
        "middle": [
            "ketik join kalau mau turun",
            "tinggal ketik join",
            "masuk antrean dulu",
            "lintasan masih terbuka",
            "kesempatan masih ada"
        ],
        "end": [
            "jangan cuma nonton!",
            "gaskeun!",
            "berani gak?",
            "langsung masuk!",
            "siapa takut?"
        ],
    },

    "question": {
        "open": [
            "Siap", "Oke", "Nah", "Tenang", "Santai", "Woy"
        ],
        "middle": [
            "kita pantau terus",
            "sebentar lagi kelihatan",
            "jawabannya bakal kebaca",
            "posisinya masih berubah",
            "kita lihat sampai finish"
        ],
        "end": [
            "tetap pantengin!",
            "jangan kedip!",
            "gas terus!",
            "sabar dulu!",
            "bentar lagi!"
        ],
    },

    "generic": {
        "open": [
            "Gas", "Woy", "Mantap", "Buset", "Nah", "Gokil"
        ],
        "middle": [
            "chat lu bikin rame",
            "suasana makin panas",
            "live makin pecah",
            "balapannya makin seru",
            "lintasan makin brutal"
        ],
        "end": [
            "lanjut terus!",
            "gas lagi!",
            "jangan pergi!",
            "pantengin terus!",
            "mantul!"
        ],
    },
}


def template_reply(user, text):
    category = template_category(text)
    parts = COMBO_PARTS.get(category, COMBO_PARTS["generic"])

    name = str(user or "bro").strip().split()[0][:12]

    # Kombinasi open × middle × end.
    reply = (
        f"{random.choice(parts['open'])} {name}, "
        f"{random.choice(parts['middle'])}, "
        f"{random.choice(parts['end'])}"
    )

    reply = re.sub(r"\\s+", " ", reply).strip()

    return reply[:180]
'''

if old not in s:
    raise SystemExit("Fungsi template_reply lama tidak ditemukan. TIDAK DIUBAH.")

s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")

print("COMBO ENGINE BERHASIL DIPASANG")
