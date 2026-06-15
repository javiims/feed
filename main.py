import requests
import json
from feedgen.feed import FeedGenerator
import datetime

def build_anime_rss():
    api_url = "https://tuamc.b4a.app/classes/Content"
    
    headers = {
        "X-Parse-Application-Id": "EqXj3CWkTa9Ens1sPrzQkKMbBdnc6bYbHKR2qvRE",
        "X-Parse-JavaScript-Key": "Cd3j7SWbPhXJahCRK3D47bcYFNnHWFjBfiDnXSjX"
    }

    params = {
        "where": json.dumps({"genre": "Series", "subgenre": "Animación"}),
        "order": "-updatedAt",
        "limit": 1000
    }

    print("Fetching data from AMC API...")
    response = requests.get(api_url, headers=headers, params=params)
    
    if response.status_code != 200:
        print(f"Error fetching data: {response.text}")
        return

    data = response.json() 
    anime_list = data.get('results', []) 
    
    if not anime_list:
        print("⚠️ Warning: The database returned 0 items. Check the 'where' filter.")
        return

    fg = FeedGenerator()
    fg.title('AMC Channels - Series de Animación')
    fg.link(href="https://amcchannels.es/buscar/categoria/Series?sub=Animacion", rel='alternate')
    fg.description('Últimas series de animación publicadas en AMC Channels.')
    fg.language('es')

    for item in anime_list:
        # 1. Grab the metaTitle which already contains the Anime + Episode Name.
        # Fallback to standard title or 'Sin título' if it's missing to prevent crashes.
        title = item.get('metaTitle') or item.get('title') or 'Sin título'
        
        # 2. Grab the slug for the URL. Fallback safely to prevent crashes.
        link = item.get('slug') or item.get('url') or ''
        if not link.startswith('http'):
            link = "https://amcchannels.es/series/" + str(link).strip('/')
            
        # 3. Grab the description. Fallback safely to prevent crashes.
        description = item.get('description') or item.get('metaDescription') or 'Sin descripción'

        fe = fg.add_entry()
        
        # 4. Wrap everything in str() to guarantee feedgen never receives a 'None' type
        fe.title(str(title))
        fe.link(href=str(link))
        fe.description(str(description))
        
        date_str = item.get('updatedAt') or item.get('createdAt')
        if date_str:
            pub_date = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            pub_date = datetime.datetime.now(datetime.timezone.utc)
            
        fe.pubDate(pub_date) 
        
    fg.rss_file('amc_animacion.xml')
    print(f"✅ RSS Feed generated with {len(anime_list)} series: amc_animacion.xml")

if __name__ == '__main__':
    build_anime_rss()
