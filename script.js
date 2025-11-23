class DocumentQAApp {
    constructor() {
        this.currentSessionId = null;
        this.chatMessages = [];
        this.isDarkMode = localStorage.getItem('darkMode') === 'true';
        this.currentQueryAbortController = null;
        
        this.initializeApp();
        this.setupEventListeners();
        this.checkSystemStatus();
    }

    initializeApp() {
        this.applyTheme(this.isDarkMode);
        this.updateUIState();
        this.loadAvailableIndexes();
        this.updateMessageCount();
    }

    setupEventListeners() {
        document.getElementById('documentUpload').addEventListener('change', (e) => this.handleFileSelection(e));
        document.getElementById('uploadBtn').addEventListener('click', () => this.uploadDocuments());
        document.getElementById('showIndexesBtn').addEventListener('click', () => this.toggleIndexesList());
        document.getElementById('changeIndexBtn').addEventListener('click', () => this.showIndexSelection());
        document.getElementById('askButton').addEventListener('click', () => this.askQuestion());
        document.getElementById('questionInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.askQuestion();
            }
        });
        document.getElementById('clearSessionBtn').addEventListener('click', () => this.clearCurrentSession());
        document.getElementById('exportChatBtn').addEventListener('click', () => this.exportChat());
        document.getElementById('refreshStatusBtn').addEventListener('click', () => this.refreshSystemStatus());
        document.getElementById('toggleDarkMode').addEventListener('click', () => this.toggleDarkMode());
        document.querySelector('.close-button').addEventListener('click', () => this.closeCorrectionModal());
        document.getElementById('submitCorrectionBtn').addEventListener('click', () => this.submitCorrection());
        document.getElementById('stopUploadBtn').addEventListener('click', () => this.stopUpload());
        document.getElementById('stopQueryBtn').addEventListener('click', () => this.stopQuery());
        
        document.getElementById('correctionModal').addEventListener('click', (e) => {
            if (e.target.id === 'correctionModal') this.closeCorrectionModal();
        });
        
        document.getElementById('setupModal').addEventListener('click', (e) => {
            if (e.target.id === 'setupModal') this.closeSetupModal();
        });
        
        document.getElementById('questionInput').addEventListener('input', () => this.updateAskButtonState());
    }

    async checkSystemStatus() {
        try {
            const response = await fetch('/system_status');
            const data = await response.json();
            
            this.updateSystemStatusUI(data);
            
            if (!data.system_ready) {
                this.showSystemAlert(data.environment_issues);
            }
        } catch (error) {
            console.error('System status check failed:', error);
            this.updateSystemStatus('System status check failed', 'error');
        }
    }

    updateSystemStatusUI(data) {
        const statusElement = document.getElementById('systemStatus');
        const statusText = data.system_ready ? 'All systems ready' : 'System issues detected';
        const statusClass = data.system_ready ? 'status-success' : 'status-error';
        
        statusElement.textContent = statusText;
        statusElement.className = `system-status ${statusClass}`;
    }

    showSystemAlert(issues) {
        const alertElement = document.getElementById('systemAlert');
        const alertMessage = document.getElementById('alertMessage');
        
        alertMessage.textContent = issues.join(', ');
        alertElement.classList.remove('hidden');
    }

    hideSystemAlert() {
        document.getElementById('systemAlert').classList.add('hidden');
    }

    async refreshSystemStatus() {
        this.showLoading('Checking system status...', 'general');
        await this.checkSystemStatus();
        this.hideLoading();
        this.showStatus('System status refreshed', 'success');
    }

    handleFileSelection(event) {
        const files = event.target.files;
        const fileNameDisplay = document.getElementById('fileNameDisplay');
        const uploadBtn = document.getElementById('uploadBtn');
        
        if (files.length > 0) {
            const fileNames = Array.from(files).map(file => file.name).join(', ');
            fileNameDisplay.textContent = `${files.length} file(s) selected: ${fileNames}`;
            uploadBtn.disabled = false;
        } else {
            fileNameDisplay.textContent = 'No files selected';
            uploadBtn.disabled = true;
        }
    }

    async uploadDocuments() {
        const files = document.getElementById('documentUpload').files;
        if (files.length === 0) {
            this.showStatus('Please select PDF files to upload', 'error');
            return;
        }

        this.showLoading('Uploading and processing documents...', 'upload');
        
        const formData = new FormData();
        for (let file of files) {
            formData.append('files', file);
        }

        try {
            const response = await fetch('/uploads', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            
            if (response.ok) {
                this.currentSessionId = data.session_id;
                this.showStatus(`Successfully uploaded ${data.documents.length} document(s). Processing in background...`, 'success');
                this.updateUIState();
                this.waitForIndexingCompletion(data.session_id);
            } else {
                throw new Error(data.error || 'Upload failed');
            }
        } catch (error) {
            this.showStatus(`Upload error: ${error.message}`, 'error');
            console.error('Upload error:', error);
        } finally {
            this.hideLoading();
        }
    }

    async waitForIndexingCompletion(sessionId) {
        const maxAttempts = 30;
        let attempts = 0;
        
        const checkIndex = async () => {
            attempts++;
            try {
                const response = await fetch('/current_index');
                const data = await response.json();
                
                if (data.has_loaded_index && data.current_files.length > 0) {
                    this.showStatus('Documents processed and ready for questions!', 'success');
                    this.updateUIState();
                    this.loadAvailableIndexes();
                    return;
                }
                
                if (attempts < maxAttempts) {
                    setTimeout(checkIndex, 2000);
                } else {
                    this.showStatus('Document processing is taking longer than expected. You can try asking questions anyway.', 'warning');
                }
            } catch (error) {
                console.error('Error checking index status:', error);
                if (attempts < maxAttempts) {
                    setTimeout(checkIndex, 2000);
                }
            }
        };
        
        setTimeout(checkIndex, 2000);
    }

    async askQuestion() {
        const questionInput = document.getElementById('questionInput');
        const question = questionInput.value.trim();
        
        if (!question) {
            this.showStatus('Please enter a question', 'error');
            return;
        }

        if (!this.currentSessionId) {
            this.showStatus('Please upload documents or load an existing index first', 'error');
            return;
        }

        this.addMessageToChat('user', question);
        questionInput.value = '';
        this.updateAskButtonState();

        this.showLoading('Generating answer using local AI...', 'query');
        
        this.currentQueryAbortController = new AbortController();

        try {
            const response = await fetch('/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    question: question,
                    session_id: this.currentSessionId
                }),
                signal: this.currentQueryAbortController.signal
            });

            const data = await response.json();
            
            if (response.ok) {
                this.addMessageToChat('bot', data.response, question);
                this.showStatus('Answer generated successfully using local AI', 'success');
            } else {
                throw new Error(data.error || 'Failed to get answer');
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                this.addMessageToChat('system', 'Query was cancelled by user');
                this.showStatus('Query cancelled', 'warning');
            } else {
                this.addMessageToChat('bot', `Error: ${error.message}`);
                this.showStatus(`Error: ${error.message}`, 'error');
                console.error('Query error:', error);
            }
        } finally {
            this.hideLoading();
            this.currentQueryAbortController = null;
        }
    }

    addMessageToChat(type, content, originalQuestion = null) {
        const chatDisplay = document.getElementById('chatDisplay');
        const messageId = Date.now();
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;
        messageDiv.id = `message-${messageId}`;
        
        const timestamp = new Date().toLocaleTimeString();
        
        let headerContent = type === 'user' ? 'You' : 'Assistant';
        if (type === 'system') headerContent = 'System';
        
        messageDiv.innerHTML = `
            <div class="message-header">
                <span>${headerContent}</span>
                <span>${timestamp}</span>
            </div>
            <div class="message-content">${this.formatMessageContent(content)}</div>
            ${type === 'bot' && originalQuestion ? `
                <div class="message-actions">
                    <button class="correct-button" onclick="app.showCorrectionModal('${this.escapeHtml(originalQuestion)}', '${this.escapeHtml(content)}')">
                        ✏️ Correct Answer
                    </button>
                </div>
            ` : ''}
        `;
        
        const initialMessage = chatDisplay.querySelector('.initial-message');
        if (initialMessage) initialMessage.remove();
        
        chatDisplay.appendChild(messageDiv);
        chatDisplay.scrollTop = chatDisplay.scrollHeight;
        
        this.chatMessages.push({
            id: messageId,
            type: type,
            content: content,
            timestamp: timestamp
        });
        
        this.updateExportButtonVisibility();
        this.updateMessageCount();
    }

    formatMessageContent(content) {
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>')
            .replace(/```([^`]+)```/g, '<pre>$1</pre>');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async loadAvailableIndexes() {
        try {
            const response = await fetch('/list_indexes');
            const data = await response.json();
            
            this.renderIndexesList(data.indexes);
            this.updateCurrentIndexInfo(data);
        } catch (error) {
            console.error('Error loading indexes:', error);
        }
    }

    renderIndexesList(indexes) {
        const indexesList = document.getElementById('indexesList');
        
        if (indexes.length === 0) {
            indexesList.innerHTML = '<div class="no-indexes">No indexed documents found</div>';
            return;
        }
        
        indexesList.innerHTML = indexes.map(index => `
            <div class="index-item" data-session-id="${index.session_id}">
                <div class="index-header">
                    <strong>Session: ${index.session_id.slice(0, 8)}...</strong>
                    <span class="index-date">${new Date(index.created_at).toLocaleDateString()}</span>
                </div>
                <div class="index-files">
                    Files: ${index.files.join(', ')} (${index.paragraph_count} paragraphs)
                </div>
            </div>
        `).join('');
        
        indexesList.querySelectorAll('.index-item').forEach(item => {
            item.addEventListener('click', () => this.loadIndex(item.dataset.sessionId));
        });
    }

    async loadIndex(sessionId) {
        this.showLoading('Loading indexed documents...', 'upload');
        
        try {
            const response = await fetch('/load_index', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ session_id: sessionId })
            });

            const data = await response.json();
            
            if (response.ok) {
                this.currentSessionId = sessionId;
                this.showStatus('Index loaded successfully', 'success');
                this.updateUIState();
                this.loadAvailableIndexes();
            } else {
                throw new Error(data.error || 'Failed to load index');
            }
        } catch (error) {
            this.showStatus(`Error loading index: ${error.message}`, 'error');
            console.error('Load index error:', error);
        } finally {
            this.hideLoading();
        }
    }

    updateCurrentIndexInfo(data) {
        const currentIndexInfo = document.getElementById('currentIndexInfo');
        const noIndexInfo = document.getElementById('noIndexInfo');
        const currentFiles = document.getElementById('currentFiles');
        const paragraphCount = document.getElementById('paragraphCount');
        
        if (data.has_loaded_index && data.current_files.length > 0) {
            currentFiles.textContent = data.current_files.join(', ');
            paragraphCount.textContent = `${data.paragraph_count} paragraphs`;
            currentIndexInfo.classList.remove('hidden');
            noIndexInfo.classList.add('hidden');
        } else {
            currentIndexInfo.classList.add('hidden');
            noIndexInfo.classList.remove('hidden');
        }
    }

    updateUIState() {
        const hasSession = this.currentSessionId !== null;
        const askButton = document.getElementById('askButton');
        const clearSessionBtn = document.getElementById('clearSessionBtn');
        
        askButton.disabled = !hasSession;
        clearSessionBtn.classList.toggle('hidden', !hasSession);
        this.updateAskButtonState();
    }

    updateAskButtonState() {
        const questionInput = document.getElementById('questionInput');
        const askButton = document.getElementById('askButton');
        const hasText = questionInput.value.trim().length > 0;
        const hasSession = this.currentSessionId !== null;
        
        askButton.disabled = !hasText || !hasSession;
    }

    updateExportButtonVisibility() {
        const exportChatBtn = document.getElementById('exportChatBtn');
        const hasMessages = this.chatMessages.length > 0;
        exportChatBtn.classList.toggle('hidden', !hasMessages);
    }

    updateMessageCount() {
        const messageCount = document.getElementById('messageCount');
        messageCount.textContent = `${this.chatMessages.length} messages`;
    }

    clearCurrentSession() {
        this.currentSessionId = null;
        this.chatMessages = [];
        
        const chatDisplay = document.getElementById('chatDisplay');
        chatDisplay.innerHTML = `
            <div class="initial-message">
                <div class="welcome-icon">📄</div>
                <h3>Welcome to Document Q&A</h3>
                <p>Upload PDF documents or load existing indexed documents to start asking questions.</p>
                <div class="feature-list">
                    <div class="feature-item">
                        <span class="icon">🛡️</span>
                        <span>100% Offline Operation</span>
                    </div>
                    <div class="feature-item">
                        <span class="icon">⚡</span>
                        <span>Local AI Processing</span>
                    </div>
                    <div class="feature-item">
                        <span class="icon">🔒</span>
                        <span>Your Data Stays Local</span>
                    </div>
                </div>
            </div>
        `;
        
        this.updateUIState();
        this.loadAvailableIndexes();
        this.updateMessageCount();
        this.showStatus('Session cleared', 'info');
    }

    async exportChat() {
        if (this.chatMessages.length === 0) {
            this.showStatus('No chat messages to export', 'warning');
            return;
        }

        try {
            const response = await fetch('/export_chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: this.currentSessionId,
                    chat_messages: this.chatMessages
                })
            });

            const data = await response.json();
            
            if (response.ok) {
                const downloadResponse = await fetch(`/download_export/${data.filename}`);
                const blob = await downloadResponse.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = data.filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                
                this.showStatus('Chat exported successfully', 'success');
            } else {
                throw new Error(data.error || 'Export failed');
            }
        } catch (error) {
            this.showStatus(`Export error: ${error.message}`, 'error');
            console.error('Export error:', error);
        }
    }

    toggleIndexesList() {
        const indexesList = document.getElementById('indexesList');
        const showIndexesBtn = document.getElementById('showIndexesBtn');
        
        indexesList.classList.toggle('hidden');
        showIndexesBtn.innerHTML = indexesList.classList.contains('hidden') ? 
            '<span class="icon">🔍</span> Show Available Indexes' : 
            '<span class="icon">🔍</span> Hide Available Indexes';
    }

    showIndexSelection() {
        this.toggleIndexesList();
    }

    showCorrectionModal(originalQuestion, botAnswer) {
        document.getElementById('originalQuestionDisplay').textContent = originalQuestion;
        document.getElementById('botWrongAnswerDisplay').textContent = botAnswer;
        document.getElementById('correctedAnswerInput').value = '';
        document.getElementById('correctionModal').style.display = 'block';
    }

    closeCorrectionModal() {
        document.getElementById('correctionModal').style.display = 'none';
    }

    showSetupInstructions() {
        document.getElementById('setupModal').style.display = 'block';
    }

    closeSetupModal() {
        document.getElementById('setupModal').style.display = 'none';
    }

    submitCorrection() {
        const correctedAnswer = document.getElementById('correctedAnswerInput').value.trim();
        
        if (!correctedAnswer) {
            this.showStatus('Please enter a corrected answer', 'error');
            return;
        }

        console.log('Correction submitted:', {
            originalQuestion: document.getElementById('originalQuestionDisplay').textContent,
            botAnswer: document.getElementById('botWrongAnswerDisplay').textContent,
            correctedAnswer: correctedAnswer
        });

        this.showStatus('Correction submitted (logged to console)', 'success');
        this.closeCorrectionModal();
    }

    toggleDarkMode() {
        this.isDarkMode = !this.isDarkMode;
        localStorage.setItem('darkMode', this.isDarkMode);
        this.applyTheme(this.isDarkMode);
    }

    applyTheme(isDark) {
        document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
        
        const toggleButton = document.getElementById('toggleDarkMode');
        const themeIcon = document.getElementById('themeIcon');
        const themeText = document.getElementById('themeText');
        
        if (isDark) {
            themeIcon.textContent = '☀️';
            themeText.textContent = 'Light Mode';
        } else {
            themeIcon.textContent = '🌙';
            themeText.textContent = 'Dark Mode';
        }
    }

    showLoading(message, type = 'general') {
        const overlay = document.getElementById('overlay');
        const loadingMessage = document.getElementById('loadingMessage');
        const stopUploadBtn = document.getElementById('stopUploadBtn');
        const stopQueryBtn = document.getElementById('stopQueryBtn');
        
        loadingMessage.textContent = message;
        stopUploadBtn.classList.toggle('hidden', type !== 'upload');
        stopQueryBtn.classList.toggle('hidden', type !== 'query');
        overlay.style.display = 'flex';
    }

    hideLoading() {
        document.getElementById('overlay').style.display = 'none';
    }

    stopUpload() {
        this.showStatus('Upload cannot be stopped once started', 'warning');
        this.hideLoading();
    }

    stopQuery() {
        if (this.currentQueryAbortController) {
            this.currentQueryAbortController.abort();
        }
        this.hideLoading();
    }

    showStatus(message, type = 'info') {
        const statusElement = document.getElementById('statusMessage');
        statusElement.textContent = message;
        statusElement.className = `status-message status-${type}`;
        
        if (type === 'success') {
            setTimeout(() => {
                if (statusElement.textContent === message) {
                    statusElement.textContent = 'Ready - System running in offline mode';
                    statusElement.className = 'status-message status-info';
                }
            }, 5000);
        }
    }
}

let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new DocumentQAApp();
});