import { useState, useEffect } from 'react';

export function CutsMonitor() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchCuts = async () => {
    try {
      const token = localStorage.getItem('julius_token');
      const headers = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const res = await fetch('/api/bgp-mitm/logs/modifications', {
        headers
      });
      if (res.ok) {
        const data = await res.json();
        setEntries(data.entries || []);
      }
    } catch (err) {
      console.error('Failed to fetch cuts', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCuts();
    const interval = setInterval(fetchCuts, 3000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div>Loading cuts...</div>;

  return (
    <div className="bg-julius-surface p-4 rounded-xl">
      <h2 className="text-lg font-bold mb-4">💰 Real‑Time Cuts</h2>
      {entries.length === 0 ? (
        <p className="text-julius-muted">No cuts recorded yet.</p>
      ) : (
        <ul className="space-y-2 max-h-96 overflow-y-auto">
          {entries.map((entry, idx) => (
            <li key={idx} className="text-xs font-mono bg-julius-bg p-2 rounded border border-julius-border">
              {entry}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
