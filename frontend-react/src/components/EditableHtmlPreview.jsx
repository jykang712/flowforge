import { useEffect, useRef } from "react";

function stripScripts(html) {
  return (html || "").replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, "");
}

/**
 * contentEditable 기반 HTML 편집 컴포넌트
 *
 * - html prop이 바뀌면 innerHTML을 업데이트한다.
 *   단, onChange로 전달된 값이 다시 prop으로 돌아오는 경우에는
 *   innerHTML을 덮어쓰지 않아 커서 튐을 방지한다.
 * - editable=true 일 때 사용자가 직접 수정 가능하다.
 * - onChange로 현재 innerHTML을 부모에 전달한다.
 */
export default function EditableHtmlPreview({ html, editable, onChange }) {
  const ref = useRef(null);
  const lastSentRef = useRef(null); // onChange로 내보낸 마지막 값

  useEffect(() => {
    if (!ref.current) return;
    // onChange로 내보낸 값이 prop으로 되돌아온 경우 → 덮어쓰지 않음 (커서 유지)
    if (html === lastSentRef.current) return;
    lastSentRef.current = html;
    ref.current.innerHTML = stripScripts(html || "");
  }, [html]);

  const handleInput = () => {
    if (!onChange || !ref.current) return;
    const current = ref.current.innerHTML;
    lastSentRef.current = current; // 다음 useEffect에서 skip하도록 마킹
    onChange(current);
  };

  return (
    <div
      ref={ref}
      contentEditable={editable}
      suppressContentEditableWarning
      onInput={handleInput}
      style={{
        width: "100%",
        minHeight: 420,
        background: "#fff",
        color: "#111",
        padding: 16,
        borderRadius: 8,
        border: editable
          ? "2px solid var(--accent)"
          : "1px solid var(--border, #333)",
        outline: "none",
        overflowY: "auto",
        boxSizing: "border-box",
        fontFamily: "Malgun Gothic, sans-serif",
        fontSize: 13,
        lineHeight: 1.6,
      }}
    />
  );
}
