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

  // Minimal WebSocket streaming toggle (replaces prior LLM chat flow)
  let streamWS = null;
  let streamMedia = null;
  let streamRecorder = null;
  let streaming = false;

  async function toggleMic() {
    unlockAudioIfNeeded();
    if (streaming) {
      try { streamRecorder && streamRecorder.state === 'recording' && streamRecorder.stop(); } catch(_){}
      try { streamMedia && streamMedia.getTracks().forEach(t=>t.stop()); } catch(_){}
      try { streamWS && streamWS.readyState === WebSocket.OPEN && streamWS.close(); } catch(_){}
      streaming = false;
      setMicState(false);
      if (llmStatus) llmStatus.textContent = '';
      console.log('[stream] stopped');
      return;
    }
    try {
      streamWS = new WebSocket((location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/ws');
      streamWS.binaryType = 'arraybuffer';
      streamWS.onopen = () => console.log('[stream] ws open');
      streamWS.onclose = () => console.log('[stream] ws close');
      streamWS.onerror = e => console.error('[stream] ws error', e);

      // Listen for real-time transcription messages from server
    let liveRow = null; // active bubble while user is speaking
    let lastPartial = '';
    let lastDisplayedFinal = '';
    streamWS.onmessage = function(event) {
      try {
        const raw = event.data;
        try {
          const obj = JSON.parse(raw);
          if (obj && obj.type === 'turn_end') {
            const finalText = obj.transcript ? normalizeTranscript(obj.transcript) : (lastPartial || null);
            // If we never created a live bubble (edge case), create now
            if (!liveRow && finalText) {
              liveRow = addMsg('user', finalText, {});
            } else if (liveRow?.bubble && finalText) {
              liveRow.bubble.textContent = finalText;
            }
            if (liveRow?.bubble) {
              liveRow.bubble.classList.add('final');
            }
            if (llmStatus) llmStatus.textContent = finalText ? ('Final: ' + finalText) : 'Turn ended';
            lastDisplayedFinal = finalText || '';
            liveRow = null; // reset for next utterance
            lastPartial = '';
            return;
          }
        } catch { /* not JSON */ }
        if (typeof raw === 'string' && raw.trim()) {
          const text = normalizeTranscript(raw);
            if (text !== lastPartial) {
              lastPartial = text;
              if (!liveRow) {
                liveRow = addMsg('user', text, {});
              } else if (liveRow?.bubble) {
                liveRow.bubble.textContent = text;
              }
              if (llmStatus) llmStatus.textContent = text;
            }
          }
      } catch(err) {
        console.error('[stream] transcription parse error', err);
      }
    };
    function normalizeTranscript(t){
      return t.replace(/\s+/g,' ').replace(/[\u200B-\u200D\uFEFF]/g,'').trim();
    }

      // Use Web Audio API for PCM streaming
      streamMedia = await navigator.mediaDevices.getUserMedia({ audio: true });
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const source = audioCtx.createMediaStreamSource(streamMedia);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      source.connect(processor);
      processor.connect(audioCtx.destination);

      processor.onaudioprocess = function(e) {
        const inputData = e.inputBuffer.getChannelData(0); // mono channel
        // Convert Float32 to 16-bit PCM
        const buffer = new ArrayBuffer(inputData.length * 2);
        const view = new DataView(buffer);
        for (let i = 0; i < inputData.length; i++) {
          let s = Math.max(-1, Math.min(1, inputData[i]));
          view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        }
        if (streamWS && streamWS.readyState === WebSocket.OPEN) {
          streamWS.send(buffer);
        }
      };

      streaming = true;
      setMicState(true);
      if (llmStatus) llmStatus.textContent = 'Streaming…';
      console.log('[stream] started');

      // Cleanup on stop
      streamWS.onclose = () => {
        processor.disconnect();
        source.disconnect();
        audioCtx.close();
        streamMedia.getTracks().forEach(t => t.stop());
        streaming = false;
        setMicState(false);
        if (llmStatus) llmStatus.textContent = '';
        console.log('[stream] ws closed and audio stopped');
      };
    } catch (err) {
      console.error('[stream] start failed', err);
      if (llmStatus) llmStatus.textContent = 'Mic error: ' + err.message;
      try { streamWS && streamWS.close(); } catch(_){}
      try { streamMedia && streamMedia.getTracks().forEach(t=>t.stop()); } catch(_){}
    }
  }

  // Wire up events
  ttsSubmit?.addEventListener('click', handleTtsGenerate);
  echoToggle?.addEventListener('click', toggleEcho);
  micToggle?.addEventListener('click', toggleMic);


});