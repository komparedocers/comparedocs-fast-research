import React, { useState } from 'react';
import axios from 'axios';

function PerformanceTest({ apiUrl }) {
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState([]);
  const [testConfig, setTestConfig] = useState({
    numDocs: 10,
    concurrent: 5,
  });

  const generateTestPdf = () => {
    // Generate a simple test PDF content
    const content = `
      Test Document ${Date.now()}

      Lorem ipsum dolor sit amet, consectetur adipiscing elit.
      Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
      Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.

      This is a test paragraph for performance testing.
      The system should process this quickly.

      Another paragraph with different content.
      Testing the anomaly detection capabilities.
    `.repeat(10);

    return new Blob([content], { type: 'application/pdf' });
  };

  const uploadTestDoc = async () => {
    const formData = new FormData();
    const blob = generateTestPdf();
    formData.append('file', blob, `test-${Date.now()}.pdf`);

    const startTime = performance.now();
    const response = await axios.post(`${apiUrl}/upload`, formData);
    const uploadTime = performance.now() - startTime;

    return {
      doc_id: response.data.doc_id,
      uploadTime,
    };
  };

  const runPerformanceTest = async () => {
    setRunning(true);
    setResults([]);
    const testResults = [];

    try {
      // Upload documents in batches
      const uploadPromises = [];
      for (let i = 0; i < testConfig.numDocs; i++) {
        uploadPromises.push(uploadTestDoc());

        if (uploadPromises.length >= testConfig.concurrent || i === testConfig.numDocs - 1) {
          const batchResults = await Promise.all(uploadPromises);
          testResults.push(...batchResults);
          uploadPromises.length = 0;

          setResults([...testResults]);
        }
      }

      // Run comparisons
      if (testResults.length >= 2) {
        const comparisonStart = performance.now();

        await axios.post(`${apiUrl}/compare`, {
          left_doc_id: testResults[0].doc_id,
          right_doc_id: testResults[1].doc_id,
        });

        const comparisonTime = performance.now() - comparisonStart;

        setResults([
          ...testResults,
          {
            type: 'comparison',
            comparisonTime,
          },
        ]);
      }
    } catch (error) {
      console.error('Performance test error:', error);
      alert('Error running performance test');
    } finally {
      setRunning(false);
    }
  };

  const calculateStats = () => {
    const uploads = results.filter((r) => r.uploadTime);
    if (uploads.length === 0) return null;

    const uploadTimes = uploads.map((r) => r.uploadTime);
    const avgUpload = uploadTimes.reduce((a, b) => a + b, 0) / uploadTimes.length;
    const minUpload = Math.min(...uploadTimes);
    const maxUpload = Math.max(...uploadTimes);

    const comparison = results.find((r) => r.type === 'comparison');

    return {
      totalDocs: uploads.length,
      avgUploadTime: avgUpload.toFixed(2),
      minUploadTime: minUpload.toFixed(2),
      maxUploadTime: maxUpload.toFixed(2),
      throughput: (uploads.length / (avgUpload / 1000)).toFixed(2),
      comparisonTime: comparison ? comparison.comparisonTime.toFixed(2) : 'N/A',
    };
  };

  const stats = calculateStats();

  return (
    <div className="performance-test">
      <h2>Performance Testing Dashboard</h2>
      <p>Test the system's ability to process multiple documents per minute</p>

      <div className="test-config">
        <div className="config-item">
          <label>Number of Documents:</label>
          <input
            type="number"
            value={testConfig.numDocs}
            onChange={(e) =>
              setTestConfig({ ...testConfig, numDocs: parseInt(e.target.value) })
            }
            min="1"
            max="100"
            disabled={running}
          />
        </div>

        <div className="config-item">
          <label>Concurrent Uploads:</label>
          <input
            type="number"
            value={testConfig.concurrent}
            onChange={(e) =>
              setTestConfig({ ...testConfig, concurrent: parseInt(e.target.value) })
            }
            min="1"
            max="20"
            disabled={running}
          />
        </div>

        <button onClick={runPerformanceTest} disabled={running} className="test-button">
          {running ? 'Running Test...' : 'Start Performance Test'}
        </button>
      </div>

      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <h3>Documents Processed</h3>
            <div className="stat-value">{stats.totalDocs}</div>
          </div>

          <div className="stat-card">
            <h3>Avg Upload Time</h3>
            <div className="stat-value">{stats.avgUploadTime}</div>
            <div className="stat-label">ms</div>
          </div>

          <div className="stat-card">
            <h3>Min / Max Upload</h3>
            <div className="stat-value">
              {stats.minUploadTime} / {stats.maxUploadTime}
            </div>
            <div className="stat-label">ms</div>
          </div>

          <div className="stat-card">
            <h3>Throughput</h3>
            <div className="stat-value">{stats.throughput}</div>
            <div className="stat-label">docs/sec</div>
          </div>

          <div className="stat-card">
            <h3>Comparison Time</h3>
            <div className="stat-value">{stats.comparisonTime}</div>
            <div className="stat-label">ms</div>
          </div>
        </div>
      )}

      {results.length > 0 && (
        <div className="results-log">
          <h3>Test Results Log</h3>
          <div className="log-container">
            {results.map((result, idx) => (
              <div key={idx} className="log-entry">
                {result.type === 'comparison' ? (
                  <span>
                    ✓ Comparison completed in {result.comparisonTime.toFixed(2)}ms
                  </span>
                ) : (
                  <span>
                    ✓ Document {idx + 1} uploaded in {result.uploadTime.toFixed(2)}ms (ID:{' '}
                    {result.doc_id.substring(0, 8)})
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default PerformanceTest;
