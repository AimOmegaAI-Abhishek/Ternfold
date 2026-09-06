/* Files go directly to a scoped Supabase signed URL; the app validates before saving. */
(() => {
  document.querySelectorAll('form[action$="/upload"]').forEach(form => {
    let retry = null;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"], button:not([type])');
      const file = form.querySelector('input[type="file"]').files[0];
      if (!file) return;
      let message = form.querySelector('[data-upload-state]');
      if (!message) { message = document.createElement('p'); message.dataset.uploadState = ''; message.setAttribute('role', 'status'); message.setAttribute('aria-live', 'polite'); message.className = 'wide'; form.append(message); }
      const original = button.textContent;
      button.disabled = true;
      const json = async (url, body) => {
        const response = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        let value; try { value = await response.json(); } catch { throw new Error('The server did not return a saved result. Your selected file is preserved; retry.'); }
        if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Upload could not be saved. Check the file and retry.');
        return value;
      };
      try {
        if (file.size > 10000000 || file.size === 0) throw new Error('Choose a nonempty file up to 10 MB.');
        const capabilityResponse = await fetch('/storage/upload-capability');
        let capability; try { capability = await capabilityResponse.json(); } catch { capability = {}; }
        if (!capabilityResponse.ok) throw new Error(typeof capability.detail === 'string' ? capability.detail : 'Your session is unavailable. Sign in and retry.');
        if (!capability.direct) { HTMLFormElement.prototype.submit.call(form); return; }
        const values = new FormData(form);
        const fingerprint = [file.name, file.size, file.lastModified, values.get('category'), values.get('validity_end')].join('|');
        if (!retry || retry.fingerprint !== fingerprint) retry = {fingerprint, key: crypto.randomUUID()};
        const csrf = values.get('csrf');
        const base = form.action.replace(/\/upload$/, '/uploads');
        message.textContent = 'Checking the file and reserving upload space…';
        const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
        const sha256 = [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, '0')).join('');
        let reservation = retry.reservation;
        if (!reservation) {
          reservation = await json(base + '/reserve', {csrf, filename: file.name, size_bytes: file.size, sha256, category: values.get('category'), validity_end: values.get('validity_end'), request_key: retry.key});
          retry.reservation = reservation;
        }
        if (reservation.complete) { location.assign(reservation.next_url); return; }
        if (!retry.uploaded) {
          message.textContent = 'Uploading file to private storage…';
          const response = await fetch(reservation.upload_url, {method: 'PUT', headers: {'Content-Type': file.type || 'application/octet-stream', 'x-upsert': 'false'}, body: file});
          // A network retry may encounter the previously completed object. Finalization verifies its exact hash.
          if (!response.ok && response.status !== 409 && response.status !== 400) throw new Error('Private upload failed. Your selected file is preserved; retry.');
          retry.uploaded = true;
        }
        message.textContent = 'Validating the uploaded source and saving evidence…';
        const result = await json(base + '/' + reservation.intent_id + '/finalize', {csrf});
        message.textContent = 'Evidence saved.';
        location.assign(result.next_url);
      } catch (error) {
        message.textContent = error.message + ' Existing case work is preserved.';
        message.setAttribute('role', 'alert');
      } finally { button.disabled = false; button.textContent = original; }
    });
  });
})();
