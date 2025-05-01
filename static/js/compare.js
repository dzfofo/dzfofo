// Device comparison functionality
document.addEventListener("DOMContentLoaded", function() {
    const compareForm = document.getElementById('compare-form');
    const device1Input = document.getElementById('device1');
    const device2Input = document.getElementById('device2');
    const clearDevice1Btn = document.getElementById('clear-device1');
    const clearDevice2Btn = document.getElementById('clear-device2');
    const resultsContainer = document.getElementById('results');
    const loader = document.getElementById('loader');
    
    // Add event listener to compare form
    if (compareForm) {
        compareForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const device1 = device1Input.value.trim();
            const device2 = device2Input.value.trim();
            
            if (!device1 || !device2) {
                showToast('يرجى إدخال اسم الجهازين', 'error');
                return;
            }
            
            // Show loader
            loader.style.display = 'block';
            
            // Clear results
            resultsContainer.innerHTML = '';
            
            // Send comparison request to server
            compareDevices(device1, device2);
        });
    }
    
    // Clear button functionality
    if (clearDevice1Btn) {
        clearDevice1Btn.addEventListener('click', function() {
            device1Input.value = '';
            device1Input.focus();
        });
    }
    
    if (clearDevice2Btn) {
        clearDevice2Btn.addEventListener('click', function() {
            device2Input.value = '';
            device2Input.focus();
        });
    }
    
    // Example device chip click handler
    window.prefillDevice = function(element) {
        const deviceName = element.innerText;
        
        if (!device1Input.value) {
            device1Input.value = deviceName;
        } else if (!device2Input.value) {
            device2Input.value = deviceName;
        } else {
            // Both inputs are filled, replace the first one
            device1Input.value = deviceName;
        }
    };
    
    // Function to compare devices
    function compareDevices(device1, device2) {
        fetch('/api/compare_devices', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                device1: device1,
                device2: device2
            })
        })
        .then(response => response.json())
        .then(data => {
            // Hide loader
            loader.style.display = 'none';
            
            if (data.status === 'success') {
                // Display comparison results
                displayComparisonResults(data.device1, data.device2);
            } else {
                // Show error message
                resultsContainer.innerHTML = `
                    <div class="no-results">
                        <p class="error-message">${data.message || 'حدث خطأ أثناء مقارنة الأجهزة'}</p>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error:', error);
            
            // Hide loader
            loader.style.display = 'none';
            
            // Show error message
            resultsContainer.innerHTML = `
                <div class="no-results">
                    <p class="error-message">حدث خطأ في الاتصال بالخادم</p>
                </div>
            `;
            
            // Show error toast
            showToast('حدث خطأ في الاتصال بالخادم', 'error');
        });
    }
    
    // Function to compare specifications and determine which is better
    function compareBetterSpecs(spec1, spec2, type) {
        // For cases where we can't compare or both are unknown
        if (spec1 === 'غير معروف' || spec2 === 'غير معروف') {
            return { first: false, second: false };
        }
        
        switch (type) {
            case 'battery':
                // Extract numbers from battery strings (e.g. "5000 mAh")
                const batteryMatch1 = spec1 ? spec1.match(/\d+/) : null;
                const batteryMatch2 = spec2 ? spec2.match(/\d+/) : null;
                const battery1 = batteryMatch1 ? parseInt(batteryMatch1[0]) : 0;
                const battery2 = batteryMatch2 ? parseInt(batteryMatch2[0]) : 0;
                if (!isNaN(battery1) && !isNaN(battery2)) {
                    return { 
                        first: battery1 > battery2, 
                        second: battery2 > battery1 
                    };
                }
                break;
                
            case 'ram':
                // Extract GB values
                const ramMatch1 = spec1 ? spec1.match(/\d+/) : null;
                const ramMatch2 = spec2 ? spec2.match(/\d+/) : null;
                const ram1 = ramMatch1 ? parseInt(ramMatch1[0]) : 0;
                const ram2 = ramMatch2 ? parseInt(ramMatch2[0]) : 0;
                if (!isNaN(ram1) && !isNaN(ram2)) {
                    return { 
                        first: ram1 > ram2, 
                        second: ram2 > ram1 
                    };
                }
                break;
                
            case 'processor':
                // Cannot easily compare processors, would need a database of benchmarks
                return { first: false, second: false };
                
            case 'camera':
                // Extract the first megapixel value which is typically the main camera
                const mpMatch1 = spec1 ? spec1.match(/\d+/) : null;
                const mpMatch2 = spec2 ? spec2.match(/\d+/) : null;
                const mp1 = mpMatch1 ? parseInt(mpMatch1[0]) : 0;
                const mp2 = mpMatch2 ? parseInt(mpMatch2[0]) : 0;
                if (!isNaN(mp1) && !isNaN(mp2)) {
                    return { 
                        first: mp1 > mp2, 
                        second: mp2 > mp1 
                    };
                }
                break;
                
            case 'network':
                // 5G is better than 4G is better than 3G
                const net1Value = spec1 && typeof spec1 === 'string' && spec1.includes('5G') ? 3 : 
                                 (spec1 && typeof spec1 === 'string' && spec1.includes('4G') ? 2 : 1);
                const net2Value = spec2 && typeof spec2 === 'string' && spec2.includes('5G') ? 3 : 
                                 (spec2 && typeof spec2 === 'string' && spec2.includes('4G') ? 2 : 1);
                return { 
                    first: net1Value > net2Value, 
                    second: net2Value > net1Value 
                };
                
            default:
                return { first: false, second: false };
        }
        
        return { first: false, second: false };
    }
    
    // Function to generate a comparison summary for text-to-speech
    function generateComparisonSummary(device1, device2) {
        // Start with basic intro
        let summary = `مقارنة بين ${device1.name} و ${device2.name}. `;
        
        // Add main specifications
        summary += `${device1.name} يأتي بـ: شاشة ${device1.display}، معالج ${device1.processor}، ذاكرة ${device1.ram}، كاميرا ${device1.camera}، وبطارية ${device1.battery}. `;
        summary += `أما ${device2.name} فيأتي بـ: شاشة ${device2.display}، معالج ${device2.processor}، ذاكرة ${device2.ram}، كاميرا ${device2.camera}، وبطارية ${device2.battery}. `;
        
        // Add additional specs if available
        if (device1.network !== 'غير معروف' || device2.network !== 'غير معروف') {
            summary += `بالنسبة لدعم الشبكات، ${device1.name} يدعم ${device1.network || 'غير معروف'}، و${device2.name} يدعم ${device2.network || 'غير معروف'}. `;
        }
        
        if (device1.nfc !== 'غير معروف' || device2.nfc !== 'غير معروف') {
            summary += `${device1.name} ${device1.nfc === 'نعم' ? 'يدعم' : 'لا يدعم'} تقنية NFC، و${device2.name} ${device2.nfc === 'نعم' ? 'يدعم' : 'لا يدعم'} هذه التقنية. `;
        }
        
        if (device1.fast_charging !== 'غير معروف' || device2.fast_charging !== 'غير معروف') {
            summary += `${device1.name} ${device1.fast_charging === 'نعم' ? 'يدعم' : 'لا يدعم'} الشحن السريع، و${device2.name} ${device2.fast_charging === 'نعم' ? 'يدعم' : 'لا يدعم'} هذه الميزة. `;
        }
        
        // Add price comparison if available
        if (device1.price !== 'غير معروف' && device2.price !== 'غير معروف') {
            summary += `سعر ${device1.name} حوالي ${device1.price}، بينما سعر ${device2.name} حوالي ${device2.price}. `;
        }
        
        return summary;
    }
    
    // Function to display comparison results
    function displayComparisonResults(device1, device2) {
        // Create comparison summary for speech
        const comparisonSummary = generateComparisonSummary(device1, device2);
        
        // Compare specs to highlight better ones
        const batteryComparison = compareBetterSpecs(device1.battery, device2.battery, 'battery');
        const ramComparison = compareBetterSpecs(device1.ram, device2.ram, 'ram');
        const cameraComparison = compareBetterSpecs(device1.camera, device2.camera, 'camera');
        const networkComparison = compareBetterSpecs(device1.network, device2.network, 'network');
        
        // Determine if images are available
        const fallbackImgUrl = 'https://images.unsplash.com/photo-1551355738-21e3c5640bd4?q=80&w=880&auto=format&fit=crop';
        const device1Image = device1.image && device1.image !== 'غير معروف' ? 
            `<img src="${device1.image}" alt="${device1.name}" onerror="this.onerror=null; this.src='${fallbackImgUrl}'; this.alt='صورة هاتف بديلة'">` : 
            `<i class="fas fa-mobile-alt"></i>`;
            
        const device2Image = device2.image && device2.image !== 'غير معروف' ? 
            `<img src="${device2.image}" alt="${device2.name}" onerror="this.onerror=null; this.src='${fallbackImgUrl}'; this.alt='صورة هاتف بديلة'">` : 
            `<i class="fas fa-mobile-alt"></i>`;
        
        resultsContainer.innerHTML = `
            <div class="comparison-wrapper">
                <div class="comparison-header">
                    <h2>نتائج المقارنة</h2>
                    <button id="speak-comparison" class="speak-button" title="استماع للنتائج">
                        <i class="fas fa-volume-up"></i> استماع للمقارنة
                    </button>
                </div>
                
                <div class="comparison-content">
                    <div class="device-box">
                        <div class="device-image">
                            ${device1Image}
                        </div>
                        <h3>${device1.name}</h3>
                        <ul class="device-specs">
                            <li><span class="spec-name">الشركة المصنعة:</span> <span class="spec-value">${device1.brand}</span></li>
                            <li><span class="spec-name">نظام التشغيل:</span> <span class="spec-value">${device1.os}</span></li>
                            <li><span class="spec-name">الشاشة:</span> <span class="spec-value">${device1.display}</span></li>
                            <li><span class="spec-name">المعالج:</span> <span class="spec-value">${device1.processor}</span></li>
                            <li><span class="spec-name">الذاكرة العشوائية:</span> <span class="spec-value ${ramComparison.first ? 'better-spec' : ''}">${device1.ram}</span></li>
                            <li><span class="spec-name">التخزين:</span> <span class="spec-value">${device1.storage || 'غير معروف'}</span></li>
                            <li><span class="spec-name">الكاميرا:</span> <span class="spec-value ${cameraComparison.first ? 'better-spec' : ''}">${device1.camera}</span></li>
                            <li><span class="spec-name">البطارية:</span> <span class="spec-value ${batteryComparison.first ? 'better-spec' : ''}">${device1.battery}</span></li>
                            <li><span class="spec-name">شبكة الاتصال:</span> <span class="spec-value ${networkComparison.first ? 'better-spec' : ''}">${device1.network || 'غير معروف'}</span></li>
                            <li><span class="spec-name">NFC:</span> <span class="spec-value">${device1.nfc || 'غير معروف'}</span></li>
                            <li><span class="spec-name">الشحن السريع:</span> <span class="spec-value">${device1.fast_charging || 'غير معروف'}</span></li>
                            <li><span class="spec-name">تاريخ الإصدار:</span> <span class="spec-value">${device1.release_date || 'غير معروف'}</span></li>
                            <li><span class="spec-name">السعر التقريبي:</span> <span class="spec-value">${device1.price || 'غير معروف'}</span></li>
                            <li><span class="spec-name">التقييم:</span> <span class="spec-value">${device1.rating || 'غير معروف'}</span></li>
                        </ul>
                    </div>
                    <div class="device-box">
                        <div class="device-image">
                            ${device2Image}
                        </div>
                        <h3>${device2.name}</h3>
                        <ul class="device-specs">
                            <li><span class="spec-name">الشركة المصنعة:</span> <span class="spec-value">${device2.brand}</span></li>
                            <li><span class="spec-name">نظام التشغيل:</span> <span class="spec-value">${device2.os}</span></li>
                            <li><span class="spec-name">الشاشة:</span> <span class="spec-value">${device2.display}</span></li>
                            <li><span class="spec-name">المعالج:</span> <span class="spec-value">${device2.processor}</span></li>
                            <li><span class="spec-name">الذاكرة العشوائية:</span> <span class="spec-value ${ramComparison.second ? 'better-spec' : ''}">${device2.ram}</span></li>
                            <li><span class="spec-name">التخزين:</span> <span class="spec-value">${device2.storage || 'غير معروف'}</span></li>
                            <li><span class="spec-name">الكاميرا:</span> <span class="spec-value ${cameraComparison.second ? 'better-spec' : ''}">${device2.camera}</span></li>
                            <li><span class="spec-name">البطارية:</span> <span class="spec-value ${batteryComparison.second ? 'better-spec' : ''}">${device2.battery}</span></li>
                            <li><span class="spec-name">شبكة الاتصال:</span> <span class="spec-value ${networkComparison.second ? 'better-spec' : ''}">${device2.network || 'غير معروف'}</span></li>
                            <li><span class="spec-name">NFC:</span> <span class="spec-value">${device2.nfc || 'غير معروف'}</span></li>
                            <li><span class="spec-name">الشحن السريع:</span> <span class="spec-value">${device2.fast_charging || 'غير معروف'}</span></li>
                            <li><span class="spec-name">تاريخ الإصدار:</span> <span class="spec-value">${device2.release_date || 'غير معروف'}</span></li>
                            <li><span class="spec-name">السعر التقريبي:</span> <span class="spec-value">${device2.price || 'غير معروف'}</span></li>
                            <li><span class="spec-name">التقييم:</span> <span class="spec-value">${device2.rating || 'غير معروف'}</span></li>
                        </ul>
                    </div>
                </div>
                
                <div class="comparison-summary">
                    <h3>خلاصة المقارنة</h3>
                    <p>تمت المقارنة بين ${device1.name} و ${device2.name} باستخدام بيانات الهاتف المتاحة. المواصفات المميزة بعلامة (✓) تشير إلى أفضلية في تلك الخاصية.</p>
                </div>
            </div>
        `;
        
        // Add event listener to speak button
        const speakButton = document.getElementById('speak-comparison');
        if (speakButton) {
            speakButton.addEventListener('click', function() {
                speakText(comparisonSummary);
            });
        }
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
                showToast('جارٍ تشغيل المقارنة الصوتية...', 'info');
                
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
}
});
