import requests
import json
from feedgen.feed import FeedGenerator
import datetime

def build_anime_rss():
    api_url = "https://tuamc.b4a.app/classes/Content"
    
    # 1. Official REST APIs put the keys in the Headers, not the payload
    headers = {
        "X-Parse-Application-Id": "EqXj3CWkTa9Ens1sPrzQkKMbBdnc6bYbHKR2qvRE",
        "X-Parse-JavaScript-Key": "Cd3j7SWbPhXJahCRK3D47bcYFNnHWFjBfiDnXSjX"
    }

    # 2. The search filters go into the URL parameters
    params = {
        "where": json.dumps({"genre": "Series", "subgenre": "Animación"}),
        "order": "-updatedAt",
        "limit": 1000
    }

    print("Fetching data from AMC API...")
    # 3. We do a standard GET request now!
    response = requests.get(api_url, headers=headers, params=params)
    
    if response.status_code != 200:
        print(f"Error fetching data: {response.text}")
        return

    data = response.json() 
    anime_list = data.get('results', []) 
    
    if not anime_list:
        print("⚠️ Warning: The database returned 0 items. Check the 'where' filter.")

    fg = FeedGenerator()
    fg.title('AMC Channels - Series de Animación')
    fg.link(href="https://amcchannels.es/buscar/categoria/Series?sub=Animaci%C3%B3n", rel='alternate')
    fg.description('Últimas series de animación publicadas en AMC Channels.')
    fg.language('es')


    data = response.json() 
    anime_list = data.get('results', []) 
    
    if not anime_list:
        print("⚠️ Warning: The database returned 0 items. Check the 'where' filter.")
        return

    # --- ADD THIS TEMPORARY DEBUG CODE ---
    print("\n🔍 --- FIRST ITEM DATA --- 🔍")
    # json.dumps with indent=4 makes it highly readable
    print(json.dumps(anime_list[0], indent=4, ensure_ascii=False))
    print("--------------------------------\n")
    # -------------------------------------

    fg = FeedGenerator()
    for item in anime_list:
        # Fetch the parent anime title. 
        # Note: Change 'showTitle' or 'seriesName' if the API uses a different key (like 'show' or 'anime_title')
        anime_title = item.get('showTitle', item.get('seriesName', ''))
        episode_title = item.get('title', item.get('name', 'Sin título')) 
        
        # Combine the anime title and episode title
        if anime_title and anime_title != episode_title:
            full_title = f"{anime_title} - {episode_title}"
        else:
            full_title = episode_title
            
        link = item.get('url', item.get('slug', ''))
        if not link.startswith('http'):
            link = "https://amcchannels.es/series/" + link.strip('/')
            
        description = item.get('description', item.get('synopsis', 'Sin descripción'))

        fe = fg.add_entry()
        fe.title(full_title) # Assign the newly formatted title here
        fe.link(href=link)
        fe.description(description)
        
        date_str = item.get('updatedAt', item.get('createdAt'))
        if date_str:
            pub_date = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            pub_date = datetime.datetime.now(datetime.timezone.utc)
            
        fe.pubDate(pub_date) 
        
    fg.rss_file('amc_animacion.xml')
    print(f"✅ RSS Feed generated with {len(anime_list)} series: amc_animacion.xml")

if __name__ == '__main__':
    build_anime_rss()
