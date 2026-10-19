from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    organization_name: str = Field(min_length=2, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class DocumentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=220)
    content: str = Field(min_length=50, max_length=120000)


class TicketCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=220)
    question: str = Field(min_length=5, max_length=6000)
    requester_email: EmailStr | None = None


class TicketDecision(BaseModel):
    decision: Literal["approve", "reject"]
    edited_draft: str | None = Field(default=None, min_length=5, max_length=12000)


class EvaluationCaseCreate(BaseModel):
    question: str = Field(min_length=5, max_length=2500)
    must_include: str | None = Field(default=None, max_length=180)
    expect_abstain: bool = False


class InviteCreate(BaseModel):
    email: EmailStr
    role: Literal["agent", "viewer"] = "agent"


class InviteAccept(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=128)


class CheckoutRequest(BaseModel):
    plan: Literal["starter", "growth"]
