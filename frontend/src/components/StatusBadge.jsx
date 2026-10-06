const LABELS = {
  APPROVED: "Approved",
  NEEDS_REVIEW: "Needs review",
  REJECTED: "Rejected",
  MANUALLY_APPROVED: "Approved by reviewer",
  MANUALLY_REJECTED: "Rejected by reviewer",
  PO_RECORDED: "PO recorded",
  EXTRACTED: "Extracted",
};

export const STATUS_OPTIONS = Object.keys(LABELS);

export default function StatusBadge({ status }) {
  return (
    <span className={`badge badge-${(status || "").toLowerCase()}`}>
      {LABELS[status] || status}
    </span>
  );
}
