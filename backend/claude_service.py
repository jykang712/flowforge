import os
import json
import re
from dotenv import load_dotenv
# from anthropic import Anthropic
from anthropic import AsyncAnthropic

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise ValueError(".env에 ANTHROPIC_API_KEY가 설정되지 않았습니다.")

# client = Anthropic(api_key=api_key)
client = AsyncAnthropic(api_key=api_key)

CLAUDE_TEMPLATE_MODEL = "claude-sonnet-4-6"
CLAUDE_LIGHT_MODEL = "claude-haiku-4-5"

def _claude_text(response) -> str:
    texts = []

    for block in response.content:
        if getattr(block, "type", None) == "text":
            texts.append(block.text)

    return "\n".join(texts).strip()

def _build_org_list(org_chart: dict) -> str:
    lines = []
    for name, info in org_chart.items():
        if isinstance(info, dict):
            title = info.get("title", "")
            email = info.get("email", "")
            approval_order = info.get("approval_order", "")
            approval_type = info.get("approval_type", "")
            lines.append(
                f"- 이름: {name}, 직급: {title}, 이메일: {email}, 결재순서: {approval_order}, 결재유형: {approval_type}"
            )
        else:
            lines.append(f"- 이름: {name}, 이메일: {info}")
    return "\n".join(lines)


def _strip_code_fence(raw: str) -> str:
    return raw.replace("```json", "").replace("```", "").strip()


def _clean_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _clean_email(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value)).strip()
    
def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ["true", "yes", "y", "1", "예", "맞음", "동의"]:
            return True
        if lowered in ["false", "no", "n", "0", "아니오", "아님", "미동의"]:
            return False

    return False

def _normalize_org_preview_rows(rows: list) -> list[dict]:
    normalized = []

    if not isinstance(rows, list):
        return normalized

    for row in rows:
        if not isinstance(row, dict):
            continue

        item = {
            "name": _clean_text(row.get("name")),
            "department": _clean_text(row.get("department")),
            "title": _clean_text(row.get("title")),
            "email": _clean_email(row.get("email")),
        }

        # 완전 빈 행 제거
        if not any(item.values()):
            continue

        # 헤더 행 같은 것 제거
        header_like = {
            item["name"],
            item["department"],
            item["title"],
            item["email"],
        }
        if header_like & {"이름", "부서", "직급", "직책", "이메일"} and (
            item["name"] in {"이름", "성명"} or item["email"] == "이메일"
        ):
            continue

        normalized.append(item)

    return normalized

# def _extract_json_from_text(raw: str):
#     raw = raw.strip().replace("```json", "").replace("```", "").strip()
#     return json.loads(raw)
def _extract_json_from_text(raw: str):
    raw = raw.strip().replace("```json", "").replace("```", "").strip()

    start = raw.find("{")
    end = raw.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"JSON 객체를 찾지 못했습니다. 원문 일부: {raw[:500]}")

    json_text = raw[start:end + 1]

    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        print("===== JSON PARSE ERROR RAW START =====")
        print(json_text[:3000])
        print("===== JSON PARSE ERROR RAW END =====")
        raise ValueError(f"AI 응답 JSON 파싱 실패: {e}")
    
def _extract_template_response(raw: str) -> dict:
    raw = raw.strip()

    html_match = re.search(
        r"<HTML_TEMPLATE>\s*(.*?)\s*</HTML_TEMPLATE>",
        raw,
        re.DOTALL,
    )

    meta_match = re.search(
        r"<JSON_META>\s*(.*?)\s*</JSON_META>",
        raw,
        re.DOTALL,
    )

    if not html_match:
        raise ValueError("AI 응답에서 HTML_TEMPLATE 블록을 찾지 못했습니다.")

    if not meta_match:
        raise ValueError("AI 응답에서 JSON_META 블록을 찾지 못했습니다.")

    html_template = html_match.group(1).strip()
    meta_text = meta_match.group(1).strip()

    try:
        meta = json.loads(meta_text)
    except json.JSONDecodeError as e:
        print("===== JSON_META PARSE ERROR START =====")
        print(meta_text[:3000])
        print("===== JSON_META PARSE ERROR END =====")
        raise ValueError(f"AI 응답 JSON_META 파싱 실패: {e}")

    return {
        "html_template": html_template,
        "json_schema": meta.get("json_schema", {}),
        "placeholder_keys": meta.get("placeholder_keys", []),
        "fields": meta.get("fields", []),
    }

def _infer_field_type(field_name: str) -> str:
    numeric_keywords = [
        "amount",
        "price",
        "cost",
        "total",
        "supply",
        "vat",
        "quantity",
        "count",
        "days",
        "hours",
        "minutes",
    ]

    lowered = (field_name or "").lower()

    for keyword in numeric_keywords:
        if keyword in lowered:
            return "integer"

    return "string"


def _extract_placeholder_keys_from_html(html: str) -> list[str]:
    found = re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", html or "")
    seen = []
    for key in found:
        if key not in seen:
            seen.append(key)
    return seen


def _normalize_template_schema(
    html_template: str,
    json_schema: dict,
    placeholder_keys: list,
) -> dict:
    if not isinstance(json_schema, dict):
        json_schema = {}

    schema_type = json_schema.get("type")
    if schema_type != "object":
        json_schema["type"] = "object"

    properties = json_schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    json_schema["properties"] = properties

    required = json_schema.get("required")
    if not isinstance(required, list):
        required = []
    json_schema["required"] = required

    html_keys = _extract_placeholder_keys_from_html(html_template)

    normalized_keys = []
    if isinstance(placeholder_keys, list):
        for key in placeholder_keys:
            key = _clean_text(key)
            if key and key not in normalized_keys:
                normalized_keys.append(key)

    for key in html_keys:
        if key not in normalized_keys:
            normalized_keys.append(key)

    for key in normalized_keys:
        field = properties.get(key)

        if not isinstance(field, dict):
            field = {}

        if "type" not in field or field["type"] not in {
            "string",
            "integer",
            "number",
            "boolean",
            "array",
            "object",
        }:
            field["type"] = _infer_field_type(key)

        properties[key] = field

    # 공통 결재문서 필드 보정
    # 공통 결재문서 필드 보정
    common_fields = {}

    for key, field_schema in common_fields.items():
        if key not in properties:
            properties[key] = field_schema

        if key not in normalized_keys:
            normalized_keys.append(key)

    # required는 실제 properties에 있는 키만 남김
    required = [key for key in required if key in properties]

    # required가 너무 비면 최소한 앞쪽 핵심 키 몇 개를 넣어줌
    if not required:
        priority_candidates = [
            "requester",
            "employee_name",
            "department",
            "title",
            "subject",
            "summary_text",
            "purpose",
            # "approver_name",
        ]
        for key in priority_candidates:
            if key in properties and key not in required:
                required.append(key)

        if not required:
            required = normalized_keys[: min(3, len(normalized_keys))]

    json_schema["required"] = required
    json_schema["additionalProperties"] = False

    return {
        "html_template": html_template,
        "json_schema": json_schema,
        "placeholder_keys": normalized_keys,
    }
    
def _safe_key(value: str, fallback: str = "field") -> str:
    value = _clean_text(value).lower()
    value = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")

    if not value:
        return fallback

    if re.match(r"^[0-9]", value):
        value = f"{fallback}_{value}"

    return value


def _ui_type_to_schema_type(ui_type: str) -> str:
    if ui_type in ["number", "amount"]:
        return "number"

    if ui_type == "array":
        return "array"

    if ui_type == "boolean":
        return "boolean"

    return "string"


def _schema_type_to_ui_type(schema_type: str, key: str = "") -> str:
    lowered_key = (key or "").lower()

    if schema_type in ["integer", "number"]:
        if any(word in lowered_key for word in ["amount", "price", "cost", "total", "vat"]):
            return "amount"
        return "number"

    if schema_type == "array":
        return "array"

    if schema_type == "boolean":
        return "boolean"

    if any(word in lowered_key for word in ["date", "day"]):
        return "date"

    return "string"


def _normalize_template_fields(
    fields: list,
    json_schema: dict,
    placeholder_keys: list,
) -> list[dict]:
    properties = json_schema.get("properties", {})
    required_keys = set(json_schema.get("required", []))

    if not isinstance(fields, list):
        fields = []

    field_map = {}

    for field in fields:
        if not isinstance(field, dict):
            continue

        key = _safe_key(
            field.get("key")
            or field.get("field_name")
            or field.get("code")
            or "",
            fallback="field",
        )

        if key:
            field_map[key] = field

    normalized = []

    for key in placeholder_keys:
        schema_info = properties.get(key, {})
        field_info = field_map.get(key, {})

        label = (
            field_info.get("label")
            or field_info.get("field_label")
            or schema_info.get("title")
            or schema_info.get("description")
            or key
        )

        schema_type = schema_info.get("type", "string")

        ui_type = (
            field_info.get("type")
            or _schema_type_to_ui_type(schema_type, key)
        )

        if ui_type not in ["string", "text", "date", "number", "amount", "array", "boolean"]:
            ui_type = "string"

        normalized.append(
            {
                "label": _clean_text(label),
                "key": key,
                "type": ui_type,
                "required": key in required_keys,
                "description": _clean_text(
                    field_info.get("description")
                    or schema_info.get("description")
                    or ""
                ),
                "position_hint": _clean_text(
                    field_info.get("position_hint")
                    or field_info.get("context")
                    or ""
                ),
            }
        )

    return normalized


def _build_schema_from_confirmed_fields(
    fields: list[dict],
) -> tuple[dict, list[str], list[dict]]:
    properties = {}
    required = []
    placeholder_keys = []
    normalized_fields = []

    for index, field in enumerate(fields or []):
        if not isinstance(field, dict):
            continue

        label = _clean_text(field.get("label"))
        key = _safe_key(
            field.get("key") or label,
            fallback=f"field_{index + 1}",
        )

        ui_type = field.get("type") or "string"

        if ui_type not in ["string", "text", "date", "number", "amount", "array", "boolean"]:
            ui_type = "string"

        schema_type = _ui_type_to_schema_type(ui_type)

        schema_field = {
            "type": schema_type,
            "description": _clean_text(field.get("description") or label or key),
        }

        if ui_type == "array":
            schema_field["items"] = {"type": "object"}

        properties[key] = schema_field
        placeholder_keys.append(key)

        if field.get("required"):
            required.append(key)

        normalized_fields.append(
            {
                "label": label or key,
                "key": key,
                "type": ui_type,
                "required": bool(field.get("required")),
                "description": _clean_text(field.get("description")),
                "position_hint": _clean_text(field.get("position_hint")),
            }
        )

    json_schema = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }

    return json_schema, placeholder_keys, normalized_fields

# PDF, HTML, DOCX, HWPX 형식의 결재서류에 {{key}} 형식의 플레이스홀더를 넣고 schema/fields를 생성하는 AI ---------------------------------------------------
async def convert_template_to_schema(
    source_text: str,
    file_type: str,
    template_name: str,
    confirmed_fields: list[dict] | None = None,
) -> dict:
    confirmed_fields = confirmed_fields or []

    if confirmed_fields:
        confirmed_fields_text = json.dumps(
            confirmed_fields,
            ensure_ascii=False,
            indent=2,
        )

        field_rule = f"""
[사용자가 최종 확정한 자동 입력 항목]
{confirmed_fields_text}

중요:
- 반드시 위 확정 항목만 사용하라.
- html_template 안의 플레이스홀더 key는 위 확정 항목의 key만 사용하라.
- 사용자가 삭제한 항목은 html_template, json_schema, placeholder_keys, fields에 포함하지 마라.
- 사용자가 추가한 항목은 position_hint와 문서 문맥을 참고해 가장 자연스러운 위치에 {{{{key}}}} 형태로 반영하라.
"""
    else:
        field_rule = """
아직 사용자가 확정한 자동 입력 항목은 없다.
문서 원문과 템플릿 이름을 보고 자동으로 채워야 할 항목 후보를 추천하라.
"""

    instructions = f"""
너는 회사 결재서류 템플릿 정규화 AI이다.

입력 문서는 {file_type} 원문이다.
템플릿 이름은 "{template_name}"이다.
DOCX/HWPX 입력의 경우 서버에서 추출한 텍스트와 표 구조가 원문으로 제공되므로, 줄바꿈과 | 기호로 구분된 표 행을 참고해 HTML 표 구조로 자연스럽게 재현하라.

이 문서를 재사용 가능한 HTML 템플릿, JSON Schema, 사용자 검수용 자동 입력 항목 목록으로 변환해야 한다.

{field_rule}

반드시 아래 JSON 객체 형식으로만 응답하라.
설명, 해설, 코드블록, 마크다운은 절대 출력하지 마라.

출력 형식:

<HTML_TEMPLATE>
<html>
...
</html>
</HTML_TEMPLATE>

<JSON_META>
{{
  "json_schema": {{
    "type": "object",
    "properties": {{
      "field_name": {{
        "type": "string",
        "description": "필드 설명"
      }}
    }},
    "required": ["field_name"],
    "additionalProperties": false
  }},
  "placeholder_keys": ["field_name"],
  "fields": [
    {{
      "label": "화면에 표시할 항목명",
      "key": "field_name",
      "type": "string",
      "required": true,
      "description": "이 항목이 문서에서 의미하는 내용",
      "position_hint": "문서 내에서 이 값이 들어가는 위치 설명"
    }}
  ]
}}
</JSON_META>

규칙:
1. 문서 종류는 template_name과 원문 내용을 함께 보고 판단하라.
2. 문서의 제목, 섹션, 표 구조, 항목 순서는 최대한 유지하라.
3. 원문 파일의 레이아웃, 문구, 표 구조, 줄바꿈, 항목명, 표시 순서, 제목 표현은 가능한 한 그대로 유지하라.
4. 단순히 값을 입력해야 하는 부분만 {{{{key}}}} 플레이스홀더로 치환하고, 원문에 있는 고정 문구는 임의로 바꾸거나 요약하거나 재작성하지 마라.
5. 원문에 존재하는 빈칸, 괄호, 서명란, 결재란, 표 셀 구조는 삭제하지 말고 HTML 안에 최대한 동일한 형태로 보존하라.
6. 디자인을 새로 만들기보다 원문 문서의 시각적 구조를 HTML로 재현하는 것을 우선하라.
7. HTML을 만들 때 원문에 없는 불필요한 섹션이나 항목을 만들지 마라.
8. 사용자가 작성해야 하는 값은 {{{{key}}}} 형식의 플레이스홀더로 치환하라.
9. key 이름은 영어 snake_case로 작성하라.
10. html_template 안에 들어가는 placeholder key는 반드시 json_schema.properties와 placeholder_keys에 포함하라.
11. placeholder_keys에는 html_template에 실제 사용된 key만 넣어라.
12. fields 배열에는 사용자가 화면에서 확인할 자동 입력 항목만 넣어라.
13. fields.label은 사용자가 이해하기 쉬운 한글 항목명으로 작성하라.
14. fields.key는 json_schema.properties의 key와 정확히 일치해야 한다.
15. fields.type은 string, text, date, number, amount, array, boolean 중 하나만 사용하라.
16. json_schema.properties.type은 string, number, integer, boolean, array, object 중 하나만 사용하라.
17. required는 문서 작성에 핵심적인 필드만 넣어라.
18. 결재자 이름은 템플릿 본문에 실제로 표시되는 경우에만 placeholder와 schema에 포함하라.
19. 메일 수신자 결정용 내부 필드는 임의로 추가하지 마라.
20. JSON_META 안에는 html_template을 절대 넣지 마라.
21. HTML은 반드시 HTML_TEMPLATE 블록 안에만 출력하라.
22. JSON_META는 반드시 json.loads로 파싱 가능한 유효한 JSON만 출력하라.
23. HTML_TEMPLATE, JSON_META 외의 어떤 문장도 출력하지 마라.
"""

    response = await client.messages.create(
        model=CLAUDE_TEMPLATE_MODEL,
        max_tokens=8192,
        temperature=0,
        system=instructions,
        messages=[
            {
                "role": "user",
                # "content": source_text,
                "content": (
                    "[문서 원문]\n"
                    f"{source_text}\n\n"
                    "[중요]\n"
                    "응답은 반드시 <HTML_TEMPLATE>...</HTML_TEMPLATE>와 "
                    "<JSON_META>...</JSON_META> 두 블록만 포함하세요. "
                    "HTML은 JSON 안에 넣지 말고 HTML_TEMPLATE 블록에 그대로 작성하세요. "
                    "JSON_META 안에는 json_schema, placeholder_keys, fields만 포함하세요."
                ),
            }
        ],
    )

    # data = _extract_json_from_text(_claude_text(response))
    raw_text = _claude_text(response)

    print("===== CLAUDE RAW RESPONSE START =====")
    print(raw_text[:3000])
    print("===== CLAUDE RAW RESPONSE END =====")

    data = _extract_template_response(raw_text)

    html_template = data.get("html_template", "").strip()
    json_schema = data.get("json_schema", {})
    placeholder_keys = data.get("placeholder_keys", [])
    fields = data.get("fields", [])

    if not html_template:
        raise ValueError("html_template 생성에 실패했습니다.")

    normalized = _normalize_template_schema(
        html_template=html_template,
        json_schema=json_schema,
        placeholder_keys=placeholder_keys,
    )

    if confirmed_fields:
        confirmed_schema, confirmed_keys, confirmed_normalized_fields = (
            _build_schema_from_confirmed_fields(confirmed_fields)
        )

        html_keys = _extract_placeholder_keys_from_html(normalized["html_template"])

        extra_keys = [key for key in html_keys if key not in confirmed_keys]
        if extra_keys:
            for key in extra_keys:
                normalized["html_template"] = re.sub(
                    r"\{\{\s*" + re.escape(key) + r"\s*\}\}",
                    "",
                    normalized["html_template"],
                )

        html_keys = _extract_placeholder_keys_from_html(normalized["html_template"])
        missing_keys = [key for key in confirmed_keys if key not in html_keys]

        if missing_keys:
            raise ValueError(
                "확정한 자동 입력 항목이 HTML 템플릿에 반영되지 않았습니다: "
                + ", ".join(missing_keys)
            )

        confirmed_schema["properties"] = {
            key: confirmed_schema["properties"][key]
            for key in confirmed_keys
            if key in confirmed_schema["properties"]
        }

        confirmed_schema["required"] = [
            key for key in confirmed_schema.get("required", [])
            if key in confirmed_schema["properties"]
        ]

        normalized["json_schema"] = confirmed_schema
        normalized["placeholder_keys"] = confirmed_keys
        normalized["fields"] = confirmed_normalized_fields

    else:
        normalized["fields"] = _normalize_template_fields(
            fields=fields,
            json_schema=normalized["json_schema"],
            placeholder_keys=normalized["placeholder_keys"],
        )

    return normalized
    

# 조직도를 읽고 json 데이터로 저장하는 AI ------------------------------------------------------------------------------
async def preview_org_members_from_image(
    image_b64: str,
    image_mime: str,
) -> list[dict]:
    instructions = """
너는 회사 조직도/인사표/주소록 표 이미지를 읽어 조직원 정보를 JSON 배열로 구조화하는 AI이다.

반드시 JSON 배열만 출력하라.
설명, 해설, 코드블록, 마크다운 없이 순수 JSON만 출력하라.

출력 형식:
[
  {
    "name": "홍길동",
    "department": "개발팀",
    "title": "팀장",
    "email": "hong@company.com"
  }
]

규칙:
1. 표의 각 사람 행을 하나의 객체로 만들어라.
2. 헤더 행은 제외하라.
3. 이름, 부서, 직급(또는 직책/직급), 이메일 컬럼을 최대한 정확히 읽어라.
4. 직책/직급처럼 합쳐진 컬럼이면 title에 그대로 넣어라.
5. 이메일은 공백 없이 반환하라.
6. 보이지 않거나 불명확한 값은 빈 문자열로 둬라.
7. 추측하지 말고 이미지에 실제로 보이는 정보만 사용하라.
8. 이름/직급/이메일이 모두 비어 있는 행은 제외하라.
"""

    response = await client.messages.create(
        model=CLAUDE_LIGHT_MODEL,
        max_tokens=4096,
        temperature=0,
        system=instructions,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_mime,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "이 조직도 표 이미지를 읽고 조직원 목록 JSON 배열로 변환하세요.",
                    },
                ],
            }
        ],
    )

    raw = _strip_code_fence(_claude_text(response))
    rows = json.loads(raw)
    return _normalize_org_preview_rows(rows)

# 결재 서류 규정을 읽고 결재 규칙 초안을 작성하는 AI --------------------------------------------------------------------------------------
async def preview_approval_rules_from_guide(
    guide_text: str,
    templates: list[dict],
    org_members: list[dict],
) -> list[dict]:
    template_lines = []
    for t in templates:
        template_lines.append(
            f"- template_id: {t['id']}, template_name: {t['template_name']}"
        )

    org_lines = []
    for m in org_members:
        org_lines.append(
            f"- member_id: {m['id']}, name: {m['name']}, department: {m.get('department','')}, title: {m['title']}, email: {m['email']}"
        )

    instructions = f"""
너는 회사 결재 처리 방침 초안을 만드는 AI이다.
사용자가 업로드한 지침서를 읽고, 저장 가능한 결재 처리 방침 후보를 JSON 배열로 생성하라.

[사용 가능한 템플릿 목록]
{chr(10).join(template_lines)}

[사용 가능한 조직도 목록]
{chr(10).join(org_lines)}

[지침서 내용]
{guide_text[:45000]}

반드시 JSON 배열만 출력하라.
설명, 해설, 코드블록, 마크다운 없이 순수 JSON만 출력하라.

출력 형식:
[
  {{
    "rule_name": "규칙명",
    "rule_text": "규칙 설명",
    "template_id": 1,
    "source_excerpt": "지침서 근거 문장",
    "approvers": [
      {{
        "approver_member_id": 3,
        "approval_order": 1,
        "approval_type": "결재"
      }}
    ]
  }}
]

규칙:
1. 반드시 제공된 template_id 중 하나만 사용하라.
2. 반드시 제공된 approver_member_id 중 하나만 사용하라.
3. approval_type은 "결재", "합의", "최종승인", "참조" 중 하나만 사용하라.
4. approvers는 approval_order 오름차순으로 구성하라.
5. 지침서에 근거가 명확한 규칙만 생성하라.
6. 너무 애매하면 생성하지 말라.
7. source_excerpt에는 규칙 판단의 핵심 근거 문장을 짧게 넣어라.
"""

    response = await client.messages.create(
        model=CLAUDE_LIGHT_MODEL,
        max_tokens=8192,
        temperature=0,
        system=instructions,
        messages=[
            {
                "role": "user",
                "content": "결재 처리 방침 초안을 JSON 배열로 생성하세요.",
            }
        ],
    )

    raw = _strip_code_fence(_claude_text(response))
    return json.loads(raw)

# 결재 서류 자동 작성 AI -------------------------------------------------------------------------------------------------------
async def extract_expense_data(
    template_html: str,
    template_name: str,
    template_schema: dict,
    description: str,
    receipt_images: list[dict] | None = None,
    approval_rules: str = "",
    org_chart: dict | None = None,
) -> dict:
    receipt_images = receipt_images or []
    org_chart = org_chart or {}

    org_list = _build_org_list(org_chart)

    schema_text = json.dumps(template_schema, ensure_ascii=False, indent=2)

    receipt_count = len(receipt_images)

    instructions = f"""
너는 회사 결재서류 자동 작성 AI이다.
사용자가 선택한 템플릿 형식과 JSON Schema에 맞춰 문서 작성용 데이터를 추출하라.
사용자의 자연어 설명, 여러 장의 영수증 이미지, 결재 규칙, 조직도를 함께 참고해야 한다.

=== 선택된 템플릿 이름 ===
{template_name}

=== 선택된 템플릿 HTML ===
{template_html}

=== 이 템플릿의 JSON Schema ===
{schema_text}

=== 결재 규칙 ===
{approval_rules}

=== 조직도 ===
{org_list}

=== 첨부된 영수증 이미지 수 ===
{receipt_count}개

반드시 위 JSON Schema를 만족하는 JSON 객체만 출력하라.
설명, 해설, 코드블록, 마크다운 없이 JSON 객체만 출력하라.

규칙:
1. 반드시 JSON Schema의 properties에 정의된 필드만 사용하라.
2. JSON Schema에 없는 필드는 절대 추가하지 마라.
3. 템플릿 HTML 안의 placeholder 문맥을 참고해서 각 필드값을 자연스럽게 채워라.
4. 영수증 이미지가 여러 장 있으면 모든 이미지를 함께 확인하라.
5. 여러 영수증에 금액, 품목, 날짜가 나누어져 있으면 문서 목적에 맞게 합산하거나 정리하라.
6. 자연어 설명과 영수증 정보가 충돌하면 영수증 이미지의 실제 정보를 더 우선하라.
7. 영수증 이미지가 일부 흐리거나 누락된 정보가 있으면 자연어 설명을 보조 근거로 사용하라.
8. 결재자 관련 필드는 템플릿 본문에 실제로 필요한 경우에만 채워라. 메일 수신자 결정은 서버가 별도로 처리하므로 결재자 추론에 과도하게 집착하지 마라.
9. 숫자형 필드는 숫자로 반환하라. 쉼표, 원, 공백, 문자열 금지.
10. 문자열 필드는 null 대신 가능한 범위에서 추정한 문자열을 넣어라.
11. 날짜 필드는 템플릿 문맥에 맞는 형식으로 작성하라.
12. 배열 필드가 있으면 여러 영수증의 품목을 가능한 한 행 단위로 정리하라.
13. JSON 외의 어떤 문장도 출력하지 않는다.
"""

    user_content = []

    user_content.append(
        {
            "type": "text",
            "text": f"[사용자 자연어 설명]\n{description}",
        }
    )

    for index, receipt in enumerate(receipt_images, start=1):
        receipt_b64 = receipt.get("b64")
        receipt_mime = receipt.get("mime") or "image/jpeg"
        file_name = receipt.get("file_name") or f"receipt_{index}"

        if not receipt_b64:
            continue

        user_content.append(
            {
                "type": "text",
                "text": f"[영수증 이미지 {index}] 파일명: {file_name}",
            }
        )

        user_content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": receipt_mime,
                    "data": receipt_b64,
                },
            }
        )

    response = await client.messages.create(
        model=CLAUDE_LIGHT_MODEL,
        max_tokens=8192,
        temperature=0,
        system=instructions,
        messages=[
            {
                "role": "user",
                "content": user_content,
            }
        ],
    )

    raw = _strip_code_fence(_claude_text(response))
    data = json.loads(raw)

    if not isinstance(data, dict):
        raise ValueError("AI 응답이 JSON 객체 형식이 아닙니다.")

    properties = template_schema.get("properties", {})
    normalized = {}

    for field_name, field_schema in properties.items():
        field_type = field_schema.get("type")
        value = data.get(field_name)

        if field_type == "integer":
            try:
                normalized[field_name] = int(value or 0)
            except (TypeError, ValueError):
                normalized[field_name] = 0

        elif field_type == "number":
            try:
                normalized[field_name] = float(value or 0)
            except (TypeError, ValueError):
                normalized[field_name] = 0

        elif field_type == "boolean":
            normalized[field_name] = _to_bool(value)

        elif field_type == "array":
            normalized[field_name] = value if isinstance(value, list) else []

        elif field_type == "object":
            normalized[field_name] = value if isinstance(value, dict) else {}

        else:
            normalized[field_name] = "" if value is None else str(value).strip()

    return normalized