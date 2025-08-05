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
        echoStatus.textContent = "getUserMedia not supported on your browser!";
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

          mediaRecorder.onstop = () => {
            console.log("recorder stopped");
            const audioBlob = new Blob(audioChunks, { type: 'audio/ogg; codecs=opus' });
            const audioUrl = window.URL.createObjectURL(audioBlob);
            echoAudio.src = audioUrl;
            echoStatus.textContent = "Recording stopped";
            stream.getTracks().forEach(track => track.stop());
            toggleRecording.textContent = "Start Recording";
            isRecording = false;
            pauseRecording.disabled = true;
          };

          mediaRecorder.start();
          console.log("recorder state:", mediaRecorder.state);
          console.log("recorder started");
          echoStatus.textContent = "Recording...";
          toggleRecording.textContent = "Stop Recording";
          isRecording = true;
          pauseRecording.disabled = false;
        })
        .catch(err => {
          echoStatus.textContent = `Microphone error: ${err.name} - ${err.message}`;
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
      echoStatus.textContent = "Recording paused...";
      pauseRecording.textContent = "Resume";
    } else if (mediaRecorder && mediaRecorder.state === 'paused') {
      mediaRecorder.resume();
      console.log("recorder resumed");
      echoStatus.textContent = "Recording...";
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