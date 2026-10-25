from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from datetime import datetime

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    organisation_name: str | None = Field(
        default=None, min_length=1, max_length=100
    )
    organisation_slug: str | None = Field(
        default=None, min_length=1, max_length=50, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )

    @model_validator(mode="after")
    def validate_organisation_fields(self):
        if (self.organisation_name is None) != (
            self.organisation_slug is None
        ):
            raise ValueError(
                "Organisation name and slug must be provided together."
            )
        return self

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    email_verified: bool

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=2)

class RefreshAccessTokens(BaseModel):
    refresh_token: str

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    organisation_id: UUID | None = None

class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None

class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    owner_user_id: UUID | None
    organisation_id: UUID | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

class ChatCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)

class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    created_by_user_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_id: UUID
    author_user_id: UUID | None
    role: str
    content: str
    metadata: dict
    created_at: datetime

class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)

class SendChatMessageResponse(BaseModel):
    message: str
    data: ChatMessageResponse