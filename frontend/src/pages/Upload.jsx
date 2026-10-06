import { useState } from "react";
import { Link } from "react-router-dom";
import { uploadDocument } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function Upload() {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [current, setCurrent] = useState("");
  const [results, setResults] = useState([]);

  async function handleUpload() {
    setBusy(true);
    setResults([]);
    // One file at a time: kinder to free-tier LLM rate limits than sending all at once.
    for (const file of files) {
      setCurrent(file.name);
      try {
        const data = await uploadDocument(file);
        setResults((prev) => [...prev, { name: file.name, ok: true, data }]);
      } catch (err) {
        setResults((prev) => [...prev, { name: file.name, ok: false, error: err.message }]);
      }
    }
    setCurrent("");
    setBusy(false);
    setFiles([]);
  }

  return (
    <div>
      <h1>Upload documents</h1>
      <p className="muted">
        Upload purchase orders first, then invoices and bills of lading. Each file is read by the AI,
        then checked against its PO using the rules in <code>rules.yaml</code>.
      </p>

      <div className="card">
        <input
          type="file"
          accept="application/pdf"
          multiple
          disabled={busy}
          onChange={(e) => setFiles(Array.from(e.target.files))}
        />
        <button className="btn primary" disabled={busy || files.length === 0} onClick={handleUpload}>
          {busy ? "Working..." : `Upload ${files.length || ""} file${files.length === 1 ? "" : "s"}`}
        </button>
        {busy && <p className="muted">Reading and validating {current} (this can take a few seconds)...</p>}
      </div>

      {results.map((r, i) => (
        <div key={i} className="card">
          <div className="row">
            <strong>{r.name}</strong>
            {r.ok ? <StatusBadge status={r.data.validation.status} /> : <span className="badge badge-rejected">Failed</span>}
          </div>
          {r.ok ? (
            <>
              <p className="muted">
                {r.data.extracted.doc_type.replace(/_/g, " ")} {r.data.extracted.doc_number}
              </p>
              {r.data.validation.findings.map((f, j) => (
                <p key={j} className={`finding ${f.severity}`}>{f.message}</p>
              ))}
              <Link to={`/documents/${r.data.id}`}>Open details →</Link>
            </>
          ) : (
            <p className="error">{r.error}</p>
          )}
        </div>
      ))}
    </div>
  );
}
