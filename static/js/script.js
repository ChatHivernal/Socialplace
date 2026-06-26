if (window.trustedTypes && trustedTypes.createPolicy) {
    trustedTypes.createPolicy('default', {
        createHTML: function (string) {
            return DOMPurify.sanitize(string, { RETURN_TRUSTED_TYPE: true });
        }
    });
}

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
}

const csrfToken = getCookie('csrf_token');

document.addEventListener('DOMContentLoaded', function () {
    console.log('Nyapi initialisé');

    // ===== Menu burger mobile =====
    var navToggle = document.querySelector('.nav-toggle');
    if (navToggle) {
        navToggle.addEventListener('click', function (e) {
            e.preventDefault();
            console.log('Burger cliqué');
            var navLeft = document.querySelector('.nav-left');
            var navRight = document.querySelector('.nav-right');
            var mobileMenu = document.querySelector('.mobile-menu');
            if (navLeft) navLeft.classList.toggle('active');
            if (navRight) navRight.classList.toggle('active');
            if (mobileMenu) mobileMenu.classList.toggle('active');
        });
    } else {
        console.warn('.nav-toggle introuvable dans le DOM');
    }

    // ----- Initialisation des autres modules -----
    setupLikes();
    setupReplies();
    setupTextareas();
    setupSearch();
    setupChat();
    setupComments();
    setupConfirmations();
    setupPreviews();
    setupScroll();
    setupNotifications();
});

function setupLikes() {
    document.addEventListener('click', function (e) {
        if (e.target.closest('.like-btn')) {
            e.preventDefault();
            likePost(e.target.closest('.like-btn'));
        }
        if (e.target.closest('.dislike-btn')) {
            e.preventDefault();
            dislikePost(e.target.closest('.dislike-btn'));
        }
    });
}

async function likePost(btn) {
    const postId = btn.dataset.postId;
    const dislikeBtn = document.querySelector(`.dislike-btn[data-post-id="${postId}"]`);
    try {
        const response = await fetch(`/like_post/${postId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRF-Token': csrfToken
            }
        });
        const data = await response.json();
        btn.querySelector('.like-count').textContent = data.likes;
        btn.classList.toggle('liked', data.liked);
        if (dislikeBtn) {
            dislikeBtn.querySelector('.dislike-count').textContent = data.dislikes;
            dislikeBtn.classList.toggle('disliked', data.disliked);
        }
        btn.querySelector('i').style.transform = 'scale(1.3)';
        setTimeout(() => btn.querySelector('i').style.transform = 'scale(1)', 300);
    } catch (error) {
        showMessage('Error liking post', 'error');
    }
}

async function dislikePost(btn) {
    const postId = btn.dataset.postId;
    const likeBtn = document.querySelector(`.like-btn[data-post-id="${postId}"]`);
    try {
        const response = await fetch(`/dislike_post/${postId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRF-Token': csrfToken
            }
        });
        const data = await response.json();
        btn.querySelector('.dislike-count').textContent = data.dislikes;
        btn.classList.toggle('disliked', data.disliked);
        if (likeBtn) {
            likeBtn.querySelector('.like-count').textContent = data.likes;
            likeBtn.classList.toggle('liked', data.liked);
        }
        btn.querySelector('i').style.transform = 'scale(1.3)';
        setTimeout(() => btn.querySelector('i').style.transform = 'scale(1)', 300);
    } catch (error) {
        showMessage('Error disliking post', 'error');
    }
}

function setupReplies() {
    document.addEventListener('click', function (e) {
        if (e.target.closest('.reply-btn')) {
            const btn = e.target.closest('.reply-btn');
            const form = document.getElementById(`reply-form-${btn.dataset.commentId}`);
            if (form) {
                form.style.display = form.style.display === 'block' ? 'none' : 'block';
                if (form.style.display === 'block') form.querySelector('textarea').focus();
            }
        }
        if (e.target.closest('.cancel-reply')) {
            const btn = e.target.closest('.cancel-reply');
            const form = document.getElementById(`reply-form-${btn.dataset.commentId}`);
            if (form) form.style.display = 'none';
        }
    });
}

function setupTextareas() {
    document.querySelectorAll('textarea').forEach(ta => {
        ta.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = this.scrollHeight + 'px';
        });
        ta.style.height = 'auto';
        ta.style.height = ta.scrollHeight + 'px';
    });
}

function setupSearch() {
    const input = document.querySelector('.search-input');
    if (!input) return;
    input.addEventListener('focus', () => input.style.width = '250px');
    input.addEventListener('blur', function () {
        if (!this.value) this.style.width = '200px';
        hideSearch();
    });
}

function hideSearch() {
    const dropdown = document.querySelector('.search-results-dropdown');
    if (dropdown) dropdown.classList.remove('show');
}

function setupChat() {
    const form = document.getElementById('chat-form');
    if (!form) return;
    const textarea = form.querySelector('textarea');
    const button = form.querySelector('button[type="submit"]');
    button.type = 'button';
    textarea.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    button.addEventListener('click', function (e) {
        e.preventDefault();
        sendMessage();
    });
    async function sendMessage() {
        const content = textarea.value.trim();
        if (!content) return;
        const original = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        button.disabled = true;
        textarea.disabled = true;
        try {
            const url = form.getAttribute('data-action') || window.location.pathname;
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRF-Token': csrfToken
                },
                body: 'content=' + encodeURIComponent(content)
            });
            const data = await response.json();
            if (data.success) {
                textarea.value = '';
                textarea.style.height = 'auto';
                addMessage({
                    id: data.message_id || 'temp_' + Date.now(),
                    content: content,
                    created_at: new Date().toISOString(),
                    sent_by_current_user: true
                });
                showMessage('Message sent!', 'success');
            } else {
                showMessage(data.error || 'Failed to send message', 'error');
            }
        } catch (error) {
            showMessage('Failed to send message', 'error');
        } finally {
            button.innerHTML = original;
            button.disabled = false;
            textarea.disabled = false;
            textarea.focus();
        }
    }
    if (window.location.pathname.includes('/messages/')) {
        setInterval(refreshChat, 2000);
    }
}

function refreshChat() {
    const chat = document.getElementById('chat-messages');
    if (!chat) return;
    const messages = chat.querySelectorAll('.message[data-message-id]');
    let lastId = 0;
    messages.forEach(msg => {
        const id = parseInt(msg.dataset.messageId) || 0;
        if (id > lastId) lastId = id;
    });
    const match = window.location.pathname.match(/\/messages\/(\d+)/);
    if (!match) return;
    fetch(`/get_new_messages?last_id=${lastId}&user_id=${match[1]}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
        .then(r => r.json())
        .then(data => {
            if (data.messages) {
                data.messages.forEach(msg => {
                    if (!document.querySelector(`[data-message-id="${msg.id}"]`)) {
                        addMessage(msg);
                    }
                });
            }
        })
        .catch(e => console.error('Refresh error:', e));
}

function parseServerDate(dateStr) {
    if (!dateStr) return new Date();
    const iso = dateStr.replace(' ', 'T') + 'Z';
    const d = new Date(iso);
    return isNaN(d) ? new Date() : d;
}

function addMessage(msg) {
    const chat = document.getElementById('chat-messages');
    if (!chat) {
        console.error('#chat-messages introuvable dans le DOM');
        return;
    }

    const div = document.createElement('div');
    div.className = `message ${msg.sent_by_current_user ? 'sent' : 'received'}`;
    div.dataset.messageId = msg.id;

    const date = parseServerDate(msg.created_at);
    const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    // Tentative d’insertion HTML sécurisé
    let sanitized;
    try {
        sanitized = DOMPurify.sanitize(msg.content, { RETURN_TRUSTED_TYPE: true });
    } catch (e) {
        console.error('DOMPurify erreur:', e);
    }

    if (sanitized) {
        try {
            contentDiv.innerHTML = sanitized;
        } catch (innerError) {
            console.error('innerHTML bloqué:', innerError);
            // Fallback : texte brut
            contentDiv.textContent = msg.content;
        }
    } else {
        contentDiv.textContent = msg.content;
    }

    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    timeDiv.textContent = time;

    div.appendChild(contentDiv);
    div.appendChild(timeDiv);
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;

    console.log('Message ajouté au chat:', msg.id, msg.content.substring(0, 30));
}

function setupComments() {
    document.querySelectorAll('.comment-form').forEach(form => {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            const textarea = this.querySelector('textarea');
            const content = textarea.value.trim();
            if (!content) return;
            const button = this.querySelector('button[type="submit"]');
            const original = button.innerHTML;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            button.disabled = true;
            fetch(this.action, {
                method: 'POST',
                body: new FormData(this),
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': csrfToken }
            })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showMessage('Comment added!', 'success');
                        setTimeout(() => location.reload(), 1000);
                    }
                })
                .catch(e => {
                    showMessage('Failed to add comment', 'error');
                })
                .finally(() => {
                    button.innerHTML = original;
                    button.disabled = false;
                });
        });
    });
}

function setupConfirmations() {
    document.querySelectorAll('form[onsubmit*="confirm"]').forEach(form => {
        form.addEventListener('submit', function (e) {
            if (!confirm('Are you sure?')) e.preventDefault();
        });
    });
}

function setupPreviews() {
    document.querySelectorAll('input[type="file"][accept*="image"]').forEach(input => {
        input.addEventListener('change', function () {
            if (this.files[0]) {
                const reader = new FileReader();
                reader.onload = function (e) {
                    const container = input.closest('.form-group');
                    if (!container) return;
                    const old = container.querySelector('.image-preview');
                    if (old) old.remove();
                    const preview = document.createElement('div');
                    preview.className = 'image-preview';
                    preview.innerHTML = '<img src="' + e.target.result + '" alt="Preview"><button type="button" class="remove-preview">&times;</button>';
                    container.appendChild(preview);
                    preview.querySelector('.remove-preview').addEventListener('click', function () {
                        preview.remove();
                        input.value = '';
                    });
                };
                reader.readAsDataURL(this.files[0]);
            }
        });
    });
}

function setupScroll() {
    const posts = document.querySelector('.posts-section');
    if (!posts || !posts.querySelector('.pagination')) return;
    let loading = false;
    let page = 1;
    window.addEventListener('scroll', function () {
        if (loading) return;
        if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 500) {
            loadMore();
        }
    });
    async function loadMore() {
        loading = true;
        page++;
        try {
            const url = new URL(window.location.href);
            url.searchParams.set('page', page);
            const response = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, 'text/html');
            const newPosts = doc.querySelector('.posts-section');
            if (newPosts) {
                newPosts.querySelectorAll('.post-card').forEach(card => {
                    posts.insertBefore(card, posts.querySelector('.pagination'));
                });
            }
        } catch (e) {
        } finally {
            loading = false;
        }
    }
}

function setupNotifications() {
    setInterval(checkUnread, 30000);
    checkUnread();
}

async function checkUnread() {
    try {
        const response = await fetch('/check_unread_messages', { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const data = await response.json();
        updateBadge(data.total_unread);
    } catch (error) {
    }
}

function updateBadge(count) {
    let badge = document.getElementById('unread-badge');
    if (count > 0) {
        if (!badge) {
            const link = document.querySelector('a[href*="messages"]');
            if (link) {
                badge = document.createElement('span');
                badge.id = 'unread-badge';
                badge.className = 'unread-badge';
                link.appendChild(badge);
            }
        }
        if (badge) {
            badge.textContent = count < 10 ? count : '9+';
            badge.style.display = 'block';
            if (count > (window.lastUnreadCount || 0)) playNotification();
        }
        document.title = count > 0 ? `(${count}) Socialplace` : 'Socialplace';
    } else {
        if (badge) badge.style.display = 'none';
        document.title = 'Socialplace';
    }
    window.lastUnreadCount = count;
}

function playNotification() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        oscillator.frequency.value = 800;
        oscillator.type = 'sine';
        const now = audioContext.currentTime;
        gainNode.gain.setValueAtTime(0, now);
        gainNode.gain.linearRampToValueAtTime(0.3, now + 0.05);
        gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
        oscillator.start(now);
        oscillator.stop(now + 0.3);
    } catch (e) {
        if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
    }
}

function showMessage(text, type) {
    const msg = document.createElement('div');
    msg.className = `notification notification-${type}`;
    msg.innerHTML = `<span>${text}</span><button class="notification-close">&times;</button>`;
    document.body.appendChild(msg);
    setTimeout(() => msg.classList.add('show'), 10);
    msg.querySelector('.notification-close').addEventListener('click', () => {
        msg.classList.remove('show');
        setTimeout(() => msg.remove(), 300);
    });
    setTimeout(() => {
        msg.classList.remove('show');
        setTimeout(() => msg.remove(), 300);
    }, 5000);
}

document.querySelector('.nav-toggle')?.addEventListener('click', () => {
    document.querySelector('.nav-left')?.classList.toggle('active');
    document.querySelector('.nav-right')?.classList.toggle('active');
});

document.querySelector('.nav-toggle')?.addEventListener('click', () => {
    document.querySelector('.mobile-menu')?.classList.toggle('active');
});
