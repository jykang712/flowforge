import { useEffect, useState } from "react";
import DropZone from "../components/DropZone";
import { createTemplate, getTemplates } from "../services/api";

export default function SetupPage() {
  const [templateFile, setTemplateFile] = useState(null);
  const [templateName, setTemplateName] = useState("");
  const [description, setDescription] = useState("");
  const [templates, setTemplates] = useState([]);
  const [templateSaving, setTemplateSaving] = useState(false);
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const data = await getTemplates();
      setTemplates(data);
    } catch (e) {
      setAlert({ type: "error", msg: e.message || "템플릿 목록 조회 실패" });
    }
  };

  const handleTemplateSave = async () => {
    setTemplateSaving(true);
    setAlert(null);

    try {
      const result = await createTemplate({
        templateFile,
        templateName,
        description,
      });

      setTemplateFile(null);
      setTemplateName("");
      setDescription("");

      await loadTemplates();

      const keyText =
        result?.placeholder_keys && result.placeholder_keys.length > 0
          ? `생성된 키: ${result.placeholder_keys.join(", ")}`
          : "플레이스홀더 키를 생성했습니다.";

      setAlert({
        type: "success",
        msg: `템플릿이 저장되었습니다. ${keyText}`,
      });
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "템플릿 저장에 실패했습니다.",
      });
    } finally {
      setTemplateSaving(false);
    }
  };

  return (
    <div className="main-inner">
      <div className="page-title">결재 서류 관리</div>
      <div className="page-desc">
        결재서류 PDF 또는 HTML을 업로드하면 AI가 {"{{key}}"} 형식의 템플릿으로 변환해 저장합니다.
      </div>

      {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}

      <div className="card">
        <div className="card-title">결재서류 템플릿 등록</div>

        <div className="form-row">
          <label>템플릿 이름 *</label>
          <input
            type="text"
            value={templateName}
            onChange={(e) => setTemplateName(e.target.value)}
            placeholder="예: 기본 지출결의서 양식"
          />
        </div>

        <div className="form-row">
          <label>설명</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="예: 일반 지출결의서 양식 / 1페이지 / 결재선 포함"
            style={{ minHeight: 88 }}
          />
        </div>

        <DropZone
          label="결재 템플릿(PDF, HTML)을 드래그하거나 클릭하여 업로드"
          accept=".pdf,.html,.htm"
          file={templateFile}
          setFile={setTemplateFile}
          icon="📄"
        />

        <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
          <button
            className="btn btn-primary"
            onClick={handleTemplateSave}
            disabled={templateSaving || !templateFile || !templateName.trim()}
          >
            {templateSaving ? (
              <>
                <span className="spinner" />
                변환 및 저장 중...
              </>
            ) : (
              "템플릿 저장"
            )}
          </button>
        </div>

        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 14, marginBottom: 10 }}>현재 저장된 템플릿 목록</div>

          {templates.length === 0 ? (
            <div className="page-desc">아직 저장된 템플릿이 없습니다.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="org-table">
                <thead>
                  <tr>
                    <th>템플릿 이름</th>
                    <th>파일명</th>
                    <th>설명</th>
                    <th>플레이스홀더 키</th>
                  </tr>
                </thead>
                <tbody>
                  {templates.map((template) => (
                    <tr key={template.id}>
                      <td>{template.template_name}</td>
                      <td>{template.file_name}</td>
                      <td style={{ whiteSpace: "normal", lineHeight: 1.5 }}>
                        {template.description || "-"}
                      </td>
                      <td style={{ whiteSpace: "normal", lineHeight: 1.5 }}>
                        {template.placeholder_keys?.length > 0
                          ? template.placeholder_keys.join(", ")
                          : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}