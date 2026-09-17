from pathlib import Path
from PIL import Image
import assets
import app as A
import store
from stimuli import generate_dot_stimulus
from conftest import start,post,finish_trial
from pilot import build_report,timing_projection


def test_all_lossless_webp_images_match_png_pixels_and_reduce_total_transfer():
    pngs=sorted(assets.STIMULUS_DIR.glob('*.png'))
    assert len(pngs)==105
    original=compressed=0
    for png in pngs:
        webp=png.with_suffix('.webp')
        with Image.open(png) as a,Image.open(webp) as b:
            assert a.size==b.size==(1024,1024)
            assert a.convert('RGB').tobytes()==b.convert('RGB').tobytes(),png.name
        original+=png.stat().st_size;compressed+=webp.stat().st_size
    assert compressed<original*.3


def test_interrupted_image_is_rebuilt_and_webp_is_repaired(tmp_path):
    png=tmp_path/'example.png';png.write_bytes(b'')
    generate_dot_stimulus(png,32,123,pixel_ratio=2,supersample=4)
    assets.ensure_webp(png)
    webp=png.with_suffix('.webp');webp.write_bytes(b'corrupt')
    assets.ensure_webp(png)
    with Image.open(png) as a,Image.open(webp) as b:assert a.tobytes()==b.convert('RGB').tobytes()
    assert not list(tmp_path.glob('*.tmp'))


def test_researcher_preview_choice_is_pinned_and_exported(client):
    post(client,'/researcher',data={'token':'researcher-test'})
    response=post(client,'/start',data=dict(consent='yes',researcher_test='1',conditions=['C5'],
                adviser_mode='offline',trials='1',skip_practice='1',advice_preview_ms='3000'))
    assert response.status_code==302
    state=client.get('/api/state').get_json()
    with client.session_transaction() as cookie:pid=cookie['pid']
    assert store.session_data(pid)['config']['advice_preview_ms']==3000
    assert '"advice_preview_ms": 3000' in client.get('/task').get_data(as_text=True)
    assert 'appears alone for 3 seconds' in client.get('/instructions').get_data(as_text=True)
    finish_trial(client,state)
    row=store.diagnostic_rows(pid)[0]
    assert row['advice_preview_target_ms']==3000 and row['stimulus_format']=='webp_lossless'
    assert b'advice_preview_target_ms' in client.get('/admin/export/model_comparison.csv').data


def test_participant_cannot_enable_preview_from_start_form(client):
    assert post(client,'/start',data={'consent':'yes','advice_preview_ms':'3000'}).status_code==302
    with client.session_transaction() as cookie:pid=cookie['pid']
    assert store.session_data(pid)['config']['advice_preview_ms']==A.ADVICE_PREVIEW_MS


def test_invalid_researcher_preview_rejected(client):
    post(client,'/researcher',data={'token':'researcher-test'})
    response=post(client,'/start',data={'consent':'yes','researcher_test':'1','advice_preview_ms':'1000'})
    assert response.status_code==400


def test_preview_modes_not_pooled_and_planning_includes_extra_exposure():
    base=dict(condition_id='C5',pid='test',history_rows=0,expected_history_rows=0)
    assert len(build_report([dict(base,advice_preview_target_ms=0),dict(base,advice_preview_target_ms=3000)],[])['model_conditions'])==2
    assert abs(timing_projection(advice_preview_s=3)['minutes']-timing_projection()['minutes']-5.25)<.11


def test_intro_consistent_and_end_summary_copy_matches_setting(client,monkeypatch):
    for show in [True,False]:
        monkeypatch.setattr(A,'SHOW_END_SCORE',show)
        html=client.get('/').get_data(as_text=True)
        assert 'task-surface info-surface' in html
        assert ('overall accuracy summary' in html)==show
        assert 'measuring the study duration' not in html and 'assistant’s recommendations' not in html
    start(client,['C5'],skip=True,trials=1)
    html=client.get('/instructions').get_data(as_text=True)
    assert 'First estimate' in html and 'Final estimate' in html and 'blue AI advice' in html
    assert 'keep this tab visible' not in html.lower() and 'type your' not in html
    assert 'switch tabs or minimise' in html
