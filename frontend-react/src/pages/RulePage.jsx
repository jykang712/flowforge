import { useEffect, useState } from "react";
import DropZone from "../components/DropZone";
import RuleEditor from "../components/RuleEditor";
import {
  getTemplates,
  getOrgMembers,
  getApprovalRules,
  saveApprovalRules,
  previewApprovalRulesByGuide,
  savePreviewApprovalRules,
} from "../services/api";

export default function RulePage() {
  const createEmptyRule = () => ({
    ruleName: "",
    ruleText: "",
    templateId: "",
    sourceExcerpt: "",
    approvers: [
      {
        approverMemberId: "",
        approvalType: "결재",
        approvalOrder: 1,
      },
    ],
  });

  const normalizePreviewRule = (rule) => ({
    ruleName: rule.rule_name || "",
    ruleText: rule.rule_text || "",
    templateId: String(rule.template_id || ""),
    sourceExcerpt: rule.source_excerpt || "",
    approvers: (rule.approvers || [])
      .sort((a, b) => (a.approval_order || 1) - (b.approval_order || 1))
      .map((a, index) => ({
        approverMemberId: String(a.approver_member_id || ""),
        approvalType: a.approval_type || "결재",
        approvalOrder: a.approval_order || index + 1,
      })),
  });

  const [templates, setTemplates] = useState([]);
  const [orgMembers, setOrgMembers] = useState([]);

  // 자동 초안용
  const [guideFile, setGuideFile] = useState(null);
  const [previewRules, setPreviewRules] = useState([]);
  const [previewSourceName, setPreviewSourceName] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewSaving, setPreviewSaving] = useState(false);

  // 수동 등록용
  const [manualRules, setManualRules] = useState([createEmptyRule()]);
  const [manualSaving, setManualSaving] = useState(false);

  // 저장된 목록
  const [existingRules, setExistingRules] = useState([]);

  const [alert, setAlert] = useState(null);

  const loadData = async () => {
    try {
      const [templateData, memberData, ruleData] = await Promise.all([
        getTemplates(),
        getOrgMembers(),
        getApprovalRules(),
      ]);

      setTemplates(templateData);
      setOrgMembers(memberData);
      setExistingRules(ruleData);
    } catch (e) {
      setAlert({ type: "error", msg: e.message || "데이터 조회 실패" });
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // -----------------------------
  // 자동 초안 생성
  // -----------------------------
  const handlePreviewGuide = async () => {
    setPreviewLoading(true);
    setAlert(null);

    try {
      const result = await previewApprovalRulesByGuide({ guideFile });
      const normalized = (result.rules || []).map(normalizePreviewRule);

      setPreviewRules(normalized);
      setPreviewSourceName(result.source_name || "");

      setAlert({
        type: "success",
        msg: `지침서 분석 완료: ${result.parsed_rule_count || 0}개 규칙 초안 생성`,
      });
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "지침서 분석 실패",
      });
    } finally {
      setPreviewLoading(false);
    }
  };

  // -----------------------------
  // 자동 초안 저장
  // -----------------------------
  const handleSavePreview = async () => {
    setPreviewSaving(true);
    setAlert(null);

    try {
      const result = await savePreviewApprovalRules(
        previewRules,
        previewSourceName
      );

      setPreviewRules([]);
      setGuideFile(null);
      setPreviewSourceName("");

      await loadData();

      setAlert({
        type: "success",
        msg: `결재 처리 방침 저장 완료: ${result.saved_rule_count}건`,
      });
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "결재 처리 방침 저장 실패",
      });
    } finally {
      setPreviewSaving(false);
    }
  };

  // -----------------------------
  // 수동 저장
  // -----------------------------
  const saveManualRules = async () => {
    setManualSaving(true);
    setAlert(null);

    try {
      const validRules = manualRules.filter((rule) => {
        if (!rule.ruleName?.trim() || !rule.ruleText?.trim() || !rule.templateId) {
          return false;
        }

        if (!rule.approvers || rule.approvers.length === 0) {
          return false;
        }

        return rule.approvers.every(
          (approver) =>
            approver.approverMemberId && (approver.approvalType || "").trim()
        );
      });

      if (!validRules.length) {
        throw new Error("저장할 결재 처리 방침을 입력해주세요.");
      }

      await saveApprovalRules(validRules);

      setAlert({ type: "success", msg: "수동 결재 처리 방침이 저장되었습니다." });
      setManualRules([createEmptyRule()]);

      await loadData();
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "수동 결재 처리 방침 저장 실패",
      });
    } finally {
      setManualSaving(false);
    }
  };

  return (
    <div className="main-inner">
      <div className="page-title">결재 처리 방침 관리</div>
      <div className="page-desc">
        지침서 기반 자동 초안을 먼저 검토하고, 필요하면 수동으로 규칙을 추가하세요.
      </div>

      {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}

      {/* 1. 지침서 기반 자동 초안 */}
      <div className="card rule-guide-card">
        <div className="card-title">지침서 기반 자동 초안</div>

        <DropZone
          label="결재 처리 지침서 PDF를 드래그하거나 클릭하여 업로드"
          accept=".pdf,application/pdf"
          file={guideFile}
          setFile={setGuideFile}
          icon="📘"
        />

        <div className="rule-guide-note">
          텍스트 기반 PDF에서 가장 정확하게 동작합니다.
        </div>

        <div className="rule-card-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handlePreviewGuide}
            disabled={!guideFile || previewLoading}
          >
            {previewLoading ? (
              <>
                <span className="spinner" />
                분석 중...
              </>
            ) : (
              "지침서 분석"
            )}
          </button>
        </div>

        {previewRules.length > 0 ? (
          <div className="rule-preview-wrap">
            <div className="rule-preview-head">
              <div>
                <div className="rule-preview-title">
                  자동 생성된 결재 처리 방침 초안
                </div>
                <div className="rule-preview-desc">
                  규칙명, 규칙 내용, 적용 템플릿, 결재자를 검토한 뒤 저장하세요.
                </div>
              </div>
              <div className="rule-preview-badge">
                PREVIEW {previewRules.length}
              </div>
            </div>

            <RuleEditor
              rules={previewRules}
              setRules={setPreviewRules}
              templates={templates}
              orgMembers={orgMembers}
            />

            <div className="rule-card-actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSavePreview}
                disabled={previewSaving || previewRules.length === 0}
              >
                {previewSaving ? (
                  <>
                    <span className="spinner" />
                    저장 중...
                  </>
                ) : (
                  "초안 확인 후 저장"
                )}
              </button>

              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => {
                  setPreviewRules([]);
                  setGuideFile(null);
                  setPreviewSourceName("");
                }}
                disabled={previewSaving}
              >
                취소
              </button>
            </div>
          </div>
        ) : guideFile ? (
          <div className="rule-empty-box">
            업로드된 PDF는 준비되었습니다. “지침서 분석” 버튼을 눌러 초안을 생성하세요.
          </div>
        ) : null}
      </div>

      {/* 2. 수동 등록 */}
      <div className="card" style={{ marginTop: 24 }}>
        <div className="card-title">수동 등록</div>

        <RuleEditor
          rules={manualRules}
          setRules={setManualRules}
          templates={templates}
          orgMembers={orgMembers}
        />

        <div className="rule-card-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={saveManualRules}
            disabled={manualSaving}
          >
            {manualSaving ? (
              <>
                <span className="spinner" />
                저장 중...
              </>
            ) : (
              "수동 규칙 저장"
            )}
          </button>
        </div>
      </div>

      {/* 3. 저장된 결재 처리 방침 */}
      <div className="card rule-list-card">
        <div
          className="card-title"
          style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
        >
          <span>저장된 결재 처리 방침</span>
          <span className="badge badge-ok">{existingRules.length}건</span>
        </div>

        {existingRules.length === 0 ? (
          <div
            className="page-desc"
            style={{
              marginBottom: 0,
              padding: "8px 0 4px",
            }}
          >
            아직 저장된 결재 처리 방침이 없습니다.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="org-table">
              <thead>
                <tr>
                  <th style={{ minWidth: 140 }}>규칙명</th>
                  <th style={{ minWidth: 220 }}>규칙 내용</th>
                  <th style={{ minWidth: 160 }}>적용 템플릿</th>
                  <th style={{ minWidth: 280 }}>결재자</th>
                </tr>
              </thead>
              <tbody>
                {existingRules.map((rule) => (
                  <tr key={rule.id}>
                    <td>{rule.rule_name}</td>
                    <td style={{ whiteSpace: "normal", lineHeight: 1.6 }}>
                      {rule.rule_text}
                    </td>
                    <td>{rule.template_name || "-"}</td>
                    <td style={{ whiteSpace: "normal", lineHeight: 1.6 }}>
                      {rule.approvers && rule.approvers.length > 0
                        ? rule.approvers
                            .map(
                              (a) =>
                                `${a.approval_order}차 ${a.approver_name}${
                                  a.approver_title ? ` (${a.approver_title})` : ""
                                }${
                                  a.approval_type ? ` / ${a.approval_type}` : ""
                                }`
                            )
                            .join(", ")
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
  );
}