from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import concurrent.futures 
import os
import subprocess
import m3u8
from playwright.sync_api import sync_playwright

api_app = Flask(__name__)

# --- CORS CONFIGURATION ---
CORS(api_app, resources={r"/api/*": {"origins": ["https://void-streaming.web.app", "http://localhost:5000"]}})

BASE_URL = "https://hianime.to"
ANILIST_API = "https://graphql.anilist.co"
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "697ec0e63af6ada6b530674b717622b8") 
# Get your token from browserless.io
BROWSERLESS_TOKEN = os.environ.get("BROWSERLESS_TOKEN") 

class ScraperEngine:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-requested-with": "XMLHttpRequest",
            "Referer": f"{BASE_URL}/home"
        }

    # ... (Keep all your existing ScraperEngine methods: get_poster, enrich, get_schedule, search, get_episodes) ...

scraper = ScraperEngine()

# --- MODIFIED MOVIE DOWNLOADER HELPER (OPTION 3) ---

def resolve_source_m3u8(tmdb_id, s=None, e=None):
    url = f"https://www.2embed.cc/embedtv/{tmdb_id}&s={s}&e={e}" if s else f"https://www.2embed.cc/embed/{tmdb_id}"
    found_m3u8 = {"master": None}
    
    with sync_playwright() as p:
        # Connect to remote browser instead of launching local chromium
        # This saves ~400MB of RAM on Render
        browser_url = f"wss://chrome.browserless.io?token={BROWSERLESS_TOKEN}"
        try:
            browser = p.chromium.connect_over_cdp(browser_url)
            context = browser.new_context()
            page = context.new_page()
            
            def handle_request(request):
                if ".m3u8" in request.url and not found_m3u8["master"]:
                    found_m3u8["master"] = request.url
            
            page.on("request", handle_request)
            
            # Navigate and wait for the link to appear in network traffic
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(4000) 
            
            browser.close()
        except Exception as e:
            print(f"Browserless Error: {e}")
            
    return found_m3u8["master"]

def get_clean_filename(tmdb_id, media_type, s=None, e=None):
    try:
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={TMDB_API_KEY}"
        data = requests.get(url).json()
        name = data.get("title") or data.get("name", "Video")
        if media_type == "tv":
            return f"{name} - S{str(s).zfill(2)}E{str(e).zfill(2)}"
        return name
    except: return "Video"

# --- ROUTES ---

@api_app.route('/')
def home(): return "Void API is Running."

@api_app.route('/api/schedule')
def api_schedule(): return jsonify({"status": "success", "data": scraper.get_schedule()})

@api_app.route('/api/search')
def api_search():
    query = request.args.get('q')
    return jsonify({"status": "success", "data": scraper.search_anime(query)}) if query else jsonify({"status": "error"})

@api_app.route('/api/episodes/<anime_id>')
def api_episodes(anime_id):
    return jsonify({"status": "success", "episodes": scraper.get_episodes(anime_id)})

@api_app.route('/api/options')
def api_options():
    tmdb_id = request.args.get('id')
    s = request.args.get('s')
    e = request.args.get('e')
    
    master_url = resolve_source_m3u8(tmdb_id, s, e)
    if not master_url:
        return jsonify({"status": "error", "message": "No stream found"}), 404
    
    playlist = m3u8.load(master_url)
    qualities = []
    for p in playlist.playlists:
        res = p.stream_info.resolution
        qualities.append({
            "quality": f"{res[1]}p" if res else "Unknown",
            "url": p.absolute_uri
        })
    
    return jsonify({"status": "success", "qualities": qualities})

@api_app.route('/api/download')
def api_download():
    m3u8_url = request.args.get('url')
    tmdb_id = request.args.get('tmdb_id')
    media_type = request.args.get('media_type', 'movie')
    quality = request.args.get('quality', '720p')
    s = request.args.get('s')
    e = request.args.get('e')

    filename = f"{get_clean_filename(tmdb_id, media_type, s, e)} ({quality}).mp4"

    ffmpeg_cmd = [
        'ffmpeg', '-headers', 'Referer: https://www.2embed.cc/\r\n',
        '-i', m3u8_url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
        '-f', 'mp4', '-movflags', 'frag_keyframe+empty_moov', 'pipe:1'
    ]

    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE)

    return Response(
        process.stdout,
        mimetype="video/mp4",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    api_app.run(host='0.0.0.0', port=port)
