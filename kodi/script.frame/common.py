import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = 'http://127.0.0.1:8080'

def api(path, data=None, timeout=3):
    request = Request(BASE + path, data=json.dumps(data).encode() if data is not None else None,
                      headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read(8192)).get('error')
        except (ValueError, AttributeError):
            detail = None
        finally:
            exc.close()
        message = detail[:1000] if isinstance(detail, str) and detail else str(exc.reason)
        raise ValueError('HTTP {}: {}'.format(exc.code, message)) from exc
