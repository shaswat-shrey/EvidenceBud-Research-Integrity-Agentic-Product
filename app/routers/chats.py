from fastapi import APIRouter, status, Depends, HTTPException
from app.auth_dependencies import get_current_user
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import or_, text, select

from app.models.project import Project
from app.models.chat import Chat
from app.models.chatMessage import ChatMessage
from app.database import get_db
from app.schemas import (
    ChatCreate,
    ChatMessageResponse,
    ChatResponse,
    ChatMessageCreate,
    SendChatMessageResponse
)

router = APIRouter(
    prefix="/api/v1",
    tags=["Chats"]
    )


######################################################################################################
# -------------------------------------- CHAT FUNCTION ------------------------------------------
######################################################################################################

@router.post(
    "/projects/{project_id}/chats",
    response_model=ChatResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chats(
    project_id: UUID, 
    payload: ChatCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = UUID(str(current_user["id"]))
    print("done-1")
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.archived_at.is_(None),
        or_(
            Project.owner_user_id == user_id,
            Project.organisation_id.in_(
                select(text("org_id")).select_from(
                    text("organisation_members")
                ).where(text("user_id = :user_id"))
            ),
        ),
    ).params(user_id=str(user_id)).first()
    print("done-2")
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    print("done-3")
    title = payload.title.strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Chat title cannot be blank.",
        )
    print(title)
    chat = Chat(
        project_id=project_id,
        created_by_user_id=user_id,
        title=title,
    )
    print(chat.project_id)
    print(chat.created_by_user_id)
    print(db.get_bind().url.database)
    try:
        db.add(chat)
        print("added")
        db.commit()
        print("comitted")
        db.refresh(chat)
        print("refreshed")
        return chat
    except Exception as e:
        db.rollback()
        print("Issue:", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create chat.",
        )


######################################################################################################
# -------------------------------------- GET CHAT FUNCTION ------------------------------------------
######################################################################################################

@router.get(
    "/projects/{project_id}/chats",
    response_model=list[ChatResponse],
)
def list_projects_chats(
    project_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = UUID(str(current_user["id"]))

    project = db.query(Project).filter(
        Project.id == project_id,
        Project.archived_at.is_(None),
        or_(
            Project.owner_user_id == user_id,
            Project.organisation_id.in_(
                select(text("org_id")).select_from(
                    text("organisation_members")
                ).where(text("user_id = :user_id"))
            ),
        ),
    ).params(user_id=str(user_id)).first()

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    return db.query(Chat).filter(
        Chat.project_id == project_id,
        Chat.archived_at.is_(None),
    ).order_by(Chat.created_at.desc()).all()

######################################################################################################
# -------------------------------------- MESSAGES FUNCTION ------------------------------------------
######################################################################################################

@router.get(
    "/chats/{chat_id}/messages",
    response_model=list[ChatMessageResponse],
)
def get_chat_messages(
    chat_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = UUID(str(current_user["id"]))

    chat = db.query(Chat).join(
        Project,
        Chat.project_id == Project.id,
    ).filter(
        Chat.id == chat_id,
        Chat.archived_at.is_(None),
        Project.archived_at.is_(None),
        or_(
            Project.owner_user_id == user_id,
            Project.organisation_id.in_(
                select(text("org_id")).select_from(
                    text("organisation_members")
                ).where(text("user_id = :user_id"))
            ),
        ),
    ).params(user_id=str(user_id)).first()

    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found.",
        )

    return db.query(ChatMessage).filter(
        ChatMessage.chat_id == chat_id,
    ).order_by(
        ChatMessage.created_at.asc(),
        ChatMessage.id.asc(),
    ).all()

######################################################################################################
# -------------------------------------- POST MESSAGES FUNCTION --------------------------------------
######################################################################################################

@router.post(
    "/chats/{chat_id}/messages",
    response_model=SendChatMessageResponse,
)
def send_chat_messages(
    chat_id: UUID,
    payload: ChatMessageCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)                             
):
    try:
        chat_query = text(
                """
                    SELECT c.id
                    FROM chats c
                    JOIN projects p ON p.id = c.project_id
                    WHERE c.id = :chat_id
                      AND c.archived_at IS NULL
                      AND p.archived_at IS NULL
                      AND (
                          p.owner_user_id = :user_id
                          OR p.organisation_id IN (
                            SELECT om.org_id
                            FROM organisation_members om
                            WHERE om.user_id = :user_id
                          )
                      )
                """
                )
        chat = db.execute(
            chat_query,
            {
                "chat_id": chat_id,
                "user_id": current_user["id"]
            }
        ).mappings().first()
            
        if chat is None:
            raise HTTPException(
                status_code=404,
                detail="Chat not found.",
            )
        
        result = db.execute(
            text(
                """
                    INSERT INTO chat_messages (
                        chat_id,
                        author_user_id,
                        role,
                        content
                    )
                    VALUES (
                        :chat_id,
                        :user_id,
                        'user',
                        :content
                    )
                    RETURNING id, chat_id, author_user_id, role, content,
                            metadata, created_at
                """
            ),
            {
                "chat_id": chat_id,
                "user_id": current_user["id"],
                "content": payload.content,
            },
        ).mappings().one()
        
        db.commit()
        return {
            "message": "Message sent successfully.",
            "data": dict(result),
        }
    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        # Log the exception server-side in production.
        print(e)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while sending the message.",
        )
    
    