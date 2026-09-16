"""Check the committed layout. Never rewrite templates or overwrite edited assets."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
REQUIRED=['assets.py','app.py','adviser.py','design.py','store.py','pilot.py','static/task.js','static/style.css']
REQUIRED += ['templates/'+name+'.html' for name in ['base','consent','instructions','task','debrief','researcher','researcher_login','unlock','rate']]
def main():
    missing=[name for name in REQUIRED if not (HERE/name).is_file()]
    if missing:raise SystemExit('Missing files: '+', '.join(missing))
    print('Layout verified. Existing templates and static assets were not modified.')
if __name__=='__main__':main()
