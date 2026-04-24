from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id = Column(Integer, primary_key=True, index=True)
    template_name = Column(String(255), nullable=False)
    file_name = Column(String(255), nullable=False)
    html_content = Column(Text, nullable=False)
    description = Column(Text, nullable=True)

    # 추가
    template_schema = Column(Text, nullable=True)
    placeholder_keys = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    approval_rules = relationship("ApprovalRule", back_populates="template")
    generated_documents = relationship("GeneratedDocument", back_populates="template")


class OrgMember(Base):
    __tablename__ = "org_members"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    title = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    department = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    approval_rule_maps = relationship("ApprovalRuleApprover", back_populates="approver")


# models.py

class ApprovalRule(Base):
    __tablename__ = "approval_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_name = Column(String(255), nullable=False)
    rule_text = Column(Text, nullable=False)

    template_id = Column(Integer, ForeignKey("document_templates.id"), nullable=False)

    # 추가
    source_type = Column(String(30), nullable=True, default="manual")   # manual / guide
    source_name = Column(String(255), nullable=True)                    # 업로드한 파일명
    source_excerpt = Column(Text, nullable=True)                        # 지침서 근거 문장

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    template = relationship("DocumentTemplate", back_populates="approval_rules")
    approver_maps = relationship(
        "ApprovalRuleApprover",
        back_populates="rule",
        cascade="all, delete-orphan"
    )


class ApprovalRuleApprover(Base):
    __tablename__ = "approval_rule_approvers"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("approval_rules.id"), nullable=False)
    approver_member_id = Column(Integer, ForeignKey("org_members.id"), nullable=False)

    # 결재 순서
    approval_order = Column(Integer, nullable=False, default=1)

    # 선택: 필수/참조/합의 같은 타입이 필요하면 추가
    approval_type = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    rule = relationship("ApprovalRule", back_populates="approver_maps")
    approver = relationship("OrgMember", back_populates="approval_rule_maps")

    __table_args__ = (
        UniqueConstraint("rule_id", "approver_member_id", name="uq_rule_approver"),
        UniqueConstraint("rule_id", "approval_order", name="uq_rule_order"),
    )
    
class GeneratedDocument(Base):
    __tablename__ = "generated_documents"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("document_templates.id"), nullable=False)

    # 추가 추천
    applied_rule_id = Column(Integer, ForeignKey("approval_rules.id"), nullable=True)
    recipient_member_id = Column(Integer, ForeignKey("org_members.id"), nullable=True)

    document_title = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)

    receipt_file_name = Column(String(255), nullable=True)
    receipt_content_type = Column(String(100), nullable=True)

    extracted_json = Column(Text, nullable=True)
    html_content = Column(Text, nullable=False)

    recipient_name = Column(String(100), nullable=True)
    recipient_email = Column(String(255), nullable=True)
    recipient_title = Column(String(100), nullable=True)

    is_sent = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    template = relationship("DocumentTemplate", back_populates="generated_documents")
    applied_rule = relationship("ApprovalRule")
    recipient_member = relationship("OrgMember")