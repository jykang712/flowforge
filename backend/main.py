import json
import base64
import re
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
import html as html_lib
from pypdf import PdfReader

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload

from database import Base, engine, get_db
from models import (
    DocumentTemplate,
    OrgMember,
    ApprovalRule,
    ApprovalRuleApprover,
    GeneratedDocument,
)
# 지피티 호출 시 사용 ------------------------------------------------------------------------
# from openai_service import (
#     extract_expense_data,
#     preview_org_members_from_image,
#     preview_approval_rules_from_guide,
#     convert_template_to_schema,
# )
# --------------------------------------------------------------------------------------------

# 클로드 호출 시 사용 -------------------------------------------------------------------------
from claude_service import (
    extract_expense_data,
    preview_org_members_from_image,
    preview_approval_rules_from_guide,
    convert_template_to_schema,
)
# ---------------------------------------------------------------------------------------------
from email_service import send_document_email

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

async def extract_html_text(file: UploadFile) -> str:
    file_bytes = await file.read()
    return file_bytes.decode("utf-8", errors="ignore")

def render_template_value(value) -> str:
    if value is None:
        return ""

    if isinstance(value, list):
        lines = []

        for item in value:
            if isinstance(item, dict):
                parts = []
                for k, v in item.items():
                    if v not in [None, ""]:
                        parts.append(f"{k}: {v}")
                lines.append(" / ".join(parts))
            else:
                lines.append(str(item))

        return "<br>".join(html_lib.escape(line) for line in lines)

    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            if v not in [None, ""]:
                lines.append(f"{k}: {v}")
        return "<br>".join(html_lib.escape(line) for line in lines)

    return html_lib.escape(str(value))

def fill_template(template: str, data: dict) -> str:
    result = template
    for key, value in data.items():
        result = result.replace(
            f"{{{{{key}}}}}", 
            render_template_value(value),
        )
    return result

def _normalize_org_row(row: dict) -> dict:
    return {
        "name": (row.get("name") or "").strip(),
        "department": (row.get("department") or "").strip(),
        "title": (row.get("title") or "").strip(),
        "email": (row.get("email") or "").strip().replace(" ", ""),
    }
    
def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    texts = []

    for page in reader.pages:
        texts.append(page.extract_text() or "")

    return "\n".join(texts).strip()

def match_approval_field_by_title(title: str) -> str | None:
    title = (title or "").strip()

    # 대표이사는 '대표'와 '이사'가 같이 들어갈 수 있으므로 대표를 먼저 판단
    if "대표" in title:
        return "approval_ceo_name"

    if "이사" in title:
        return "approval_director_name"

    if "부장" in title:
        return "approval_general_manager_name"

    if "과장" in title:
        return "approval_manager_name"

    return None

def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _clean_extracted_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _collect_xml_text(element: ET.Element) -> str:
    parts = []

    for node in element.iter():
        name = _xml_local_name(node.tag)

        if name == "t" and node.text:
            parts.append(node.text)
        elif name == "tab":
            parts.append("\t")
        elif name in {"br", "cr"}:
            parts.append("\n")

    return _clean_extracted_text("".join(parts))


def _extract_docx_table_text(table: ET.Element) -> list[str]:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    rows = []

    for tr in table.findall("./w:tr", ns):
        cells = []

        for tc in tr.findall("./w:tc", ns):
            paragraphs = []

            for paragraph in tc.findall(".//w:p", ns):
                paragraph_text = _collect_xml_text(paragraph)
                if paragraph_text:
                    paragraphs.append(paragraph_text)

            cells.append(" ".join(paragraphs).strip())

        if any(cells):
            rows.append(" | ".join(cells))

    return rows


def extract_docx_text(file_bytes: bytes) -> str:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    blocks = []

    try:
        with zipfile.ZipFile(BytesIO(file_bytes)) as archive:
            names = archive.namelist()

            if "word/document.xml" not in names:
                raise ValueError("word/document.xml을 찾지 못했습니다.")

            xml_targets = ["word/document.xml"]
            xml_targets += sorted(
                name
                for name in names
                if re.match(r"word/(header|footer)\d+\.xml$", name)
            )

            for xml_name in xml_targets:
                root = ET.fromstring(archive.read(xml_name))
                body = root.find("w:body", ns) if xml_name == "word/document.xml" else root

                if body is None:
                    body = root

                for child in list(body):
                    child_name = _xml_local_name(child.tag)

                    if child_name == "p":
                        text = _collect_xml_text(child)
                        if text:
                            blocks.append(text)

                    elif child_name == "tbl":
                        table_rows = _extract_docx_table_text(child)
                        if table_rows:
                            blocks.extend(table_rows)
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail="DOCX 파일 형식이 올바르지 않습니다.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"DOCX 원문을 읽지 못했습니다: {str(e)}",
        )

    return _clean_extracted_text("\n".join(blocks))


def extract_hwpx_text(file_bytes: bytes) -> str:
    blocks = []

    try:
        with zipfile.ZipFile(BytesIO(file_bytes)) as archive:
            names = archive.namelist()
            section_names = sorted(
                name
                for name in names
                if name.startswith("Contents/section") and name.endswith(".xml")
            )

            if not section_names:
                section_names = sorted(
                    name
                    for name in names
                    if name.endswith(".xml")
                    and not name.startswith("META-INF/")
                    and not name.startswith("Preview/")
                )

            if not section_names:
                raise ValueError("HWPX 본문 XML을 찾지 못했습니다.")

            for xml_name in section_names:
                try:
                    root = ET.fromstring(archive.read(xml_name))
                except ET.ParseError:
                    continue

                paragraph_texts = []

                for node in root.iter():
                    if _xml_local_name(node.tag) == "p":
                        text = _collect_xml_text(node)
                        if text:
                            paragraph_texts.append(text)

                if paragraph_texts:
                    blocks.extend(paragraph_texts)
                else:
                    text = _collect_xml_text(root)
                    if text:
                        blocks.append(text)

    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail="HWPX 파일 형식이 올바르지 않습니다.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"HWPX 원문을 읽지 못했습니다: {str(e)}",
        )

    return _clean_extracted_text("\n".join(blocks))


async def read_template_source(template: UploadFile) -> tuple[str, str, str]:
    filename = template.filename or "template"
    lowered = filename.lower()

    if lowered.endswith(".html") or lowered.endswith(".htm"):
        source_text = await extract_html_text(template)
        file_type = "html"

    elif lowered.endswith(".pdf"):
        file_bytes = await template.read()
        source_text = extract_pdf_text(file_bytes)
        file_type = "pdf"

    elif lowered.endswith(".docx"):
        file_bytes = await template.read()
        source_text = extract_docx_text(file_bytes)
        file_type = "docx"

    elif lowered.endswith(".hwpx"):
        file_bytes = await template.read()
        source_text = extract_hwpx_text(file_bytes)
        file_type = "hwpx"

    elif lowered.endswith(".hwp"):
        raise HTTPException(
            status_code=400,
            detail="HWP 파일은 바로 처리하기 어렵습니다. HWPX로 변환한 뒤 업로드해주세요.",
        )

    else:
        raise HTTPException(
            status_code=400,
            detail="HTML, PDF, DOCX, HWPX 파일만 업로드 가능합니다.",
        )

    if not source_text.strip():
        raise HTTPException(
            status_code=400,
            detail="템플릿 원문을 읽지 못했습니다.",
        )

    return filename, file_type, source_text


def parse_json_list_form(value: str, field_name: str) -> list:
    try:
        parsed = json.loads(value or "[]")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} JSON 형식이 올바르지 않습니다.",
        )

    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} 값은 배열이어야 합니다.",
        )

    return parsed


def build_template_fields_from_schema(
    json_schema: dict,
    placeholder_keys: list,
) -> list[dict]:
    properties = json_schema.get("properties", {}) if isinstance(json_schema, dict) else {}
    required = set(json_schema.get("required", [])) if isinstance(json_schema, dict) else set()

    fields = []

    for key in placeholder_keys:
        schema_info = properties.get(key, {})
        schema_type = schema_info.get("type", "string")

        if schema_type in ["integer", "number"]:
            ui_type = "number"
        elif schema_type == "array":
            ui_type = "array"
        elif schema_type == "boolean":
            ui_type = "boolean"
        else:
            ui_type = "string"

        fields.append(
            {
                "label": schema_info.get("title")
                or schema_info.get("description")
                or key,
                "key": key,
                "type": ui_type,
                "required": key in required,
                "description": schema_info.get("description", ""),
                "position_hint": "",
            }
        )

    return fields

def validate_template_conversion(
    html_template: str,
    json_schema: dict,
    placeholder_keys: list,
):
    if not html_template or not html_template.strip():
        raise HTTPException(
            status_code=500,
            detail="변환된 HTML 템플릿이 비어 있습니다."
        )

    if "{{" not in html_template or "}}" not in html_template:
        raise HTTPException(
            status_code=500,
            detail="플레이스홀더 변환에 실패했습니다. 템플릿에 {{key}} 형식이 없습니다."
        )

    if not isinstance(json_schema, dict):
        raise HTTPException(
            status_code=500,
            detail="템플릿 스키마 형식이 올바르지 않습니다."
        )

    if json_schema.get("type") != "object":
        raise HTTPException(
            status_code=500,
            detail="템플릿 스키마의 최상위 type은 object여야 합니다."
        )

    properties = json_schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        raise HTTPException(
            status_code=500,
            detail="템플릿 스키마 properties 생성에 실패했습니다."
        )

    if not isinstance(placeholder_keys, list) or not placeholder_keys:
        raise HTTPException(
            status_code=500,
            detail="placeholder_keys 생성에 실패했습니다."
        )

    found_keys = re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", html_template)
    found_keys = list(dict.fromkeys(found_keys))

    if not found_keys:
        raise HTTPException(
            status_code=500,
            detail="HTML 템플릿에서 플레이스홀더를 찾지 못했습니다."
        )

    schema_keys = list(properties.keys())

    missing_in_schema = [key for key in found_keys if key not in schema_keys]
    if missing_in_schema:
        raise HTTPException(
            status_code=500,
            detail=f"HTML의 placeholder 중 schema에 없는 key가 있습니다: {missing_in_schema}"
        )

    missing_in_placeholder_keys = [key for key in found_keys if key not in placeholder_keys]
    if missing_in_placeholder_keys:
        raise HTTPException(
            status_code=500,
            detail=f"HTML의 placeholder 중 placeholder_keys에 없는 key가 있습니다: {missing_in_placeholder_keys}"
        )

def persist_approval_rule(
    db: Session,
    payload: dict,
    source_type: str = "manual",
    source_name: str | None = None,
):
    required = ["rule_name", "rule_text", "template_id", "approvers"]
    for field in required:
        if payload.get(field) in [None, "", []]:
            raise HTTPException(status_code=400, detail=f"{field} 값이 필요합니다.")

    if not isinstance(payload["approvers"], list) or len(payload["approvers"]) == 0:
        raise HTTPException(status_code=400, detail="approvers는 1명 이상이어야 합니다.")

    template = (
        db.query(DocumentTemplate)
        .filter(
            DocumentTemplate.id == int(payload["template_id"]),
            DocumentTemplate.is_active == True,
        )
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="적용할 템플릿을 찾을 수 없습니다.")

    rule = ApprovalRule(
        rule_name=payload["rule_name"].strip(),
        rule_text=payload["rule_text"].strip(),
        template_id=int(payload["template_id"]),
        source_type=source_type,
        source_name=source_name,
        source_excerpt=(payload.get("source_excerpt") or "").strip() or None,
        is_active=True,
    )
    db.add(rule)
    db.flush()

    used_orders = set()

    for item in payload["approvers"]:
        member_id = item.get("approver_member_id")
        approval_order = int(item.get("approval_order", 1))
        approval_type = (item.get("approval_type") or "").strip() or None

        if not member_id:
            raise HTTPException(status_code=400, detail="결재자 ID가 필요합니다.")

        if approval_order in used_orders:
            raise HTTPException(status_code=400, detail="결재 순서는 중복될 수 없습니다.")
        used_orders.add(approval_order)

        approver = (
            db.query(OrgMember)
            .filter(
                OrgMember.id == int(member_id),
                OrgMember.is_active == True,
            )
            .first()
        )
        if not approver:
            raise HTTPException(status_code=404, detail=f"ID {member_id} 조직원을 찾을 수 없습니다.")

        db.add(
            ApprovalRuleApprover(
                rule_id=rule.id,
                approver_member_id=int(member_id),
                approval_order=approval_order,
                approval_type=approval_type,
            )
        )

    return rule

@app.get("/")
def root():
    return {"message": "FastAPI backend is running"}

# 템플릿 저장/조회-------------------------------------------------------------------------------------------------------------
# 기존 방식 호환용: 업로드 즉시 AI 변환 후 저장
@app.post("/api/templates")
async def create_template(
    template: UploadFile = File(...),
    template_name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    filename, file_type, source_text = await read_template_source(template)

    try:
        converted = await convert_template_to_schema(
            source_text=source_text,
            file_type=file_type,
            template_name=template_name.strip(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI 템플릿 변환 중 오류가 발생했습니다: {str(e)}",
        )

    html_template = converted["html_template"]
    json_schema = converted["json_schema"]
    placeholder_keys = converted["placeholder_keys"]
    fields = converted.get("fields", [])

    validate_template_conversion(
        html_template=html_template,
        json_schema=json_schema,
        placeholder_keys=placeholder_keys,
    )

    new_template = DocumentTemplate(
        template_name=template_name.strip(),
        file_name=filename,
        html_content=html_template,
        description=description.strip(),
        template_schema=json.dumps(json_schema, ensure_ascii=False),
        placeholder_keys=json.dumps(placeholder_keys, ensure_ascii=False),
        is_active=True,
    )

    db.add(new_template)
    db.commit()
    db.refresh(new_template)

    return {
        "status": "ok",
        "id": new_template.id,
        "template_name": new_template.template_name,
        "file_name": new_template.file_name,
        "description": new_template.description,
        "placeholder_keys": placeholder_keys,
        "fields": fields,
    }

# 미리보기 버튼 클릭 시 템플릿 보여주기 -----------------------------------------------------------------------------------------------------
@app.get("/api/templates/{template_id}")
def get_template_detail(
    template_id: int,
    db: Session = Depends(get_db),
):
    template = (
        db.query(DocumentTemplate)
        .filter(
            DocumentTemplate.id == template_id,
            DocumentTemplate.is_active == True,
        )
        .first()
    )

    if not template:
        raise HTTPException(
            status_code=404,
            detail="템플릿을 찾을 수 없습니다.",
        )

    try:
        placeholder_keys = (
            json.loads(template.placeholder_keys)
            if template.placeholder_keys
            else []
        )
    except Exception:
        placeholder_keys = []

    try:
        json_schema = (
            json.loads(template.template_schema)
            if template.template_schema
            else {}
        )
    except Exception:
        json_schema = {}

    return {
        "id": template.id,
        "template_name": template.template_name,
        "file_name": template.file_name,
        "description": template.description,
        "html_content": template.html_content,
        "placeholder_keys": placeholder_keys,
        "fields": build_template_fields_from_schema(
            json_schema=json_schema,
            placeholder_keys=placeholder_keys,
        ),
    }

# 신규 방식 1단계: AI가 자동 입력 항목 후보와 미리보기 HTML 생성
@app.post("/api/templates/preview-fields")
async def preview_template_fields(
    template: UploadFile = File(...),
    template_name: str = Form(...),
    description: str = Form(""),
):
    filename, file_type, source_text = await read_template_source(template)

    try:
        converted = await convert_template_to_schema(
            source_text=source_text,
            file_type=file_type,
            template_name=template_name.strip(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI 자동 입력 항목 분석 중 오류가 발생했습니다: {str(e)}",
        )

    html_template = converted["html_template"]
    json_schema = converted["json_schema"]
    placeholder_keys = converted["placeholder_keys"]
    fields = converted.get("fields", [])

    validate_template_conversion(
        html_template=html_template,
        json_schema=json_schema,
        placeholder_keys=placeholder_keys,
    )

    return {
        "status": "ok",
        "file_name": filename,
        "template_name": template_name.strip(),
        "description": description.strip(),
        "html_template": html_template,
        "preview_html": html_template,
        "json_schema": json_schema,
        "placeholder_keys": placeholder_keys,
        "fields": fields,
    }


# 신규 방식 2단계: 사용자가 확정한 자동 입력 항목으로 최종 저장
@app.post("/api/templates/save-with-fields")
async def save_template_with_fields(
    template: UploadFile = File(...),
    template_name: str = Form(...),
    description: str = Form(""),
    fields: str = Form("[]"),
    db: Session = Depends(get_db),
):
    confirmed_fields = parse_json_list_form(fields, "fields")

    if not confirmed_fields:
        raise HTTPException(
            status_code=400,
            detail="자동 입력 항목을 1개 이상 설정해주세요.",
        )

    filename, file_type, source_text = await read_template_source(template)

    try:
        converted = await convert_template_to_schema(
            source_text=source_text,
            file_type=file_type,
            template_name=template_name.strip(),
            confirmed_fields=confirmed_fields,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"확정 항목 기반 템플릿 저장 중 오류가 발생했습니다: {str(e)}",
        )

    html_template = converted["html_template"]
    json_schema = converted["json_schema"]
    placeholder_keys = converted["placeholder_keys"]
    normalized_fields = converted.get("fields", [])

    validate_template_conversion(
        html_template=html_template,
        json_schema=json_schema,
        placeholder_keys=placeholder_keys,
    )

    new_template = DocumentTemplate(
        template_name=template_name.strip(),
        file_name=filename,
        html_content=html_template,
        description=description.strip(),
        template_schema=json.dumps(json_schema, ensure_ascii=False),
        placeholder_keys=json.dumps(placeholder_keys, ensure_ascii=False),
        is_active=True,
    )

    db.add(new_template)
    db.commit()
    db.refresh(new_template)

    return {
        "status": "ok",
        "id": new_template.id,
        "template_name": new_template.template_name,
        "file_name": new_template.file_name,
        "description": new_template.description,
        "placeholder_keys": placeholder_keys,
        "fields": normalized_fields,
    }


@app.get("/api/templates")
def get_templates(db: Session = Depends(get_db)):
    templates = (
        db.query(DocumentTemplate)
        .filter(DocumentTemplate.is_active == True)
        .order_by(DocumentTemplate.id.desc())
        .all()
    )

    results = []

    for t in templates:
        try:
            placeholder_keys = json.loads(t.placeholder_keys) if t.placeholder_keys else []
        except Exception:
            placeholder_keys = []

        try:
            json_schema = json.loads(t.template_schema) if t.template_schema else {}
        except Exception:
            json_schema = {}

        results.append(
            {
                "id": t.id,
                "template_name": t.template_name,
                "file_name": t.file_name,
                "description": t.description,
                "placeholder_keys": placeholder_keys,
                "fields": build_template_fields_from_schema(
                    json_schema=json_schema,
                    placeholder_keys=placeholder_keys,
                ),
            }
        )

    return results
    
# 조직도 저장/조회---------------------------------------------------------------------------------------------------------
@app.post("/api/org-members")
def create_org_member(
    payload: dict,
    db: Session = Depends(get_db),
):
    required = ["name", "title", "email"]
    for field in required:
        if not payload.get(field):
            raise HTTPException(status_code=400, detail=f"{field} 값이 필요합니다.")

    name = payload["name"].strip()
    title = payload["title"].strip()
    email = payload["email"].strip().replace(" ", "")
    department = (payload.get("department") or "").strip()

    existing = (
        db.query(OrgMember)
        .filter(OrgMember.is_active == True)
        .all()
    )
    existing_emails = {(m.email or "").strip().lower() for m in existing if m.email}
    if email.lower() in existing_emails:
        raise HTTPException(status_code=400, detail="이미 저장된 이메일입니다.")

    member = OrgMember(
        name=name,
        title=title,
        email=email,
        department=department,
        is_active=True,
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    return {
        "status": "ok",
        "id": member.id,
    }


@app.get("/api/org-members")
def get_org_members(db: Session = Depends(get_db)):
    members = (
        db.query(OrgMember)
        .filter(OrgMember.is_active == True)
        .order_by(OrgMember.id.asc())
        .all()
    )

    return [
        {
            "id": m.id,
            "name": m.name,
            "title": m.title,
            "email": m.email,
            "department": m.department,
        }
        for m in members
    ]

# 조직도 이미지 미리보기---------------------------------------------------------------------------------------------------------
@app.post("/api/org-members/preview-image")
async def preview_org_members_image(
    org_image: UploadFile = File(...),
):
    content_type = org_image.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드할 수 있습니다.")

    image_bytes = await org_image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="업로드된 이미지가 비어 있습니다.")

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    rows = await preview_org_members_from_image(
        image_b64=image_b64,
        image_mime=content_type,
    )

    return {
        "status": "ok",
        "rows": rows,
        "parsed_count": len(rows),
        "file_name": org_image.filename,
    }

# 조직도 이미지 미리보기 저장---------------------------------------------------------------------------------------------------------
@app.post("/api/org-members/save-preview")
def save_preview_org_members(
    payload: dict,
    db: Session = Depends(get_db),
):
    rows = payload.get("rows")

    if not isinstance(rows, list) or len(rows) == 0:
        raise HTTPException(status_code=400, detail="저장할 조직도 미리보기 데이터가 없습니다.")

    existing_members = (
        db.query(OrgMember)
        .filter(OrgMember.is_active == True)
        .all()
    )
    existing_emails = {(m.email or "").strip().lower() for m in existing_members if m.email}
    batch_emails = set()

    saved = []
    skipped = []

    for idx, raw_row in enumerate(rows, start=1):
        if not isinstance(raw_row, dict):
            skipped.append({
                "row_index": idx,
                "reason": "행 데이터 형식이 올바르지 않습니다.",
                "data": raw_row,
            })
            continue

        row = _normalize_org_row(raw_row)

        if not row["name"] or not row["title"] or not row["email"]:
            skipped.append({
                "row_index": idx,
                "reason": "이름/직급/이메일은 필수입니다.",
                "data": row,
            })
            continue

        lower_email = row["email"].lower()

        if lower_email in existing_emails:
            skipped.append({
                "row_index": idx,
                "reason": "이미 저장된 이메일입니다.",
                "data": row,
            })
            continue

        if lower_email in batch_emails:
            skipped.append({
                "row_index": idx,
                "reason": "업로드 목록 안에서 이메일이 중복됩니다.",
                "data": row,
            })
            continue

        member = OrgMember(
            name=row["name"],
            title=row["title"],
            email=row["email"],
            department=row["department"],
            is_active=True,
        )
        db.add(member)
        db.flush()

        batch_emails.add(lower_email)
        existing_emails.add(lower_email)

        saved.append({
            "id": member.id,
            "name": member.name,
            "department": member.department,
            "title": member.title,
            "email": member.email,
        })

    db.commit()

    return {
        "status": "ok",
        "saved_count": len(saved),
        "skipped_count": len(skipped),
        "saved": saved,
        "skipped": skipped,
    }

# 결재 방침 저장/조회 수정 전--------------------------------------------------------------------------------------------------------
# @app.post("/api/approval-rules")
# def create_approval_rule(
#     payload: dict,
#     db: Session = Depends(get_db),
# ):
#     required = ["rule_name", "rule_text", "template_id", "approvers"]
#     for field in required:
#         if payload.get(field) in [None, ""]:
#             raise HTTPException(status_code=400, detail=f"{field} 값이 필요합니다.")

#     if not isinstance(payload["approvers"], list) or len(payload["approvers"]) == 0:
#         raise HTTPException(status_code=400, detail="approvers는 1명 이상이어야 합니다.")

#     template = (
#         db.query(DocumentTemplate)
#         .filter(
#             DocumentTemplate.id == payload["template_id"],
#             DocumentTemplate.is_active == True,
#         )
#         .first()
#     )
#     if not template:
#         raise HTTPException(status_code=404, detail="적용할 템플릿을 찾을 수 없습니다.")

#     rule = ApprovalRule(
#         rule_name=payload["rule_name"].strip(),
#         rule_text=payload["rule_text"].strip(),
#         template_id=payload["template_id"],
#         is_active=True,
#     )
#     db.add(rule)
#     db.flush()  # rule.id 확보

#     used_orders = set()

#     for item in payload["approvers"]:
#         member_id = item.get("approver_member_id")
#         approval_order = item.get("approval_order", 1)
#         approval_type = (item.get("approval_type") or "").strip() or None

#         if not member_id:
#             raise HTTPException(status_code=400, detail="결재자 ID가 필요합니다.")

#         if approval_order in used_orders:
#             raise HTTPException(status_code=400, detail="결재 순서는 중복될 수 없습니다.")
#         used_orders.add(approval_order)

#         approver = (
#             db.query(OrgMember)
#             .filter(
#                 OrgMember.id == member_id,
#                 OrgMember.is_active == True,
#             )
#             .first()
#         )
#         if not approver:
#             raise HTTPException(status_code=404, detail=f"ID {member_id} 조직원을 찾을 수 없습니다.")

#         db.add(
#             ApprovalRuleApprover(
#                 rule_id=rule.id,
#                 approver_member_id=member_id,
#                 approval_order=approval_order,
#                 approval_type=approval_type,
#             )
#         )

#     db.commit()
#     db.refresh(rule)

#     return {
#         "status": "ok",
#         "id": rule.id,
#     }


# @app.get("/api/approval-rules")
# def get_approval_rules(db: Session = Depends(get_db)):
#     rules = (
#         db.query(ApprovalRule)
#         .options(
#             joinedload(ApprovalRule.template),
#             joinedload(ApprovalRule.approver_maps).joinedload(ApprovalRuleApprover.approver)
#         )
#         .filter(ApprovalRule.is_active == True)
#         .order_by(ApprovalRule.id.desc())
#         .all()
#     )

#     return [
#         {
#             "id": r.id,
#             "rule_name": r.rule_name,
#             "rule_text": r.rule_text,
#             "template_id": r.template_id,
#             "template_name": r.template.template_name if r.template else "",
#             "approvers": [
#                 {
#                     "id": m.id,
#                     "approver_member_id": m.approver_member_id,
#                     "approval_order": m.approval_order,
#                     "approval_type": m.approval_type,
#                     "approver_name": m.approver.name if m.approver else "",
#                     "approver_title": m.approver.title if m.approver else "",
#                     "approver_email": m.approver.email if m.approver else "",
#                 }
#                 for m in sorted(r.approver_maps, key=lambda x: x.approval_order)
#             ],
#         }
#         for r in rules
#     ]

# 결재 방침 저장/조회--------------------------------------------------------------------------------------------------------
@app.post("/api/approval-rules")
def create_approval_rule(
    payload: dict,
    db: Session = Depends(get_db),
):
    rule = persist_approval_rule(db, payload, source_type="manual", source_name=None)
    db.commit()
    db.refresh(rule)

    return {
        "status": "ok",
        "id": rule.id,
    }


@app.post("/api/approval-rules/preview-guide")
async def preview_approval_rules_guide(
    guide_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not guide_file.filename or not guide_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    file_bytes = await guide_file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="업로드된 파일이 비어 있습니다.")

    guide_text = extract_pdf_text(file_bytes)
    if not guide_text:
        raise HTTPException(status_code=400, detail="PDF에서 텍스트를 추출하지 못했습니다.")

    templates = (
        db.query(DocumentTemplate)
        .filter(DocumentTemplate.is_active == True)
        .order_by(DocumentTemplate.id.asc())
        .all()
    )
    template_list = [
        {"id": t.id, "template_name": t.template_name}
        for t in templates
    ]

    members = (
        db.query(OrgMember)
        .filter(OrgMember.is_active == True)
        .order_by(OrgMember.id.asc())
        .all()
    )
    member_list = [
        {
            "id": m.id,
            "name": m.name,
            "department": m.department,
            "title": m.title,
            "email": m.email,
        }
        for m in members
    ]

    rules = await preview_approval_rules_from_guide(
        guide_text=guide_text,
        templates=template_list,
        org_members=member_list,
    )

    template_map = {t["id"]: t["template_name"] for t in template_list}
    member_map = {m["id"]: m["name"] for m in member_list}

    normalized_rules = []
    for rule in rules:
        template_id = int(rule.get("template_id", 0) or 0)
        approvers = []

        for a in sorted(rule.get("approvers", []), key=lambda x: int(x.get("approval_order", 1))):
            member_id = int(a.get("approver_member_id", 0) or 0)
            if not member_id:
                continue

            approvers.append({
                "approver_member_id": member_id,
                "approver_name": member_map.get(member_id, ""),
                "approval_order": int(a.get("approval_order", 1)),
                "approval_type": a.get("approval_type", "결재"),
            })

        if not rule.get("rule_name") or not rule.get("rule_text") or not template_id or not approvers:
            continue

        normalized_rules.append({
            "rule_name": rule.get("rule_name", ""),
            "rule_text": rule.get("rule_text", ""),
            "template_id": template_id,
            "template_name": template_map.get(template_id, ""),
            "source_excerpt": rule.get("source_excerpt", ""),
            "approvers": approvers,
        })

    return {
        "status": "ok",
        "rules": normalized_rules,
        "parsed_rule_count": len(normalized_rules),
        "source_name": guide_file.filename,
    }


@app.post("/api/approval-rules/save-preview")
def save_preview_approval_rules(
    payload: dict,
    db: Session = Depends(get_db),
):
    rules = payload.get("rules")
    source_name = (payload.get("source_name") or "").strip() or None

    if not isinstance(rules, list) or len(rules) == 0:
        raise HTTPException(status_code=400, detail="저장할 규칙이 없습니다.")

    results = []

    for rule_payload in rules:
        rule = persist_approval_rule(
            db,
            rule_payload,
            source_type="guide",
            source_name=source_name,
        )
        results.append({"id": rule.id})

    db.commit()

    return {
        "status": "ok",
        "saved_rule_count": len(results),
        "results": results,
    }


@app.get("/api/approval-rules")
def get_approval_rules(db: Session = Depends(get_db)):
    rules = (
        db.query(ApprovalRule)
        .options(
            joinedload(ApprovalRule.template),
            joinedload(ApprovalRule.approver_maps).joinedload(ApprovalRuleApprover.approver)
        )
        .filter(ApprovalRule.is_active == True)
        .order_by(ApprovalRule.id.desc())
        .all()
    )

    return [
        {
            "id": r.id,
            "rule_name": r.rule_name,
            "rule_text": r.rule_text,
            "template_id": r.template_id,
            "template_name": r.template.template_name if r.template else "",
            "source_type": r.source_type,
            "source_name": r.source_name,
            "source_excerpt": r.source_excerpt,
            "approvers": [
                {
                    "id": m.id,
                    "approver_member_id": m.approver_member_id,
                    "approval_order": m.approval_order,
                    "approval_type": m.approval_type,
                    "approver_name": m.approver.name if m.approver else "",
                    "approver_title": m.approver.title if m.approver else "",
                    "approver_email": m.approver.email if m.approver else "",
                }
                for m in sorted(r.approver_maps, key=lambda x: x.approval_order)
            ],
        }
        for r in rules
    ]
    
# 문서 생성---------------------------------------------------------------------------------------------------------
# @app.post("/api/process")
# async def process_expense(
#     template_id: int = Form(...),
#     description: str = Form(...),
#     receipt: UploadFile = File(None),
#     db: Session = Depends(get_db),
# ):
#     template = (
#         db.query(DocumentTemplate)
#         .filter(
#             DocumentTemplate.id == template_id,
#             DocumentTemplate.is_active == True,
#         )
#         .first()
#     )
#     if not template:
#         raise HTTPException(status_code=404, detail="선택한 템플릿을 찾을 수 없습니다.")

#     rules = (
#         db.query(ApprovalRule)
#         .options(
#             joinedload(ApprovalRule.approver_maps).joinedload(ApprovalRuleApprover.approver)
#         )
#         .filter(
#             ApprovalRule.template_id == template_id,
#             ApprovalRule.is_active == True,
#         )
#         .order_by(ApprovalRule.id.asc())
#         .all()
#     )

#     if not rules:
#         raise HTTPException(status_code=400, detail="해당 템플릿에 연결된 결재 방침이 없습니다.")

#     org_chart = {}
#     approval_rule_lines = []
#     approval_line = []

#     first_approver = None
#     applied_rule = None
#     recipient_member = None

#     for rule in rules:
#         approval_rule_lines.append(f"- {rule.rule_name}: {rule.rule_text}")

#         sorted_maps = sorted(rule.approver_maps, key=lambda x: x.approval_order)

#         for approver_map in sorted_maps:
#             approver = approver_map.approver
#             if approver:
#                 org_chart[approver.name] = {
#                     "title": approver.title,
#                     "email": approver.email,
#                     "approval_order": approver_map.approval_order,
#                     "approval_type": approver_map.approval_type,
#                 }

#                 approval_line.append(
#                     f"{approver_map.approval_order}차 {approver.name} ({approver.title})"
#                 )

#         # 첫 번째 규칙의 1차 결재자를 기본 수신자로 사용
#         if not first_approver and sorted_maps:
#             first_map = sorted_maps[0]
#             if first_map.approver:
#                 applied_rule = rule
#                 first_approver = first_map.approver
#                 recipient_member = first_map.approver

#     approval_rule_text = "\n".join(approval_rule_lines)

#     if not first_approver:
#         raise HTTPException(status_code=400, detail="1차 결재자 정보를 찾을 수 없습니다.")

#     receipt_b64 = None
#     receipt_mime = None
#     receipt_file_name = None
#     receipt_content_type = None

#     if receipt:
#         receipt_bytes = await receipt.read()
#         receipt_b64 = base64.b64encode(receipt_bytes).decode("utf-8")
#         receipt_mime = receipt.content_type or "image/jpeg"
#         receipt_file_name = receipt.filename
#         receipt_content_type = receipt.content_type

#     if not template.template_schema:
#         raise HTTPException(status_code=400, detail="선택한 템플릿에 JSON Schema가 저장되어 있지 않습니다.")

#     try:
#         template_schema = json.loads(template.template_schema)
#     except Exception:
#         raise HTTPException(status_code=500, detail="템플릿의 JSON Schema 형식이 올바르지 않습니다.")

#     expense_data = await extract_expense_data(
#         template_html=template.html_content,
#         template_name=template.template_name,
#         template_schema=template_schema,
#         description=description,
#         receipt_b64=receipt_b64,
#         receipt_mime=receipt_mime,
#         approval_rules=approval_rule_text,
#         org_chart=org_chart,
#     )

#     if not isinstance(expense_data, dict):
#         raise HTTPException(status_code=500, detail="AI 응답 형식이 올바르지 않습니다.")

#     # AI가 결재자를 잘못 내놔도 무시하고 DB 기준 1차 결재자로 덮어씀
#     expense_data["approver_name"] = first_approver.name

#     # 템플릿에서 결재선 전체를 쓸 수 있도록 보조 필드 추가
#     expense_data["approval_line"] = ", ".join(approval_line)

#     filled_html = fill_template(template.html_content, expense_data)

#     recipient_name = first_approver.name
#     recipient_title = first_approver.title
#     recipient_email = first_approver.email

#     saved_doc = GeneratedDocument(
#         template_id=template.id,
#         applied_rule_id=applied_rule.id if applied_rule else None,
#         recipient_member_id=recipient_member.id if recipient_member else None,
#         document_title=f"{template.template_name} 자동작성본",
#         description=description,
#         receipt_file_name=receipt_file_name,
#         receipt_content_type=receipt_content_type,
#         extracted_json=json.dumps(expense_data, ensure_ascii=False),
#         html_content=filled_html,
#         recipient_name=recipient_name,
#         recipient_email=recipient_email,
#         recipient_title=recipient_title,
#         is_sent=False,
#     )

#     db.add(saved_doc)
#     db.commit()
#     db.refresh(saved_doc)

#     return {
#         "document_id": saved_doc.id,
#         "expense_data": expense_data,
#         "filled_html": filled_html,
#         "recipient_name": recipient_name,
#         "recipient_title": recipient_title,
#         "recipient_email": recipient_email,
#         "template_name": template.template_name,
#         "file_name": template.file_name,
#     }

@app.post("/api/process")
async def process_expense(
    template_id: int = Form(...),
    description: str = Form(...),
    receipts: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    template = (
        db.query(DocumentTemplate)
        .filter(
            DocumentTemplate.id == template_id,
            DocumentTemplate.is_active == True,
        )
        .first()
    )

    if not template:
        raise HTTPException(status_code=404, detail="선택한 템플릿을 찾을 수 없습니다.")

    rules = (
        db.query(ApprovalRule)
        .options(
            joinedload(ApprovalRule.approver_maps).joinedload(ApprovalRuleApprover.approver)
        )
        .filter(
            ApprovalRule.template_id == template_id,
            ApprovalRule.is_active == True,
        )
        .order_by(ApprovalRule.id.asc())
        .all()
    )

    if not rules:
        raise HTTPException(
            status_code=400,
            detail="해당 템플릿에 연결된 결재 방침이 없습니다.",
        )

    org_chart = {}
    approval_rule_lines = []
    approval_line = []
    
    approval_field_values = {
        "approval_manager_name": "",
        "approval_general_manager_name": "",
        "approval_director_name": "",
        "approval_ceo_name": "",
    }

    first_approver = None
    applied_rule = None
    recipient_member = None

    for rule in rules:
        approval_rule_lines.append(f"- {rule.rule_name}: {rule.rule_text}")

        sorted_maps = sorted(rule.approver_maps, key=lambda x: x.approval_order)

        for approver_map in sorted_maps:
            approver = approver_map.approver

            if approver:
                org_chart[approver.name] = {
                    "title": approver.title,
                    "email": approver.email,
                    "approval_order": approver_map.approval_order,
                    "approval_type": approver_map.approval_type,
                }

                approval_line.append(
                    f"{approver_map.approval_order}차 {approver.name} ({approver.title})"
                )
                
                field_key = match_approval_field_by_title(approver.title)

                if field_key and not approval_field_values[field_key]:
                    approval_field_values[field_key] = approver.name

        # 첫 번째 규칙의 1차 결재자를 기본 수신자로 사용
        if not first_approver and sorted_maps:
            first_map = sorted_maps[0]

            if first_map.approver:
                applied_rule = rule
                first_approver = first_map.approver
                recipient_member = first_map.approver

    approval_rule_text = "\n".join(approval_rule_lines)

    if not first_approver:
        raise HTTPException(
            status_code=400,
            detail="1차 결재자 정보를 찾을 수 없습니다.",
        )

    # 여러 영수증 이미지 처리
    receipt_images = []
    receipt_file_names = []
    receipt_content_types = []

    for receipt in receipts:
        if not receipt:
            continue
        
        if receipt.content_type not in ["image/jpeg", "image/png", "image/webp"]:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 파일 형식입니다: {receipt.filename}. JPG, PNG, WEBP 이미지만 업로드해주세요.",
            )

        receipt_bytes = await receipt.read()

        if not receipt_bytes:
            continue

        receipt_mime = receipt.content_type or "image/jpeg"

        receipt_images.append(
            {
                "b64": base64.b64encode(receipt_bytes).decode("utf-8"),
                "mime": receipt_mime,
                "file_name": receipt.filename,
                "content_type": receipt.content_type,
            }
        )

        receipt_file_names.append(receipt.filename)
        receipt_content_types.append(receipt_mime)

    receipt_file_name = ", ".join(receipt_file_names) if receipt_file_names else None
    receipt_content_type = ", ".join(receipt_content_types) if receipt_content_types else None

    if not template.template_schema:
        raise HTTPException(
            status_code=400,
            detail="선택한 템플릿에 JSON Schema가 저장되어 있지 않습니다.",
        )

    try:
        template_schema = json.loads(template.template_schema)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="템플릿의 JSON Schema 형식이 올바르지 않습니다.",
        )

    expense_data = await extract_expense_data(
        template_html=template.html_content,
        template_name=template.template_name,
        template_schema=template_schema,
        description=description,
        receipt_images=receipt_images,
        approval_rules=approval_rule_text,
        org_chart=org_chart,
    )

    if not isinstance(expense_data, dict):
        raise HTTPException(
            status_code=500,
            detail="AI 응답 형식이 올바르지 않습니다.",
        )
        
    schema_properties = template_schema.get("properties", {})

    # 결재자 이름 필드는 AI 결과와 무관하게 DB 결재선 기준으로 강제 주입
    for key, value in approval_field_values.items():
        if key in schema_properties or f"{{{{{key}}}}}" in template.html_content:
            expense_data[key] = value    

    # AI가 결재자를 잘못 내놔도 무시하고 DB 기준 1차 결재자로 덮어씀
    expense_data["approver_name"] = first_approver.name

    # 템플릿에서 결재선 전체를 쓸 수 있도록 보조 필드 추가
    expense_data["approval_line"] = ", ".join(approval_line)

    filled_html = fill_template(template.html_content, expense_data)

    recipient_name = first_approver.name
    recipient_title = first_approver.title
    recipient_email = first_approver.email

    saved_doc = GeneratedDocument(
        template_id=template.id,
        applied_rule_id=applied_rule.id if applied_rule else None,
        recipient_member_id=recipient_member.id if recipient_member else None,
        document_title=f"{template.template_name} 자동작성본",
        description=description,
        receipt_file_name=receipt_file_name,
        receipt_content_type=receipt_content_type,
        extracted_json=json.dumps(expense_data, ensure_ascii=False),
        html_content=filled_html,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        recipient_title=recipient_title,
        is_sent=False,
    )

    db.add(saved_doc)
    db.commit()
    db.refresh(saved_doc)

    return {
        "document_id": saved_doc.id,
        "expense_data": expense_data,
        "filled_html": filled_html,
        "recipient_name": recipient_name,
        "recipient_title": recipient_title,
        "recipient_email": recipient_email,
        "template_name": template.template_name,
        "file_name": template.file_name,
    }
    
# 이메일 발송---------------------------------------------------------------------------------------------------
@app.post("/api/send-email")
async def send_email(payload: dict, db: Session = Depends(get_db)):
    required_fields = [
        "to_email",
        "to_name",
        "requester",
        "template_name",
        "filled_html",
        "expense_data",
    ]

    for field in required_fields:
        if field not in payload:
            raise HTTPException(status_code=400, detail=f"{field} 값이 필요합니다.")

    result = await send_document_email(
        to_email=payload["to_email"],
        to_name=payload["to_name"],
        requester=payload["requester"],
        template_name=payload["template_name"],
        filled_html=payload["filled_html"],
        expense_data=payload["expense_data"],
    )

    document_id = payload.get("document_id")
    if document_id:
        doc = (
            db.query(GeneratedDocument)
            .filter(GeneratedDocument.id == document_id)
            .first()
        )
        if doc:
            doc.is_sent = True
            db.commit()

    return result