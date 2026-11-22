
        (function() {
            var presets = {
                fit: { label: 'Fit', width: 1280, height: 820, cls: '' },
                desktop: { label: 'Desktop', width: 1440, height: 900, cls: '' },
                wide: { label: '16:9', width: 1440, height: 810, cls: '' },
                tablet: { label: 'Tablet', width: 768, height: 1024, cls: 'device-tablet', chromeX: 10, chromeTop: 10, chromeBottom: 10 },
                'iphone-standard': { label: 'iPhone Standard', width: 393, height: 852, cls: 'device-ios', chromeX: 10, chromeTop: 14, chromeBottom: 10 },
                'iphone-pro-max': { label: 'iPhone Pro Max', width: 430, height: 932, cls: 'device-ios', chromeX: 10, chromeTop: 14, chromeBottom: 10 },
                'android-large': { label: 'Android Large', width: 412, height: 915, cls: 'device-android', chromeX: 9, chromeTop: 10, chromeBottom: 9 },
                'android-compact': { label: 'Android Compact', width: 360, height: 780, cls: 'device-android device-compact', chromeX: 8, chromeTop: 10, chromeBottom: 8 },
                'small-phone': { label: 'Small Phone', width: 375, height: 667, cls: 'device-ios device-compact', chromeX: 8, chromeTop: 12, chromeBottom: 8 }
            };
            var device = document.getElementById('device');
            var shell = document.getElementById('deviceShell');
            var canvas = document.getElementById('canvas');
            var label = document.getElementById('label');
            var modeLabel = document.getElementById('modeLabel');
            var buttons = Array.from(document.querySelectorAll('button[data-mode]'));
            var phonePicker = document.getElementById('phonePicker');
            var phoneMenuButton = document.getElementById('phoneMenuButton');
            var previewFrame = document.querySelector('iframe[title="WebForge generated preview"]');
            var hoverOverlay = document.getElementById('hoverOverlay');
            var selectedOverlay = document.getElementById('selectedOverlay');
            var tooltip = document.getElementById('selectTooltip');
            var pocket = document.getElementById('selectPocket');
            var selectedSummary = document.getElementById('selectedSummary');
            var selectedName = document.getElementById('selectedName');
            var submitModKey = document.getElementById('submitModKey');
            var requestInput = document.getElementById('modificationRequest');
            if (submitModKey) {
                var isMacPlatform = /Mac|iPhone|iPad/.test(navigator.platform || '');
                submitModKey.textContent = isMacPlatform ? '⌘' : 'Ctrl';
            }
            var submitButton = document.getElementById('submitModification');
            var closePocket = document.getElementById('closePocket');
            var current = 'desktop';
            var previewLoaded = false;
            var selectEnabled = __WF_SELECT_ENABLED__;
            var selectedInfo = null;
            var phoneModes = ['iphone-standard', 'iphone-pro-max', 'android-large', 'android-compact', 'small-phone'];
            function baseUrlFor(src) {
                return src.slice(0, src.lastIndexOf('/') + 1);
            }
            // Same-page anchors inside the srcdoc page. The <base> below makes
            // href="#hero" resolve to http://127.0.0.1:PORT/#hero, and Chrome
            // treats that as a full navigation of the iframe, not a scroll: the
            // preview server then answers with its directory listing (seen
            // 2026-09-15 on 13b71045, clicking Home in the nav). Fragment links
            // are handled in the page itself. Select mode owns clicks once it
            // has bound, so the fix steps aside there.
            var anchorFix = '<script>(function(){' +
                'document.addEventListener("click",function(e){' +
                    'if(document.__webforgeSelectBound)return;' +
                    'var a=e.target&&e.target.closest?e.target.closest("a"):null;' +
                    'var href=a?(a.getAttribute("href")||""):"";' +
                    'if(href.charAt(0)!=="#")return;' +
                    'e.preventDefault();' +
                    'var id=href.slice(1);' +
                    'try{id=decodeURIComponent(id);}catch(err){}' +
                    'if(!id)return;' +
                    'if(id==="top"){window.scrollTo({top:0});return;}' +
                    'var el=document.getElementById(id);' +
                    'if(el){el.scrollIntoView({block:"start"});}' +
                '},true);' +
            '})();<\/script>';
            function htmlWithBase(html, src) {
                var base = '<base href="' + baseUrlFor(src) + '">' + anchorFix;
                if (/<base\s/i.test(html)) return html;
                if (/<head[^>]*>/i.test(html)) {
                    return html.replace(/<head[^>]*>/i, function(match) { return match + base; });
                }
                return base + html;
            }
            function withoutPageScripts(html) {
                // Select mode only needs the generated DOM and CSS. Running the
                // page's own JavaScript inside same-origin srcdoc would let one
                // generated infinite loop freeze the whole WebForge shell.
                return html.replace(/<script\b[^>]*>[\s\S]*?<\/script\s*>/gi, '');
            }
            function loadPreview() {
                if (previewLoaded || !previewFrame) return;
                var src = previewFrame.getAttribute('data-src');
                if (!src) return;
                if (!selectEnabled) {
                    // Keep the generated app on its 127.0.0.1 origin. Chromium
                    // can isolate this cross-site iframe from the Streamlit
                    // shell, so broken page JavaScript cannot starve the chat
                    // UI's event loop. Native fragment links also work here.
                    previewFrame.setAttribute('src', src);
                    previewLoaded = true;
                    return;
                }
                fetch(src, { cache: 'no-store' })
                    .then(function(response) {
                        if (!response.ok) throw new Error('Preview fetch failed');
                        return response.text();
                    })
                    .then(function(html) {
                        previewFrame.setAttribute(
                            'srcdoc',
                            htmlWithBase(withoutPageScripts(html), src)
                        );
                        previewLoaded = true;
                        window.setTimeout(bindSelectMode, 350);
                    })
                    .catch(function() {
                        previewFrame.setAttribute('src', src);
                        previewLoaded = true;
                        window.setTimeout(bindSelectMode, 500);
                    });
            }
            function bindPanelOpenLoader() {
                try {
                    var input = window.parent.document.getElementById('webforge-preview-toggle-input');
                    var open = input && input.checked;
                    window.setTimeout(loadPreview, 180);
                    if (open) {
                        window.setTimeout(loadPreview, 80);
                    }
                    if (input && !input.dataset.previewLoaderBound) {
                        input.addEventListener('change', function() {
                            if (input.checked) {
                                window.setTimeout(loadPreview, 120);
                            }
                        });
                        input.dataset.previewLoaderBound = 'true';
                    }
                } catch (e) {
                    window.setTimeout(loadPreview, 250);
                }
            }
            function outerSize(preset) {
                var chromeX = preset.chromeX || 0;
                var chromeTop = preset.chromeTop || 0;
                var chromeBottom = preset.chromeBottom || chromeTop;
                return {
                    width: preset.width + chromeX * 2,
                    height: preset.height + chromeTop + chromeBottom
                };
            }
            function scaleFor(preset) {
                var box = canvas.getBoundingClientRect();
                var outer = outerSize(preset);
                return Math.min((box.width - 28) / outer.width, (box.height - 28) / outer.height, 1);
            }
            function apply(mode) {
                current = mode;
                var preset = presets[mode] || presets.desktop;
                var outer = outerSize(preset);
                var chromeX = preset.chromeX || 0;
                var chromeTop = preset.chromeTop || 0;
                var chromeBottom = preset.chromeBottom || chromeTop;
                var scale = scaleFor(preset);
                device.style.setProperty('--frame-w', preset.width + 'px');
                device.style.setProperty('--frame-h', preset.height + 'px');
                device.style.setProperty('--outer-w', outer.width + 'px');
                device.style.setProperty('--outer-h', outer.height + 'px');
                device.style.setProperty('--chrome-x', chromeX + 'px');
                device.style.setProperty('--chrome-top', chromeTop + 'px');
                device.style.setProperty('--chrome-bottom', chromeBottom + 'px');
                device.style.setProperty('--frame-scale', scale);
                shell.style.width = Math.max(1, Math.round(outer.width * scale)) + 'px';
                shell.style.height = Math.max(1, Math.round(outer.height * scale)) + 'px';
                device.className = 'device ' + preset.cls;
                if (label) label.textContent = preset.label;
                if (modeLabel) modeLabel.textContent = selectEnabled ? 'Select' : 'Preview';
                buttons.forEach(function(btn) {
                    btn.classList.toggle('active', btn.dataset.mode === mode);
                });
                if (phoneMenuButton) {
                    phoneMenuButton.classList.toggle('active', phoneModes.indexOf(mode) !== -1);
                }
                canvas.classList.remove('is-tall');
                window.requestAnimationFrame(function() {
                    canvas.classList.toggle(
                        'is-tall',
                        shell.offsetHeight > Math.max(1, canvas.clientHeight - 36)
                    );
                    canvas.scrollTop = 0;
                    canvas.scrollLeft = 0;
                });
            }
            buttons.forEach(function(btn) {
                btn.addEventListener('click', function() {
                    apply(btn.dataset.mode);
                    if (phoneModes.indexOf(btn.dataset.mode) !== -1 && phonePicker) {
                        phonePicker.classList.remove('open');
                        if (phoneMenuButton) phoneMenuButton.setAttribute('aria-expanded', 'false');
                    }
                });
            });
            if (phoneMenuButton && phonePicker) {
                phoneMenuButton.addEventListener('click', function() {
                    var open = !phonePicker.classList.contains('open');
                    phonePicker.classList.toggle('open', open);
                    phoneMenuButton.setAttribute('aria-expanded', open ? 'true' : 'false');
                });
            }
            function cssEscape(value) {
                if (window.CSS && typeof window.CSS.escape === 'function') {
                    return window.CSS.escape(value);
                }
                return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
            }
            function stableClass(el) {
                var classes = Array.from(el.classList || []);
                var ignored = {
                    active: true, open: true, selected: true, hidden: true,
                    disabled: true, expanded: true, collapsed: true
                };
                return classes.find(function(cls) { return cls && !ignored[cls]; }) || classes[0] || '';
            }
            function selectorFor(el) {
                var cls = stableClass(el);
                if (cls) return '.' + cssEscape(cls);
                if (el.id) return '#' + cssEscape(el.id);
                var component = el.getAttribute('data-component') || '';
                if (component) return '[data-component="' + component.replace(/"/g, '\\"') + '"]';
                return '';
            }
            function componentName(el) {
                return el.getAttribute('data-component') || el.id || stableClass(el) || el.tagName.toLowerCase();
            }
            function targetInfo(el, doc) {
                var selector = selectorFor(el);
                if (!selector) return null;
                var matches = Array.from(doc.querySelectorAll(selector));
                var instance = Math.max(1, matches.indexOf(el) + 1);
                return {
                    selector: selector,
                    instance: instance,
                    component: componentName(el),
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    dataComponent: el.getAttribute('data-component') || '',
                    className: stableClass(el)
                };
            }
            function displayedRect(el) {
                var frameRect = previewFrame.getBoundingClientRect();
                var rect = el.getBoundingClientRect();
                var scaleX = frameRect.width / Math.max(1, previewFrame.clientWidth);
                var scaleY = frameRect.height / Math.max(1, previewFrame.clientHeight);
                return {
                    left: frameRect.left + rect.left * scaleX,
                    top: frameRect.top + rect.top * scaleY,
                    width: rect.width * scaleX,
                    height: rect.height * scaleY,
                    right: frameRect.left + rect.right * scaleX,
                    bottom: frameRect.top + rect.bottom * scaleY
                };
            }
            function showOverlay(overlay, rect) {
                overlay.style.left = Math.round(rect.left) + 'px';
                overlay.style.top = Math.round(rect.top) + 'px';
                overlay.style.width = Math.max(1, Math.round(rect.width)) + 'px';
                overlay.style.height = Math.max(1, Math.round(rect.height)) + 'px';
                overlay.style.opacity = '1';
            }
            function hideHover() {
                hoverOverlay.style.opacity = '0';
                tooltip.classList.remove('visible');
            }
            function tooltipHtml(info) {
                var detail = info.selector + ' · instance ' + info.instance;
                if (info.dataComponent) detail += ' · data-component=' + info.dataComponent;
                return '<strong>' + info.component + '</strong><code>' + detail + '</code>';
            }
            function positionTooltip(rect, info, cursor) {
                tooltip.innerHTML = tooltipHtml(info);
                tooltip.classList.add('visible');
                var width = Math.min(260, Math.max(180, tooltip.offsetWidth || 220));
                var height = tooltip.offsetHeight || 44;
                // Follow the cursor (converted out of the preview iframe's own
                // coordinate space through the frame scale) instead of anchoring
                // to the component's top-left corner. A large component in a large
                // panel put that corner far from the pointer; a cursor anchor
                // stays beside the pointer at any panel size.
                var anchorLeft = cursor ? cursor.x + 14 : rect.left;
                var anchorTop = cursor ? cursor.y + 18 : rect.top - height - 8;
                var left = Math.min(window.innerWidth - width - 10, Math.max(10, anchorLeft));
                var top = anchorTop;
                if (top + height > window.innerHeight - 8) {
                    top = (cursor ? cursor.y : rect.top) - height - 10;
                }
                if (top < 8) top = 8;
                tooltip.style.left = Math.round(left) + 'px';
                tooltip.style.top = Math.round(top) + 'px';
            }
            function positionPocket(rect) {
                var margin = 10;
                var pocketRect = pocket.getBoundingClientRect();
                var pocketW = Math.min(288, Math.max(220, pocketRect.width || 288));
                var pocketH = Math.max(150, pocketRect.height || 178);
                var vw = window.innerWidth;
                var vh = window.innerHeight;
                function clampX(x) {
                    return Math.min(vw - pocketW - margin, Math.max(margin, x));
                }
                var belowTop = rect.bottom + margin;
                var aboveTop = rect.top - pocketH - margin;
                var placement = 'below';
                var left, top;
                if (belowTop + pocketH <= vh - margin) {
                    placement = 'below';
                    top = belowTop;
                    left = clampX(rect.left);
                } else if (aboveTop >= margin) {
                    placement = 'above';
                    top = aboveTop;
                    left = clampX(rect.left);
                } else {
                    var rightLeft = rect.right + margin;
                    var leftLeft = rect.left - pocketW - margin;
                    top = Math.min(vh - pocketH - margin, Math.max(margin, rect.top));
                    if (rightLeft + pocketW <= vw - margin) {
                        placement = 'side';
                        left = rightLeft;
                    } else if (leftLeft >= margin) {
                        placement = 'side';
                        left = leftLeft;
                    } else {
                        placement = 'below';
                        top = Math.min(vh - pocketH - margin, belowTop);
                        left = clampX(rect.left);
                    }
                }
                pocket.classList.toggle('is-above', placement === 'above');
                pocket.classList.toggle('is-side', placement === 'side');
                var caret = Math.min(pocketW - 24, Math.max(16, rect.left + Math.min(rect.width / 2, 40) - left));
                pocket.style.left = Math.round(left) + 'px';
                pocket.style.top = Math.round(top) + 'px';
                pocket.style.setProperty('--pocket-caret-x', Math.round(caret) + 'px');
                var originY = placement === 'above' ? '100%' : (placement === 'side' ? '24px' : '0');
                var originX = placement === 'side' ? '0' : (Math.round(caret) + 'px');
                pocket.style.setProperty('--pocket-origin', originX + ' ' + originY);
            }
            function renderParentAnnotation(info, request) {
                try {
                    var pdoc = window.parent.document;
                    var old = pdoc.getElementById('webforgeClientAnnotation');
                    if (old) old.remove();
                    var chip = pdoc.createElement('div');
                    chip.id = 'webforgeClientAnnotation';
                    chip.className = 'webforge-annotation-chip webforge-client-annotation';
                    chip.title = 'Target: ' + info.selector + ' · instance ' + info.instance + '\nRequest: ' + request;
                    chip.innerHTML = '<span>Annotation 1</span>' +
                        '<button type="button" class="wf-anno-x" aria-label="Remove annotation">&times;</button>';
                    var input = pdoc.querySelector('[data-testid="stChatInput"]');
                    if (input && input.parentElement) {
                        input.parentElement.insertBefore(chip, input);
                    } else {
                        chip.style.position = 'fixed';
                        chip.style.left = '50%';
                        chip.style.bottom = '72px';
                        chip.style.transform = 'translateX(-50%)';
                        chip.style.zIndex = '1000004';
                        pdoc.body.appendChild(chip);
                    }
                    var annoX = chip.querySelector('.wf-anno-x');
                    if (annoX) {
                        annoX.addEventListener('click', function(ev) {
                            ev.preventDefault();
                            ev.stopPropagation();
                            try { window.parent.localStorage.removeItem('webforge-modification-annotation:v1'); } catch (e) {}
                            if (chip && chip.parentNode) chip.parentNode.removeChild(chip);
                        });
                    }
                    try {
                        // The thread this annotation belongs to, read from the
                        // URL the app pins (?t=). The composer bridge applies the
                        // annotation only while that same thread is open.
                        var threadId = '';
                        try {
                            threadId = new window.parent.URLSearchParams(window.parent.location.search).get('t') || '';
                        } catch (threadError) {}
                        window.parent.localStorage.setItem('webforge-modification-annotation:v1', JSON.stringify({
                            thread: threadId,
                            target_component: info.selector,
                            target_instance: info.instance,
                            component: info.component,
                            request: request,
                            marker: __WF_MODIFY_MARKER__
                        }));
                    } catch (storageError) {}
                } catch (e) {}
            }
            function bindSelectMode() {
                if (!selectEnabled || !previewFrame) return;
                var doc;
                try {
                    doc = previewFrame.contentDocument || previewFrame.contentWindow.document;
                } catch (e) {
                    return;
                }
                if (!doc || doc.__webforgeSelectBound) return;
                doc.__webforgeSelectBound = true;
                doc.addEventListener('mousemove', function(event) {
                    var target = event.target && event.target.closest
                        ? event.target.closest('[data-component]')
                        : null;
                    if (!target) {
                        hideHover();
                        return;
                    }
                    var info = targetInfo(target, doc);
                    if (!info) {
                        hideHover();
                        return;
                    }
                    var rect = displayedRect(target);
                    showOverlay(hoverOverlay, rect);
                    var _fr = previewFrame.getBoundingClientRect();
                    var _sx = _fr.width / Math.max(1, previewFrame.clientWidth);
                    var _sy = _fr.height / Math.max(1, previewFrame.clientHeight);
                    var cursor = { x: _fr.left + event.clientX * _sx, y: _fr.top + event.clientY * _sy };
                    positionTooltip(rect, info, cursor);
                }, true);
                doc.addEventListener('mouseleave', hideHover, true);
                doc.addEventListener('click', function(event) {
                    var target = event.target && event.target.closest
                        ? event.target.closest('[data-component]')
                        : null;
                    if (!target) return;
                    var info = targetInfo(target, doc);
                    if (!info) return;
                    event.preventDefault();
                    event.stopPropagation();
                    selectedInfo = info;
                    var rect = displayedRect(target);
                    selectedOverlay.style.display = 'block';
                    showOverlay(selectedOverlay, rect);
                    if (selectedName) selectedName.textContent = info.component;
                    selectedSummary.textContent = info.selector + ' · #' + info.instance;
                    pocket.classList.add('visible');
                    positionPocket(rect);
                    requestInput.value = '';
                    submitButton.disabled = true;
                    window.setTimeout(function() { requestInput.focus(); }, 80);
                }, true);
                doc.addEventListener('scroll', function() {
                    hideHover();
                    if (selectedInfo) {
                        selectedOverlay.style.opacity = '0';
                        pocket.classList.remove('visible');
                    }
                }, true);
            }
            requestInput.addEventListener('input', function() {
                submitButton.disabled = !requestInput.value.trim();
            });
            requestInput.addEventListener('keydown', function(event) {
                if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                    event.preventDefault();
                    if (!submitButton.disabled) submitButton.click();
                }
            });
            submitButton.addEventListener('click', function() {
                if (!selectedInfo) return;
                var request = requestInput.value.trim();
                if (!request) return;
                renderParentAnnotation(selectedInfo, request);
                pocket.classList.remove('visible');
            });
            closePocket.addEventListener('click', function() {
                pocket.classList.remove('visible');
            });
            window.addEventListener('resize', function() { apply(current); });
            if (previewFrame) {
                previewFrame.addEventListener('load', bindSelectMode);
            }
            apply(current);
            bindPanelOpenLoader();
        })();
        