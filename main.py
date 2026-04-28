import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
import datetime

def build_anime_rss():
    url = "https://amcchannels.es/buscar/categoria/Series?sub=Animaci%C3%B3n"
    
    # Use headers to mimic a real browser, preventing the site from blocking you
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    }

    # 1. Fetch the webpage
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    # 2. Parse the HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 3. Initialize the RSS Feed
    fg = FeedGenerator()
    fg.title('AMC Channels - Series de Animación')
    fg.link(href=url, rel='alternate')
    fg.description('Últimas series de animación publicadas en AMC Channels.')
    fg.language('es')

    # 4. Find all anime items on the page
    # ---> CHANGE 'article.card-item' TO THE ACTUAL CSS SELECTOR OF THE ANIME CARDS <---
    anime_items = soup.select('.item-class') 

    for item in anime_items:
        # ---> CHANGE THESE SELECTORS TO MATCH THE SITE'S HTML <---
        title_element = item.select_one('.title-class')
        link_element = item.select_one('a')
        desc_element = item.select_one('.description-class')
        
        if not title_element or not link_element:
            continue

        title = title_element.get_text(strip=True)
        link = link_element['href']
        
        # Make sure the link is an absolute URL
        if not link.startswith('http'):
            link = "https://amcchannels.es" + link
            
        description = desc_element.get_text(strip=True) if desc_element else "Sin descripción"

        # 5. Add the item to our RSS feed
        fe = fg.add_entry()
        fe.title(title)
        fe.link(href=link)
        fe.description(description)
        # Using a fixed date or current time if the site doesn't list publish dates
        fe.pubDate(datetime.datetime.now(datetime.timezone.utc)) 
        
    # 6. Save the RSS feed to an XML file
    fg.rss_file('amc_animacion.xml')
    print("✅ RSS Feed successfully generated: amc_animacion.xml")

if __name__ == '__main__':
    build_anime_rss()
