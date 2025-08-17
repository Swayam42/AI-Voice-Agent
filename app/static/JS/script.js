// Minimal chat-first UI script wiring: sidebar tools, mic toggle, chat bubbles with play button
document.addEventListener('DOMContentLoaded', () => {
  // Sidebar controls
  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebarClose = document.getElementById('sidebarClose');

  const openSidebar = () => sidebar?.classList.add('open');
  const closeSidebar = () => sidebar?.classList.remove('open');
  sidebarToggle?.addEventListener('click', openSidebar);
  sidebarClose?.addEventListener('click', closeSidebar);

  // Elements - Tools (TTS & Echo) inside sidebar
  const ttsText = document.getElementById('ttsText');
  const ttsSubmit = document.getElementById('ttsSubmit');
  const ttsStatus = document.getElementById('ttsStatus');
  const ttsAudio = document.getElementById('ttsAudio');
  const ttsDownload = document.getElementById('ttsDownload');

  const echoToggle = document.getElementById('echoToggle');
  const echoStatus = document.getElementById('echoStatus');
  const echoAudio = document.getElementById('echoAudio');
  const echoDownload = document.getElementById('echoDownload');

  // Main LLM UI elements
  const micToggle = document.getElementById('micToggle');
  const micLabel = document.getElementById('micLabel');
  const llmStatus = document.getElementById('llmStatus');
  const chatMessages = document.getElementById('chatMessages');
  const agentAudio = document.getElementById('agentAudio');
  // Optional UI sounds (place files in /static/sounds)
  const uiSoundStart = new Audio('/static/sounds/mic_start.mp3');
  const uiSoundStop = new Audio('/static/sounds/mic_stop.mp3');
  const uiSoundMute = new Audio('/static/sounds/mic_mute.mp3');

  // ---- Autoplay Reliability Helpers (no external silence file needed) ----
  let audioUnlocked = false;
  let pendingAutoPlayUrl = null;
  function unlockAudioIfNeeded() {
    if (audioUnlocked) return;
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx) {
        const ctx = new Ctx();
        const buffer = ctx.createBuffer(1, 1, 22050); // 1 sample silent buffer
        const src = ctx.createBufferSource();
        src.buffer = buffer;
        src.connect(ctx.destination);
        src.start();
        setTimeout(() => { try { src.stop(); ctx.close(); } catch(_){} }, 25);
        audioUnlocked = true;
        if (pendingAutoPlayUrl) { const u = pendingAutoPlayUrl; pendingAutoPlayUrl = null; playAgentAudio(u, true); }
        return;
      }
    } catch(e) { console.warn('Audio unlock fallback', e); }
    audioUnlocked = true;
    if (pendingAutoPlayUrl) { const u = pendingAutoPlayUrl; pendingAutoPlayUrl = null; playAgentAudio(u, true); }
  }


  // Auto-play helper for agent audio
function playAgentAudio(url, force = false) {
  if (!agentAudio || !url) return;

  if (!audioUnlocked && !force) {
    pendingAutoPlayUrl = url;
    return;
  }

  try {
    agentAudio.pause();
    agentAudio.currentTime = 0;
  } catch (_) {}

  try {
    agentAudio.srcObject = null;
  } catch (_) {}

  const cacheBustUrl = url + (url.includes('?') ? '&' : '?') + 't=' + Date.now();
  agentAudio.src = cacheBustUrl;

  // Try to play immediately once metadata is loaded
  agentAudio.onloadeddata = () => {
    agentAudio.play().catch(err => {
      console.warn('First play attempt blocked:', err);
      retryPlay();
    });
  };

  // fallback retry logic
  function retryPlay(attempt = 1) {
    if (attempt > 3) {
      pendingAutoPlayUrl = url; // try on next gesture
      return;
    }
    setTimeout(() => {
      agentAudio.play()
        .then(() => console.log('Audio playback started (retry)', attempt))
        .catch(() => retryPlay(attempt + 1));
    }, 250 * attempt);
  }
}


  // Session management: ensure session_id in URL
  function ensureSessionId() {
    const url = new URL(window.location.href);
    let sid = url.searchParams.get('session_id');
    if (!sid) {
      sid = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
      url.searchParams.set('session_id', sid);
      window.history.replaceState({}, '', url.toString());
    }
    return sid;
  }
  const sessionId = ensureSessionId();

  // Recording state
  let echoRecorder = null;
  let echoChunks = [];
  let isEchoRecording = false;

  let micRecorder = null;
  let micChunks = [];
  let isMicRecording = false;
  let pendingUserBubble = null;

  // Helpers: UI
  function setMicState(active) {
    isMicRecording = !!active;
    if (micToggle) {
      micToggle.classList.toggle('active', active);
      micToggle.classList.toggle('idle', !active);
    }
    if (micLabel) micLabel.textContent = active ? 'Stop Speaking' : 'Start Speaking';
    if (llmStatus) llmStatus.textContent = active ? 'Listening…' : '';
    // Try playing small UI sound cues; ignore failures
    try {
      if (active) {
        // If coming from muted state, prefer start sound
        uiSoundStart.currentTime = 0; uiSoundStart.play().catch(() => {});
      } else {
        uiSoundStop.currentTime = 0; uiSoundStop.play().catch(() => {});
      }
    } catch (_) {}
  }

  function addMsg(role, text, opts = {}) {
    if (!chatMessages) return null;
    const row = document.createElement('div');
    row.className = `msg ${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = (text && String(text).trim()) || (role === 'user' ? '[Unrecognized]' : '[No response]');
    row.appendChild(bubble);

    if (role === 'agent' && opts.audioUrl) {
      const btn = document.createElement('button');
      btn.className = 'play-btn';
      btn.setAttribute('aria-label', 'Play response');
      btn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M8 5v14l11-7-11-7z" fill="currentColor"/>
        </svg>`;
      btn.addEventListener('click', () => {
        if (!agentAudio) return;
        if (agentAudio.src !== opts.audioUrl) agentAudio.src = opts.audioUrl;
        agentAudio.play().catch(() => {});
      });
      row.appendChild(btn);
    }

    chatMessages.appendChild(row);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return { row, bubble };
  }

  // Sidebar: TTS
  async function handleTtsGenerate() {
    if (!ttsText || !ttsAudio || !ttsStatus) return;
    const text = ttsText.value.trim();
    if (!text) {
      ttsStatus.textContent = 'Enter text';
      return;
    }
    ttsStatus.textContent = 'Generating audio…';
    ttsAudio.removeAttribute('src');
    try {
      const res = await fetch('/generate_audio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voiceId: 'en-US-charles', style: 'Conversational' })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      ttsAudio.src = data.audio_url;
      ttsStatus.textContent = 'Audio ready';
      if (ttsDownload) {
        ttsDownload.href = data.audio_url;
        ttsDownload.style.display = 'inline-block';
        const fname = 'tts_audio_' + Date.now() + '.mp3';
        ttsDownload.setAttribute('download', fname);
      }
      ttsAudio.play().catch(() => {});
    } catch (e) {
      ttsStatus.textContent = 'Error: ' + e.message;
    }
  }

  // Sidebar: Echo
  function toggleEcho() {
    if (isEchoRecording) {
      echoRecorder && echoRecorder.state !== 'inactive' && echoRecorder.stop();
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      echoChunks = [];
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/ogg;codecs=opus';
      echoRecorder = new MediaRecorder(stream, { mimeType: mime });
      echoRecorder.ondataavailable = e => e.data && echoChunks.push(e.data);
      echoRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        isEchoRecording = false;
        if (echoToggle) echoToggle.textContent = 'Start Recording';
        if (echoStatus) echoStatus.textContent = 'Generating audio…';

        const blob = new Blob(echoChunks, { type: mime });
        const fd = new FormData();
        fd.append('file', blob, mime.includes('webm') ? 'echo.webm' : 'echo.ogg');
        try {
          const res = await fetch('/tts/echo', { method: 'POST', body: fd });
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail || res.statusText);
          if (echoAudio) echoAudio.src = data.audio_url;
          if (echoStatus) echoStatus.textContent = 'Murf audio ready';
          if (echoDownload) {
            echoDownload.href = data.audio_url;
            echoDownload.style.display = 'inline-block';
            echoDownload.setAttribute('download', 'echo_audio_' + Date.now() + '.mp3');
          }
          echoAudio?.play().catch(() => {});
        } catch (e) {
          if (echoStatus) echoStatus.textContent = 'Error: ' + e.message;
        }
      };
      echoRecorder.start();
      isEchoRecording = true;
      if (echoToggle) echoToggle.textContent = 'Stop Recording';
      if (echoStatus) echoStatus.textContent = 'Recording…';
    }).catch(err => {
      if (echoStatus) echoStatus.textContent = 'Microphone error: ' + err.message;
    });
  }

  // LLM: Mic toggle and chat flow
  function toggleMic() {
  // Unlock audio on first user gesture
  unlockAudioIfNeeded();

  if (isMicRecording) {
    micRecorder && micRecorder.state !== 'inactive' && micRecorder.stop();
    return;
  }

  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      micChunks = [];
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
        ? 'audio/webm;codecs=opus' 
        : 'audio/ogg;codecs=opus';
      micRecorder = new MediaRecorder(stream, { mimeType: mime });
      micRecorder.ondataavailable = e => e.data && micChunks.push(e.data);
      micRecorder.onstop = () => handleMicStop(stream, mime);
      micRecorder.start();
      setMicState(true);
      const pending = addMsg('user', '…');
      pendingUserBubble = pending?.bubble || null;
    })
    .catch(err => {
      if (llmStatus) llmStatus.textContent = 'Microphone error: ' + err.message;
    });
}


  function handleMicStop(stream, mime) {
    stream.getTracks().forEach(t => t.stop());
    setMicState(false);
    if (llmStatus) llmStatus.textContent = 'Processing…';

    const blob = new Blob(micChunks, { type: mime });
    const fd = new FormData();
    fd.append('file', blob, mime.includes('webm') ? 'input.webm' : 'input.ogg');

    fetch(`/agent/chat/${sessionId}`, { method: 'POST', body: fd })
      .then(r => r.json().then(data => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) throw new Error(data.detail || 'Request failed');

        // Replace pending user bubble with actual transcript
        if (pendingUserBubble) {
          pendingUserBubble.textContent = (data.transcribed_text && String(data.transcribed_text).trim()) || '[Unrecognized]';
          pendingUserBubble = null;
        } else {
          addMsg('user', data.transcribed_text || '[Unrecognized]');
        }

        // Agent message with play button
  addMsg('agent', data.llm_response || '[No response]', { audioUrl: data.audio_url });
  playAgentAudio(data.audio_url);

        if (llmStatus) llmStatus.textContent = '';
      })
      .catch(err => {
        if (pendingUserBubble) {
          pendingUserBubble.textContent = '[Unrecognized]';
          pendingUserBubble = null;
        }
        if (llmStatus) llmStatus.textContent = 'Error: ' + err.message;
      });
  }

  // Wire up events
  ttsSubmit?.addEventListener('click', handleTtsGenerate);
  echoToggle?.addEventListener('click', toggleEcho);
  micToggle?.addEventListener('click', toggleMic);

  // ================= Day 16: Non-destructive Streaming Add-On =================
  const streamBtn = document.getElementById('startAndstopBtn'); // Optional separate streaming control
  const streamLog = document.getElementById('chat-log') || chatMessages; // Reuse chat if no dedicated log
  let streamWS = null;
  let streamRecorder = null;
  let streamMedia = null;
  let streamActive = false;

  function logStream(msg, cls='stream') {
    if (!streamLog) { console.log('[stream]', msg); return; }
    const div = document.createElement('div');
    div.className = `msg ${cls}`;
    div.textContent = `[stream] ${msg}`;
    streamLog.appendChild(div);
    streamLog.scrollTop = streamLog.scrollHeight;
  }

  function wsProto() { return location.protocol === 'https:' ? 'wss' : 'ws'; }

  async function startStreaming() {
    if (streamActive) return;
    try {
      streamWS = new WebSocket(`${wsProto()}://${location.host}/ws/stream-audio`);
      streamWS.onopen = () => logStream('WebSocket connected','status');
      streamWS.onclose = () => logStream('WebSocket closed','status');
      streamWS.onerror = e => logStream('WebSocket error','error');
      streamWS.onmessage = e => {
        try {
          const d = JSON.parse(e.data);
          if (d.type === 'ready') logStream('File: '+d.file,'status');
          else if (d.type === 'progress') logStream('Progress '+d.bytes+' bytes','progress');
            else if (d.type === 'done') logStream('Saved '+d.file+' ('+d.bytes+' bytes)','success');
            else if (d.type === 'error') logStream('Error: '+d.message,'error');
            else logStream((d.type||'msg')+': '+e.data,'meta');
        } catch { logStream(e.data,'meta'); }
      };

      streamMedia = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : '';
      streamRecorder = new MediaRecorder(streamMedia, mime? { mimeType: mime }: undefined);
      streamRecorder.ondataavailable = ev => {
        if (ev.data && ev.data.size > 0 && streamWS?.readyState === WebSocket.OPEN) streamWS.send(ev.data);
      };
      streamRecorder.onstop = () => {
        try { streamWS?.readyState === WebSocket.OPEN && streamWS.send('END'); } catch {}
        try { streamWS?.close(); } catch {}
      };
      streamRecorder.start(500);
      streamActive = true;
      if (streamBtn) { streamBtn.textContent = 'Stop Streaming'; streamBtn.classList.add('recording'); }
      logStream('Streaming started…','status');
    } catch (err) {
      logStream('Start error: '+err.message,'error');
      try { streamMedia?.getTracks().forEach(t=>t.stop()); } catch {}
    }
  }

  function stopStreaming() {
    if (!streamActive) return;
    try { streamRecorder && streamRecorder.state !== 'inactive' && streamRecorder.stop(); } catch {}
    try { streamMedia?.getTracks().forEach(t=>t.stop()); } catch {}
    streamActive = false;
    if (streamBtn) { streamBtn.textContent = 'Start Streaming'; streamBtn.classList.remove('recording'); }
    logStream('Streaming stopped','status');
  }

  streamBtn?.addEventListener('click', e => { e.preventDefault(); streamActive ? stopStreaming() : startStreaming(); });
  // Expose helpers for console debugging
  window.__streaming = { startStreaming, stopStreaming };
  // ========================================================================
});