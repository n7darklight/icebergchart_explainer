document.addEventListener('DOMContentLoaded', () => {
    const explanationPanel = document.getElementById('explanation-panel');
    const explanationTitle = document.getElementById('explanation-title');
    const explanationContent = document.getElementById('explanation-content');
    const explanationImage = document.getElementById('explanation-image');
    const closePanelButton = document.getElementById('close-panel');
    const entries = document.querySelectorAll('.iceberg-entry');

    // Dynamically set layer colors to avoid Jinja in style attributes
    const layers = document.querySelectorAll('.iceberg-layer');
    layers.forEach(layer => {
        const index = parseInt(layer.dataset.index, 10);
        const lightness = 95 - (index * 7);
        layer.style.backgroundColor = `hsl(200, 100%, ${lightness}%)`;
    });

    // Function to show the explanation panel on mobile
    const openPanel = () => {
        if (window.innerWidth < 1024) { // lg breakpoint in Tailwind
            explanationPanel.classList.add('is-open');
        }
    };

    // Function to hide the explanation panel on mobile
    const closePanel = () => {
        explanationPanel.classList.remove('is-open');
    };

    if (closePanelButton) {
        closePanelButton.addEventListener('click', closePanel);
    }

    entries.forEach(entry => {
        entry.addEventListener('click', async () => {
            const entryText = entry.dataset.entry;

            openPanel();
            explanationTitle.textContent = entryText;
            explanationImage.classList.add('hidden'); // Hide image while loading
            explanationContent.innerHTML = `
                <div class="flex items-center justify-center h-full">
                    <div class="loader ease-linear rounded-full border-4 border-t-4 border-gray-200 h-12 w-12 mb-4"></div>
                </div>
                <p class="text-center">Summoning digital spirits to explain...</p>
            `;

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
                
                // Update image with a placeholder fallback
                const placeholderUrl = `https://placehold.co/600x400/1f2937/a5f3fc?text=${encodeURIComponent(entryText)}`;
                explanationImage.src = data.image_url || placeholderUrl;
                explanationImage.onerror = () => {
                    explanationImage.src = placeholderUrl; // Fallback on image load error
                };
                explanationImage.classList.remove('hidden');


                // Update text
                explanationContent.innerHTML = data.explanation;

            } catch (error) {
                console.error('Error fetching explanation:', error);
                explanationImage.classList.add('hidden');
                explanationContent.innerHTML = `
                    <p class="text-red-400"><b>Error:</b> Could not fetch explanation.</p>
                    <p class="text-gray-400 mt-2">${error.message}</p>
                `;
            }
        });
    });

    // Simple CSS for the loader animation
    const style = document.createElement('style');
    style.innerHTML = `
        .loader {
            border-top-color: #22d3ee; /* cyan-400 */
            -webkit-animation: spinner 1.5s linear infinite;
            animation: spinner 1.5s linear infinite;
        }
        @-webkit-keyframes spinner { 0% { -webkit-transform: rotate(0deg); } 100% { -webkit-transform: rotate(360deg); } }
        @keyframes spinner { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    `;
    document.head.appendChild(style);
});
