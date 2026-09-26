// UI Controller and State Management for TrackShip

document.addEventListener('DOMContentLoaded', () => {
    // Initialise Lucide icons
    lucide.createIcons();
    
    // UI Elements
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const selectedFileContainer = document.getElementById('selected-file-container');
    const selectedFileName = document.getElementById('selected-file-name');
    const selectedFileSize = document.getElementById('selected-file-size');
    const removeFileBtn = document.getElementById('remove-file-btn');
    const startTrackingBtn = document.getElementById('start-tracking-btn');
    const progressPanel = document.getElementById('progress-panel');
    const progressBarFill = document.getElementById('progress-bar-fill');
    const progressText = document.getElementById('progress-text');
    const progressPercent = document.getElementById('progress-percent');
    const exportBtn = document.getElementById('export-btn');
    const clearAllBtn = document.getElementById('clear-all-btn');
    const searchInput = document.getElementById('search-input');
    const filterCourier = document.getElementById('filter-courier');
    const filterStatus = document.getElementById('filter-status');
    const tableBody = document.getElementById('table-body');
    
    // Download Images & Sync Selected Elements
    const downloadImagesBtn = document.getElementById('download-images-btn');
    const syncSelectedBtn = document.getElementById('sync-selected-btn');
    const selectedCountSpan = document.getElementById('selected-count');
    const selectAllCheckbox = document.getElementById('select-all-checkbox');

    // Bulk Tracking Mode Toggle Elements
    const screenshotToggle = document.getElementById('screenshot-toggle');
    const modeToggleLabel = document.getElementById('mode-toggle-label');

    // Quick Track Mode Toggle Elements
    const quickScreenshotToggle = document.getElementById('quick-screenshot-toggle');
    const quickModeToggleLabel = document.getElementById('quick-mode-toggle-label');
    
    // Pagination Elements
    const prevPageBtn = document.getElementById('prev-page-btn');
    const nextPageBtn = document.getElementById('next-page-btn');
    const currentPageNum = document.getElementById('current-page-num');
    const totalPagesNum = document.getElementById('total-pages-num');
    const gotoPageInput = document.getElementById('goto-page-input');
    const gotoPageBtn = document.getElementById('goto-page-btn');
    
    // Stats elements
    const statTotal = document.getElementById('stat-total');
    const statDelivered = document.getElementById('stat-delivered');
    const statTransit = document.getElementById('stat-transit');
    const statFailed = document.getElementById('stat-failed');
    const statApi = document.getElementById('stat-api');

    // Custom Sync All Completed Modal Elements
    const syncCompleteModal = document.getElementById('sync-complete-modal');
    const syncCompleteCloseX = document.getElementById('sync-complete-close-x');
    const syncCompleteDoneBtn = document.getElementById('sync-complete-done-btn');
    const modalExportExcelBtn = document.getElementById('modal-export-excel-btn');
    const modalStatTotal = document.getElementById('modal-stat-total');
    const modalStatDelivered = document.getElementById('modal-stat-delivered');
    const modalStatTransit = document.getElementById('modal-stat-transit');
    const modalStatFailed = document.getElementById('modal-stat-failed');
    const modalSyncTime = document.getElementById('modal-sync-time');
    const modalSyncHits = document.getElementById('modal-sync-hits');
    let syncStartTime = null;

    // Timeline Modal Elements
    const timelineModal = document.getElementById('timeline-modal');
    const timelineModalCloseX = document.getElementById('timeline-modal-close-x');
    const timelineModalCloseBtn = document.getElementById('timeline-modal-close-btn');
    const timelineSubtitle = document.getElementById('timeline-subtitle');
    const timelineStatusBadge = document.getElementById('timeline-status-badge');
    const timelineLocation = document.getElementById('timeline-location');
    const timelineTime = document.getElementById('timeline-time');
    const timelineScreenshotBox = document.getElementById('timeline-screenshot-box');
    const timelineScreenshotLink = document.getElementById('timeline-screenshot-link');
    const timelineEventsList = document.getElementById('timeline-events-list');
    const resViewTimelineBtn = document.getElementById('res-view-timeline-btn');
    // Custom Alert Modal Elements & Handler
    const customAlertModal = document.getElementById('custom-alert-modal');
    const alertModalTitle = document.getElementById('alert-modal-title');
    const alertModalMessage = document.getElementById('alert-modal-message');
    const alertIconWrap = document.getElementById('alert-icon-wrap');
    const alertModalOkBtn = document.getElementById('alert-modal-ok-btn');

    function closeCustomAlert() {
        if (customAlertModal) customAlertModal.style.display = 'none';
    }

    if (alertModalOkBtn) alertModalOkBtn.addEventListener('click', closeCustomAlert);
    if (customAlertModal) {
        customAlertModal.addEventListener('click', (e) => {
            if (e.target === customAlertModal) closeCustomAlert();
        });
    }

    document.addEventListener('keydown', (e) => {
        if (customAlertModal && customAlertModal.style.display === 'flex') {
            if (e.key === 'Escape' || e.key === 'Enter') {
                e.preventDefault();
                closeCustomAlert();
            }
        }
    });

    function showAlert(message, type = 'warning', title = '') {
        if (!customAlertModal || !alertModalMessage) {
            console.warn('Alert:', message);
            return;
        }

        if (!title) {
            if (type === 'warning') title = 'Attention';
            else if (type === 'error') title = 'Error';
            else if (type === 'success') title = 'Success';
            else title = 'Information';
        }

        alertModalTitle.textContent = title;
        alertModalMessage.textContent = message;

        if (type === 'warning') {
            alertIconWrap.className = 'alert-icon-container alert-type-warning';
            alertIconWrap.innerHTML = '<i data-lucide="alert-circle"></i>';
        } else if (type === 'error') {
            alertIconWrap.className = 'alert-icon-container alert-type-error';
            alertIconWrap.innerHTML = '<i data-lucide="alert-octagon"></i>';
        } else if (type === 'success') {
            alertIconWrap.className = 'alert-icon-container alert-type-success';
            alertIconWrap.innerHTML = '<i data-lucide="check-circle-2"></i>';
        } else {
            alertIconWrap.className = 'alert-icon-container alert-type-info';
            alertIconWrap.innerHTML = '<i data-lucide="info"></i>';
        }

        if (window.lucide) window.lucide.createIcons();

        customAlertModal.style.display = 'flex';
        if (alertModalOkBtn) alertModalOkBtn.focus();
    }

    // Override native browser alert globally
    window.alert = (msg) => {
        const text = String(msg || '');
        let type = 'warning';
        let title = 'Attention';
        if (text.toLowerCase().includes('error') || text.toLowerCase().includes('failed') || text.toLowerCase().includes('unsupported')) {
            type = 'error';
            title = 'Error';
        } else if (text.toLowerCase().includes('success') || text.toLowerCase().includes('completed')) {
            type = 'success';
            title = 'Success';
        }
        showAlert(text, type, title);
    };

    let currentSingleResult = null;
    const SESSION_KEY = 'trackship_session_state_v3';

    // Application State
    let state = {
        isTracking: false,
        progress: 0,
        taskId: null,
        captureScreenshot: false, // Bulk / Excel Tracking Mode (Default OFF / Fast Track)
        quickCaptureScreenshot: false, // Quick Single Track Mode (Default OFF / Fast Track)
        shipments: [], // Full list of shipments tracked
        filteredShipments: [], // Screen filtered list
        stats: { total: 0, delivered: 0, transit: 0, failed: 0, api_calls: 0 },
        currentPage: 1,
        rowsPerPage: 50,
        activeColumnFilters: {}, // Excel column filter tracking
        selectedAwbs: new Set() // Set of selected tracking numbers
    };

    function updateDownloadImagesVisibility() {
        if (!downloadImagesBtn) return;
        const hasAnyScreenshots = (state.shipments || []).some(s => s.screenshot && s.screenshot !== '-');
        if (state.captureScreenshot || state.quickCaptureScreenshot || hasAnyScreenshots) {
            downloadImagesBtn.style.display = 'inline-flex';
        } else {
            downloadImagesBtn.style.display = 'none';
        }
    }

    function updateBulkModeToggleUI() {
        if (!modeToggleLabel || !screenshotToggle) return;
        screenshotToggle.checked = !!state.captureScreenshot;
        if (state.captureScreenshot) {
            modeToggleLabel.innerHTML = `<span class="image-mode-badge"><img src="/static/image_mode_icon.png?v=3.1.0" class="mode-badge-icon" alt="Image Mode"> Image Mode</span>`;
        } else {
            modeToggleLabel.innerHTML = `<span class="fast-badge"><img src="/static/fast_track_icon.png?v=3.1.0" class="mode-badge-icon" alt="Fast Track"> Fast Track</span>`;
        }
        updateDownloadImagesVisibility();
    }

    function updateQuickModeToggleUI() {
        if (!quickModeToggleLabel || !quickScreenshotToggle) return;
        quickScreenshotToggle.checked = !!state.quickCaptureScreenshot;
        if (state.quickCaptureScreenshot) {
            quickModeToggleLabel.innerHTML = `<span class="image-mode-badge"><img src="/static/image_mode_icon.png?v=3.1.0" class="mode-badge-icon" alt="Image Mode"> Image Mode</span>`;
        } else {
            quickModeToggleLabel.innerHTML = `<span class="fast-badge"><img src="/static/fast_track_icon.png?v=3.1.0" class="mode-badge-icon" alt="Fast Track"> Fast Track</span>`;
        }
        updateDownloadImagesVisibility();
    }

    function updateModeToggleUI() {
        updateBulkModeToggleUI();
        updateQuickModeToggleUI();
    }
    updateModeToggleUI();

    function updateSelectionUI() {
        if (!state.selectedAwbs) state.selectedAwbs = new Set();
        const count = state.selectedAwbs.size;
        if (selectedCountSpan) selectedCountSpan.textContent = count;
        if (syncSelectedBtn) {
            syncSelectedBtn.disabled = (count === 0 || state.isTracking);
        }

        // Update header select-all checkbox
        if (selectAllCheckbox) {
            const visibleAwbs = (state.filteredShipments || []).map(s => s.tracking_number);
            if (visibleAwbs.length === 0) {
                selectAllCheckbox.checked = false;
                selectAllCheckbox.indeterminate = false;
            } else {
                const selectedVisible = visibleAwbs.filter(awb => state.selectedAwbs.has(awb)).length;
                if (selectedVisible === visibleAwbs.length) {
                    selectAllCheckbox.checked = true;
                    selectAllCheckbox.indeterminate = false;
                } else if (selectedVisible > 0) {
                    selectAllCheckbox.checked = false;
                    selectAllCheckbox.indeterminate = true;
                } else {
                    selectAllCheckbox.checked = false;
                    selectAllCheckbox.indeterminate = false;
                }
            }
        }
    }

    if (screenshotToggle) {
        screenshotToggle.addEventListener('change', () => {
            state.captureScreenshot = screenshotToggle.checked;
            updateBulkModeToggleUI();
            saveSessionState();
        });
    }

    if (quickScreenshotToggle) {
        quickScreenshotToggle.addEventListener('change', () => {
            state.quickCaptureScreenshot = quickScreenshotToggle.checked;
            updateQuickModeToggleUI();
            saveSessionState();
        });
    }

    // --- Session Storage State Persistence ---
    function saveSessionState() {
        try {
            const payload = {
                taskId: state.taskId,
                shipments: state.shipments,
                stats: state.stats,
                isTracking: state.isTracking,
                progress: state.progress || 0,
                progressText: progressText.textContent || '',
                captureScreenshot: state.captureScreenshot,
                quickCaptureScreenshot: state.quickCaptureScreenshot,
                currentPage: state.currentPage,
                activeColumnFilters: state.activeColumnFilters,
                fileSelected: selectedFileContainer.style.display !== 'none',
                fileName: selectedFileName.textContent,
                fileSize: selectedFileSize.textContent
            };
            sessionStorage.setItem(SESSION_KEY, JSON.stringify(payload));
        } catch (e) {
            console.warn('Failed to save to sessionStorage:', e);
        }
    }

    async function syncTaskToBackendSilently() {
        if (!state.taskId || !state.shipments || state.shipments.length === 0) return;
        try {
            await fetch('/api/restore_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: state.taskId,
                    shipments: state.shipments
                })
            });
        } catch (e) {
            // Silently ignore if server is sleeping or waking up
        }
    }

    async function restoreSessionState() {
        try {
            const raw = sessionStorage.getItem(SESSION_KEY);
            if (raw) {
                const saved = JSON.parse(raw);
                if (saved && saved.shipments && saved.shipments.length > 0) {
                    state.taskId = saved.taskId || ('task_' + Date.now());
                    state.shipments = saved.shipments;
                    state.stats = saved.stats || { total: saved.shipments.length, delivered: 0, transit: 0, failed: 0, api_calls: 0 };
                    state.currentPage = saved.currentPage || 1;
                    state.activeColumnFilters = saved.activeColumnFilters || {};
                    state.isTracking = !!saved.isTracking;
                    state.progress = saved.progress || 0;
                    state.captureScreenshot = false;
                    state.quickCaptureScreenshot = false;
                    updateModeToggleUI();

                    if (saved.fileSelected && saved.fileName) {
                        selectedFileName.textContent = saved.fileName;
                        selectedFileSize.textContent = saved.fileSize || '';
                        dropZone.style.display = 'none';
                        selectedFileContainer.style.display = 'block';
                    }

                    startTrackingBtn.disabled = false;
                    exportBtn.disabled = false;
                    clearAllBtn.disabled = false;

                    updateStatsUI();
                    applyFilters(false);

                    if (state.isTracking && state.progress < 100) {
                        progressPanel.style.visibility = 'visible';
                        progressBarFill.style.width = `${state.progress}%`;
                        progressPercent.textContent = `${state.progress}%`;
                        progressText.textContent = saved.progressText || 'Resuming tracking...';
                        startTrackingBtn.disabled = true;
                        pollProgress();
                    } else if (state.progress >= 100) {
                        progressPanel.style.visibility = 'visible';
                        progressBarFill.style.width = `100%`;
                        progressPercent.textContent = `100%`;
                        progressText.textContent = 'Sync All Completed!';
                    }

                    // Background restore to backend in case Render woke up from sleep
                    syncTaskToBackendSilently();
                    return true;
                }
            }
        } catch (e) {
            console.warn('Failed to parse sessionStorage:', e);
        }
        return false;
    }

    // --- Drag and Drop File Handlers ---
    
    dropZone.addEventListener('click', (e) => {
        if (e.target.className !== 'browse-btn' && !e.target.closest('.browse-btn')) {
            // trigger file dialog
        }
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    // Drag and drop events
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over'), false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFileSelect(files[0]);
        }
    });

    removeFileBtn.addEventListener('click', () => {
        resetUploadSection();
    });

    function resetUploadSection() {
        fileInput.value = '';
        selectedFileContainer.style.display = 'none';
        dropZone.style.display = 'flex';
        startTrackingBtn.disabled = true;
        exportBtn.disabled = true;
        clearAllBtn.disabled = true;
        progressPanel.style.visibility = 'hidden';
        progressBarFill.style.width = '0%';
        progressPercent.textContent = '0%';
        progressText.textContent = 'Awaiting start...';

        state.taskId = null;
        state.shipments = [];
        state.filteredShipments = [];
        if (state.selectedAwbs) state.selectedAwbs.clear();
        updateSelectionUI();
        state.stats = { total: 0, delivered: 0, transit: 0, failed: 0, api_calls: state.stats.api_calls || 0 };
        state.currentPage = 1;
        state.activeColumnFilters = {};
        state.isTracking = false;
        state.progress = 0;

        sessionStorage.removeItem(SESSION_KEY);
        updateStatsUI();
        updateDownloadImagesVisibility();
        applyFilters();
    }

    async function handleFileSelect(file) {
        if (!file) return;

        const allowedExtensions = ['.csv', '.xlsx', '.xls'];
        const fileName = file.name;
        const fileExt = fileName.substring(fileName.lastIndexOf('.')).toLowerCase();

        if (!allowedExtensions.includes(fileExt)) {
            alert('Unsupported file format. Please upload a CSV or Excel file.');
            return;
        }

        // Show UI file info
        selectedFileName.textContent = fileName;
        selectedFileSize.textContent = formatBytes(file.size);
        dropZone.style.display = 'none';
        selectedFileContainer.style.display = 'block';

        // Prepare FormData for server upload
        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || 'Upload failed');
            }

            const uploadData = await res.json();
            
            // Set App State
            state.taskId = uploadData.task_id;
            state.shipments = uploadData.shipments || [];
            if (uploadData.stats) {
                state.stats = uploadData.stats;
            }
            
            // Enable buttons
            startTrackingBtn.disabled = false;
            exportBtn.disabled = false;
            clearAllBtn.disabled = false;
            
            // Render rows in table
            applyFilters();
            recalculateStats();
            updateDownloadImagesVisibility();
            saveSessionState();
            
        } catch (error) {
            alert(`Error uploading file: ${error.message}`);
            resetUploadSection();
        }
    }

    // "Sync All" button triggers bulk simulation run
    startTrackingBtn.addEventListener('click', async () => {
        if (!state.taskId && state.shipments.length === 0) return;
        if (!state.taskId) {
            state.taskId = 'task_' + Date.now();
        }

        try {
            syncStartTime = Date.now();
            startTrackingBtn.disabled = true;
            progressPanel.style.visibility = 'visible';
            state.isTracking = true;
            state.progress = 0;
            progressBarFill.style.width = '0%';
            progressPercent.textContent = '0%';
            progressText.textContent = state.captureScreenshot ? 'Starting screenshot tracking...' : 'Starting fast tracking...';
            saveSessionState();
            renderCurrentPage();

            const startRes = await fetch('/api/track/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: state.taskId,
                    shipments: state.shipments,
                    capture_screenshot: !!state.captureScreenshot
                })
            });

            if (!startRes.ok) {
                const errData = await startRes.json().catch(() => ({}));
                throw new Error(errData.detail || 'Failed to start tracking engine');
            }

            pollProgress();

        } catch (error) {
            alert(`Error starting tracking: ${error.message}`);
            startTrackingBtn.disabled = false;
            state.isTracking = false;
            updateSelectionUI();
            saveSessionState();
        }
    });

    // "Sync Selected" button triggers tracking ONLY for selected shipments
    if (syncSelectedBtn) {
        syncSelectedBtn.addEventListener('click', async () => {
            if (!state.selectedAwbs || state.selectedAwbs.size === 0) {
                alert('Please select at least one shipment checkbox to sync.');
                return;
            }
            if (state.isTracking) return;

            const selectedList = Array.from(state.selectedAwbs);
            if (!state.taskId) {
                state.taskId = 'task_' + Date.now();
            }

            try {
                syncStartTime = Date.now();
                state.isTracking = true;
                syncSelectedBtn.disabled = true;
                startTrackingBtn.disabled = true;
                progressPanel.style.visibility = 'visible';
                state.progress = 0;
                progressBarFill.style.width = '0%';
                progressPercent.textContent = '0%';
                progressText.textContent = `Starting sync for ${selectedList.length} selected shipments...`;
                saveSessionState();
                renderCurrentPage();

                const startRes = await fetch('/api/track/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        task_id: state.taskId,
                        shipments: state.shipments,
                        capture_screenshot: !!state.captureScreenshot,
                        selected_tracking_numbers: selectedList
                    })
                });

                if (!startRes.ok) {
                    const errData = await startRes.json().catch(() => ({}));
                    throw new Error(errData.detail || 'Failed to start tracking selected shipments');
                }

                pollProgress();

            } catch (error) {
                alert(`Error starting selective tracking: ${error.message}`);
                syncSelectedBtn.disabled = false;
                startTrackingBtn.disabled = false;
                state.isTracking = false;
                updateSelectionUI();
                saveSessionState();
            }
        });
    }

    // "Download Images" button triggers ZIP download of screenshots
    if (downloadImagesBtn) {
        downloadImagesBtn.addEventListener('click', async () => {
            try {
                let targetAwbs = [];
                if (state.selectedAwbs && state.selectedAwbs.size > 0) {
                    targetAwbs = Array.from(state.selectedAwbs);
                } else {
                    targetAwbs = (state.shipments || [])
                        .filter(s => s.screenshot && s.screenshot !== '-')
                        .map(s => s.tracking_number);
                }

                if (targetAwbs.length === 0) {
                    alert('No screenshots found to download. Please sync shipments in Image Mode first!');
                    return;
                }

                const originalBtnHtml = downloadImagesBtn.innerHTML;
                downloadImagesBtn.disabled = true;
                downloadImagesBtn.innerHTML = `<span class="duo-spinner btn-duo-spinner"></span> Preparing ZIP...`;

                const res = await fetch('/api/download-screenshots', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        task_id: state.taskId || '',
                        tracking_numbers: targetAwbs
                    })
                });

                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || 'Failed to download screenshots');
                }

                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const now = new Date();
                const dateStr = now.toISOString().slice(0, 10);
                a.download = `screenshots_${dateStr}.zip`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);

                downloadImagesBtn.disabled = false;
                downloadImagesBtn.innerHTML = originalBtnHtml;
                lucide.createIcons();
            } catch (err) {
                alert(`Error downloading screenshots: ${err.message}`);
                downloadImagesBtn.disabled = false;
                downloadImagesBtn.innerHTML = `<i data-lucide="download"></i> Download Images`;
                lucide.createIcons();
            }
        });
    }

    // Master Header Select All Checkbox Handler
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', () => {
            if (!state.selectedAwbs) state.selectedAwbs = new Set();
            const visibleShipments = state.filteredShipments || [];
            if (selectAllCheckbox.checked) {
                visibleShipments.forEach(s => state.selectedAwbs.add(s.tracking_number));
            } else {
                visibleShipments.forEach(s => state.selectedAwbs.delete(s.tracking_number));
            }
            document.querySelectorAll('.row-select-checkbox').forEach(cb => {
                const awb = cb.getAttribute('data-awb');
                cb.checked = state.selectedAwbs.has(awb);
            });
            updateSelectionUI();
        });
    }

    // Custom Delete Modal Elements
    const deleteModal = document.getElementById('delete-modal');
    const modalCancelBtn = document.getElementById('modal-cancel-btn');
    const modalConfirmBtn = document.getElementById('modal-confirm-btn');

    clearAllBtn.addEventListener('click', () => {
        deleteModal.style.display = 'flex';
    });

    modalCancelBtn.addEventListener('click', () => {
        deleteModal.style.display = 'none';
    });

    // Close modal if user clicks outside the modal card
    deleteModal.addEventListener('click', (e) => {
        if (e.target === deleteModal) {
            deleteModal.style.display = 'none';
        }
    });

    modalConfirmBtn.addEventListener('click', async () => {
        try {
            await fetch('/api/clear', { method: 'DELETE' });
        } catch (e) {
            console.error('Failed to clear server data:', e);
        }
        deleteModal.style.display = 'none';
        resetUploadSection();
    });

    async function pollProgress() {
        if (!state.isTracking) return;

        try {
            const res = await fetch(`/api/track/progress?task_id=${state.taskId}`);
            if (!res.ok) {
                if (res.status === 404) {
                    // Task lost during server sleep/restart: auto-resume by starting with current shipments
                    console.log('Task missing in DB on poll, auto-recovering tracking session...');
                    await fetch('/api/track/start', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            task_id: state.taskId,
                            shipments: state.shipments,
                            capture_screenshot: !!state.captureScreenshot
                        })
                    });
                    setTimeout(pollProgress, 1500);
                    return;
                }
                throw new Error('Progress fetch failed');
            }

            const data = await res.json();
            
            // Log latest progress and shipment data in console
            if (data.shipments && data.shipments.length > 0) {
                const latestCompleted = data.shipments.filter(s => s.status && s.status !== 'Pending' && s.last_sync && s.last_sync !== '-');
                if (latestCompleted.length > 0) {
                    const lastTracked = latestCompleted[latestCompleted.length - 1];
                    console.log(`%c[BATCH PROGRESS ${data.progress}%] AWB: ${lastTracked.tracking_number} (${lastTracked.courier}) -> Status: ${lastTracked.status}`, 'color: #9333ea; font-weight: bold; font-size: 11px;', lastTracked);
                }
            }
            
            // Update local state
            state.shipments = data.shipments;
            const progress = data.progress;
            state.progress = progress;
            if (data.stats) {
                state.stats = data.stats;
            }
            
            // Update progress elements
            progressBarFill.style.width = `${progress}%`;
            progressPercent.textContent = `${progress}%`;
            
            // Show latest log message as status text if any logs exist
            if (data.logs && data.logs.length > 0) {
                progressText.textContent = data.logs[data.logs.length - 1].message;
            } else {
                progressText.textContent = data.current_action || 'Processing...';
            }

            // Update Table and Stats without resetting active page
            applyFilters(false);
            recalculateStats();
            saveSessionState();

            if (data.status === 'completed' || progress >= 100) {
                state.isTracking = false;
                progressText.textContent = 'Sync Completed!';
                startTrackingBtn.disabled = false;
                if (state.selectedAwbs) state.selectedAwbs.clear();
                updateSelectionUI();
                saveSessionState();
                setTimeout(() => {
                    showSyncCompletedModal();
                }, 350);
            } else if (data.status === 'failed') {
                state.isTracking = false;
                progressText.textContent = 'Sync Failed.';
                startTrackingBtn.disabled = false;
                updateSelectionUI();
                saveSessionState();
            } else {
                // Poll again in 1.5 seconds
                setTimeout(pollProgress, 1500);
            }

        } catch (error) {
            console.error('Polling error:', error);
            if (state.isTracking) {
                setTimeout(pollProgress, 2000);
            }
        }
    }

    // --- Custom Sync All Completed Modal Functions ---
    function formatElapsedTime(ms) {
        if (!ms || ms <= 0) return 'Few seconds';
        const seconds = Math.round(ms / 1000);
        if (seconds < 60) return `${seconds}s`;
        const mins = Math.floor(seconds / 60);
        const remSecs = seconds % 60;
        return `${mins}m ${remSecs}s`;
    }

    function showSyncCompletedModal() {
        if (!syncCompleteModal) return;

        recalculateStats();

        if (modalStatTotal) modalStatTotal.textContent = state.shipments.length;
        if (modalStatDelivered) modalStatDelivered.textContent = state.stats.delivered || 0;
        if (modalStatTransit) modalStatTransit.textContent = state.stats.transit || 0;
        if (modalStatFailed) modalStatFailed.textContent = state.stats.failed || 0;

        const elapsed = syncStartTime ? (Date.now() - syncStartTime) : 0;
        if (modalSyncTime) modalSyncTime.textContent = `Time: ${formatElapsedTime(elapsed)}`;
        if (modalSyncHits) modalSyncHits.textContent = `API Hits: ${state.stats.api_calls || state.shipments.length}`;

        syncCompleteModal.style.display = 'flex';
        lucide.createIcons();
    }

    function closeSyncCompletedModal() {
        if (syncCompleteModal) {
            syncCompleteModal.style.display = 'none';
        }
    }

    if (syncCompleteCloseX) syncCompleteCloseX.addEventListener('click', closeSyncCompletedModal);
    if (syncCompleteDoneBtn) syncCompleteDoneBtn.addEventListener('click', closeSyncCompletedModal);
    if (syncCompleteModal) {
        syncCompleteModal.addEventListener('click', (e) => {
            if (e.target === syncCompleteModal) {
                closeSyncCompletedModal();
            }
        });
    }
    if (modalExportExcelBtn) {
        modalExportExcelBtn.addEventListener('click', () => {
            closeSyncCompletedModal();
            exportBtn.click();
        });
    }

    // Global Escape key handler to close any active modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSyncCompletedModal();
            const resModal = document.getElementById('result-modal');
            if (resModal) resModal.style.display = 'none';
            if (deleteModal) deleteModal.style.display = 'none';
        }
    });

    // Individual Row Sync Handler
    async function syncSingleShipment(trackingNumber, courier, syncButton) {
        if (!state.taskId && state.shipments.length === 0) return;
        if (!state.taskId) state.taskId = 'task_' + Date.now();
        
        syncButton.innerHTML = `<span class="duo-spinner table-duo-spinner"></span>`;
        syncButton.disabled = true;

        const currentItem = state.shipments.find(s => s.tracking_number === trackingNumber);

        const reqPayload = {
            task_id: state.taskId,
            tracking_number: trackingNumber,
            courier: courier,
            channel: currentItem ? currentItem.channel : '',
            seller_name: currentItem ? currentItem.seller_name : '',
            return_date: currentItem ? currentItem.return_date : '',
            mp_date: currentItem ? currentItem.mp_date : '',
            days_left: currentItem ? currentItem.days_left : '',
            invoice_no: currentItem ? currentItem.invoice_no : '',
            platform_status: currentItem ? currentItem.platform_status : '',
            capture_screenshot: !!state.captureScreenshot
        };
        console.log(`%c[AWB REQUEST SYNC] >>> ${courier} | ${trackingNumber}`, 'color: #2563eb; font-weight: bold; font-size: 12px;', reqPayload);

        try {
            const res = await fetch('/api/track/sync_single', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(reqPayload)
            });

            if (!res.ok) {
                const errData = await res.json();
                console.error(`%c[AWB SYNC ERROR] <<< ${courier} | ${trackingNumber}`, 'color: #ef4444; font-weight: bold;', errData);
                throw new Error(errData.detail || 'Sync failed');
            }

            const data = await res.json();
            console.log(`%c[AWB RESPONSE SYNC] <<< ${courier} | ${trackingNumber}`, 'color: #16a34a; font-weight: bold; font-size: 12px;', data);

            // Update today's API hits count
            if (data.api_calls !== undefined) {
                state.stats.api_calls = data.api_calls;
            }

            // Update local state record
            const idx = state.shipments.findIndex(s => s.tracking_number === trackingNumber);
            if (idx !== -1) {
                if (data.status) state.shipments[idx].status = data.status;
                if (data.last_location) state.shipments[idx].last_location = data.last_location;
                if (data.timestamp) state.shipments[idx].timestamp = data.timestamp;
                if (data.last_sync) state.shipments[idx].last_sync = data.last_sync || "-";
                if (data.screenshot && data.screenshot !== '-') {
                    state.shipments[idx].screenshot = data.screenshot;
                }
            }

            // Render and update stats & download button
            applyFilters(false);
            recalculateStats();
            updateDownloadImagesVisibility();
            saveSessionState();

        } catch (error) {
            showAlert(`Error syncing AWB ${trackingNumber}: ${error.message}`, 'error', 'Sync Failed');
        } finally {
            syncButton.innerHTML = `<i data-lucide="refresh-cw"></i>`;
            lucide.createIcons();
            syncButton.disabled = false;
        }
    }

    // Individual Row Screenshot Capture Handler (Camera Button)
    async function captureSingleScreenshot(trackingNumber, courier, cameraButton) {
        if (!state.taskId && state.shipments.length === 0) return;
        if (!state.taskId) state.taskId = 'task_' + Date.now();
        
        // Show Option 3 dual-tone arc spinner on camera button
        cameraButton.innerHTML = `<span class="duo-spinner table-duo-spinner"></span>`;
        cameraButton.disabled = true;

        const currentItem = state.shipments.find(s => s.tracking_number === trackingNumber);

        const reqPayload = {
            task_id: state.taskId,
            tracking_number: trackingNumber,
            courier: courier,
            channel: currentItem ? currentItem.channel : '',
            seller_name: currentItem ? currentItem.seller_name : '',
            return_date: currentItem ? currentItem.return_date : '',
            mp_date: currentItem ? currentItem.mp_date : '',
            days_left: currentItem ? currentItem.days_left : '',
            invoice_no: currentItem ? currentItem.invoice_no : '',
            platform_status: currentItem ? currentItem.platform_status : '',
            capture_screenshot: true // ALWAYS capture official screenshot
        };
        console.log(`%c[CAMERA SCREENSHOT CAPTURE] >>> ${courier} | ${trackingNumber}`, 'color: #2563eb; font-weight: bold; font-size: 12px;', reqPayload);

        try {
            const res = await fetch('/api/track/sync_single', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(reqPayload)
            });

            if (!res.ok) {
                const errData = await res.json();
                console.error(`%c[CAMERA CAPTURE ERROR] <<< ${courier} | ${trackingNumber}`, 'color: #ef4444; font-weight: bold;', errData);
                throw new Error(errData.detail || 'Screenshot capture failed');
            }

            const data = await res.json();
            console.log(`%c[CAMERA CAPTURE SUCCESS] <<< ${courier} | ${trackingNumber}`, 'color: #16a34a; font-weight: bold; font-size: 12px;', data);

            // Update today's API hits count
            if (data.api_calls !== undefined) {
                state.stats.api_calls = data.api_calls;
            }

            // Update local state record
            const idx = state.shipments.findIndex(s => s.tracking_number === trackingNumber);
            if (idx !== -1) {
                if (data.status) state.shipments[idx].status = data.status;
                if (data.last_location) state.shipments[idx].last_location = data.last_location;
                if (data.timestamp) state.shipments[idx].timestamp = data.timestamp;
                if (data.last_sync) state.shipments[idx].last_sync = data.last_sync || "-";
                if (data.screenshot && data.screenshot !== '-') {
                    state.shipments[idx].screenshot = data.screenshot;
                }
            }

            // Re-render and update stats & download button
            applyFilters(false);
            recalculateStats();
            updateDownloadImagesVisibility();
            saveSessionState();

        } catch (error) {
            showAlert(`Error capturing screenshot for AWB ${trackingNumber}: ${error.message}`, 'error', 'Screenshot Failed');
            cameraButton.innerHTML = `<img src="/static/camera_capture_icon.png?v=3.4.0" alt="Capture Screenshot">`;
            cameraButton.disabled = false;
        }
    }

    // Direct Excel export from client memory (guarantees export works even if Render woke up recently)
    exportBtn.addEventListener('click', async () => {
        if (!state.shipments || state.shipments.length === 0) return;

        const originalBtnHtml = exportBtn.innerHTML;
        exportBtn.innerHTML = `<span class="duo-spinner btn-duo-spinner"></span> Exporting...`;
        exportBtn.disabled = true;

        try {
            const res = await fetch('/api/export_direct', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_id: state.taskId || 'export',
                    shipments: state.shipments
                })
            });

            if (!res.ok) throw new Error('Failed to generate Excel export');

            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const taskSuffix = state.taskId ? state.taskId.substring(0, 8) : 'export';
            a.download = `tracking_export_${taskSuffix}.xlsx`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (e) {
            console.error('[EXPORT ERROR]', e);
            showAlert(`Export failed: ${e.message}`, 'error', 'Export Failed');
        } finally {
            exportBtn.innerHTML = originalBtnHtml;
            exportBtn.disabled = false;
            lucide.createIcons();
        }
    });

    // --- Search & Filters ---

    searchInput.addEventListener('input', () => applyFilters(true));
    filterCourier.addEventListener('change', () => applyFilters(true));
    filterStatus.addEventListener('change', () => applyFilters(true));

    function applyFilters(resetPage = true) {
        const query = searchInput.value.toLowerCase().trim();
        const courier = filterCourier.value;
        const status = filterStatus.value;

        state.filteredShipments = state.shipments.filter(item => {
            const matchesQuery = item.tracking_number.toLowerCase().includes(query) || 
                                 item.courier.toLowerCase().includes(query) ||
                                 (item.channel || '').toLowerCase().includes(query) ||
                                 (item.seller_name || '').toLowerCase().includes(query) ||
                                 (item.invoice_no || '').toLowerCase().includes(query) ||
                                 (item.last_location || '').toLowerCase().includes(query);
            
            const matchesCourier = courier === 'all' || item.courier.toLowerCase() === courier.toLowerCase();
            const matchesStatus = status === 'all' || mapStatusFilter(item.status) === status;

            // Excel Column Filters
            let matchesColumnFilters = true;
            for (const [col, selectedVals] of Object.entries(state.activeColumnFilters)) {
                if (selectedVals && selectedVals.length > 0) {
                    let itemVal = item[col] || '';
                    if (col === 'screenshot') {
                        itemVal = (item.screenshot && item.screenshot !== '-') ? 'Has Image' : 'No Image';
                    } else if (col === 'invoice_no' || col === 'platform_status' || col === 'channel' || col === 'seller_name' || col === 'return_date' || col === 'mp_date' || col === 'days_left') {
                        itemVal = itemVal || '-';
                    } else if (col === 'last_location') {
                        itemVal = itemVal || 'Pending scan';
                    } else if (col === 'timestamp' || col === 'last_sync') {
                        itemVal = itemVal || '-';
                    }
                    
                    if (!selectedVals.includes(String(itemVal))) {
                        matchesColumnFilters = false;
                        break;
                    }
                }
            }

            return matchesQuery && matchesCourier && matchesStatus && matchesColumnFilters;
        });

        // Highlight header buttons that have active filters
        document.querySelectorAll('.header-filter-btn').forEach(btn => {
            const th = btn.closest('th');
            if (th) {
                const colKey = th.getAttribute('data-col');
                const active = state.activeColumnFilters[colKey] && state.activeColumnFilters[colKey].length > 0;
                if (active) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            }
        });

        if (resetPage) {
            state.currentPage = 1;
        }
        renderCurrentPage();
    }

    function renderCurrentPage() {
        const total = state.filteredShipments.length;
        const totalPages = Math.ceil(total / state.rowsPerPage) || 1;
        
        if (state.currentPage > totalPages) {
            state.currentPage = totalPages;
        }
        if (state.currentPage < 1) {
            state.currentPage = 1;
        }

        // Update labels
        currentPageNum.textContent = state.currentPage;
        totalPagesNum.textContent = totalPages;
        gotoPageInput.max = totalPages;
        gotoPageInput.value = state.currentPage;

        // Buttons state
        prevPageBtn.disabled = (state.currentPage === 1);
        nextPageBtn.disabled = (state.currentPage === totalPages);

        // Slice data
        const start = (state.currentPage - 1) * state.rowsPerPage;
        const end = start + state.rowsPerPage;
        const pageData = state.filteredShipments.slice(start, end);

        renderTable(pageData);
    }

    // Pagination Listeners
    prevPageBtn.addEventListener('click', () => {
        if (state.currentPage > 1) {
            state.currentPage--;
            renderCurrentPage();
            saveSessionState();
        }
    });

    nextPageBtn.addEventListener('click', () => {
        const totalPages = Math.ceil(state.filteredShipments.length / state.rowsPerPage) || 1;
        if (state.currentPage < totalPages) {
            state.currentPage++;
            renderCurrentPage();
            saveSessionState();
        }
    });

    gotoPageBtn.addEventListener('click', () => {
        const totalPages = Math.ceil(state.filteredShipments.length / state.rowsPerPage) || 1;
        let page = parseInt(gotoPageInput.value);
        if (isNaN(page) || page < 1) {
            page = 1;
        } else if (page > totalPages) {
            page = totalPages;
        }
        state.currentPage = page;
        renderCurrentPage();
        saveSessionState();
    });

    gotoPageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            gotoPageBtn.click();
        }
    });

    function mapStatusFilter(status) {
        status = status.toLowerCase();
        if (status.includes('delivered')) return 'delivered';
        if (status.includes('transit') || status.includes('picked') || status.includes('pickup') || status.includes('dispatched') || status.includes('shipped') || status.includes('route')) return 'transit';
        if (status.includes('out') || status.includes('delivery') || status.includes('schedule')) return 'out_for_delivery';
        if (status.includes('fail') || status.includes('except') || status.includes('error') || status.includes('invalid') || status.includes('return') || status.includes('cancel') || status.includes('undelivered')) return 'exception';
        return 'pending';
    }

    function recalculateStats() {
        const total = state.shipments.length;
        let delivered = 0;
        let transit = 0;
        let failed = 0;

        state.shipments.forEach(s => {
            const mapped = mapStatusFilter(s.status);
            if (mapped === 'delivered') delivered++;
            else if (mapped === 'transit' || mapped === 'out_for_delivery') transit++;
            else if (mapped === 'exception') failed++;
        });

        state.stats = { total, delivered, transit, failed, api_calls: state.stats.api_calls || 0 };
        updateStatsUI();
    }

    function getCourierBadgeClass(courier) {
        courier = courier.toLowerCase();
        if (courier.includes('delhivery')) return 'courier-delhivery';
        if (courier.includes('xpressbees')) return 'courier-xpressbees';
        if (courier.includes('shadowfax')) return 'courier-shadowfax';
        if (courier.includes('bluedart') || courier.includes('blue dart')) return 'courier-bluedart';
        if (courier.includes('dtdc')) return 'courier-dtdc';
        if (courier.includes('ecom')) return 'courier-ecom';
        if (courier.includes('ekart')) return 'courier-ekart';
        if (courier.includes('india post')) return 'courier-indiapost';
        return 'courier-default';
    }

    // --- 30 Unique AWB Color Palettes (bg, text) ---
    const AWB_COLORS = [
        { bg: '#dbeafe', text: '#1e40af' },  // Blue
        { bg: '#fce7f3', text: '#9d174d' },  // Pink
        { bg: '#d1fae5', text: '#065f46' },  // Emerald
        { bg: '#fef3c7', text: '#92400e' },  // Amber
        { bg: '#ede9fe', text: '#5b21b6' },  // Violet
        { bg: '#ffedd5', text: '#c2410c' },  // Orange
        { bg: '#cffafe', text: '#155e75' },  // Cyan
        { bg: '#fecdd3', text: '#9f1239' },  // Rose
        { bg: '#dcfce7', text: '#166534' },  // Green
        { bg: '#e0e7ff', text: '#3730a3' },  // Indigo
        { bg: '#fef9c3', text: '#854d0e' },  // Yellow
        { bg: '#f3e8ff', text: '#6b21a8' },  // Purple
        { bg: '#ccfbf1', text: '#134e4a' },  // Teal
        { bg: '#fee2e2', text: '#991b1b' },  // Red
        { bg: '#e0f2fe', text: '#075985' },  // Sky
        { bg: '#fae8ff', text: '#86198f' },  // Fuchsia
        { bg: '#ecfccb', text: '#3f6212' },  // Lime
        { bg: '#f1f5f9', text: '#334155' },  // Slate
        { bg: '#fff1f2', text: '#be123c' },  // Light Rose
        { bg: '#f0fdfa', text: '#115e59' },  // Light Teal
        { bg: '#fdf4ff', text: '#a21caf' },  // Light Fuchsia
        { bg: '#f0fdf4', text: '#14532d' },  // Light Green
        { bg: '#eff6ff', text: '#1e3a8a' },  // Light Blue
        { bg: '#fffbeb', text: '#78350f' },  // Light Amber
        { bg: '#fdf2f8', text: '#831843' },  // Light Pink
        { bg: '#f5f3ff', text: '#4c1d95' },  // Light Violet
        { bg: '#ecfdf5', text: '#064e3b' },  // Light Emerald
        { bg: '#fff7ed', text: '#9a3412' },  // Light Orange
        { bg: '#f8fafc', text: '#0f172a' },  // Light Slate
        { bg: '#fefce8', text: '#713f12' },  // Light Yellow
    ];

    function getAwbColorIndex(trackingNumber) {
        let hash = 0;
        for (let i = 0; i < trackingNumber.length; i++) {
            hash = ((hash << 5) - hash) + trackingNumber.charCodeAt(i);
            hash |= 0;
        }
        return Math.abs(hash) % AWB_COLORS.length;
    }

    // --- Helper UI Renderers ---

    function renderTable(dataList) {
        if (dataList.length === 0) {
            tableBody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="16">
                        <div class="empty-state">
                            <i data-lucide="file-warning"></i>
                            <p>No matching shipments found.</p>
                        </div>
                    </td>
                </tr>
            `;
            updateSelectionUI();
            return;
        }

        tableBody.innerHTML = '';
        dataList.forEach((item, index) => {
            const tr = document.createElement('tr');

            const statusKey = item.status.toLowerCase().replace(/[\s_]+/g, '_');
            let badgeClass = 'badge-pending';
            if (statusKey === 'delivered') badgeClass = 'badge-delivered';
            else if (statusKey.includes('transit') || statusKey.includes('picked') || statusKey.includes('out_for')) badgeClass = 'badge-transit';
            else if (statusKey === 'exception' || statusKey.includes('fail') || statusKey.includes('error') || statusKey.includes('invalid') || statusKey.includes('not_found') || statusKey.includes('not found')) badgeClass = 'badge-exception';

            // Determine timestamp filled/empty status
            const isTimestampEmpty = !item.timestamp || item.timestamp === '-';
            const timestampBadgeClass = isTimestampEmpty ? 'timestamp-empty' : 'timestamp-filled';
            const printTimestamp = isTimestampEmpty ? '-' : item.timestamp;

            // Determine last sync filled/empty status
            const isLastSyncEmpty = !item.last_sync || item.last_sync === '-';
            const lastSyncBadgeClass = isLastSyncEmpty ? 'lastsync-empty' : 'lastsync-filled';
            const printLastSync = isLastSyncEmpty ? '-' : item.last_sync;

            // Unique row color
            const awbColor = AWB_COLORS[index % AWB_COLORS.length];
            const rowTextColor = awbColor.text;

            // Spin single sync button if bulk tracking is in progress and this item is still pending
            const isSpinning = state.isTracking && item.status.toLowerCase() === 'pending';

            // Determine screenshot column markup
            const hasScreenshot = item.screenshot && item.screenshot !== '-';
            const screenshotUrl = hasScreenshot ? `${item.screenshot.split('?')[0]}?t=${Date.now()}` : '';
            const screenshotHtml = hasScreenshot ? 
                `<a href="${screenshotUrl}" target="_blank" class="gallery-icon-link has-screenshot" title="View & Download Screenshot"><img src="/static/gallery_icon_blue.png?v=3.4.0" alt="Screenshot Available"></a>` : 
                `<span class="gallery-icon-link no-screenshot" title="No screenshot captured (Fast Track)"><img src="/static/gallery_icon_red.png?v=3.4.0" alt="No Screenshot"></span>`;

            const isChecked = state.selectedAwbs && state.selectedAwbs.has(item.tracking_number);

            tr.innerHTML = `
                <td style="text-align: center; width: 42px;">
                    <input type="checkbox" class="row-select-checkbox" data-awb="${item.tracking_number}" ${isChecked ? 'checked' : ''}>
                </td>
                <td><span style="color:${rowTextColor}">${item.channel || '-'}</span></td>
                <td><span style="color:${rowTextColor}">${item.seller_name || '-'}</span></td>
                <td><span style="color:${rowTextColor}">${item.return_date || '-'}</span></td>
                <td><span style="color:${rowTextColor}">${item.mp_date || '-'}</span></td>
                <td><span style="color:${rowTextColor}">${item.days_left || '-'}</span></td>
                <td><span style="color:${rowTextColor}">${item.invoice_no || '-'}</span></td>
                <td><span class="awb-badge clickable-awb" style="color:${rowTextColor}" title="Click to view journey timeline">${item.tracking_number}</span></td>
                <td><span class="courier-badge ${getCourierBadgeClass(item.courier)}">${item.courier}</span></td>
                <td><span style="color:${rowTextColor}">${item.platform_status || '-'}</span></td>
                <td><span class="badge ${badgeClass}">${item.status}</span></td>
                <td><span class="location-badge" style="color:${rowTextColor}">${item.last_location || 'Pending scan'}</span></td>
                <td><span class="timestamp-badge ${timestampBadgeClass}" style="color:${isTimestampEmpty ? '' : rowTextColor}">${printTimestamp}</span></td>
                <td><span class="lastsync-badge ${lastSyncBadgeClass}" style="color:${isLastSyncEmpty ? '' : rowTextColor}">${printLastSync}</span></td>
                <td class="screenshot-cell">${screenshotHtml}</td>
                <td style="text-align: center; white-space: nowrap;">
                    <div class="actions-cell-content">
                        <button class="btn-timeline-view" title="View Journey Timeline">
                            <i data-lucide="route"></i>
                        </button>
                        <button class="btn-camera-capture" title="Capture Screenshot Only" data-awb="${item.tracking_number}">
                            <img src="/static/camera_capture_icon.png?v=3.4.0" alt="Capture Screenshot">
                        </button>
                        <button class="btn-sync-single" title="Sync Status" style="color:${rowTextColor}" ${isSpinning ? 'disabled' : ''}>
                            ${isSpinning ? 
                                `<span class="duo-spinner table-duo-spinner"></span>` : 
                                `<i data-lucide="refresh-cw"></i>`
                            }
                        </button>
                    </div>
                </td>
            `;

            // Bind row selection checkbox handler
            const rowCheckbox = tr.querySelector('.row-select-checkbox');
            if (rowCheckbox) {
                rowCheckbox.addEventListener('change', (e) => {
                    e.stopPropagation();
                    if (!state.selectedAwbs) state.selectedAwbs = new Set();
                    if (rowCheckbox.checked) {
                        state.selectedAwbs.add(item.tracking_number);
                    } else {
                        state.selectedAwbs.delete(item.tracking_number);
                    }
                    updateSelectionUI();
                });
            }

            // Bind single sync button handler
            const syncButton = tr.querySelector('.btn-sync-single');
            syncButton.addEventListener('click', (e) => {
                e.stopPropagation();
                syncSingleShipment(item.tracking_number, item.courier, syncButton);
            });

            // Bind single camera screenshot capture handler
            const cameraButton = tr.querySelector('.btn-camera-capture');
            if (cameraButton) {
                cameraButton.addEventListener('click', (e) => {
                    e.stopPropagation();
                    captureSingleScreenshot(item.tracking_number, item.courier, cameraButton);
                });
            }

            // Bind timeline view handlers
            const awbBadge = tr.querySelector('.clickable-awb');
            if (awbBadge) {
                awbBadge.addEventListener('click', () => openTimelineModal(item));
            }
            const timelineBtn = tr.querySelector('.btn-timeline-view');
            if (timelineBtn) {
                timelineBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    openTimelineModal(item);
                });
            }

            tableBody.appendChild(tr);
        });

        lucide.createIcons();
        updateSelectionUI();
    }

    function updateStatsUI() {
        statTotal.textContent = state.stats.total || 0;
        statDelivered.textContent = state.stats.delivered || 0;
        statTransit.textContent = state.stats.transit || 0;
        statFailed.textContent = state.stats.failed || 0;
        statApi.textContent = state.stats.api_calls || 0;
    }

    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    // --- Auto-load latest data on page refresh if sessionStorage was empty ---
    async function loadLatestData() {
        try {
            const res = await fetch('/api/latest');
            if (!res.ok) return;
            const data = await res.json();
            if (data.task_id && data.shipments && data.shipments.length > 0) {
                state.taskId = data.task_id;
                state.shipments = data.shipments;
                state.stats = data.stats;
                state.filteredShipments = [...state.shipments];
                state.currentPage = 1;
                updateStatsUI();
                renderCurrentPage();
                exportBtn.disabled = false;
                clearAllBtn.disabled = false;
                startTrackingBtn.disabled = false;
                saveSessionState();
            }
        } catch (e) {
            console.log('No previous data to restore from server.');
        }
    }

    // --- Quick Track Single AWB Handler ---
    const quickAwbInput = document.getElementById('quick-awb-input');
    const quickCourierSelect = document.getElementById('quick-courier-select');
    const quickTrackBtn = document.getElementById('quick-track-btn');

    quickTrackBtn.addEventListener('click', async () => {
        const awb = quickAwbInput.value.trim();
        const courier = quickCourierSelect.value;

        if (!awb) {
            alert('Please enter an AWB number.');
            return;
        }
        if (!courier) {
            alert('Please select a courier partner.');
            return;
        }

        const originalBtnHtml = quickTrackBtn.innerHTML;
        quickTrackBtn.innerHTML = `<span class="duo-spinner btn-duo-spinner"></span> Syncing...`;
        quickTrackBtn.disabled = true;

        const reqPayload = {
            tracking_number: awb,
            courier: courier,
            capture_screenshot: !!state.quickCaptureScreenshot
        };
        console.log(`%c[QUICK TRACK REQUEST] >>> ${courier} | ${awb}`, 'color: #2563eb; font-weight: bold; font-size: 12px;', reqPayload);

        try {
            const res = await fetch('/api/track/query_single', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(reqPayload)
            });

            if (!res.ok) {
                const errData = await res.json();
                console.error(`%c[QUICK TRACK ERROR] <<< ${courier} | ${awb}`, 'color: #ef4444; font-weight: bold;', errData);
                throw new Error(errData.detail || 'Failed to query AWB');
            }

            const data = await res.json();
            console.log(`%c[QUICK TRACK RESPONSE] <<< ${courier} | ${awb}`, 'color: #16a34a; font-weight: bold; font-size: 12px;', data);

            currentSingleResult = data;

            // Update API Hits counter in state and UI
            state.stats.api_calls = data.api_calls;
            statApi.textContent = data.api_calls;

            // Clear inputs
            quickAwbInput.value = '';
            quickCourierSelect.value = '';

            // Update shipment in table if present, or add to table so user can view/export/download screenshot
            const existingIdx = (state.shipments || []).findIndex(s => s.tracking_number === data.tracking_number);
            if (existingIdx !== -1) {
                state.shipments[existingIdx].status = data.status || state.shipments[existingIdx].status;
                state.shipments[existingIdx].last_location = data.last_location || state.shipments[existingIdx].last_location;
                state.shipments[existingIdx].timestamp = data.timestamp || state.shipments[existingIdx].timestamp;
                if (data.screenshot && data.screenshot !== '-') {
                    state.shipments[existingIdx].screenshot = data.screenshot;
                }
                if (data.events && data.events.length > 0) {
                    state.shipments[existingIdx].events = data.events;
                }
                state.shipments[existingIdx].last_sync = 'Just now';
                recalculateStats();
                applyFilters(false);
                saveSessionState();
            } else if (state.shipments && state.shipments.length > 0) {
                state.shipments.unshift({
                    channel: 'Quick Track',
                    seller_name: '-',
                    return_date: '-',
                    mp_date: '-',
                    days_left: '-',
                    invoice_no: '-',
                    tracking_number: data.tracking_number,
                    courier: data.courier,
                    platform_status: '-',
                    status: data.status,
                    last_location: data.last_location || 'Pending scan',
                    timestamp: data.timestamp || '-',
                    last_sync: 'Just now',
                    screenshot: data.screenshot || '-',
                    events: data.events || []
                });
                recalculateStats();
                applyFilters(false);
                saveSessionState();
            }
            updateDownloadImagesVisibility();

            // Populate and show Result Modal
            document.getElementById('res-awb').textContent = data.tracking_number;
            
            // Courier Badge
            const resCourier = document.getElementById('res-courier');
            resCourier.innerHTML = `<span class="courier-badge ${getCourierBadgeClass(data.courier)}">${data.courier}</span>`;
            
            // Status Badge
            const statusKey = data.status.toLowerCase().replace(/[\s_]+/g, '_');
            let badgeClass = 'badge-pending';
            if (statusKey === 'delivered') badgeClass = 'badge-delivered';
            else if (statusKey.includes('transit') || statusKey.includes('picked') || statusKey.includes('out_for')) badgeClass = 'badge-transit';
            else if (statusKey === 'exception' || statusKey.includes('fail') || statusKey.includes('error') || statusKey.includes('invalid') || statusKey.includes('not_found') || statusKey.includes('not found')) badgeClass = 'badge-exception';
            
            const resStatus = document.getElementById('res-status');
            resStatus.innerHTML = `<span class="badge ${badgeClass}">${data.status}</span>`;
            
            document.getElementById('res-location').textContent = data.last_location || 'Pending scan';
            document.getElementById('res-timestamp').textContent = data.timestamp || '-';
            
            // Populate screenshot and preview image if available
            const resScreenshot = document.getElementById('res-screenshot');
            const previewRow = document.getElementById('res-screenshot-preview-row');
            const previewImg = document.getElementById('res-screenshot-img');
            
            const hasScreenshot = data.screenshot && data.screenshot !== '-';
            if (hasScreenshot) {
                const freshUrl = `${data.screenshot.split('?')[0]}?t=${Date.now()}`;
                resScreenshot.innerHTML = `<a href="${freshUrl}" target="_blank" class="gallery-icon-link has-screenshot" title="View & Download Screenshot"><img src="/static/gallery_icon_blue.png?v=3.4.0" alt="Screenshot Available"></a>`;
                previewImg.src = freshUrl;
                previewRow.style.display = 'flex';
            } else {
                resScreenshot.innerHTML = `<span class="gallery-icon-link no-screenshot" title="No screenshot captured (Fast Track)"><img src="/static/gallery_icon_red.png?v=3.4.0" alt="No Screenshot"></span>`;
                previewImg.src = '';
                previewRow.style.display = 'none';
            }
            
            // Show modal
            resultModal.style.display = 'flex';
            lucide.createIcons();

        } catch (error) {
            showAlert(`Error: ${error.message}`, 'error', 'Tracking Error');
        } finally {
            quickTrackBtn.innerHTML = originalBtnHtml;
            quickTrackBtn.disabled = false;
        }
    });

    // Result Modal close handlers
    const resultModal = document.getElementById('result-modal');
    const resModalCloseX = document.getElementById('result-modal-close-x');
    const resModalCloseBtn = document.getElementById('result-modal-close-btn');

    function closeResultModal() {
        resultModal.style.display = 'none';
    }

    resModalCloseX.addEventListener('click', closeResultModal);
    resModalCloseBtn.addEventListener('click', closeResultModal);
    resultModal.addEventListener('click', (e) => {
        if (e.target === resultModal) {
            closeResultModal();
        }
    });

    if (resViewTimelineBtn) {
        resViewTimelineBtn.addEventListener('click', () => {
            if (currentSingleResult) {
                closeResultModal();
                openTimelineModal(currentSingleResult);
            }
        });
    }

    // --- Timeline Modal Handlers ---
    function closeTimelineModal() {
        if (timelineModal) timelineModal.style.display = 'none';
    }

    if (timelineModalCloseX) timelineModalCloseX.addEventListener('click', closeTimelineModal);
    if (timelineModalCloseBtn) timelineModalCloseBtn.addEventListener('click', closeTimelineModal);
    if (timelineModal) {
        timelineModal.addEventListener('click', (e) => {
            if (e.target === timelineModal) closeTimelineModal();
        });
    }

    async function openTimelineModal(item) {
        if (!timelineModal || !item) return;

        timelineSubtitle.textContent = `AWB: ${item.tracking_number} | Courier: ${item.courier}`;

        // Status badge
        const statusKey = (item.status || '').toLowerCase().replace(/[\s_]+/g, '_');
        let badgeClass = 'badge-pending';
        if (statusKey === 'delivered') badgeClass = 'badge-delivered';
        else if (['in_transit', 'in transit', 'picked_up', 'out_for_delivery', 'out for delivery', 'out_for_pickup'].includes(statusKey)) badgeClass = 'badge-transit';
        else if (statusKey === 'exception' || statusKey.includes('fail') || statusKey.includes('error') || statusKey.includes('invalid') || statusKey.includes('not_found') || statusKey.includes('not found')) badgeClass = 'badge-exception';

        timelineStatusBadge.innerHTML = `<span class="badge ${badgeClass}">${item.status || 'Pending'}</span>`;
        timelineLocation.textContent = item.last_location || 'Pending scan';
        timelineTime.textContent = item.timestamp || '-';

        // Screenshot preview
        if (item.screenshot && item.screenshot !== '-') {
            timelineScreenshotBox.style.display = 'flex';
            timelineScreenshotLink.href = item.screenshot;
        } else {
            timelineScreenshotBox.style.display = 'none';
        }

        // Check if events are already available
        let events = item.events || [];
        if (!events || events.length === 0) {
            // Show loading in timeline
            timelineEventsList.innerHTML = `
                <div style="text-align: center; padding: 25px; color: var(--text-muted);">
                    <div><span class="duo-spinner modal-duo-spinner"></span></div>
                    <div style="margin-top: 8px; font-weight: 500;">Loading tracking journey...</div>
                </div>
            `;
            timelineModal.style.display = 'flex';

            try {
                const res = await fetch(`/api/track/events/${encodeURIComponent(item.tracking_number)}`);
                if (res.ok) {
                    const data = await res.json();
                    events = data.events || [];
                    item.events = events;
                    if (data.status) item.status = data.status;
                    if (data.last_location) {
                        item.last_location = data.last_location;
                        timelineLocation.textContent = data.last_location;
                    }
                    if (data.timestamp) {
                        item.timestamp = data.timestamp;
                        timelineTime.textContent = data.timestamp;
                    }
                    if (data.screenshot && data.screenshot !== '-') {
                        item.screenshot = data.screenshot;
                        timelineScreenshotBox.style.display = 'flex';
                        timelineScreenshotLink.href = data.screenshot;
                    }
                }
            } catch (e) {
                console.warn('Failed to fetch events:', e);
            }
        }

        renderTimelineEvents(item, events);
        timelineModal.style.display = 'flex';
        lucide.createIcons();
    }

    function renderTimelineEvents(item, events) {
        if (!timelineEventsList) return;
        
        if (events && events.length > 0) {
            let html = '';
            events.forEach((ev, idx) => {
                const isLatest = idx === 0;
                html += `
                    <div class="timeline-event-item ${isLatest ? 'is-latest' : ''}">
                        <div class="timeline-event-dot">
                            ${isLatest ? '<i data-lucide="check" style="width:12px;height:12px;color:#fff;"></i>' : ''}
                        </div>
                        <div class="timeline-event-body">
                            <div class="timeline-event-title">${ev.status || 'Status Update'}</div>
                            <div class="timeline-event-meta">
                                <span><i data-lucide="clock" style="width:13px;height:13px;vertical-align:middle;"></i> ${ev.time || '-'}</span>
                                ${ev.location ? `<span class="timeline-event-location"><i data-lucide="map-pin" style="width:13px;height:13px;vertical-align:middle;"></i> ${ev.location}</span>` : ''}
                            </div>
                        </div>
                    </div>
                `;
            });
            timelineEventsList.innerHTML = html;
        } else {
            // Render single milestone card if no detailed checkpoints
            timelineEventsList.innerHTML = `
                <div class="timeline-event-item is-latest">
                    <div class="timeline-event-dot">
                        <i data-lucide="package" style="width:12px;height:12px;color:#fff;"></i>
                    </div>
                    <div class="timeline-event-body">
                        <div class="timeline-event-title">${item.status || 'Status Update'}</div>
                        <div class="timeline-event-meta">
                            <span><i data-lucide="clock" style="width:13px;height:13px;vertical-align:middle;"></i> ${item.timestamp || '-'}</span>
                            <span class="timeline-event-location"><i data-lucide="map-pin" style="width:13px;height:13px;vertical-align:middle;"></i> ${item.last_location || 'No scan records yet'}</span>
                        </div>
                    </div>
                </div>
            `;
        }
        lucide.createIcons();
    }

    // Floating Excel-like Dropdown logic
    let activeDropdown = null;

    document.addEventListener('click', (e) => {
        if (activeDropdown && !activeDropdown.contains(e.target) && !e.target.closest('.header-filter-btn')) {
            closeActiveDropdown();
        }
    });

    function closeActiveDropdown() {
        if (activeDropdown) {
            activeDropdown.remove();
            activeDropdown = null;
        }
    }

    // Setup Column Header Filter Triggers
    document.querySelectorAll('.header-filter-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const th = btn.closest('th');
            const colKey = th.getAttribute('data-col');
            
            if (activeDropdown && activeDropdown.getAttribute('data-col') === colKey) {
                closeActiveDropdown();
                return;
            }
            
            closeActiveDropdown();
            openFilterDropdown(btn, colKey);
        });
    });

    function openFilterDropdown(btn, colKey) {
        // Get all distinct values of this column from state.shipments
        let allValues = state.shipments.map(item => {
            let val = item[colKey] || '';
            if (colKey === 'screenshot') {
                return (item.screenshot && item.screenshot !== '-') ? 'Has Image' : 'No Image';
            } else if (colKey === 'invoice_no' || colKey === 'platform_status' || colKey === 'channel' || colKey === 'seller_name' || colKey === 'return_date' || colKey === 'mp_date' || colKey === 'days_left') {
                return val || '-';
            } else if (colKey === 'last_location') {
                return val || 'Pending scan';
            } else if (colKey === 'timestamp' || colKey === 'last_sync') {
                return val || '-';
            }
            return String(val).trim();
        });
        
        // Remove duplicates and sort
        let uniqueValues = [...new Set(allValues)].filter(v => v !== '').sort((a, b) => {
            if (a === '-' || a === 'Pending scan') return 1;
            if (b === '-' || b === 'Pending scan') return -1;
            return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
        });
        
        // If no data
        if (uniqueValues.length === 0) {
            uniqueValues = ['No data'];
        }
        
        const activeSelections = state.activeColumnFilters[colKey] || [];
        
        const dropdown = document.createElement('div');
        dropdown.className = 'excel-filter-dropdown';
        dropdown.setAttribute('data-col', colKey);
        
        let dropdownHtml = `
            <div class="excel-filter-search-container">
                <input type="text" class="excel-filter-search" placeholder="Search values...">
            </div>
            <div class="excel-filter-list">
                <label class="excel-filter-item select-all-item">
                    <input type="checkbox" id="filter-select-all" ${activeSelections.length === 0 || activeSelections.length === uniqueValues.length ? 'checked' : ''}>
                    <span class="excel-filter-item-label" style="font-weight: 600;">(Select All)</span>
                </label>
        `;
        
        uniqueValues.forEach(val => {
            const isChecked = activeSelections.length === 0 || activeSelections.includes(val);
            dropdownHtml += `
                <label class="excel-filter-item val-item">
                    <input type="checkbox" class="excel-filter-val-cb" value="${val}" ${isChecked ? 'checked' : ''}>
                    <span class="excel-filter-item-label" title="${val}">${val}</span>
                </label>
            `;
        });
        
        dropdownHtml += `
            </div>
            <div class="excel-filter-actions">
                <button class="excel-filter-btn excel-filter-clear">Clear</button>
                <button class="excel-filter-btn excel-filter-apply">OK</button>
            </div>
        `;
        
        dropdown.innerHTML = dropdownHtml;
        document.body.appendChild(dropdown);
        activeDropdown = dropdown;
        
        // Position dropdown
        const btnRect = btn.getBoundingClientRect();
        const dropdownWidth = 250;
        let leftPos = btnRect.left + window.scrollX;
        if (leftPos + dropdownWidth > window.innerWidth) {
            leftPos = window.innerWidth - dropdownWidth - 10;
        }
        dropdown.style.top = `${btnRect.bottom + window.scrollY + 5}px`;
        dropdown.style.left = `${leftPos}px`;
        
        const searchInput = dropdown.querySelector('.excel-filter-search');
        const valItems = dropdown.querySelectorAll('.excel-filter-item.val-item');
        const selectAllCb = dropdown.querySelector('#filter-select-all');
        
        searchInput.focus();
        
        searchInput.addEventListener('input', () => {
            const query = searchInput.value.toLowerCase().trim();
            valItems.forEach(item => {
                const text = item.querySelector('.excel-filter-item-label').textContent.toLowerCase();
                if (text.includes(query)) {
                    item.style.display = 'flex';
                } else {
                    item.style.display = 'none';
                }
            });
        });
        
        selectAllCb.addEventListener('change', () => {
            const isChecked = selectAllCb.checked;
            valItems.forEach(item => {
                if (item.style.display !== 'none') {
                    item.querySelector('input').checked = isChecked;
                }
            });
        });
        
        dropdown.querySelectorAll('.excel-filter-val-cb').forEach(cb => {
            cb.addEventListener('change', () => {
                const visibleCbs = Array.from(dropdown.querySelectorAll('.excel-filter-val-cb')).filter(c => c.closest('.excel-filter-item').style.display !== 'none');
                const checkedVisible = visibleCbs.filter(c => c.checked);
                selectAllCb.checked = (checkedVisible.length === visibleCbs.length);
            });
        });
        
        dropdown.querySelector('.excel-filter-apply').addEventListener('click', () => {
            const checkedValues = Array.from(dropdown.querySelectorAll('.excel-filter-val-cb'))
                .filter(cb => cb.checked)
                .map(cb => cb.value);
                
            if (checkedValues.length === uniqueValues.length || checkedValues.length === 0) {
                state.activeColumnFilters[colKey] = [];
            } else {
                state.activeColumnFilters[colKey] = checkedValues;
            }
            
            closeActiveDropdown();
            applyFilters(true);
            saveSessionState();
        });
        
        dropdown.querySelector('.excel-filter-clear').addEventListener('click', () => {
            state.activeColumnFilters[colKey] = [];
            closeActiveDropdown();
            applyFilters(true);
            saveSessionState();
        });
    }

    // Initialize State on Page Load (restore from session storage first)
    restoreSessionState().then(hasSession => {
        if (!hasSession) {
            loadLatestData();
        }
    });
});
