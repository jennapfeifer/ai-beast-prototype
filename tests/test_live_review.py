from conftest import post

def test_live_review_requires_researcher_session(client):
    assert client.get('/researcher/live-review').status_code==302
    post(client,'/researcher',data={'token':'researcher-test'})
    page=client.get('/researcher/live-review')
    assert page.status_code==200
    assert b'234 generated-message requests' in page.data
    assert b'REVIEW_CONFIG' in page.data
    assert b'researcher-test' not in page.data
