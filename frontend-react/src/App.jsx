import { useState } from "react";
import SetupPage from "./pages/SetupPage";
import OrgPage from "./pages/OrgPage";
import RulePage from "./pages/RulePage";
import ProcessPage from "./pages/ProcessPage";
import "./styles/style.css";

export default function App() {
  const [page, setPage] = useState("setup");

  return (
    <div className="app">
      <div className="sidebar">
        <div className="sidebar-logo">
          FlowForge <span>결재서류 작성 자동화</span>
        </div>

        <div
          className={`nav-item${page === "setup" ? " active" : ""}`}
          onClick={() => setPage("setup")}
        >
          <span className="nav-dot" />
          결재 서류 관리
        </div>

        <div
          className={`nav-item${page === "org" ? " active" : ""}`}
          onClick={() => setPage("org")}
        >
          <span className="nav-dot" />
          조직도 관리
        </div>

        <div
          className={`nav-item${page === "rule" ? " active" : ""}`}
          onClick={() => setPage("rule")}
        >
          <span className="nav-dot" />
          결재 처리 방침 관리
        </div>

        <div
          className={`nav-item${page === "process" ? " active" : ""}`}
          onClick={() => setPage("process")}
        >
          <span className="nav-dot" />
          결재서류 작성
        </div>
      </div>

      <div className="main">
        {page === "setup" && <SetupPage />}
        {page === "org" && <OrgPage />}
        {page === "rule" && <RulePage />}
        {page === "process" && <ProcessPage />}
      </div>
    </div>
  );
}