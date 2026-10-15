import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, Mock
from storage import require_storage, file_path

class StorageTests(unittest.TestCase):
    def test_missing_mount_and_wrong_uuid_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);media=root/'files';media.mkdir()
            with patch.dict(os.environ,{'HYPERDRIVE_USB_MOUNT':tmp,'HYPERDRIVE_USB_UUID':'expected'}):
                with patch.object(Path,'is_mount',return_value=False):
                    with self.assertRaises(ValueError):require_storage(media)
                with patch.object(Path,'is_mount',return_value=True),patch('storage.subprocess.run',return_value=Mock(stdout='wrong')):
                    with self.assertRaises(ValueError):require_storage(media)
                with patch.object(Path,'is_mount',return_value=True),patch('storage.subprocess.run',return_value=Mock(stdout='expected\n')):
                    require_storage(media)
    def test_any_extension_but_no_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('hello.html','report.pdf','program.exe','no-extension','photo.jpg'):
                self.assertEqual(file_path(tmp,name).name,name)
            for name in ('../escape','..','.','a/b','a\\b','bad\nname'):
                with self.assertRaises(ValueError):file_path(tmp,name)
