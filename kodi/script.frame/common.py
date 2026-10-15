import json
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:8080'

def api(path, data=None, timeout=3):
    request = Request(BASE + path, data=json.dumps(data).encode() if data is not None else None,
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)
