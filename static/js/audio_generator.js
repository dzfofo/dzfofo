// Audio Generator JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const textInput = document.getElementById('text-input');
    const voiceSelect = document.getElementById('voice-select');
    const useBrowserTts = document.getElementById('use-browser-tts');
    const generateButton = document.getElementById('generate-audio-button');
    const loadingSpinner = document.getElementById('loading-spinner');
    const audioResult = document.getElementById('audio-result');
    
    // Event listeners
    generateButton.addEventListener('click', generateAudio);
    
    // Load settings from localStorage
    const savedVoice = localStorage.getItem('audioVoice') || 'EXAVITQu4vr4xnSDxMaL';
    const useBrowser = localStorage.getItem('useBrowserTTS') === 'true';
    
    voiceSelect.value = savedVoice;
    useBrowserTts.checked = useBrowser;
    
    // Save settings to localStorage
    voiceSelect.addEventListener('change', function() {
        localStorage.setItem('audioVoice', voiceSelect.value);
    });
    
    useBrowserTts.addEventListener('change', function() {
        localStorage.setItem('useBrowserTTS', useBrowserTts.checked);
    });
    
    // Generate audio function
    function generateAudio() {
        const text = textInput.value.trim();
        const voiceId = voiceSelect.value;
        const useBrowser = useBrowserTts.checked;
        
        // Validate input
        if (!text) {
            showToast('يرجى إدخال نص لتحويله إلى صوت', 'error');
            return;
        }
        
        // Use browser's built-in TTS if selected
        if (useBrowser) {
            useBrowserTTS(text);
            return;
        }
        
        // Show loading state
        loadingSpinner.style.display = 'block';
        generateButton.disabled = true;
        audioResult.innerHTML = '';
        
        // Call API
        fetch('/api/text_to_speech', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                text: text,
                voice_id: voiceId
            }),
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            // Hide loading spinner
            loadingSpinner.style.display = 'none';
            generateButton.disabled = false;
            
            if (data.status === 'error') {
                // Show error message
                showToast(data.message || 'حدث خطأ أثناء توليد الصوت', 'error');
                
                // Use browser TTS as fallback
                useBrowserTTS(text);
                return;
            }
            
            if (data.status === 'success' && data.audio) {
                // Success with audio data
                showToast(data.message, 'success');
                
                // Create audio from base64
                const audioSrc = 'data:audio/mpeg;base64,' + data.audio;
                
                // Create audio element
                const audio = document.createElement('audio');
                audio.controls = true;
                audio.src = audioSrc;
                
                // Create download button
                const downloadBtn = document.createElement('button');
                downloadBtn.className = 'download-button';
                downloadBtn.innerHTML = '<i class="fas fa-download"></i> تحميل الصوت';
                downloadBtn.addEventListener('click', function() {
                    // Create a temporary link to download the audio
                    const link = document.createElement('a');
                    link.href = audioSrc;
                    link.download = 'yasmin-generated-audio.mp3';
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                });
                
                // Clear previous results and add new audio
                audioResult.innerHTML = '';
                
                // Create container for audio and download button
                const audioContainer = document.createElement('div');
                audioContainer.className = 'audio-container';
                
                // Add audio and download button to container
                audioContainer.appendChild(audio);
                audioContainer.appendChild(downloadBtn);
                
                // Add container to result area
                audioResult.appendChild(audioContainer);
                
                // Auto-play the audio
                audio.play();
            } else {
                // Success message but no audio (should not happen)
                showToast(data.message || 'تم توليد الصوت، لكن هناك مشكلة في تشغيله', 'warning');
                
                // Use browser TTS as fallback
                useBrowserTTS(text);
            }
        })
        .catch(error => {
            console.error('Error generating audio:', error);
            loadingSpinner.style.display = 'none';
            generateButton.disabled = false;
            
            // Try browser TTS as fallback
            showToast('حدث خطأ أثناء توليد الصوت، جارٍ استخدام المتصفح كبديل', 'error');
            useBrowserTTS(text);
        });
    }
    
    // Browser TTS function with improved Arabic support
    function useBrowserTTS(text) {
        if ('speechSynthesis' in window) {
            // Clear previous results if no content
            if (audioResult.innerHTML === '') {
                audioResult.innerHTML = '';
                
                // Create message
                const message = document.createElement('div');
                message.className = 'browser-tts-message';
                message.innerHTML = `
                    <i class="fas fa-volume-up"></i>
                    <p>جارٍ التشغيل باستخدام المتصفح...</p>
                `;
                audioResult.appendChild(message);
            }
            
            // Create and configure utterance with improved settings
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'ar-SA';
            utterance.rate = 0.9; // Slightly slower for better Arabic pronunciation
            utterance.pitch = 1.0; // Normal pitch
            utterance.volume = 1.0; // Full volume
            
            // Log available voices for debugging
            console.log('Available voices:', window.speechSynthesis.getVoices());
            
            // Get available voices
            let voices = window.speechSynthesis.getVoices();
            
            // If voices array is empty, wait for voices to load (Chrome needs this)
            if (voices.length === 0) {
                window.speechSynthesis.onvoiceschanged = function() {
                    voices = window.speechSynthesis.getVoices();
                    console.log('Voices loaded:', voices);
                    setVoiceAndSpeak();
                };
            } else {
                setVoiceAndSpeak();
            }
            
            function setVoiceAndSpeak() {
                // Try to find Arabic voice with more robust detection
                let arabicVoice = voices.find(voice => 
                    voice.lang.includes('ar') || 
                    voice.name.includes('Arabic') || 
                    voice.name.includes('العرب') ||
                    voice.name.includes('Arab')
                );
                
                if (arabicVoice) {
                    utterance.voice = arabicVoice;
                    console.log('Using Arabic voice:', arabicVoice.name);
                } else {
                    console.log('No Arabic voice found, using default voice');
                    
                    // If no Arabic voice is found, try to use a voice that supports multiple languages
                    let multilingualVoice = voices.find(voice => 
                        voice.name.includes('Google') || 
                        voice.name.includes('Microsoft')
                    );
                    
                    if (multilingualVoice) {
                        utterance.voice = multilingualVoice;
                        console.log('Using multilingual voice:', multilingualVoice.name);
                    }
                }
                
                // Handle speech end
                utterance.onend = function() {
                    console.log('Speech ended successfully');
                    const message = document.querySelector('.browser-tts-message');
                    if (message) {
                        message.innerHTML = `
                            <i class="fas fa-check-circle"></i>
                            <p>تم تشغيل الصوت بنجاح</p>
                        `;
                    }
                };
                
                // Handle speech error
                utterance.onerror = function(event) {
                    console.error('Speech synthesis error:', event);
                    const message = document.querySelector('.browser-tts-message');
                    if (message) {
                        message.innerHTML = `
                            <i class="fas fa-exclamation-circle"></i>
                            <p>حدث خطأ أثناء التشغيل</p>
                        `;
                    }
                };
                
                // Handle speech start
                utterance.onstart = function() {
                    console.log('Speech started');
                };
                
                // Cancel any ongoing speech
                window.speechSynthesis.cancel();
                
                // A small trick to ensure playback works more reliably
                setTimeout(() => {
                    // Speak the text
                    window.speechSynthesis.speak(utterance);
                    
                    // Show info message
                    showToast('جارٍ التشغيل باستخدام المتصفح', 'info');
                }, 100);
            }
        } else {
            showToast('المتصفح لا يدعم ميزة تحويل النص إلى كلام', 'error');
        }
    }
    
    // Handle Ctrl+Enter to generate
    textInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && (e.ctrlKey || e.shiftKey)) {
            e.preventDefault();
            generateAudio();
        }
    });
});