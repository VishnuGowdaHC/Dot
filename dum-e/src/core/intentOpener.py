from AppOpener import open as openApp
import urllib.parse
import webbrowser

def routeAppOpener(text):

    text = text.lower()
    print(text)
    if "open" in text:
        target = text.split("open", 1)[1].strip()
    else:
        target = text.strip()

    if not target:
        print("Im unable to process your command")
        return
    
    try:
        #opening the app directly
        openApp(target, throw_error=True, match_closest=True)
        print(f"Found the {target} app to open")
        return
    
    except Exception:
        print("Did not find the app to open,  routing to web")

    
    searchQuery = urllib.parse.quote(f"!ducky {target}") #bang feature of duckduckgo
    url = f"https://duckduckgo.com/?q={searchQuery}"
    webbrowser.open(url)

 
            
