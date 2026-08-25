import os
import sys

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

    print("[YOUTUBE] Membuat broadcast baru...")

    broadcast = youtube.liveBroadcasts().insert(
        part="snippet,contentDetails,status",
        body={
            "snippet": {
                "title": "AI Racing Live",
                "description": "AI Racing Live Stream",
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

        if stream_name:
            stream = item
            break

    if stream is None:
        raise RuntimeError(
            "Tidak ditemukan stream yang memiliki stream key."
        )

    stream_id = stream["id"]

    print(f"[YOUTUBE] Stream ID: {stream_id}")

    print("[YOUTUBE] Menghubungkan broadcast ke stream...")

    youtube.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream_id,
    ).execute()

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
