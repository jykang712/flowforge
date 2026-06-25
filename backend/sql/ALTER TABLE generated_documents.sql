ALTER TABLE generated_documents
  ADD COLUMN requester_name      VARCHAR(100)  NULL    AFTER recipient_title,
  ADD COLUMN requester_department VARCHAR(100) NULL    AFTER requester_name,
  ADD COLUMN approval_line_text  TEXT          NULL    AFTER requester_department,
  ADD COLUMN approval_line_json  LONGTEXT      NULL    AFTER approval_line_text,
  ADD COLUMN is_active           BOOLEAN       NOT NULL DEFAULT TRUE AFTER approval_line_json;
