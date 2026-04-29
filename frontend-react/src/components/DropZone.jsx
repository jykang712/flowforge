// import { useRef, useState } from "react";

// export default function DropZone({ label, accept, file, setFile, icon }) {
//   const [drag, setDrag] = useState(false);
//   const ref = useRef();

//   const onDrop = (e) => {
//     e.preventDefault();
//     setDrag(false);
//     const f = e.dataTransfer.files[0];
//     if (f) setFile(f);
//   };

//   return (
//     <div
//       className={`drop-zone${drag ? " drag" : ""}`}
//       onDragOver={(e) => {
//         e.preventDefault();
//         setDrag(true);
//       }}
//       onDragLeave={() => setDrag(false)}
//       onDrop={onDrop}
//       onClick={() => ref.current.click()}
//     >
//       <div className="icon">{icon}</div>
//       <div>{label}</div>
//       {file && <div className="file-name">📎 {file.name}</div>}

//       <input
//         ref={ref}
//         type="file"
//         accept={accept}
//         style={{ display: "none" }}
//         onChange={(e) => setFile(e.target.files[0])}
//       />
//     </div>
//   );
// }

import { useRef, useState } from "react";

function getFileExtension(fileName = "") {
  const dotIndex = fileName.lastIndexOf(".");
  return dotIndex >= 0 ? fileName.slice(dotIndex).toLowerCase() : "";
}

function parseAcceptList(accept = "") {
  return String(accept)
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function matchesAccept(file, accept = "") {
  const acceptList = parseAcceptList(accept);

  if (acceptList.length === 0) return true;

  const fileType = String(file.type || "").toLowerCase();
  const fileExt = getFileExtension(file.name);

  return acceptList.some((accepted) => {
    if (accepted.startsWith(".")) {
      return fileExt === accepted;
    }

    if (accepted.endsWith("/*")) {
      return fileType.startsWith(accepted.replace("/*", "/"));
    }

    return fileType === accepted;
  });
}

function makeAcceptMessage(accept = "") {
  const extensions = parseAcceptList(accept)
    .filter((item) => item.startsWith("."))
    .map((item) => item.replace(".", "").toUpperCase());

  if (extensions.length === 0) {
    return "허용된 형식의 파일만 업로드할 수 있습니다.";
  }

  return `${extensions.join(", ")} 형식의 파일만 업로드할 수 있습니다.`;
}

export default function DropZone({
  label,
  accept,
  file,
  setFile,
  files,
  setFiles,
  icon,
  multiple = false,
  imageOnly = false,
}) {
  const [drag, setDrag] = useState(false);
  const ref = useRef();

  const selectedFiles = multiple ? files || [] : file ? [file] : [];

  const addFiles = (fileList) => {
    const newFiles = Array.from(fileList || []);

    if (newFiles.length === 0) return;

    let validFiles = newFiles;

    if (imageOnly) {
      validFiles = newFiles.filter((item) => item.type.startsWith("image/"));

      if (validFiles.length !== newFiles.length) {
        alert("영수증은 PNG, JPG, JPEG, WEBP 같은 이미지 파일만 업로드할 수 있습니다.");
      }

      if (validFiles.length === 0) return;
    } else if (accept) {
      validFiles = newFiles.filter((item) => matchesAccept(item, accept));

      if (validFiles.length !== newFiles.length) {
        alert(makeAcceptMessage(accept));
      }

      if (validFiles.length === 0) return;
    }

    if (multiple) {
      setFiles((prev = []) => [...prev, ...validFiles]);
    } else {
      setFile(validFiles[0]);
    }

    if (ref.current) {
      ref.current.value = "";
    }
  };

  const removeFile = (index) => {
    if (multiple) {
      setFiles((prev = []) => prev.filter((_, i) => i !== index));
    } else {
      setFile(null);
    }

    if (ref.current) {
      ref.current.value = "";
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    addFiles(e.dataTransfer.files);
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

      {selectedFiles.length > 0 && (
        <div className="file-list" onClick={(e) => e.stopPropagation()}>
          {selectedFiles.map((selectedFile, index) => (
            <div className="file-name" key={`${selectedFile.name}-${index}`}>
              <span>📎 {selectedFile.name}</span>

              <button
                type="button"
                className="file-remove-btn"
                aria-label={`${selectedFile.name} 삭제`}
                onClick={() => removeFile(index)}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <input
        ref={ref}
        type="file"
        accept={accept}
        multiple={multiple}
        style={{ display: "none" }}
        onChange={(e) => addFiles(e.target.files)}
      />
    </div>
  );
}