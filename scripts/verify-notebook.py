"""Execute every code cell without rewriting the notebook or its evidence."""
import json,os,sys,traceback
from pathlib import Path
if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8')
root=Path(__file__).resolve().parents[1]
notebook=root/'notebooks/XAI_Compress_Model_Analysis.ipynb'
os.environ.setdefault('MPLBACKEND','Agg')
namespace={'__name__':'__notebook_validation__','display':lambda value: print(value)}
old=Path.cwd();os.chdir(root)
try:
    data=json.loads(notebook.read_text(encoding='utf-8'))
    for index,cell in enumerate(data['cells']):
        if cell.get('cell_type')!='code':continue
        try:exec(compile(''.join(cell.get('source',[])),f'{notebook.name}:cell-{index}','exec'),namespace)
        except Exception:
            print(f'NOTEBOOK_CELL_{index}=FAIL',file=sys.stderr);traceback.print_exc();raise
    print('NOTEBOOK_EXECUTION=PASS')
finally:os.chdir(old)
