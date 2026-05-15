import { useEffect, useState } from "react";
import DropZone from "../components/DropZone";
import EditableHtmlPreview from "../components/EditableHtmlPreview";
import {
  getTemplates,
  getTemplateDetail,
  processExpense,
  sendExpenseEmail,
  updateGeneratedDocument,
} from "../services/api";

// ─── 레이블 한글 매핑 ───────────────────────────────────────────────────────
const LABEL_MAP = {
  expense_date: "지출일",
  request_date: "문서일자",
  department: "부서",
  position: "직급",
  requester: "청구인",
  vendor: "거래처",
  summary_text: "적요",
  purpose: "목적",
  total_amount: "총액",
  supply_amount: "공급가액",
  vat_amount: "부가세",
  payment_method: "결제수단",
  notes: "비고",
  approver_name: "결재자",
  amount_hangul: "금액 한글",
};

function getDisplayLabel(key) {
  return LABEL_MAP[key] || key.replaceAll("_", " ");
}

function isAmountKey(key) {
  const lowered = String(key).toLowerCase();
  return ["amount", "price", "cost", "total", "supply", "vat", "fee", "budget"].some(
    (word) => lowered.includes(word)
  );
}

function isDateKey(key) {
  const lowered = String(key).toLowerCase();
  return lowered.includes("date") || lowered.endsWith("_at");
}

function formatDateValue(value) {
  if (!value) return "-";
  const str = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(str)) {
    const [y, m, d] = str.split("-");
    return `${y}.${m}.${d}`;
  }
  return str;
}

function formatPrimitiveValue(key, value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") {
    if (isAmountKey(key)) return `${value.toLocaleString()}원`;
    return value.toLocaleString();
  }
  if (typeof value === "boolean") return value ? "예" : "아니오";
  const str = String(value).trim();
  if (isDateKey(key)) return formatDateValue(str);
  return str || "-";
}

function renderValue(key, value) {
  if (value === null || value === undefined || value === "") {
    return <span className="result-value">-</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="result-value">-</span>;
    return (
      <div className="result-value" style={{ textAlign: "left", width: "100%" }}>
        {value.map((item, idx) => (
          <div key={idx} style={{ marginBottom: idx === value.length - 1 ? 0 : 6 }}>
            {typeof item === "object" && item !== null
              ? JSON.stringify(item, null, 2)
              : formatPrimitiveValue(key, item)}
          </div>
        ))}
      </div>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 0) return <span className="result-value">-</span>;
    return (
      <div className="result-value" style={{ textAlign: "left", width: "100%" }}>
        {entries.map(([childKey, childValue]) => (
          <div key={childKey} style={{ marginBottom: 6 }}>
            <strong>{getDisplayLabel(childKey)}:</strong>{" "}
            {formatPrimitiveValue(childKey, childValue)}
          </div>
        ))}
      </div>
    );
  }
  return <span className="result-value">{formatPrimitiveValue(key, value)}</span>;
}

// ─── 메인 컴포넌트 ───────────────────────────────────────────────────────────
export default function ProcessPage() {
  const [templates, setTemplates] = useState([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [desc, setDesc] = useState("");
  const [receiptFiles, setReceiptFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [sending, setSending] = useState(false);
  const [alert, setAlert] = useState(null);
  const [selectedTemplatePreview, setSelectedTemplatePreview] = useState(null);
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);

  // ── 편집 관련 상태 ──────────────────────────────────────────────────────
  const [editedHtml, setEditedHtml] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);

  // ── 템플릿 목록 로드 ────────────────────────────────────────────────────
  useEffect(() => {
    const loadTemplates = async () => {
      try {
        const data = await getTemplates();
        setTemplates(data);
        if (data.length > 0) {
          setSelectedTemplateId(String(data[0].id));
        }
      } catch (e) {
        setAlert({ type: "error", msg: e.message || "템플릿 목록 조회 실패" });
      }
    };
    loadTemplates();
  }, []);

  // ── 자동 작성 실행 ──────────────────────────────────────────────────────
  const process = async () => {
    if (!desc.trim()) {
      setAlert({ type: "error", msg: "설명을 입력해주세요." });
      return;
    }
    if (!selectedTemplateId) {
      setAlert({ type: "error", msg: "템플릿을 먼저 선택해주세요." });
      return;
    }

    setLoading(true);
    setResult(null);
    setEditedHtml("");
    setEditMode(false);
    setAlert(null);

    try {
      const data = await processExpense({
        templateId: selectedTemplateId,
        desc,
        receiptFiles,
      });
      setResult(data);
      setEditedHtml(data.filled_html || "");
    } catch (e) {
      setAlert({ type: "error", msg: e.message || "문서 생성 실패" });
    } finally {
      setLoading(false);
    }
  };

  // ── 템플릿 미리보기 ─────────────────────────────────────────────────────
  const openTemplatePreview = async (templateId) => {
    if (!templateId) {
      setAlert({ type: "error", msg: "미리보기할 템플릿을 먼저 선택해주세요." });
      return;
    }
    setPreviewLoading(true);
    setAlert(null);
    try {
      const detail = await getTemplateDetail(templateId);
      setSelectedTemplatePreview(detail);
      setPreviewModalOpen(true);
    } catch (e) {
      setAlert({ type: "error", msg: e.message || "미리보기를 불러오지 못했습니다." });
    } finally {
      setPreviewLoading(false);
    }
  };

  const closeTemplatePreview = () => setPreviewModalOpen(false);

  // ── 편집 내용 저장 ──────────────────────────────────────────────────────
  const saveEditedHtml = async () => {
    if (!result?.document_id) return;
    setSavingEdit(true);
    setAlert(null);
    try {
      await updateGeneratedDocument({
        documentId: result.document_id,
        htmlContent: editedHtml,
      });
      setAlert({ type: "success", msg: "수정 내용이 저장되었습니다." });
    } catch (e) {
      setAlert({ type: "error", msg: e.message || "저장 실패" });
    } finally {
      setSavingEdit(false);
    }
  };

  // ── 이메일 발송 (editedHtml 기준) ────────────────────────────────────────
  const sendEmail = async () => {
    if (!result) return;
    setSending(true);
    setAlert(null);
    try {
      await sendExpenseEmail(result, editedHtml);
      setAlert({
        type: "success",
        msg: `이메일을 발송했습니다. (${result.recipient_email || "수신자 없음"})`,
      });
    } catch (e) {
      setAlert({ type: "error", msg: e.message || "이메일 발송 실패" });
    } finally {
      setSending(false);
    }
  };

  const selectedTemplate = templates.find(
    (t) => String(t.id) === String(selectedTemplateId)
  );

  const entries = result?.expense_data
    ? Object.entries(result.expense_data).filter(
        ([, value]) => value !== null && value !== undefined && value !== ""
      )
    : [];

  const handleDownloadWord = () => {
    const html = editedHtml || "";

    const wordHtml = `
  <!DOCTYPE html>
  <html>
  <head>
    <meta charset="utf-8" />
    <title>${result?.template_name || "document"}</title>
  </head>
  <body>
  ${html}
  </body>
  </html>
  `;

    const blob = new Blob([wordHtml], {
      type: "application/msword;charset=utf-8",
    });

    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = `${result?.template_name || "document"}.doc`;

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
  };

  // ─── 렌더 ────────────────────────────────────────────────────────────────
  return (
    <div className="main-inner">
      <div className="page-title">결재서류 작성</div>
      <div className="page-desc">
        저장된 템플릿을 선택한 뒤 자연어 설명과 증빙 이미지를 입력하면 AI가 문서를
        자동 작성합니다.
      </div>

      {alert && (
        <div className={`alert alert-${alert.type}`}>{alert.msg}</div>
      )}

      {/* ── [1] 문서 작성 요청 카드 ── */}
      <div className="card">
        <div className="card-title">문서 작성 요청</div>

        <div className="form-row">
          <label>결재서류 템플릿 선택 *</label>
          <select
            value={selectedTemplateId}
            onChange={(e) => setSelectedTemplateId(e.target.value)}
          >
            <option value="">템플릿을 선택하세요</option>
            {templates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.template_name} ({template.file_name})
              </option>
            ))}
          </select>
        </div>

        {selectedTemplate && (
          <div className="form-row">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => openTemplatePreview(selectedTemplateId)}
                disabled={previewLoading || !selectedTemplateId}
                style={{ width: "auto", minWidth: 120 }}
              >
                {previewLoading ? (
                  <>
                    <span className="spinner" />
                    불러오는 중...
                  </>
                ) : (
                  "선택한 템플릿 미리보기"
                )}
              </button>
            </div>
          </div>
        )}

        <div className="form-row">
          <label>자연어 설명 *</label>
          <textarea
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="예: 지난주 금요일 개발팀 홍길동 팀장이 거래처 ABC컨설팅과 점심 미팅 후 식대 55,000원을 법인카드로 결제했습니다."
            style={{ minHeight: 120 }}
          />
        </div>

        <div className="form-row">
          <label>증빙 이미지 (선택)</label>
          <DropZone
            label="증빙 이미지를 드래그하거나 클릭하여 업로드"
            accept="image/*"
            files={receiptFiles}
            setFiles={setReceiptFiles}
            multiple
            icon="🧾"
          />
        </div>

        <button
          className="btn btn-primary"
          onClick={process}
          disabled={loading || !desc.trim() || !selectedTemplateId}
        >
          {loading ? (
            <>
              <span className="spinner" />
              처리 중...
            </>
          ) : (
            "자동 작성"
          )}
        </button>
      </div>

      {/* ── [2] 생성 결과 카드 ── */}
      {result && (
        <div className="card">
          <div
            className="card-title"
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>생성 결과</span>
            <span className="badge badge-ok">완료</span>
          </div>

          <div style={{ marginBottom: 12 }}>
            사용 템플릿: <strong>{result.template_name}</strong>
          </div>

          {/* AI 추출 데이터 */}
          <div className="result-box">
            {entries.length === 0 ? (
              <div className="page-desc" style={{ marginBottom: 0 }}>
                추출된 데이터가 없습니다.
              </div>
            ) : (
              entries.map(([key, value]) => (
                <div
                  className="result-row"
                  key={key}
                  style={{
                    alignItems:
                      Array.isArray(value) ||
                      (typeof value === "object" && value !== null)
                        ? "flex-start"
                        : "center",
                  }}
                >
                  <span className="result-label">{getDisplayLabel(key)}</span>
                  {renderValue(key, value)}
                </div>
              ))
            )}
          </div>

          {/* 이메일 발송 대상 */}
          <div style={{ marginTop: 20 }}>
            <div className="card-title">이메일 발송 대상</div>
            <div className="email-preview">
              결재자:{" "}
              <span className="email-to">{result.recipient_name || "-"}</span>
              {" → "}
              <span className="email-to">
                {result.recipient_email || "⚠ 조직도에 이메일 없음"}
              </span>
            </div>
          </div>

          {/* ── [3] 문서 미리보기 & 편집 영역 ── */}
          <div className="html-preview-wrap">
            {/* 상단 바 */}
            <div
              className="html-preview-bar"
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              <span>
                결재서류 미리보기
                {editMode && (
                  <span
                    style={{
                      marginLeft: 8,
                      color: "var(--accent)",
                      fontWeight: 700,
                      fontSize: 12,
                    }}
                  >
                    ✏ 편집 모드
                  </span>
                )}
              </span>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                {/* 편집 모드 토글 */}
                <button
                  type="button"
                  className={`btn ${editMode ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setEditMode((v) => !v)}
                  style={{ width: "auto", minWidth: 110, fontSize: 12 }}
                >
                  {editMode ? "미리보기 모드" : "편집 모드"}
                </button>

                {/* 수정 내용 저장 (편집 모드일 때만) */}
                {editMode && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={saveEditedHtml}
                    disabled={savingEdit}
                    style={{ width: "auto", minWidth: 110, fontSize: 12 }}
                  >
                    {savingEdit ? (
                      <>
                        <span className="spinner" />
                        저장 중...
                      </>
                    ) : (
                      "수정 내용 저장"
                    )}
                  </button>
                )}

                <button
                  type="button"
                  onClick={handleDownloadWord}
                  className="btn btn-secondary"
                >
                  Word 다운로드
                </button>
              </div>
            </div>

            {/* 편집 모드 안내 문구 */}
            {editMode && (
              <div
                style={{
                  background: "rgba(99,102,241,0.08)",
                  border: "1px solid var(--accent)",
                  borderRadius: 6,
                  padding: "8px 12px",
                  marginBottom: 8,
                  fontSize: 13,
                  color: "var(--accent)",
                }}
              >
                현재 편집 모드입니다. 문서 내용을 직접 수정한 뒤 저장하세요.
              </div>
            )}

            {/* 편집 모드: EditableHtmlPreview */}
            {editMode ? (
              <EditableHtmlPreview
                key={result.document_id}
                html={editedHtml}
                editable
                onChange={setEditedHtml}
              />
            ) : (
              /* 미리보기 모드: iframe (editedHtml 기준으로 최신 상태 표시) */
              <iframe
                srcDoc={editedHtml}
                sandbox="allow-same-origin"
                style={{
                  width: "100%",
                  minHeight: 420,
                  border: "1px solid var(--border, #333)",
                  borderRadius: 8,
                  background: "#fff",
                }}
              />
            )}
          </div>

          {/* ── [4] 액션 버튼 ── */}
          <div style={{ display: "flex", gap: 10, marginTop: 20, flexWrap: "wrap" }}>
            <button
              className="btn btn-primary"
              onClick={sendEmail}
              disabled={sending || !result.recipient_email}
            >
              {sending ? (
                <>
                  <span className="spinner" />
                  발송 중...
                </>
              ) : (
                "이메일 발송"
              )}
            </button>

            <button
              className="btn btn-secondary"
              onClick={() => {
                setResult(null);
                setEditedHtml("");
                setEditMode(false);
                setDesc("");
                setReceiptFiles([]);
              }}
            >
              새 문서 작성
            </button>
          </div>
        </div>
      )}

      {/* ── 템플릿 미리보기 모달 ── */}
      {previewModalOpen && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1000,
            backgroundColor: "rgba(0, 0, 0, 0.45)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 20,
          }}
          onClick={closeTemplatePreview}
        >
          <div
            className="card"
            style={{
              width: "min(1100px, 96vw)",
              height: "min(820px, 92vh)",
              margin: 0,
              display: "flex",
              flexDirection: "column",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="card-title"
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
                marginBottom: 12,
              }}
            >
              <span>선택한 템플릿 미리보기</span>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={closeTemplatePreview}
                style={{ width: "auto", minWidth: 80 }}
              >
                닫기
              </button>
            </div>

            <div className="page-desc" style={{ marginBottom: 12 }}>
              {selectedTemplatePreview?.template_name || "-"}
              {selectedTemplatePreview?.file_name
                ? ` (${selectedTemplatePreview.file_name})`
                : ""}
            </div>

            {selectedTemplatePreview?.html_content ? (
              <iframe
                title="template-preview"
                srcDoc={selectedTemplatePreview.html_content.replace(
                  /<script[\s\S]*?>[\s\S]*?<\/script>/gi,
                  ""
                )}
                sandbox="allow-same-origin"
                style={{
                  flex: 1,
                  width: "100%",
                  border: "1px solid #ddd",
                  borderRadius: 8,
                  backgroundColor: "#fff",
                }}
              />
            ) : (
              <div className="page-desc" style={{ marginBottom: 0 }}>
                미리보기 가능한 HTML이 없습니다.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
