import { useRef, useState } from "react";

export default function EducationDropzone({
  file = null,
  files = [],
  multiple = false,
  accept = ".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  icon = "📄",
  title = "DOCX 양식을 드래그하거나 클릭하여 업로드",
  disabled = false,
  onFileChange,
}) {
  const inputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);

  const selectedFiles = multiple ? files : file ? [file] : [];

  const openFileDialog = () => {
    if (disabled) return;
    inputRef.current?.click();
  };

  const handleFiles = (fileList) => {
    if (!fileList || fileList.length === 0) return;

    if (multiple) {
      onFileChange?.(Array.from(fileList));
    } else {
      onFileChange?.(fileList[0]);
    }
  };

  const handleInputChange = (e) => {
    handleFiles(e.target.files);
    e.target.value = "";
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    if (disabled) return;
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);

    if (disabled) return;
    handleFiles(e.dataTransfer.files);
  };

  return (
    <div>
      <div
        className={`education-dropzone${isDragging ? " dragging" : ""}${
          disabled ? " disabled" : ""
        }`}
        onClick={openFileDialog}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          onChange={handleInputChange}
          style={{ display: "none" }}
        />

        <div className="education-dropzone-icon">{icon}</div>
        <div className="education-dropzone-title">{title}</div>

        {selectedFiles.length > 0 && (
          <div className="education-dropzone-file-list">
            {selectedFiles.map((item, index) => (
              <div className="education-dropzone-file" key={`${item.name}_${index}`}>
                {item.name}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}