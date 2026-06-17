import os
import time
import threading
import subprocess
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = 8000


# --------- SERVEUR WEB (rapide + multi-clients) ----------
def run_server():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    handler = SimpleHTTPRequestHandler
    handler.log_message = lambda *args: None  # désactive logs (plus léger)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), handler)

    print(f"[WEB] Serveur lancé sur http://0.0.0.0:{PORT}")
    server.serve_forever()


# --------- UPDATE ----------
def run_update():
    print("[UPDATE] Lancement de update.py...")
    try:
        subprocess.run(["python", "update.py"], check=True)
        print("[UPDATE] Terminé")
    except subprocess.CalledProcessError as e:
        print("[UPDATE] ERREUR:", e)


# --------- SCHEDULER (tous les jours à minuit) ----------
def scheduler_daily():
    while True:
        now = datetime.now()

        next_run = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        wait_seconds = (next_run - now).total_seconds()

        print(f"[SCHEDULER] Prochaine update dans {int(wait_seconds)} secondes")

        time.sleep(wait_seconds)

        run_update()


# --------- MAIN ----------
if __name__ == "__main__":
    t1 = threading.Thread(target=run_server, daemon=True)
    t1.start()

    t2 = threading.Thread(target=scheduler_daily, daemon=True)
    t2.start()

    print("[MAIN] Serveur + scheduler actifs")

    while True:
        time.sleep(3600)
