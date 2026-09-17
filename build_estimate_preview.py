"""Build a self-contained, API-free preview using the actual estimate JS and CSS."""
from pathlib import Path
import argparse

HERE=Path(__file__).resolve().parent


def build(out):
    css=(HERE/'static'/'style.css').read_text()
    js=(HERE/'static'/'estimate.js').read_text().replace('</script','<\\/script')
    runner=(HERE/'static'/'task.js').read_text().rsplit('\nrun().catch',1)[0].replace('</script','<\\/script')
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BEAST · Estimate preview</title><style>'''+css+'''
.preview-tools{display:flex;gap:10px;flex-wrap:wrap;padding:16px 5%;align-items:center;border-bottom:1px solid #35404a}
.preview-tools button{background:#222a32;color:#edf2f7;border:1px solid #73808b;border-radius:4px;padding:8px 12px;font-size:14px}
.preview-tools span{font-size:14px;color:#bac2cc;margin-right:auto}
.advice-focus .preview-tools,.advice-focus #preview-result{display:none}\n#preview-result{color:#bac2cc;text-align:center;font-size:16px;padding:12px}
</style><body class="task-surface"><nav class="preview-tools" aria-label="Preview controls">
<span>Preview · synthetic values · nothing saved</span><button data-mode="first">First estimate</button><button data-mode="final">Final estimate</button><button data-mode="equal">Same values</button><button data-mode="timed">5-second advice</button></nav>
<div id="phase-name" class="sr-only"></div><div id="visibility-cover" class="visibility-cover" hidden><p>Return to this tab to continue.</p></div><main class="task-page"><section class="card trial-card"><div id="stage"></div></section><p id="preview-result" role="status"></p></main>
<script>'''+js+'''
window.BEAST_CFG={max_estimate:400,advice_preview_ms:location.hash==='#timed'?5000:0};
window.fetch=()=>Promise.reject(Error('This offline preview cannot make API requests.'));
'''+runner+'''
const previewMode=location.hash.slice(1)||'final';
document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>{location.hash=button.dataset.mode;location.reload();});
const previewRun=previewMode==='first'?initialEstimator():showAdvice({estimate:151},{advice_number:previewMode==='equal'?151:160,advice_text:'I would use that estimate for the display.'});
previewRun.then(result=>{document.getElementById('preview-result').textContent='Confirmed '+result.estimate+'. This preview does not save responses.';});
// Synthetic illustration only. Real pilot final choices always start at the first estimate.
if(previewMode==='final'){const input=document.getElementById('est');input.value=119;input.oninput();}
</script></body></html>'''
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(html)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default=str(HERE/'validation'/'estimate-preview.html'))
    print(build(parser.parse_args().out))
