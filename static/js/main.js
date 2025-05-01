// Main JavaScript functionality for the application
document.addEventListener("DOMContentLoaded", function() {
    // Initialize theme based on user preference or system setting
    initializeTheme();
    
    // Initialize toast container
    if (!document.getElementById('toast-container')) {
        const toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        document.body.appendChild(toastContainer);
    }
    
    // Add event listener to theme toggle button if it exists
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
    
    // Add event listener to logout button if it exists
    const logoutButton = document.getElementById('logout-button');
    if (logoutButton) {
        logoutButton.addEventListener('click', logout);
    }
});

// Function to initialize theme based on user preference or system setting
function initializeTheme() {
    const savedTheme = localStorage.getItem('theme');
    
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-mode');
        updateThemeIcon('dark');
    } else if (savedTheme === 'light') {
        document.body.classList.remove('dark-mode');
        updateThemeIcon('light');
    } else {
        // Check system preference
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            document.body.classList.add('dark-mode');
            updateThemeIcon('dark');
        } else {
            document.body.classList.remove('dark-mode');
            updateThemeIcon('light');
        }
    }
}

// Function to toggle between light and dark theme
function toggleTheme() {
    if (document.body.classList.contains('dark-mode')) {
        document.body.classList.remove('dark-mode');
        localStorage.setItem('theme', 'light');
        updateThemeIcon('light');
    } else {
        document.body.classList.add('dark-mode');
        localStorage.setItem('theme', 'dark');
        updateThemeIcon('dark');
    }
}

// Function to update theme icon based on current theme
function updateThemeIcon(theme) {
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        if (theme === 'dark') {
            themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
        } else {
            themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
        }
    }
}

// Function to show toast notifications
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) return;
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = message;
    
    toastContainer.appendChild(toast);
    
    // Add visible class for animation
    setTimeout(() => {
        toast.classList.add('visible');
    }, 10);
    
    // Remove toast after duration
    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3000);
}

// Function to handle user logout
function logout() {
    fetch('/api/logout', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            window.location.href = data.redirect;
        } else {
            showToast('حدث خطأ أثناء تسجيل الخروج', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('حدث خطأ في الاتصال بالخادم', 'error');
    });
}

// Function to get first name initial for avatar
function getInitials(name) {
    if (!name) return '';
    return name.trim().charAt(0).toUpperCase();
}
