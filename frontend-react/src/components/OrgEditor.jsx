export default function OrgEditor({ org, setOrg }) {
    const addRow = () =>
      setOrg([...org, { name: "", department: "", title: "", email: "" }]);
  
    const del = (i) => {
      setOrg(org.filter((_, idx) => idx !== i));
    };
  
    const update = (i, field, val) => {
      const next = [...org];
      next[i] = { ...next[i], [field]: val };
      setOrg(next);
    };
  
    return (
      <div>
        <table className="org-table">
          <thead>
            <tr>
              <th>이름</th>
              <th>부서</th>
              <th>직급</th>
              <th>이메일</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {org.map((row, i) => (
              <tr key={i}>
                <td>
                  <input
                    type="text"
                    value={row.name}
                    onChange={(e) => update(i, "name", e.target.value)}
                    placeholder="홍길동"
                  />
                </td>
                <td>
                  <input
                    type="text"
                    value={row.department || ""}
                    onChange={(e) => update(i, "department", e.target.value)}
                    placeholder="개발팀"
                  />
                </td>
                <td>
                  <input
                    type="text"
                    value={row.title || ""}
                    onChange={(e) => update(i, "title", e.target.value)}
                    placeholder="팀장"
                  />
                </td>
                <td>
                  <input
                    type="text"
                    value={row.email}
                    onChange={(e) => update(i, "email", e.target.value)}
                    placeholder="hong@company.com"
                  />
                </td>
                <td>
                  <button className="del-btn" onClick={() => del(i)}>
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
  
        <button className="add-row-btn" onClick={addRow}>
          + 행 추가
        </button>
      </div>
    );
  }