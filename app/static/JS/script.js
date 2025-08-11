// Function to format file size in a human-readable format
function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

document.addEventListener('DOMContentLoaded', () => {
  // Elements - TTS section
  const textInput = document.getElementById('textInput');
  const submitButton = document.getElementById('submitBtn');
  const audio = document.getElementById('audio');
  const status = document.getElementById('status');

  // Echo bot
  const toggleRecording = document.getElementById('toggleRecording');
  const pauseRecording = document.getElementById('pauseRecording');
  const echoAudio = document.getElementById('echoAudio');
  const echoStatus = document.getElementById('echoStatus');

  // LLM bot
  const llmToggleRecording = document.getElementById('llmToggleRecording');
  const llmPauseRecording = document.getElementById('llmPauseRecording');
  const llmAudio = document.getElementById('llmAudio');
  const llmStatus = document.getElementById('llmStatus');
  const llmChatMessages = document.getElementById('llmChatMessages');

  // Session management: ensure session_id is in URL query param
  function ensureSessionId() {
    const url = new URL(window.location.href);
    let sid = url.searchParams.get('session_id');
    if (!sid) {
      sid = crypto.randomUUID();
      url.searchParams.set('session_id', sid);
      window.history.replaceState({}, '', url.toString());
    }
    return sid;
  }
  const sessionId = ensureSessionId();

  // Recording state
  let mediaRecorder; // echo
  let audioChunks = [];
  let isRecording = false;

  let llmMediaRecorder; // llm
  let llmAudioChunks = [];
  let isLlmRecording = false;
  // (no hands-free auto loop)

  async function generateAudio() {
    const text = textInput.value;
    if (!text) {
      status.textContent = "Please enter text!";
      return;
    }
    status.textContent = "Generating audio...";
    audio.src = "";
    try {
      const response = await fetch('/generate_audio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voiceId: "en-US-charles", style: "Conversational" })
      });
      const data = await response.json();
      if (response.ok) {
        audio.src = data.audio_url;
        status.textContent = "Audio ready!";
        audio.play().catch(() => status.textContent = "Error playing audio");
      } else {
        status.textContent = "Error: " + (data.detail || response.statusText);
      }
    } catch (error) {
      status.textContent = "Error: " + error.message;
      console.error("Fetch error:", error);
    }
  }

  function toggleEchoRecording() {
    if (!isRecording) {
      navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
          mediaRecorder = new MediaRecorder(stream);
          audioChunks = [];
          mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
          mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/ogg; codecs=opus' });
            echoStatus.textContent = "Generating Murf audio...";
            stream.getTracks().forEach(track => track.stop());
            toggleRecording.textContent = "Start Recording";
            isRecording = false;
            pauseRecording.disabled = true;

            const formData = new FormData();
            formData.append('file', audioBlob, 'echo_recording.ogg');
            try {
              const response = await fetch('/tts/echo', { method: 'POST', body: formData });
              const result = await response.json();
              if (response.ok) {
                echoAudio.src = result.audio_url;
                echoStatus.innerHTML = `Murf audio ready!<br><b>Transcription:</b> ${result.transcription || 'N/A'}`;
                echoAudio.play().catch(() => echoStatus.textContent = "Error playing audio");
              } else {
                echoStatus.textContent = "Error: " + (result.detail || response.statusText);
              }
            } catch (error) {
              echoStatus.textContent = "Error: " + error.message;
              console.error("Fetch error:", error);
            }
          };
          mediaRecorder.start();
          echoStatus.textContent = "Recording...";
          toggleRecording.textContent = "Stop Recording";
          isRecording = true;
          pauseRecording.disabled = false;
        })
        .catch(err => {
          echoStatus.textContent = "Microphone error: " + err.message;
          console.error("Microphone error:", err);
        });
    } else {
      mediaRecorder.stop();
    }
  }

  function pauseEchoRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.pause();
      echoStatus.textContent = "Paused...";
      pauseRecording.textContent = "Resume";
    } else if (mediaRecorder && mediaRecorder.state === 'paused') {
      mediaRecorder.resume();
      echoStatus.textContent = "Recording...";
      pauseRecording.textContent = "Pause";
    }
  }

  function toggleLlmRecording() {
    if (!isLlmRecording) {
      startLlmRecording();
    } else if (llmMediaRecorder && llmMediaRecorder.state !== 'inactive') {
      llmMediaRecorder.stop();
    }
  }

  function startLlmRecording() {
    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      llmMediaRecorder = new MediaRecorder(stream);
      llmAudioChunks = [];
      llmMediaRecorder.ondataavailable = e => llmAudioChunks.push(e.data);
      llmMediaRecorder.onstop = () => handleLlmStop(stream);
      llmMediaRecorder.start();
      isLlmRecording = true;
      llmPauseRecording.disabled = false;
      llmToggleRecording.textContent = 'Stop Recording';
      llmStatus.textContent = 'Listening...';
    }).catch(err => {
      llmStatus.textContent = 'Microphone error: ' + err.message;
    });
  }

  function handleLlmStop(stream) {
    stream.getTracks().forEach(t => t.stop());
    isLlmRecording = false;
    llmPauseRecording.disabled = true;
    llmToggleRecording.textContent = 'Start Recording';
    llmStatus.textContent = 'Processing...';
    const blob = new Blob(llmAudioChunks, { type: 'audio/ogg' });
    const fd = new FormData();
    fd.append('file', blob, 'llm_recording.ogg');
    fetch(`/agent/chat/${sessionId}`, { method: 'POST', body: fd })
      .then(r => r.json().then(data => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        console.log('LLM chat response:', data);
        if (!ok) throw new Error(data.detail || 'Request failed');
        appendChatMessage('user', data.transcribed_text || '[Unrecognized]');
        appendChatMessage('agent', data.llm_response || '[No response]');
        llmAudio.src = data.audio_url;
        llmAudio.onended = () => {
          // Auto start next user turn after reply plays
          if (!isLlmRecording) startLlmRecording();
        };
        llmAudio.play().catch(() => (llmStatus.textContent = 'Error playing audio'));
      })
      .catch(err => {
        llmStatus.textContent = 'Error: ' + err.message;
      });
  }

  function pauseLlmRecording() {
    if (!llmMediaRecorder) return;
    if (llmMediaRecorder.state === 'recording') {
      llmMediaRecorder.pause();
      llmStatus.textContent = 'Paused';
      llmPauseRecording.textContent = 'Resume';
    } else if (llmMediaRecorder.state === 'paused') {
      llmMediaRecorder.resume();
      llmStatus.textContent = 'Listening...';
      llmPauseRecording.textContent = 'Pause';
    }
  }

  function appendChatMessage(role, text) {
    if (!llmChatMessages) return null;
    const div = document.createElement('div');
    div.className = `chat-message ${role}`;
    const safeText = (text && text.toString().trim()) ? text.toString().trim() : (role === 'user' ? '[Unrecognized]' : '[No response]');
    div.innerHTML = `<div class="chat-text">${safeText}</div>`;
    llmChatMessages.appendChild(div);
    llmChatMessages.scrollTop = llmChatMessages.scrollHeight;
    return div;
  }

  function appendSystemMessage(text) {
    const div = document.createElement('div');
    div.className = 'chat-message agent';
    div.style.opacity = '0.7';
    div.innerHTML = `<div>${text}</div>`;
    llmChatMessages.appendChild(div);
  }

  function clearChat() {
    if (llmChatMessages) llmChatMessages.innerHTML = '';
  }

  // Add click events with error handling
  if (submitButton) {
    submitButton.addEventListener('click', generateAudio);
  } else {
    console.error("Submit button not found!");
  }
  if (toggleRecording) {
    toggleRecording.addEventListener('click', toggleEchoRecording);
  } else {
    console.error("Toggle Recording button not found!");
  }
  if (pauseRecording) {
    pauseRecording.addEventListener('click', pauseEchoRecording);
    pauseRecording.disabled = true;
  } else {
    console.error("Pause Recording button not found!");
  }
  llmToggleRecording?.addEventListener('click', toggleLlmRecording);
  llmPauseRecording?.addEventListener('click', pauseLlmRecording);
  llmPauseRecording && (llmPauseRecording.disabled = true);
});