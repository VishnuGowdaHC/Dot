import urllib.parse
import webbrowser
import asyncio
import re
import httpx
from AppOpener import open as openApp

async def resolve_direct_video_url(query: str):
    """Resolves the direct YouTube watch URL for the specified video query."""
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
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            matches = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", resp.text)
            if matches:
                return f"https://www.youtube.com/watch?v={matches[0]}"
    except Exception as e:
        print(f"[Warning] Direct video resolution failed: {e}")
    return None

async def routeAppOpener(text: str):
    """Opens a desktop application or plays media directly."""
    print(f"[Intent Opener] Processing command: '{text}'")
    lower_text = text.lower()
    
    # Direct video or music playback intent.
    if any(k in lower_text for k in ["play", "youtube", "song", "video", "track", "listen"]):
        video_url = await resolve_direct_video_url(text)
        if video_url:
            print(f"[Intent Opener] Playing YouTube video: {video_url}")
            webbrowser.open(video_url)
            return "Task Executed"

    if "open" in lower_text:
        target = lower_text.split("open", 1)[1].strip()
    else:
        target = lower_text.strip()

    if not target:
        print("[Intent Opener] No application target detected.")
        return None
    
    try:
        if target == "gmail":
            raise ValueError("Gmail routes to browser.")
        
        # Open the application in worker thread to prevent event loop blocking.
        await asyncio.to_thread(openApp, target, throw_error=True, match_closest=True)
        print(f"[Intent Opener] Opened application: '{target}'")
        return "Task Executed"
    
    except Exception:
        print(f"[Intent Opener] Application '{target}' not found. Falling back to browser search.")

    searchQuery = urllib.parse.quote(target)
    url = f"https://www.google.com/search?q={searchQuery}"
    webbrowser.open(url)
    return "Task Executed"

if __name__ == "__main__":
    asyncio.run(routeAppOpener("play bbno$ on youtube"))

 
            
