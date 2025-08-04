// Wait for the page to load
document.addEventListener('DOMContentLoaded', () => {
  const textInput = document.getElementById('textInput');
  const submitButton = document.getElementById('submitBtn');
  const audio = document.getElementById('audio');
  const status = document.getElementById('status');

  // Debug: Log elements to ensure they exist
  console.log("Elements:", { textInput, submitButton, audio, status });

  // Function to generate and play audio
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

  // Add click event to the submit button only if it exists
  if (submitButton) {
    submitButton.addEventListener('click', () => {
      console.log('Submit button clicked!');
      generateAudio();
    });
  } else {
    console.error("Submit button not found! Check the button ID in index.html.");
  }
});