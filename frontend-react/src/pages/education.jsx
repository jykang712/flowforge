import { useMemo, useRef, useState } from "react";
import {
  previewTemplateFields,
  generateEducationDocumentOnce,
} from "../services/api";
import EducationDropzone from "../components/education_dropzone";

const TEMPLATE_FILE_ACCEPT =
  ".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

const typeOptions = [
  { value: "string", label: "짧은 텍스트" },
  { value: "text", label: "긴 문장" },
  { value: "date", label: "날짜" },
  { value: "number", label: "숫자" },
  { value: "amount", label: "금액" },
  { value: "array", label: "목록/표" },
  { value: "boolean", label: "예/아니오" },
];

function makeId(index = 0) {
  return `${Date.now()}_${index}_${Math.random().toString(16).slice(2)}`;
}

function normalizeInternalCode(value) {
  return String(value || "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function normalizeFields(fields = []) {
  return fields.map((field, index) => {
    const cellIds = Array.isArray(field.cell_ids)
      ? field.cell_ids.filter(Boolean)
      : field.cell_id
      ? [field.cell_id]
      : [];

    const locators = Array.isArray(field.locators)
      ? field.locators
      : field.locator && typeof field.locator === "object"
      ? [field.locator]
      : [];

    const label =
      field.label ||
      field.field_label ||
      field.name ||
      field.title ||
      `항목 ${index + 1}`;

    const rawKey =
      field.key ||
      field.field_name ||
      field.code ||
      `field_${index + 1}`;

    return {
      id: field.id || makeId(index),
      label,
      key: normalizeInternalCode(rawKey) || `field_${index + 1}`,
      type: field.type || "string",
      required: Boolean(field.required),
      description: field.description || "",
      position_hint: field.position_hint || field.context || "",
      cell_id: cellIds[0] || "",
      locator: locators[0] || {},
      cell_ids: cellIds,
      locators,
      source: field.source || "",
    };
  });
}

function removeViewOnlyId(fields = []) {
  return fields.map(({ id, ...field }) => ({
    ...field,
    key: normalizeInternalCode(field.key),
    placeholder: `{{${normalizeInternalCode(field.key)}}}`,
  }));
}

export default function EducationPage() {
  const [templateFile, setTemplateFile] = useState(null);
  const [templateName, setTemplateName] = useState("");
  const [previewHtml, setPreviewHtml] = useState("");
  const [fields, setFields] = useState([]);

  const previewRef = useRef(null);
  const [selectedFieldId, setSelectedFieldId] = useState(null);

  const [description, setDescription] = useState("");
  const [receiptFiles, setReceiptFiles] = useState([]);

  const [filledHtml, setFilledHtml] = useState("");
  const [expenseData, setExpenseData] = useState(null);

  const [analyzing, setAnalyzing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [alert, setAlert] = useState(null);

  const canAnalyze = useMemo(() => {
    return templateFile && templateName.trim();
  }, [templateFile, templateName]);

  const canGenerate = useMemo(() => {
    return previewHtml && fields.length > 0 && description.trim();
  }, [previewHtml, fields, description]);

  const handleAnalyzeTemplate = async () => {
    setAnalyzing(true);
    setAlert(null);
    setFilledHtml("");
    setExpenseData(null);

    try {
      const result = await previewTemplateFields({
        templateFile,
        templateName,
        description: "교육용 1회성 문서 자동작성 양식 분석",
      });

      const nextFields = normalizeFields(result.fields || []);

      setFields(nextFields);
      setPreviewHtml(result.preview_html || result.html_template || "");

      setAlert({
        type: "success",
        msg: "1차 AI 분석이 완료되었습니다. 자동 입력 항목을 확인한 뒤 자연어 설명과 이미지를 넣어 문서를 작성해보세요.",
      });
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "양식 분석에 실패했습니다.",
      });
    } finally {
      setAnalyzing(false);
    }
  };

  const updateField = (id, name, value) => {
    setFields((prev) =>
      prev.map((field) => {
        if (field.id !== id) return field;

        if (name === "key") {
          return {
            ...field,
            key: value
              .toLowerCase()
              .replace(/\s+/g, "_")
              .replace(/[^a-z0-9_]/g, ""),
            // normalizeInternalCode(value),
          };
        }

        return {
          ...field,
          [name]: value,
        };
      })
    );
  };

  const removeField = (id) => {
    setFields((prev) => prev.filter((field) => field.id !== id));
  };

  const validateBeforeGenerate = () => {
    if (!previewHtml) {
      throw new Error("먼저 결재서류 양식을 AI로 분석해주세요.");
    }

    if (fields.length === 0) {
      throw new Error("자동 입력 항목이 없습니다.");
    }

    if (!description.trim()) {
      throw new Error("문서 작성에 필요한 자연어 설명을 입력해주세요.");
    }

    const keys = fields.map((field) => normalizeInternalCode(field.key));

    if (keys.some((key) => !key)) {
      throw new Error("내부 코드가 비어 있는 항목이 있습니다.");
    }

    const duplicatedKey = keys.find((key, index) => keys.indexOf(key) !== index);

    if (duplicatedKey) {
      throw new Error(`중복된 내부 코드가 있습니다: ${duplicatedKey}`);
    }
  };

  const getFieldCellIds = (field) => {
    if (!field) return [];
  
    if (Array.isArray(field.cell_ids)) {
      return field.cell_ids.filter(Boolean);
    }
  
    if (field.cell_id) {
      return [field.cell_id];
    }
  
    return [];
  };
  
  const addField = () => {
    const nextIndex = fields.length + 1;
  
    const newField = {
      id: makeId(nextIndex),
      label: `추가 항목 ${nextIndex}`,
      key: `custom_field_${nextIndex}`,
      type: "string",
      required: false,
      description: "",
      position_hint: "사용자 수동 추가 항목",
      cell_id: "",
      locator: {},
      cell_ids: [],
      locators: [],
      source: "manual",
    };
  
    setFields((prev) => [newField, ...prev]);
    setSelectedFieldId(newField.id);
  
    setAlert({
      type: "info",
      msg: "추가한 항목을 넣을 위치를 왼쪽 미리보기에서 클릭해주세요.",
    });
  };
  
  const startSelectFieldLocation = (field) => {
    setSelectedFieldId(field.id);
  
    setAlert({
      type: "info",
      msg: `${field.label || "선택한 항목"}을 넣을 위치를 왼쪽 미리보기에서 클릭해주세요.`,
    });
  };
  
  const handlePreviewClick = (e) => {
    if (!selectedFieldId) return;
  
    const target = e.target.closest("[data-cell-id]");
  
    if (!target) {
      setAlert({
        type: "error",
        msg: "위치 ID가 있는 영역만 선택할 수 있습니다. 입력 칸 안쪽을 클릭해주세요.",
      });
      return;
    }
  
    const cellId = target.getAttribute("data-cell-id");
    const locatorType =
      target.getAttribute("data-locator-type") || "table_cell";
  
    if (!cellId) return;
  
    const targetText = target.innerText || "";
  
    if (targetText.includes("{{") || targetText.includes("}}")) {
      setAlert({
        type: "error",
        msg: "이미 다른 자동 입력 항목이 연결된 위치입니다. 빈 입력 칸을 선택해주세요.",
      });
      return;
    }
  
    const locator = {
      type: "cell",
      locator_type: locatorType,
      cell_id: cellId,
    };
  
    setFields((prev) =>
      prev.map((field) => {
        if (field.id !== selectedFieldId) return field;
  
        return {
          ...field,
          cell_id: cellId,
          cell_ids: [cellId],
          locator,
          locators: [locator],
          position_hint: field.position_hint || `문서 위치 ${cellId}`,
          source: field.source || "manual",
        };
      })
    );
  
    setAlert({
      type: "success",
      msg: `위치가 연결되었습니다: ${cellId}`,
    });
  
    setSelectedFieldId(null);
  };

  const handleGenerateDocument = async () => {
    setGenerating(true);
    setAlert(null);

    try {
      validateBeforeGenerate();

      const confirmedFields = removeViewOnlyId(fields);

      const result = await generateEducationDocumentOnce({
        templateName,
        htmlTemplate: previewHtml,
        fields: confirmedFields,
        description,
        receiptFiles,
      });

      setFilledHtml(result.filled_html || "");
      setExpenseData(result.expense_data || null);

      setAlert({
        type: "success",
        msg: "2차 AI 호출이 완료되었습니다. 자동 작성된 결재서류를 확인해보세요.",
      });
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "문서 자동 작성에 실패했습니다.",
      });
    } finally {
      setGenerating(false);
    }
  };

  const handleResetPage = () => {
    const ok = window.confirm(
      "현재 입력한 내용과 AI 분석 결과가 모두 초기화됩니다. 계속하시겠습니까?"
    );
  
    if (!ok) return;
  
    window.location.reload();
  };

  const makeDownloadFileName = (extension) => {
    const safeName = String(templateName || "결재서류")
      .trim()
      .replace(/[\\/:*?"<>|]/g, "_")
      .replace(/\s+/g, "_");

    const today = new Date().toISOString().slice(0, 10);

    return `${safeName}_자동작성본_${today}.${extension}`;
  };

  const downloadBlob = (content, fileName, mimeType) => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();

    a.remove();
    URL.revokeObjectURL(url);
  };

  const downloadFilledHtml = () => {
    if (!filledHtml) {
      setAlert({
        type: "error",
        msg: "다운로드할 자동 작성 결과가 없습니다.",
      });
      return;
    }

    const htmlDocument = `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>${templateName || "자동 작성 결재서류"}</title>
</head>
<body>
${filledHtml}
</body>
</html>`;

    downloadBlob(
      htmlDocument,
      makeDownloadFileName("html"),
      "text/html;charset=utf-8"
    );
  };

  const downloadFilledDoc = () => {
    if (!filledHtml) {
      setAlert({
        type: "error",
        msg: "다운로드할 자동 작성 결과가 없습니다.",
      });
      return;
    }

    const wordDocument = `<!doctype html>
<html lang="ko" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word">
<head>
  <meta charset="utf-8" />
  <title>${templateName || "자동 작성 결재서류"}</title>
  <style>
    body {
      font-family: Malgun Gothic, Apple SD Gothic Neo, sans-serif;
    }
    table {
      border-collapse: collapse;
    }
    td, th {
      vertical-align: middle;
    }
  </style>
</head>
<body>
${filledHtml}
</body>
</html>`;

    downloadBlob(
      wordDocument,
      makeDownloadFileName("doc"),
      "application/msword;charset=utf-8"
    );
  };

  return (
    <div className="main-inner">
        <div className="education-page-head">
            <div>
                <div className="page-title">교육용 결재서류 자동작성 MVP</div>
                <div className="page-desc">
                DB 저장 없이 결재서류 양식을 1차로 분석하고, 사용자가 확인한 항목과 자연어 설명·이미지를 바탕으로 2차 AI 호출을 진행합니다.
                </div>
            </div>

            <button
                type="button"
                className="btn btn-primary"
                onClick={handleResetPage}
            >
                초기화
            </button>
        </div>

      {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}

      <div className="card">
        <div className="card-title">1. 결재서류 양식 업로드</div>

        <div className="form-row">
          <label>양식 이름 *</label>
          <input
            type="text"
            value={templateName}
            onChange={(e) => setTemplateName(e.target.value)}
            placeholder="예: 출장여비선급신청서"
          />
        </div>

        <div className="form-row">
            <label>결재서류 양식 파일 *</label>

            <EducationDropzone
                file={templateFile}
                accept={TEMPLATE_FILE_ACCEPT}
                title="DOCX 양식을 드래그하거나 클릭하여 업로드"
                icon="📄"
                onFileChange={(file) => setTemplateFile(file)}
            />
            </div>

        <button
          type="button"
          className="btn btn-primary"
          onClick={handleAnalyzeTemplate}
          disabled={!canAnalyze || analyzing}
        >
          {analyzing ? "1차 AI 분석 중..." : "1차 AI로 양식 분석하기"}
        </button>
      </div>

      {(previewHtml || fields.length > 0) && (
        <div className="template-setting-grid">
          <div className="card template-preview-card">
            <div className="card-title">2. 양식 미리보기</div>
            <div className="page-desc">
              AI가 자동 입력 위치에 placeholder를 넣은 미리보기입니다.
            </div>

            {previewHtml ? (
              <div className="template-preview-frame">
                <div
                ref={previewRef}
                className={`clickable-template-preview${
                    selectedFieldId ? " selecting-location" : ""
                }`}
                onClick={handlePreviewClick}
                dangerouslySetInnerHTML={{ __html: previewHtml }}
                />
              </div>
            ) : (
              <div className="empty-box">미리보기 HTML이 없습니다.</div>
            )}
          </div>

          <div className="card field-panel-card">
            <div className="education-section-head">
                <div>
                    <div className="card-title">3. 자동 입력 항목 확인</div>
                    <div className="page-desc">
                    필요 없는 항목은 삭제하고, 항목명과 내부 코드를 간단히 수정할 수 있습니다.
                    </div>
                </div>

                <button
                    className="btn btn-primary education-add-field-btn"
                    type="button"
                    onClick={addField}
                >
                  + 필드 추가
                </button>
                </div>

            {fields.length === 0 ? (
              <div className="empty-box">자동 입력 항목이 없습니다.</div>
            ) : (
              <div className="field-list">
                {fields.map((field, index) => (
                  <div className="field-card expanded" key={field.id}>
                    <div className="field-card-head">
                      <div className="field-summary">
                        <strong>
                          {index + 1}. {field.label || "항목명 없음"}
                        </strong>
                        <div className="field-summary-meta">
                          <span>{field.key}</span>
                          <span>{field.type}</span>
                          {getFieldCellIds(field).length > 0 ? (
                            <span>위치: {getFieldCellIds(field).join(", ")}</span>
                          ) : (
                            <span>위치 없음</span>
                          )}
                        </div>
                      </div>

                      <div className="field-card-actions">
                        <button
                            type="button"
                            className="field-toggle-btn"
                            onClick={() => startSelectFieldLocation(field)}
                        >
                            {selectedFieldId === field.id ? "위치 선택 중" : "위치 선택"}
                        </button>

                        <button
                            type="button"
                            className="field-toggle-btn"
                            onClick={() => removeField(field.id)}
                        >
                            삭제
                        </button>
                      </div>
                    </div>

                    <div className="field-edit-area">
                      <div className="form-row">
                        <label>항목명</label>
                        <input
                          value={field.label}
                          onChange={(e) =>
                            updateField(field.id, "label", e.target.value)
                          }
                        />
                      </div>

                      <div className="form-row">
                        <label>내부 코드</label>
                        <input
                          value={field.key}
                          onChange={(e) =>
                            updateField(field.id, "key", e.target.value)
                          }
                          placeholder="예: business_trip_purpose"
                        />
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
                        <label>문서 위치 ID</label>
                        <input
                            type="text"
                            value={getFieldCellIds(field).join(", ")}
                            readOnly
                            className="readonly-input"
                            placeholder="위치 선택 버튼을 누른 뒤 미리보기에서 입력 칸을 클릭하세요."
                        />
                      </div>

                      <label className="problem-filter-row">
                        <input
                          type="checkbox"
                          checked={field.required}
                          onChange={(e) =>
                            updateField(field.id, "required", e.target.checked)
                          }
                        />
                        필수 입력 항목
                      </label>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {previewHtml && fields.length > 0 && (
        <div className="card">
          <div className="card-title">4. 자연어 설명과 관련 이미지 입력</div>

          <div className="form-row">
            <label>자연어 설명 *</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="예: 2026년 4월 18일 부산에서 서울로 거래처 미팅을 다녀왔고, KTX 왕복 교통비 119,600원을 선지급 신청합니다."
              style={{ minHeight: 120 }}
            />
          </div>

          <div className="form-row">
            <label>관련 이미지</label>
            <EducationDropzone
                multiple
                files={receiptFiles}
                accept="image/*"
                title="관련 이미지를 드래그하거나 클릭하여 업로드"
                icon="🖼️"
                previewImage
                onFileChange={(files) => setReceiptFiles(files)}
            />
          </div>

          <button
            type="button"
            className="btn btn-primary"
            onClick={handleGenerateDocument}
            disabled={!canGenerate || generating}
          >
            {generating ? "2차 AI 자동 작성 중..." : "2차 AI로 결재서류 자동 작성"}
          </button>
        </div>
      )}

      {filledHtml && (
        <div className="card">
            <div className="education-result-head">
                <div>
                <div className="card-title">5. 자동 작성 결과</div>
                <div className="page-desc">
                    AI가 작성한 결재서류를 확인한 뒤 파일로 다운로드할 수 있습니다.
                </div>
                </div>

                <div className="education-result-actions">
                <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={downloadFilledHtml}
                >
                    HTML 다운로드
                </button>

                <button
                    type="button"
                    className="btn btn-primary"
                    onClick={downloadFilledDoc}
                >
                    Word 파일 다운로드
                </button>
                </div>
            </div>

            <div className="template-preview-frame">
                <div
                className="clickable-template-preview"
                dangerouslySetInnerHTML={{ __html: filledHtml }}
                />
            </div>
        </div>
      )}

      {expenseData && (
        <div className="card">
          <div className="card-title">AI 추출 데이터</div>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>
            {JSON.stringify(expenseData, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}