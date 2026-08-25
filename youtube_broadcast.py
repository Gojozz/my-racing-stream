import os
import sys
from datetime import datetime, timezone

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/youtube"
]


def get_credentials():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()

    if not client_id or not client_secret or not refresh_token:
        raise RuntimeError(
            "OAuth YouTube belum lengkap."
        )

    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )


def find_stream_by_key(youtube, stream_key):
    streams = youtube.liveStreams().list(
        part="id,snippet,cdn,status",
        mine=True,
        maxResults=50,
    ).execute()

    items = streams.get("items", [])
    if not items:
        raise RuntimeError("Tidak ditemukan Live Stream YouTube.")

    for item in items:
        cdn = item.get("cdn", {})
        ingestion = cdn.get("ingestionInfo", {})
        stream_name = ingestion.get("streamName", "")
        if stream_name == stream_key:
            return item

    raise RuntimeError(
        f"Stream key tidak cocok dengan stream YouTube mana pun: {stream_key[:8]}..."
    )


def create_and_bind_broadcast(youtube, title, description, stream_key, label):
    print(f"[YOUTUBE] [{label}] Membuat broadcast baru...")

    broadcast = youtube.liveBroadcasts().insert(
        part="snippet,contentDetails,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "scheduledStartTime": datetime.now(timezone.utc).isoformat(),
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": True,
                "enableDvr": True,
            },
        },
    ).execute()

    broadcast_id = broadcast["id"]
    print(f"[YOUTUBE] [{label}] Broadcast ID: {broadcast_id}")

    print(f"[YOUTUBE] [{label}] Mencari live stream...")
    stream = find_stream_by_key(youtube, stream_key)
    stream_id = stream["id"]
    stream_status = stream.get("status", {}).get("streamStatus", "unknown")

    print(f"[YOUTUBE] [{label}] Stream ID yang cocok: {stream_id}")
    print(f"[YOUTUBE] [{label}] Stream status sebelum FFmpeg: {stream_status}")

    print(f"[YOUTUBE] [{label}] Menghubungkan broadcast ke stream yang tepat...")
    bound = youtube.liveBroadcasts().bind(
        part="id,contentDetails,status",
        id=broadcast_id,
        streamId=stream_id,
    ).execute()

    bound_stream_id = bound.get("contentDetails", {}).get("boundStreamId", "")
    lifecycle = bound.get("status", {}).get("lifeCycleStatus", "unknown")

    if bound_stream_id != stream_id:
        raise RuntimeError(
            f"[{label}] Bind gagal: boundStreamId={bound_stream_id}, expected={stream_id}"
        )

    print(f"[YOUTUBE] [{label}] Bound Stream ID: {bound_stream_id}")
    print(f"[YOUTUBE] [{label}] Lifecycle: {lifecycle}")

    return broadcast_id, stream_id


DESCRIPTION = """🏁 AI RACING BATTLE — LIVE!

This is not just a racing stream — YOU can join the race and control your own car! 🏎️💨

Race against AI drivers, fight for position, use Nitro, stop, start, and try to reach the finish line first!

🎮 HOW TO JOIN THE RACE

Want to play?

Type:

JOIN

in the live chat to enter the race.

🚗 RACING COMMANDS

JOIN
→ Join the current race.

N
→ Activate Nitro and boost your car! ⚡

S
→ Stop your car.

G
→ Start your car again and continue racing.

🏆 YOUR GOAL

Join the race, control your car, battle against AI drivers and other players, use your Nitro at the right moment, and fight for the podium!

🔥 THIS IS INTERACTIVE RACING

You're not just watching the race.

YOU ARE PART OF THE RACE.

Your commands control your car during the live stream.

🏁 CAN YOU BEAT THE AI?

Join the chat.
Enter the race.
Take control.
Use your Nitro.
Fight for the win.

🔔 SUBSCRIBE & TURN ON NOTIFICATIONS

Don't miss the next race and your chance to get on the track!

#AIRacing #InteractiveRacing #SimRacing #RacingGame #LiveRacing #AIRacingBattle #PlayWithViewers"""


def create_broadcasts():
    youtube = build(
        "youtube",
        "v3",
        credentials=get_credentials(),
    )

    landscape_key = os.environ.get("YOUTUBE_STREAM_KEY", "").strip()
    vertical_key = os.environ.get("YOUTUBE_VERTICAL_STREAM_KEY", "").strip()

    if not landscape_key:
        raise RuntimeError("YOUTUBE_STREAM_KEY belum tersedia.")

    landscape_title = "🏁 AI Racing Battle LIVE | JOIN & DRIVE Your Own Car! 🚗💨"
    land_broadcast_id, land_stream_id = create_and_bind_broadcast(
        youtube,
        landscape_title,
        DESCRIPTION,
        landscape_key,
        "LANDSCAPE",
    )

    print("========================================")
    print("YOUTUBE LANDSCAPE BROADCAST SIAP")
    print(f"VIDEO_ID={land_broadcast_id}")
    print(f"STREAM_ID={land_stream_id}")
    print("AUTO START=TRUE")
    print("AUTO STOP=TRUE")
    print("========================================")
    print(land_broadcast_id)

    if vertical_key:
        vertical_title = "🏁 AI Racing Battle VERTICAL | JOIN & DRIVE! 🚗💨"
        vert_broadcast_id, vert_stream_id = create_and_bind_broadcast(
            youtube,
            vertical_title,
            DESCRIPTION,
            vertical_key,
            "VERTICAL",
        )

        print("========================================")
        print("YOUTUBE VERTICAL BROADCAST SIAP")
        print(f"VERTICAL_VIDEO_ID={vert_broadcast_id}")
        print(f"VERTICAL_STREAM_ID={vert_stream_id}")
        print("AUTO START=TRUE")
        print("AUTO STOP=TRUE")
        print("========================================")
    else:
        print("[YOUTUBE] YOUTUBE_VERTICAL_STREAM_KEY tidak ada — skip vertical broadcast.")


if __name__ == "__main__":
    try:
        create_broadcasts()
    except Exception as e:
        print(f"[YOUTUBE BROADCAST ERROR] {e}")
        sys.exit(1)
