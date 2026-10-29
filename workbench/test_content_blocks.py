import secrets
import unittest
import zipfile
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from lxml import etree as E
from openpyxl import load_workbook
from PIL import Image
from app import Store
from content_blocks import text_block, cover_modules
from report_engine import NS


class ContentBlockTests(unittest.TestCase):
    def setUp(self):
        qa=Path(__file__).resolve().parents[1]/'.build/qa';qa.mkdir(parents=True,exist_ok=True)
        self.tmp=TemporaryDirectory(dir=qa);self.store=Store(self.tmp.name)
        image=BytesIO();Image.new('RGB',(600,360),'#7eaa6c').save(image,'PNG')
        self.photo=self.store.upload(image.getvalue(),'section.png')
        self.blocks=[text_block('Section text retained.'),
                     {'id':secrets.token_hex(16),'type':'table','rows':[['Load','Result'],['=1+1','Literal text']]},
                     {'id':secrets.token_hex(16),'type':'image','photo':{**self.photo,'caption':'Section figure'},'width':70}]

    def tearDown(self):self.store.previews.close();self.tmp.cleanup()

    def test_inspection_rich_sections_export_and_backup_preserve_order_and_photos(self):
        p=self.store.new();p['metadata'].update(site='Rich QA',project_number='QA',report_number='QA-01')
        p['items']=[{'id':secrets.token_hex(16),'element':'Columns','condition_rating':'3. Minor corrosion','likelihood':'Possible','severity':'Minor','priority':'Low',
                     'subitems':[{'id':secrets.token_hex(16),'photos':[self.photo.copy()],'observation':'Item description','recommendation':''}]}]
        p['sections']['introduction']='Stale legacy text'
        p['section_blocks']={'introduction':deepcopy(self.blocks),'conclusion':[text_block('Conclusion retained.')],'cost_estimate':[text_block('Basis of estimate')]}
        p['cost_rows']=[{'description':'Repair','quantity':'2','unit':'each','rate':'10','priority':'Low'}]
        saved=self.store.save(p);restored=self.store.restore(self.store.backup(saved['id']))
        photo=restored['section_blocks']['introduction'][2]['photo']
        self.assertNotEqual(photo['id'],self.photo['id']);self.assertTrue(self.store.photo_path(photo['id']).exists())
        self.assertEqual(photo['caption'],'Section figure')
        self.assertEqual(self.store.copy_project(restored)['section_blocks'],restored['section_blocks'])
        export=self.store.export(restored['id']);path=self.store.path/'exports'/(export['id']+'.docx')
        with zipfile.ZipFile(path) as z:
            doc=E.fromstring(z.read('word/document.xml'));body=doc.find('w:body',NS)
            text=' '.join(doc.xpath('//w:t/text()',namespaces=NS))
            self.assertNotIn('Stale legacy text',text)
            for value in ['=1+1','Conclusion retained.','Basis of estimate','20.00','Section figure']:self.assertIn(value,text)
            texts=[' '.join(n.xpath('.//w:t/text()',namespaces=NS)) for n in body]
            self.assertLess(next(i for i,t in enumerate(texts) if 'Section text retained.' in t),next(i for i,t in enumerate(texts) if '=1+1' in t))
            self.assertLess(next(i for i,t in enumerate(texts) if 'Section figure' in t),next(i for i,t in enumerate(texts) if ' '.join(t.split()).upper()=='EXTERNAL BUILDING OBSERVATIONS'))
            self.assertLess(next(i for i,t in enumerate(texts) if ' '.join(t.split()).upper()=='EXTERNAL BUILDING OBSERVATIONS'),next(i for i,t in enumerate(texts) if 'Item description' in t))
            self.assertTrue(any('section-' in name for name in z.namelist()))

    def test_cal_cover_modules_start_blank_and_export_all_block_types(self):
        p=self.store.new('calculation')
        self.assertEqual([(m['title'],m['blocks']) for m in p['cal_cover']['modules']],[('',[]),('',[])])
        p['cal_cover']['modules'][0].update(title='PROJECT BRIEF',blocks=deepcopy(self.blocks))
        saved=self.store.save(p);restored=self.store.restore(self.store.backup(saved['id']))
        self.assertNotEqual(restored['cal_cover']['modules'][0]['blocks'][2]['photo']['id'],self.photo['id'])
        for format in ['xlsx','docx']:
            result=self.store.export_snapshot(restored,format);path=self.store.path/'exports'/(result['id']+'.'+format)
            if format=='xlsx':
                book=load_workbook(path);values=[c.value for row in book['Cover'] for c in row]
                for value in ['PROJECT BRIEF','Section text retained.','=1+1','Section figure']:self.assertIn(value,values)
                self.assertNotIn('INTRODUCTION',values);self.assertNotIn('MATERIAL PROPERTIES',values)
                self.assertEqual(len(book['Cover']._images),2);book.close()
            else:
                with zipfile.ZipFile(path) as z:
                    text=' '.join(E.fromstring(z.read('word/document.xml')).xpath('//w:t/text()',namespaces=NS))
                    for value in ['PROJECT BRIEF','Section text retained.','=1+1','Section figure']:self.assertIn(value,text)
                    self.assertNotIn('MATERIAL PROPERTIES',text)

    def test_invalid_blocks_rejected_without_saving(self):
        p=self.store.new();p['section_blocks']={'introduction':deepcopy(self.blocks)}
        for mutate in [lambda b:b[1].update(rows=[['A'],['B','C']]),lambda b:b[2].update(width=101),lambda b:b[2]['photo'].update(id='f'*32),lambda b:b[1].update(id=b[0]['id'])]:
            bad=deepcopy(p);mutate(bad['section_blocks']['introduction'])
            with self.assertRaises(ValueError):self.store.save(bad)
        self.assertNotIn('section_blocks',self.store.load(p['id']))

    def test_legacy_cover_text_and_headings_are_available_for_migration(self):
        p=self.store.new('calculation');p['cal_cover'].pop('modules')
        p['cal_cover'].update(introduction_title='LEGACY PURPOSE',introduction='Existing cover text')
        modules=cover_modules(p)
        self.assertEqual(modules[0]['title'],'LEGACY PURPOSE')
        self.assertEqual(modules[0]['blocks'][0]['text'],'Existing cover text')


if __name__=='__main__':unittest.main()
