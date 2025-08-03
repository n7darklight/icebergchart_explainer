document.addEventListener('DOMContentLoaded', () => {
    const explanationPanel = document.getElementById('explanation-panel');
    const explanationTitle = document.getElementById('explanation-title');
    const explanationContent = document.getElementById('explanation-content');
    const explanationImage = document.getElementById('explanation-image');
    const refreshImageBtn = document.getElementById('refresh-image-btn');
    const closePanelButton = document.getElementById('close-panel');
    const entries = document.querySelectorAll('.iceberg-entry');

    // Dynamically set layer colors
    const layers = document.querySelectorAll('.iceberg-layer');
    layers.forEach(layer => {
        const index = parseInt(layer.dataset.index, 10);
        const lightness = 95 - (index * 7);
        layer.style.backgroundColor = `hsl(200, 100%, ${lightness}%)`;
    });

    const openPanel = () => {
        if (window.innerWidth < 1024) {
            explanationPanel.classList.add('is-open');
        }
    };

    const closePanel = () => {
        explanationPanel.classList.remove('is-open');
    };

    if (closePanelButton) {
        closePanelButton.addEventListener('click', closePanel);
    }

    // --- Main function to fetch and display explanation ---
    async function fetchAndDisplayExplanation(entryText, forceRefresh = false) {
        const cacheKey = `${CHART_NAME}-${entryText}`;

        openPanel();
        explanationTitle.textContent = entryText;
        explanationImage.classList.add('hidden');
        refreshImageBtn.classList.add('hidden');
        explanationContent.innerHTML = `
            <div class="flex items-center justify-center h-full">
                <div class="loader ease-linear rounded-full border-4 border-t-4 border-gray-200 h-12 w-12 mb-4"></div>
            </div>
            <p class="text-center">Loading explanation...</p>
        `;

        const cachedData = sessionStorage.getItem(cacheKey);
        if (cachedData && !forceRefresh) {
            console.log("Loading from cache:", cacheKey);
            const data = JSON.parse(cachedData);
            updateExplanationPanel(data);
            return;
        }

        console.log("Fetching from API:", cacheKey);
        try {
            const response = await fetch('/api/explain', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chart_name: CHART_NAME, entry_text: entryText }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            // Only update cache if it's not a forced refresh of a failed image
            if (!forceRefresh) {
                sessionStorage.setItem(cacheKey, JSON.stringify(data));
            }
            
            updateExplanationPanel(data);

        } catch (error) {
            console.error('Error fetching explanation:', error);
            explanationImage.classList.add('hidden');
            refreshImageBtn.classList.add('hidden');
            explanationContent.innerHTML = `
                <p class="text-red-400"><b>Error:</b> Could not fetch explanation.</p>
                <p class="text-gray-400 mt-2">${error.message}</p>
            `;
        }
    }

    // --- Add event listeners ---
    entries.forEach(entry => {
        entry.addEventListener('click', () => {
            fetchAndDisplayExplanation(entry.dataset.entry, false);
        });
    });

    refreshImageBtn.addEventListener('click', () => {
        const currentEntry = explanationTitle.textContent;
        if (currentEntry) {
            // Force a refresh from the API, bypassing the cache
            fetchAndDisplayExplanation(currentEntry, true);
        }
    });

    function updateExplanationPanel(data) {
        const placeholderUrl = `https://placehold.co/600x400/1f2937/a5f3fc?text=${encodeURIComponent(explanationTitle.textContent)}`;
        
        // Use the proxy for the image URL
        const imageUrl = data.image_url ? `/api/image-proxy?url=${encodeURIComponent(data.image_url)}` : placeholderUrl;

        explanationImage.src = imageUrl;
        explanationImage.onerror = () => {
            explanationImage.src = placeholderUrl;
        };
        explanationImage.classList.remove('hidden');
        refreshImageBtn.classList.remove('hidden');

        explanationContent.innerHTML = data.explanation;
    }

    // Loader animation CSS
    const style = document.createElement('style');
    style.innerHTML = `
        .loader {
            border-top-color: #22d3ee;
            -webkit-animation: spinner 1.5s linear infinite;
            animation: spinner 1.5s linear infinite;
        }
        @-webkit-keyframes spinner { 0% { -webkit-transform: rotate(0deg); } 100% { -webkit-transform: rotate(360deg); } }
        @keyframes spinner { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    `;
    document.head.appendChild(style);
});
