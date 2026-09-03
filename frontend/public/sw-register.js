// Shared service worker registration + update-toast UI for all Prepza pages.
// Replaces the old inline "navigator.serviceWorker.register(...)" block that
// was duplicated across all 14 HTML pages.
//
// Update flow: sw.js (v4+) installs a new worker but does NOT auto-activate
// it (no self.skipWaiting() in install()). This script detects that a new
// worker is waiting (or starts installing while the tab is open), shows a
// small toast with an "Update" button, and only tells the worker to take
// over once the user clicks it. This keeps updates explicit rather than
// silently swapping content under someone mid-session.
(function () {
  if (!('serviceWorker' in navigator)) return;

  function showUpdateToast(worker) {
    if (document.getElementById('prepza-update-toast')) return;

    var toast = document.createElement('div');
    toast.id = 'prepza-update-toast';
    toast.style.cssText = [
      'position:fixed',
      'left:50%',
      'bottom:24px',
      'transform:translateX(-50%)',
      'background:#16233E',
      'color:#ffffff',
      'padding:12px 16px',
      'border-radius:10px',
      'box-shadow:0 4px 16px rgba(0,0,0,0.28)',
      'display:flex',
      'align-items:center',
      'gap:12px',
      'font-family:"Inter",system-ui,sans-serif',
      'font-size:14px',
      'z-index:9999',
      'max-width:calc(100vw - 32px)'
    ].join(';');

    var text = document.createElement('span');
    text.textContent = 'New version available';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = 'Update';
    btn.style.cssText = [
      'background:#C9A227',
      'color:#16233E',
      'border:none',
      'border-radius:6px',
      'padding:6px 14px',
      'font-weight:600',
      'cursor:pointer',
      'font-size:14px',
      'font-family:inherit',
      'white-space:nowrap'
    ].join(';');

    btn.addEventListener('click', function () {
      btn.disabled = true;
      btn.style.cursor = 'default';
      btn.textContent = 'Updating…';
      worker.postMessage({ type: 'SKIP_WAITING' });
    });

    toast.appendChild(text);
    toast.appendChild(btn);
    document.body.appendChild(toast);
  }

  // Reload exactly once, when the new worker actually takes control -
  // not before, so we don't reload into a page a waiting worker can't
  // yet serve consistently.
  var reloading = false;
  navigator.serviceWorker.addEventListener('controllerchange', function () {
    if (reloading) return;
    reloading = true;
    window.location.reload();
  });

  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/sw.js').then(function (registration) {
      // Case 1: a previous visit already left an update waiting. This is a
      // fresh page load (e.g. an installed PWA being reopened) - there's no
      // in-progress session to disrupt, and the user is likely staring at
      // the *old* shell right now (stale splash, stale logo, etc), so we
      // apply the update immediately instead of making them notice and tap
      // a toast on a screen that looks fine to them.
      if (registration.waiting && navigator.serviceWorker.controller) {
        registration.waiting.postMessage({ type: 'SKIP_WAITING' });
      }

      // Case 2: a new worker starts installing during this visit, i.e. the
      // user already has the app open and in use. Prompt instead of
      // swapping content out from under them mid-session.
      registration.addEventListener('updatefound', function () {
        var newWorker = registration.installing;
        if (!newWorker) return;

        newWorker.addEventListener('statechange', function () {
          // Only prompt if this page already had a controller - otherwise
          // this is just the very first install, with nothing to update
          // from, and no toast is needed.
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            showUpdateToast(newWorker);
          }
        });
      });

      // Browsers (especially for installed/standalone PWAs launched outside
      // a normal navigation) can be slow or inconsistent about checking for
      // a new sw.js in the background. Ask explicitly on every load so a
      // waiting worker shows up as soon as possible instead of sitting
      // unnoticed for days.
      registration.update().catch(function () {});
    }).catch(function (err) {
      console.warn('Service worker registration failed:', err);
    });
  });
})();
