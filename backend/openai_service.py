import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError(".env에 OPENAI_API_KEY가 설정되지 않았습니다.")

client = OpenAI(api_key=api_key)


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

def _extract_json_from_text(raw: str):
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

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

# PDF,html 형식의 결재서류에 {{키}} 형식의 플레이스 홀더로 변환하는 AI
async def convert_template_to_schema(
    source_text: str,
    file_type: str,
    template_name: str,
) -> dict:
    instructions = f"""
너는 회사 결재서류 템플릿 정규화 AI이다.

입력 문서는 {file_type} 원문이다.
이 문서를 재사용 가능한 HTML 템플릿과 JSON 스키마로 변환해야 한다.

반드시 아래 JSON 객체 형식으로만 응답하라.
설명, 해설, 코드블록, 마크다운 없이 순수 JSON만 출력하라.

출력 형식:
{{
  "html_template": "<html>...</html>",
  "json_schema": {{
    "type": "object",
    "properties": {{
      "field_name": {{ "type": "string" }}
    }},
    "required": ["field_name"],
    "additionalProperties": false
  }},
  "placeholder_keys": ["field_name"]
}}

규칙:
1. 문서의 구조, 표, 스타일, 레이아웃은 최대한 유지하라.
2. 예시 데이터(이름, 날짜, 금액, 부서명 등)는 문맥에 맞는 {{{{key}}}} 플레이스홀더로 치환하라.
3. key 이름은 snake_case로 작성하라.
4. html_template 안에 들어가는 플레이스홀더는 반드시 json_schema.properties에 존재해야 한다.
5. placeholder_keys에는 html_template에 실제 사용된 key만 넣어라.
6. json_schema는 이 문서 작성에 필요한 필드만 포함하라.
7. required는 핵심 필드만 넣어라.
8. 추가 설명 없이 JSON만 출력하라.
9. 결재자 이름은 템플릿 본문에 실제로 표시되는 경우에만 placeholder와 schema에 포함하라. 메일 수신자 결정용 내부 필드는 임의로 추가하지 마라.

템플릿 이름:
{template_name}
"""

    response = client.responses.create(
        model="gpt-5.4",
        instructions=instructions,
        input=source_text,
    )

    data = _extract_json_from_text(response.output_text)

    # html_template = data.get("html_template", "").strip()
    # json_schema = data.get("json_schema", {})
    # placeholder_keys = data.get("placeholder_keys", [])

    # if not html_template:
    #     raise ValueError("html_template 생성에 실패했습니다.")

    # if not isinstance(json_schema, dict) or not json_schema:
    #     raise ValueError("json_schema 생성에 실패했습니다.")

    # if not isinstance(placeholder_keys, list):
    #     raise ValueError("placeholder_keys 형식이 올바르지 않습니다.")

    # return {
    #     "html_template": html_template,
    #     "json_schema": json_schema,
    #     "placeholder_keys": placeholder_keys,
    # }
    html_template = data.get("html_template", "").strip()
    json_schema = data.get("json_schema", {})
    placeholder_keys = data.get("placeholder_keys", [])

    if not html_template:
        raise ValueError("html_template 생성에 실패했습니다.")

    normalized = _normalize_template_schema(
        html_template=html_template,
        json_schema=json_schema,
        placeholder_keys=placeholder_keys,
    )

    return normalized    
    

# 조직도를 읽고 json 데이터로 저장하는 AI
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

    response = client.responses.create(
        model="gpt-5.4",
        instructions=instructions,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": f"data:{image_mime};base64,{image_b64}",
                    },
                    {
                        "type": "input_text",
                        "text": "이 조직도 표 이미지를 읽고 조직원 목록 JSON 배열로 변환하세요.",
                    },
                ],
            }
        ],
    )

    raw = _strip_code_fence(response.output_text)
    rows = json.loads(raw)
    return _normalize_org_preview_rows(rows)

# 결재 서류 규정을 읽고 결재 규칙 초안을 작성하는 AI
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

    response = client.responses.create(
        model="gpt-5.4",
        instructions=instructions,
        input="결재 처리 방침 초안을 JSON 배열로 생성하세요.",
    )

    raw = _strip_code_fence(response.output_text)
    return json.loads(raw)

# 결재 서류 자동 작성 AI
async def extract_expense_data(
    template_html: str,
    template_name: str,
    template_schema: dict,
    description: str,
    receipt_b64: str | None,
    receipt_mime: str | None,
    approval_rules: str,
    org_chart: dict,
) -> dict:
    org_list = _build_org_list(org_chart)

    schema_text = json.dumps(template_schema, ensure_ascii=False, indent=2)

    instructions = f"""
너는 회사 결재서류 자동 작성 AI이다.
사용자가 선택한 템플릿 형식과 JSON Schema에 맞춰 문서 작성용 데이터를 추출하라.
사용자의 자연어 설명, 영수증 이미지, 결재 규칙, 조직도를 함께 참고해야 한다.

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

반드시 위 JSON Schema를 만족하는 JSON 객체만 출력하라.
설명, 해설, 코드블록, 마크다운 없이 JSON 객체만 출력하라.

규칙:
1. 반드시 JSON Schema의 properties에 정의된 필드만 사용하라.
2. JSON Schema에 없는 필드는 절대 추가하지 마라.
3. 템플릿 HTML 안의 placeholder 문맥을 참고해서 각 필드값을 자연스럽게 채워라.
4. 영수증 이미지가 있으면 이미지의 정보와 자연어 설명을 함께 참고하되, 이미지 정보가 더 신뢰할 만하면 우선한다.
5. 결재자 관련 필드는 템플릿 본문에 실제로 필요한 경우에만 채워라. 메일 수신자 결정은 서버가 별도로 처리하므로 결재자 추론에 과도하게 집착하지 마라.
6. 숫자형 필드는 숫자로 반환하라. 쉼표, 원, 공백, 문자열 금지.
7. 문자열 필드는 null 대신 가능한 범위에서 추정한 문자열을 넣어라.
8. 날짜 필드는 템플릿 문맥에 맞는 형식으로 작성하라.
9. JSON 외의 어떤 문장도 출력하지 않는다.
"""

    user_content = []

    if receipt_b64 and receipt_mime:
        user_content.append(
            {
                "type": "input_image",
                "image_url": f"data:{receipt_mime};base64,{receipt_b64}",
            }
        )

    user_content.append(
        {
            "type": "input_text",
            "text": f"[사용자 자연어 설명]\n{description}",
        }
    )

    response = client.responses.create(
        model="gpt-5.4",
        instructions=instructions,
        input=[
            {
                "role": "user",
                "content": user_content,
            }
        ],
    )

    raw = _strip_code_fence(response.output_text)
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
            normalized[field_name] = bool(value)

        elif field_type == "array":
            normalized[field_name] = value if isinstance(value, list) else []

        elif field_type == "object":
            normalized[field_name] = value if isinstance(value, dict) else {}

        else:
            normalized[field_name] = "" if value is None else str(value).strip()

    return normalized