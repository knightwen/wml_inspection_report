import sys,json,shutil,hashlib,argparse
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'workbench'))
from report_engine import prepare_template
target=root/'workbench/resources';target.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--reference');args=parser.parse_args()
source=Path(args.reference) if args.reference else root/'reference_reports/REVA/1_19_Dempster_Street/12477-SIR-004_REVA-Town of Port Hedland-1 19 Dempster Street.docx'
inventory=json.loads((root/'.build/qa/template_inventory.json').read_text(encoding='utf-8'))
assert hashlib.sha256(source.read_bytes()).hexdigest()==inventory['sha256']
prepare_template(source,target/'report_template.docx')
data=json.loads((root/'analysis/word_library_workbook_data.json').read_text(encoding='utf-8'))
library={key:[{'id':r[0],'text':r[2],'elements':r[3],'frequency':r[4]} for r in rows if r[1]=='是'] for key,rows in data['library'].items()}
(target/'library.json').write_text(json.dumps(library,ensure_ascii=False),encoding='utf-8')
# Keep all original menu variants until the user reviews their consolidation.
shutil.copyfile(root/'analysis/dropdown_options.json',target/'options.json')
shutil.copyfile(root/'outputs/word_library_20261010/报告文字库_精简初稿.xlsx',target/'word_library.xlsx')
print(json.dumps({'library_counts':{k:len(v) for k,v in library.items()},'template_bytes':(target/'report_template.docx').stat().st_size}))
