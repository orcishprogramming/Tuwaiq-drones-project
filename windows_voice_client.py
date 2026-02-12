import os
import json
import queue
import socket
import threading

import sounddevice as sd
from vosk import Model, KaldiRecognizer

print("Drones Tuwaiq project (Windows voice client)")

SAMPLE_RATE = 16000
BLOCK_SIZE = 4096

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "vosk-model-small-en-us-0.15")

WSL_HOST = "172.28.191.207"
WSL_PORT = 9999


def send_cmd(cmd: str) -> str:
    """Send one command to the WSL drone server and return its response."""
    try:
        with socket.create_connection((WSL_HOST, WSL_PORT), timeout=2) as s:
            s.sendall((cmd.strip() + "\n").encode("utf-8"))
            return s.recv(1024).decode("utf-8", errors="ignore").strip()
    except Exception as e:
        return f"ERR cannot reach WSL server: {e}"


def main():
    if not os.path.isdir(MODEL_PATH):
        raise FileNotFoundError(f"Model folder not found: {MODEL_PATH}")

    print("Loading Vosk model from:", MODEL_PATH)
    model = Model(MODEL_PATH)
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)

    audio_q = queue.Queue()

    def audio_callback(indata, frames, time, status):
        if status:
            print("Audio status:", status)
        audio_q.put(bytes(indata))

    def worker():
        print("🎤 Voice ready. Say: takeoff / mission / land / stop")
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            channels=1,
            dtype="int16",
            callback=audio_callback,
        ):
            while True:
                data = audio_q.get()
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").strip().lower()
                    if not text:
                        continue

                    print("Heard:", text)

                    # Map speech -> command
                    if "takeoff" in text or "take off" in text:
                        print(send_cmd("takeoff"))

                    elif "mission" in text:
                        print(send_cmd("mission"))

                    elif "land" in text:
                        print(send_cmd("land"))

                    elif "stop" in text:
                        print(send_cmd("stop"))
                        break

    t = threading.Thread(target=worker, daemon=False)
    t.start()
    t.join()


if __name__ == "__main__":
    main()