import { useEffect, useMemo, useState } from "react";
import DropZone from "../components/DropZone";
import { getTemplates, processExpense, sendExpenseEmail } from "../services/api";

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
  return [
    "amount",
    "price",
    "cost",
    "total",
    "supply",
    "vat",
    "fee",
    "budget",
  ].some((word) => lowered.includes(word));
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
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  if (typeof value === "number") {
    if (isAmountKey(key)) {
      return `${value.toLocaleString()}원`;
    }
    return value.toLocaleString();
  }

  if (typeof value === "boolean") {
    return value ? "예" : "아니오";
  }

  const str = String(value).trim();

  if (isDateKey(key)) {
    return formatDateValue(str);
  }

  return str || "-";
}

function renderValue(key, value) {
  if (value === null || value === undefined || value === "") {
    return <span className="result-value">-</span>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="result-value">-</span>;
    }

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
    if (entries.length === 0) {
      return <span className="result-value">-</span>;
    }

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

export default function ProcessPage() {
  const [templates, setTemplates] = useState([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [desc, setDesc] = useState("");
  const [receiptFile, setReceiptFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [sending, setSending] = useState(false);
  const [alert, setAlert] = useState(null);

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

  const safeHtml = useMemo(() => {
    if (!result?.filled_html) return "";
    return result.filled_html.replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, "");
  }, [result]);

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
    setAlert(null);

    try {
      const data = await processExpense({
        templateId: selectedTemplateId,
        desc,
        receiptFile,
      });
      setResult(data);
    } catch (e) {
      setAlert({ type: "error", msg: e.message || "문서 생성 실패" });
    } finally {
      setLoading(false);
    }
  };

  const sendEmail = async () => {
    if (!result) return;

    setSending(true);
    setAlert(null);

    try {
      await sendExpenseEmail(result);
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

  return (
    <div className="main-inner">
      <div className="page-title">결재서류 작성</div>
      <div className="page-desc">
        저장된 템플릿을 선택한 뒤 자연어 설명과 영수증을 입력하면 AI가 문서를 자동 작성합니다.
      </div>

      {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}

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

        {selectedTemplate?.placeholder_keys?.length > 0 && (
          <div className="form-row">
            <label>템플릿 플레이스홀더 키</label>
            <div className="page-desc" style={{ marginBottom: 0 }}>
              {selectedTemplate.placeholder_keys.join(", ")}
            </div>
          </div>
        )}

        <div className="form-row">
          <label>자연어 설명 *</label>
          <textarea
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="예: 지난주 금요일 개발팀 강지윤이 거래처 ABC컨설팅과 점심 미팅 후 식대 55,000원을 법인카드로 결제했습니다."
            style={{ minHeight: 120 }}
          />
        </div>

        <div className="form-row">
          <label>영수증 이미지 (선택)</label>
          <DropZone
            label="영수증 이미지를 드래그하거나 클릭하여 업로드"
            accept="image/*"
            file={receiptFile}
            setFile={setReceiptFile}
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

      {result && (
        <div className="card">
          <div
            className="card-title"
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
          >
            <span>생성 결과</span>
            <span className="badge badge-ok">완료</span>
          </div>

          <div style={{ marginBottom: 12 }}>
            사용 템플릿: <strong>{result.template_name}</strong>
          </div>

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
                      Array.isArray(value) || (typeof value === "object" && value !== null)
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

          <div style={{ marginTop: 20 }}>
            <div className="card-title">이메일 발송 대상</div>
            <div className="email-preview">
              결재자: <span className="email-to">{result.recipient_name || "-"}</span>
              {" → "}
              <span className="email-to">
                {result.recipient_email || "⚠ 조직도에 이메일 없음"}
              </span>
            </div>
          </div>

          <div className="html-preview-wrap">
            <div className="html-preview-bar">
              <span>결재서류 미리보기</span>
              <a
                href={`data:text/html;charset=utf-8,${encodeURIComponent(safeHtml)}`}
                download={`${result.template_name || "document"}.html`}
                style={{ color: "var(--accent2)", fontSize: 11 }}
              >
                다운로드
              </a>
            </div>
            <iframe srcDoc={safeHtml} sandbox="allow-same-origin" />
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
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
                setDesc("");
                setReceiptFile(null);
              }}
            >
              새 문서 작성
            </button>
          </div>
        </div>
      )}
    </div>
  );
}