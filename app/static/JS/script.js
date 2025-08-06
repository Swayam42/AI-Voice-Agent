// Function to format file size in a human-readable format
function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Wait for the page to load
document.addEventListener('DOMContentLoaded', () => {
  const textInput = document.getElementById('textInput');
  const submitButton = document.getElementById('submitBtn');
  const audio = document.getElementById('audio');
  const status = document.getElementById('status');

  // Echo Bot elements
  const toggleRecording = document.getElementById('toggleRecording');
  const pauseRecording = document.getElementById('pauseRecording');
  const echoAudio = document.getElementById('echoAudio');
  const echoStatus = document.getElementById('echoStatus');

  // Debug: Log elements to ensure they exist
  console.log("Elements:", { textInput, submitButton, audio, status, toggleRecording, pauseRecording, echoAudio, echoStatus });

  let mediaRecorder;
  let audioChunks = [];
  let isRecording = false;

  // Function to generate and play TTS audio
  async function generateAudio() {
    const text = textInput.value;
    if (!text) {
      status.textContent = "Please enter some text!";
      return;
    }

    status.textContent = "Generating audio...";
    audio.src = ""; // Clear previous audio
    console.log("Generating audio for:", text);

    try {
      const response = await fetch('/generate_audio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: text,
          voiceId: "en-US-charles",
          style: "Conversational",
          multiNativeLocale: "hi-IN"
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log("Response data:", data);
      if (data.error) {
        status.textContent = data.error;
      } else {
        audio.src = data.audio_url;
        status.textContent = "Audio ready! Click play.";
        audio.play().catch(err => status.textContent = "Error playing audio: " + err);
      }
    } catch (error) {
      status.textContent = "Error: " + error.message;
      console.error("Fetch error:", error);
    }
  }

  // Function to toggle recording
  function toggleEchoRecording() {
    if (!isRecording) {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (echoStatus) {
          echoStatus.textContent = "getUserMedia not supported on your browser!";
        }
        console.log("getUserMedia not supported on your browser!");
        return;
      }

      navigator.mediaDevices.getUserMedia({ audio: true })
        .then(stream => {
          mediaRecorder = new MediaRecorder(stream);
          audioChunks = [];

          mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
            console.log("Audio chunk captured:", event.data.size);
          };

          mediaRecorder.onstop = async () => {
            console.log("recorder stopped");
            const audioBlob = new Blob(audioChunks, { type: 'audio/ogg; codecs=opus' });
            const audioUrl = window.URL.createObjectURL(audioBlob);
            echoAudio.src = audioUrl;
            if (echoStatus) {
              echoStatus.textContent = "Uploading...";
            }
            stream.getTracks().forEach(track => track.stop());
            toggleRecording.innerHTML = '<span class="record-icon" id="recordDot">●</span> Start Recording';
            isRecording = false;
            pauseRecording.disabled = true;

            // Upload audio blob to server
            const formData = new FormData();
            formData.append('file', audioBlob, 'echo_recording.ogg');
            console.log('Uploading file:', audioBlob.size, 'bytes');
            try {
              const response = await fetch('/upload-audio', {
                method: 'POST',
                body: formData
              });
              console.log('Upload response status:', response.status);
              if (!response.ok) {
                const errorText = await response.text();
                console.error('Upload error response:', errorText);
                throw new Error(`Upload failed: ${response.status} - ${errorText}`);
              }
              const result = await response.json();
              console.log('Upload result:', result);
              // Show upload info directly in echoStatus for reliability
              if (echoStatus) {
                echoStatus.innerHTML = 'Upload successful ✅<br>' +
                  '<b>File:</b> ' + result.filename + '<br>' +
                  '<b>Type:</b> ' + result.content_type + '<br>' +
                  '<b>Size:</b> ' + formatFileSize(result.file_size);
              }
            } catch (err) {
              if (echoStatus) {
                echoStatus.innerHTML = 'Upload failed ❌<br>' + err.message;
              }
              console.error('Upload error:', err);
            }
          };

          mediaRecorder.start();
          console.log("recorder state:", mediaRecorder.state);
          console.log("recorder started");
          if (echoStatus) {
            echoStatus.textContent = "Recording...";
          }
          toggleRecording.innerHTML = '<span class="record-icon blinking" id="recordDot">●</span> Stop Recording';
          isRecording = true;
          pauseRecording.disabled = false;
        })
        .catch(err => {
          if (echoStatus) {
            echoStatus.textContent = `Microphone error: ${err.name} - ${err.message}`;
          }
          console.error("Microphone error:", err);
        });
    } else {
      if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        console.log("recorder state:", mediaRecorder.state);
        console.log("recorder stopped");
      }
    }
  }

  // Function to pause/resume recording
  function pauseEchoRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.pause();
      console.log("recorder paused");
      if (echoStatus) {
        echoStatus.textContent = "Recording paused...";
      }
      pauseRecording.textContent = "Resume";
    } else if (mediaRecorder && mediaRecorder.state === 'paused') {
      mediaRecorder.resume();
      console.log("recorder resumed");
      if (echoStatus) {
        echoStatus.textContent = "Recording...";
      }
      pauseRecording.textContent = "Pause";
    }
  }

  // Add click events
  if (submitButton) {
    submitButton.addEventListener('click', () => {
      console.log('Submit button clicked!');
      generateAudio();
    });
  } else {
    console.error("Submit button not found! Check the button ID in index.html.");
  }

  if (toggleRecording) {
    toggleRecording.addEventListener('click', () => {
      console.log('Toggle recording clicked!');
      toggleEchoRecording();
    });
  } else {
    console.error("Toggle recording button not found!");
  }

  if (pauseRecording) {
    pauseRecording.addEventListener('click', () => {
      console.log('Pause/resume clicked!');
      pauseEchoRecording();
    });
    pauseRecording.disabled = true; // Disable pause until recording starts
  } else {
    console.error("Pause button not found!");
  }
});