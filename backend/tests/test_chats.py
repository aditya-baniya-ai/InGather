"""Direct conversations unlock only through confirmed meetups; blocks override connections."""
import pytest
from tests.helpers import approve
from tests.test_proposals import flow, accept

pytestmark = pytest.mark.usefixtures('fake_agent')


def confirmed(users, as_user, flow):
    alice, pid = flow
    approve(alice, pid, users['sofia'], users['jordan'])
    accept(as_user, users, pid, 'sofia', 'jordan')
    final = alice.post(f'/api/proposals/{pid}/finalize', {}).json()
    for name in ['alice', 'sofia', 'jordan']:
        out = as_user(users[name]).post(f'/api/proposals/{pid}/confirm', {'version': final['version']})
        assert out.status_code == 200
    return alice, pid


def test_direct_messages_require_full_confirmation_and_stay_private(users, as_user, flow):
    alice, pid = flow
    url = f"/api/chats/people/{users['sofia'].id}/messages"
    assert alice.get(url).status_code == 404
    assert alice.post(url, {'body': 'too early'}).status_code == 404
    assert alice.get('/api/chats').json() == []
    alice, pid = confirmed(users, as_user, flow)
    inbox = alice.get('/api/chats').json()
    assert {(c['kind'], c['title']) for c in inbox} >= {('direct', 'Sofia'), ('direct', 'Jordan')}
    assert len([c for c in inbox if c['kind'] == 'group']) == 1
    assert all('email' not in str(c) and 'goal_text' not in str(c) for c in inbox)
    assert alice.post(url, {'body': ' Hello Sofia! '}).status_code == 201
    sofia = as_user(users['sofia'])
    back = f"/api/chats/people/{users['alice'].id}/messages"
    assert sofia.get(back).json()[0]['body'] == 'Hello Sofia!'
    assert sofia.post(back, {'body': 'Hi Alice!'}).status_code == 201
    assert [m['sender_name'] for m in alice.get(url).json()] == ['Alice', 'Sofia']
    assert as_user(users['jordan']).get(url).json() == []  # same group, separate private thread
    assert as_user(users['eve']).get(back).status_code == 404
    assert alice.get(f"/api/chats/people/{users['alice'].id}/messages").status_code == 404
    assert alice.post(url, {'body': '  '}).status_code == 422
    assert alice.post(url, {'body': 'x' * 1001}).status_code == 422
    assert alice.post(url, {'body': 'forged', 'sender_id': str(users['eve'].id)}).json()['sender_name'] == 'Alice'


def test_connections_persist_after_meetup_and_blocks_deny_both_directions(users, as_user, flow):
    alice, pid = confirmed(users, as_user, flow)
    url = f"/api/chats/people/{users['sofia'].id}/messages"
    alice.post(url, {'body': 'Keep in touch'})
    assert alice.post(f'/api/proposals/{pid}/leave', {}).status_code == 204
    assert alice.get(url).status_code == 200
    assert alice.post('/api/blocks', {'user_id': str(users['sofia'].id)}).status_code == 201
    for actor, peer in [(alice, users['sofia']), (as_user(users['sofia']), users['alice'])]:
        path = f'/api/chats/people/{peer.id}/messages'
        assert actor.get(path).status_code == 404
        assert actor.post(path, {'body': 'blocked'}).status_code == 404
        assert str(peer.id) not in [c['id'] for c in actor.get('/api/chats').json() if c['kind'] == 'direct']
