import sys, unittest, tempfile, json, zipfile, hashlib, secrets
from io import BytesIO
from pathlib import Path
from PIL import Image
import pillow_heif
from lxml import etree as E
from unittest.mock import patch
from app import Store, RESOURCES, read_library_xlsx, library_digest, LIBRARY_POLICY, atomic_json
from report_engine import NS, generate_report, normalize_package, q, xml, child

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'.build/qa'

def image_bytes(size=(800,600),mode='JPEG'):
    image=Image.new('RGB',size,(173,197,157));out=BytesIO()
    image.save(out,mode);return out.getvalue()

class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        QA.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=QA);self.store=Store(self.tmp.name);self.project=self.store.new()

    def tearDown(self):self.store.previews.close();self.tmp.cleanup()

    def test_cover_combines_project_and_report_numbers_without_duplicate_prefix(self):
        self.project['items']=[self.item([self.store.upload(image_bytes(),'cover.jpg')])]
        self.project['metadata'].update(site='Cover QA',project_number='12477',document_name='Custom document name')
        with zipfile.ZipFile(RESOURCES/'report_template.docx') as z:
            parts={name:z.read(name) for name in z.namelist()}
        original=E.fromstring(parts['word/document.xml']).find('w:body',NS)[1]
        # Exercise both the current template and the report-only marker in older templates.
        for marker in ['{{report_reference}}','{{report_number}}']:
            doc=E.fromstring(parts['word/document.xml'])
            doc.find('w:body',NS)[1].find('.//w:t',NS).text=marker
            legacy_template=Path(self.tmp.name)/'cover-template.docx'
            with zipfile.ZipFile(legacy_template,'w') as z:
                for name,data in parts.items():z.writestr(name,xml(doc) if name=='word/document.xml' else data)
            for number in ['SIR-004','12477-SIR-004','  SIR-004  ']:
                with self.subTest(marker=marker,number=number):
                    self.project['metadata']['report_number']=number
                    target=Path(self.tmp.name)/'cover.docx'
                    generate_report(legacy_template,self.project,self.store.photo_path,target)
                    with zipfile.ZipFile(target) as z:
                        body=E.fromstring(z.read('word/document.xml')).find('w:body',NS)
                        cover=body[1]
                        self.assertEqual(''.join(cover.xpath('.//w:t/text()',namespaces=NS)),'12477-SIR-004')
                        self.assertEqual(E.tostring(cover.find('w:pPr',NS)),E.tostring(original.find('w:pPr',NS)))
                        self.assertEqual(E.tostring(cover.find('w:r/w:rPr',NS)),E.tostring(original.find('w:r/w:rPr',NS)))
                        self.assertIn('12477',body[5].xpath('.//w:t/text()',namespaces=NS))
                        self.assertIn('Custom document name',body[5].xpath('.//w:t/text()',namespaces=NS))
                        self.assertEqual(z.read('word/styles.xml'),parts['word/styles.xml'])
                    self.assertEqual(self.project['metadata']['report_number'],number)

    def test_cost_rows_decimal_export_and_backup(self):
        from costs import amount
        rows=[{'description':'Repair steel','quantity':'3','unit':'each','rate':'0.335','priority':'High'},{'description':'Clean','quantity':'2.5','unit':'m2','rate':'100','priority':'Low'}]
        self.assertEqual(str(amount(rows[0])),'1.01')
        self.project['cost_rows']=rows
        self.project['items']=[self.item([self.store.upload(image_bytes(),'costs.jpg')])]
        self.project['metadata'].update(site='Costs QA',report_number='QA-COSTS',project_number='QA')
        saved=self.store.save(self.project)
        self.assertEqual(self.store.restore(self.store.backup(saved['id']))['cost_rows'],rows)
        exported=self.store.export(saved['id'])
        with zipfile.ZipFile(self.store.path/'exports'/(exported['id']+'.docx')) as z:
            doc=E.fromstring(z.read('word/document.xml'))
            self.assertIn('251.01',doc.xpath('//w:t/text()',namespaces=NS))
            self.assertIn('Repair steel',doc.xpath('//w:t/text()',namespaces=NS))
        for value in ['-1','NaN','Infinity','1000000001','0.0000001']:
            saved['cost_rows'][0]['rate']=value
            with self.assertRaises(ValueError):self.store.save(saved)

    def test_sections_save_copy_backup_and_word(self):
        text={key:key+' first paragraph.\n\nSecond paragraph.' for key in ['introduction','remedial_works','conclusion','cost_estimate']}
        self.project['sections']=text.copy()
        photo=self.store.upload(image_bytes(),'sections.jpg');self.project['items']=[self.item([photo])]
        self.project['metadata'].update(site='Sections QA',report_number='QA-SECTIONS',project_number='QA')
        saved=self.store.save(self.project)
        self.assertEqual(self.store.load(saved['id'])['sections'],text)
        self.assertEqual(self.store.copy_project(saved)['sections'],text)
        self.assertEqual(self.store.restore(self.store.backup(saved['id']))['sections'],text)
        exported=self.store.export(saved['id'])
        with zipfile.ZipFile(self.store.path/'exports'/(exported['id']+'.docx')) as z, zipfile.ZipFile(RESOURCES/'report_template.docx') as template:
            body=E.fromstring(z.read('word/document.xml')).find('w:body',NS)
            original=E.fromstring(template.read('word/document.xml')).find('w:body',NS)
            for key,label in [('introduction','introduction'),('remedial_works','recommended remedial works'),('conclusion','conclusion'),('cost_estimate','cost estimate')]:
                anchor=next(p for p in body.findall('w:p',NS) if ''.join(p.xpath('.//w:t/text()',namespaces=NS)).strip().casefold()==label)
                source=next(p for p in original.findall('w:p',NS) if ''.join(p.xpath('.//w:t/text()',namespaces=NS)).strip().casefold()==label)
                self.assertEqual(E.tostring(anchor),E.tostring(source))
                self.assertEqual(''.join(anchor.getnext().xpath('.//w:t/text()',namespaces=NS)),key+' first paragraph.')
            self.assertEqual(z.read('word/styles.xml'),template.read('word/styles.xml'))
            self.assertEqual(E.tostring(body.find('w:sectPr',NS)),E.tostring(original.find('w:sectPr',NS)))

    def test_legacy_sections_and_validation(self):
        self.project.pop('sections');path=self.store.path_for_project(self.project['id']);atomic_json(path,self.project)
        before=path.read_bytes();self.assertEqual(self.store.load(self.project['id'])['sections']['introduction'],'');self.assertEqual(path.read_bytes(),before)
        for value in [None,[],{'introduction':1},{'introduction':'x'*60001}]:
            self.project['sections']=value
            with self.assertRaises(ValueError):self.store.save(self.project)

    def test_preview_conversion_failure_preserves_draft(self):
        from preview import PreviewManager
        import time
        photo=self.store.upload(image_bytes(),'preview.jpg')
        self.project['items']=[self.item([photo])]
        self.project['metadata'].update(site='Preview',report_number='PREVIEW',project_number='TEST')
        saved=self.store.save(self.project)
        before=self.store.path_for_project(saved['id']).read_bytes()
        for message in ['转换超时','Microsoft Word 不可用']:
            def failing(*args):raise ValueError(message)
            manager=PreviewManager(self.store,RESOURCES,converter=failing,capability=lambda:{'available':True})
            job=manager.start(self.store.report_snapshot(saved['id']))
            for _ in range(200):
                state=manager.get(job['id'])
                if state['status']=='failed':break
                time.sleep(.01)
            self.assertEqual(state['status'],'failed');self.assertIn(message,state['error']);manager.close()
        self.assertEqual(before,self.store.path_for_project(saved['id']).read_bytes())

    def test_manual_person_does_not_inherit_qualifications(self):
        person=self.store.personnel['people'][0]
        self.project['metadata'].update(prepared_by='Selected Person',prepared_by_id=person['id'],author_qualifications='OLD QUALIFICATION',author_title='OLD TITLE',site='Manual person',report_number='QA-PERSON',project_number='QA')
        photo=self.store.upload(image_bytes(),'person.jpg');self.project['items']=[self.item([photo])]
        saved=self.store.save(self.project);edited=json.loads(json.dumps(saved))
        edited['metadata'].update(prepared_by='Manual Person',prepared_by_id='')
        saved=self.store.save(edited)
        self.assertEqual(saved['metadata']['author_qualifications'],'');self.assertEqual(saved['metadata']['author_title'],'')
        export=self.store.export(saved['id'])
        with zipfile.ZipFile(self.store.path/'exports'/(export['id']+'.docx')) as z:
            text=z.read('word/document.xml').decode()
        self.assertIn('Manual Person',text);self.assertNotIn('OLD QUALIFICATION',text);self.assertNotIn('OLD TITLE',text)
        self.assertEqual(self.store.personnel['people'][0],person)

    def test_conflict_copy_and_unsaved_backup_preserve_all_edits(self):
        from app import RevisionConflict
        photo=self.store.upload(image_bytes(),'conflict.jpg');self.project['items']=[self.item([photo])]
        saved=self.store.save(self.project);local=json.loads(json.dumps(saved));remote=json.loads(json.dumps(saved))
        remote['metadata']['site']='Remote saved';self.store.save(remote)
        local['metadata']['site']='Local unsaved';local['editor']['subitems'][0]['observation']='Pending editor text';local['items'][0]['subitems'][0]['observation']='Changed item'
        with self.assertRaises(RevisionConflict):self.store.save(local)
        copied=self.store.copy_project(local)
        self.assertNotEqual(copied['id'],local['id']);self.assertEqual(copied['revision'],0)
        self.assertEqual(self.store.load(local['id'])['metadata']['site'],'Remote saved')
        restored=self.store.restore(self.store.backup_snapshot(local))
        self.assertEqual(restored['metadata']['site'],'Local unsaved');self.assertEqual(restored['editor']['subitems'][0]['observation'],'Pending editor text')
        self.assertEqual(restored['items'][0]['subitems'][0]['observation'],'Changed item')
        with Image.open(self.store.photo_path(restored['items'][0]['subitems'][0]['photos'][0]['id'])) as image:self.assertEqual(image.size,(800,600))

    def test_preview_snapshot_does_not_block_save(self):
        from preview import PreviewManager
        import threading,time
        entered=threading.Event();release=threading.Event()
        def converter(source,resources,cancel):
            entered.set();release.wait(3);pdf=source.with_suffix('.pdf');pdf.write_bytes(b'%PDF-test');return pdf
        def renderer(pdf,source,progress,cancel):progress(1,2);progress(2,2);return 2
        manager=PreviewManager(self.store,RESOURCES,converter=converter,renderer=renderer,capability=lambda:{'available':True})
        photo=self.store.upload(image_bytes(),'snapshot.jpg');self.project['items']=[self.item([photo])]
        self.project['metadata'].update(site='Before preview',report_number='SNAPSHOT',project_number='QA');saved=self.store.save(self.project)
        job=manager.start(self.store.report_snapshot(saved['id']));self.assertTrue(entered.wait(3))
        try:
            start=time.monotonic();saved['metadata']['site']='After preview';self.store.save(saved)
            self.assertLess(time.monotonic()-start,.5)
            self.assertEqual(manager.get(job['id'])['status'],'converting')
        finally:release.set()
        for _ in range(200):
            result=manager.get(job['id'])
            if result['status'] in ['ready','failed']:break
            time.sleep(.01)
        self.assertEqual(result['status'],'ready');self.assertEqual(result['pages'],2)
        with zipfile.ZipFile(self.store.path/'exports'/(result['report_id']+'.docx')) as z:text=z.read('word/document.xml').decode()
        self.assertIn('Before preview',text);self.assertNotIn('After preview',text);manager.close()

    def test_no_word_preview_still_allows_docx(self):
        from preview import PreviewManager
        photo=self.store.upload(image_bytes(),'no-word.jpg');self.project['items']=[self.item([photo])]
        self.project['metadata'].update(site='No Word',report_number='NOWORD',project_number='QA');self.store.save(self.project)
        manager=PreviewManager(self.store,RESOURCES,capability=lambda:{'available':False,'reason':'Microsoft Word not installed'})
        with self.assertRaisesRegex(ValueError,'not installed'):manager.start(self.store.report_snapshot(self.project['id']))
        self.assertTrue((self.store.path/'exports'/(self.store.export(self.project['id'])['id']+'.docx')).exists())

    def test_conversion_timeout_cleans_only_owned_session(self):
        from preview import convert_word_pdf
        import threading
        process=unittest.mock.Mock();process.poll.side_effect=[None,0];process.communicate.return_value=(b'',b'')
        with patch('preview.subprocess.Popen',return_value=process),patch('preview.cleanup_owned_word') as cleanup:
            with self.assertRaisesRegex(ValueError,'超时'):convert_word_pdf(self.store.path/'timeout.docx',RESOURCES,threading.Event(),timeout=-1)
        process.kill.assert_called_once();cleanup.assert_called_once_with(self.store.path/'timeout.word-owner.json')

    def test_word_cleanup_checks_ownership_process_identity_and_creation_time(self):
        from preview import cleanup_owned_word
        owner=self.store.path/'owned-session.json'
        for owned,created,image,terminate in [(True,123,'WINWORD.EXE',True),(True,456,'WINWORD.EXE',False),(True,123,'other.exe',False),(False,123,'WINWORD.EXE',False)]:
            owner.write_text(json.dumps({'owned':owned,'pid':42,'creation_time':'123'}),encoding='utf-8')
            kernel=unittest.mock.Mock();kernel.OpenProcess.return_value=99
            def get_times(handle,creation,*args):creation._obj.value=created;return True
            def get_name(handle,flags,name,size):name.value='C:/Program Files/'+image;return True
            kernel.GetProcessTimes.side_effect=get_times;kernel.QueryFullProcessImageNameW.side_effect=get_name
            with patch('preview.ctypes.WinDLL',return_value=kernel) as library:cleanup_owned_word(owner)
            self.assertEqual(kernel.TerminateProcess.called,terminate)
            if owned:kernel.CloseHandle.assert_called_once_with(99)
            else:library.assert_not_called()

    def item(self,photos):
        return {'id':secrets.token_hex(16),'element':'Columns','condition_rating':'5. Major deterioration',
                'likelihood':'Likely','severity':'Significant','priority':'Critical',
                'subitems':[{'id':secrets.token_hex(16),'photos':photos,
                'observation':'Minor corrosion at the lower section. Manual edit: C1 & C2 <test>.',
                'recommendation':'Clean, wire brush and repaint.'}]}

    def test_subitems_share_ratings_and_merge_only_their_own_photos(self):
        photos=[self.store.upload(image_bytes(),f'group-{i}.jpg') for i in range(4)]
        item=self.item([photos[0]])
        item['subitems'][0].update(observation='Overview of the columns.',recommendation='')
        item['subitems'] += [
            {'id':secrets.token_hex(16),'photos':photos[1:3],'observation':'Corrosion at Column 1.','recommendation':'Clean and repaint Column 1.'},
            {'id':secrets.token_hex(16),'photos':photos[3:],'observation':'Column 2 is in good condition.','recommendation':''}]
        self.project['items']=[item]
        self.project['metadata'].update(site='Subitem merge QA',report_number='QA-SUBITEM',project_number='QA')
        saved=self.store.save(self.project)
        backup=self.store.restore(self.store.backup(saved['id']))
        self.assertEqual([len(g['photos']) for g in backup['items'][0]['subitems']],[1,2,1])
        self.assertEqual([g['observation'] for g in backup['items'][0]['subitems']],[g['observation'] for g in item['subitems']])
        self.assertTrue(all(g['photos'][0]['id']!=old['photos'][0]['id'] for g,old in zip(backup['items'][0]['subitems'],item['subitems'])))
        exported=self.store.export(saved['id'])
        report=self.store.path/'exports'/(exported['id']+'.docx')
        with zipfile.ZipFile(report) as package:
            doc=E.fromstring(package.read('word/document.xml'))
            table=doc.xpath('.//w:tbl[w:tblPr/w:tblCaption/@w:val="InspectionItems"]',namespaces=NS)[0]
            rows=table.findall('w:tr',NS);self.assertEqual(len(rows),9)
            self.assertEqual([''.join(row.findall('w:tc',NS)[0].itertext()) for row in rows[5:]],['1.1','1.2','1.3','1.4'])
            merges=[row.findall('w:tc',NS)[2].find('w:tcPr/w:vMerge',NS) for row in rows[5:]]
            self.assertEqual([node.get(q('val')) if node is not None else None for node in merges],[None,'restart','continue',None])
            text=''.join(table.xpath('.//w:t/text()',namespaces=NS))
            for group in item['subitems']:self.assertEqual(text.count(group['observation']),1)
            self.assertEqual(text.count('CONDITION RATING'),1)
            self.assertEqual(len([n for n in package.namelist() if n.startswith('word/media/inspection-')]),4)
        (QA/'subitems-merged.docx').write_bytes(report.read_bytes())

    def test_legacy_item_migration_is_read_only_and_preserves_content(self):
        photo=self.store.upload(image_bytes(),'legacy.jpg');item=self.item([photo]);group=item.pop('subitems')[0]
        item.update({k:v for k,v in group.items() if k!='id'})
        self.project['items']=[item];self.project['editor']={'photos':[photo],'observation':'Pending old editor','recommendation':'','element':''}
        self.project.pop('schema_version')
        path=self.store.path_for_project(self.project['id']);atomic_json(path,self.project);before=path.read_bytes()
        migrated=self.store.load(self.project['id'])
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(migrated['schema_version'],2)
        self.assertEqual(migrated['items'][0]['subitems'][0]['observation'],group['observation'])
        self.assertEqual(migrated['editor']['subitems'][0]['observation'],'Pending old editor')
        self.assertNotIn('photos',migrated['items'][0])
        restored=self.store.restore(self.store.backup_snapshot(self.project))
        self.assertEqual(restored['editor']['subitems'][0]['observation'],'Pending old editor')

    def test_subitem_validation_allows_incomplete_editor_but_not_saved_item(self):
        photo=self.store.upload(image_bytes(),'validation.jpg');self.project['items']=[self.item([photo])]
        self.project['editor']['subitems'].append({'id':secrets.token_hex(16),'photos':[photo],'observation':'','recommendation':''})
        saved=self.store.save(self.project)
        self.assertEqual(len(self.store.restore(self.store.backup(saved['id']))['editor']['subitems']),2)
        for group in [
            {'id':secrets.token_hex(16),'photos':[],'observation':'Missing photo','recommendation':''},
            {'id':secrets.token_hex(16),'photos':[photo],'observation':'','recommendation':''},
            {**saved['items'][0]['subitems'][0]}]:
            edited=json.loads(json.dumps(saved));edited['items'][0]['subitems'].append(group)
            with self.assertRaises(ValueError):self.store.save(edited)

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
        item=self.item([photo]);item['subitems'][0]['observation']='Unique wording retained in an existing report.'
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

    def test_personnel_edit_persist_conflict_and_report_snapshot(self):
        personnel=json.loads(json.dumps(self.store.personnel));old=json.loads(json.dumps(personnel))
        person=personnel['people'][0]
        person.update(name='Test Engineer',qualifications='BE, CPEng',title='Structural Engineer',roles=['author','reviewer'])
        saved=self.store.save_personnel(personnel)
        self.assertEqual(Store(self.store.path).personnel,saved)
        with self.assertRaises(ValueError):self.store.save_personnel(old)
        self.project['metadata'].update(prepared_by=person['name'],prepared_by_id=person['id'],author_qualifications=person['qualifications'],author_title=person['title'],
                                        reviewed_by=person['name'],reviewed_by_id=person['id'],reviewer_qualifications=person['qualifications'],reviewer_title=person['title'],
                                        site='Personnel Test',report_number='TEST-PEOPLE',project_number='TEST')
        self.project['items']=[self.item([self.store.upload(image_bytes(),'test.jpg')])];self.store.save(self.project)
        edited=json.loads(json.dumps(saved));edited['people'][0]['name']='Renamed Engineer';self.store.save_personnel(edited)
        self.assertEqual(self.store.load(self.project['id'])['metadata'],self.project['metadata'])
        exported=self.store.export(self.project['id'])
        with zipfile.ZipFile(self.store.path/'exports'/(exported['id']+'.docx')) as package:
            text=''.join(E.fromstring(package.read('word/document.xml')).xpath('.//w:t/text()',namespaces=NS))
            for value in ['Test Engineer','BE, CPEng','Structural Engineer']:self.assertIn(value,text)
        empty={'revision':self.store.personnel['revision'],'people':[]};self.store.save_personnel(empty)
        self.assertEqual(Store(self.store.path).personnel['people'],[])
        restored=self.store.restore(self.store.backup(self.project['id']))
        self.assertEqual(restored['metadata'],self.project['metadata'])

    def test_personnel_invalid_input_does_not_change_saved_library(self):
        original=json.loads(json.dumps(self.store.personnel))
        variants=[]
        for patch_values in [{'name':'  '},{'title':'x'*501},{'roles':[]},{'roles':['invalid']},{'id':'../other'}]:
            value=json.loads(json.dumps(original));value['people'][0].update(patch_values);variants.append(value)
        duplicate=json.loads(json.dumps(original));duplicate['people'][1]['name']=duplicate['people'][0]['name'];variants.append(duplicate)
        for value in variants:
            with self.assertRaises(ValueError):self.store.save_personnel(value)
        self.assertEqual(Store(self.store.path).personnel,original)

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
        self.assertEqual(restored['items'][0]['subitems'][0]['observation'],saved['items'][0]['subitems'][0]['observation'])
        self.assertNotEqual(restored['items'][0]['subitems'][0]['photos'][0]['id'],ph['id'])

    def test_reports_template_fidelity_multiphoto_long_text(self):
        photos=[self.store.upload(image_bytes(size),'photo'+str(i)+'.jpg') for i,size in enumerate([(1200,900),(900,1200),(1200,900),(900,1200)],1)]
        self.project['metadata'].update({'site':'Prototype Layout Test','report_number':'TEST-SIR-001','project_number':'TEST','report_date':'2026-10-10','prepared_by':'Test Author','reviewed_by':'Test Reviewer'})
        self.project['items']=[self.item(photos),self.item([photos[0]])]
        self.project['items'][1]['priority']='Low'
        self.project['items'][1]['subitems'][0]['observation']='Long observation for pagination verification. '+('The inspected area has a separately recorded local condition. '*55)
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
            self.assertIn(self.project['items'][0]['subitems'][0]['observation'],text);self.assertIn('Prototype Layout Test',text)
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

    def test_report_repairs_legacy_property_order_and_empty_dates(self):
        # Reproduce the old template's schema errors without using write_package,
        # which now repairs them. XML parsing alone cannot detect this corruption.
        with zipfile.ZipFile(RESOURCES/'report_template.docx') as template:
            parts={name:template.read(name) for name in template.namelist()}
        doc=E.fromstring(parts['word/document.xml'])
        child(doc.xpath('.//w:pPr[w:spacing]',namespaces=NS)[0],'pageBreakBefore',val='false')
        cell_properties=doc.xpath('.//w:tcPr',namespaces=NS)[0]
        child(cell_properties,'tcMar');child(cell_properties,'vAlign',val='top')
        for parent in doc.xpath('.//w:pPr | .//w:rPr | .//w:tcPr',namespaces=NS):
            parent[:]=list(reversed(list(parent)))
        parts['word/document.xml']=xml(doc)
        settings=E.fromstring(parts['word/settings.xml'])
        update=settings.find('w:updateFields',NS);settings.remove(update);settings.append(update)
        parts['word/settings.xml']=xml(settings)
        core=E.fromstring(parts['docProps/core.xml'])
        for name in ['created','modified']:
            node=E.SubElement(core,'{http://purl.org/dc/terms/}'+name)
            node.set('{http://www.w3.org/2001/XMLSchema-instance}type','dcterms:W3CDTF')
        E.SubElement(core,'{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}lastPrinted')
        parts['docProps/core.xml']=xml(core)
        legacy=Path(self.tmp.name)/'legacy-template.docx'
        with zipfile.ZipFile(legacy,'w',zipfile.ZIP_DEFLATED) as package:
            for name,content in parts.items():package.writestr(name,content)
        self.project['metadata'].update(site='Legacy template test',report_number='TEST-REPAIR',project_number='TEST')
        self.project['items']=[self.item([self.store.upload(image_bytes(),'repair.jpg')])]
        report=QA/'legacy-template-regression.docx'
        generate_report(legacy,self.project,self.store.photo_path,report)
        with zipfile.ZipFile(report) as package:
            repaired={name:package.read(name) for name in package.namelist()}
        self.assertEqual(normalize_package(repaired),repaired)
        doc=E.fromstring(repaired['word/document.xml'])
        for path,earlier,later in [('.//w:pPr','keepNext','spacing'),('.//w:pPr','pageBreakBefore','spacing'),
                                    ('.//w:rPr','color','sz'),('.//w:tcPr','tcMar','vAlign')]:
            checked=0
            for parent in doc.xpath(path,namespaces=NS):
                tags=[node.tag for node in parent]
                if q(earlier) in tags and q(later) in tags:
                    self.assertLess(tags.index(q(earlier)),tags.index(q(later)));checked+=1
            self.assertGreater(checked,0)
        settings=E.fromstring(repaired['word/settings.xml']);tags=[node.tag for node in settings]
        self.assertLess(tags.index(q('updateFields')),tags.index(q('compat')))
        core=E.fromstring(repaired['docProps/core.xml'])
        dates=core.findall('{http://purl.org/dc/terms/}created')+core.findall('{http://purl.org/dc/terms/}modified')
        self.assertEqual(len(dates),2)
        for node in dates:self.assertRegex(node.text,r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        self.assertIsNone(core.find('{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}lastPrinted'))
        self.assertIn(self.project['items'][0]['subitems'][0]['observation'],''.join(doc.xpath('.//w:t/text()',namespaces=NS)))
        pr=E.Element(q('pPr'));child(pr,'keepNext');child(pr,'keepNext')
        self.assertEqual(len(pr.findall(q('keepNext'))),1)

    def test_photo_names_optional_preserved_in_backup_and_report(self):
        first=self.store.upload(image_bytes(),'original.jpg');first['caption']='Column A & baseplate'
        second=self.store.upload(image_bytes(),'other.jpg');second['caption']=''
        self.project['metadata'].update(site='Photo names',report_number='TEST-NAMES',project_number='TEST')
        self.project['items']=[self.item([first,second])]
        self.project['items'][0]['severity']='Minor. Review after repainting.'
        self.project['items'][0]['priority']='High. Repair within a month.'
        saved=self.store.save(self.project)
        self.assertEqual(saved['items'][0]['subitems'][0]['photos'][0]['caption'],first['caption'])
        restored=self.store.restore(self.store.backup(saved['id']))
        self.assertEqual([p['caption'] for p in restored['items'][0]['subitems'][0]['photos']],[first['caption'],''])
        self.assertEqual(restored['items'][0]['severity'],self.project['items'][0]['severity'])
        result=self.store.export(saved['id']);report=self.store.path/'exports'/(result['id']+'.docx')
        (QA/'photo-names.docx').write_bytes(report.read_bytes())
        with zipfile.ZipFile(report) as package:
            doc=E.fromstring(package.read('word/document.xml'))
        text=doc.xpath('.//w:t/text()',namespaces=NS)
        self.assertEqual(text.count(first['caption']),1)
        self.assertNotIn('other.jpg',text)
        for invalid in [None,3,'x'*201]:
            edited=json.loads(json.dumps(saved));edited['items'][0]['subitems'][0]['photos'][0]['caption']=invalid
            with self.assertRaises(ValueError):self.store.save(edited)

    def test_crop_annotation_preserves_source_and_survives_backup(self):
        photo=self.store.upload(image_bytes(),'original.jpg')
        source=self.store.photo_path(photo['id']).read_bytes()
        edited=self.store.edit_photo(photo['id'],[{'type':'crop','box':[100,50,700,550]},
                                                {'type':'circle','box':[50,40,250,240]}])
        self.assertNotEqual(edited['id'],photo['id'])
        self.assertEqual(self.store.photo_path(photo['id']).read_bytes(),source)
        self.assertEqual((self.store.path/'originals'/(edited['id']+'.jpg')).read_bytes(),image_bytes())
        with Image.open(self.store.photo_path(edited['id'])) as image:
            self.assertEqual(image.size,(600,500))
            red,green,blue=image.getpixel((150,40));self.assertGreater(red,green+50)
        edited['caption']='Column A';self.project['items']=[self.item([edited])]
        self.project['metadata'].update(site='Photo edit',report_number='QA-EDIT',project_number='QA')
        self.store.save(self.project)
        report=self.store.export(self.project['id'])
        report_file=self.store.path/'exports'/(report['id']+'.docx')
        (QA/'edited-photo.docx').write_bytes(report_file.read_bytes())
        with zipfile.ZipFile(report_file) as package:
            self.assertEqual(package.read('word/media/inspection-1-1.jpg'),self.store.photo_path(edited['id']).read_bytes())
        restored=self.store.restore(self.store.backup(self.project['id']))
        restored_photo=restored['items'][0]['subitems'][0]['photos'][0]
        self.assertEqual(restored_photo['caption'],'Column A')
        self.assertEqual(self.store.photo_path(restored_photo['id']).read_bytes(),self.store.photo_path(edited['id']).read_bytes())
        count=len(self.store.catalog)
        for operations in [[],[{'type':'crop','box':[-1,0,500,400]}],[{'type':'crop','box':[0,0,5,5]}],
                           [{'type':'circle','box':[0,0,900,500]}],[{'type':'crop','box':[0,0,float('nan'),500]}],
                           [{'type':'other','box':[0,0,100,100]}]]:
            with self.assertRaises(ValueError):self.store.edit_photo(photo['id'],operations)
        self.assertEqual(len(self.store.catalog),count)

    def test_photo_markup_rotation_and_invalid_operations(self):
        photo=self.store.upload(image_bytes(),'markup.jpg')
        original=self.store.photo_path(photo['id']).read_bytes()
        edited=self.store.edit_photo(photo['id'],[
            {'type':'rotate','turn':1},
            {'type':'crop','box':[0,0,400,700]},
            {'type':'rectangle','box':[30,30,150,150],'color':'#1677ff','width':10},
            {'type':'arrow','box':[300,300,200,200],'color':'#e32636','width':8},
            {'type':'pen','points':[[20,500],[100,500],[180,550]],'color':'#f5c400','width':12}])
        with Image.open(self.store.photo_path(edited['id'])) as image:
            self.assertEqual(image.size,(400,700))
            r,g,b=image.getpixel((80,33));self.assertGreater(b,r+80)
            r,g,b=image.getpixel((250,250));self.assertGreater(r,g+80)
            r,g,b=image.getpixel((80,500));self.assertGreater(r,b+100)
        self.assertEqual(original,self.store.photo_path(photo['id']).read_bytes())
        count=len(self.store.catalog)
        invalid=[{'type':'rotate','turn':True},{'type':'rotate','turn':2},
                 {'type':'arrow','box':[0,0,800,600]},
                 {'type':'rectangle','box':[0,0,30,30],'color':'bad'},
                 {'type':'circle','box':[0,0,30,30],'width':True},
                 {'type':'pen','points':[[0,0],[float('inf'),10]]},
                 {'type':'pen','points':[[0,0],[800,0]]}]
        for operation in invalid:
            with self.assertRaises(ValueError):self.store.edit_photo(photo['id'],[operation])
        self.assertEqual(count,len(self.store.catalog))

if __name__=='__main__':unittest.main(verbosity=2)
