"""Verify English presets retain library content and leave bilingual sources intact."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

from distribution import ROOT
from prepare_english_assets import prepare_english_assets
sys.path.insert(0, str(ROOT / 'workbench'))
from app import read_library_xlsx


class EnglishAssetsTest(unittest.TestCase):
    def test_independent_english_presets(self):
        originals = [ROOT / 'workbench' / name for name in (
            'web/index.html', 'web/interface.js', 'resources/personnel.json',
            'resources/word_library.xlsx', 'resources/ui_config.json')]
        before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in originals]
        qa = ROOT / '.build/qa'
        qa.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='english-assets-', dir=qa) as folder:
            web, resources = prepare_english_assets(Path(folder) / 'english')
            page = (web / 'index.html').read_text(encoding='utf-8')
            self.assertNotRegex(page, r'[\u4e00-\u9fff]')
            self.assertNotIn('languageSelect', page)
            self.assertIn('lang="en-AU"', page)
            self.assertIn('Photo and wording subitems', page)
            self.assertIn('Add subitem', page)
            self.assertIn('Photos in this subitem share the same wording', page)
            self.assertIn('englishOnly: true', (web / 'interface.js').read_text())
            self.assertEqual(json.loads((resources / 'ui_config.json').read_text())['edition'], 'english')
            people = json.loads((resources / 'personnel.json').read_text())['people']
            self.assertEqual(people[0]['name'], 'Example author (please edit)')
            self.assertEqual(people[1]['roles'], ['reviewer'])
            english = (resources / 'word_library.xlsx').read_bytes()
            self.assertEqual(read_library_xlsx(english), read_library_xlsx(originals[3].read_bytes()))
            with zipfile.ZipFile(resources / 'word_library.xlsx') as workbook:
                for name in workbook.namelist():
                    if name.endswith('.xml'):
                        self.assertNotRegex(workbook.read(name).decode(), r'[\u4e00-\u9fff]', name)
        self.assertEqual(before, [hashlib.sha256(p.read_bytes()).hexdigest() for p in originals])


if __name__ == '__main__':
    unittest.main()
