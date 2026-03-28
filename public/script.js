/**
 * IslamAI — Interactive UI Enhancements for Chainlit
 * Injected via custom_js in config.toml
 */

(function() {
    const COPY_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
    const CHECK_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;

    /**
     * Attaches interactive features to a citation block (Quran/Hadith)
     */
    function setupCitationBlock(block) {
        if (block.dataset.initialized) return;
        block.dataset.initialized = "true";

        // 1. Spotlight Effect Tracking
        block.addEventListener('mousemove', (e) => {
            const rect = block.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            block.style.setProperty('--mouse-x', `${x}px`);
            block.style.setProperty('--mouse-y', `${y}px`);
        });

        // 2. Inject Copy Button
        const btn = document.createElement('button');
        btn.className = 'citation-copy-btn';
        btn.title = 'Copy citation';
        btn.innerHTML = COPY_ICON;

        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            
            // Get text excluding the metadata blocks for a cleaner copy if desired, 
            // or just copy the whole thing. Let's copy the quote + meta for context.
            const clone = block.cloneNode(true);
            const copyBtn = clone.querySelector('.citation-copy-btn');
            if (copyBtn) copyBtn.remove();
            
            const textToCopy = clone.innerText.trim();
            
            navigator.clipboard.writeText(textToCopy).then(() => {
                btn.innerHTML = CHECK_ICON;
                btn.classList.add('copied');
                setTimeout(() => {
                    btn.innerHTML = COPY_ICON;
                    btn.classList.remove('copied');
                }, 2000);
            }).catch(err => {
                console.error('Failed to copy text: ', err);
            });
        });

        block.appendChild(btn);
    }

    /**
     * Mutation Observer to handle dynamically added messages
     */
    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    // Check if the node itself is a citation block
                    if (node.classList.contains('quran') || node.classList.contains('hadith')) {
                        setupCitationBlock(node);
                    }
                    // Or if it contains citation blocks (more common as messages are updated)
                    const blocks = node.querySelectorAll('.quran, .hadith');
                    blocks.forEach(setupCitationBlock);
                }
            }
        }
    });

    // Start observing the entire body for changes
    // Chainlit's message list is deep in the DOM, so subtree: true is essential.
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

    // Also run on existing blocks (for page reloads/restored sessions)
    document.querySelectorAll('.quran, .hadith').forEach(setupCitationBlock);

    console.log('🌙 IslamAI Custom Script Loaded.');
})();
