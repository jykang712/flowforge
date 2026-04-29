import { useEffect, useRef, useState } from "react";
import DropZone from "../components/DropZone";
import {
  getTemplates,
  getTemplateDetail,
  previewTemplateFields,
  saveTemplateWithFields,
} from "../services/api";

const TEMPLATE_FILE_ACCEPT = ".pdf,.html,.htm,.docx,.hwpx";
const TEMPLATE_FILE_GUIDE = "PDF, HTML, DOCX, HWPX, html";

const typeOptions = [
  { value: "string", label: "짧은 텍스트" },
  { value: "text", label: "긴 문장" },
  { value: "date", label: "날짜" },
  { value: "number", label: "숫자" },
  { value: "amount", label: "금액" },
  { value: "array", label: "목록/표" },
  { value: "boolean", label: "예/아니오" },
];

function makeEmptyField() {
  return {
    id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
    label: "",
    key: "",
    type: "string",
    required: false,
    description: "",
    position_hint: "",
  };
}

function isGenericKey(key) {
  return /^field_?\d+$/.test(String(key || "").trim());
}

function makeSafeKey(value, index = 0) {
  const safe = String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_]/g, "");

  return safe || `field_${index + 1}`;
}

function makeSmartKey(label, index = 0) {
  const value = String(label || "").trim();

  if (!value) return `field_${index + 1}`;

  if (value.includes("결재선")) return "approval_line";
  if (value.includes("대표이사") && value.includes("결재")) return "approval_ceo_name";
  if (value.includes("이사") && value.includes("결재")) return "approval_director_name";
  if (value.includes("부장") && value.includes("결재")) return "approval_general_manager_name";
  if (value.includes("과장") && value.includes("결재")) return "approval_manager_name";
  if (value.includes("결재자") || value.includes("승인자")) return "approver_name";

  const koreanKeyMap = {
    문서번호: "document_number",
    번호: "document_number",

    작성일: "issue_date",
    발행일: "issue_date",
    신청일: "request_date",
    일자: "issue_date",
    날짜: "issue_date",

    성명: "name",
    이름: "name",
    신청자: "requester_name",
    작성자: "writer_name",
    수령자: "recipient_name",
    공급받는자: "recipient_name",

    소속: "department",
    부서: "department",
    직위: "position",
    직급: "title",

    상호: "company_name",
    업체명: "company_name",
    회사명: "company_name",
    대표자: "representative_name",
    대표자명: "representative_name",
    주소: "address",
    사업장소재지: "address",
    사업자등록번호: "business_number",

    공급가액: "supply_amount",
    세액: "tax_amount",
    총액: "total_amount",
    합계금액: "total_amount",
    합계: "total_amount",
    금액: "amount",
    신청금액: "request_amount",

    내용: "description",
    적요: "description",
    비고: "remarks",
    사유: "reason",
    목적: "purpose",

    출장처: "business_trip_destination",
    출장목적: "business_trip_purpose",
    출장기간: "business_trip_period",
    예정정산일: "expected_settlement_date",
  };

  if (koreanKeyMap[value]) {
    return koreanKeyMap[value];
  }

  const safe = value
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_]/g, "");

  return safe || `field_${index + 1}`;
}

function normalizeFields(fields = []) {
  return fields.map((field, index) => {
    const label =
      field.label ||
      field.field_label ||
      field.name ||
      field.title ||
      "";

    const rawKey =
      field.key ||
      field.field_name ||
      field.code ||
      "";

    const safeKey = rawKey
      ? makeSafeKey(rawKey, index)
      : makeSmartKey(label, index);

    return {
      id: field.id || `${Date.now()}_${index}`,
      label,
      key: isGenericKey(safeKey) ? makeSmartKey(label, index) : safeKey,
      type: field.type || "string",
      required: Boolean(field.required),
      description: field.description || "",
      position_hint: field.position_hint || field.context || "",
    };
  });
}

export default function SetupPage() {
  const [templateFile, setTemplateFile] = useState(null);
  const [templateName, setTemplateName] = useState("");
  const [description, setDescription] = useState("");
  const [templates, setTemplates] = useState([]);

  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [selectedTemplatePreview, setSelectedTemplatePreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const [fields, setFields] = useState([]);
  const [previewHtml, setPreviewHtml] = useState("");

  const [expandedFieldId, setExpandedFieldId] = useState(null);
  const [editableKeyIds, setEditableKeyIds] = useState({});
  const fieldRefs = useRef({});

  const [analyzing, setAnalyzing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const data = await getTemplates();
      setTemplates(Array.isArray(data) ? data : []);
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "템플릿 목록 조회 실패",
      });
    }
  };

  const toggleKeyEditable = (id) => {
    setEditableKeyIds((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const handlePreviewFields = async () => {
    setAnalyzing(true);
    setAlert(null);

    try {
      const result = await previewTemplateFields({
        templateFile,
        templateName,
        description,
      });

      const recommendedFields = normalizeFields(
        result.fields || result.placeholders || []
      );

      setFields(recommendedFields);
      setExpandedFieldId(recommendedFields[0]?.id || null);
      setPreviewHtml(result.preview_html || result.html_content || result.html_template || "");

      setAlert({
        type: "success",
        msg: "AI가 문서에서 자동으로 채워질 항목을 찾았습니다. 필요 없는 항목은 삭제하고, 빠진 항목은 직접 추가해주세요.",
      });
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "자동 입력 항목 분석에 실패했습니다.",
      });
    } finally {
      setAnalyzing(false);
    }
  };

  const addField = () => {
    const newField = makeEmptyField();

    setFields((prev) => [newField, ...prev]);
    setExpandedFieldId(newField.id);
    setEditableKeyIds((prev) => ({
      ...prev,
      [newField.id]: true,
    }));

    setTimeout(() => {
      fieldRefs.current[newField.id]?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }, 0);
  };

  const updateField = (id, name, value) => {
    setFields((prev) =>
      prev.map((field, index) => {
        if (field.id !== id) return field;

        const next = {
          ...field,
          [name]: value,
        };

        if (name === "label" && (!field.key || isGenericKey(field.key))) {
          next.key = makeSmartKey(value, index);
        }

        if (name === "key") {
          next.key = makeSafeKey(value, index);
        }

        return next;
      })
    );
  };

  const removeField = (id) => {
    setFields((prev) => {
      const next = prev.filter((field) => field.id !== id);

      if (expandedFieldId === id) {
        setExpandedFieldId(next[0]?.id || null);
      }

      return next;
    });

    setEditableKeyIds((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const validateFields = () => {
    if (!templateFile) {
      throw new Error("문서 양식 파일을 업로드해주세요.");
    }

    if (!templateName.trim()) {
      throw new Error("양식 이름을 입력해주세요.");
    }

    if (fields.length === 0) {
      throw new Error("자동 입력 항목을 1개 이상 설정해주세요.");
    }

    for (const field of fields) {
      if (!field.label.trim()) {
        throw new Error("항목명이 비어 있는 항목이 있습니다.");
      }

      if (!field.key.trim()) {
        throw new Error(`${field.label} 항목의 내부 코드가 비어 있습니다.`);
      }

      if (isGenericKey(field.key)) {
        throw new Error(
          `${field.label || field.key} 항목의 내부 코드가 너무 일반적입니다. approver_name, approval_line, total_amount처럼 의미 있는 코드로 수정해주세요.`
        );
      }
    }

    const keys = fields.map((field) => field.key.trim());
    const duplicatedKey = keys.find((key, index) => keys.indexOf(key) !== index);

    if (duplicatedKey) {
      throw new Error(`중복된 내부 코드가 있습니다: ${duplicatedKey}`);
    }
  };

  const handleOpenSavedTemplatePreview = async (templateId) => {
    setPreviewLoading(true);
    setAlert(null);
  
    try {
      const detail = await getTemplateDetail(templateId);
      setSelectedTemplatePreview(detail);
      setPreviewModalOpen(true);
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "미리보기를 불러오지 못했습니다.",
      });
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleEditTemplate = (template) => {
    setAlert({
      type: "info",
      msg: `${template.template_name} 수정 기능은 이후 단계에서 연결하면 됩니다.`,
    });
  };

  const handleSaveTemplate = async () => {
    setSaving(true);
    setAlert(null);

    try {
      validateFields();

      const confirmedFields = fields.map(({ id, ...field }) => ({
        ...field,
        key: makeSafeKey(field.key),
        placeholder: `{{${makeSafeKey(field.key)}}}`,
      }));

      await saveTemplateWithFields({
        templateFile,
        templateName,
        description,
        fields: confirmedFields,
      });

      setTemplateFile(null);
      setTemplateName("");
      setDescription("");
      setFields([]);
      setPreviewHtml("");
      setExpandedFieldId(null);
      setEditableKeyIds({});

      await loadTemplates();

      setAlert({
        type: "success",
        msg: "문서 양식과 자동 입력 항목이 저장되었습니다.",
      });
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "템플릿 저장에 실패했습니다.",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="main-inner">
      <div className="page-title">문서 양식 등록</div>
      <div className="page-desc">
        {TEMPLATE_FILE_GUIDE} 양식을 업로드하면 AI가 문서에서 자동으로 채워질 항목을 찾습니다.
        추천된 항목은 저장 전 직접 추가, 수정, 삭제할 수 있습니다.
      </div>

      {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}

      <div className="card">
        <div className="card-title">1. 문서 양식 업로드</div>

        <div className="form-row">
          <label>양식 이름 *</label>
          <input
            type="text"
            value={templateName}
            onChange={(e) => setTemplateName(e.target.value)}
            placeholder="예: 구매 품의서, 입금표, 지출결의서"
          />
        </div>

        <div className="form-row">
          <label>양식 설명</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="예: 이 양식이 어떤 결재 상황에서 사용되는지 간단히 입력해주세요."
            style={{ minHeight: 88 }}
          />
        </div>

        <DropZone
          label={`${TEMPLATE_FILE_GUIDE} 양식을 드래그하거나 클릭하여 업로드`}
          accept={TEMPLATE_FILE_ACCEPT}
          file={templateFile}
          setFile={setTemplateFile}
          icon="📄"
        />

        <p className="file-guide-text">
          <strong>※ 원본 양식과 가장 유사한 결과가 필요한 경우 HTML 형식 업로드를 권장합니다.</strong>
          <br />
          <strong>PDF, DOCX, HWPX는 문서 구조를 추출해 HTML 템플릿으로 재구성하므로 원본과 일부 여백이나 배치가 다를 수 있습니다.</strong>
        </p>

        <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
          <button
            className="btn btn-primary"
            type="button"
            onClick={handlePreviewFields}
            disabled={analyzing || !templateFile || !templateName.trim()}
          >
            {analyzing ? (
              <>
                <span className="spinner" />
                분석 중...
              </>
            ) : (
              "AI로 자동 입력 항목 찾기"
            )}
          </button>

          <button
            className="btn btn-secondary"
            type="button"
            onClick={() => {
              setFields([]);
              setPreviewHtml("");
              setExpandedFieldId(null);
              setEditableKeyIds({});
              setAlert(null);
            }}
            disabled={analyzing || saving}
          >
            분석 결과 초기화
          </button>
        </div>
      </div>

      {(fields.length > 0 || previewHtml) && (
        <div className="template-setting-grid">
          <div className="card template-preview-card">
            <div className="card-title">2. 원본 양식 미리보기</div>
            <div className="page-desc">
              업로드한 양식의 형태를 확인하는 영역입니다. 실제 저장 시에는 사용자가 확정한 자동 입력 항목이 함께 저장됩니다.
            </div>

            {previewHtml ? (
              <div className="template-preview-frame">
                <iframe title="template-preview" srcDoc={previewHtml} />
              </div>
            ) : (
              <div className="empty-box">
                미리보기 화면이 없습니다. 오른쪽의 자동 입력 항목만 확인해주세요.
              </div>
            )}
          </div>

          <div className="card field-panel-card">
            <div className="card-title">3. 자동 입력 항목 확인</div>
            <div className="page-desc">
              AI가 찾은 항목입니다. 문서 작성 시 자연어 설명, 첨부파일, 결재 규칙을 바탕으로 이 항목들의 값이 자동 입력됩니다.
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 12,
                gap: 10,
              }}
            >
              <div style={{ fontSize: 13, opacity: 0.75 }}>
                총 {fields.length}개 항목
              </div>

              <button
                className="btn btn-secondary"
                type="button"
                onClick={addField}
              >
                + 항목 추가
              </button>
            </div>

            {fields.length === 0 ? (
              <div className="empty-box">
                아직 자동 입력 항목이 없습니다. 항목을 직접 추가할 수 있습니다.
              </div>
            ) : (
              <div className="field-list">
                {fields.map((field, index) => {
                  const isExpanded = expandedFieldId === field.id;
                  const typeLabel =
                    typeOptions.find((option) => option.value === field.type)?.label ||
                    field.type;

                  const keyIsGeneric = isGenericKey(field.key);
                  const isKeyEditable = editableKeyIds[field.id] || keyIsGeneric;

                  return (
                    <div
                      className={`field-card${isExpanded ? " expanded" : ""}`}
                      key={field.id}
                      ref={(el) => {
                        fieldRefs.current[field.id] = el;
                      }}
                    >
                      <div
                        className="field-card-head"
                        onClick={() =>
                          setExpandedFieldId(isExpanded ? null : field.id)
                        }
                      >
                        <div className="field-summary">
                          <strong>
                            {index + 1}. {field.label || "새 항목"}
                          </strong>

                          <div className="field-summary-meta">
                            <span>{field.key || "내부 코드 없음"}</span>
                            <span>{typeLabel}</span>
                            {field.required && <span>필수</span>}
                            {keyIsGeneric && <span>코드 수정 필요</span>}
                          </div>
                        </div>

                        <div className="field-card-actions">
                          <button
                            type="button"
                            className="field-toggle-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              setExpandedFieldId(isExpanded ? null : field.id);
                            }}
                          >
                            {isExpanded ? "접기" : "수정"}
                          </button>

                          <button
                            type="button"
                            className="field-delete-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              removeField(field.id);
                            }}
                          >
                            삭제
                          </button>
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="field-card-body">
                          <div className="form-row">
                            <label>항목명</label>
                            <input
                              type="text"
                              value={field.label}
                              onChange={(e) =>
                                updateField(field.id, "label", e.target.value)
                              }
                              placeholder="예: 작성일, 신청자, 총 금액, 품목 목록"
                            />
                          </div>

                          <div className="form-row">
                            <label>내부 코드</label>

                            <div className="field-code-row">
                              <input
                                type="text"
                                value={field.key}
                                readOnly={!isKeyEditable}
                                className={!isKeyEditable ? "readonly-input" : ""}
                                onChange={(e) =>
                                  updateField(field.id, "key", e.target.value)
                                }
                                placeholder="예: issue_date, approver_name, approval_line"
                              />

                              <button
                                type="button"
                                className="field-toggle-btn"
                                onClick={() => toggleKeyEditable(field.id)}
                              >
                                {keyIsGeneric
                                  ? "수정 필요"
                                  : editableKeyIds[field.id]
                                  ? "잠금"
                                  : "코드 수정"}
                              </button>
                            </div>

                            <div className="input-help">
                              기본값은 자동 생성됩니다. field_28처럼 의미가 불명확한 코드는 직접 수정해야 저장할 수 있습니다.
                            </div>
                          </div>

                          <div className="form-row">
                            <label>입력 유형</label>
                            <select
                              value={field.type}
                              onChange={(e) =>
                                updateField(field.id, "type", e.target.value)
                              }
                            >
                              {typeOptions.map((option) => (
                                <option key={option.value} value={option.value}>
                                  {option.label}
                                </option>
                              ))}
                            </select>
                          </div>

                          <div className="form-row">
                            <label>항목 설명</label>
                            <textarea
                              value={field.description}
                              onChange={(e) =>
                                updateField(field.id, "description", e.target.value)
                              }
                              placeholder="예: 문서에 입력될 신청자 이름"
                              style={{ minHeight: 70 }}
                            />
                          </div>

                          <div className="form-row">
                            <label>문서 내 위치 설명</label>
                            <input
                              type="text"
                              value={field.position_hint}
                              onChange={(e) =>
                                updateField(field.id, "position_hint", e.target.value)
                              }
                              placeholder="예: 항목명 오른쪽 빈칸, 표의 금액 열, 하단 서명란"
                            />
                          </div>

                          <label className="checkbox-row">
                            <input
                              type="checkbox"
                              checked={field.required}
                              onChange={(e) =>
                                updateField(field.id, "required", e.target.checked)
                              }
                            />
                            비어 있으면 안 되는 항목
                          </label>

                          <div className="input-help">
                            체크하지 않아도 문서에는 포함됩니다. 문서에서 제외하려면 삭제 버튼을 눌러주세요.
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
              <button
                className="btn btn-primary"
                type="button"
                onClick={handleSaveTemplate}
                disabled={saving || !templateFile || !templateName.trim()}
              >
                {saving ? (
                  <>
                    <span className="spinner" />
                    저장 중...
                  </>
                ) : (
                  "최종 양식 저장"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-title">저장된 문서 양식</div>

        {templates.length === 0 ? (
          <div className="page-desc">아직 저장된 문서 양식이 없습니다.</div>
        ) : (
          <div className="saved-template-list">
            {templates.map((template) => (
              <div className="template-card" key={template.id}>
                <div className="template-card-body">
                  <h3 className="template-title">{template.template_name}</h3>

                  <p className="template-file">
                    <span>파일명</span>
                    {template.file_name}
                  </p>

                  <p className="template-desc">
                    <span>설명</span>
                    {template.description || "등록된 설명이 없습니다."}
                  </p>
                </div>

                <div className="template-card-actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => handleOpenSavedTemplatePreview(template.id)}
                    disabled={previewLoading}
                  >
                    {previewLoading ? "불러오는 중..." : "미리보기"}
                  </button>

                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => handleEditTemplate(template)}
                  >
                    수정
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {previewModalOpen && selectedTemplatePreview && (
        <div className="modal-backdrop">
          <div className="template-preview-modal">
            <div className="modal-header">
              <div>
                <h3>{selectedTemplatePreview.template_name}</h3>
                <p>{selectedTemplatePreview.file_name}</p>
              </div>

              <button
                type="button"
                className="modal-close-btn"
                onClick={() => {
                  setPreviewModalOpen(false);
                  setSelectedTemplatePreview(null);
                }}
              >
                닫기
              </button>
            </div>

            <div className="modal-body">
              <iframe
                title="saved-template-preview"
                srcDoc={selectedTemplatePreview.html_content || ""}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}