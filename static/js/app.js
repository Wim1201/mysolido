/* === MySolido JavaScript === */

/* --- Dark Mode Toggle --- */
function toggleTheme() {
    var html = document.documentElement;
    var current = html.dataset.theme;
    var next = current === 'dark' ? '' : 'dark';
    html.dataset.theme = next;
    if (next) {
        localStorage.setItem('mysolido-theme', next);
    } else {
        localStorage.removeItem('mysolido-theme');
    }
    // Update settings toggle if on settings page
    var toggle = document.getElementById('dark-mode-toggle');
    if (toggle) {
        toggle.checked = next === 'dark';
    }
}

/* --- Dropdown Toggles --- */
function toggleMove(btn) {
    var dropdown = btn.closest('.move-wrapper').querySelector('.move-dropdown');
    closeAllDropdowns(dropdown);
    dropdown.classList.toggle('show');
}

function toggleShare(btn) {
    var dropdown = btn.closest('.share-wrapper').querySelector('.share-dropdown');
    closeAllDropdowns(dropdown);
    dropdown.classList.toggle('show');
}

function toggleWebidField(select) {
    var form = select.closest('form');
    var webidLabel = form.querySelector('.webid-label');
    var webidInput = form.querySelector('.webid-input');
    if (select.value === 'public') {
        webidLabel.style.display = 'none';
        webidInput.style.display = 'none';
        webidInput.removeAttribute('required');
    } else {
        webidLabel.style.display = '';
        webidInput.style.display = '';
        webidInput.setAttribute('required', '');
    }
}

function toggleShareLinkForm(btn) {
    var fileItem = btn.closest('.file-item');
    var form = fileItem.querySelector('.share-link-form');
    if (form) {
        form.style.display = form.style.display === 'none' ? '' : 'none';
    }
}

function closeAllDropdowns(except) {
    document.querySelectorAll('.move-dropdown.show, .share-dropdown.show').forEach(function(d) {
        if (d !== except) d.classList.remove('show');
    });
}

// Close dropdowns when clicking outside
document.addEventListener('click', function(e) {
    if (!e.target.closest('.move-wrapper') && !e.target.closest('.share-wrapper')) {
        closeAllDropdowns();
    }
});

/* --- Share Link Copy --- */
function copyShareLink() {
    var input = document.getElementById('share-link-url');
    if (!input) return;
    navigator.clipboard.writeText(input.value).then(function() {
        var btn = input.nextElementSibling;
        var orig = btn.innerHTML;
        btn.textContent = 'Gekopieerd!';
        setTimeout(function() { btn.innerHTML = orig; }, 2000);
    });
}

/* --- Loading Spinner --- */
function showSpinner() {
    document.getElementById('spinner-overlay').classList.add('active');
}

(function() {
    // Show spinner on form submits (upload, search, create folder)
    document.querySelectorAll('form').forEach(function(form) {
        // Skip delete forms (they have confirm dialogs)
        if (form.action && form.action.includes('/delete')) return;
        // Skip move/share dropdown forms
        if (form.closest('.move-dropdown') || form.closest('.share-dropdown')) return;

        form.addEventListener('submit', function() {
            showSpinner();
            // Disable submit buttons to prevent double-click
            form.querySelectorAll('button[type="submit"]').forEach(function(btn) {
                btn.disabled = true;
            });
        });
    });

    // Show spinner on folder card clicks (dashboard)
    document.querySelectorAll('.folder-card').forEach(function(card) {
        card.addEventListener('click', function() {
            showSpinner();
        });
    });
})();

/* --- Drag and Drop Upload --- */
(function() {
    var zone = document.querySelector('.upload-zone');
    if (!zone) return;

    var fileInput = zone.querySelector('input[type="file"]');
    var form = zone.closest('form');

    zone.addEventListener('click', function() {
        fileInput.click();
    });

    fileInput.addEventListener('change', function() {
        if (fileInput.files.length > 0) {
            form.submit();
        }
    });

    zone.addEventListener('dragover', function(e) {
        e.preventDefault();
        zone.classList.add('drag-over');
    });

    zone.addEventListener('dragleave', function() {
        zone.classList.remove('drag-over');
    });

    zone.addEventListener('drop', function(e) {
        e.preventDefault();
        zone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            form.submit();
        }
    });
})();
