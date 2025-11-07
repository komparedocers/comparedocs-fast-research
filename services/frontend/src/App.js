import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';
import PerformanceTest from './PerformanceTest';

// Use same origin - nginx will proxy to gateway service
const API_URL = process.env.REACT_APP_API_URL || '';

function App() {
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [leftDoc, setLeftDoc] = useState('');
  const [rightDoc, setRightDoc] = useState('');
  const [comparing, setComparing] = useState(false);
  const [comparisonResult, setComparisonResult] = useState(null);
  const [activeTab, setActiveTab] = useState('compare');

  useEffect(() => {
    loadDocuments();
  }, []);

  const loadDocuments = async () => {
    try {
      const response = await axios.get(`${API_URL}/documents`);
      setDocuments(response.data);
    } catch (error) {
      console.error('Error loading documents:', error);
    }
  };

  const handleUpload = async (event, side) => {
    const file = event.target.files[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`${API_URL}/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (side === 'left') {
        setLeftDoc(response.data.doc_id);
      } else {
        setRightDoc(response.data.doc_id);
      }

      await loadDocuments();
      alert(`Uploaded ${file.name} successfully!`);
    } catch (error) {
      console.error('Error uploading:', error);
      alert('Error uploading file');
    } finally {
      setUploading(false);
    }
  };

  const handleCompare = async () => {
    if (!leftDoc || !rightDoc) {
      alert('Please select both documents to compare');
      return;
    }

    setComparing(true);
    setComparisonResult(null);

    try {
      const response = await axios.post(`${API_URL}/compare`, {
        left_doc_id: leftDoc,
        right_doc_id: rightDoc,
      });

      setComparisonResult(response.data);
    } catch (error) {
      console.error('Error comparing:', error);
      alert('Error comparing documents');
    } finally {
      setComparing(false);
    }
  };

  return (
    <div className="App">
      <header className="header">
        <h1>🚀 DocCompare - Ultra-Fast Document Comparison</h1>
        <p>Rust + Python Powered Anomaly Detection System</p>
      </header>

      <div className="tabs">
        <button
          className={activeTab === 'compare' ? 'tab active' : 'tab'}
          onClick={() => setActiveTab('compare')}
        >
          Document Comparison
        </button>
        <button
          className={activeTab === 'performance' ? 'tab active' : 'tab'}
          onClick={() => setActiveTab('performance')}
        >
          Performance Testing
        </button>
      </div>

      {activeTab === 'compare' && (
        <div className="container">
          <div className="upload-section">
            <div className="upload-box">
              <h3>Left Document</h3>
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => handleUpload(e, 'left')}
                disabled={uploading}
              />
              <select
                value={leftDoc}
                onChange={(e) => setLeftDoc(e.target.value)}
                className="doc-select"
              >
                <option value="">Select document...</option>
                {documents.map((doc) => (
                  <option key={doc.doc_id} value={doc.doc_id}>
                    {doc.filename} ({doc.page_count} pages)
                  </option>
                ))}
              </select>
            </div>

            <div className="compare-button-container">
              <button
                onClick={handleCompare}
                disabled={comparing || !leftDoc || !rightDoc}
                className="compare-button"
              >
                {comparing ? 'Comparing...' : 'Compare Documents'}
              </button>
            </div>

            <div className="upload-box">
              <h3>Right Document</h3>
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => handleUpload(e, 'right')}
                disabled={uploading}
              />
              <select
                value={rightDoc}
                onChange={(e) => setRightDoc(e.target.value)}
                className="doc-select"
              >
                <option value="">Select document...</option>
                {documents.map((doc) => (
                  <option key={doc.doc_id} value={doc.doc_id}>
                    {doc.filename} ({doc.page_count} pages)
                  </option>
                ))}
              </select>
            </div>
          </div>

          {comparisonResult && (
            <div className="results">
              <h2>Comparison Results</h2>

              <div className="stats-grid">
                <div className="stat-card compliant">
                  <h3>Compliant Paragraphs</h3>
                  <div className="stat-value">{comparisonResult.compliant_count}</div>
                  <div className="stat-percentage">
                    {comparisonResult.compliant_percentage.toFixed(2)}%
                  </div>
                </div>

                <div className="stat-card non-compliant">
                  <h3>Non-Compliant Paragraphs</h3>
                  <div className="stat-value">{comparisonResult.non_compliant_count}</div>
                  <div className="stat-percentage">
                    {comparisonResult.non_compliant_percentage.toFixed(2)}%
                  </div>
                </div>

                <div className="stat-card">
                  <h3>Processing Time</h3>
                  <div className="stat-value">{comparisonResult.processing_time_ms}</div>
                  <div className="stat-label">milliseconds</div>
                </div>

                <div className="stat-card">
                  <h3>Total Chunks</h3>
                  <div className="stat-value">
                    {comparisonResult.total_chunks_left} vs {comparisonResult.total_chunks_right}
                  </div>
                  <div className="stat-label">left vs right</div>
                </div>
              </div>

              <div style={{ textAlign: 'center', margin: '30px 0' }}>
                <button
                  onClick={() => window.open(`${API_URL}/comparisons/${comparisonResult.comparison_id}/report`, '_blank')}
                  className="report-button"
                >
                  📄 Download Full Report (HTML)
                </button>
              </div>

              <div className="matches-section">
                <h3>Detailed Comparison Table (3 Columns)</h3>
                <p style={{ marginBottom: '20px', color: '#666' }}>
                  Left Document | Right Document | Status & Percentage
                </p>

                <table className="comparison-table">
                  <thead>
                    <tr>
                      <th>Left Document Paragraph</th>
                      <th>Right Document Paragraph</th>
                      <th>Compliance Status & Percentage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparisonResult.matches.map((match, idx) => (
                      <tr key={idx}>
                        <td>{match.left_text.substring(0, 200)}{match.left_text.length > 200 ? '...' : ''}</td>
                        <td>{match.right_text.substring(0, 200)}{match.right_text.length > 200 ? '...' : ''}</td>
                        <td>
                          <div className={`status-badge ${match.match_type === 'exact' || match.match_type === 'similar' ? 'compliant' : 'non-compliant'}`}>
                            {match.match_type === 'exact' || match.match_type === 'similar' ? '✓ COMPLIANT' : '✗ NON-COMPLIANT'}
                          </div>
                          <div style={{ fontSize: '18px', fontWeight: 'bold', marginTop: '8px' }}>
                            {(match.similarity_score * 100).toFixed(1)}%
                          </div>
                          <div style={{ fontSize: '12px', color: '#666', marginTop: '4px' }}>
                            Type: {match.match_type.toUpperCase()}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <h3 style={{ marginTop: '40px' }}>Detailed Matches ({comparisonResult.matches.length})</h3>
                <div className="matches-list">
                  {comparisonResult.matches.map((match, idx) => (
                    <div
                      key={idx}
                      className={`match-item ${match.match_type}`}
                    >
                      <div className="match-header">
                        <span className="match-type-badge">{match.match_type}</span>
                        <span className="match-score">
                          {(match.similarity_score * 100).toFixed(1)}% similar
                        </span>
                      </div>
                      <div className="match-content">
                        <div className="match-text">
                          <strong>Left:</strong>
                          <p>{match.left_text.substring(0, 200)}...</p>
                        </div>
                        <div className="match-text">
                          <strong>Right:</strong>
                          <p>{match.right_text.substring(0, 200)}...</p>
                        </div>
                      </div>
                      {match.match_type === 'no_match' && (
                        <div className="diff-view">
                          <strong>Differences:</strong>
                          <div dangerouslySetInnerHTML={{ __html: match.diff_html.substring(0, 300) }} />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'performance' && <PerformanceTest apiUrl={API_URL} />}
    </div>
  );
}

export default App;
