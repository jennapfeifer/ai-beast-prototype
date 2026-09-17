"""Count/geometry preservation, smoother raster, protected delivery and version audit."""
import hashlib
import io
from PIL import Image
import pytest
import app as A
import assets
import design
import store
from stimuli import dot_positions, generate_dot_stimulus, STIMULUS_RENDER_VERSION
from conftest import start,finish_trial
from pilot import build_report

LEGACY_SHA={32:'70d3119a9e799f94404b13534cf5b95d079426c73b0f046e6d2ccc689962b23f',
            144:'4abfcd341b1e20cd4279fc7921e7d9952477108490c6296a0c8476535b4c8384',
            256:'65a42d6c73164f0aef05c697383a9cf465c0fdcc5fcf1ca87c42b0a40f7a7196'}


@pytest.mark.parametrize('count',[32,144,256])
def test_legacy_raster_remains_identical_and_smooth_raster_keeps_centres(tmp_path,count):
    seed=design.stable_seed(f'stimulus|{design.STUDY_SEED}|N{count}|V1')
    old=tmp_path/'legacy.png';new=tmp_path/'smooth.png'
    generate_dot_stimulus(old,count,seed)
    assert hashlib.sha256(old.read_bytes()).hexdigest()==LEGACY_SHA[count]
    generate_dot_stimulus(new,count,seed,pixel_ratio=2,supersample=4)
    with Image.open(old) as legacy,Image.open(new) as smooth:
        assert smooth.size==(1024,1024) and legacy.size==(512,512)
        points=dot_positions(count,seed)
        assert len(points)==count and all(legacy.getpixel((x,y))==(0,0,0) and smooth.getpixel((2*x,2*y))==(0,0,0) for x,y in points)
        assert any(0<colour[0]<255 for _,colour in smooth.getcolors(1024*1024))
        assert len(legacy.getcolors())==2
    before=new.read_bytes()
    generate_dot_stimulus(new,count,seed,pixel_ratio=2,supersample=4,force=True)
    assert new.read_bytes()==before


def test_dense_render_contains_exactly_the_requested_number_of_connected_dots(tmp_path):
    path=tmp_path/'dense.png'
    generate_dot_stimulus(path,256,321,pixel_ratio=2,supersample=4)
    with Image.open(path) as image:
        width,height=image.size
        pixels=bytearray(value<128 for value in image.convert('L').tobytes())
    components=0
    for i in range(len(pixels)):
        if not pixels[i]:continue
        components+=1;pixels[i]=0;stack=[i]
        while stack:
            point=stack.pop();x=point%width
            neighbours=[point-width,point+width]
            if x:neighbours.append(point-1)
            if x<width-1:neighbours.append(point+1)
            for neighbour in neighbours:
                if 0<=neighbour<len(pixels) and pixels[neighbour]:pixels[neighbour]=0;stack.append(neighbour)
    assert components==256


def test_versioned_images_stay_protected_and_filename_does_not_reveal_count(client):
    state=start(client,['C5'],trials=1,skip=True)
    response=client.get(state['image'])
    assert response.status_code==200
    assert response.headers['Content-Disposition']=='inline; filename=dot-field.webp'
    assert Image.open(io.BytesIO(response.data)).size==(1024,1024)
    assert client.get('/static/stimuli/'+STIMULUS_RENDER_VERSION+'/N256_V1.png').status_code==404
    assert client.get('/stimulus/not-the-current-token').status_code==404
    finish_trial(client,state)
    assert client.get(state['image']).status_code==404
    row=store.diagnostic_rows()[0]
    assert row['ui_version']==A.APP_VERSION and row['stimulus_render_version']==STIMULUS_RENDER_VERSION
    assert A.APP_VERSION=='fieldwork-2.10.1-marker-layer'
    assert b'stimulus_render_version' in client.get('/admin/export/diagnostics.csv').data


def test_versions_are_not_pooled_in_model_comparisons():
    base=dict(condition_id='C5',pid='test',history_rows=0,expected_history_rows=0)
    rows=[dict(base,ui_version='old',stimulus_render_version='legacy'),
          dict(base,ui_version='new',stimulus_render_version='legacy'),
          dict(base,ui_version='new',stimulus_render_version='dots-aa-v1')]
    groups=build_report(rows,[])['model_conditions']
    assert len(groups)==3


def test_new_ui_loads_before_task_runner_and_dark_surface_is_task_only(client):
    start(client,['C5'],trials=1,skip=True)
    task=client.get('/task').get_data(as_text=True)
    assert task.index('/static/estimate.js')<task.index('/static/task.js')
    assert 'class="task-surface"' in task and 'class="task-heading sr-only"' in task
    assert 'class="task-surface"' not in client.get('/researcher').get_data(as_text=True)
