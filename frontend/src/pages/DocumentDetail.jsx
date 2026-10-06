import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { decide, getAudit, getDocument, revalidate } from "../api";
import StatusBadge from "../components/StatusBadge";

const FIELD_LABELS = [
  ["doc_type", "Type"], ["doc_number", "Number"], ["date", "Date"], ["po_reference", "PO reference"],
  ["vendor", "Vendor / shipper"], ["buyer", "Buyer / consignee"], ["total", "Total"], ["currency", "Currency"],
  ["incoterm", "Incoterm"], ["port_of_loading", "Port of loading"], ["port_of_discharge", "Port of discharge"],
  ["vessel", "Vessel"], ["container_no", "Container"], ["gross_weight_kg", "Gross weight (kg)"],
];

export default function DocumentDetail() {
  const { id } = useParams();
  const [doc, setDoc] = useState(null);
  const [audit, setAudit] = useState([]);
  const [error, setError] = useState("");
  const [reviewer, setReviewer] = useState(localStorage.getItem("reviewer") || "");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, a] = await Promise.all([getDocument(id), getAudit(id)]);
      setDoc(d);
      setAudit(a);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function submitDecision(action) {
    localStorage.setItem("reviewer", reviewer);
    run(async () => {
      await decide(id, { action, reviewer, comment });
      setComment("");
    });
  }

  if (!doc) return <p className={error ? "error" : "muted"}>{error || "Loading..."}</p>;

  const ex = doc.extracted;
  const decided = doc.status.startsWith("MANUALLY_");
  const canDecide = doc.status === "NEEDS_REVIEW";
  const findings = doc.validation?.findings || [];

  return (
    <div>
      <p><Link to="/documents">← All documents</Link></p>
      <div className="row">
        <h1>{ex.doc_number || doc.filename}</h1>
        <StatusBadge status={doc.status} />
      </div>
      <p className="muted">{doc.filename} · uploaded {new Date(doc.created_at).toLocaleString()}</p>
      {error && <p className="error">{error}</p>}

      <div className="card">
        <h2>Validation findings</h2>
        {findings.length === 0 && <p className="muted">No problems found by the rules.</p>}
        {findings.map((f, i) => (
          <p key={i} className={`finding ${f.severity}`}>{f.message}</p>
        ))}
        <button className="btn" disabled={busy || decided} onClick={() => run(() => revalidate(id))}>
          Re-run validation
        </button>
        {decided && <span className="muted"> A reviewer has decided this document.</span>}
      </div>

      {canDecide && (
        <div className="card">
          <h2>Your decision</h2>
          <label>Your name
            <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="e.g. Priya" />
          </label>
          <label>Reason (required)
            <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)}
              placeholder="Why are you approving or rejecting this?" />
          </label>
          <div className="row">
            <button className="btn approve" disabled={busy || !reviewer.trim() || comment.trim().length < 3}
              onClick={() => submitDecision("approve")}>Approve</button>
            <button className="btn reject" disabled={busy || !reviewer.trim() || comment.trim().length < 3}
              onClick={() => submitDecision("reject")}>Reject</button>
          </div>
        </div>
      )}

      <div className="card">
        <h2>Extracted data</h2>
        <table className="fields">
          <tbody>
            {FIELD_LABELS.filter(([key]) => ex[key] !== null && ex[key] !== undefined).map(([key, label]) => (
              <tr key={key}><th>{label}</th><td>{String(ex[key])}</td></tr>
            ))}
          </tbody>
        </table>
        {ex.items.length > 0 && (
          <>
            <h3>Line items</h3>
            <table>
              <thead><tr><th>Description</th><th>Quantity</th><th>Unit price</th></tr></thead>
              <tbody>
                {ex.items.map((it, i) => (
                  <tr key={i}>
                    <td>{it.description}</td>
                    <td>{it.quantity ?? "-"}</td>
                    <td>{it.unit_price ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="card">
        <h2>Audit trail</h2>
        <ul className="timeline">
          {audit.map((e, i) => (
            <li key={i}>
              <strong>{e.action}</strong> by {e.actor}
              {e.from_status !== e.to_status && e.to_status && (
                <span className="muted"> ({e.from_status || "none"} → {e.to_status})</span>
              )}
              {e.comment && <div>“{e.comment}”</div>}
              <div className="muted small">{new Date(e.created_at).toLocaleString()}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
