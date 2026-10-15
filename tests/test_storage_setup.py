import importlib.util, json, sqlite3, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, Mock

spec=importlib.util.spec_from_file_location('configure_storage',Path(__file__).resolve().parents[1]/'scripts/configure-storage.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)

class StorageSetupTests(unittest.TestCase):
    def test_migration_preserves_originals_and_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();app=root/'app';app.mkdir();usb=root/'usb';usb.mkdir()
            media=app/'movies';media.mkdir();movie=media/'Movie.mkv';movie.write_bytes(b'movie')
            with sqlite3.connect(app/'library.db') as db:
                db.execute('CREATE TABLE movies (id INTEGER PRIMARY KEY,path TEXT,progress REAL)')
                db.execute('INSERT INTO movies VALUES(1,?,0.4)',(str(movie),))
            with patch.object(setup,'ROOT',app),patch.object(Path,'is_mount',return_value=True),patch.object(setup.subprocess,'run',return_value=Mock(stdout='test-uuid',returncode=3)):
                setup.configure(usb)
            self.assertEqual(movie.read_bytes(),b'movie')
            self.assertEqual((usb/'Hyperdrive/files/Movie.mkv').read_bytes(),b'movie')
            with sqlite3.connect(app/'library.db') as db:
                path,progress=db.execute('SELECT path,progress FROM movies').fetchone()
            self.assertEqual(path,str(usb/'Hyperdrive/files/Movie.mkv'));self.assertEqual(progress,.4)
            self.assertIn('HYPERDRIVE_USB_UUID="test-uuid"',(app/'frame.env').read_text())
            self.assertTrue(list(app.glob('library-before-usb-*.db')))
    def test_conflicting_usb_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();app=root/'app';(app/'movies').mkdir(parents=True);usb=root/'usb';target=usb/'Hyperdrive/files';target.mkdir(parents=True)
            (app/'movies/test.txt').write_text('old');(target/'test.txt').write_text('different')
            with patch.object(setup,'ROOT',app),patch.object(Path,'is_mount',return_value=True),patch.object(setup.subprocess,'run',return_value=Mock(stdout='test-uuid',returncode=3)):
                with self.assertRaises(ValueError):setup.configure(usb)
            self.assertEqual((target/'test.txt').read_text(),'different');self.assertFalse((app/'frame.env').exists())
