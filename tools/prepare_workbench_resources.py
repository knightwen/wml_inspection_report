import sys,json,shutil,hashlib,argparse
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'workbench'))
from report_engine import prepare_template
from ratings import DEFAULT_RATING_OPTIONS
target=root/'workbench/resources';target.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--reference');args=parser.parse_args()
source=Path(args.reference) if args.reference else root/'reference_reports/REVA/1_19_Dempster_Street/12477-SIR-004_REVA-Town of Port Hedland-1 19 Dempster Street.docx'
inventory=json.loads((root/'.build/qa/template_inventory.json').read_text(encoding='utf-8'))
assert hashlib.sha256(source.read_bytes()).hexdigest()==inventory['sha256']
prepare_template(source,target/'report_template.docx')
data=json.loads((root/'analysis/word_library_workbook_data.json').read_text(encoding='utf-8'))
library={key:[{'id':r[0],'text':r[2],'elements':r[3],'frequency':r[4]} for r in rows if r[1]=='是' and r[4]>=2] for key,rows in data['library'].items()}
(target/'library.json').write_text(json.dumps(library,ensure_ascii=False),encoding='utf-8')
# Keep the reviewed ratings when rebuilding resources from historical reports.
options=json.loads((root/'analysis/dropdown_options.json').read_text(encoding='utf-8'))
options.update(DEFAULT_RATING_OPTIONS)
(target/'options.json').write_text(json.dumps(options,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Rebuild the matching common Excel workbook with tools/build_common_word_library.mjs; do not copy the historical full workbook.')
print(json.dumps({'library_counts':{k:len(v) for k,v in library.items()},'template_bytes':(target/'report_template.docx').stat().st_size}))
