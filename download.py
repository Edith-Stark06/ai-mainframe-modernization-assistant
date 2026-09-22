import urllib.request
import re

url = "https://www.ibm.com/products/z16"  # z16 as fallback if 17 doesn't exist
try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req).read().decode("utf-8")
    images = re.findall(r"https://[^\"\'\s]+\.(?:png|jpg|jpeg|webp)", html)
    print("Found images z16:", list(set(images))[:10])
except Exception:
    pass

url = "https://www.ibm.com/products/z17"
try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req).read().decode("utf-8")
    images = re.findall(r"https://[^\"\'\s]+\.(?:png|jpg|jpeg|webp)", html)
    print("Found images z17:", list(set(images))[:10])
except Exception:
    pass
