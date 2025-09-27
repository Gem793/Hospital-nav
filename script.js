let mediaRecorder;
let audioChunks = [];
let isRecording = false;

function showStatus(message, type) {
    const status = document.getElementById('status');
    status.textContent = message;
    status.className = `status ${type}`;
    status.classList.remove('hidden');
}

async function findPath() {
    const start = document.getElementById('startRoom').value.trim();
    const end = document.getElementById('endRoom').value.trim();
    
    if (!start || !end) {
        showStatus('Please enter both start and end rooms.', 'error');
        return;
    }
    
    showStatus('Finding path...', 'processing');
    
    try {
        const response = await fetch('/get_path', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ start, end })
        });
        
        if (!response.ok) {
            const error = await response.json();
            showStatus('Error: ' + error.error, 'error');
            return;
        }
        
        const blob = await response.blob();
        const imageUrl = URL.createObjectURL(blob);
        document.getElementById('pathImage').src = imageUrl;
        document.getElementById('pathImage').style.display = 'block';
        showStatus('Path found successfully!', 'success');
        
    } catch (error) {
        showStatus('Failed to connect to server.', 'error');
    }
}

async function toggleRecording() {
    if (isRecording) stopRecording();
    else await startRecording();
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        
        mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
        mediaRecorder.onstop = processAudio;
        mediaRecorder.start();
        isRecording = true;
        
        document.getElementById('voiceBtn').classList.add('recording');
        document.getElementById('voiceBtn').textContent = '⏹ Stop Recording';
        showStatus('Recording... Speak now', 'info');
        
    } catch (error) {
        showStatus('Microphone access denied.', 'error');
    }
}

function stopRecording() {
    if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        isRecording = false;
        document.getElementById('voiceBtn').classList.remove('recording');
        document.getElementById('voiceBtn').textContent = '🎤 Voice Command';
        showStatus('Processing voice...', 'processing');
        mediaRecorder.stream.getTracks().forEach(track => track.stop());
    }
}

async function processAudio() {
    const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
    const formData = new FormData();
    formData.append('audio', audioBlob);
    
    try {
        const response = await fetch('/voice_path', {method: 'POST', body: formData});
        if (!response.ok) throw new Error((await response.json()).error);
        
        const blob = await response.blob();
        const imageUrl = URL.createObjectURL(blob);
        document.getElementById('pathImage').src = imageUrl;
        document.getElementById('pathImage').style.display = 'block';
        showStatus('Voice command processed!', 'success');
        
    } catch (error) {
        showStatus('Error: ' + error.message, 'error');
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('findPath').addEventListener('click', findPath);
    document.getElementById('voiceBtn').addEventListener('click', toggleRecording);
    
    document.addEventListener('keypress', function(event) {
        if (event.key === 'Enter') findPath();
    });
});