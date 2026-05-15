import os
import json
import re
import textwrap
from dotenv import load_dotenv
from anthropic import AsyncAnthropic
from bs4 import BeautifulSoup

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise ValueError(".env에 ANTHROPIC_API_KEY가 설정되지 않았습니다.")

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

# --------------------------------------------------------------------------------------------------
def _compact_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _compact_org_members_for_prompt(org_members: list[dict]) -> str:
    lines = []
    for m in org_members or []:
        lines.append(
            f"{m.get('id','')}|{_clean_text(m.get('name'))}|{_clean_text(m.get('department'))}|{_clean_text(m.get('title'))}|{_clean_email(m.get('email'))}"
        )
    return "\n".join(lines)


def _compact_templates_for_prompt(templates: list[dict]) -> str:
    return "\n".join(
        f"{t.get('id','')}|{_clean_text(t.get('template_name'))}"
        for t in templates or []
    )
    
def _filter_approval_guide_text(guide_text: str, max_chars: int = 45000) -> str:
    if not guide_text:
        return ""

    keywords = [
        "결재", "승인", "합의", "전결", "참조", "검토", "확인", "보고",
        "담당", "팀장", "부서장", "본부장", "임원", "대표", "대표이사",
        "사장", "이사", "부장", "과장",
        "금액", "만원", "원", "이상", "이하", "초과", "미만",
        "출장", "지출", "비용", "구매", "발주", "정산", "품의", "신청",
        "처리", "규정", "기준", "절차", "권한", "위임"
    ]

    lines = [line.strip() for line in re.split(r"[\n\r]+", guide_text) if line.strip()]
    picked_indexes = set()

    context_size = 4

    for i, line in enumerate(lines):
        if any(keyword in line for keyword in keywords):
            start = max(0, i - context_size)
            end = min(len(lines), i + context_size + 1)

            for j in range(start, end):
                picked_indexes.add(j)

    picked = [lines[i] for i in sorted(picked_indexes)]
    picked_text = "\n".join(picked).strip()

    # 필터 결과가 너무 적으면 필터링 실패로 보고 원문 앞부분 사용
    if len(picked_text) < 1500:
        return _clean_text(guide_text)[:max_chars]

    return picked_text[:max_chars]

def _build_field_context_from_schema(template_schema: dict) -> list[dict]:
    properties = template_schema.get("properties", {})
    required = set(template_schema.get("required", []))
    result = []

    for key, info in properties.items():
        if not isinstance(info, dict):
            continue

        item = {
            "k": key,
            "t": info.get("type", "string"),
        }

        if key in required:
            item["req"] = 1

        desc = _clean_text(info.get("description"))
        if desc:
            item["desc"] = desc[:80]

        title = _clean_text(info.get("title"))
        if title:
            item["label"] = title[:40]

        result.append(item)

    return result
# ----------------------------------------------------------------------------------------------------
    
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

def _extract_json_from_text(raw: str):
    raw = (raw or "").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        start = raw.find("{")
        end = raw.rfind("}")

        if start != -1 and end != -1 and end > start:
            candidate = raw[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        preview = raw[:1000]
        raise ValueError(
            f"AI가 올바른 JSON을 반환하지 않았습니다. "
            f"JSON 오류: {str(e)} / 응답 일부: {preview}"
        )

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
                "cell_id": _clean_text(field_info.get("cell_id")),
                "locator": field_info.get("locator") if isinstance(field_info.get("locator"), dict) else {},
                "source": _clean_text(field_info.get("source")),
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
        
        desc_parts = [
            _clean_text(field.get("description")),
            _clean_text(label),
            _clean_text(field.get("position_hint")),
        ]
        desc = " / ".join([x for x in desc_parts if x])
        # schema_field = {
        #     "type": schema_type,
        #     "description": _clean_text(field.get("description") or label or key),
        # }
        schema_field = {
            "type": schema_type,
            "description": desc or key,
        }

        if ui_type == "array":
            schema_field["items"] = {"type": "object"}

        properties[key] = schema_field
        # placeholder_keys.append(key)
        if key not in placeholder_keys:
            placeholder_keys.append(key)

        if field.get("required"):
            required.append(key)

        locations = _get_field_locations(field)
        cell_ids = _unique_texts([location.get("cell_id") for location in locations])

        normalized_fields.append(
            {
                "label": label or key,
                "key": key,
                "type": ui_type,
                "required": bool(field.get("required")),
                "description": _clean_text(field.get("description")),
                "position_hint": _clean_text(field.get("position_hint")),

                # 기존 호환
                "cell_id": cell_ids[0] if cell_ids else "",
                "locator": locations[0] if locations else {},

                # 여러 위치 지원
                "cell_ids": cell_ids,
                "locators": locations,

                "source": _clean_text(field.get("source")),
            }
        )

    json_schema = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }

    return json_schema, placeholder_keys, normalized_fields

def _is_blank_cell(cell) -> bool:
    text = cell.get_text(" ", strip=True)

    if text:
        return False

    return True


def _empty_schema_result(html_template: str, layout_type: str, support_level: str):
    return {
        "html_template": html_template,
        "json_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "placeholder_keys": [],
        "fields": [],
        "analysis_mode": layout_type,
        "support_level": support_level,
    }


def _strip_locator_attrs(soup):
    for tag in soup.find_all(attrs={"data-cell-id": True}):
        del tag["data-cell-id"]

    for tag in soup.find_all(attrs={"data-locator-type": True}):
        del tag["data-locator-type"]

    return soup

def _remove_scripts(soup):
    for tag in soup.find_all(["script", "noscript"]):
        tag.decompose()
    return soup

def _set_cell_locator(tag, cell_id: str, locator_type: str):
    tag["data-cell-id"] = cell_id
    tag["data-locator-type"] = locator_type


def _clean_label_text(text: str) -> str:
    text = _clean_text(text)
    text = text.replace("+", "").replace("-", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _camel_to_snake(value: str) -> str:
    value = _clean_text(value)

    if not value:
        return ""

    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    value = re.sub(r"_+", "_", value).strip("_").lower()

    return value


def _field_key_from_label(label: str, fallback: str) -> str:
    normalized_label = _clean_label_text(label).replace(" ", "")

    known_map = {
        "문서번호": "document_number",
        "작성일자": "draft_date",
        "기안일": "draft_date",
        "작성부서": "draft_department",
        "기안부서": "draft_department",
        "작성자": "draft_person",
        "작 성 자": "draft_person",
        "기안자": "draft_person",
        "프로젝트코드": "project_code",
        "프로젝트명": "project_name",
        "소속": "department",
        "직위": "position",
        "성명": "name",
        "출장기간": "trip_period",
        "출장지": "trip_destination",
        "출장처": "trip_destination",
        "출장목적": "trip_purpose",
        "신청금액": "advance_amount",
        "출납": "cashier_note",
        "예정정산일": "expected_settlement_date",
        "비고": "note",
        "교통편": "transportation_type",
        "이용구간": "transportation_route",
        "금액": "amount",
        "숙박비": "lodging_amount",
        "일비": "daily_allowance_amount",
        "합계": "total_amount",
        "정산액": "settlement_amount",
        "대표이사": "approval_ceo_name",
        "대표": "approval_ceo_name",
        "이사": "approval_director_name",
        "부장": "approval_general_manager_name",
        "과장": "approval_manager_name",
        "출장자소속": "traveler_department",
        "출장자직위": "traveler_position",
        "출장자성명": "traveler_name",
        "동행자소속": "companion_department",
        "동행자직위": "companion_position",
        "동행자성명": "companion_name",
        "고객정보성명": "customer_name",
        "고객정보직위": "customer_position",
        "고객정보업체명": "customer_company",
        "고객정보연락처": "customer_contact",
        "프로젝트코드": "project_code",
        "프로젝트명": "project_name",
        "출장기간": "trip_period",
        "출장지": "trip_destination",
        "출장목적": "trip_purpose",
    }

    if normalized_label in known_map:
        return known_map[normalized_label]

    if "문서번호" in normalized_label:
        return "document_number"
    if "작성일" in normalized_label or "기안일" in normalized_label:
        return "draft_date"
    if "작성부서" in normalized_label or "기안부서" in normalized_label:
        return "draft_department"
    if "작성자" in normalized_label or "기안자" in normalized_label:
        return "draft_person"
    if "프로젝트코드" in normalized_label:
        return "project_code"
    if "프로젝트명" in normalized_label:
        return "project_name"
    if "출장기간" in normalized_label:
        return "trip_period"
    if "출장지" in normalized_label or "출장처" in normalized_label:
        return "trip_destination"
    if "출장목적" in normalized_label:
        return "trip_purpose"
    if "신청금액" in normalized_label:
        return "advance_amount"
    if "정산액" in normalized_label:
        return "settlement_amount"

    return fallback

def _normalize_korean_label(text: str) -> str:
    text = _clean_text(text)
    text = text.replace("+", "").replace("-", "")
    text = re.sub(r"\s+", "", text)
    return text


def _get_table_cell_grid(table):
    grid = []
    rowspan_map = {}

    for r_idx, tr in enumerate(table.find_all("tr")):
        row = []
        c_idx = 0

        # 이전 row에서 내려온 rowspan 채우기
        while (r_idx, c_idx) in rowspan_map:
            row.append(rowspan_map[(r_idx, c_idx)])
            c_idx += 1

        for cell in tr.find_all(["td", "th"], recursive=False):
            while (r_idx, c_idx) in rowspan_map:
                row.append(rowspan_map[(r_idx, c_idx)])
                c_idx += 1

            colspan = int(cell.get("colspan") or 1)
            rowspan = int(cell.get("rowspan") or 1)

            info = {
                "cell": cell,
                "row": r_idx,
                "col_start": c_idx,
                "col_end": c_idx + colspan - 1,
                "text": _normalize_korean_label(cell.get_text(" ", strip=True)),
            }

            for _ in range(colspan):
                row.append(info)
                c_idx += 1

            if rowspan > 1:
                for rr in range(r_idx + 1, r_idx + rowspan):
                    for cc in range(info["col_start"], info["col_end"] + 1):
                        rowspan_map[(rr, cc)] = info

        grid.append(row)

    return grid


def _find_cell_info_in_grid(grid, target_cell):
    for row in grid:
        for info in row:
            if info and info.get("cell") is target_cell:
                return info
    return None


def _infer_component_label_from_table(comp) -> tuple[str, str]:
    """
    전자결재 HTML의 comp_wrap이 들어간 td 기준으로:
    - 왼쪽 라벨
    - 위쪽 헤더
    - rowspan 섹션 라벨
    을 조합해 label/key 힌트를 만든다.
    """
    td = comp.find_parent(["td", "th"])
    table = comp.find_parent("table")

    if not td or not table:
        return "", ""

    grid = _get_table_cell_grid(table)
    current = _find_cell_info_in_grid(grid, td)

    if not current:
        return "", ""

    row_idx = current["row"]
    col_start = current["col_start"]
    col_end = current["col_end"]

    labels = []

    # 1) 같은 행 왼쪽 라벨
    if row_idx < len(grid):
        row = grid[row_idx]
        for c in range(0, min(col_start, len(row))):
            info = row[c]
            if info and info["cell"] is not td and info.get("text"):
                labels.append(info["text"])

    # 2) 위쪽 행에서 같은 열 범위와 겹치는 헤더
    for r in range(row_idx - 1, -1, -1):
        if r >= len(grid):
            continue

        for info in grid[r]:
            if not info or not info.get("text"):
                continue

            overlap = not (
                info["col_end"] < col_start or info["col_start"] > col_end
            )

            if overlap and info["cell"] is not td:
                labels.append(info["text"])

    # 중복 제거
    deduped = []
    for label in labels:
        if label and label not in deduped:
            deduped.append(label)

    # 너무 긴 문구 제거
    deduped = [
        x for x in deduped
        if len(x) <= 20 and x not in ["아래와같이출장계를제출합니다"]
    ]

    # 예: 출장자 + 소속 / 고객정보 + 성명
    section = ""
    column = ""

    section_candidates = ["출장자", "동행자", "고객정보"]
    for item in deduped:
        if item in section_candidates:
            section = item

    column_candidates = [
        "소속", "직위", "성명", "업체명", "연락처",
        "프로젝트코드", "프로젝트명", "출장기간", "출장지", "출장목적",
        "문서번호", "작성일자", "작성부서", "작성자"
    ]
    for item in deduped:
        if item in column_candidates:
            column = item
            break

    if section and column:
        return f"{section} {column}", f"{section}_{column}"

    if column:
        return column, column

    if deduped:
        return deduped[-1], deduped[-1]

    return "", ""


def _classify_template_layout(soup) -> str:
    if soup.select(".comp_wrap[data-cid], .comp_wrap[data-dsl]"):
        return "component_html"

    if soup.select(".hpa .hce, .htb .hce"):
        return "positioned_div_html"

    if soup.find("table"):
        return "table_html"

    return "manual_html"

# ---------------------------------------------------------------------------------------------------------
def _collect_above_labels(grid, row_idx: int, col_start: int, col_end: int) -> list[str]:
    labels = []

    for r in range(row_idx - 1, -1, -1):
        if r >= len(grid):
            continue

        seen_cells = set()

        for info in grid[r]:
            if not info:
                continue

            cell = info.get("cell")
            if id(cell) in seen_cells:
                continue

            seen_cells.add(id(cell))

            text = _clean_label_text(info.get("text", ""))

            if not text:
                continue

            overlap = not (
                info["col_end"] < col_start or info["col_start"] > col_end
            )

            if overlap:
                labels.append(text)

    deduped = []
    for label in labels:
        if label and label not in deduped:
            deduped.append(label)

    return deduped[:5]


def _collect_left_labels(grid, row_idx: int, col_start: int) -> list[str]:
    if row_idx >= len(grid):
        return []

    labels = []
    seen_cells = set()

    for c in range(0, min(col_start, len(grid[row_idx]))):
        info = grid[row_idx][c]

        if not info:
            continue

        cell = info.get("cell")
        if id(cell) in seen_cells:
            continue

        seen_cells.add(id(cell))

        text = _clean_label_text(info.get("text", ""))

        if text:
            labels.append(text)

    deduped = []
    for label in labels:
        if label and label not in deduped:
            deduped.append(label)

    return deduped[-5:]


def _is_approval_label(text: str) -> bool:
    text = _normalize_korean_label(text)

    approval_words = [
        "담당",
        "팀장",
        "담당임원",
        "임원",
        "사장",
        "대표",
        "대표이사",
        "과장",
        "부장",
        "이사",
        "총무팀",
        "선생팀",
    ]

    return any(word in text for word in approval_words)

def _extract_visible_text(tag) -> str:
    """
    DOCX -> HTML 변환 결과에서
    <p><font>20</font><font>년</font><font>월</font>...</p>
    처럼 잘게 쪼개진 텍스트를 사람이 보는 문자열로 정리한다.
    """
    if not tag:
        return ""

    parts = []

    for text in tag.stripped_strings:
        text = str(text).strip()
        if text:
            parts.append(text)

    return _clean_label_text(" ".join(parts))


def _extract_p_texts_from_cell(cell) -> list[str]:
    """
    td/th 내부의 p 태그 텍스트를 추출한다.
    p 안에 font/span이 여러 개여도 텍스트만 정리한다.
    """
    p_texts = []

    for p in cell.find_all("p"):
        text = _extract_visible_text(p)

        if text and text not in p_texts:
            p_texts.append(text)

    return p_texts


def _is_slash_only_text(text: str) -> bool:
    text = _normalize_korean_label(text)
    return text in {"/", "／"}


def _looks_like_template_input_text(text: str) -> bool:
    """
    사용자가 실제 값을 채워야 하는 기본 양식 문구인지 판단한다.
    예: 20 년 월 일 ~ 20 년 월 일 ( 박 일 )
    """
    raw = _clean_text(text)
    compact = _normalize_korean_label(raw)

    if not compact:
        return False

    patterns = [
        r"\d{2,4}년월일",
        r"\d{2,4}년월일[~∼\-]\d{2,4}년월일",
        r"년월일[~∼\-].*년월일",
        r"\(박일\)",
        r"박일",
        r"금.*원",
        r"₩",
        r"￦",
        r"[○〇O]{2,}",
    ]

    return any(re.search(pattern, compact) for pattern in patterns)

def _assign_table_cell_ids(soup):
    rows_for_ai = []
    table_index = 0

    for table in soup.find_all("table"):
        grid = _get_table_cell_grid(table)
        trs = table.find_all("tr")

        for row_index, tr in enumerate(trs):
            cells = tr.find_all(["td", "th"], recursive=False)

            if not cells:
                continue

            row_items = []

            for physical_cell_index, cell in enumerate(cells):
                info = _find_cell_info_in_grid(grid, cell)

                if not info:
                    logical_col_start = physical_cell_index
                    logical_col_end = physical_cell_index
                else:
                    logical_col_start = info.get("col_start", physical_cell_index)
                    logical_col_end = info.get("col_end", physical_cell_index)

                if logical_col_start == logical_col_end:
                    cell_id = f"t{table_index}_r{row_index}_c{logical_col_start}"
                else:
                    cell_id = f"t{table_index}_r{row_index}_c{logical_col_start}_{logical_col_end}"

                _set_cell_locator(cell, cell_id, "table_cell")

                # text = cell.get_text(" ", strip=True)
                # clean_text = _clean_label_text(text)
                # normalized_text = _normalize_korean_label(clean_text)

                # is_empty = not bool(clean_text)

                # # 표 안에서 글자가 있는 칸은 기본적으로 라벨/헤더로 봄
                # # 단, / 만 있는 결재칸은 사용자가 결재 위치로 선택할 수 있도록 허용
                # slash_only = normalized_text in {"/", "／"}
                # is_fillable = is_empty or slash_only

                # cell["data-fillable"] = "true" if is_fillable else "false"
                # cell["data-row-index"] = str(row_index)
                # cell["data-col-start"] = str(logical_col_start)
                # cell["data-col-end"] = str(logical_col_end)
                
                text = _extract_visible_text(cell)
                p_texts = _extract_p_texts_from_cell(cell)

                clean_text = _clean_label_text(text)
                normalized_text = _normalize_korean_label(clean_text)

                is_empty = not bool(clean_text)
                slash_only = _is_slash_only_text(clean_text)

                template_input_text = (
                    _looks_like_template_input_text(clean_text)
                    or any(_looks_like_template_input_text(p_text) for p_text in p_texts)
                )

                # 빈칸, "/" 결재칸, "20년 월일 ~ ..." 같은 기본 입력 문구는 입력 가능
                is_fillable = is_empty or slash_only or template_input_text

                # 기존 문구를 지우고 placeholder로 교체해야 하는 칸
                replace_original = slash_only or template_input_text

                cell["data-fillable"] = "true" if is_fillable else "false"
                cell["data-replace-original"] = "true" if replace_original else "false"
                cell["data-row-index"] = str(row_index)
                cell["data-col-start"] = str(logical_col_start)
                cell["data-col-end"] = str(logical_col_end)

                above_labels = _collect_above_labels(
                    grid=grid,
                    row_idx=row_index,
                    col_start=logical_col_start,
                    col_end=logical_col_end,
                )

                left_labels = _collect_left_labels(
                    grid=grid,
                    row_idx=row_index,
                    col_start=logical_col_start,
                )

                label_hint = " / ".join(above_labels or left_labels)

                row_items.append(
                    {
                        "cell_id": cell_id,
                        "locator_type": "table_cell",
                        "text": clean_text,
                        "p_texts": p_texts,
                        "is_empty": is_empty,
                        "is_fillable": is_fillable,
                        "replace_original": replace_original,
                        "is_approval_like": _is_approval_label(clean_text) or _is_approval_label(label_hint),
                        "table_index": table_index,
                        "row_index": row_index,
                        "physical_cell_index": physical_cell_index,
                        "logical_col_start": logical_col_start,
                        "logical_col_end": logical_col_end,
                        "above_labels": above_labels,
                        "left_labels": left_labels,
                        "position_hint": label_hint,
                    }
                )

            row_text = " | ".join([item["text"] for item in row_items if item["text"]])

            rows_for_ai.append(
                {
                    "layout_type": "table_html",
                    "table_index": table_index,
                    "row_index": row_index,
                    "row_text": row_text,
                    "cells": row_items,
                }
            )

        table_index += 1

    return rows_for_ai, soup

def _assign_inline_text_ids(soup, rows_for_ai: list[dict] | None = None):
    rows_for_ai = rows_for_ai or []
    inline_index = 0

    for tag in soup.find_all(["p"]):
        # 핵심: td/th 안에 있는 p는 별도 입력 위치로 만들지 않음
        # td 자체가 data-cell-id를 가져야 placeholder가 p 아래에 붙지 않는다.
        if tag.find_parent(["td", "th"]):
            continue

        if tag.find(["table", "tr", "td", "th"]):
            continue

        text = _extract_visible_text(tag)

        if not text:
            continue

        if "{{" in text or "}}" in text:
            continue

        if len(text) > 120:
            continue

        cell_id = tag.get("data-cell-id")

        if not cell_id:
            cell_id = f"inline_p_{inline_index}"
            _set_cell_locator(tag, cell_id, "inline_text")
            inline_index += 1

        tag["data-fillable"] = "true"
        tag["data-replace-original"] = "false"

        rows_for_ai.append(
            {
                "layout_type": "inline_text_html",
                "row_index": inline_index,
                "row_text": text,
                "cells": [
                    {
                        "cell_id": cell_id,
                        "locator_type": "inline_text",
                        "text": text,
                        "is_empty": False,
                        "is_fillable": True,
                        "replace_original": False,
                        "row_index": inline_index,
                        "cell_index": 0,
                        "position_hint": text,
                    }
                ],
            }
        )

    return rows_for_ai, soup
# -----------------------------------------------------------------------------------------------

def _infer_label_from_left_cell(cell) -> str:
    tr = cell.find_parent("tr")
    if not tr:
        return ""
    cells = tr.find_all(["td", "th"], recursive=False)
    try:
        index = cells.index(cell)
    except ValueError:
        return ""
    for prev_index in range(index - 1, -1, -1):
        text = _clean_label_text(cells[prev_index].get_text(" ", strip=True))
        if text:
            return text
    return ""


def _key_from_component(comp, label: str, fallback: str) -> str:
    dsl = comp.get("data-dsl") or ""
    label_match = re.search(r"\{\{\s*label\s*:\s*([^}]+)\s*\}\}", dsl)
    if label_match:
        raw_key = label_match.group(1).strip()
        key = _camel_to_snake(raw_key)
        mapped = {
            "doc_no": "document_number",
            "draft_date": "draft_date",
            "draft_dept": "draft_department",
            "draft_user": "draft_person",
        }
        return mapped.get(key, key)
    return _field_key_from_label(label, fallback)


def _extract_component_fields_from_soup(soup) -> list[dict]:
    _assign_table_cell_ids(soup)
    fields = []
    used_keys = set()
    components = soup.select(".comp_wrap[data-cid]")

    for index, comp in enumerate(components, start=1):
        data_cid = _clean_text(comp.get("data-cid") or str(index))
        cell = comp.find_parent(["td", "th"]) or comp.parent
        if not cell:
            continue
        cell_id = cell.get("data-cell-id")
        if not cell_id:
            cell_id = f"component_{data_cid}"
            _set_cell_locator(cell, cell_id, "component_cell")
            
        table_label, table_key_hint = _infer_component_label_from_table(comp)

        # label = _infer_label_from_left_cell(cell)
        label = table_label
        comp_item = comp.select_one(".comp_item")
        comp_item_text = _clean_label_text(comp_item.get_text(" ", strip=True)) if comp_item else ""
        if not label:
            label = _infer_label_from_left_cell(cell)
        
        if not label:
            label = comp_item_text or f"항목 {data_cid}"

        key = _key_from_component(comp=comp, label=label, fallback=f"field_{data_cid}")
        key = _safe_key(key, fallback=f"field_{data_cid}")
        original_key = key
        count = 2
        while key in used_keys:
            key = f"{original_key}_{count}"
            count += 1
        used_keys.add(key)

        dsl = comp.get("data-dsl") or ""
        ui_type = "date" if "period" in dsl or "기간" in label else "string"

        fields.append({
            "label": label,
            "key": key,
            "type": ui_type,
            "required": False,
            "description": label,
            "position_hint": f"전자결재 컴포넌트 data-cid={data_cid}",
            "cell_id": cell_id,
            "locator": {"type": "component", "cell_id": cell_id, "component_id": data_cid},
            "source": "component_html",
        })
    return fields


def _parse_mm_style_value(style: str, name: str) -> float | None:
    if not style:
        return None
    match = re.search(rf"{name}\s*:\s*(-?\d+(?:\.\d+)?)mm", style, re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_position_info(tag) -> dict:
    style = tag.get("style") or ""
    return {
        "left": _parse_mm_style_value(style, "left"),
        "top": _parse_mm_style_value(style, "top"),
        "width": _parse_mm_style_value(style, "width"),
        "height": _parse_mm_style_value(style, "height"),
    }


def _extract_positioned_rows_for_ai(soup):
    rows_for_ai = []
    pages = soup.select(".hpa") or [soup]

    for page_index, page in enumerate(pages):
        cells = page.select(".hce")
        cell_items = []
        for cell_index, cell in enumerate(cells):
            cell_id = f"p{page_index}_c{cell_index}"
            _set_cell_locator(cell, cell_id, "positioned_div")
            text = _clean_label_text(cell.get_text(" ", strip=True))
            pos = _extract_position_info(cell)
            cell_items.append({
                "cell_id": cell_id,
                "locator_type": "positioned_div",
                "page_index": page_index,
                "cell_index": cell_index,
                "text": text,
                "is_empty": not bool(text),
                "left": pos.get("left"),
                "top": pos.get("top"),
                "width": pos.get("width"),
                "height": pos.get("height"),
            })

        cell_items.sort(key=lambda x: (x.get("top") if x.get("top") is not None else 99999, x.get("left") if x.get("left") is not None else 99999))

        for item in cell_items:
            if not item["is_empty"]:
                continue
            left = item.get("left")
            top = item.get("top")
            near_labels = []
            for other in cell_items:
                if other["is_empty"]:
                    continue
                other_left = other.get("left")
                other_top = other.get("top")
                if left is None or top is None or other_left is None or other_top is None:
                    continue
                if abs(other_top - top) <= 2.5 and other_left < left:
                    near_labels.append(other["text"])
            item["near_labels"] = near_labels[-3:]
            item["position_hint"] = " / ".join(item["near_labels"])

        rows_for_ai.append({
            "layout_type": "positioned_div_html",
            "page_index": page_index,
            "row_index": page_index,
            "row_text": "",
            "cells": cell_items,
        })
    return rows_for_ai, soup


def _extract_manual_blocks(soup):
    rows_for_ai = []
    body = soup.body or soup
    blocks = body.find_all(["p", "div", "span"])
    for index, tag in enumerate(blocks):
        text = _clean_label_text(tag.get_text(" ", strip=True))
        if not text and index > 200:
            continue
        cell_id = f"manual_{index}"
        _set_cell_locator(tag, cell_id, "manual_block")
        rows_for_ai.append({
            "layout_type": "manual_html",
            "row_index": index,
            "row_text": text,
            "cells": [{
                "cell_id": cell_id,
                "locator_type": "manual_block",
                "text": text,
                "is_empty": not bool(text),
                "row_index": index,
                "cell_index": 0,
            }],
        })
    return rows_for_ai, soup

# ----------------------------------------------------------------------------------------------------
def _extract_rows_by_layout(html: str):
    soup = BeautifulSoup(html or "", "html.parser")
    layout_type = _classify_template_layout(soup)

    if layout_type == "component_html":
        rows_for_ai, soup = _assign_table_cell_ids(soup)
        rows_for_ai, soup = _assign_inline_text_ids(soup, rows_for_ai)
        return layout_type, rows_for_ai, soup

    if layout_type == "positioned_div_html":
        rows_for_ai, soup = _extract_positioned_rows_for_ai(soup)
        rows_for_ai, soup = _assign_inline_text_ids(soup, rows_for_ai)
        return layout_type, rows_for_ai, soup

    if layout_type == "table_html":
        rows_for_ai, soup = _assign_table_cell_ids(soup)
        rows_for_ai, soup = _assign_inline_text_ids(soup, rows_for_ai)
        return layout_type, rows_for_ai, soup

    rows_for_ai, soup = _extract_manual_blocks(soup)
    return layout_type, rows_for_ai, soup
# ---------------------------------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------------------------------------------
def _compress_rows_for_ai(rows_for_ai: list[dict]) -> dict:
    result = {
        "v": 1,
        "rows": [],
    }

    for row in rows_for_ai or []:
        layout = row.get("layout_type", "")
        compact_row = {
            "ly": layout,
            "r": row.get("row_index"),
            "cells": [],
        }

        if row.get("table_index") is not None:
            compact_row["t"] = row.get("table_index")

        if row.get("page_index") is not None:
            compact_row["p"] = row.get("page_index")

        for cell in row.get("cells", []) or []:
            cell_id = _clean_text(cell.get("cell_id"))
            if not cell_id:
                continue

            c = {"id": cell_id}

            text = _clean_text(cell.get("text"))
            if text:
                c["txt"] = text[:80]
            
            c["fill"] = 1 if cell.get("is_fillable", True) else 0
            # if cell.get("is_fillable") is not None:
            #     c["fill"] = 1 if cell.get("is_fillable") else 0

            if cell.get("replace_original"):
                c["rep"] = 1

            if cell.get("is_approval_like"):
                c["apv"] = 1

            left = cell.get("left_labels") or []
            top = cell.get("above_labels") or []
            near = cell.get("near_labels") or []

            if left:
                c["left"] = left[:3]

            if top:
                c["top"] = top[:3]

            if near:
                c["near"] = near[:3]

            hint = _clean_text(cell.get("position_hint"))
            if hint:
                c["hint"] = hint[:60]

            p_texts = cell.get("p_texts") or []
            useful_p_texts = [
                p for p in p_texts
                if _looks_like_template_input_text(p)
            ]
            if useful_p_texts:
                c["pt"] = useful_p_texts[:2]

            if layout == "positioned_div_html":
                pos_map = {
                    "left": "x",
                    "top": "y",
                    "width": "w",
                    "height": "h",
                }
                for raw_key, short_key in pos_map.items():
                    value = cell.get(raw_key)
                    if value is not None:
                        c[short_key] = round(float(value), 1)

            compact_row["cells"].append(c)

        if compact_row["cells"]:
            result["rows"].append(compact_row)

    return result
# -----------------------------------------------------------------------------------------------------------------

def _unique_texts(values: list) -> list[str]:
    result = []

    for value in values or []:
        value = _clean_text(value)

        if value and value not in result:
            result.append(value)

    return result


def _get_field_locations(field: dict) -> list[dict]:
    locations = []
    seen = set()

    raw_locators = field.get("locators")
    if not isinstance(raw_locators, list):
        raw_locators = []

    raw_locator = field.get("locator")
    if isinstance(raw_locator, dict):
        raw_locators.append(raw_locator)

    raw_cell_ids = field.get("cell_ids")
    if not isinstance(raw_cell_ids, list):
        raw_cell_ids = []

    if field.get("cell_id"):
        raw_cell_ids.append(field.get("cell_id"))

    for locator in raw_locators:
        if not isinstance(locator, dict):
            continue

        cell_id = _clean_text(locator.get("cell_id"))

        if not cell_id or cell_id in seen:
            continue

        seen.add(cell_id)
        locations.append(locator)

    for cell_id in raw_cell_ids:
        cell_id = _clean_text(cell_id)

        if not cell_id or cell_id in seen:
            continue

        seen.add(cell_id)
        locations.append(
            {
                "type": "cell",
                "cell_id": cell_id,
            }
        )

    return locations

def _add_default_locator_to_fields(fields: list[dict], layout_type: str) -> list[dict]:
    normalized = []
    for field in fields or []:
        if not isinstance(field, dict):
            continue
        cell_id = _clean_text(field.get("cell_id"))
        locator = field.get("locator")
        if not isinstance(locator, dict):
            locator = {"type": "cell", "cell_id": cell_id, "layout_type": layout_type}
        field["locator"] = locator
        field["cell_id"] = cell_id or _clean_text(locator.get("cell_id"))
        field["source"] = field.get("source") or layout_type
        normalized.append(field)
    return normalized

# ---------------------------------------------------------------------------------------------------
def _make_placeholder_span(soup, key: str):
    span = soup.new_tag("span")
    span["class"] = "template-placeholder"
    span["data-placeholder-key"] = key
    span["title"] = "{{" + key + "}}"
    span["style"] = (
        "display:block;"
        "width:100%;"
        "max-width:100%;"
        "white-space:normal;"
        "overflow-wrap:anywhere;"
        "word-break:break-all;"
        "overflow:hidden;"
        "text-overflow:clip;"
        "font-size:9pt;"
        "line-height:1.1;"
        "vertical-align:middle;"
        "color:#000000;"
        "font-family:Malgun Gothic, 맑은 고딕, sans-serif;"
    )
    span.string = "{{" + key + "}}"
    return span
# -----------------------------------------------------------------------------------------------------------

# def _filter_fields_to_empty_cells(
#     fields: list[dict],
#     rows_for_ai: list[dict],
# ) -> list[dict]:
#     cell_map = {}

#     for row in rows_for_ai or []:
#         for cell in row.get("cells", []) or []:
#             cell_id = _clean_text(cell.get("cell_id"))

#             if cell_id:
#                 cell_map[cell_id] = cell

#     filtered = []
#     used_cell_ids = set()

#     for field in fields or []:
#         if not isinstance(field, dict):
#             continue

#         locator = field.get("locator") if isinstance(field.get("locator"), dict) else {}
#         cell_id = _clean_text(field.get("cell_id") or locator.get("cell_id"))

#         if not cell_id:
#             continue

#         cell = cell_map.get(cell_id)

#         if not cell:
#             continue

#         # 핵심: 실제 텍스트가 있는 셀은 제외
#         if not cell.get("is_empty"):
#             continue

#         if _clean_text(cell.get("text")):
#             continue

#         if cell_id in used_cell_ids:
#             continue

#         used_cell_ids.add(cell_id)
#         filtered.append(field)

#     return filtered

def _inject_placeholders_by_locator(
    soup,
    fields: list[dict],
    keep_cell_id: bool = False,
) -> str:
    for field in fields or []:
        key = _safe_key(field.get("key") or field.get("label") or "")

        if not key:
            continue

        placeholder = "{{" + key + "}}"
        locations = _get_field_locations(field)

        for locator in locations:
            locator_type = locator.get("type")
            locator_detail_type = locator.get("locator_type") or locator_type
            cell_id = _clean_text(locator.get("cell_id"))

            if locator_type == "component":
                component_id = _clean_text(locator.get("component_id"))
                comp = soup.select_one(f'.comp_wrap[data-cid="{component_id}"]')

                if comp:
                    comp.replace_with(_make_placeholder_span(soup, key))
                    continue

            if not cell_id:
                continue

            target = soup.find(attrs={"data-cell-id": cell_id})

            if not target:
                continue

            if placeholder in target.get_text(" ", strip=False):
                continue

            target_locator_type = (
                locator.get("locator_type")
                or target.get("data-locator-type")
                or locator.get("type")
                or ""
            )
            
            target_actual_type = target.get("data-locator-type") or target_locator_type
            
            target_text = _normalize_korean_label(target.get_text(" ", strip=True))
            is_fillable = target.get("data-fillable") == "true"
            replace_original = target.get("data-replace-original") == "true"
            insert_mode = _clean_text(locator.get("insert_mode"))
            
            # 사용자가 직접 위치 선택한 텍스트 셀은 기존 문구를 지우지 않고 뒤에 placeholder를 붙임
            if target_actual_type == "table_cell" and insert_mode == "append":
                target.append(" ")
                target.append(_make_placeholder_span(soup, key))
                continue

            # 실제 HTML target이 table_cell이면 locator 정보와 상관없이 무조건 표 셀 보호 로직 적용
            if target_actual_type == "table_cell":
                if not is_fillable:
                    continue

                # 제목, 라벨, 헤더처럼 텍스트가 있는 셀은 원본 유지
                # 단, 20년 월일~ 같은 입력 예시 문구나 "/" 결재칸만 교체 허용
                if target_text and not replace_original:
                    continue

            # p/div/span 같은 인라인 라인은 기존 글자를 유지하고 뒤에 추가
            if target_locator_type in ["inline_text", "manual_block"]:
                target.append(" ")
                target.append(_make_placeholder_span(soup, key))
                continue
            
            # 최종 안전장치: table_cell인데 입력 가능 칸이 아니면 절대 원본 텍스트를 지우지 않음
            if target.get("data-locator-type") == "table_cell":
                final_text = _normalize_korean_label(target.get_text(" ", strip=True))
                final_is_fillable = target.get("data-fillable") == "true"
                final_replace_original = target.get("data-replace-original") == "true"

                if not final_is_fillable:
                    continue

                if final_text and not final_replace_original:
                    continue

            target.clear()

            if "hce" in (target.get("class") or []):
                wrapper = soup.new_tag("div")
                wrapper["style"] = (
                    "position:absolute;"
                    "left:0mm;"
                    "top:0mm;"
                    "width:100%;"
                    "height:100%;"
                    "display:flex;"
                    "align-items:center;"
                    "justify-content:center;"
                    "font-size:9pt;"
                    "font-family:Malgun Gothic, sans-serif;"
                )
                wrapper.append(_make_placeholder_span(soup, key))
                target.append(wrapper)
            else:
                target.append(_make_placeholder_span(soup, key))

    if not keep_cell_id:
        _strip_locator_attrs(soup)
    
    _remove_scripts(soup)

    return str(soup)

def _guess_field_type_from_label(label: str) -> str:
    label = _clean_text(label)

    if any(word in label for word in ["일자", "날짜", "기간", "예정일"]):
        return "date"

    if any(word in label for word in ["금액", "합계", "총액", "비용", "단가", "세액"]):
        return "amount"

    if any(word in label for word in ["내용", "목적", "사유", "비고", "적요"]):
        return "text"

    return "string"


def _pick_label_from_row_cells(cells: list[dict], target_index: int) -> str:
    labels = []

    for i in range(target_index - 1, -1, -1):
        text = _clean_label_text(cells[i].get("text", ""))
        if text:
            labels.append(text)
            break

    if labels:
        return labels[0]

    return ""

def _filter_fields_to_fillable_cells(
    fields: list[dict],
    rows_for_ai: list[dict],
) -> list[dict]:
    cell_map = {}

    for row in rows_for_ai or []:
        for cell in row.get("cells", []) or []:
            cell_id = _clean_text(cell.get("cell_id"))

            if cell_id:
                cell_map[cell_id] = cell

    filtered = []
    used_cell_ids = set()

    for field in fields or []:
        if not isinstance(field, dict):
            continue

        locator = field.get("locator") if isinstance(field.get("locator"), dict) else {}
        cell_id = _clean_text(field.get("cell_id") or locator.get("cell_id"))

        if not cell_id:
            continue

        cell = cell_map.get(cell_id)

        if not cell:
            continue

        locator_type = cell.get("locator_type", "")

        if locator_type == "table_cell":
            if not cell.get("is_fillable"):
                continue

            text = _normalize_korean_label(cell.get("text", ""))
            replace_original = bool(cell.get("replace_original"))

            # 텍스트가 있어도 replace_original=true인 입력 예시 문구는 통과
            # 예: 20년월일~20년월일, / 결재칸
            if text and not replace_original:
                continue

        elif locator_type in ["inline_text", "manual_block"]:
            if not cell.get("is_fillable", True):
                continue

        else:
            if cell.get("is_fillable") is False:
                continue

        if cell_id in used_cell_ids:
            continue

        used_cell_ids.add(cell_id)
        filtered.append(field)

    return filtered

def _fallback_fields_from_rows(rows_for_ai: list[dict], limit: int = 60) -> list[dict]:
    fields = []
    used_keys = set()

    for row in rows_for_ai:
        cells = row.get("cells", [])

        if not isinstance(cells, list):
            continue

        for idx, cell in enumerate(cells):
            if cell.get("is_fillable") is False:
                continue

            cell_text = _normalize_korean_label(cell.get("text", ""))
            locator_type = cell.get("locator_type", "")

            if locator_type == "table_cell":
                replace_original = bool(cell.get("replace_original"))

                if cell_text and not replace_original:
                    continue

            cell_id = _clean_text(cell.get("cell_id"))
            if not cell_id:
                continue

            label = _pick_label_from_row_cells(cells, idx)

            if not label:
                above_labels = cell.get("above_labels") or []
                left_labels = cell.get("left_labels") or []
                label = " ".join(above_labels or left_labels)

            if not label:
                label = _clean_text(cell.get("position_hint"))

            if not label:
                continue

            if len(label) > 40:
                continue

            key = _field_key_from_label(label, fallback=f"field_{len(fields) + 1}")
            key = _safe_key(key, fallback=f"field_{len(fields) + 1}")

            original_key = key
            count = 2

            while key in used_keys:
                key = f"{original_key}_{count}"
                count += 1

            used_keys.add(key)

            fields.append(
                {
                    "label": label,
                    "key": key,
                    "type": _guess_field_type_from_label(label),
                    "required": False,
                    "cell_id": cell_id,
                    "description": label,
                    "position_hint": label,
                    "locator": {
                        "type": "cell",
                        "locator_type": locator_type,
                        "cell_id": cell_id,
                        "layout_type": row.get("layout_type", ""),
                    },
                    "source": row.get("layout_type", ""),
                }
            )

            if len(fields) >= limit:
                return fields

    return fields

async def _analyze_template_cells_with_claude(rows_for_ai: list[dict], template_name: str) -> list[dict]:
    # table_map_text = json.dumps(rows_for_ai, ensure_ascii=False, indent=2)
    compressed_rows = _compress_rows_for_ai(rows_for_ai)
    table_map_text = _compact_json(compressed_rows)
    instructions = textwrap.dedent(f"""
    역할: 결재서류 HTML 변환 구조에서 자동입력 필드 위치를 찾는다.
    입력은 압축 문서구조 JSON이며 HTML 원문이 아니다.
    템플릿: {template_name}

    입력 키:
    row.ly=layout, row.t=표번호, row.r=행번호, row.p=페이지번호.
    cell.id=출력 cell_id, cell.txt=셀텍스트, cell.fill=입력후보, cell.rep=원문교체가능.
    cell.left/top/near/hint=주변라벨, cell.pt=입력예시문구, cell.apv=결재후보, cell.x/y/w/h=좌표.

    순수 JSON 객체만 출력한다. 설명/마크다운/코드블록 금지.

    형식:
    {{"fields":[{{"label":"항목명","key":"field_name","type":"string","required":true,"cell_id":"t0_r0_c0","description":"필드 의미","position_hint":"문서 위치"}}]}}

    규칙:
    1. cell_id는 입력 cell.id 중 하나만 사용한다.
    2. cell.fill=1인 셀만 선택한다.
    3. cell.txt가 있고 cell.rep!=1이면 선택하지 않는다.
    4. 제목/고정문구/설명문구/컬럼명은 제외한다.
    5. table_html은 left/top 라벨이 있는 입력 가능 셀을 우선한다.
    6. positioned_div_html은 near/hint가 있는 빈 셀을 우선한다.
    7. pt에 날짜/금액/○○○ 귀하 등 입력 예시가 있으면 후보가 될 수 있다.
    8. 출장확인/월일/출발지/도착지/업무내용 등 컬럼명은 제외한다.
    9. 결재란 key: 담당=approval_staff_name, 팀장=approval_team_leader_name, 임원=approval_executive_name, 대표/대표이사=approval_ceo_name, 과장=approval_manager_name, 부장=approval_general_manager_name, 이사=approval_director_name.
    10. key는 영어 snake_case.
    11. type은 string,text,date,number,amount,array,boolean 중 하나.
    12. fields 최대 60개.
    13. label 20자 이내, description/position_hint 40자 이내.
    14. 확실한 자동입력 칸만 포함한다.
    """).strip()
    response = await client.messages.create(
        model=CLAUDE_TEMPLATE_MODEL,
        max_tokens=8192,
        # max_tokens=4096,
        temperature=0,
        system=instructions,
        messages=[{"role": "user", "content": table_map_text}],
    )
    data = _extract_json_from_text(_claude_text(response))
    fields = data.get("fields", [])
    return fields if isinstance(fields, list) else []


# DOCX/HWPX에서 변환된 HTML에 {{key}} 형식의 플레이스홀더를 넣고 schema/fields를 생성 ---------------------------------------------------
async def convert_template_to_schema(
    source_text: str,
    file_type: str,
    template_name: str,
    confirmed_fields: list[dict] | None = None,
    keep_cell_id: bool = False,
) -> dict:
    confirmed_fields = confirmed_fields or []
    layout_type, rows_for_ai, soup = _extract_rows_by_layout(source_text)
    soup = _remove_scripts(soup)

    if confirmed_fields:
        fields = confirmed_fields
    elif layout_type == "component_html":
        fields = _extract_component_fields_from_soup(soup)

    elif layout_type in ["table_html", "positioned_div_html"]:
        try:
            fields = await _analyze_template_cells_with_claude(
                rows_for_ai=rows_for_ai,
                template_name=template_name,
            )

            fields = _filter_fields_to_fillable_cells(
                fields=fields,
                rows_for_ai=rows_for_ai,
            )

            fields = _add_default_locator_to_fields(fields, layout_type)

        except Exception as e:
            print(f"[WARN] AI field analysis failed. fallback used: {e}")

            fields = _fallback_fields_from_rows(
                rows_for_ai=rows_for_ai,
                limit=60,
            )
            fields = _filter_fields_to_fillable_cells(
                fields=fields,
                rows_for_ai=rows_for_ai,
            )
            fields = _add_default_locator_to_fields(fields, layout_type)
    else:
        fields = []

    if not fields:
        html_preview = str(soup) if keep_cell_id else str(_strip_locator_attrs(soup))
        return _empty_schema_result(html_template=html_preview, layout_type=layout_type, support_level="manual")

    fields = _add_default_locator_to_fields(fields, layout_type)
    html_template = _inject_placeholders_by_locator(soup=soup, fields=fields, keep_cell_id=keep_cell_id)
    json_schema, placeholder_keys, normalized_fields = _build_schema_from_confirmed_fields(fields)
    normalized = _normalize_template_schema(html_template=html_template, json_schema=json_schema, placeholder_keys=placeholder_keys)
    normalized["fields"] = normalized_fields
    normalized["analysis_mode"] = layout_type
    normalized["support_level"] = "auto" if layout_type == "component_html" else ("semi_auto" if layout_type in ["table_html", "positioned_div_html"] else "manual")
    return normalized


# 조직도를 읽고 json 데이터로 저장하는 AI ------------------------------------------------------------------------------
async def preview_org_members_from_image(
    image_b64: str,
    image_mime: str,
) -> list[dict]:
    instructions = textwrap.dedent("""
    역할: 조직도/인사표/주소록 이미지를 읽어 조직원 JSON 배열을 만든다.
    순수 JSON 배열만 출력한다. 설명/마크다운/코드블록 금지.

    형식:
    [{"name":"","department":"","title":"","email":""}]

    규칙:
    1. 사람 행만 추출하고 헤더는 제외한다.
    2. 이름/부서/직급·직책/이메일을 보이는 대로 입력한다.
    3. 직급·직책이 합쳐진 컬럼은 title에 그대로 둔다.
    4. 이메일 공백은 제거한다.
    5. 없거나 불명확한 값은 빈 문자열로 둔다.
    6. 이미지에 없는 정보는 추측하지 않는다.
    7. name/title/email이 모두 비면 제외한다.
    """).strip()

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
    # template_lines = []
    # for t in templates:
    #     template_lines.append(
    #         f"- template_id: {t['id']}, template_name: {t['template_name']}"
    #     )

    # org_lines = []
    # for m in org_members:
    #     org_lines.append(
    #         f"- member_id: {m['id']}, name: {m['name']}, department: {m.get('department','')}, title: {m['title']}, email: {m['email']}"
    #     )
    template_text = _compact_templates_for_prompt(templates)
    org_text = _compact_org_members_for_prompt(org_members)

    filtered_guide = _filter_approval_guide_text(guide_text)

    if len(filtered_guide) < 1500:
        filtered_guide = _clean_text(guide_text)[:45000]


    user_payload = {
        "templates": template_text,
        "org_members": org_text,
        # "guide": _clean_text(guide_text)[:45000],
        "guide": filtered_guide,
    }

    instructions = textwrap.dedent("""
    역할: 결재 지침서에서 저장 가능한 결재 처리 규칙 후보를 추출한다.
    입력은 templates/org_members/guide를 담은 JSON이다.

    입력 형식:
    - templates: 줄 단위 id|template_name
    - org_members: 줄 단위 id|name|department|title|email
    - guide: 결재 지침서 텍스트

    순수 JSON 배열만 출력한다. 설명/마크다운/코드블록 금지.

    형식:
    [{"rule_name":"","rule_text":"","template_id":1,"source_excerpt":"","approvers":[{"approver_member_id":1,"approval_order":1,"approval_type":"결재"}]}]

    규칙:
    1. template_id는 입력 templates의 id만 사용한다.
    2. approver_member_id는 입력 org_members의 id만 사용한다.
    3. approval_type은 결재, 합의, 최종승인, 참조 중 하나.
    4. approvers는 approval_order 오름차순.
    5. guide에 근거가 명확한 규칙만 생성한다.
    6. 애매한 규칙은 생성하지 않는다.
    7. source_excerpt는 판단 근거 문장을 짧게 적는다.
    8. 같은 의미의 규칙은 중복 생성하지 않는다.
    """).strip()

    response = await client.messages.create(
        model=CLAUDE_LIGHT_MODEL,
        max_tokens=8192,
        temperature=0,
        system=instructions,
        messages=[
            {
                "role": "user",
                "content": _compact_json(user_payload),
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

    # schema_text = json.dumps(template_schema, ensure_ascii=False, indent=2)
    field_context = _build_field_context_from_schema(template_schema)
    field_context_text = _compact_json(field_context)

    receipt_count = len(receipt_images)

    instructions = textwrap.dedent(f"""
    역할: 결재서류 작성용 JSON 데이터를 생성한다.
    템플릿: {template_name}
    필드목록: {field_context_text}
    결재규칙: {_clean_text(approval_rules)[:6000]}
    조직도: {_clean_text(org_list)[:6000]}
    영수증이미지수: {receipt_count}

    순수 JSON 객체만 출력한다. 설명/마크다운/코드블록 금지.

    규칙:
    1. 필드목록의 k만 key로 사용한다.
    2. 필드목록에 없는 key는 추가하지 않는다.
    3. t가 integer/number이면 숫자로 반환한다. 쉼표/원/공백/문자열 금지.
    4. boolean은 true/false로 반환한다.
    5. array는 여러 영수증 품목·내역을 행 단위로 정리한다.
    6. string은 null 대신 가능한 문자열을 넣는다.
    7. 날짜는 문서 문맥에 맞게 작성한다.
    8. 사용자 설명과 영수증이 충돌하면 영수증을 우선한다.
    9. 흐리거나 누락된 정보는 사용자 설명을 보조 근거로 사용한다.
    10. 결재자 관련 필드는 템플릿 필드에 있을 때만 채운다.
    """).strip()

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








# 교육용 테스트 코드----------------------------------------------------------------------------------------------------------------------------


# 교육용 1회성 자동 작성
# 1차 분석 결과(html_template + confirmed_fields)를 받아
# DB 저장 없이 문서 작성용 데이터만 생성한다.
async def generate_document_once(
    html_template: str,
    template_name: str,
    confirmed_fields: list[dict],
    description: str,
    receipt_images: list[dict] | None = None,
) -> dict:
    receipt_images = receipt_images or []

    if not html_template or not html_template.strip():
        raise ValueError("html_template 값이 비어 있습니다.")

    if not confirmed_fields:
        raise ValueError("confirmed_fields 값이 비어 있습니다.")

    # confirmed_fields가 있으므로 양식 분석 AI를 다시 호출하지 않고,
    # 확정된 항목 기준으로 placeholder와 JSON Schema를 재구성한다.
    converted = await convert_template_to_schema(
        source_text=html_template,
        file_type="html",
        template_name=template_name,
        confirmed_fields=confirmed_fields,
        keep_cell_id=False,
    )

    clean_html_template = converted["html_template"]
    template_schema = converted["json_schema"]

    expense_data = await extract_expense_data(
        template_html=clean_html_template,
        template_name=template_name,
        template_schema=template_schema,
        description=description,
        receipt_images=receipt_images,
        approval_rules="",
        org_chart={},
    )

    return {
        "html_template": clean_html_template,
        "json_schema": template_schema,
        "placeholder_keys": converted.get("placeholder_keys", []),
        "fields": converted.get("fields", []),
        "expense_data": expense_data,
    }