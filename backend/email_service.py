import os
import re
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")


LABEL_MAP = {
    "draft_department": "기안부서",
    "draft_date": "기안일자",
    "draft_user": "기안자",
    "subject": "제목",
    "request_department": "요청부서",
    "department": "부서",
    "position": "직급",
    "requester": "청구인",
    "vendor": "거래처",
    "summary_text": "적요",
    "purpose": "목적",
    "total_amount": "총액",
    "supply_amount": "공급가액",
    "vat_amount": "부가세",
    "payment_method": "결제수단",
    "notes": "비고",
    "remarks": "비고",
    "approver_name": "결재자",
    "amount_hangul": "금액 한글",
    "approval_line": "결재선",
}

# 메일 본문에 노출하지 않을 필드
EXCLUDED_KEYS = {
    "items_rows",
    "items_html",
    "table_html",
    "approval_line_html",
    "raw_html",
    "html_content",
}

# 본문에 우선적으로 보여줄 필드 순서
PREFERRED_ORDER = [
    "draft_department",
    "draft_date",
    "draft_user",
    "subject",
    "request_department",
    "department",
    "position",
    "requester",
    "vendor",
    "summary_text",
    "purpose",
    "total_amount",
    "supply_amount",
    "vat_amount",
    "payment_method",
    "remarks",
    "notes",
    "approver_name",
    "approval_line",
]


def _labelize(key: str) -> str:
    return LABEL_MAP.get(key, key.replace("_", " "))


def _is_amount_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(word in lowered for word in [
        "amount", "price", "cost", "total", "supply", "vat", "fee", "budget"
    ])


def _looks_like_html(value) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    return "<tr" in text or "<td" in text or "<table" in text or "<div" in text or "<span" in text


def _format_value(key: str, value) -> str:
    if value is None or value == "":
        return "-"

    if isinstance(value, bool):
        return "예" if value else "아니오"

    if isinstance(value, (int, float)):
        if _is_amount_key(key):
            return f"{value:,.0f}원"
        return str(value)

    if isinstance(value, list):
        if not value:
            return "-"
        return ", ".join(str(v) for v in value)

    if isinstance(value, dict):
        if not value:
            return "-"
        return ", ".join(f"{_labelize(k)}: {_format_value(k, v)}" for k, v in value.items())

    text = str(value).strip()
    if not text:
        return "-"

    # HTML 조각이면 본문에 노출하지 않음
    if _looks_like_html(text):
        return "(본문 생략)"

    # 너무 길면 잘라서 표시
    if len(text) > 120:
        return text[:117] + "..."

    return text


def _ordered_items(expense_data: dict):
    if not isinstance(expense_data, dict):
        return []

    items = []

    # 우선순위 필드 먼저
    for key in PREFERRED_ORDER:
        if key in expense_data and key not in EXCLUDED_KEYS:
            value = expense_data.get(key)
            if value in [None, "", [], {}]:
                continue
            if _looks_like_html(value):
                continue
            items.append((key, value))

    # 나머지 필드 뒤에
    for key, value in expense_data.items():
        if key in EXCLUDED_KEYS or key in PREFERRED_ORDER:
            continue
        if value in [None, "", [], {}]:
            continue
        if _looks_like_html(value):
            continue
        items.append((key, value))

    return items


def _pick_requester(expense_data: dict, fallback: str) -> str:
    for key in ["draft_user", "requester", "employee_name", "user_name"]:
        value = expense_data.get(key)
        if value:
            return str(value).strip()
    return fallback or "작성자"


def _pick_title(template_name: str, expense_data: dict) -> str:
    for key in ["subject", "summary_text", "purpose", "title"]:
        value = expense_data.get(key)
        if value and not _looks_like_html(value):
            text = str(value).strip()
            if text:
                return text
    return template_name


def _build_dynamic_body(
    to_name: str,
    template_name: str,
    requester: str,
    expense_data: dict,
) -> str:
    lines = []
    lines.append(f"{to_name} 님께,")
    lines.append("")
    lines.append(f"{requester}님의 '{template_name}' 결재 요청이 접수되었습니다.")
    lines.append("")
    lines.append("[문서 요약]")

    for key, value in _ordered_items(expense_data):
        formatted = _format_value(key, value)
        if formatted in ["-", "(본문 생략)"]:
            continue
        lines.append(f"- {_labelize(key)}: {formatted}")

    lines.append("")
    lines.append("첨부된 결재서류를 확인하신 후 결재 부탁드립니다.")
    lines.append("")
    lines.append("감사합니다.")

    return "\n".join(lines)


def _safe_filename(text: str) -> str:
    text = str(text or "").strip()
    if not text:
        return "document"
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        text = text.replace(ch, "_")
    return text


async def send_document_email(
    to_email: str,
    to_name: str,
    requester: str,
    template_name: str,
    filled_html: str,
    expense_data: dict,
) -> dict:
    if not SMTP_USER or not SMTP_PASS:
        raise ValueError(".env에 SMTP_USER, SMTP_PASS가 설정되지 않았습니다.")

    real_requester = _pick_requester(expense_data, requester)
    title_text = _pick_title(template_name, expense_data)

    subject = f"[결재 요청] {template_name} - {real_requester}"
    body_text = _build_dynamic_body(
        to_name=to_name,
        template_name=title_text,
        requester=real_requester,
        expense_data=expense_data,
    )

    msg = MIMEMultipart("mixed")
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    attachment = MIMEBase("text", "html")
    attachment.set_payload(filled_html.encode("utf-8"))
    encoders.encode_base64(attachment)

    safe_template_name = _safe_filename(template_name)
    attachment.add_header(
        "Content-Disposition",
        "attachment",
        filename=f"{safe_template_name}.html",
    )
    msg.attach(attachment)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())

    return {
        "status": "sent",
        "to": to_email,
        "subject": subject,
    }