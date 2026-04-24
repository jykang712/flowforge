import { useEffect, useState } from "react";
import OrgEditor from "../components/OrgEditor";
import DropZone from "../components/DropZone";
import {
  createOrgMember,
  getOrgMembers,
  previewOrgMembersByImage,
  savePreviewOrgMembers,
} from "../services/api";

export default function OrgPage() {
  const [org, setOrg] = useState([
    { name: "", department: "", title: "", email: "" },
  ]);
  const [existingMembers, setExistingMembers] = useState([]);

  const [saving, setSaving] = useState(false);
  const [alert, setAlert] = useState(null);

  // 이미지 업로드/미리보기용 상태
  const [orgImageFile, setOrgImageFile] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewSaving, setPreviewSaving] = useState(false);
  const [previewRows, setPreviewRows] = useState([]);

  const loadMembers = async () => {
    try {
      const data = await getOrgMembers();
      setExistingMembers(data);
    } catch (e) {
      setAlert({ type: "error", msg: e.message || "조직도 조회 실패" });
    }
  };

  useEffect(() => {
    loadMembers();
  }, []);

  // 수동 입력 저장
  const saveMembers = async () => {
    setSaving(true);
    setAlert(null);

    try {
      const validMembers = org.filter(
        (m) => m.name && m.title && m.email
      );

      if (!validMembers.length) {
        throw new Error("저장할 조직도 정보를 입력해주세요.");
      }

      for (const member of validMembers) {
        await createOrgMember({
          name: member.name,
          department: member.department,
          title: member.title,
          email: member.email,
        });
      }

      setAlert({ type: "success", msg: "조직도가 저장되었습니다." });
      setOrg([{ name: "", department: "", title: "", email: "" }]);
      await loadMembers();
    } catch (e) {
      setAlert({ type: "error", msg: e.message || "조직도 저장 실패" });
    } finally {
      setSaving(false);
    }
  };

  // 이미지 분석 실행
  const handlePreviewImage = async () => {
    setPreviewLoading(true);
    setAlert(null);

    try {
      const result = await previewOrgMembersByImage({
        imageFile: orgImageFile,
      });

      setPreviewRows(result.rows || []);
      setAlert({
        type: "success",
        msg: `이미지 분석 완료: ${result.parsed_count || 0}건 인식`,
      });
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "조직도 이미지 분석 실패",
      });
    } finally {
      setPreviewLoading(false);
    }
  };

  // 미리보기 행 수정
  const updatePreviewRow = (index, key, value) => {
    setPreviewRows((prev) =>
      prev.map((row, i) => (i === index ? { ...row, [key]: value } : row))
    );
  };

  // 미리보기 행 삭제
  const removePreviewRow = (index) => {
    setPreviewRows((prev) => prev.filter((_, i) => i !== index));
  };

  // 미리보기 저장
  const handleSavePreview = async () => {
    setPreviewSaving(true);
    setAlert(null);

    try {
      const result = await savePreviewOrgMembers(previewRows);

      await loadMembers();

      if (result.skipped_count > 0) {
        setPreviewRows(result.skipped.map((item) => item.data));
        setAlert({
          type: "success",
          msg: `저장 완료: ${result.saved_count}건 저장, ${result.skipped_count}건 제외`,
        });
      } else {
        setPreviewRows([]);
        setOrgImageFile(null);
        setAlert({
          type: "success",
          msg: `저장 완료: ${result.saved_count}건 저장`,
        });
      }
    } catch (e) {
      setAlert({
        type: "error",
        msg: e.message || "미리보기 저장 실패",
      });
    } finally {
      setPreviewSaving(false);
    }
  };

  return (
    <div className="main-inner">
      <div className="page-title">조직도 관리</div>
      <div className="page-desc">
        이름, 부서, 직급, 이메일을 등록하여 결재자 정보를 관리하세요.
      </div>

      {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}

      {/* 수동 등록 */}
      <div className="card">
        <div className="card-title">조직도 등록</div>
        <OrgEditor org={org} setOrg={setOrg} />
        <div className="org-card-actions">
          <button type="button" className="btn btn-primary" onClick={saveMembers} disabled={saving}>
            {saving ? <span className="spinner" /> : ""} 조직도 저장
          </button>
        </div>
      </div>

      {/* 이미지 자동 분석 */}
      <div className="card org-image-card">
        <div className="card-title">조직도 이미지 자동 분석</div>

        <DropZone
          label="조직도 표 이미지를 드래그하거나 클릭하여 업로드"
          accept="image/*"
          file={orgImageFile}
          setFile={setOrgImageFile}
          icon="🖼️"
        />

        <div className="org-section-note">
          표가 선명한 캡처본일수록 이름, 부서, 직급, 이메일 인식률이 높습니다.
        </div>

        <div className="org-card-actions">
          <button
            className="btn btn-secondary"
            onClick={handlePreviewImage}
            disabled={!orgImageFile || previewLoading}
          >
            {previewLoading ? <span className="spinner" /> : ""} 이미지 분석
          </button>
        </div>

        {previewRows.length > 0 ? (
          <div className="org-preview-wrap">
            <div className="org-preview-head">
              <div>
                <div className="org-preview-title">이미지 분석 결과 미리보기</div>
                <div className="org-preview-desc">
                  저장 전에 잘못 인식된 값을 직접 수정할 수 있습니다.
                </div>
              </div>
              <div className="org-preview-badge">PREVIEW {previewRows.length}</div>
            </div>

            <div className="org-preview-table-wrap">
              <table className="org-table">
                <thead>
                  <tr>
                    <th>이름</th>
                    <th>부서</th>
                    <th>직급</th>
                    <th>이메일</th>
                    <th style={{ width: 60 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {previewRows.map((row, index) => (
                    <tr key={index}>
                      <td>
                        <input
                          type="text"
                          value={row.name || ""}
                          onChange={(e) =>
                            updatePreviewRow(index, "name", e.target.value)
                          }
                          placeholder="이름"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={row.department || ""}
                          onChange={(e) =>
                            updatePreviewRow(index, "department", e.target.value)
                          }
                          placeholder="부서"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={row.title || ""}
                          onChange={(e) =>
                            updatePreviewRow(index, "title", e.target.value)
                          }
                          placeholder="직급"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={row.email || ""}
                          onChange={(e) =>
                            updatePreviewRow(index, "email", e.target.value)
                          }
                          placeholder="이메일"
                        />
                      </td>
                      <td>
                        <button
                          className="btn btn-ghost"
                          type="button"
                          onClick={() => removePreviewRow(index)}
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="org-preview-actions">
              <button
                className="btn btn-primary"
                onClick={handleSavePreview}
                disabled={previewSaving || previewRows.length === 0}
              >
                {previewSaving ? <span className="spinner" /> : ""} 확인 후 저장
              </button>

              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => {
                  setPreviewRows([]);
                  setOrgImageFile(null);
                }}
                disabled={previewSaving}
              >
                취소
              </button>
            </div>
          </div>
        ) : orgImageFile ? (
          <div className="org-empty-box">
            업로드된 이미지는 준비되었습니다. “이미지 분석” 버튼을 눌러 미리보기를 생성하세요.
          </div>
        ) : null}
      </div>

      {/* 저장된 조직도 */}
      <div className="card org-list-card">
        <div className="card-title">저장된 조직도</div>
        {existingMembers.length === 0 ? (
          <div className="page-desc">아직 등록된 조직도가 없습니다.</div>
        ) : (
          <table className="org-table">
            <thead>
              <tr>
                <th>이름</th>
                <th>부서</th>
                <th>직급</th>
                <th>이메일</th>
              </tr>
            </thead>
            <tbody>
              {existingMembers.map((member) => (
                <tr key={member.id}>
                  <td>{member.name}</td>
                  <td>{member.department || "-"}</td>
                  <td>{member.title}</td>
                  <td>{member.email}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}