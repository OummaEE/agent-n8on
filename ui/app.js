const chat = document.getElementById('chat');
const messages = document.getElementById('messages');
const input = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const welcome = document.getElementById('welcome');
const statusEl = document.getElementById('status');
const statusText = document.getElementById('statusText');

let isWaiting = false;

input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 200) + 'px';
});

input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

async function checkStatus() {
    try {
        const r = await fetch('http://localhost:5000/api/status');
        const data = await r.json();
        if (data.ollama) {
            statusEl.className = 'status-badge connected';
            statusText.textContent = data.model || 'Connected';
        } else {
            statusEl.className = 'status-badge disconnected';
            statusText.textContent = 'Ollama offline';
        }
    } catch {
        statusEl.className = 'status-badge disconnected';
        statusText.textContent = 'Backend offline';
    }
}

checkStatus();
setInterval(checkStatus, 30000);

// Listen for backend-ready event from Tauri (sent after installer completes)
if (window.__TAURI__) {
    window.__TAURI__.event.listen('backend-ready', function(event) {
        if (event.payload) {
            checkStatus();
        } else {
            showBackendError();
        }
    });
}

function showBackendError() {
    statusEl.className = 'status-badge disconnected';
    statusText.textContent = 'Backend offline';

    const existingBanner = document.getElementById('backend-error-banner');
    if (existingBanner) return;

    const banner = document.createElement('div');
    banner.id = 'backend-error-banner';
    banner.style.cssText = 'background:#2a1010;border:1px solid #c0392b;border-radius:8px;padding:12px 16px;margin:8px 0;color:#e74c3c;font-size:14px;display:flex;align-items:center;gap:10px;';

    const msg = document.createElement('span');
    msg.textContent = 'Backend not responding. Taking longer than expected...';

    const retryBtn = document.createElement('button');
    retryBtn.textContent = 'Retry';
    retryBtn.style.cssText = 'margin-left:auto;padding:4px 12px;background:#c0392b;color:#fff;border:none;border-radius:4px;cursor:pointer;';
    retryBtn.addEventListener('click', async () => {
        retryBtn.disabled = true;
        retryBtn.textContent = 'Restarting...';
        try {
            const ok = await window.__TAURI__.tauri.invoke('restart_backend');
            if (ok) {
                banner.remove();
                checkStatus();
            } else {
                retryBtn.disabled = false;
                retryBtn.textContent = 'Retry';
                msg.textContent = 'Still not responding. Check if Python is installed.';
            }
        } catch (e) {
            retryBtn.disabled = false;
            retryBtn.textContent = 'Retry';
        }
    });

    banner.appendChild(msg);
    banner.appendChild(retryBtn);

    const chatEl = document.getElementById('chat');
    if (chatEl && chatEl.parentNode) {
        chatEl.parentNode.insertBefore(banner, chatEl);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function addMessage(role, content, toolName, toolResult, thinking) {
    if (welcome) welcome.style.display = 'none';

    const msg = document.createElement('div');
    msg.className = 'message ' + role;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? 'U' : 'n8';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const nameDiv = document.createElement('div');
    nameDiv.className = 'name';
    nameDiv.textContent = role === 'user' ? 'User' : 'Agent';
    contentDiv.appendChild(nameDiv);

    if (thinking) {
        const thinkDiv = document.createElement('div');
        thinkDiv.className = 'thinking';
        thinkDiv.textContent = thinking;
        contentDiv.appendChild(thinkDiv);
    }

    if (content) {
        const textDiv = document.createElement('div');
        textDiv.className = 'text';
        textDiv.textContent = content;
        contentDiv.appendChild(textDiv);
    }

    if (toolName && toolName !== 'chat') {
        const toolBlock = document.createElement('div');
        toolBlock.className = 'tool-block';
        const toolHeader = document.createElement('div');
        toolHeader.className = 'tool-header';
        const iconSpan = document.createElement('span');
        iconSpan.className = 'tool-icon';
        iconSpan.textContent = String.fromCodePoint(0x1F527);
        const nameSpan = document.createElement('span');
        nameSpan.textContent = toolName || '';
        toolHeader.appendChild(iconSpan);
        toolHeader.appendChild(nameSpan);
        const toolBody = document.createElement('div');
        toolBody.className = 'tool-body';
        toolBody.textContent = toolResult || '';
        toolBlock.appendChild(toolHeader);
        toolBlock.appendChild(toolBody);
        contentDiv.appendChild(toolBlock);
    }

    msg.appendChild(avatar);
    msg.appendChild(contentDiv);
    messages.appendChild(msg);
    chat.scrollTop = chat.scrollHeight;
}

function addTyping() {
    const msg = document.createElement('div');
    msg.className = 'message assistant';
    msg.id = 'typing';
    const av = document.createElement('div');
    av.className = 'message-avatar';
    av.textContent = 'n8';
    const ct = document.createElement('div');
    ct.className = 'message-content';
    const nm = document.createElement('div');
    nm.className = 'name';
    nm.textContent = 'Agent';
    const ti = document.createElement('div');
    ti.className = 'typing-indicator';
    for (let i = 0; i < 3; i++) {
        const d = document.createElement('div');
        d.className = 'typing-dot';
        ti.appendChild(d);
    }
    ct.appendChild(nm);
    ct.appendChild(ti);
    msg.appendChild(av);
    msg.appendChild(ct);
    messages.appendChild(msg);
    chat.scrollTop = chat.scrollHeight;
}

function removeTyping() {
    const el = document.getElementById('typing');
    if (el) el.remove();
}

function sendQuick(text) {
    input.value = text;
    sendMessage();
}

async function sendMessage() {
    const text = input.value.trim();
    if (!text || isWaiting) return;

    isWaiting = true;
    sendBtn.disabled = true;
    input.value = '';
    input.style.height = 'auto';

    addMessage('user', text);
    addTyping();

    try {
        const resp = await fetch('http://localhost:5000/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: text})
        });
        const data = await resp.json();
        removeTyping();

        if (data.response) {
            addMessage('assistant', data.response, data.tool_name, data.tool_result, data.thinking);
        } else if (data.tool_result) {
            addMessage('assistant', null, data.tool_name, data.tool_result, data.thinking);
        } else {
            addMessage('assistant', data.raw || 'No response');
        }
    } catch (err) {
        removeTyping();
        addMessage('assistant', 'Connection error: ' + err.message);
    }

    isWaiting = false;
    sendBtn.disabled = false;
    input.focus();
}

async function clearHistory() {
    if (!confirm('Clear chat history?')) return;
    await fetch('http://localhost:5000/api/clear', {method: 'POST'});
    messages.textContent = '';
    if (welcome) welcome.style.display = '';
}

input.focus();
