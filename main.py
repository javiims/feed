import requests
from feedgen.feed import FeedGenerator
import datetime

def build_anime_rss():
    api_url = "https://tuamc.b4a.app/classes/Content"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'text/plain',
        'Origin': 'https://amcchannels.es',
        'Referer': 'https://amcchannels.es/'
    }

    # Your exact payload from the Network Tab
    payload = {
        "_ApplicationId": "EqXj3CWkTa9Ens1sPrzQkKMbBdnc6bYbHKR2qvRE",
        "_JavaScriptKey": "Cd3j7SWbPhXJahCRK3D47bcYFNnHWFjBfiDnXSjX",
        "_ClientVersion": "js3.4.1",
        "_Method": "GET",
        "where": {
            "genre": "Series",
            "subgenre": "Animación"
        },
        "order": "-updatedAt",
        "limit": 24
    }

    print("Fetching data via POST request...")
    response = requests.post(api_url, headers=headers, json=payload)
    
    if response.status_code != 200:
        print(f"Error fetching data: {response.text}")
        return

    data = response.json() 
    anime_list = data.get('results', []) 
    
    fg = FeedGenerator()
    fg.title('AMC Channels - Series de Animación')
    fg.link(href="https://amcchannels.es/buscar/categoria/Series?sub=Animaci%C3%B3n", rel='alternate')
    fg.description('Últimas series de animación publicadas en AMC Channels.')
    fg.language('es')

    for item in anime_list:
        title = item.get('title', item.get('name', 'Sin título')) 
        
        link = item.get('url', item.get('slug', ''))
        if not link.startswith('http'):
            link = "https://amcchannels.es/series/" + link.strip('/')
            
        description = item.get('description', item.get('synopsis', 'Sin descripción'))

        fe = fg.add_entry()
        fe.title(title)
        fe.link(href=link)
        fe.description(description)
        
        # Pull the actual "updatedAt" or "createdAt" time from the database
        date_str = item.get('updatedAt', item.get('createdAt'))
        if date_str:
            # Parse the ISO format date provided by Back4App (e.g., "2023-10-05T14:48:00.000Z")
            # The replace('Z', '+00:00') ensures Python handles the UTC timezone correctly
            pub_date = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            pub_date = datetime.datetime.now(datetime.timezone.utc)
            
        fe.pubDate(pub_date) 
        
    fg.rss_file('amc_animacion.xml')
    print(f"✅ RSS Feed generated with {len(anime_list)} series: amc_animacion.xml")

if __name__ == '__main__':
    build_anime_rss()
