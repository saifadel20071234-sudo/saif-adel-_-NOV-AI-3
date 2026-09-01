import urllib.request
import urllib.error
import time
import webbrowser
import sys

url = "http://127.0.0.1:8000"
print("Waiting for server to be ready before opening browser...")

for _ in range(60):
    try:
        urllib.request.urlopen(url)
        webbrowser.open(url)
        sys.exit(0)
    except urllib.error.HTTPError as e:
        if e.code == 401: # 401 means server is up but requires auth (which is expected)
            webbrowser.open(url)
            sys.exit(0)
        time.sleep(1)
    except Exception:
        time.sleep(1)

print("Server did not start in time.")
