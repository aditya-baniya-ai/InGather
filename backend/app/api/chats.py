from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.schemas import ConversationOut, MessageIn, MessageOut
from app.security import current_user
from app.services.chats import Chats
from app.services.ratelimit import limiter

router = APIRouter(prefix='/api/chats', tags=['chats'])


def chats(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    return Chats(db, settings)


@router.get('', response_model=list[ConversationOut])
def inbox(user: User = Depends(current_user), svc: Chats = Depends(chats)):
    return svc.inbox(user)


@router.get('/people/{peer_id}/messages', response_model=list[MessageOut])
def messages(peer_id: UUID, user: User = Depends(current_user), svc: Chats = Depends(chats)):
    return svc.messages(user, peer_id)


@router.post('/people/{peer_id}/messages', response_model=MessageOut, status_code=201)
def send(peer_id: UUID, body: MessageIn, user: User = Depends(current_user), svc: Chats = Depends(chats)):
    limiter.hit('message', user.id)
    return svc.send(user, peer_id, body.body)


@router.delete('/people/{peer_id}', status_code=204)
def delete_chat(peer_id: UUID, user: User = Depends(current_user), svc: Chats = Depends(chats)):
    svc.delete(user, peer_id)
    return Response(status_code=204)
