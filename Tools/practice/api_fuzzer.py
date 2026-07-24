import requests
import sys
import json

res = requests.get(url=f"https://jsonplaceholder.typicode.com/")
print (res)
#to check what the server is saying, use the command print (res.text)
data = res.json()
print(data)
#since this file is not json, we use html, but the tool works just fine.