import pytchat
import time
import os

VIDEO_ID = os.environ.get("YOUTUBE_LIVE_ID", "MASUKKAN_VIDEO_ID_DISINI")

def start_bot():
    chat = pytchat.create(video_id=VIDEO_ID)
    print(f"Bot mendengarkan live chat ID: {VIDEO_ID}")

    while chat.is_alive():
        for c in chat.get().sync_items():
            user = c.author.name
            msg = c.message.lower().strip()

            if "join" in msg:
                print(f"[JOIN] {user} masuk ke balapan!")

        time.sleep(1)

if __name__ == "__main__":
    start_bot()
