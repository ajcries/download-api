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
# Replace the origins list with your actual Firebase domain
CORS(api_app, resources={r"/api/*": {"origins": ["https://void-streaming.web.app", "http://localhost:5000"]}})

BASE_URL = "https://hianime.to"
ANILIST_API = "https://graphql.anilist.co"
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "697ec0e63af6ada6b530674b717622b8") 

class ScraperEngine:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-requested-with": "XMLHttpRequest",
            "Referer": f"{BASE_URL}/home"
        }

    def get_poster_from_anilist(self, title):
        query = '''
        query ($search: String) {
          Media (search: $search, type: ANIME) {
            id
            coverImage { large }
            bannerImage
            averageScore
            startDate { year }
          }
        }
        '''
        try:
            response = self.session.post(ANILIST_API, json={'query': query, 'variables': {'search': title}}, timeout=2)
            data = response.json()
            media = data['data']['Media']
            return {
                "poster": media['coverImage']['large'],
                "banner": media['bannerImage'],
                "score": media['averageScore'],
                "year": media['startDate']['year'],
                "al_id": media['id']
            }
        except:
            return {"poster": "https://via.placeholder.com/400x600?text=No+Poster", "banner": "", "score": "N/A", "year": "N/A", "al_id": None}

    def enrich_with_metadata(self, anime_list):
        def fetch_meta(anime):
            meta = self.get_poster_from_anilist(anime['title'])
            anime.update(meta)
            return anime
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            return list(executor.map(fetch_meta, anime_list))

    def get_schedule(self, date_str=None):
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        url = f"{BASE_URL}/ajax/schedule/list?tzOffset=0&date={date_str}"
        try:
            r = self.session.get(url, headers=self.headers)
            soup = BeautifulSoup(r.json().get("html", ""), "html.parser")
            anime_list = []
            for item in soup.select("li"):
                title_elem = item.select_one(".film-name")
                if title_elem and title_elem.find('a'):
                    link = title_elem.find('a')['href']
                    anime_list.append({
                        "title": title_elem.text.strip(),
                        "id": link.split("-")[-1].split("?")[0],
                        "full_id": link.split("/")[-1].split("?")[0],
                        "time": item.select_one(".time").text.strip() if item.select_one(".time") else ""
                    })
            return self.enrich_with_metadata(anime_list[:15])
        except: return []

    def search_anime(self, keyword):
        url = f"{BASE_URL}/search?keyword={keyword}"
        try:
            r = self.session.get(url, headers=self.headers)
            soup = BeautifulSoup(r.text, "html.parser")
            results = []
            for item in soup.select(".flw-item"):
                name_link = item.select_one(".film-name a")
                if name_link:
                    link = name_link['href']
                    results.append({
                        "title": name_link.text.strip(),
                        "id": link.split("-")[-1].split("?")[0],
                        "full_id": link.split("/")[-1].split("?")[0]
                    })
            return self.enrich_with_metadata(results[:10])
        except: return []

    def get_episodes(self, anime_id):
        try:
            numeric_id = anime_id.split("-")[-1] if "-" in str(anime_id) else anime_id
            url = f"{BASE_URL}/ajax/v2/episode/list/{numeric_id}"
            r = self.session.get(url, headers=self.headers)
            soup = BeautifulSoup(r.json().get("html", ""), "html.parser")
            eps = []
            for e in soup.select(".ep-item"):
                eps.append({
                    "number": e.get('data-number'), 
                    "id": e.get('data-id'),
                    "title": e.get('title')
                })
            return eps
        except: return []

scraper = ScraperEngine()

# --- MOVIE DOWNLOADER HELPERS ---

def resolve_source_m3u8(tmdb_id, s=None, e=None):
    # Using 2Embed as the primary scraping source
    url = f"https://www.2embed.cc/embedtv/{tmdb_id}&s={s}&e={e}" if s else f"https://www.2embed.cc/embed/{tmdb_id}"
    
    found_m3u8 = {"master": None}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Intercept network requests to find the .m3u8 playlist
        def handle_request(request):
            if ".m3u8" in request.url and not found_m3u8["master"]:
                found_m3u8["master"] = request.url
        
        page.on("request", handle_request)
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000) # Give it time to trigger the player
        except: pass
        finally: browser.close()
        
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

# --- NEW DOWNLOAD ROUTES ---

@api_app.route('/api/options')
def api_options():
    tmdb_id = request.args.get('id')
    s = request.args.get('s')
    e = request.args.get('e')
    
    master_url = resolve_source_m3u8(tmdb_id, s, e)
    if not master_url:
        return jsonify({"status": "error", "message": "No stream found"}), 404
    
    # Parse the master playlist to find different qualities
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

    # FFmpeg command to convert stream to mp4 and pipe to output
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
    # For Docker on Render, 10000 is the standard port
    port = int(os.environ.get("PORT", 10000))
    api_app.run(host='0.0.0.0', port=port)
