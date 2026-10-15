import importlib.util, tempfile, unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('package_kodi', ROOT/'scripts/package-kodi.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)

class KodiPackageTests(unittest.TestCase):
    def test_installable_archive_contains_explicit_folders_and_entrypoints(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            shutil.copytree(ROOT/'kodi', root/'kodi')
            output=package.build(root)
            self.assertEqual(package.validate_package(output), (ROOT/'VERSION').read_text().strip())
            with ZipFile(output) as z:
                self.assertTrue(z.getinfo('script.frame/').is_dir())
                self.assertTrue(z.getinfo('script.frame/resources/skins/Default/1080i/').is_dir())
                self.assertIn('script.frame/controls.py', z.namelist())
                self.assertFalse(any('__pycache__' in n for n in z.namelist()))
    def test_rejects_portal_update_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'wrong.zip'
            with ZipFile(path,'w') as z:
                z.writestr('manifest.json','{}');z.writestr('server.py','# app')
            with self.assertRaises(ValueError):package.validate_package(path)

    def test_hyperdrive_is_separate_installable_addon(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shutil.copytree(ROOT/'kodi',root/'kodi')
            output=package.build(root,addon_id='script.hyperdrive')
            self.assertEqual(package.validate_package(output),(ROOT/'VERSION').read_text().strip())
            with ZipFile(output) as z:
                self.assertIn('script.hyperdrive/service.py',z.namelist())
                self.assertNotIn('script.frame/default.py',z.namelist())
