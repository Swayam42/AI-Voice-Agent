// Function to format file size in a human-readable format
function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

document.addEventListener('DOMContentLoaded', () => {
  const textInput = document.getElementById('textInput');
  const submitButton = document.getElementById('submitBtn');
  const audio = document.getElementById('audio');
  const status = document.getElementById('status');
  const toggleRecording = document.getElementById('toggleRecording');
  const pauseRecording = document.getElementById('pauseRecording');
  const echoAudio = document.getElementById('echoAudio');
  const echoStatus = document.getElementById('echoStatus');
  const llmToggleRecording = document.getElementById('llmToggleRecording');
  const llmPauseRecording = document.getElementById('llmPauseRecording');
  const llmAudio = document.getElementById('llmAudio');
  const llmStatus = document.getElementById('llmStatus');

  // Debug: Log elements to ensure they exist
  console.log("Elements:", {
    textInput, submitButton, audio, status,
    toggleRecording, pauseRecording, echoAudio, echoStatus,
    llmToggleRecording, llmPauseRecording, llmAudio, llmStatus
  });

  let mediaRecorder;
  let llmMediaRecorder;
  let audioChunks = [];
  let llmAudioChunks = [];
  let isRecording = false;
  let isLlmRecording = false;

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

  async function toggleLlmRecording() {
    if (!isLlmRecording) {
      if (!llmToggleRecording) {
        console.error("LLM Toggle Recording button not found!");
        llmStatus.textContent = "Error: Recording button not found!";
        return;
      }
      console.log("Starting LLM recording...");
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        llmMediaRecorder = new MediaRecorder(stream);
        llmAudioChunks = [];
        llmMediaRecorder.ondataavailable = event => llmAudioChunks.push(event.data);
        llmMediaRecorder.onstop = async () => {
          const audioBlob = new Blob(llmAudioChunks, { type: 'audio/ogg; codecs=opus' });
          llmStatus.textContent = "Processing LLM query...";
          stream.getTracks().forEach(track => track.stop());
          llmToggleRecording.textContent = "Start Recording";
          isLlmRecording = false;
          llmPauseRecording.disabled = true;

          const formData = new FormData();
          formData.append('file', audioBlob, 'llm_recording.ogg');
          try {
            const response = await fetch('/llm/query', { method: 'POST', body: formData });
            const result = await response.json();
            if (response.ok) {
              llmAudio.src = result.audio_url;
              llmStatus.textContent = "LLM audio ready!";
              llmAudio.play().catch(() => llmStatus.textContent = "Error playing audio");

              // Show transcribed text and LLM response
              const llmTranscribedText = document.getElementById('llmTranscribedText');
              const llmResponseText = document.getElementById('llmResponseText');
              if (llmTranscribedText) {
                llmTranscribedText.textContent = result.transcribed_text || '';
              }
              if (llmResponseText) {
                llmResponseText.textContent = result.llm_response || '';
              }
            } else {
              llmStatus.textContent = "Error: " + (result.detail || response.statusText);
            }
          } catch (error) {
            llmStatus.textContent = "Error: " + error.message;
            console.error("Fetch error:", error);
          }
        };
        llmMediaRecorder.start();
        llmStatus.textContent = "Recording...";
        llmToggleRecording.textContent = "Stop Recording";
        isLlmRecording = true;
        llmPauseRecording.disabled = false;
      } catch (err) {
        llmStatus.textContent = "Microphone error: " + err.message;
        console.error("Microphone error:", err);
      }
    } else {
      if (llmMediaRecorder && llmMediaRecorder.state !== 'inactive') {
        llmMediaRecorder.stop();
        console.log("LLM recorder stopped");
      }
    }
  }

  function pauseLlmRecording() {
    if (llmMediaRecorder && llmMediaRecorder.state === 'recording') {
      llmMediaRecorder.pause();
      llmStatus.textContent = "Paused...";
      llmPauseRecording.textContent = "Resume";
    } else if (llmMediaRecorder && llmMediaRecorder.state === 'paused') {
      llmMediaRecorder.resume();
      llmStatus.textContent = "Recording...";
      llmPauseRecording.textContent = "Pause";
    }
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
  if (llmToggleRecording) {
    llmToggleRecording.addEventListener('click', toggleLlmRecording);
  } else {
    console.error("LLM Toggle Recording button not found!");
  }
  if (llmPauseRecording) {
    llmPauseRecording.addEventListener('click', pauseLlmRecording);
    llmPauseRecording.disabled = true;
  } else {
    console.error("LLM Pause Recording button not found!");
  }
});