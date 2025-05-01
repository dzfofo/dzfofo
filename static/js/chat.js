// Chat functionality
document.addEventListener("DOMContentLoaded", function() {
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const messagesContainer = document.getElementById('chat-messages');
    const suggestedChips = document.querySelectorAll('.suggestion-chip');
    const micButton = document.getElementById('mic-btn');
    const autoModeButton = document.getElementById('auto-mode-btn');
    
    // Get assistant ID from data attribute
    const assistantId = messagesContainer.dataset.assistantId;
    const assistantAvatar = messagesContainer.dataset.assistantAvatar;
    
    // Auto mode variables
    let autoModeEnabled = true; // Enable auto mode by default
    let typingTimer = null;
    const doneTypingInterval = 1500; // Time in ms after user stops typing to auto-send (1.5 seconds)
    
    // Add event listener to auto mode button
    if (autoModeButton) {
        autoModeButton.addEventListener('click', function() {
            autoModeEnabled = !autoModeEnabled;
            
            if (autoModeEnabled) {
                autoModeButton.classList.add('active');
                autoModeButton.classList.remove('inactive');
                autoModeButton.title = "وضع الإرسال التلقائي مفعل";
                showToast('تم تفعيل وضع الإرسال التلقائي', 'info');
            } else {
                autoModeButton.classList.remove('active');
                autoModeButton.classList.add('inactive');
                autoModeButton.title = "وضع الإرسال التلقائي معطل";
                showToast('تم تعطيل وضع الإرسال التلقائي', 'info');
            }
            
            // Clear any pending auto-send timer
            clearTimeout(typingTimer);
        });
    }
    
    // Speech recognition setup
    let recognition;
    let isListening = false;
    
    // Check if browser supports speech recognition
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        // Initialize speech recognition
        recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        recognition.continuous = false;
        recognition.interimResults = true;
        recognition.lang = 'ar-SA'; // Set language to Arabic
        
        // Handle speech recognition results
        recognition.onresult = function(event) {
            const transcript = Array.from(event.results)
                .map(result => result[0])
                .map(result => result.transcript)
                .join('');
            
            chatInput.value = transcript;
        };
        
        // Handle speech recognition end
        recognition.onend = function() {
            micButton.classList.remove('listening');
            isListening = false;
            
            // If there's text, automatically submit the form after a short delay
            if (chatInput.value.trim()) {
                setTimeout(() => {
                    // Trigger form submission
                    const event = new Event('submit', {
                        'bubbles': true,
                        'cancelable': true
                    });
                    chatForm.dispatchEvent(event);
                }, 500);
            }
        };
        
        // Handle speech recognition errors
        recognition.onerror = function(event) {
            console.error('Speech recognition error', event.error);
            micButton.classList.remove('listening');
            isListening = false;
            
            // Show error toast
            showToast('حدث خطأ في التعرف على الصوت', 'error');
        };
        
        // Add click event to mic button
        if (micButton) {
            micButton.addEventListener('click', function() {
                if (!isListening) {
                    // Start listening
                    recognition.start();
                    micButton.classList.add('listening');
                    isListening = true;
                    
                    // Show toast
                    showToast('جاري الاستماع... تحدث الآن', 'info');
                } else {
                    // Stop listening
                    recognition.stop();
                    micButton.classList.remove('listening');
                    isListening = false;
                }
            });
        }
    } else {
        // Hide mic button if speech recognition is not supported
        if (micButton) {
            micButton.style.display = 'none';
        }
    }
    
    // Add auto-typing detection for auto-send
    if (chatInput) {
        // On keyup, start the countdown
        chatInput.addEventListener('keyup', function() {
            // Only proceed if auto mode is enabled and input has text
            if (autoModeEnabled && chatInput.value.trim()) {
                clearTimeout(typingTimer);
                typingTimer = setTimeout(function() {
                    // Submit the form automatically when user stops typing
                    if (chatInput.value.trim()) {
                        chatForm.dispatchEvent(new Event('submit', {
                            'bubbles': true,
                            'cancelable': true
                        }));
                    }
                }, doneTypingInterval);
            }
        });
        
        // On keydown, clear the countdown
        chatInput.addEventListener('keydown', function() {
            clearTimeout(typingTimer);
        });
    }
    
    // Add event listener to chat form
    if (chatForm) {
        chatForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const messageText = chatInput.value.trim();
            if (!messageText) return;
            
            // Add user message to chat
            addUserMessage(messageText);
            
            // Clear input
            chatInput.value = '';
            
            // Clear any pending auto-send timers
            clearTimeout(typingTimer);
            
            // Show typing indicator
            showTypingIndicator();
            
            // Send message to server
            sendMessage(messageText);
        });
    }
    
    // Add event listeners to suggestion chips
    if (suggestedChips) {
        suggestedChips.forEach(chip => {
            chip.addEventListener('click', function() {
                const messageText = this.textContent.trim();
                
                // Add user message to chat
                addUserMessage(messageText);
                
                // Show typing indicator
                showTypingIndicator();
                
                // Send message to server
                sendMessage(messageText);
            });
        });
    }
    
    // Function to add user message to chat
    function addUserMessage(text) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message message-user';
        
        const currentTime = new Date();
        const timeString = currentTime.toLocaleTimeString('ar-SA', {
            hour: '2-digit',
            minute: '2-digit'
        });
        
        messageElement.innerHTML = `
            <div class="message-content">
                ${text}
                <span class="message-time">${timeString}</span>
            </div>
        `;
        
        messagesContainer.appendChild(messageElement);
        
        // Scroll to bottom
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    // Function to add assistant message to chat
    function addAssistantMessage(text, timestamp) {
        // Remove typing indicator if exists
        const typingIndicator = document.querySelector('.typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
        
        const messageElement = document.createElement('div');
        messageElement.className = 'message message-assistant';
        
        messageElement.innerHTML = `
            <div class="message-avatar">
                <img src="${assistantAvatar}" alt="Assistant">
            </div>
            <div class="message-content">
                ${text}
                <div class="message-footer">
                    <span class="message-time">${timestamp}</span>
                    <button class="speak-button" title="استماع للرد">
                        <i class="fas fa-volume-up"></i>
                    </button>
                </div>
            </div>
        `;
        
        messagesContainer.appendChild(messageElement);
        
        // Add click event to speak button
        const speakButton = messageElement.querySelector('.speak-button');
        if (speakButton) {
            speakButton.addEventListener('click', function() {
                speakText(text);
            });
        }
        
        // Scroll to bottom
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    // Function to speak text using browser's speech synthesis or ElevenLabs
    function speakText(text) {
        // First try using ElevenLabs API
        fetch('/api/text_to_speech', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                text: text,
                voice_id: localStorage.getItem('preferredVoice') || 'EXAVITQu4vr4xnSDxMaL' // Default to Adam voice
            }),
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success' && data.audio) {
                // Success with audio data
                showToast('جارٍ تشغيل الصوت...', 'info');
                
                // Create audio from base64
                const audioSrc = 'data:audio/mpeg;base64,' + data.audio;
                
                // Create and play audio
                const audio = new Audio(audioSrc);
                audio.play();
            } else {
                // Fall back to browser TTS
                useBrowserTTS(text);
            }
        })
        .catch(error => {
            console.error('Error using ElevenLabs:', error);
            // Fall back to browser TTS
            useBrowserTTS(text);
        });
    }
    
    // Fallback to browser's built-in speech synthesis
    function useBrowserTTS(text) {
        if ('speechSynthesis' in window) {
            // Show toast notification
            showToast('جارٍ استخدام المتصفح للنطق...', 'info');
            
            // Create utterance
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'ar-SA'; // Arabic
            utterance.rate = 0.9; // Slightly slower for better pronunciation
            utterance.pitch = 1.0; // Normal pitch
            utterance.volume = 1.0; // Full volume
            
            // Get available voices
            let voices = window.speechSynthesis.getVoices();
            
            // If voices array is empty, wait for voices to load (Chrome needs this)
            if (voices.length === 0) {
                window.speechSynthesis.onvoiceschanged = function() {
                    voices = window.speechSynthesis.getVoices();
                    setVoiceAndSpeak();
                };
            } else {
                setVoiceAndSpeak();
            }
            
            function setVoiceAndSpeak() {
                // Try to find Arabic voice
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
                }
                
                // Cancel any ongoing speech
                window.speechSynthesis.cancel();
                
                // Add event handlers for debugging
                utterance.onstart = () => console.log('Speech started');
                utterance.onend = () => console.log('Speech ended');
                utterance.onerror = (e) => console.error('Speech error:', e);
                
                // Speak the text
                window.speechSynthesis.speak(utterance);
            }
        } else {
            showToast('المتصفح لا يدعم ميزة تحويل النص إلى كلام', 'error');
        }
    }
    
    // Function to show typing indicator
    function showTypingIndicator() {
        const typingElement = document.createElement('div');
        typingElement.className = 'typing-indicator';
        typingElement.innerHTML = `
            <span></span>
            <span></span>
            <span></span>
        `;
        
        messagesContainer.appendChild(typingElement);
        
        // Scroll to bottom
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    // Function to send message to server
    function sendMessage(message) {
        fetch('/api/chat_message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                assistant_id: assistantId
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Add assistant response to chat
                setTimeout(() => {
                    addAssistantMessage(data.response, data.timestamp);
                }, 1000); // Small delay for realism
            } else {
                // Remove typing indicator
                const typingIndicator = document.querySelector('.typing-indicator');
                if (typingIndicator) {
                    typingIndicator.remove();
                }
                
                // Show error toast
                showToast('حدث خطأ أثناء إرسال الرسالة', 'error');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            
            // Remove typing indicator
            const typingIndicator = document.querySelector('.typing-indicator');
            if (typingIndicator) {
                typingIndicator.remove();
            }
            
            // Show error toast
            showToast('حدث خطأ في الاتصال بالخادم', 'error');
        });
    }
});
