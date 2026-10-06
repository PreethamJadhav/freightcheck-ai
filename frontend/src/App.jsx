import { BrowserRouter, NavLink, Navigate, Route, Routes } from "react-router-dom";
import Upload from "./pages/Upload";
import DocumentList from "./pages/DocumentList";
import DocumentDetail from "./pages/DocumentDetail";

export default function App() {
  return (
    <BrowserRouter>
      <header className="topbar">
        <span className="brand">FreightCheck AI</span>
        <nav>
          <NavLink to="/upload">Upload</NavLink>
          <NavLink to="/documents">Documents</NavLink>
        </nav>
      </header>
      <main className="page">
        <Routes>
          <Route path="/" element={<Navigate to="/upload" replace />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/documents" element={<DocumentList />} />
          <Route path="/documents/:id" element={<DocumentDetail />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
