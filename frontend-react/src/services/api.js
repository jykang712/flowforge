const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

function assertTemplateFileType(file) {
  const name = String(file?.name || "").toLowerCase();

  if (!name.endsWith(".docx")) {
    throw new Error("DOCX 파일만 업로드할 수 있습니다. HWPX는 DOCX로 변환 후 업로드해주세요.");
  }
}

// -----------------------------
// 템플릿 저장
// -----------------------------
export async function createTemplate({
  templateFile,
  templateName,
  description = "",
}) {
  const fd = new FormData();

  if (!templateFile) {
    throw new Error("템플릿 파일이 필요합니다.");
  }

  if (!templateName?.trim()) {
    throw new Error("템플릿 이름을 입력해주세요.");
  }

  fd.append("template", templateFile);
  fd.append("template_name", templateName.trim());
  fd.append("description", description);

  const res = await fetch(`${API}/api/templates`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(errorText || "템플릿 저장 실패");
  }

  return res.json();
}

// -----------------------------
// 템플릿 목록 조회
// -----------------------------
export async function getTemplates() {
  const res = await fetch(`${API}/api/templates`);

  if (!res.ok) {
    throw new Error("템플릿 목록 조회 실패");
  }

  return res.json();
}

export async function getTemplateDetail(templateId) {
  const res = await fetch(`${API}/api/templates/${templateId}`);

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "템플릿 상세 조회 실패");
  }

  return res.json();
}

// -----------------------------
// 템플릿 자동 입력 항목 미리보기
// 업로드한 DOCX를 서버에서 HTML로 변환한 뒤 AI가 fields 후보 반환
// -----------------------------
export async function previewTemplateFields({
  templateFile,
  templateName,
  description = "",
}) {
  const fd = new FormData();

  if (!templateFile) {
    throw new Error("문서 양식 파일이 필요합니다.");
  }

  if (!templateName?.trim()) {
    throw new Error("양식 이름을 입력해주세요.");
  }

  assertTemplateFileType(templateFile);
  fd.append("template", templateFile);
  fd.append("template_name", templateName.trim());
  fd.append("description", description);

  const res = await fetch(`${API}/api/templates/preview-fields`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "자동 입력 항목 분석 실패");
  }

  return res.json();
}

function normalizeTemplateFieldForSubmit(field = {}) {
  const key = String(field.key || "").trim();

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

  return {
    label: String(field.label || "").trim(),
    key,
    type: field.type || "string",
    required: Boolean(field.required),
    description: String(field.description || "").trim(),
    position_hint: String(field.position_hint || "").trim(),

    // 기존 호환
    cell_id: cellIds[0] || "",
    locator: locators[0] || {},

    // 여러 위치 지원
    cell_ids: cellIds,
    locators,

    source: String(field.source || "").trim(),
    placeholder: key ? `{{${key}}}` : "",
  };
}

// -----------------------------
// 사용자가 확정한 자동 입력 항목으로 템플릿 저장
// -----------------------------
export async function saveTemplateWithFields({
  templateFile,
  templateName,
  description = "",
  fields = [],
  // htmlTemplate = "",
}) {
  const fd = new FormData();

  if (!templateFile) {
    throw new Error("문서 양식 파일이 필요합니다.");
  }

  if (!templateName?.trim()) {
    throw new Error("양식 이름을 입력해주세요.");
  }

  if (!Array.isArray(fields) || fields.length === 0) {
    throw new Error("자동 입력 항목을 1개 이상 설정해주세요.");
  }

  const normalizedFields = fields.map(normalizeTemplateFieldForSubmit);

  fd.append("template", templateFile);
  fd.append("template_name", templateName.trim());
  fd.append("description", description);
  fd.append("fields", JSON.stringify(normalizedFields));
  // fd.append("html_template", htmlTemplate || "");

  const res = await fetch(`${API}/api/templates/save-with-fields`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "템플릿 저장 실패");
  }

  return res.json();
}

// -----------------------------
// 조직도 1건 저장
// -----------------------------
export async function createOrgMember({
  name,
  department = "",
  title,
  email,
}) {
  const res = await fetch(`${API}/api/org-members`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name,
      department,
      title,
      email,
    }),
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "조직도 저장 실패");
  }

  return res.json();
}

// -----------------------------
// 조직도 목록 조회
// -----------------------------
export async function getOrgMembers() {
  const res = await fetch(`${API}/api/org-members`);

  if (!res.ok) {
    throw new Error("조직도 목록 조회 실패");
  }

  return res.json();
}

// -----------------------------
// 조직도 이미지 업로드 후 미리보기
// -----------------------------
export async function previewOrgMembersByImage({ imageFile }) {
  if (!imageFile) {
    throw new Error("조직도 이미지 파일이 필요합니다.");
  }

  const fd = new FormData();
  fd.append("org_image", imageFile);

  const res = await fetch(`${API}/api/org-members/preview-image`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "조직도 이미지 분석 실패");
  }

  return res.json();
}

// -----------------------------
// 미리보기 조직도 저장
// -----------------------------
export async function savePreviewOrgMembers(rows = []) {
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error("저장할 미리보기 데이터가 없습니다.");
  }

  const res = await fetch(`${API}/api/org-members/save-preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ rows }),
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "조직도 일괄 저장 실패");
  }

  return res.json();
}

// -----------------------------
// 결재 방침 1건 저장
// payload 예시:
// {
//   ruleName: "지출결의서 규칙",
//   ruleText: "50만원 이상 지출은 순차 결재",
//   templateId: 1,
//   approvers: [
//     { approverMemberId: 3, approvalType: "결재" },
//     { approverMemberId: 5, approvalType: "최종승인" }
//   ]
// }
// -----------------------------
export async function createApprovalRule({
  ruleName,
  ruleText,
  templateId,
  approvers = [],
}) {
  if (!ruleName?.trim()) {
    throw new Error("규칙명을 입력해주세요.");
  }

  if (!ruleText?.trim()) {
    throw new Error("규칙 내용을 입력해주세요.");
  }

  if (!templateId) {
    throw new Error("적용 템플릿을 선택해주세요.");
  }

  if (!Array.isArray(approvers) || approvers.length === 0) {
    throw new Error("결재자를 1명 이상 선택해주세요.");
  }

  const normalizedApprovers = approvers.map((approver, index) => {
    if (!approver.approverMemberId) {
      throw new Error(`${index + 1}차 결재자를 선택해주세요.`);
    }

    return {
      approver_member_id: Number(approver.approverMemberId),
      approval_order: index + 1,
      approval_type: approver.approvalType || "결재",
    };
  });

  const res = await fetch(`${API}/api/approval-rules`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      rule_name: ruleName.trim(),
      rule_text: ruleText.trim(),
      template_id: Number(templateId),
      approvers: normalizedApprovers,
    }),
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "결재 방침 저장 실패");
  }

  return res.json();
}

// -----------------------------
// 결재 방침 목록 조회
// -----------------------------
export async function getApprovalRules() {
  const res = await fetch(`${API}/api/approval-rules`);

  if (!res.ok) {
    throw new Error("결재 방침 목록 조회 실패");
  }

  return res.json();
}

// --------------------------------
// 결재 방침 미리보기
// --------------------------------
export async function previewApprovalRulesByGuide({ guideFile }) {
  if (!guideFile) {
    throw new Error("지침서 PDF 파일이 필요합니다.");
  }

  const fd = new FormData();
  fd.append("guide_file", guideFile);

  const res = await fetch(`${API}/api/approval-rules/preview-guide`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "지침서 분석 실패");
  }

  return res.json();
}

// -----------------------------------------
// 결재 방침 미리보기 후 저장
// -----------------------------------------
export async function savePreviewApprovalRules(rules = [], sourceName = "") {
  if (!Array.isArray(rules) || rules.length === 0) {
    throw new Error("저장할 결재 규칙이 없습니다.");
  }

  const normalizedRules = rules
    .filter((rule) => {
      if (!rule.ruleName || !rule.ruleText || !rule.templateId) {
        return false;
      }

      if (!Array.isArray(rule.approvers) || rule.approvers.length === 0) {
        return false;
      }

      return rule.approvers.every((a) => a.approverMemberId);
    })
    .map((rule) => ({
      rule_name: rule.ruleName.trim(),
      rule_text: rule.ruleText.trim(),
      template_id: Number(rule.templateId),
      source_excerpt: (rule.sourceExcerpt || "").trim(),
      approvers: rule.approvers.map((a, index) => ({
        approver_member_id: Number(a.approverMemberId),
        approval_order: Number(a.approvalOrder || index + 1),
        approval_type: a.approvalType || "결재",
      })),
    }));

  const res = await fetch(`${API}/api/approval-rules/save-preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      source_name: sourceName,
      rules: normalizedRules,
    }),
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "결재 처리 방침 일괄 저장 실패");
  }

  return res.json();
}

// -----------------------------
// 여러 결재 방침 일괄 저장
// rules 형식:
// [
//   {
//     ruleName: "...",
//     ruleText: "...",
//     templateId: "1",
//     approvers: [
//       { approverMemberId: "3", approvalType: "결재" },
//       { approverMemberId: "5", approvalType: "최종승인" }
//     ]
//   }
// ]
// -----------------------------
export async function saveApprovalRules(rules = []) {
  const validRules = rules.filter((rule) => {
    if (!rule.ruleName || !rule.ruleText || !rule.templateId) {
      return false;
    }

    if (!Array.isArray(rule.approvers) || rule.approvers.length === 0) {
      return false;
    }

    return rule.approvers.every((a) => a.approverMemberId);
  });

  if (validRules.length === 0) {
    throw new Error("저장할 결재 처리 방침을 입력해주세요.");
  }

  const results = [];

  for (const rule of validRules) {
    const saved = await createApprovalRule({
      ruleName: rule.ruleName,
      ruleText: rule.ruleText,
      templateId: rule.templateId,
      approvers: rule.approvers,
    });

    results.push(saved);
  }

  return {
    status: "ok",
    savedRuleCount: results.length,
    results,
  };
}

// -----------------------------
// 문서 자동 생성
// -----------------------------
// export async function processExpense({ templateId, desc, receiptFile }) {
//   const fd = new FormData();
//   fd.append("template_id", templateId);
//   fd.append("description", desc);

//   if (receiptFile) {
//     fd.append("receipt", receiptFile);
//   }

//   const res = await fetch(`${API}/api/process`, {
//     method: "POST",
//     body: fd,
//   });

//   if (!res.ok) {
//     const e = await res.json().catch(() => null);
//     throw new Error(e?.detail || "처리 실패");
//   }

//   return res.json();
// }

export async function processExpense({ templateId, desc, receiptFiles = [] }) {
  const fd = new FormData();
  fd.append("template_id", templateId);
  fd.append("description", desc);

  receiptFiles.forEach((file) => {
    fd.append("receipts", file);
  });

  const res = await fetch(`${API}/api/process`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "처리 실패");
  }

  return res.json();
}

// -----------------------------
// 이메일 발송
// filledHtml: 편집된 최신 HTML (없으면 result.filled_html 사용)
// -----------------------------
export async function sendExpenseEmail(result, filledHtml) {
  const res = await fetch(`${API}/api/send-email`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      document_id: result.document_id,
      to_email: result.recipient_email,
      to_name: result.recipient_name,
      requester:
        result.expense_data?.requester ||
        result.requester_name ||
        "작성자",
      template_name: result.template_name,
      filled_html: filledHtml !== undefined ? filledHtml : result.filled_html,
      expense_data: result.expense_data,
    }),
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "발송 실패");
  }

  return res.json();
}




// ─────────────────────────────────────────────────────────────────────────────
// 자동작성 문서 관리 API
// ─────────────────────────────────────────────────────────────────────────────

// 목록 조회
export async function getGeneratedDocuments() {
  const res = await fetch(`${API}/api/generated-documents`);

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "자동작성 문서 목록 조회 실패");
  }

  return res.json();
}

// 상세 조회
export async function getGeneratedDocumentDetail(documentId) {
  const res = await fetch(`${API}/api/generated-documents/${documentId}`);

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "자동작성 문서 상세 조회 실패");
  }

  return res.json();
}

// 수정 (HTML 편집 저장 또는 상태 변경)
export async function updateGeneratedDocument({
  documentId,
  htmlContent,
  extractedJson,
  documentTitle,
  isSent,
}) {
  const body = {};

  if (htmlContent !== undefined) body.html_content = htmlContent;
  if (documentTitle !== undefined) body.document_title = documentTitle;
  if (typeof isSent === "boolean") body.is_sent = isSent;
  if (extractedJson !== undefined) body.extracted_json = extractedJson;

  const res = await fetch(`${API}/api/generated-documents/${documentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "문서 수정 실패");
  }

  return res.json();
}

// 삭제 (비활성화)
export async function deleteGeneratedDocument(documentId) {
  const res = await fetch(`${API}/api/generated-documents/${documentId}`, {
    method: "DELETE",
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "문서 삭제 실패");
  }

  return res.json();
}


// 교육용 테스트 코드---------------------------------------------------------------------------------------------------------------------------



// -----------------------------
// 교육용 1회성 문서 자동 작성
// DB 저장 없이, 1차 분석 결과 + 자연어 + 이미지로 바로 작성
// -----------------------------
export async function generateEducationDocumentOnce({
  templateName,
  htmlTemplate,
  fields = [],
  description,
  receiptFiles = [],
}) {
  if (!templateName?.trim()) {
    throw new Error("양식 이름이 필요합니다.");
  }

  if (!htmlTemplate?.trim()) {
    throw new Error("먼저 AI 양식 분석을 진행해주세요.");
  }

  if (!Array.isArray(fields) || fields.length === 0) {
    throw new Error("자동 입력 항목이 필요합니다.");
  }

  if (!description?.trim()) {
    throw new Error("문서 작성에 필요한 자연어 설명을 입력해주세요.");
  }

  const fd = new FormData();

  const normalizedFields = fields.map(normalizeTemplateFieldForSubmit);

  fd.append("template_name", templateName.trim());
  fd.append("html_template", htmlTemplate);
  fd.append("fields", JSON.stringify(normalizedFields));
  fd.append("description", description.trim());

  receiptFiles.forEach((file) => {
    fd.append("receipts", file);
  });

  const res = await fetch(`${API}/api/education/generate-once`, {
    method: "POST",
    body: fd,
  });

  if (!res.ok) {
    const e = await res.json().catch(() => null);
    throw new Error(e?.detail || "교육용 문서 자동 작성 실패");
  }

  return res.json();
}