import sys, unittest, tempfile, json, zipfile, hashlib, secrets
from io import BytesIO
from pathlib import Path
from PIL import Image
import pillow_heif
from lxml import etree as E
from unittest.mock import patch
from app import Store, RESOURCES, read_library_xlsx, library_digest, LIBRARY_POLICY, atomic_json
from report_engine import NS

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'.build/qa'

def image_bytes(size=(800,600),mode='JPEG'):
    image=Image.new('RGB',size,(173,197,157));out=BytesIO()
    image.save(out,mode);return out.getvalue()

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        QA.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=QA);self.store=Store(self.tmp.name);self.project=self.store.new()

    def tearDown(self):self.tmp.cleanup()

    def item(self,photos):
        return {'id':secrets.token_hex(16),'photos':photos,'element':'Columns','condition_rating':'5. Major deterioration',
                'likelihood':'Likely','severity':'Significant','priority':'Critical',
                'observation':'Minor corrosion at the lower section. Manual edit: C1 & C2 <test>.',
                'recommendation':'Clean, wire brush and repaint.'}

    def test_common_library_matches_excel_and_keeps_stable_ids(self):
        lib=read_library_xlsx((RESOURCES/'word_library.xlsx').read_bytes())
        self.assertEqual([len(lib[k]) for k in ['observation','recommendation']],[90,44])
        for rows in lib.values():
            self.assertTrue(all(r['frequency']>=2 for r in rows))
            self.assertEqual([r['frequency'] for r in rows],sorted([r['frequency'] for r in rows],reverse=True))
        self.assertEqual(lib['observation'][0]['id'],'OBS-0001')
        self.assertEqual(lib['recommendation'][0]['text'],'Clean, wire brush and repaint.')
        self.assertEqual(lib,self.store.library)

    def test_old_preset_upgrades_without_changing_saved_item_text(self):
        photo=self.store.upload(image_bytes(),'saved.jpg')
        item=self.item([photo]);item['observation']='Unique wording retained in an existing report.'
        item['observation_source']='OBS-0622';self.project['items']=[item]
        self.store.save(self.project)
        legacy={'observation':[{'id':'OBS-0622','text':'One-off historical wording','elements':'Columns','frequency':1}],
                'recommendation':self.store.library['recommendation']}
        atomic_json(self.store.library_path,legacy)
        (self.store.path/'library.xlsx').write_bytes(b'old default workbook')
        with patch.dict(LIBRARY_POLICY,{'legacy_default_sha256':library_digest(legacy)}):
            upgraded=Store(self.store.path)
        self.assertEqual([len(upgraded.library[k]) for k in ['observation','recommendation']],[90,44])
        self.assertEqual((upgraded.path/'library.xlsx').read_bytes(),(RESOURCES/'word_library.xlsx').read_bytes())
        self.assertEqual(upgraded.load(self.project['id'])['items'],self.project['items'])
        self.assertEqual(Store(self.store.path).library,upgraded.library)

    def test_custom_library_is_preserved_on_upgrade(self):
        custom=json.loads(json.dumps(self.store.library))
        custom['observation'][0]['text']='Custom team wording';custom['observation'][0]['frequency']=1
        atomic_json(self.store.library_path,custom)
        workbook=b'custom workbook';(self.store.path/'library.xlsx').write_bytes(workbook)
        reopened=Store(self.store.path)
        self.assertEqual(reopened.library,custom)
        self.assertEqual((reopened.path/'library.xlsx').read_bytes(),workbook)

    def test_photos_heic_exif_rotate_original_preserved(self):
        jpg=image_bytes();photo=self.store.upload(jpg,'phone.jpg');original=self.store.path/'originals'/(photo['id']+'.jpg')
        self.assertEqual(original.read_bytes(),jpg)
        rotated=self.store.rotate(photo['id'])
        with Image.open(self.store.photo_path(rotated['id'])) as im:self.assertEqual(im.size,(600,800))
        heic=BytesIO();Image.new('RGB',(320,480),'#789977').save(heic,'HEIF')
        ph=self.store.upload(heic.getvalue(),'phone.heic')
        with Image.open(self.store.photo_path(ph['id'])) as im:self.assertEqual(im.size,(320,480))
        # Real phone metadata orientation: transpose before stripping GPS/EXIF from report JPEG.
        exif=Image.Exif();exif[274]=6;buf=BytesIO();Image.new('RGB',(900,600),'white').save(buf,'JPEG',exif=exif)
        ph=self.store.upload(buf.getvalue(),'oriented.jpg')
        with Image.open(self.store.photo_path(ph['id'])) as im:
            self.assertEqual(im.size,(600,900));self.assertFalse(im.getexif())
        (QA/'upload-fixtures').mkdir(exist_ok=True)
        (QA/'upload-fixtures/landscape.jpg').write_bytes(jpg)
        (QA/'upload-fixtures/portrait.heic').write_bytes(heic.getvalue())

    def test_atomic_save_reopen_conflict_and_backup(self):
        ph=self.store.upload(image_bytes(),'site.jpg');self.project['items']=[self.item([ph])]
        old=json.loads(json.dumps(self.project));saved=self.store.save(self.project)
        self.assertEqual(self.store.load(saved['id']),saved)
        with self.assertRaises(ValueError):self.store.save(old)
        self.assertTrue((self.store.path/'backups'/(saved['id']+'.previous.json')).exists())
        restored=self.store.restore(self.store.backup(saved['id']))
        self.assertNotEqual(restored['id'],saved['id'])
        self.assertEqual(restored['items'][0]['observation'],saved['items'][0]['observation'])
        self.assertNotEqual(restored['items'][0]['photos'][0]['id'],ph['id'])

    def test_reports_template_fidelity_multiphoto_long_text(self):
        photos=[self.store.upload(image_bytes(size),'photo'+str(i)+'.jpg') for i,size in enumerate([(1200,900),(900,1200),(1200,900),(900,1200)],1)]
        self.project['metadata'].update({'site':'Prototype Layout Test','report_number':'TEST-SIR-001','project_number':'TEST','report_date':'2026-10-10','prepared_by':'Test Author','reviewed_by':'Test Reviewer'})
        self.project['items']=[self.item(photos),self.item([photos[0]])]
        self.project['items'][1]['priority']='Low'
        self.project['items'][1]['observation']='Long observation for pagination verification. '+('The inspected area has a separately recorded local condition. '*55)
        self.store.save(self.project);result=self.store.export(self.project['id'])
        report=self.store.path/'exports'/(result['id']+'.docx');sample=QA/'generated-sample.docx';sample.write_bytes(report.read_bytes())
        with zipfile.ZipFile(report) as z,zipfile.ZipFile(RESOURCES/'report_template.docx') as template:
            for name in ['word/styles.xml','word/numbering.xml','word/theme/theme1.xml']:
                self.assertEqual(z.read(name),template.read(name))
            doc=E.fromstring(z.read('word/document.xml'));before=E.fromstring(template.read('word/document.xml'))
            reference=ROOT/'reference_reports/REVA/1_19_Dempster_Street/12477-SIR-004_REVA-Town of Port Hedland-1 19 Dempster Street.docx'
            source=None
            try:
                with zipfile.ZipFile(reference) as original:source=E.fromstring(original.read('word/document.xml'))
            except PermissionError:
                snapshot=QA/'layout-reference-snapshot.docx'
                inventory=json.loads((QA/'template_inventory.json').read_text(encoding='utf-8'))
                self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(),inventory['sha256'])
                with zipfile.ZipFile(snapshot) as original:source=E.fromstring(original.read('word/document.xml'))
            except FileNotFoundError:
                pass  # Historical reports remain local and are not required in a clone.
            cover_source=source if source is not None else before
            self.assertEqual(len(doc.find('w:body',NS)[1].xpath('.//w:drawing',namespaces=NS)),len(cover_source.find('w:body',NS)[1].xpath('.//w:drawing',namespaces=NS)))
            self.assertEqual([E.tostring(n) for n in doc.xpath('.//w:sectPr',namespaces=NS)],[E.tostring(n) for n in before.xpath('.//w:sectPr',namespaces=NS)])
            text=''.join(doc.xpath('.//w:t/text()',namespaces=NS))
            self.assertIn(self.project['items'][0]['observation'],text);self.assertIn('Prototype Layout Test',text)
            for old in ['1/19 Dempster Street','Salman Agherdien','15 July 2025','The most significant corrosion','{{']:
                self.assertNotIn(old,text)
            self.assertEqual(len([n for n in z.namelist() if n.startswith('word/media/inspection-')]),5)
            self.assertEqual(len(doc.xpath('.//w:tblPr/w:tblCaption[@w:val="InspectionItems"]',namespaces=NS)),2)
            self.assertNotIn(' DATE ',''.join(doc.xpath('.//w:instrText/text()',namespaces=NS)))
            # Compare against the retained source, rather than only the prepared
            # template: a wrong prototype can otherwise satisfy its own checks.
            main=source.find('w:body',NS)[34] if source is not None else before.xpath('.//w:tbl[w:tblPr/w:tblCaption[@w:val="InspectionItems"]]',namespaces=NS)[0]
            inspection=doc.xpath('.//w:tbl[w:tblPr/w:tblCaption[@w:val="InspectionItems"]]',namespaces=NS)
            for table in inspection:
                self.assertEqual(table.xpath('./w:tblPr/w:tblW/@w:w',namespaces=NS),main.xpath('./w:tblPr/w:tblW/@w:w',namespaces=NS))
                self.assertEqual(table.xpath('./w:tblPr/w:tblW/@w:w',namespaces=NS),['9771'])
                self.assertEqual(table.xpath('./w:tblGrid/w:gridCol/@w:w',namespaces=NS),['703','3259','5809'])
                for p in table.xpath('./w:tr[6]/w:tc[3]/w:p',namespaces=NS):
                    self.assertEqual(p.xpath('./w:pPr/w:jc/@w:val',namespaces=NS),['left'])
            main_section=doc.xpath('.//w:sectPr',namespaces=NS)[3]
            self.assertEqual(main_section.xpath('./w:type/@w:val',namespaces=NS),['nextPage'])
            if source is not None:
                self.assertEqual(E.tostring(main_section.find('w:pgMar',NS)),E.tostring(source.xpath('.//w:sectPr',namespaces=NS)[3].find('w:pgMar',NS)))
            self.assertEqual(main_section.xpath('./w:pgMar/@w:left',namespaces=NS),['993'])
            self.assertEqual(main_section.xpath('./w:pgMar/@w:right',namespaces=NS),['849'])
            wp={'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}
            widths=doc.xpath('.//wp:inline/wp:extent/@cx',namespaces=wp)
            self.assertTrue(all(abs(int(w)-3259*635)<=1 for w in widths))

    def test_invalid_photo_missing_fields_and_path_rejected(self):
        with self.assertRaises(Exception):self.store.upload(b'not an image','bad.heic')
        with self.assertRaises(ValueError):self.store.load('../other')
        with self.assertRaises(ValueError):self.store.export(self.project['id'])
        ph=self.store.upload(image_bytes(),'sample.jpg');i=self.item([ph]);i['element']='';self.project['items']=[i]
        with self.assertRaises(ValueError):self.store.save(self.project)

if __name__=='__main__':unittest.main(verbosity=2)
