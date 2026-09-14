// Prepza service-worker registration and safe update prompt.
// O1 keeps the current session stable: a new worker may install in the
// background, but it does not reload the app until the user explicitly taps
// Update. This prevents background deployments from throwing users back to a
// splash/home screen mid-session.
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

  var reloading = false;
  navigator.serviceWorker.addEventListener('controllerchange', function () {
    if (reloading) return;
    reloading = true;
    window.location.reload();
  });

  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/sw.js').then(function (registration) {
      // Never force an update into an active session. If a worker is already
      // waiting, surface the same explicit prompt instead.
      if (registration.waiting && navigator.serviceWorker.controller) {
        showUpdateToast(registration.waiting);
      }

      registration.addEventListener('updatefound', function () {
        var newWorker = registration.installing;
        if (!newWorker) return;

        newWorker.addEventListener('statechange', function () {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            showUpdateToast(newWorker);
          }
        });
      });

      registration.update().catch(function () {});
    }).catch(function (err) {
      console.warn('Service worker registration failed:', err);
    });
  });
})();
