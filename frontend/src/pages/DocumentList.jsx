import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listDocuments } from "../api";
import StatusBadge, { STATUS_OPTIONS } from "../components/StatusBadge";

export default function DocumentList() {
  const [status, setStatus] = useState("");
  const [docs, setDocs] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    listDocuments(status)
      .then((data) => {
        if (!cancelled) {
          setDocs(data);
          setError("");
        }
      })
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [status]);

  return (
    <div>
      <h1>Documents</h1>
      <div className="card row">
        <label>
          Filter by status{" "}
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <button className="btn" onClick={() => setStatus("NEEDS_REVIEW")}>Show review queue</button>
      </div>

      {error && <p className="error">{error}</p>}
      {!docs && !error && <p className="muted">Loading...</p>}
      {docs && docs.length === 0 && <p className="muted">No documents found.</p>}

      {docs && docs.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>ID</th><th>Number</th><th>Type</th><th>File</th><th>Status</th><th>Uploaded</th></tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>{d.id}</td>
                  <td><Link to={`/documents/${d.id}`}>{d.doc_number || "(no number)"}</Link></td>
                  <td>{(d.doc_type || "").replace(/_/g, " ")}</td>
                  <td>{d.filename}</td>
                  <td><StatusBadge status={d.status} /></td>
                  <td>{new Date(d.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
