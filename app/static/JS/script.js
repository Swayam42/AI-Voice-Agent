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
  // Settings modal elements
  const settingsBtn = document.getElementById('settingsBtn');
  const settingsModal = document.getElementById('settingsModal');
  const settingsClose = document.getElementById('settingsClose');
  const settingsReveal = document.getElementById('settingsReveal');
  const settingsSave = document.getElementById('settingsSave');
  const keyGemini = document.getElementById('keyGemini');
  const keyAAI = document.getElementById('keyAAI');
  const keyMurf = document.getElementById('keyMurf');
  const keyTavily = document.getElementById('keyTavily');
  const keyOW = document.getElementById('keyOW');
  const settingsPromptMsg = document.getElementById('settingsPromptMsg');
  // Optional UI sounds (place files in /static/sounds)
  const uiSoundStart = new Audio('/static/sounds/mic_start.mp3');
  const uiSoundStop = new Audio('/static/sounds/mic_stop.mp3');
  const uiSoundMute = new Audio('/static/sounds/mic_mute.mp3');

  // ---- Murf Streaming Audio Playback (WAV buffering) ----
  let murfAudioCtx = null;
  let murfAudioChunks = [];
  let murfPlaying = false;
  let murfFirstChunk = true;
  let murfSourceNode = null;

  function initMurfStreamPlayback() {
    if (!murfAudioCtx) {
      murfAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    murfAudioChunks = [];
    murfPlaying = true;
  murfFirstChunk = true;
  // Stop any previous source cleanly
  try { if (murfSourceNode) { murfSourceNode.onended = null; murfSourceNode.stop(0); } } catch(_) {}
  murfSourceNode = null;
    // Optionally show buffering/loading indicator
    if (llmStatus) llmStatus.textContent = 'Buffering Murf audio…';
  }

  function pushMurfAudioChunk(b64) {
    // Decode base64 to Uint8Array and buffer
    const binary = atob(b64);
    const len = binary.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
    // If a non-first chunk accidentally includes a WAV header, strip it
    // WAV header starts with 'RIFF' (52 49 46 46)
    if (!murfFirstChunk && len >= 44 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46) {
      murfAudioChunks.push(bytes.subarray(44));
    } else {
      murfAudioChunks.push(bytes);
    }
    murfFirstChunk = false;
    // console.log('[Murf] Received audio chunk, length:', len);
  }

  function finalizeMurfStream() {
    murfPlaying = false;
    if (!murfAudioCtx || murfAudioChunks.length === 0) return;
  try { if (murfAudioCtx.state === 'suspended') murfAudioCtx.resume(); } catch(_) {}
    // Concatenate all chunks into one Uint8Array
    const totalLen = murfAudioChunks.reduce((acc, arr) => acc + arr.length, 0);
    const fullAudio = new Uint8Array(totalLen);
    let offset = 0;
    for (const arr of murfAudioChunks) {
      fullAudio.set(arr, offset);
      offset += arr.length;
    }
    // If first chunk looked like WAV, fix RIFF sizes to reflect concatenated data
    if (murfAudioChunks.length > 0 && murfAudioChunks[0].length >= 44) {
      const first = murfAudioChunks[0];
      if (first[0] === 0x52 && first[1] === 0x49 && first[2] === 0x46 && first[3] === 0x46) {
        // Update ChunkSize (at offset 4) and Subchunk2Size (at offset 40)
        const view = new DataView(fullAudio.buffer);
        const dataSize = fullAudio.length - 44; // bytes after header
        // ChunkSize = 36 + Subchunk2Size
        view.setUint32(4, 36 + dataSize, true);
        view.setUint32(40, dataSize, true);
      }
    }
    // Decode and play the full WAV file
    murfAudioCtx.decodeAudioData(fullAudio.buffer, (audioBuffer) => {
      const source = murfAudioCtx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(murfAudioCtx.destination);
      murfSourceNode = source;
      // Update status
      if (llmStatus) llmStatus.textContent = 'Speaking…';
      // Close context only after playback finishes to avoid cutting tail
      source.onended = () => {
        try { source.disconnect(); } catch(_) {}
        if (llmStatus) llmStatus.textContent = '';
        try { murfAudioCtx && murfAudioCtx.close(); } catch(_) {}
        murfAudioCtx = null;
        murfSourceNode = null;
      };
      source.start();
    }, (err) => {
      console.error('Murf WAV decode error', err);
      if (llmStatus) llmStatus.textContent = 'Audio decode error';
    });
  }

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

  // Key storage helpers: persist per-session (survives hard refresh in this tab, resets when session_id changes)
  function readSessionKey(name){
    try { return sessionStorage.getItem(`KEY_${sessionId}_${name}`) || ''; } catch(_) { return ''; }
  }
  function writeSessionKey(name, value){
    try { if (typeof value === 'string') sessionStorage.setItem(`KEY_${sessionId}_${name}`, value); } catch(_) {}
  }

  // ---- Settings modal wiring ----
  function openSettings() { settingsModal?.classList.add('open'); settingsModal?.setAttribute('aria-hidden','false'); }
  function closeSettings() { settingsModal?.classList.remove('open'); settingsModal?.setAttribute('aria-hidden','true'); }
  settingsBtn?.addEventListener('click', openSettings);
  settingsClose?.addEventListener('click', closeSettings);
  // Close on click outside (backdrop or container outside the card)
  settingsModal?.addEventListener('click', (e)=>{
    if (!settingsModal) return;
    const card = settingsModal.querySelector('.modal-card');
    if (!card) return;
    if (e.target === settingsModal || e.target === settingsModal.querySelector('.modal-backdrop')) {
      closeSettings();
      return;
    }
    if (!card.contains(e.target)) closeSettings();
  });

  // Toggle show/hide for all API inputs
  let keysVisible = false;
  const ICON_EYE = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 5C7 5 2.73 8.11 1 12c1.73 3.89 6 7 11 7s9.27-3.11 11-7c-1.73-3.89-6-7-11-7Zm0 12a5 5 0 1 1 0-10 5 5 0 0 1 0 10Z" fill="currentColor"/>
    </svg>`;
  const ICON_EYE_OFF = `
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 5C7 5 2.73 8.11 1 12c1.73 3.89 6 7 11 7s9.27-3.11 11-7c-1.73-3.89-6-7-11-7Zm0 12a5 5 0 1 1 0-10 5 5 0 0 1 0 10Z" fill="currentColor"/>
      <path d="M3 3l18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    </svg>`;
  function setKeysVisibility(show) {
    const type = show ? 'text' : 'password';
    if (keyGemini) keyGemini.type = type;
    if (keyAAI) keyAAI.type = type;
    if (keyMurf) keyMurf.type = type;
    if (keyTavily) keyTavily.type = type;
    if (keyOW) keyOW.type = type;
    keysVisible = !!show;
    if (settingsReveal) {
      settingsReveal.innerHTML = show ? ICON_EYE : ICON_EYE_OFF;
      settingsReveal.setAttribute('aria-label', show ? 'Hide keys' : 'Show keys');
      settingsReveal.title = show ? 'Hide keys' : 'Show keys';
    }
  }
  settingsReveal?.addEventListener('click', (e)=> { e.stopPropagation(); setKeysVisibility(!keysVisible); });
  // Default to hidden (password)
  setKeysVisibility(false);

  // Prefill inputs from sessionStorage per session (never from server for security)
  try {
    if (keyGemini) keyGemini.value = readSessionKey('GEMINI');
    if (keyAAI) keyAAI.value = readSessionKey('AAI');
    if (keyMurf) keyMurf.value = readSessionKey('MURF');
    if (keyTavily) keyTavily.value = readSessionKey('TAVILY');
    if (keyOW) keyOW.value = readSessionKey('OW');
  } catch(_) {}

  async function saveSettings() {
    const payload = {
      GEMINI_API_KEY: (keyGemini && keyGemini.value.trim()) || '',
      ASSEMBLYAI_API_KEY: (keyAAI && keyAAI.value.trim()) || '',
      MURF_API_KEY: (keyMurf && keyMurf.value.trim()) || '',
      TAVILY_API_KEY: (keyTavily && keyTavily.value.trim()) || '',
      OPENWEATHER_API_KEY: (keyOW && keyOW.value.trim()) || ''
    };
  // Persist per-session (tab) for UX only
  writeSessionKey('GEMINI', payload.GEMINI_API_KEY);
  writeSessionKey('AAI', payload.ASSEMBLYAI_API_KEY);
  writeSessionKey('MURF', payload.MURF_API_KEY);
  writeSessionKey('TAVILY', payload.TAVILY_API_KEY);
  writeSessionKey('OW', payload.OPENWEATHER_API_KEY);
    try {
      const res = await fetch(`/settings/${encodeURIComponent(sessionId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error('Save failed');
      closeSettings();
      if (llmStatus) { llmStatus.textContent = 'Settings saved for this session'; setTimeout(()=>{ if (llmStatus.textContent === 'Settings saved for this session') llmStatus.textContent=''; }, 2000); }
    } catch(e) {
      if (llmStatus) { llmStatus.textContent = 'Settings save error'; setTimeout(()=>{ if (llmStatus.textContent === 'Settings save error') llmStatus.textContent=''; }, 2500); }
    }
  }
  settingsSave?.addEventListener('click', saveSettings);

  // --- Deployment mode: Require users to provide their own API keys ---
  function getCurrentKeys() {
    return {
      GEMINI: readSessionKey('GEMINI') || (keyGemini && keyGemini.value.trim()) || '',
      AAI: readSessionKey('AAI') || (keyAAI && keyAAI.value.trim()) || '',
      MURF: readSessionKey('MURF') || (keyMurf && keyMurf.value.trim()) || '',
      TAVILY: readSessionKey('TAVILY') || (keyTavily && keyTavily.value.trim()) || '',
      OW: readSessionKey('OW') || (keyOW && keyOW.value.trim()) || ''
    };
  }

  function requireKeysOrPrompt(feature) {
    const keys = getCurrentKeys();
    const missing = [];
    // Minimum keys by feature
    if (feature === 'mic') {
      if (!keys.AAI) missing.push('AssemblyAI');
      if (!keys.GEMINI) missing.push('Gemini');
      if (!keys.MURF) missing.push('Murf');
    } else if (feature === 'tts') {
      if (!keys.MURF) missing.push('Murf');
    } else if (feature === 'echo') {
      if (!keys.MURF) missing.push('Murf');
    }
    // Optional tools; uncomment to enforce
    // if (!keys.TAVILY) missing.push('Tavily');
    // if (!keys.OW) missing.push('OpenWeather');

    if (missing.length > 0) {
      if (settingsPromptMsg) {
        settingsPromptMsg.style.display = 'block';
        settingsPromptMsg.textContent = `Please provide your API keys to start: ${missing.join(', ')}`;
      }
      openSettings();
      // Focus first empty field for convenience
      const order = [keyAAI, keyGemini, keyMurf, keyTavily, keyOW];
      for (const el of order) { if (el && !el.value.trim()) { try { el.focus(); } catch(_){} break; } }
      return false;
    }
    // Hide any previous prompt
    if (settingsPromptMsg) { settingsPromptMsg.style.display = 'none'; settingsPromptMsg.textContent = ''; }
    return true;
  }

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
  if (!requireKeysOrPrompt('tts')) { return; }
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
  if (!requireKeysOrPrompt('echo')) { return; }
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
  if (!requireKeysOrPrompt('mic')) { return; }
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
  streamWS = new WebSocket((location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/ws?session_id=' + encodeURIComponent(sessionId));
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
            if (obj && obj.type === 'tts_chunk' && typeof obj.audio_b64 === 'string') {
              // Streaming Murf audio chunk received
              if (!murfPlaying) initMurfStreamPlayback();
              pushMurfAudioChunk(obj.audio_b64);
              return;
          }
            if (obj && obj.type === 'tts_done') {
              finalizeMurfStream();
              console.log('[client] TTS streaming done');
              return;
          }
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
           
            if (obj.llm_response) {
              addMsg('agent', obj.llm_response, {});
            }
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


  // Keyboard shortcut: 'm' toggles mic on/off (unless typing or modal open)
  document.addEventListener('keydown', (e) => {
    try {
      if (e.defaultPrevented) return;
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      const k = (e.key || '').toLowerCase();
      if (k !== 'm') return;
      const target = e.target;
      const tag = target && target.tagName ? target.tagName.toLowerCase() : '';
      if (tag === 'input' || tag === 'textarea' || (target && target.isContentEditable)) return;
      if (settingsModal && settingsModal.classList.contains('open')) return;
      e.preventDefault();
      toggleMic();
    } catch (_) {}
  });


});