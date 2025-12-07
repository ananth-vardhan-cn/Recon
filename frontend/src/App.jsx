import React, { useState, useEffect, useRef } from 'react';
import { Terminal, MapPin, Search, Eye, Cpu, ArrowDownCircle, PauseCircle, PlayCircle } from 'lucide-react';

function App() {
  const [connected, setConnected] = useState(false);
  const [logs, setLogs] = useState([]);
  const [imageFile, setImageFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [zoomedImage, setZoomedImage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  
  const wsRef = useRef(null);
  const logsContainerRef = useRef(null);

  // Auto-scroll logs
  useEffect(() => {
    if (autoScroll && logsContainerRef.current) {
      const container = logsContainerRef.current;
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [logs, autoScroll]);

  // Auto-connect on mount
  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const connect = () => {
    // Connect to the FastAPI WebSocket
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket('ws://localhost:8000/ws');
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      // Clean slate on new connection
      setLogs([]);
    };


    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'new_image') {
        setZoomedImage(`http://localhost:8000${data.url}`);
        addLog('tool_result', 'Received High-Res Crop.');
      } else if (data.type === 'session_end') {
        setLoading(false);
        addLog('system', data.content);
      } else {
        addLog(data.type, data.content);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      addLog('error', 'Connection Lost. Reconnect required.');
      setLoading(false);
    };

    ws.onerror = (err) => {
      addLog('error', 'Connection Error.');
      setLoading(false);
    };
  };

  const addLog = (type, content) => {
    setLogs(prev => [...prev, { type, content, timestamp: new Date().toLocaleTimeString() }]);
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      setImageFile(file);
      setPreviewUrl(URL.createObjectURL(file));
      addLog('user', `Image selected: ${file.name}`);
    }
  };

  const startInvestigation = async () => {
    if (!imageFile || !connected) return;
    
    setLoading(true);
    setLogs([]); // Clear logs for fresh start
    setZoomedImage(null); // Clear previous zoom
    
    // 1. Upload Image via HTTP POST
    const formData = new FormData();
    formData.append('file', imageFile);

    try {
      const res = await fetch('http://localhost:8000/upload', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      
      // 2. Send the path to WS to start the agent
      wsRef.current.send(JSON.stringify({ file_path: data.file_path }));
    } catch (err) {
      addLog('error', 'Upload Failed.');
      setLoading(false);
    }
  };

  return (
    <div className="h-screen w-screen bg-obsidian-950 text-magma-50 flex font-mono relative overflow-hidden selection:bg-magma-900 selection:text-white">
      
      {/* Background Decoration */}
      <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-20 pointer-events-none"></div>
      <div className="scanline"></div>

      {/* Sidebar / Status Panel */}
      <div className="w-80 h-full border-r-2 border-magma-900 bg-obsidian-900/90 p-6 flex flex-col gap-6 z-10 backdrop-blur-sm shrink-0">
        <div className="border-b-2 border-magma-600 pb-4">
          <h1 className="text-4xl font-black tracking-tighter text-magma-500 glitch" data-text="RECON">RECON</h1>
          <p className="text-xs text-magma-300 mt-1 tracking-widest uppercase">Autonomous Geolocator</p>
        </div>

        {/* Connection Status */}
        <div className={`p-4 border ${connected ? 'border-magma-500 bg-magma-900/20' : 'border-stone-700 bg-stone-900'} transition-all duration-500`}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs uppercase font-bold">System Status</span>
            <Cpu size={16} className={connected ? "animate-pulse text-magma-400" : "text-stone-500"} />
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 shadow-[0_0_10px_#22c55e]' : 'bg-red-500'}`}></div>
            <span className="text-sm font-bold">{connected ? "ONLINE" : "OFFLINE"}</span>
          </div>
          {!connected && (
            <button onClick={connect} className="mt-3 w-full py-1 px-2 bg-magma-700 hover:bg-magma-600 text-xs font-bold uppercase tracking-wider transition-colors">
              Initialize Uplink
            </button>
          )}
        </div>

        {/* Image Input */}
        <div className="border border-dashed border-magma-800 p-4 text-center hover:bg-magma-900/10 transition-colors cursor-pointer relative group">
          <input 
            type="file" 
            onChange={handleFileSelect} 
            className="absolute inset-0 opacity-0 cursor-pointer"
            accept="image/*"
          />
          {previewUrl ? (
             <img src={previewUrl} alt="Target" className="w-full h-32 object-cover border border-magma-800 opacity-80 group-hover:opacity-100 transition-opacity" />
          ) : (
            <div className="py-8 text-magma-400 flex flex-col items-center gap-2">
              <MapPin size={32} />
              <span className="text-xs uppercase">Drop Target Image</span>
            </div>
          )}
        </div>

        {/* Action Button */}
        <button 
          onClick={startInvestigation}
          disabled={!connected || !imageFile || loading}
          className={`py-4 font-bold text-xl tracking-widest uppercase transition-all duration-300 
            ${(!connected || !imageFile) 
              ? 'bg-obsidian-800 text-stone-600 cursor-not-allowed' 
              : 'bg-magma-600 hover:bg-magma-500 text-black shadow-[0_0_20px_rgba(250,82,82,0.4)] hover:shadow-[0_0_30px_rgba(250,82,82,0.6)]'
            }`}
        >
          {loading ? 'Analyzing...' : 'Engage Agent'}
        </button>

        {/* Zoomed Image Preview */}
        {zoomedImage && (
          <div className="mt-auto border border-magma-500 p-1 bg-black">
            <p className="text-[10px] text-magma-500 mb-1 uppercase flex items-center gap-1"><Eye size={10}/> Active Focus</p>
            <img src={zoomedImage} alt="Zoom" className="w-full max-h-48 object-contain border border-magma-900" />
          </div>
        )}
      </div>

      {/* Main Terminal Area */}
      <div className="flex-1 h-full flex flex-col p-8 relative z-0 overflow-hidden">
        

        {/* Terminal Window */}
        <div className="flex-1 bg-black/80 border border-magma-900/50 shadow-2xl backdrop-blur-md flex flex-col overflow-hidden h-full">
          {/* Terminal Header */}
          <div className="bg-magma-950/50 border-b border-magma-900 p-2 flex items-center justify-between px-4 shrink-0">
            <div className="flex items-center gap-2">
              <Terminal size={14} className="text-magma-500" />
              <span className="text-xs text-magma-300 font-bold tracking-wider">AGENT_LOGS</span>
            </div>
            <div className="flex items-center gap-4">
               {/* Scroll Toggle */}
               <button 
                onClick={() => setAutoScroll(!autoScroll)}
                className={`flex items-center gap-1 text-[10px] uppercase font-bold ${autoScroll ? 'text-magma-400' : 'text-stone-600'} hover:text-white transition-colors`}
               >
                 {autoScroll ? <PauseCircle size={12} /> : <ArrowDownCircle size={12} />}
                 {autoScroll ? 'Auto-Scroll: ON' : 'Auto-Scroll: OFF'}
               </button>
            </div>
          </div>

          {/* Logs Container */}
          <div 
            ref={logsContainerRef} 
            className="flex-1 p-6 overflow-y-auto font-mono text-sm space-y-1 scrollbar-thin scrollbar-thumb-magma-600 scrollbar-track-obsidian-900"
          >
            {logs.length === 0 && connected && <div className="text-stone-600 italic">Waiting for input...</div>}
            {logs.map((log, i) => (
              <LogEntry key={i} log={log} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// Component for individual log lines
const LogEntry = ({ log }) => {
  const { type, content } = log;

  // Minimal styling that respects the raw text content but adds color
  const styles = {
    system: "text-magma-600 font-bold",
    user: "text-stone-400",
    agent_thought: "text-magma-100",
    tool_call: "text-amber-500",
    tool_result: "text-emerald-500",
    error: "text-red-500 bg-red-900/10",
    turn_start: "text-magma-400 font-bold pt-4 border-b border-magma-900/30 mb-2 inline-block w-full"
  };

  return (
    <div className={`${styles[type] || "text-gray-400"} whitespace-pre-wrap break-words font-mono leading-relaxed`}>
      {content}
    </div>
  );
};

export default App;
