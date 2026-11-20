import os, sys, tempfile, shutil, subprocess, queue, threading, time
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, request, jsonify, render_template
import yt_dlp

# Save to the current Windows user's Downloads folder.
# Example: C:\Users\YourName\Downloads\SENG SOKSOMNANG
BASE_DIR = Path.home() / 'Downloads' / 'SENG SOKSOMNANG' 
PLATFORMS = ('Facebook', 'TikTok', 'YouTube', 'X', 'Instagram')
FOLDERS = {name: BASE_DIR / name.lower() for name in PLATFORMS}
DOMAINS = {
    'Facebook': ('facebook.com', 'fb.watch', 'fb.com'),
    'TikTok': ('tiktok.com',),
    'YouTube': ('youtube.com', 'youtu.be'),
    'X': ('x.com', 'twitter.com'),
    'Instagram': ('instagram.com',),
}
for folder in FOLDERS.values():
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'image').mkdir(parents=True, exist_ok=True)

class QueueLogger:
    def __init__(self, events): self.events = events
    def debug(self, msg):
        if not str(msg).startswith('[debug]'): self.events.put(('log', str(msg)))
    def warning(self, msg): self.events.put(('log', 'WARNING: ' + str(msg)))
    def error(self, msg): self.events.put(('log', 'ERROR: ' + str(msg)))

class DownloadEngine:
    def __init__(self): self.events = queue.Queue()
    def progress_hook(self, data):
            if data.get('status') == 'downloading':
                downloaded = data.get('downloaded_bytes', 0)
                total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
                if total:
                    self.events.put(('progress', min(100, downloaded / total * 100)))
            elif data.get('status') == 'finished':
                self.events.put(('status', 'Processing downloaded video...'))

    def download_media(self, platform, url, mode):
            folder = FOLDERS[platform]
            try:
                self.events.put(('log', f'Mode: {mode} | Videos: {folder} | Images: {folder / "image"}'))
                if mode == 'Video / Reel':
                    files = self.download_video(platform, url, folder)
                elif mode == 'Image / Photo':
                    files = self.download_images(platform, url, folder)
                else:
                    # Gallery-dl handles photo posts and many reels. Try it first
                    # on photo-oriented sites, then fall back to yt-dlp.
                    if platform in ('Instagram', 'X', 'TikTok', 'Facebook'):
                        try:
                            files = self.download_gallery_sorted(url, folder)
                        except Exception as gallery_error:
                            self.events.put(('log', 'Gallery method: ' + str(gallery_error)))
                            files = self.download_video(platform, url, folder)
                    else:
                        files = self.download_video(platform, url, folder)
                if not files:
                    raise RuntimeError('No downloaded media files were found.')
                self.events.put(('success', platform, files, url))
            except Exception as error:
                self.events.put(('error', str(error)))

    def download_video(self, platform, url, folder):
            before = self.snapshot(folder)
            options = {
                'paths': {'home': str(folder)},
                'outtmpl': '%(title).150B [%(id)s].%(ext)s',
                'noplaylist': True,
                'windowsfilenames': True,
                'progress_hooks': [self.progress_hook],
                'logger': QueueLogger(self.events),
                'quiet': True,
                'no_warnings': False,
                'ignoreerrors': False,
                'retries': 5,
                'fragment_retries': 5,
                'extractor_retries': 5,
                'socket_timeout': 30,
                'overwrites': False,
            }
            if platform == 'YouTube':
                options['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                options['merge_output_format'] = 'mp4'
            elif platform in ('TikTok', 'X', 'Instagram'):
                options['format'] = 'best'
            else:
                options['format'] = 'best[ext=mp4]/best'
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise RuntimeError('The site returned no video information.')
                requested = info.get('requested_downloads') or []
                candidates = [Path(item['filepath']) for item in requested if item.get('filepath')]
                expected = Path(ydl.prepare_filename(info))
                candidates.extend([expected, expected.with_suffix('.mp4'), expected.with_suffix('.mkv')])
            found = self.changed_files(folder, before)
            found.extend(str(path) for path in candidates if path.is_file())
            return list(dict.fromkeys(found))

    def download_images(self, platform, url, folder):
            if platform == 'YouTube':
                return self.download_thumbnail(url, folder / 'image')
            files = self.download_gallery_sorted(url, folder)
            images = [p for p in files if Path(p).suffix.lower() in
                      ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif')]
            if not images:
                raise RuntimeError('No downloadable images found for this post. '
                                   'Try Auto or Video / Reel instead.')
            return images

    def download_thumbnail(self, url, folder):
            before = self.snapshot(folder)
            options = {
                'paths': {'home': str(folder)},
                'outtmpl': '%(title).150B [%(id)s].%(ext)s',
                'skip_download': True,
                'writethumbnail': True,
                'noplaylist': True,
                'windowsfilenames': True,
                'logger': QueueLogger(self.events),
                'quiet': True,
            }
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise RuntimeError('Could not retrieve thumbnail.')
            files = self.changed_files(folder, before)
            if not files:
                raise RuntimeError('No new thumbnail saved. It may already exist.')
            return files

    def snapshot(self, folder):
            return {str(p.resolve()): (p.stat().st_size, p.stat().st_mtime_ns)
                    for p in folder.rglob("*") if p.is_file()}

    def changed_files(self, folder, before):
            result = []
            for p in folder.rglob("*"):
                if not p.is_file() or p.suffix.lower() in ('.part', '.ytdl', '.tmp'):
                    continue
                key = str(p.resolve())
                stamp = (p.stat().st_size, p.stat().st_mtime_ns)
                if key not in before or before[key] != stamp:
                    result.append(key)
            return result

    def download_gallery_sorted(self, url, platform_folder):
            """Download to a temporary folder and sort images into image/."""
            image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif', '.bmp'}
            with tempfile.TemporaryDirectory(prefix='seng_media_') as temporary:
                files = self.download_gallery(url, Path(temporary))
                saved = []
                for filename in files:
                    source = Path(filename)
                    if not source.is_file():
                        continue
                    destination_dir = (platform_folder / 'image'
                                       if source.suffix.lower() in image_exts
                                       else platform_folder)
                    destination_dir.mkdir(parents=True, exist_ok=True)
                    destination = destination_dir / source.name
                    # Avoid overwriting existing files with the same name.
                    index = 1
                    while destination.exists():
                        destination = destination_dir / (
                            f'{source.stem}_{index}{source.suffix}')
                        index += 1
                    shutil.move(str(source), str(destination))
                    saved.append(str(destination))
                return saved

    def download_gallery(self, url, folder):
            before = self.snapshot(folder)
            cmd = [sys.executable, '-m', 'gallery_dl', '--no-mtime',
                   '--directory', str(folder), url]
            self.events.put(('log', 'Trying image / post extractor...'))
            if getattr(sys, 'frozen', False):
                # The bundled executable is not a Python interpreter; call gallery-dl directly.
                import gallery_dl
                from gallery_dl import config as gallery_config, job as gallery_job
                gallery_config.set(('extractor',), 'base-directory', str(folder))
                gallery_config.set(('extractor',), 'directory', [])
                gallery_config.set(('extractor',), 'mtime', False)
                result = gallery_job.DownloadJob
                from gallery_dl import extractor
                ext = extractor.find(url)
                if ext is None:
                    raise RuntimeError('Unsupported image post URL')
                result(ext).run()
            else:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=180, errors='replace')
                if proc.returncode != 0:
                    detail = (proc.stderr or proc.stdout).strip()
                    raise RuntimeError(detail[-900:] or 'gallery-dl failed.')
            files = self.changed_files(folder, before)
            if not files:
                raise RuntimeError('No new media saved. The post may be unsupported, '
                                   'restricted, or already downloaded.')
            return files

# Resolve HTML/CSS assets both from source and a PyInstaller bundle.
def resource_path(relative):
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return str(root / relative)

app = Flask(__name__, template_folder=resource_path('templates'), static_folder=resource_path('static'))

@app.errorhandler(Exception)
def api_error(exc):
    from werkzeug.exceptions import HTTPException
    if request.path.startswith('/api/'):
        app.logger.exception('API failure')
        code = exc.code if isinstance(exc, HTTPException) else 500
        return jsonify(error=str(exc), ok=False), code
    raise exc

engine = DownloadEngine()
lock = threading.Lock()
state = {'busy': False, 'progress': 0, 'status': 'Ready for launch', 'logs': [], 'success': False, 'folder': ''}

def drain():
    while True:
        try: event = engine.events.get_nowait()
        except queue.Empty: break
        kind = event[0]
        if kind == 'progress': state['progress'] = round(event[1], 1); state['status'] = 'Downloading...'
        elif kind == 'status': state['status'] = event[1]
        elif kind == 'log': state['logs'].append(str(event[1]))
        elif kind == 'success':
            state['busy'] = False; state['progress'] = 100; state['success'] = True
            state['status'] = 'Download complete!'; state['folder'] = str(FOLDERS[event[1]])
            state['logs'].append('Saved ' + str(len(event[2])) + ' file(s)')
        elif kind == 'error':
            state['busy'] = False; state['status'] = 'Download failed'; state['logs'].append('ERROR: ' + str(event[1]))
    state['logs'] = state['logs'][-60:]

@app.get('/')
def index(): return render_template('index.html')

@app.get('/api/status')
def status():
    with lock:
        drain()
        return jsonify(state)

@app.post('/api/download')
def download():
    data = request.get_json(silent=True) or {}
    platform = data.get('platform')
    url = str(data.get('url', '')).strip()
    mode = data.get('mode')
    if platform not in PLATFORMS or mode not in ('Auto', 'Video / Reel', 'Image / Photo'):
        return jsonify(error='Invalid platform or media type'), 400
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        valid = parsed.scheme in ('http', 'https') and any(host == d or host.endswith('.'+d) for d in DOMAINS[platform])
    except ValueError: valid = False
    if not valid: return jsonify(error='Paste a valid ' + platform + ' URL'), 400
    with lock:
        drain()
        if state['busy']: return jsonify(error='A download is already running'), 409
        state.update(busy=True, progress=0, status='Connecting to ' + platform, logs=[], success=False, folder='')
    try:
        threading.Thread(target=engine.download_media, args=(platform,url,mode), daemon=True).start()
    except Exception:
        with lock: state['busy'] = False
        raise
    return jsonify(ok=True)

if __name__ == '__main__':
    print('Open http://127.0.0.1:5055 in your browser')
    app.run(host='127.0.0.1', port=5055, debug=False, threaded=True)
