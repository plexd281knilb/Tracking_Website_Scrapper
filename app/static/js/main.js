document.addEventListener("DOMContentLoaded", () => {
    // State
    let products = [];
    let releases = [];
    let trackers = [];

    // Tab Switching
    const navItems = document.querySelectorAll(".nav-item");
    const tabPanes = document.querySelectorAll(".tab-pane");

    navItems.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");

            navItems.forEach(i => i.classList.remove("active"));
            tabPanes.forEach(p => p.classList.remove("active"));

            btn.classList.add("active");
            document.getElementById(`tab-${targetTab}`).classList.add("active");

            // Load data when tab opens
            if (targetTab === "dashboard") fetchProducts();
            if (targetTab === "releases") fetchReleases();
            if (targetTab === "trackers") fetchTrackers();
            if (targetTab === "smtp") fetchSMTP();
            if (targetTab === "logs") fetchLogs();
        });
    });

    // Toast Notifications
    function showToast(message, type = "info") {
        const container = document.getElementById("toast-container");
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.textContent = message;

        container.appendChild(toast);
        setTimeout(() => {
            toast.remove();
        }, 4000);
    }

    // 1. Fetch & Render Products
    async function fetchProducts() {
        try {
            const res = await fetch("/api/products");
            products = await res.json();
            renderProducts();
            updateStats();
        } catch (err) {
            console.error("Failed to fetch products", err);
            showToast("Failed to fetch products list", "error");
        }
    }

    function renderProducts() {
        const tbody = document.getElementById("products-table-body");
        const searchVal = document.getElementById("product-search").value.toLowerCase();
        const filterVal = document.getElementById("stock-filter").value;

        const filtered = products.filter(p => {
            const matchesSearch = p.title.toLowerCase().includes(searchVal);
            const matchesStock = filterVal === "all" ||
                (filterVal === "in_stock" && p.in_stock) ||
                (filterVal === "out_of_stock" && !p.in_stock);
            return matchesSearch && matchesStock;
        });

        if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No products found matching filters.</td></tr>`;
            return;
        }

        tbody.innerHTML = filtered.map(p => `
            <tr>
                <td>
                    <span class="badge-status ${p.in_stock ? 'badge-instock' : 'badge-outstock'}">
                        ${p.in_stock ? '● IN STOCK' : '○ OUT OF STOCK'}
                    </span>
                </td>
                <td><strong>${escapeHtml(p.title)}</strong></td>
                <td>
                    <span class="badge-retailer badge-${p.retailer || 'custom'}">
                        ${(p.retailer || 'custom').replace('_', ' ')}
                    </span>
                </td>
                <td><strong style="color: var(--accent-green);">${p.price || 'N/A'}</strong></td>
                <td style="font-size: 12px; color: var(--text-secondary);">${formatDate(p.last_checked)}</td>
                <td>
                    <a href="${p.url}" target="_blank" class="btn btn-secondary btn-sm">🔗 View Item</a>
                </td>
            </tr>
        `).join('');
    }

    function updateStats() {
        const total = products.length;
        const inStock = products.filter(p => p.in_stock).length;
        const outStock = total - inStock;

        document.getElementById("stat-total").textContent = total;
        document.getElementById("stat-in-stock").textContent = inStock;
        document.getElementById("stat-out-stock").textContent = outStock;
    }

    // Product Search & Filter Listeners
    document.getElementById("product-search").addEventListener("input", renderProducts);
    document.getElementById("stock-filter").addEventListener("change", renderProducts);

    // 2. Fetch & Render Release Calendar
    async function fetchReleases() {
        try {
            const res = await fetch("/api/releases");
            releases = await res.json();
            renderReleases();
        } catch (err) {
            console.error("Failed to fetch releases", err);
        }
    }

    function renderReleases() {
        const tbody = document.getElementById("releases-table-body");
        const badge = document.getElementById("release-count-badge");
        badge.textContent = releases.length;

        if (releases.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No releases scraped yet. Run scrape cycle to fetch calendar.</td></tr>`;
            return;
        }

        tbody.innerHTML = releases.map(r => `
            <tr>
                <td><strong>${escapeHtml(r.title)}</strong></td>
                <td>${escapeHtml(r.distillery || 'Unknown')}</td>
                <td><span style="color: var(--accent-blue); font-weight: 500;">${r.release_date || 'TBD'}</span></td>
                <td>${r.msrp || 'N/A'}</td>
                <td>
                    <span class="badge-status ${r.is_tracked ? 'badge-instock' : 'badge-outstock'}">
                        ${r.is_tracked ? 'TRACKED' : 'UNTRACKED'}
                    </span>
                </td>
                <td>
                    <button class="btn btn-primary btn-sm track-release-btn" data-title="${escapeHtml(r.title)}">
                        ➕ Track This
                    </button>
                    ${r.details_url ? `<a href="${r.details_url}" target="_blank" class="btn btn-secondary btn-sm">Read Info</a>` : ''}
                </td>
            </tr>
        `).join('');

        // Attach 1-click track button listeners
        document.querySelectorAll(".track-release-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                const title = btn.getAttribute("data-title");
                openTrackerModal({
                    name: `${title} Tracker`,
                    retailer: 'goody_goody',
                    url: `https://goodygoody.com/search?q=${encodeURIComponent(title)}`,
                    include_keywords: title.toLowerCase(),
                    exclude_keywords: 'old no 7, gentleman, honey, fire, apple'
                });
            });
        });
    }

    // 3. Trackers Management
    async function fetchTrackers() {
        try {
            const res = await fetch("/api/trackers");
            trackers = await res.json();
            renderTrackers();
            document.getElementById("stat-trackers-active").textContent = trackers.filter(t => t.enabled).length;
        } catch (err) {
            console.error("Failed to fetch trackers", err);
        }
    }

    function renderTrackers() {
        const grid = document.getElementById("trackers-grid");
        if (trackers.length === 0) {
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 40px;">No target scrapers configured yet. Click "Add New Tracker" to create one.</div>`;
            return;
        }

        grid.innerHTML = trackers.map(t => `
            <div class="tracker-card">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <h4 class="tracker-title">${escapeHtml(t.name)}</h4>
                        <span class="badge-retailer badge-${t.retailer}">${t.retailer.replace('_', ' ')}</span>
                    </div>
                    <div class="tracker-url">${escapeHtml(t.url)}</div>
                    <div class="tracker-rules">
                        <div><strong>Include:</strong> ${t.include_keywords || 'None (All)'}</div>
                        <div style="margin-top: 4px;"><strong>Exclude:</strong> ${t.exclude_keywords || 'None'}</div>
                    </div>
                </div>
                <div class="tracker-actions">
                    <span class="badge-status ${t.enabled ? 'badge-instock' : 'badge-outstock'}">
                        ${t.enabled ? 'ACTIVE' : 'DISABLED'}
                    </span>
                    <div>
                        <button class="btn btn-secondary btn-sm edit-tracker-btn" data-id="${t.id}">✏️ Edit</button>
                        <button class="btn btn-danger btn-sm delete-tracker-btn" data-id="${t.id}">🗑️</button>
                    </div>
                </div>
            </div>
        `).join('');

        // Event listeners
        document.querySelectorAll(".edit-tracker-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                const id = parseInt(btn.getAttribute("data-id"));
                const tracker = trackers.find(t => t.id === id);
                if (tracker) openTrackerModal(tracker);
            });
        });

        document.querySelectorAll(".delete-tracker-btn").forEach(btn => {
            btn.addEventListener("click", async () => {
                const id = parseInt(btn.getAttribute("data-id"));
                if (confirm("Are you sure you want to delete this target scraper rule?")) {
                    await deleteTracker(id);
                }
            });
        });
    }

    // Modal Control
    const modal = document.getElementById("tracker-modal");
    const trackerForm = document.getElementById("tracker-form");

    function openTrackerModal(data = null) {
        document.getElementById("tracker_id").value = data && data.id ? data.id : "";
        document.getElementById("tracker_name").value = data ? data.name : "";
        document.getElementById("tracker_retailer").value = data ? data.retailer : "goody_goody";
        document.getElementById("tracker_url").value = data ? data.url : "";
        document.getElementById("tracker_include").value = data ? data.include_keywords : "";
        document.getElementById("tracker_exclude").value = data ? data.exclude_keywords : "";
        document.getElementById("tracker_enabled").checked = data ? data.enabled : true;

        document.getElementById("modal-title").textContent = data && data.id ? "Edit Target Scraper" : "Add Target Scraper";
        modal.classList.add("active");
    }

    function closeModal() {
        modal.classList.remove("active");
    }

    document.getElementById("add-tracker-btn").addEventListener("click", () => openTrackerModal());
    document.querySelectorAll(".modal-close, .modal-close-btn").forEach(el => el.addEventListener("click", closeModal));

    trackerForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const id = document.getElementById("tracker_id").value;
        const payload = {
            name: document.getElementById("tracker_name").value,
            retailer: document.getElementById("tracker_retailer").value,
            url: document.getElementById("tracker_url").value,
            include_keywords: document.getElementById("tracker_include").value,
            exclude_keywords: document.getElementById("tracker_exclude").value,
            enabled: document.getElementById("tracker_enabled").checked
        };

        try {
            const url = id ? `/api/trackers/${id}` : "/api/trackers";
            const method = id ? "PUT" : "POST";
            const res = await fetch(url, {
                method: method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                showToast(id ? "Tracker updated!" : "New tracker created!", "success");
                closeModal();
                fetchTrackers();
            } else {
                showToast("Failed to save tracker.", "error");
            }
        } catch (err) {
            showToast("Network error saving tracker.", "error");
        }
    });

    const aiBtn = document.getElementById("ai-generate-btn");
    if (aiBtn) {
        aiBtn.addEventListener("click", async () => {
            const trackerName = document.getElementById("tracker_name").value;
            if (!trackerName) {
                showToast("Please enter a Tracker Name first (e.g. Jack Daniel's Coy Hill)", "info");
                return;
            }

            aiBtn.disabled = true;
            aiBtn.innerHTML = "<span>⏳ Analyzing...</span>";

            try {
                const res = await fetch("/api/ai/suggest-keywords", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ bourbon_name: trackerName })
                });
                const data = await res.json();
                if (res.ok) {
                    document.getElementById("tracker_include").value = data.include_keywords || "";
                    document.getElementById("tracker_exclude").value = data.exclude_keywords || "";

                    const badge = document.getElementById("ai-reasoning-badge");
                    if (badge) {
                        badge.style.display = "block";
                        badge.innerHTML = `<strong>Matched:</strong> ${data.preset_matched}<br>${data.reasoning}`;
                    }

                    showToast(`🤖 AI generated optimal keywords for '${trackerName}'!`, "success");
                } else {
                    showToast("AI keyword generation failed.", "error");
                }
            } catch (err) {
                showToast("Error connecting to AI Assistant.", "error");
            } finally {
                aiBtn.disabled = false;
                aiBtn.innerHTML = "<span>✨ Generate Keywords</span>";
            }
        });
    }

    async function deleteTracker(id) {
        try {
            const res = await fetch(`/api/trackers/${id}`, { method: "DELETE" });
            if (res.ok) {
                showToast("Tracker deleted", "info");
                fetchTrackers();
            }
        } catch (err) {
            showToast("Error deleting tracker", "error");
        }
    }

    // 4. SMTP Settings Form
    async function fetchSMTP() {
        try {
            const res = await fetch("/api/smtp");
            const data = await res.json();
            if (data) {
                document.getElementById("smtp_host").value = data.host || "";
                document.getElementById("smtp_port").value = data.port || 587;
                document.getElementById("smtp_username").value = data.username || "";
                document.getElementById("smtp_password").value = data.password || "";
                document.getElementById("smtp_use_tls").checked = data.use_tls !== false;
                document.getElementById("smtp_use_ssl").checked = data.use_ssl === true;
                document.getElementById("smtp_sender").value = data.sender_email || "";
                document.getElementById("smtp_recipient").value = data.recipient_email || "";
            }
        } catch (err) {
            console.error("Failed to fetch SMTP settings", err);
        }
    }

    document.getElementById("smtp-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            host: document.getElementById("smtp_host").value,
            port: parseInt(document.getElementById("smtp_port").value),
            username: document.getElementById("smtp_username").value,
            password: document.getElementById("smtp_password").value,
            use_tls: document.getElementById("smtp_use_tls").checked,
            use_ssl: document.getElementById("smtp_use_ssl").checked,
            sender_email: document.getElementById("smtp_sender").value,
            recipient_email: document.getElementById("smtp_recipient").value
        };

        try {
            const res = await fetch("/api/smtp", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                showToast("SMTP Settings saved successfully!", "success");
            } else {
                showToast("Failed to save SMTP settings.", "error");
            }
        } catch (err) {
            showToast("Error saving SMTP settings", "error");
        }
    });

    document.getElementById("test-email-btn").addEventListener("click", async () => {
        showToast("Sending test email...", "info");
        try {
            const res = await fetch("/api/smtp/test", { method: "POST" });
            const data = await res.json();
            if (res.ok && data.status === "success") {
                showToast("✅ Test email sent successfully! Check your inbox.", "success");
            } else {
                showToast(`❌ Test Email Failed: ${data.detail || data.message || "Unknown error"}`, "error");
            }
        } catch (err) {
            showToast("Error triggering test email.", "error");
        }
    });

    // 5. System Logs
    async function fetchLogs() {
        try {
            const res = await fetch("/api/logs");
            const logs = await res.json();
            const tbody = document.getElementById("logs-table-body");

            if (logs.length === 0) {
                tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No log records yet.</td></tr>`;
                return;
            }

            tbody.innerHTML = logs.map(l => `
                <tr>
                    <td style="font-size: 12px; color: var(--text-secondary);">${formatDate(l.timestamp)}</td>
                    <td>
                        <span class="badge-status ${l.status === 'SUCCESS' ? 'badge-instock' : 'badge-outstock'}">
                            ${l.status}
                        </span>
                    </td>
                    <td><strong>${l.items_found}</strong></td>
                    <td style="font-size: 13px;">${escapeHtml(l.message)}</td>
                </tr>
            `).join('');
        } catch (err) {
            console.error("Failed to fetch logs", err);
        }
    }

    // 6. Schedule Management
    async function fetchSchedule() {
        try {
            const res = await fetch("/api/schedule");
            const data = await res.json();
            if (data) {
                const select = document.getElementById("scrape-interval-select");
                if (select) select.value = data.scrape_interval_minutes || 30;

                const nextRunLabel = document.getElementById("next-run-label");
                if (nextRunLabel) {
                    nextRunLabel.textContent = data.next_run ? `Next check: ${formatDate(data.next_run)}` : "Next check: Scheduled";
                }
            }
        } catch (err) {
            console.error("Failed to fetch schedule", err);
        }
    }

    const scheduleSelect = document.getElementById("scrape-interval-select");
    if (scheduleSelect) {
        scheduleSelect.addEventListener("change", async () => {
            const val = parseInt(scheduleSelect.value);
            try {
                const res = await fetch("/api/schedule", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ scrape_interval_minutes: val })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(`⏱️ Scrape schedule updated to every ${val} minutes!`, "success");
                    if (data.next_run) {
                        document.getElementById("next-run-label").textContent = `Next check: ${formatDate(data.next_run)}`;
                    }
                } else {
                    showToast("Failed to update schedule.", "error");
                }
            } catch (err) {
                showToast("Error updating schedule.", "error");
            }
        });
    }

    // Manual Scrape Trigger Button
    const scrapeBtn = document.getElementById("run-scrape-btn");
    scrapeBtn.addEventListener("click", async () => {
        scrapeBtn.disabled = true;
        scrapeBtn.innerHTML = `<span>⏳</span> <span>Scraping...</span>`;
        showToast("Scrape cycle launched! Scraping target sites...", "info");

        try {
            const res = await fetch("/api/scrape-now", { method: "POST" });
            const data = await res.json();
            if (res.ok) {
                showToast(`Scrape completed! ${data.items_found} items parsed.`, "success");
                fetchProducts();
                fetchLogs();
                fetchSchedule();
                updateLastRunLabel();
            } else {
                showToast("Scrape cycle failed.", "error");
            }
        } catch (err) {
            showToast("Error running scrape.", "error");
        } finally {
            scrapeBtn.disabled = false;
            scrapeBtn.innerHTML = `<span class="btn-icon">⚡</span> <span>Run Scrape Now</span>`;
        }
    });

    function updateLastRunLabel() {
        const now = new Date().toLocaleTimeString();
        document.getElementById("last-run-label").textContent = `Last check: ${now}`;
    }

    // Utilities
    function formatDate(str) {
        if (!str) return "Never";
        const date = new Date(str);
        return date.toLocaleString();
    }

    function escapeHtml(str) {
        if (!str) return "";
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    // Initial Load
    fetchProducts();
    fetchTrackers();
    fetchSchedule();
    updateLastRunLabel();
    setInterval(fetchProducts, 30000); // Auto refresh dashboard every 30s
});
