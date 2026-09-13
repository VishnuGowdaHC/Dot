from AppOpener import open as openApp
import urllib.parse
import webbrowser
import asyncio
import re
import httpx

def resolve_direct_video_url(query: str):
    clean_query = query.lower()
    for prefix in ["play", "open", "watch", "listen to", "video of", "song"]:
        if clean_query.startswith(prefix):
            clean_query = clean_query[len(prefix):].strip()
    clean_query = clean_query.replace("on youtube", "").replace("in youtube", "").replace("youtube", "").strip()
    if not clean_query:
        clean_query = query.strip()

    try:
        q = urllib.parse.quote_plus(clean_query)
        url = f"https://www.youtube.com/results?search_query={q}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        }
        resp = httpx.get(url, headers=headers, timeout=5.0)
        matches = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", resp.text)
        if matches:
            return f"https://www.youtube.com/watch?v={matches[0]}"
    except Exception as e:
        print(f"[Warning] Direct video resolution failed: {e}")
    return None

async def routeAppOpener(text):
    print("inside routeAppOpener", text)
    lower_text = text.lower()
    
    # Direct video or music playback intent
    if any(k in lower_text for k in ["play", "youtube", "song", "video", "track", "listen"]):
        video_url = resolve_direct_video_url(text)
        if video_url:
            print(f"Directly playing YouTube video: {video_url}")
            webbrowser.open(video_url)
            return "Task Executed"

    if "open" in lower_text:
        target = lower_text.split("open", 1)[1].strip()
    else:
        target = lower_text.strip()

    if not target:
        print("Im unable to process your command")
        return
    
    try:
        if target == "gmail":
            raise Exception("routing to browser")
        
        #opening the app directly
        openApp(target, throw_error=True, match_closest=True)
        print(f"Found the {target} app to open")
        return "Task Executed"
    
    except Exception:
        print("Caught exception: app not found, falling back to browser")

    searchQuery = urllib.parse.quote(target)
    url = f"https://www.google.com/search?q={searchQuery}"
    webbrowser.open(url)
    return "Task Executed"

if __name__ == "__main__":
    asyncio.run(routeAppOpener("play bbno$ on youtube"))

 
            
