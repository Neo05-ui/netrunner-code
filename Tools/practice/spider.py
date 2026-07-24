import requests
from bs4 import BeautifulSoup
def get_page(url):
    response = requests.get(url)
    
    soup = BeautifulSoup(response.content, 'html.parser')
    print(soup.a)
get_page(input("what url would you like to scrape? "))
