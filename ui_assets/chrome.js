
    (function initWebforgeChrome() {
        try {
            var pdoc = window.parent.document;
            var pwin = window.parent;
            var html = pdoc.documentElement;
            if (!pdoc.body) {
                pwin.setTimeout(initWebforgeChrome, 50);
                return;
            }
            // Every listener this script hangs on the PARENT page goes through
            // `bind`. Reason: this script lives in a components.html iframe, and
            // a full st.rerun() (sending a message, opening a thread, New chat)
            // destroys that iframe and builds a fresh one. Listeners registered
            // by the dead iframe never fire again, yet a once-only flag stored
            // on the parent window ("already bound") survived the rebuild and
            // told the new iframe to skip binding. That is how the annotation
            // marker stopped being attached after the first rerun (found live,
            // 2026-09-14: 5 of 6 modify requests reached the orchestrator with
            // no marker), and it silently killed the panel resizers too. `bind`
            // records each listener under a key on the parent, removes the
            // previous copy, and adds the live one, so a rebuild rebinds.
            var listenerRegistry = pwin.__wfChromeListeners || (pwin.__wfChromeListeners = {});
            var bind = function(key, target, type, fn, opts) {
                var prev = listenerRegistry[key];
                if (prev) {
                    try { prev.target.removeEventListener(prev.type, prev.fn, prev.opts); } catch (e) {}
                }
                target.addEventListener(type, fn, opts);
                listenerRegistry[key] = { target: target, type: type, fn: fn, opts: opts };
            };
            html.classList.remove('dark', 'light');
            html.classList.add('dark');
            try {
                // The left panel always starts CLOSED on every load. The user
                // opens it with the edge chevron. We intentionally ignore any
                // saved "open" so a fresh page always begins collapsed.
                html.classList.add('sidebar-collapsed');
            } catch (e) {}
            try {
                var previewState = pwin.localStorage.getItem('webforge-preview-panel');
                if (previewState === 'open') {
                    html.classList.add('webforge-preview-open');
                } else {
                    html.classList.remove('webforge-preview-open');
                }
            } catch (e) {}
            var clamp = function(value, min, max) {
                return Math.min(Math.max(value, min), max);
            };
            var readPxVar = function(name, fallback) {
                var raw = pwin.getComputedStyle(html).getPropertyValue(name);
                var parsed = parseFloat(raw);
                return Number.isFinite(parsed) ? parsed : fallback;
            };
            var minMain = function() {
                return Math.min(420, Math.max(120, Math.round(pwin.innerWidth * 0.30)));
            };
            var sidebarMin = 220;
            var sidebarMaxW = function() {
                // Left sidebar drags at most to 35% of the window.
                return Math.max(sidebarMin, Math.round(pwin.innerWidth * 0.35));
            };
            var previewMin = 360;
            var pctWidth = function(fraction) {
                return Math.round(pwin.innerWidth * fraction);
            };
            var PANEL_DEFAULT_FRACTION = 0.25;  // both panels open at 25% of the window
            var currentSidebarWidth = function() {
                var collapsed = html.classList.contains('sidebar-collapsed');
                var input = pdoc.getElementById('uigpt-sidebar-toggle-input');
                if (input) {
                    collapsed = !input.checked;
                }
                return collapsed
                    ? readPxVar('--uigpt-sidebar-w-collapsed', 64)
                    : readPxVar('--uigpt-sidebar-w-expanded', 260);
            };
            var maxPreviewWidth = function(sidebarWidth) {
                // The right preview panel may be dragged all the way to full
                // screen (it is position:fixed and covers the whole window at
                // 100vw). The maximize button is a one-click shortcut for the
                // same, and remembers the previous width to restore.
                return Math.max(previewMin, pwin.innerWidth);
            };
            var applySavedPanelWidths = function() {
                // Saved widths win; otherwise both panels default to 25% of the
                // window. Saved values are re-clamped to the current ranges so
                // an old width from a wider window never overflows.
                try {
                    var sidebar = parseFloat(pwin.localStorage.getItem('webforge-sidebar-width'));
                    var sidebarW = Number.isFinite(sidebar)
                        ? clamp(sidebar, sidebarMin, sidebarMaxW())
                        : clamp(pctWidth(PANEL_DEFAULT_FRACTION), sidebarMin, sidebarMaxW());
                    html.style.setProperty('--uigpt-sidebar-w-expanded', sidebarW + 'px');
                } catch (e) {}
                try {
                    var preview = parseFloat(pwin.localStorage.getItem('webforge-preview-width:v2'));
                    var previewMaxForWindow = maxPreviewWidth(currentSidebarWidth());
                    var previewW = Number.isFinite(preview)
                        ? clamp(preview, previewMin, previewMaxForWindow)
                        : clamp(pctWidth(PANEL_DEFAULT_FRACTION), previewMin, previewMaxForWindow);
                    html.style.setProperty('--webforge-preview-panel-w', previewW + 'px');
                } catch (e) {}
            };
            var clampPanelWidthsToWindow = function() {
                var sidebarWidth = readPxVar('--uigpt-sidebar-w-expanded', 260);
                var sidebarMaxNow = sidebarMaxW();
                if (sidebarWidth > sidebarMaxNow) {
                    html.style.setProperty('--uigpt-sidebar-w-expanded', sidebarMaxNow + 'px');
                    try { pwin.localStorage.setItem('webforge-sidebar-width', String(sidebarMaxNow)); } catch (e) {}
                }
                var previewWidth = readPxVar('--webforge-preview-panel-w', 380);
                var previewMaxForWindow = maxPreviewWidth(currentSidebarWidth());
                if (previewWidth > previewMaxForWindow) {
                    html.style.setProperty('--webforge-preview-panel-w', previewMaxForWindow + 'px');
                    try { pwin.localStorage.setItem('webforge-preview-width:v2', String(previewMaxForWindow)); } catch (e) {}
                }
            };
            // --- Right preview panel: maximize / restore ---------------------
            // The button lives in the panel header (top-right, beside the
            // Preview/Select control). Expand = arrows out; it sets the panel
            // to the full window width. Collapse = arrows in; it restores the
            // width the panel had before it was maximized.
            var PREVIEW_EXPAND_SVG =
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                '<polyline points="15 3 21 3 21 9"></polyline>' +
                '<polyline points="9 21 3 21 3 15"></polyline>' +
                '<line x1="21" y1="3" x2="14" y2="10"></line>' +
                '<line x1="3" y1="21" x2="10" y2="14"></line></svg>';
            var PREVIEW_COLLAPSE_SVG =
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                '<polyline points="4 14 10 14 10 20"></polyline>' +
                '<polyline points="20 10 14 10 14 4"></polyline>' +
                '<line x1="14" y1="10" x2="21" y2="3"></line>' +
                '<line x1="10" y1="14" x2="3" y2="21"></line></svg>';
            var previewIsMaximized = function() {
                return readPxVar('--webforge-preview-panel-w', 380) >= pwin.innerWidth - 2;
            };
            var updateMaximizeIcon = function() {
                var full = previewIsMaximized();
                // When the preview fills the screen, hide the sidebar logo and
                // its (now covered) drag handle so nothing overlaps the panel
                // header. Restoring the width brings them back.
                html.classList.toggle('webforge-preview-maximized', full);
                var btn = pdoc.getElementById('webforge-maximize-btn');
                if (!btn) return;
                btn.innerHTML = full ? PREVIEW_COLLAPSE_SVG : PREVIEW_EXPAND_SVG;
                var lbl = full ? 'Restore preview size' : 'Maximize preview';
                btn.setAttribute('aria-label', lbl);
                btn.title = lbl;
                btn.classList.toggle('is-maximized', full);
            };
            var setPreviewPanelWidthPx = function(w) {
                var maxAllowed = maxPreviewWidth(currentSidebarWidth());
                w = clamp(w, previewMin, maxAllowed);
                html.style.setProperty('--webforge-preview-panel-w', w + 'px');
                try { pwin.localStorage.setItem('webforge-preview-width:v2', String(w)); } catch (e) {}
                updateMaximizeIcon();
            };
            var togglePreviewMaximize = function() {
                if (previewIsMaximized()) {
                    var prev = parseFloat(pwin.localStorage.getItem('webforge-preview-width-prev'));
                    if (!Number.isFinite(prev)) prev = pctWidth(PANEL_DEFAULT_FRACTION);
                    setPreviewPanelWidthPx(prev);
                } else {
                    try { pwin.localStorage.setItem('webforge-preview-width-prev', String(readPxVar('--webforge-preview-panel-w', 380))); } catch (e) {}
                    setPreviewPanelWidthPx(pwin.innerWidth);
                }
            };
            var ensurePreviewMaximizeBtn = function() {
                var panel = pdoc.querySelector('.st-key-webforge_preview_panel');
                if (!panel) return;
                var btn = pdoc.getElementById('webforge-maximize-btn');
                if (!btn) {
                    btn = pdoc.createElement('button');
                    btn.id = 'webforge-maximize-btn';
                    btn.type = 'button';
                    btn.className = 'webforge-maximize-btn';
                    btn.addEventListener('click', function(evt) {
                        evt.preventDefault();
                        evt.stopPropagation();
                        togglePreviewMaximize();
                    });
                }
                if (btn.parentElement !== panel) {
                    panel.appendChild(btn);
                }
                updateMaximizeIcon();
            };
            // Keep the Preview/Select sliding pill in sync with the actually
            // active segment. Called after every rerun (the buttons are rebuilt
            // each mode switch); it writes the active index onto the track,
            // which persists, so the pill's transform transition animates.
            var syncPreviewModePill = function() {
                var group = pdoc.querySelector('.st-key-webforge_preview_panel [data-testid="stButtonGroup"]');
                if (!group) return;
                var track = group.querySelector(':scope > div');
                if (!track) return;
                var btns = track.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    if ((btns[i].getAttribute('data-testid') || '').indexOf('controlActive') >= 0) {
                        track.dataset.wfActive = String(i);
                        break;
                    }
                }
                // Streamlit inserts the two buttons first and only marks the active
                // one with data-testid="...controlActive" a tick LATER, as an
                // ATTRIBUTE change. The outer toggle observer watches childList
                // additions only, so it misses that flip and the pill would stay on
                // the previous segment (pill on Preview while the model is Select ->
                // Select gets the dark on-pill text with no pill under it, invisible).
                // Watch this group's attributes directly -- cheap, one small node --
                // so the pill follows controlActive whenever Streamlit moves it.
                if (!group.dataset.wfActiveObs) {
                    group.dataset.wfActiveObs = '1';
                    try {
                        var ao = new pwin.MutationObserver(function() {
                            var t = group.querySelector(':scope > div');
                            if (!t) return;
                            var bs = t.querySelectorAll('button');
                            for (var k = 0; k < bs.length; k++) {
                                if ((bs[k].getAttribute('data-testid') || '').indexOf('controlActive') >= 0) {
                                    t.dataset.wfActive = String(k);
                                    return;
                                }
                            }
                        });
                        ao.observe(group, { attributes: true, attributeFilter: ['data-testid'], subtree: true });
                    } catch (e) {}
                }
            };
            // --- Preview status: loading overlay + floating bubble -----------
            // pwin.webforgeSetPreviewState('loading'|'ready'|'idle') drives a
            // spinner overlay inside the panel and an orange (loading) / green
            // (ready) bubble beside it. The empty state is server-rendered. The
            // backend will call this once it emits a generating / ready signal;
            // until then it is the hook used to preview each state by hand.
            var previewNoticeTimer = null;
            var positionPreviewBubble = function() {
                var bubble = pdoc.getElementById('webforge-preview-bubble');
                if (!bubble) return;
                var open = !!pdoc.querySelector('#webforge-preview-toggle-input:checked');
                var right = open ? (readPxVar('--webforge-preview-panel-w', 380) + 16) : 66;
                right = Math.min(right, pwin.innerWidth - 60);
                bubble.style.right = right + 'px';
            };
            var ensurePreviewStatusEls = function() {
                if (!pdoc.getElementById('webforge-preview-bubble')) {
                    var b = pdoc.createElement('div');
                    b.id = 'webforge-preview-bubble';
                    b.className = 'webforge-preview-bubble';
                    b.innerHTML = '<span class="wf-bubble-dot"></span><span class="wf-bubble-txt"></span>';
                    // The bubble has no time limit: it stays until the user clicks
                    // it, then it dismisses. Nothing else hides it.
                    b.style.cursor = 'pointer';
                    b.title = 'Click to dismiss';
                    b.addEventListener('click', function () {
                        html.setAttribute('data-preview-notice', 'idle');
                    });
                    (pdoc.body || pdoc.documentElement).appendChild(b);
                }
                var panel = pdoc.querySelector('.st-key-webforge_preview_panel');
                if (panel && !panel.querySelector('.webforge-preview-loading-overlay')) {
                    var s = pdoc.createElement('div');
                    s.className = 'webforge-preview-loading-overlay';
                    s.innerHTML = '<div class="wf-spinner"></div>' +
                        '<div class="wf-loading-txt">The preview of the web app is loading</div>';
                    panel.appendChild(s);
                }
                var pinput = pdoc.getElementById('webforge-preview-toggle-input');
                if (pinput && !pinput.dataset.wfBubbleBound) {
                    pinput.addEventListener('change', positionPreviewBubble);
                    pinput.dataset.wfBubbleBound = '1';
                }
                positionPreviewBubble();
            };
            pwin.webforgeSetPreviewState = function(state) {
                if (state !== 'loading' && state !== 'ready') state = 'idle';
                ensurePreviewStatusEls();
                if (previewNoticeTimer) { pwin.clearTimeout(previewNoticeTimer); previewNoticeTimer = null; }
                if (state === 'ready') {
                    var input = pdoc.getElementById('webforge-preview-toggle-input');
                    if (input && !input.checked) {
                        input.checked = true;
                        input.dispatchEvent(new pwin.Event('change', { bubbles: true }));
                    }
                }
                html.setAttribute('data-preview-notice', state);
                var bubble = pdoc.getElementById('webforge-preview-bubble');
                if (bubble) {
                    bubble.classList.toggle('is-ready', state === 'ready');
                    var txt = bubble.querySelector('.wf-bubble-txt');
                    if (txt) {
                        txt.textContent = state === 'ready' ? 'The preview is ready'
                            : (state === 'loading' ? 'The preview is loading...' : '');
                    }
                }
                // No auto-hide timer: the green "ready" bubble has no time limit
                // and is dismissed only by clicking it (handler in
                // ensurePreviewStatusEls).
                positionPreviewBubble();
            };
            // (The previous "click the panel to dismiss the notice" handler was
            // removed: the bubble now has no time limit and is dismissed only by
            // clicking the bubble itself.)
            // Slide the Preview/Select pill the instant a segment is clicked,
            // before Streamlit's rerun rebuilds the buttons. Setting the active
            // index on the persistent track starts the transform transition now;
            // syncPreviewModePill() re-affirms the same value after the rerun.
            bind('previewPill.click', pdoc, 'click', function(evt) {
                var btn = evt.target && evt.target.closest
                    ? evt.target.closest('.st-key-webforge_preview_panel [data-testid="stButtonGroup"] button')
                    : null;
                if (!btn) return;
                var group = btn.closest('[data-testid="stButtonGroup"]');
                var track = group ? group.querySelector(':scope > div') : null;
                if (!track) return;
                var btns = track.querySelectorAll('button');
                var clickedIndex = -1;
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i] === btn) { clickedIndex = i; track.dataset.wfActive = String(i); break; }
                }
                // Leaving Preview for Select (index 1): play the toolbar's
                // exit animation now, before the rerun swaps the iframe out.
                if (clickedIndex === 1) {
                    try {
                        var frames = pdoc.querySelectorAll('.st-key-webforge_preview_panel iframe');
                        for (var f = 0; f < frames.length; f++) {
                            var idoc = null;
                            try { idoc = frames[f].contentDocument; } catch (e) { idoc = null; }
                            if (!idoc) continue;
                            var bar = idoc.querySelector('.bar');
                            if (bar) bar.classList.add('wf-exiting');
                        }
                    } catch (e) {}
                }
            }, true);
            applySavedPanelWidths();
            clampPanelWidthsToWindow();
            pwin.toggleUigptTheme = function() {
                var h = pwin.document.documentElement;
                h.classList.remove('light');
                h.classList.add('dark');
            };
            pwin.toggleUigptSidebar = function() {
                var h = pwin.document.documentElement;
                h.classList.toggle('sidebar-collapsed');
                try {
                    pwin.localStorage.setItem(
                        'webforge-sidebar',
                        h.classList.contains('sidebar-collapsed') ? 'collapsed' : 'open'
                    );
                } catch (e) {}
            };
            pwin.toggleWebforgePreviewPanel = function() {
                var h = pwin.document.documentElement;
                h.classList.toggle('webforge-preview-open');
                try {
                    pwin.localStorage.setItem(
                        'webforge-preview-panel',
                        h.classList.contains('webforge-preview-open') ? 'open' : 'closed'
                    );
                } catch (e) {}
            };
            pwin.setUigptStreamLock = function(locked) {
                html.classList.toggle('uigpt-stream-locked', !!locked);
            };
            pwin.setUigptStreamLock(false);
            pwin.attachWebforgeAnnotationBridge = function() {
                var storageKey = 'webforge-modification-annotation:v1';
                // The thread this page is showing, as pinned in the URL by the
                // app (st.query_params["t"]). An annotation is only valid for
                // the thread it was made in: localStorage is per site, not per
                // thread, and it survives a reload, so without this check an
                // annotation armed in one conversation would silently turn the
                // next message in another conversation into a modify request.
                var currentThread = function() {
                    try {
                        return new pwin.URLSearchParams(pwin.location.search).get('t') || '';
                    } catch (e) {
                        return '';
                    }
                };
                var readAnnotation = function() {
                    try {
                        var raw = pwin.localStorage.getItem(storageKey);
                        if (!raw) return null;
                        var payload = JSON.parse(raw);
                        if (!payload || !payload.marker) return null;
                        if (!payload.thread || payload.thread !== currentThread()) {
                            // Made for another thread (or by an older build that
                            // recorded no thread): drop it rather than apply it.
                            try { pwin.localStorage.removeItem(storageKey); } catch (e) {}
                            return null;
                        }
                        return payload;
                    } catch (e) {
                        return null;
                    }
                };
                var setNativeValue = function(textarea, value) {
                    var setter = Object.getOwnPropertyDescriptor(
                        pwin.HTMLTextAreaElement.prototype,
                        'value'
                    );
                    if (setter && setter.set) {
                        setter.set.call(textarea, value);
                    } else {
                        textarea.value = value;
                    }
                    textarea.dispatchEvent(new pwin.Event('input', { bubbles: true }));
                    textarea.dispatchEvent(new pwin.Event('change', { bubbles: true }));
                };
                var chatRootFor = function(target) {
                    if (!target || !target.closest) return null;
                    return target.closest('[data-testid="stChatInput"]');
                };
                var applyAnnotationToInput = function(root) {
                    var annotation = readAnnotation();
                    if (!annotation) return false;
                    var textarea = root && root.querySelector('textarea');
                    if (!textarea) return false;
                    var current = textarea.value || '';
                    if (!current.trim()) return false;
                    if (current.indexOf(annotation.marker) === 0) return true;
                    setNativeValue(textarea, annotation.marker + '\n' + current);
                    return true;
                };
                var clearClientAnnotation = function() {
                    try { pwin.localStorage.removeItem(storageKey); } catch (e) {}
                    try {
                        var chip = pdoc.getElementById('webforgeClientAnnotation');
                        if (chip) chip.remove();
                    } catch (e) {}
                };
                // Keep the chip and the stored annotation in step. The preview
                // panel draws the chip when the user submits the pocket, but a
                // reload or a Streamlit rebuild of the composer drops that DOM
                // while localStorage keeps the payload, leaving an armed
                // annotation nobody can see or remove. Re-drawn here (same
                // markup as the preview's renderParentAnnotation) whenever the
                // payload exists and the chip does not; removed when the payload
                // is gone. Polled briefly because on a fresh load the composer
                // can render after this script runs.
                var syncAnnotationChip = function(attempt) {
                    var annotation = readAnnotation();
                    var chip = pdoc.getElementById('webforgeClientAnnotation');
                    if (!annotation) {
                        if (chip) chip.remove();
                        return;
                    }
                    if (chip) return;
                    var input = pdoc.querySelector('[data-testid="stChatInput"]');
                    if (!input || !input.parentElement) {
                        if ((attempt || 0) < 40) {
                            pwin.setTimeout(function() { syncAnnotationChip((attempt || 0) + 1); }, 200);
                        }
                        return;
                    }
                    chip = pdoc.createElement('div');
                    chip.id = 'webforgeClientAnnotation';
                    chip.className = 'webforge-annotation-chip webforge-client-annotation';
                    chip.title = 'Target: ' + annotation.target_component + ' · instance ' +
                        annotation.target_instance + '\nRequest: ' + annotation.request;
                    chip.innerHTML = '<span>Annotation 1</span>' +
                        '<button type="button" class="wf-anno-x" aria-label="Remove annotation">&times;</button>';
                    input.parentElement.insertBefore(chip, input);
                    var annoX = chip.querySelector('.wf-anno-x');
                    if (annoX) {
                        annoX.addEventListener('click', function(ev) {
                            ev.preventDefault();
                            ev.stopPropagation();
                            clearClientAnnotation();
                        });
                    }
                };
                var submitWithAnnotation = function(root) {
                    if (!root || root.dataset.webforgeAnnotationSubmitting === '1') {
                        return false;
                    }
                    if (!applyAnnotationToInput(root)) return false;
                    root.dataset.webforgeAnnotationSubmitting = '1';
                    var button = root.querySelector('button[data-testid="stChatInputSubmitButton"], button');
                    if (!button) return false;
                    pwin.setTimeout(function() {
                        button.click();
                        pwin.setTimeout(function() {
                            delete root.dataset.webforgeAnnotationSubmitting;
                            clearClientAnnotation();
                        }, 160);
                    }, 35);
                    return true;
                };
                bind('annotationBridge.click', pdoc, 'click', function(evt) {
                    var target = evt.target;
                    if (!target || !target.closest) return;
                    var button = target.closest('button[data-testid="stChatInputSubmitButton"], [data-testid="stChatInput"] button');
                    if (!button) return;
                    var root = chatRootFor(button);
                    if (!root || root.dataset.webforgeAnnotationSubmitting === '1') return;
                    if (submitWithAnnotation(root)) {
                        evt.preventDefault();
                        evt.stopImmediatePropagation();
                    }
                }, true);
                bind('annotationBridge.keydown', pdoc, 'keydown', function(evt) {
                    if (evt.key !== 'Enter' || evt.shiftKey) return;
                    var root = chatRootFor(evt.target);
                    if (!root || root.dataset.webforgeAnnotationSubmitting === '1') return;
                    if (submitWithAnnotation(root)) {
                        evt.preventDefault();
                        evt.stopImmediatePropagation();
                    }
                }, true);
                syncAnnotationChip(0);
            };
            pwin.attachWebforgeAnnotationBridge();
            pwin.initWebforgePanelResizers = function() {
                // A full Streamlit rerun destroys the components iframe that
                // owns the active drag callbacks. If that happens mid-drag,
                // its transparent, full-window overlay can otherwise survive
                // in the parent document and intercept every later click.
                // Always recover the parent document before binding the live
                // listeners for this script instance.
                var staleDragOverlays = pdoc.querySelectorAll('.webforge-drag-overlay');
                for (var staleIdx = 0; staleIdx < staleDragOverlays.length; staleIdx++) {
                    staleDragOverlays[staleIdx].remove();
                }
                html.classList.remove('webforge-resizing');
                var setSidebarWidth = function(clientX) {
                    var sidebarToggle = pdoc.getElementById('uigpt-sidebar-toggle-input');
                    if (sidebarToggle && !sidebarToggle.checked) {
                        var collapsedWidth = readPxVar('--uigpt-sidebar-w-collapsed', 64);
                        if (clientX > collapsedWidth + 16) {
                            sidebarToggle.checked = true;
                            html.classList.remove('sidebar-collapsed');
                            try { pwin.localStorage.setItem('webforge-sidebar', 'open'); } catch (e) {}
                        }
                    }
                    var maxAllowed = sidebarMaxW();
                    var width = clamp(clientX, sidebarMin, maxAllowed);
                    html.style.setProperty('--uigpt-sidebar-w-expanded', width + 'px');
                    try { pwin.localStorage.setItem('webforge-sidebar-width', String(width)); } catch (e) {}
                };
                var setPreviewWidth = function(clientX) {
                    var maxAllowed = maxPreviewWidth(currentSidebarWidth());
                    var width = clamp(pwin.innerWidth - clientX, previewMin, maxAllowed);
                    html.style.setProperty('--webforge-preview-panel-w', width + 'px');
                    try { pwin.localStorage.setItem('webforge-preview-width:v2', String(width)); } catch (e) {}
                    updateMaximizeIcon();
                };
                var dragOverlay = null;
                var showDragOverlay = function() {
                    if (!dragOverlay) {
                        dragOverlay = pdoc.createElement('div');
                        dragOverlay.className = 'webforge-drag-overlay';
                        dragOverlay.style.cssText = 'position:fixed;inset:0;z-index:2147483000;cursor:col-resize;background:transparent;';
                    }
                    if (!dragOverlay.parentNode) pdoc.body.appendChild(dragOverlay);
                };
                var hideDragOverlay = function() {
                    if (dragOverlay && dragOverlay.parentNode) dragOverlay.parentNode.removeChild(dragOverlay);
                };
                var bindHandle = function(selector, setter) {
                    bind('resizer.pointerdown:' + selector, pdoc, 'pointerdown', function(evt) {
                        var target = evt.target;
                        if (!target || !target.closest || !target.closest(selector)) return;
                        var handle = target.closest(selector);
                        evt.preventDefault();
                        html.classList.add('webforge-resizing');
                        showDragOverlay();
                        try { if (handle) handle.setPointerCapture(evt.pointerId); } catch (e) {}
                        var move = function(moveEvt) {
                            setter(moveEvt.clientX);
                        };
                        var stop = function(stopEvt) {
                            if (stopEvt && typeof stopEvt.clientX === 'number') {
                                setter(stopEvt.clientX);
                            }
                            html.classList.remove('webforge-resizing');
                            hideDragOverlay();
                            pwin.removeEventListener('pointermove', move);
                            pwin.removeEventListener('pointerup', stop);
                            pwin.removeEventListener('pointercancel', stop);
                            pwin.removeEventListener('blur', stop);
                        };
                        pwin.addEventListener('pointermove', move);
                        pwin.addEventListener('pointerup', stop, { once: true });
                        pwin.addEventListener('pointercancel', stop, { once: true });
                        // Releasing the mouse outside the browser can skip the
                        // expected pointerup. Window blur is the final cleanup
                        // path so an interrupted drag never freezes the UI.
                        pwin.addEventListener('blur', stop, { once: true });
                    }, true);
                };
                bindHandle('.uigpt-sidebar-resizer', setSidebarWidth);
                bindHandle('.webforge-preview-resizer', setPreviewWidth);
                bind('resizer.windowResize', pwin, 'resize', clampPanelWidthsToWindow);
            };
            pwin.initWebforgePanelResizers();

            var scrollStateKey = 'uigpt-scroll-state:v1';
            var getScrollMetrics = function() {
                var docEl = pdoc.documentElement;
                var body = pdoc.body;
                var scrollY = pwin.scrollY || docEl.scrollTop || body.scrollTop || 0;
                var viewportHeight = pwin.innerHeight || docEl.clientHeight || 0;
                var documentHeight = Math.max(
                    body.scrollHeight || 0,
                    docEl.scrollHeight || 0,
                    body.offsetHeight || 0,
                    docEl.offsetHeight || 0,
                    body.clientHeight || 0,
                    docEl.clientHeight || 0
                );
                return {
                    scrollY: scrollY,
                    viewportHeight: viewportHeight,
                    documentHeight: documentHeight,
                    distanceFromBottom: Math.max(0, documentHeight - (scrollY + viewportHeight))
                };
            };
            var persistScrollState = function() {
                try {
                    var metrics = getScrollMetrics();
                    pwin.sessionStorage.setItem(scrollStateKey, JSON.stringify({
                        scrollY: metrics.scrollY,
                        stickToBottom: metrics.distanceFromBottom < 160
                    }));
                } catch (e) {}
            };
            var restoreScrollState = function() {
                try {
                    var raw = pwin.sessionStorage.getItem(scrollStateKey);
                    if (!raw) return;
                    var saved = JSON.parse(raw);
                    if (!saved || typeof saved.scrollY !== 'number') return;
                    var apply = function() {
                        var metrics = getScrollMetrics();
                        var maxScrollY = Math.max(0, metrics.documentHeight - metrics.viewportHeight);
                        var targetY = saved.stickToBottom
                            ? maxScrollY
                            : Math.min(Math.max(0, saved.scrollY), maxScrollY);
                        pwin.scrollTo(0, targetY);
                    };
                    if (Array.isArray(pwin.__uigptScrollRestoreTimers)) {
                        for (var i = 0; i < pwin.__uigptScrollRestoreTimers.length; i++) {
                            pwin.clearTimeout(pwin.__uigptScrollRestoreTimers[i]);
                        }
                    }
                    var applySoon = function() {
                        pwin.requestAnimationFrame(function() {
                            pwin.requestAnimationFrame(apply);
                        });
                    };
                    pwin.__uigptScrollRestoreTimers = [
                        pwin.setTimeout(applySoon, 0),
                        pwin.setTimeout(apply, 80),
                        pwin.setTimeout(apply, 220),
                        pwin.setTimeout(apply, 500)
                    ];
                } catch (e) {}
            };
            restoreScrollState();
            var scrollTicking = false;
            var scheduleScrollPersist = function() {
                if (scrollTicking) return;
                scrollTicking = true;
                pwin.requestAnimationFrame(function() {
                    scrollTicking = false;
                    persistScrollState();
                });
            };
            bind('scrollState.scroll', pwin, 'scroll', scheduleScrollPersist, { passive: true });
            bind('scrollState.beforeunload', pwin, 'beforeunload', persistScrollState);
            bind('scrollState.click', pwin.document, 'click', function(evt) {
                var target = evt.target;
                if (!target || !target.closest) return;
                if (target.closest('button, [role="button"], a[href]')) {
                    persistScrollState();
                }
            }, true);
            bind('scrollState.submit', pwin.document, 'submit', persistScrollState, true);
            bind('scrollState.keydown', pwin.document, 'keydown', function(evt) {
                if (evt.key !== 'Enter' || evt.shiftKey) return;
                var target = evt.target;
                if (!target || !target.closest) return;
                if (target.closest('[data-testid="stChatInput"]')) {
                    persistScrollState();
                }
            }, true);

            // Reparent the sidebar/theme toggles to <body> so that no
            // ancestor with `transform`/`filter`/`will-change` can
            // change their containing block (those properties make a
            // `position: fixed` element position relative to the
            // ancestor instead of the viewport — Streamlit applies
            // some of these on its main wrapper). This also flushes
            // them OUT of any local stacking context so their huge
            // z-index actually wins against the sidebar.
            //
            // IMPORTANT: Streamlit re-renders the markdown on every
            // rerun (e.g. clicking "+ New Chat" or a thread button),
            // which injects FRESH copies of the toggle elements into
            // the markdown container. Without cleanup the old copies
            // pile up inside <body>, and the constant DOM-mutation
            // polling that used to live here was disrupting the
            // <textarea> inside st.chat_input — every appendChild
            // triggered React reconciliation and stole focus from
            // the input as the user typed. We now:
            //   1. Reconcile duplicates idempotently in moveToggle
            //      (keep one bound copy in body, delete the rest).
            //   2. Use a MutationObserver instead of setInterval so
            //      the function only runs when the DOM ACTUALLY
            //      changes (not on a 500ms timer that fires while
            //      the user is mid-keystroke).
            var bindSidebarToggle = function(el) {
                if (!el) return;
                if ((el.tagName || '').toLowerCase() === 'label') {
                    el.dataset.uigptBound = '1';
                    return;
                }
                el.onclick = function() {
                    if (typeof pwin.toggleUigptSidebar === 'function') {
                        pwin.toggleUigptSidebar();
                    }
                };
                el.dataset.uigptBound = '1';
            };
            var bindThemeToggle = function(wrap) {
                if (!wrap) return;
                // onclick attributes are stripped by DOMPurify even
                // with unsafe_allow_html=True, so the inline
                // onclick="window.toggleUigptTheme()" never fires.
                // Attach the listener here on the inner <button>.
                var b = wrap.querySelector('button');
                if (b) {
                    b.onclick = function() {
                        if (typeof pwin.toggleUigptTheme === 'function') {
                            pwin.toggleUigptTheme();
                        }
                    };
                }
                wrap.dataset.uigptBound = '1';
            };
            var bindPreviewToggle = function(el) {
                if (!el) return;
                el.onclick = function() {
                    if (typeof pwin.toggleWebforgePreviewPanel === 'function') {
                        pwin.toggleWebforgePreviewPanel();
                    }
                };
                el.dataset.uigptBound = '1';
            };
            var promoteFixedElement = function(selector) {
                var nodes = pdoc.querySelectorAll(selector);
                if (!nodes.length) return;
                var keep = null;
                for (var i = 0; i < nodes.length; i++) {
                    if (nodes[i].parentElement === pdoc.body) {
                        keep = nodes[i];
                        break;
                    }
                }
                if (!keep) {
                    keep = nodes[0];
                    pdoc.body.appendChild(keep);
                }
                for (var j = 0; j < nodes.length; j++) {
                    if (nodes[j] !== keep && nodes[j].parentNode) {
                        nodes[j].parentNode.removeChild(nodes[j]);
                    }
                }
            };
            var reconcile = function(selector, binder) {
                var nodes = pdoc.querySelectorAll(selector);
                if (!nodes.length) return;
                // Prefer the already-bound copy that lives in <body>.
                var keep = null;
                for (var i = 0; i < nodes.length; i++) {
                    if (nodes[i].parentElement === pdoc.body && nodes[i].dataset.uigptBound) {
                        keep = nodes[i];
                        break;
                    }
                }
                if (!keep) {
                    // Otherwise promote the first one to body and bind it.
                    keep = nodes[0];
                    if (keep.parentElement !== pdoc.body) {
                        pdoc.body.appendChild(keep);
                    }
                }
                // Always rebind the kept copy. Streamlit reruns can
                // leave us with a visually preserved node whose prior
                // JS listener is gone, so binding cannot be treated as
                // a one-time operation.
                binder(keep);
                // Remove any other copies so we don't accumulate
                // overlapping fixed-position duplicates on rerun.
                for (var j = 0; j < nodes.length; j++) {
                    if (nodes[j] !== keep && nodes[j].parentNode) {
                        nodes[j].parentNode.removeChild(nodes[j]);
                    }
                }
            };
            var moveToggle = function() {
                var sidebarInput = pdoc.getElementById('uigpt-sidebar-toggle-input');
                if (sidebarInput && !sidebarInput.dataset.webforgeBound) {
                    // Always start CLOSED on load. We intentionally ignore any
                    // saved "open" so every fresh page begins collapsed; the
                    // user opens the panel with the edge chevron.
                    sidebarInput.checked = false;
                    html.classList.toggle('sidebar-collapsed', !sidebarInput.checked);
                    sidebarInput.addEventListener('change', function() {
                        html.classList.toggle('sidebar-collapsed', !sidebarInput.checked);
                        try {
                            pwin.localStorage.setItem(
                                'webforge-sidebar',
                                sidebarInput.checked ? 'open' : 'collapsed'
                            );
                        } catch (e) {}
                    });
                    sidebarInput.dataset.webforgeBound = '1';
                }
                reconcile('.uigpt-sidebar-toggle', bindSidebarToggle);
                reconcile('.uigpt-floating-toggle', bindThemeToggle);
                reconcile('.webforge-preview-toggle', bindPreviewToggle);
                promoteFixedElement('.uigpt-sidebar-resizer');
                promoteFixedElement('.webforge-preview-resizer');
                ensurePreviewMaximizeBtn();
                ensurePreviewStatusEls();
                syncPreviewModePill();
            };
            moveToggle();
            // Replace the old setInterval polling with a one-shot
            // MutationObserver scoped to <body>. It fires only when
            // Streamlit actually adds new toggle nodes — never while
            // the user is typing — so the chat input's focus is no
            // longer stolen mid-keystroke.
            if (pwin.__uigptToggleInterval) {
                try { pwin.clearInterval(pwin.__uigptToggleInterval); } catch (e) {}
                pwin.__uigptToggleInterval = null;
            }
            if (pwin.__uigptToggleObserver) {
                try { pwin.__uigptToggleObserver.disconnect(); } catch (e) {}
                pwin.__uigptToggleObserver = null;
            }
            try {
                var obs = null;
                var toggleMovePending = false;
                var scheduleMoveToggle = function() {
                    if (toggleMovePending) return;
                    toggleMovePending = true;
                    pwin.setTimeout(function() {
                        toggleMovePending = false;
                        // Reparenting the fixed controls is itself a DOM
                        // mutation. Pause observation while reconciling so one
                        // Streamlit patch cannot recursively schedule more
                        // scans of the whole document.
                        try { if (obs) obs.disconnect(); } catch (e) {}
                        try { moveToggle(); } finally {
                            try {
                                if (obs && pdoc.body) {
                                    obs.observe(pdoc.body, { childList: true, subtree: true });
                                }
                            } catch (e) {}
                        }
                    }, 50);
                };
                obs = new pwin.MutationObserver(function(muts) {
                    for (var i = 0; i < muts.length; i++) {
                        var added = muts[i].addedNodes;
                        for (var j = 0; j < added.length; j++) {
                            var n = added[j];
                            if (n && n.nodeType === 1 && (
                                (n.classList && (n.classList.contains('uigpt-sidebar-toggle-input') || n.classList.contains('uigpt-sidebar-toggle') || n.classList.contains('uigpt-floating-toggle') || n.classList.contains('webforge-preview-toggle') || n.classList.contains('uigpt-sidebar-resizer') || n.classList.contains('webforge-preview-resizer') || n.classList.contains('st-key-webforge_preview_panel'))) ||
                                (n.querySelector && (n.querySelector('.uigpt-sidebar-toggle-input') || n.querySelector('.uigpt-sidebar-toggle') || n.querySelector('.uigpt-floating-toggle') || n.querySelector('.webforge-preview-toggle') || n.querySelector('.uigpt-sidebar-resizer') || n.querySelector('.webforge-preview-resizer') || n.querySelector('.st-key-webforge_preview_panel')))
                            )) {
                                scheduleMoveToggle();
                                return;
                            }
                        }
                    }
                });
                obs.observe(pdoc.body, { childList: true, subtree: true });
                pwin.__uigptToggleObserver = obs;
            } catch (e) {
                // MutationObserver unavailable — fall back to a much
                // slower poll so we still survive in odd environments
                // without thrashing the DOM mid-typing.
                pwin.__uigptToggleInterval = pwin.setInterval(moveToggle, 2000);
            }
            // Live elapsed timer for the "WebForge is working..." box. Ticks
            // client-side so the box's own HTML need not change every second
            // (that re-render is what made it flicker/stutter). Each
            // .wf-st-elapsed / .wf-st-dur span carries data-start (epoch ms);
            // we show Date.now() - data-start.
            //
            // IMPORTANT: re-arm on EVERY chrome-script run, clearing any prior
            // interval first. The callback belongs to THIS components.html
            // iframe's realm; when Streamlit recreates the iframe on a rerun the
            // old iframe is torn down and its callback goes dead, yet the parent
            // still holds the (now useless) interval id. A one-time guard would
            // then never re-arm, so the timer silently stopped ticking after the
            // first rerun (found live: spans stuck empty during a real run).
            // Clearing + re-arming with the current iframe's live callback keeps
            // it ticking and never stacks intervals.
            var wfFmtElapsed = function(sec) {
                sec = Math.max(0, Math.floor(sec));
                if (sec < 60) return sec + 's';
                if (sec < 3600) return Math.floor(sec / 60) + 'm ' + (sec % 60) + 's';
                return Math.floor(sec / 3600) + 'h ' + Math.floor((sec % 3600) / 60) + 'm ' + (sec % 60) + 's';
            };
            var wfTickElapsed = function() {
                // Overall timers: always tick to now.
                var els = pdoc.querySelectorAll('.wf-st-elapsed[data-start]');
                for (var i = 0; i < els.length; i++) {
                    var start = Number(els[i].getAttribute('data-start'));
                    if (start > 0) {
                        els[i].textContent = wfFmtElapsed((Date.now() - start) / 1000);
                    }
                }
                // Per-step timers: frozen if data-end is set (done step),
                // otherwise tick to now (the step running right now).
                var durs = pdoc.querySelectorAll('.wf-st-dur[data-start]');
                for (var j = 0; j < durs.length; j++) {
                    var s = Number(durs[j].getAttribute('data-start'));
                    if (!s) continue;
                    var e = durs[j].getAttribute('data-end');
                    var endMs = e ? Number(e) : Date.now();
                    durs[j].textContent = wfFmtElapsed((endMs - s) / 1000);
                }
            };
            if (pwin.__wfElapsedTimer) {
                try { pwin.clearInterval(pwin.__wfElapsedTimer); } catch (e) {}
            }
            // The labels display whole seconds, so four DOM writes per second
            // only consume the browser main thread without adding information.
            pwin.__wfElapsedTimer = pwin.setInterval(wfTickElapsed, 1000);
            wfTickElapsed();
        } catch (e) {
                console.error('WebForge: theme/sidebar JS failed to attach', e);
        }
    })();
    