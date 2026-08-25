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


def create_broadcast():
    youtube = build(
        "youtube",
        "v3",
        credentials=get_credentials(),
    )

    configured_stream_key = os.environ.get("YOUTUBE_STREAM_KEY", "").strip()

    if not configured_stream_key:
        raise RuntimeError(
            "YOUTUBE_STREAM_KEY belum tersedia."
        )

    print("[YOUTUBE] Membuat broadcast baru...")

    broadcast = youtube.liveBroadcasts().insert(
        part="snippet,contentDetails,status",
        body={
            "snippet": {
                "title": "🏁 AI Racing Battle LIVE | JOIN & DRIVE Your Own Car! 🚗💨",
                "description": """🏁 AI RACING BATTLE — LIVE!

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

#AIRacing #InteractiveRacing #SimRacing #RacingGame #LiveRacing #AIRacingBattle #PlayWithViewers""",
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

    print(f"[YOUTUBE] Broadcast ID: {broadcast_id}")

    print("[YOUTUBE] Mencari live stream...")

    streams = youtube.liveStreams().list(
        part="id,snippet,cdn,status",
        mine=True,
        maxResults=50,
    ).execute()

    items = streams.get("items", [])

    if not items:
        raise RuntimeError(
            "Tidak ditemukan Live Stream YouTube."
        )

    stream = None

    for item in items:
        cdn = item.get("cdn", {})
        ingestion = cdn.get("ingestionInfo", {})
        stream_name = ingestion.get("streamName", "")

        if stream_name == configured_stream_key:
            stream = item
            break

    if stream is None:
        raise RuntimeError(
            "YOUTUBE_STREAM_KEY tidak cocok dengan stream YouTube mana pun."
        )

    stream_id = stream["id"]
    stream_status = stream.get("status", {}).get(
        "streamStatus", "unknown"
    )

    print(f"[YOUTUBE] Stream ID yang cocok: {stream_id}")
    print(f"[YOUTUBE] Stream status sebelum FFmpeg: {stream_status}")

    print("[YOUTUBE] Menghubungkan broadcast ke stream yang tepat...")

    bound = youtube.liveBroadcasts().bind(
        part="id,contentDetails,status",
        id=broadcast_id,
        streamId=stream_id,
    ).execute()

    bound_stream_id = bound.get(
        "contentDetails", {}
    ).get("boundStreamId", "")

    lifecycle = bound.get(
        "status", {}
    ).get("lifeCycleStatus", "unknown")

    if bound_stream_id != stream_id:
        raise RuntimeError(
            f"Bind gagal: boundStreamId={bound_stream_id}, expected={stream_id}"
        )

    print(f"[YOUTUBE] Bound Stream ID: {bound_stream_id}")
    print(f"[YOUTUBE] Lifecycle: {lifecycle}")

    print("========================================")
    print("YOUTUBE BROADCAST SIAP")
    print(f"VIDEO_ID={broadcast_id}")
    print(f"STREAM_ID={stream_id}")
    print("AUTO START=TRUE")
    print("AUTO STOP=TRUE")
    print("========================================")

    print(broadcast_id)


if __name__ == "__main__":
    try:
        create_broadcast()
    except Exception as e:
        print(f"[YOUTUBE BROADCAST ERROR] {e}")
        sys.exit(1)
