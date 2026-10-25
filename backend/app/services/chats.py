"""Inbox and persistent one-to-one conversations. No contact information is exposed."""
from itertools import combinations
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session
from app.config import Settings
from app.models import DirectConnection, DirectMessage, MemberStatus, Message, Proposal, ProposalMember, ProposalStatus, User
from app.schemas import ChatPerson, ConversationOut, MessageOut
from app.security import not_found
from app.services.policy import Policy
from app.services.profile import details as profile_details


class Chats:
    def __init__(self, db: Session, settings: Settings):
        self.db, self.policy = db, Policy(db, settings)

    def connect(self, proposal: Proposal):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        insert = sqlite_insert if self.db.get_bind().dialect.name == 'sqlite' else pg_insert
        ids = sorted({m.user_id for m in proposal.members if m.status == MemberStatus.accepted}, key=str)
        for a, b in combinations(ids, 2):
            self.db.execute(insert(DirectConnection).values(user_a_id=a, user_b_id=b).on_conflict_do_nothing())

    @staticmethod
    def person(user: User):
        return ChatPerson(user_id=user.id, display_name=user.display_name, avatar_url=user.avatar_url, details=profile_details(user))

    @staticmethod
    def pair_messages(a, b):
        return or_((DirectMessage.sender_id == a) & (DirectMessage.recipient_id == b),
                   (DirectMessage.sender_id == b) & (DirectMessage.recipient_id == a))

    def inbox(self, user: User):
        result = []
        proposals = self.db.scalars(select(Proposal).join(ProposalMember).where(
            ProposalMember.user_id == user.id, ProposalMember.status == MemberStatus.accepted,
            Proposal.status == ProposalStatus.confirmed)).unique()
        for p in proposals:
            if self.policy.viewer_role(user, p) not in {'owner', 'member'}:
                continue
            people = [self.person(m.user) for m in p.members if m.status == MemberStatus.accepted]
            last = self.db.scalar(select(Message).where(Message.proposal_id == p.id).order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
            sender = self.db.get(User, last.sender_id) if last and last.sender_id else None
            result.append(ConversationOut(id=p.id, kind='group', title=p.activity_title, people=people,
                last_message=last.body if last else None, last_sender_name=sender.display_name if sender else 'Gather Agent',
                updated_at=last.created_at if last else p.updated_at))
        blocked = self.policy.blocked_with(user.id)
        connections = self.db.scalars(select(DirectConnection).where(or_(DirectConnection.user_a_id == user.id, DirectConnection.user_b_id == user.id)))
        for connection in connections:
            peer_id = connection.user_b_id if connection.user_a_id == user.id else connection.user_a_id
            if peer_id in blocked:
                continue
            peer = self.db.get(User, peer_id)
            if peer is None:
                continue
            last = self.db.scalar(select(DirectMessage).where(self.pair_messages(user.id, peer_id)).order_by(DirectMessage.created_at.desc(), DirectMessage.id.desc()).limit(1))
            sender = self.db.get(User, last.sender_id) if last else None
            result.append(ConversationOut(id=peer.id, kind='direct', title=peer.display_name, people=[self.person(peer)],
                last_message=last.body if last else None, last_sender_name=sender.display_name if sender else None,
                updated_at=last.created_at if last else connection.created_at))
        return sorted(result, key=lambda c: c.updated_at, reverse=True)

    def delete(self, user: User, peer_id) -> None:
        """Delete a direct chat and its messages for both people; 404 if there is no such chat."""
        pair = or_(and_(DirectConnection.user_a_id == user.id, DirectConnection.user_b_id == peer_id),
                   and_(DirectConnection.user_a_id == peer_id, DirectConnection.user_b_id == user.id))
        if self.db.scalar(select(DirectConnection).where(pair)) is None:
            raise not_found()
        self.db.execute(delete(DirectMessage).where(self.pair_messages(user.id, peer_id)))
        self.db.execute(delete(DirectConnection).where(pair))
        self.db.commit()

    def messages(self, user: User, peer_id):
        self.policy.direct_peer(user, peer_id)
        rows = self.db.execute(select(DirectMessage, User).join(User, User.id == DirectMessage.sender_id)
            .where(self.pair_messages(user.id, peer_id)).order_by(DirectMessage.created_at.desc(), DirectMessage.id.desc()).limit(200)).all()
        return [MessageOut.build(m, sender) for m, sender in reversed(rows)]

    def send(self, user: User, peer_id, body):
        self.policy.direct_peer(user, peer_id)
        msg = DirectMessage(sender_id=user.id, recipient_id=peer_id, body=body.strip())
        self.db.add(msg)
        self.db.commit()
        return MessageOut.build(msg, user)
