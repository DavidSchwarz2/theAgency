"use client";

import { useEffect, useState } from "react";

interface HeartbeatEvent {
  type: string;
  ts: number;
}

export default function Home() {
  const [events, setEvents] = useState<HeartbeatEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const source = new EventSource("http://localhost:8000/events");

    source.onopen = () => setConnected(true);

    source.onmessage = (e) => {
      const data = JSON.parse(e.data) as HeartbeatEvent;
      setEvents((prev) => [data, ...prev].slice(0, 10));
    };

    source.onerror = () => setConnected(false);

    return () => source.close();
  }, []);

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 p-8">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">theAgency</h1>
        <p className="text-zinc-400 mb-8">AI Development Pipeline Orchestrator</p>

        <div className="flex items-center gap-2 mb-6">
          <span
            className={`inline-block w-2.5 h-2.5 rounded-full ${connected ? "bg-green-400" : "bg-red-500"}`}
          />
          <span className="text-sm text-zinc-400">
            {connected ? "Backend connected" : "Backend disconnected"}
          </span>
        </div>

        <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-400 mb-3">SSE Heartbeats</h2>
          {events.length === 0 ? (
            <p className="text-zinc-600 text-sm">Waiting for events...</p>
          ) : (
            <ul className="space-y-1">
              {events.map((e, i) => (
                <li key={i} className="text-xs font-mono text-zinc-300">
                  {new Date(e.ts * 1000).toISOString()} — {e.type}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </main>
  );
}
