import { useEffect, useRef, useState } from "react";
import {
  getGeneratedDocuments,
  getGeneratedDocumentDetail,
  updateGeneratedDocument,
  deleteGeneratedDocument,
} from "../services/api";

// script 태그 제거 (XSS 방지)
function stripScripts(html) {
  return (html || "").replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "");
}

// 날짜 포맷 (ISO → 한국어)
function formatDate(iso) {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ManagePage() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [listError, setListError] = useState("");

  // 필터
  const [searchText, setSearchText] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  // 모달
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // HTML 편집
  const [editMode, setEditMode] = useState(false);
  const [editedHtml, setEditedHtml] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  // JSON 펼침 여부
  const [jsonOpen, setJsonOpen] = useState(false);

  const textareaRef = useRef(null);

  useEffect(() => {
    fetchDocs();
  }, []);

  const fetchDocs = async () => {
    setLoading(true);
    setListError("");
    try {
      const data = await getGeneratedDocuments();
      setDocs(data);
    } catch (e) {
      setListError(e.message || "목록 조회 실패");
    } finally {
      setLoading(false);
    }
  };

  const openDetail = async (docId) => {
    setModalOpen(true);
    setSelectedDoc(null);
    setDetailLoading(true);
    setEditMode(false);
    setEditedHtml("");
    setSaveMsg("");
    setJsonOpen(false);
    try {
      const data = await getGeneratedDocumentDetail(docId);
      setSelectedDoc(data);
      setEditedHtml(data.html_content || "");
    } catch (e) {
      alert("상세 조회 실패: " + e.message);
      setModalOpen(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeModal = () => {
    setModalOpen(false);
    setSelectedDoc(null);
    setEditMode(false);
    setEditedHtml("");
    setSaveMsg("");
  };

  const handleSave = async () => {
    if (!selectedDoc) return;
    setSaving(true);
    setSaveMsg("");
    try {
      await updateGeneratedDocument({
        documentId: selectedDoc.id,
        htmlContent: editedHtml,
      });
      const updated = await getGeneratedDocumentDetail(selectedDoc.id);
      setSelectedDoc(updated);
      setEditedHtml(updated.html_content || "");
      setEditMode(false);
      setSaveMsg("저장되었습니다.");
      await fetchDocs();
    } catch (e) {
      setSaveMsg("저장 실패: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (docId) => {
    if (!window.confirm("이 문서를 삭제(비활성화)하시겠습니까?")) return;
    try {
      await deleteGeneratedDocument(docId);
      closeModal();
      await fetchDocs();
    } catch (e) {
      alert("삭제 실패: " + e.message);
    }
  };

  const handleDownload = () => {
    const html = editMode ? editedHtml : (selectedDoc?.html_content || "");
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${selectedDoc?.document_title || "document"}.html`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── 필터링 ──────────────────────────────────────────────────────────────────
  const filtered = docs.filter((doc) => {
    if (statusFilter === "sent" && !doc.is_sent) return false;
    if (statusFilter === "unsent" && doc.is_sent) return false;

    const q = searchText.trim().toLowerCase();
    if (q) {
      const haystack = [
        doc.requester_name,
        doc.requester_department,
        doc.template_name,
        doc.document_title,
        doc.approval_line_text,
        doc.recipient_name,
      ]
        .map((v) => (v || "").toLowerCase())
        .join(" ");
      if (!haystack.includes(q)) return false;
    }
    return true;
  });

  // ── 요약 통계 ────────────────────────────────────────────────────────────────
  const total = docs.length;
  const unsent = docs.filter((d) => !d.is_sent).length;
  const sent = docs.filter((d) => d.is_sent).length;

  // ── 스타일 상수 ──────────────────────────────────────────────────────────────
  const S = {
    statGrid: {
      display: "grid",
      gridTemplateColumns: "repeat(3, 1fr)",
      gap: 12,
      marginBottom: 24,
    },
    statCard: {
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 12,
      padding: "18px 20px",
      textAlign: "center",
    },
    statValue: { fontSize: 28, fontWeight: 700, color: "var(--accent)" },
    statLabel: { fontSize: 12, color: "var(--muted)", marginTop: 4 },

    filterRow: {
      display: "flex",
      gap: 10,
      marginBottom: 16,
      flexWrap: "wrap",
    },
    searchInput: {
      flex: 1,
      minWidth: 200,
      padding: "8px 12px",
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      color: "var(--text)",
      fontSize: 13,
    },
    select: {
      padding: "8px 12px",
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      color: "var(--text)",
      fontSize: 13,
    },

    table: {
      width: "100%",
      borderCollapse: "collapse",
      fontSize: 13,
    },
    th: {
      padding: "10px 12px",
      background: "var(--surface2)",
      color: "var(--muted)",
      fontWeight: 600,
      textAlign: "left",
      borderBottom: "1px solid var(--border)",
      whiteSpace: "nowrap",
    },
    td: {
      padding: "10px 12px",
      borderBottom: "1px solid var(--border)",
      verticalAlign: "middle",
      color: "var(--text)",
    },

    badgeSent: {
      display: "inline-block",
      padding: "2px 8px",
      borderRadius: 20,
      fontSize: 11,
      fontWeight: 600,
      background: "rgba(52,211,153,0.15)",
      color: "var(--success)",
    },
    badgeUnsent: {
      display: "inline-block",
      padding: "2px 8px",
      borderRadius: 20,
      fontSize: 11,
      fontWeight: 600,
      background: "rgba(248,113,113,0.12)",
      color: "var(--danger)",
    },

    // 모달
    overlay: {
      position: "fixed",
      inset: 0,
      zIndex: 1000,
      background: "rgba(0,0,0,0.6)",
      display: "flex",
      alignItems: "flex-start",
      justifyContent: "center",
      padding: "32px 16px",
      overflowY: "auto",
    },
    modal: {
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 16,
      width: "min(900px, 96vw)",
      padding: 28,
      position: "relative",
    },
    modalHeader: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      marginBottom: 20,
      gap: 12,
    },
    modalTitle: { fontSize: 18, fontWeight: 700 },

    detailGrid: {
      display: "grid",
      gridTemplateColumns: "1fr 1fr",
      gap: "8px 24px",
      marginBottom: 20,
      fontSize: 13,
    },
    detailItem: {
      display: "flex",
      gap: 6,
      alignItems: "flex-start",
      lineHeight: 1.5,
    },
    detailLabel: { color: "var(--muted)", flexShrink: 0, minWidth: 80 },
    detailValue: { color: "var(--text)", wordBreak: "break-word" },

    section: {
      marginBottom: 20,
      borderTop: "1px solid var(--border)",
      paddingTop: 16,
    },
    sectionTitle: {
      fontSize: 13,
      fontWeight: 700,
      color: "var(--accent2)",
      marginBottom: 10,
    },

    jsonPre: {
      background: "var(--surface2)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: "12px 14px",
      fontSize: 11,
      color: "var(--muted)",
      overflowX: "auto",
      maxHeight: 260,
      overflowY: "auto",
      lineHeight: 1.6,
    },

    previewControls: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      marginBottom: 10,
      gap: 8,
      flexWrap: "wrap",
    },
    btnGroup: { display: "flex", gap: 8, flexWrap: "wrap" },

    textarea: {
      width: "100%",
      minHeight: 420,
      background: "var(--surface2)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      color: "var(--text)",
      padding: "12px 14px",
      fontSize: 12,
      fontFamily: "'DM Mono', monospace",
      lineHeight: 1.6,
      resize: "vertical",
    },
    iframe: {
      width: "100%",
      height: 480,
      border: "1px solid var(--border)",
      borderRadius: 8,
      background: "#fff",
    },

    saveMsg: {
      fontSize: 12,
      color: "var(--success)",
      marginTop: 6,
    },
    saveMsgError: {
      fontSize: 12,
      color: "var(--danger)",
      marginTop: 6,
    },

    dangerBtn: {
      marginTop: 16,
      padding: "8px 16px",
      background: "rgba(248,113,113,0.1)",
      border: "1px solid var(--danger)",
      borderRadius: 8,
      color: "var(--danger)",
      cursor: "pointer",
      fontSize: 13,
    },
  };

  return (
    <div className="main-inner">
      <div className="page-title">자동작성 문서 관리</div>
      <div className="page-desc">
        AI가 자동 작성한 결재서류의 작성자, 결재라인, 발송 상태와 문서 내용을 관리합니다.
      </div>

      {/* ── 요약 카드 ─────────────────────────────────────────────────────── */}
      <div style={S.statGrid}>
        <div style={S.statCard}>
          <div style={S.statValue}>{total}</div>
          <div style={S.statLabel}>전체 문서</div>
        </div>
        <div style={S.statCard}>
          <div style={{ ...S.statValue, color: "var(--danger)" }}>{unsent}</div>
          <div style={S.statLabel}>미발송</div>
        </div>
        <div style={S.statCard}>
          <div style={{ ...S.statValue, color: "var(--success)" }}>{sent}</div>
          <div style={S.statLabel}>발송 완료</div>
        </div>
      </div>

      {/* ── 필터 ──────────────────────────────────────────────────────────── */}
      <div style={S.filterRow}>
        <input
          style={S.searchInput}
          type="text"
          placeholder="작성 사원, 부서, 템플릿명, 결재자, 문서 제목 검색..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
        />
        <select
          style={S.select}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="all">전체 상태</option>
          <option value="unsent">미발송</option>
          <option value="sent">발송 완료</option>
        </select>
        <button className="btn btn-secondary" style={{ width: "auto" }} onClick={fetchDocs}>
          새로고침
        </button>
      </div>

      {/* ── 문서 목록 테이블 ───────────────────────────────────────────────── */}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        {loading ? (
          <div style={{ padding: 32, textAlign: "center", color: "var(--muted)" }}>
            로딩 중...
          </div>
        ) : listError ? (
          <div style={{ padding: 24, color: "var(--danger)" }}>{listError}</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: "var(--muted)" }}>
            {docs.length === 0 ? "저장된 문서가 없습니다." : "검색 결과가 없습니다."}
          </div>
        ) : (
          <table style={S.table}>
            <thead>
              <tr>
                {["ID", "문서 제목", "작성 사원", "부서", "사용 양식", "결재라인", "1차 수신자", "발송", "작성일", ""].map(
                  (h) => (
                    <th key={h} style={S.th}>{h}</th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {filtered.map((doc) => (
                <tr
                  key={doc.id}
                  style={{ cursor: "default" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface2)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "")}
                >
                  <td style={{ ...S.td, color: "var(--muted)", width: 40 }}>{doc.id}</td>
                  <td style={{ ...S.td, maxWidth: 160 }}>
                    <div
                      style={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        maxWidth: 155,
                      }}
                      title={doc.document_title}
                    >
                      {doc.document_title || "-"}
                    </div>
                  </td>
                  <td style={S.td}>{doc.requester_name || "-"}</td>
                  <td style={S.td}>{doc.requester_department || "-"}</td>
                  <td style={S.td}>{doc.template_name || "-"}</td>
                  <td style={{ ...S.td, maxWidth: 220 }}>
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--muted)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        maxWidth: 215,
                      }}
                      title={doc.approval_line_text}
                    >
                      {doc.approval_line_text || "-"}
                    </div>
                  </td>
                  <td style={S.td}>
                    {doc.recipient_name
                      ? `${doc.recipient_name}${doc.recipient_title ? ` (${doc.recipient_title})` : ""}`
                      : "-"}
                  </td>
                  <td style={S.td}>
                    <span style={doc.is_sent ? S.badgeSent : S.badgeUnsent}>
                      {doc.is_sent ? "발송 완료" : "미발송"}
                    </span>
                  </td>
                  <td style={{ ...S.td, whiteSpace: "nowrap", fontSize: 12, color: "var(--muted)" }}>
                    {formatDate(doc.created_at)}
                  </td>
                  <td style={{ ...S.td, width: 80 }}>
                    <button
                      className="btn btn-secondary"
                      style={{ width: "auto", padding: "5px 12px", fontSize: 12 }}
                      onClick={() => openDetail(doc.id)}
                    >
                      상세보기
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── 상세보기 모달 ─────────────────────────────────────────────────── */}
      {modalOpen && (
        <div style={S.overlay} onClick={closeModal}>
          <div style={S.modal} onClick={(e) => e.stopPropagation()}>
            {detailLoading ? (
              <div style={{ padding: 32, textAlign: "center", color: "var(--muted)" }}>
                불러오는 중...
              </div>
            ) : selectedDoc ? (
              <>
                {/* 모달 헤더 */}
                <div style={S.modalHeader}>
                  <div style={S.modalTitle}>{selectedDoc.document_title || "문서 상세"}</div>
                  <button
                    className="btn btn-secondary"
                    style={{ width: "auto", padding: "5px 14px" }}
                    onClick={closeModal}
                  >
                    닫기
                  </button>
                </div>

                {/* 기본 정보 그리드 */}
                <div style={S.detailGrid}>
                  <DetailItem label="작성 사원" value={selectedDoc.requester_name || "-"} />
                  <DetailItem label="작성 부서" value={selectedDoc.requester_department || "-"} />
                  <DetailItem label="사용 양식" value={selectedDoc.template_name || "-"} />
                  <DetailItem label="파일명" value={selectedDoc.file_name || "-"} />
                  <DetailItem
                    label="수신 결재자"
                    value={
                      selectedDoc.recipient_name
                        ? `${selectedDoc.recipient_name} (${selectedDoc.recipient_title || "직함 없음"})`
                        : "-"
                    }
                  />
                  <DetailItem label="이메일" value={selectedDoc.recipient_email || "-"} />
                  <DetailItem
                    label="발송 상태"
                    value={
                      <span style={selectedDoc.is_sent ? S.badgeSent : S.badgeUnsent}>
                        {selectedDoc.is_sent ? "발송 완료" : "미발송"}
                      </span>
                    }
                  />
                  <DetailItem label="증빙 파일" value={selectedDoc.receipt_file_name || "-"} />
                  <DetailItem label="작성일" value={formatDate(selectedDoc.created_at)} />
                  <DetailItem label="수정일" value={formatDate(selectedDoc.updated_at)} />
                  <div style={{ ...S.detailItem, gridColumn: "1 / -1" }}>
                    <span style={S.detailLabel}>자연어 입력</span>
                    <span style={{ ...S.detailValue, whiteSpace: "pre-wrap" }}>
                      {selectedDoc.description || "-"}
                    </span>
                  </div>
                  <div style={{ ...S.detailItem, gridColumn: "1 / -1" }}>
                    <span style={S.detailLabel}>결재라인</span>
                    <span style={S.detailValue}>
                      {selectedDoc.approval_line_text || "-"}
                    </span>
                  </div>
                </div>

                {/* 추출 JSON */}
                <div style={S.section}>
                  <div
                    style={{ ...S.sectionTitle, cursor: "pointer", userSelect: "none" }}
                    onClick={() => setJsonOpen((v) => !v)}
                  >
                    추출된 JSON 데이터 {jsonOpen ? "▲" : "▼"}
                  </div>
                  {jsonOpen && (
                    <pre style={S.jsonPre}>
                      {JSON.stringify(selectedDoc.extracted_json, null, 2)}
                    </pre>
                  )}
                </div>

                {/* HTML 미리보기 / 편집 */}
                <div style={S.section}>
                  <div style={S.previewControls}>
                    <div style={S.sectionTitle}>HTML 문서 미리보기</div>
                    <div style={S.btnGroup}>
                      <button
                        className="btn btn-secondary"
                        style={{ width: "auto", padding: "5px 12px", fontSize: 12 }}
                        onClick={() => {
                          if (!editMode) {
                            setEditedHtml(stripScripts(selectedDoc.html_content));
                          }
                          setEditMode((v) => !v);
                          setSaveMsg("");
                        }}
                      >
                        {editMode ? "미리보기 모드" : "편집 모드"}
                      </button>
                      {editMode && (
                        <button
                          className="btn btn-primary"
                          style={{ width: "auto", padding: "5px 12px", fontSize: 12 }}
                          onClick={handleSave}
                          disabled={saving}
                        >
                          {saving ? "저장 중..." : "수정 내용 저장"}
                        </button>
                      )}
                      <button
                        className="btn btn-secondary"
                        style={{ width: "auto", padding: "5px 12px", fontSize: 12 }}
                        onClick={handleDownload}
                      >
                        HTML 다운로드
                      </button>
                    </div>
                  </div>

                  {saveMsg && (
                    <div
                      style={
                        saveMsg.startsWith("저장 실패") ? S.saveMsgError : S.saveMsg
                      }
                    >
                      {saveMsg}
                    </div>
                  )}

                  {editMode ? (
                    <>
                      <div
                        style={{
                          fontSize: 11,
                          color: "var(--muted)",
                          marginBottom: 6,
                        }}
                      >
                        HTML 소스를 직접 편집하고 "수정 내용 저장"을 누르세요.
                      </div>
                      <textarea
                        ref={textareaRef}
                        style={S.textarea}
                        value={editedHtml}
                        onChange={(e) => setEditedHtml(e.target.value)}
                        spellCheck={false}
                      />
                    </>
                  ) : (
                    <iframe
                      title="doc-preview"
                      srcDoc={stripScripts(selectedDoc.html_content)}
                      sandbox="allow-same-origin"
                      style={S.iframe}
                    />
                  )}
                </div>

                {/* 삭제 버튼 */}
                <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }}>
                  <button
                    style={S.dangerBtn}
                    onClick={() => handleDelete(selectedDoc.id)}
                  >
                    문서 삭제 (비활성화)
                  </button>
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 상세 항목 컴포넌트 ────────────────────────────────────────────────────────
function DetailItem({ label, value }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 6,
        alignItems: "flex-start",
        fontSize: 13,
        lineHeight: 1.5,
      }}
    >
      <span
        style={{ color: "var(--muted)", flexShrink: 0, minWidth: 80, fontWeight: 500 }}
      >
        {label}
      </span>
      <span style={{ color: "var(--text)", wordBreak: "break-word" }}>{value}</span>
    </div>
  );
}
