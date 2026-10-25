from app.models import DirectConnection, DirectMessage, Plan, Proposal


def test_owner_deletes_plan_and_its_groups(users, plan_of, as_user, db):
    plan_id = plan_of(users["sofia"]).id
    assert as_user(users["alice"]).delete(f"/api/plans/{plan_id}").status_code == 404  # not the owner
    assert as_user(users["sofia"]).delete(f"/api/plans/{plan_id}").status_code == 204
    db.expire_all()
    assert db.get(Plan, plan_id) is None and db.query(Proposal).filter_by(plan_id=plan_id).count() == 0
    assert as_user(users["sofia"]).get(f"/api/plans/{plan_id}").status_code == 404


def test_delete_direct_chat_for_both(users, as_user, db):
    a, b = users["alice"], users["maya"]
    db.add(DirectConnection(user_a_id=a.id, user_b_id=b.id))
    db.add(DirectMessage(sender_id=a.id, recipient_id=b.id, body="hi"))
    db.commit()
    assert as_user(users["eve"]).delete(f"/api/chats/people/{a.id}").status_code == 404
    assert as_user(a).delete(f"/api/chats/people/{b.id}").status_code == 204
    db.expire_all()
    assert db.query(DirectConnection).count() == 0 and db.query(DirectMessage).count() == 0
    assert [c for c in as_user(b).get("/api/chats").json() if c["kind"] == "direct"] == []
