export default function RuleEditor({
  rules = [],
  setRules,
  templates = [],
  orgMembers = [],
}) {
  const createEmptyApprover = () => ({
    approverMemberId: "",
    approvalType: "결재",
  });

  const createEmptyRule = () => ({
    ruleName: "",
    ruleText: "",
    templateId: "",
    approvers: [createEmptyApprover()],
  });

  const addRule = () => {
    setRules([...rules, createEmptyRule()]);
  };

  const deleteRule = (ruleIndex) => {
    const next = rules.filter((_, idx) => idx !== ruleIndex);
    setRules(next.length > 0 ? next : [createEmptyRule()]);
  };

  const updateRule = (ruleIndex, field, value) => {
    const next = [...rules];
    next[ruleIndex] = {
      ...next[ruleIndex],
      [field]: value,
    };
    setRules(next);
  };

  const addApprover = (ruleIndex) => {
    const next = [...rules];
    next[ruleIndex] = {
      ...next[ruleIndex],
      approvers: [...(next[ruleIndex].approvers || []), createEmptyApprover()],
    };
    setRules(next);
  };

  const deleteApprover = (ruleIndex, approverIndex) => {
    const next = [...rules];

    const filtered = (next[ruleIndex].approvers || []).filter(
      (_, idx) => idx !== approverIndex
    );

    next[ruleIndex] = {
      ...next[ruleIndex],
      approvers: filtered.length > 0 ? filtered : [createEmptyApprover()],
    };

    setRules(next);
  };

  const updateApprover = (ruleIndex, approverIndex, field, value) => {
    const next = [...rules];
    const currentApprovers = [...(next[ruleIndex].approvers || [])];

    currentApprovers[approverIndex] = {
      ...currentApprovers[approverIndex],
      [field]: value,
    };

    next[ruleIndex] = {
      ...next[ruleIndex],
      approvers: currentApprovers,
    };

    setRules(next);
  };

  return (
    <div>
      {rules.map((rule, ruleIndex) => (
        <div key={ruleIndex} className="rule-block">
          <div className="rule-block-header">
            <div className="rule-block-title">규칙 {ruleIndex + 1}</div>
            <button
              type="button"
              className="del-btn"
              onClick={() => deleteRule(ruleIndex)}
            >
              ×
            </button>
          </div>

          <div className="form-row">
            <label>규칙명</label>
            <input
              type="text"
              value={rule.ruleName || ""}
              onChange={(e) => updateRule(ruleIndex, "ruleName", e.target.value)}
              placeholder="예: 지출결의서 규칙"
            />
          </div>

          <div className="form-row">
            <label>규칙 내용</label>
            <input
              type="text"
              value={rule.ruleText || ""}
              onChange={(e) => updateRule(ruleIndex, "ruleText", e.target.value)}
              placeholder="예: 50만원 이상 지출은 순차 결재"
            />
          </div>

          <div className="form-row">
            <label>적용 템플릿</label>
            <select
              value={rule.templateId || ""}
              onChange={(e) => updateRule(ruleIndex, "templateId", e.target.value)}
            >
              <option value="">템플릿 선택</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.template_name} ({template.file_name})
                </option>
              ))}
            </select>
          </div>

          <div className="form-row">
            <label>결재자 목록</label>

            {(rule.approvers || []).map((approver, approverIndex) => (
              <div key={approverIndex} className="approver-row">
                <div className="approver-order">{approverIndex + 1}차</div>

                <select
                  value={approver.approverMemberId || ""}
                  onChange={(e) =>
                    updateApprover(
                      ruleIndex,
                      approverIndex,
                      "approverMemberId",
                      e.target.value
                    )
                  }
                  style={{ flex: 1 }}
                >
                  <option value="">결재자 선택</option>
                  {orgMembers.map((member) => (
                    <option key={member.id} value={member.id}>
                      {member.name} / {member.title}
                      {member.department ? ` / ${member.department}` : ""}
                    </option>
                  ))}
                </select>

                <select
                  value={approver.approvalType || "결재"}
                  onChange={(e) =>
                    updateApprover(
                      ruleIndex,
                      approverIndex,
                      "approvalType",
                      e.target.value
                    )
                  }
                  style={{ width: 120 }}
                >
                  <option value="결재">결재</option>
                  <option value="합의">합의</option>
                  <option value="최종승인">최종승인</option>
                </select>

                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => deleteApprover(ruleIndex, approverIndex)}
                >
                  삭제
                </button>
              </div>
            ))}

            <button
              type="button"
              className="add-row-btn"
              onClick={() => addApprover(ruleIndex)}
            >
              + 결재자 추가
            </button>
          </div>
        </div>
      ))}

      <button type="button" className="add-row-btn" onClick={addRule}>
        + 규칙 추가
      </button>
    </div>
  );
}