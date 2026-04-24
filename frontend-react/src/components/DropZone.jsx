import { useRef, useState } from "react";

export default function DropZone({ label, accept, file, setFile, icon }) {
  const [drag, setDrag] = useState(false);
  const ref = useRef();

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  };

  return (
    <div
      className={`drop-zone${drag ? " drag" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={onDrop}
      onClick={() => ref.current.click()}
    >
      <div className="icon">{icon}</div>
      <div>{label}</div>
      {file && <div className="file-name">📎 {file.name}</div>}

      <input
        ref={ref}
        type="file"
        accept={accept}
        style={{ display: "none" }}
        onChange={(e) => setFile(e.target.files[0])}
      />
    </div>
  );
}