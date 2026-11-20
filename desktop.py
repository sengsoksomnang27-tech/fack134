"""Desktop launcher for SENG SOKSOMNANG (Windows)."""
import threading
import time
import urllib.request
import webview
from app import app

URL = 'http://127.0.0.1:5055'

def serve():
    from werkzeug.serving import make_server
    server = make_server('127.0.0.1', 5055, app, threaded=True)
    server.serve_forever()

def main():
    threading.Thread(target=serve, daemon=True).start()
    for _ in range(80):
        try:
            with urllib.request.urlopen(URL + '/api/status', timeout=0.5) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError('Could not start local server on port 5055. Close another app using that port.')
    webview.create_window('SENG SOKSOMNANG | Media Downloader', URL, width=1100, height=760, min_size=(780, 550), background_color='#020613')
    webview.start(debug=False)

if __name__ == '__main__':
    main()
