import importlib.util, io, unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('kodi_common_test',Path(__file__).resolve().parent.parent/'kodi/script.frame/common.py')
common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)

class KodiApiTests(unittest.TestCase):
    def test_server_reason_is_shown_and_response_closed(self):
        body=io.BytesIO(b'{"error":"The staged update changed. Review it again."}')
        error=HTTPError('http://localhost',400,'Bad Request',{},body)
        with patch.object(common,'urlopen',side_effect=error):
            with self.assertRaisesRegex(ValueError,'staged update changed'):common.api('/api/update/apply',{})
        self.assertTrue(body.closed)
    def test_non_json_error_falls_back_to_status(self):
        with patch.object(common,'urlopen',side_effect=HTTPError('http://localhost',400,'Bad Request',{},io.BytesIO(b'<html>Error</html>'))):
            with self.assertRaisesRegex(ValueError,'HTTP 400: Bad Request'):common.api('/api/update/apply',{})
