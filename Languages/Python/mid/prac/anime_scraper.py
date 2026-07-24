import requests
from bs4 import BeautifulSoup
import pandas as pd

# 1. Replace with your actual profile/watchlist URL
URL = "https://aniwatchtv.to/user/watch-list" 

def scrape_anime():
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(URL, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')

    anime_data = []

    # This part depends on the specific site's HTML. 
    # Usually, categories are inside <div> or <table> with specific classes.
    # We will look for headers like "Watching", "Completed", etc.
    
    categories = {
        "watching": "Continuing Watching",
        "plantowatch": "Plan to Watch",
        "completed": "Completed"
    }

    for key, status_label in categories.items():
        # Example logic: finding a section by its ID or class
        # You'll need to inspect the site (Ctrl+Shift+I) to find the right class names
        section = soup.find('div', class_=f'section-{key}') 
        
        if section:
            titles = section.find_all('a', class_='anime-title')
            for title in titles:
                anime_data.append({
                    "Name": title.text.strip(),
                    "Status": status_label
                })

    # Save to CSV
    df = pd.DataFrame(anime_data)
    df.to_csv("my_anime_list.csv", index=False)
    print(f"Success! {len(anime_data)} animes saved to my_anime_list.csv")

if __name__ == "__main__":
    scrape_anime()