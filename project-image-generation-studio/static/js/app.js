/* =========================================================================
   Orchestra — frontend logic.

   Note on the pipeline monitor: the backend runs the full six-stage
   pipeline synchronously and returns a complete, REAL event log (every
   status here actually happened server-side — see services/pipeline.py).
   This script replays that log with short delays so the monitor reads as
   live, rather than streaming it over a websocket. That trade-off is
   intentional and documented in the README.
   ========================================================================= */

const els = {
  form: document.getElementById('generate-form'),
  prompt: document.getElementById('prompt'),
  negativePrompt: document.getElementById('negative_prompt'),
  promptCount: document.getElementById('prompt-count'),
  negativeCount: document.getElementById('negative-count'),
  ratioCards: document.getElementById('ratio-cards'),
  ratioDetails: document.getElementById('ratio-details'),
  numImages: document.getElementById('num_images'),
  stylePreset: document.getElementById('style_preset'),
  generateBtn: document.getElementById('generate-btn'),
  inspectorToggle: document.getElementById('inspector-toggle'),
  payloadInspector: document.getElementById('payload-inspector'),
  pipelineMonitor: document.getElementById('pipeline-monitor'),
  emptyState: document.getElementById('empty-state'),
  skeletonState: document.getElementById('skeleton-state'),
  errorState: document.getElementById('error-state'),
  errorCode: document.getElementById('error-code'),
  errorMessage: document.getElementById('error-message'),
  imageResult: document.getElementById('image-result'),
  imageActions: document.getElementById('image-actions'),
  resultMeta: document.getElementById('result-meta'),
  resultImage: document.getElementById('result-image'),
  technicalDetails: document.getElementById('technical-details'),
  exportHub: document.getElementById('export-hub'),
  metaPrompt: document.getElementById('meta-prompt'),
  metaResolution: document.getElementById('meta-resolution'),
  metaFilesize: document.getElementById('meta-filesize'),
  metaAesthetic: document.getElementById('meta-aesthetic'),
  metaSemantic: document.getElementById('meta-semantic'),
  techGrid: document.getElementById('tech-grid'),
  btnPreview: document.getElementById('btn-preview'),
  btnDownload: document.getElementById('btn-download'),
  btnRegenerate: document.getElementById('btn-regenerate'),
  previewModal: document.getElementById('preview-modal'),
  modalImage: document.getElementById('modal-image'),
  modalClose: document.getElementById('modal-close'),
  toastStack: document.getElementById('toast-stack'),
  navBtns: document.querySelectorAll('.nav-btn'),
  panelStudio: document.getElementById('panel-studio'),
  panelHistory: document.getElementById('panel-history'),
  historyGrid: document.getElementById('history-grid'),
  exportCards: document.querySelectorAll('.export-card'),
};

let selectedRatio = '1:1';
let lastResult = null;

/* ---------------- char counters ---------------- */
els.prompt.addEventListener('input', () => {
  els.promptCount.textContent = `${els.prompt.value.length} / ${els.prompt.maxLength}`;
});
els.negativePrompt.addEventListener('input', () => {
  els.negativeCount.textContent = `${els.negativePrompt.value.length} / ${els.negativePrompt.maxLength}`;
});

/* ---------------- aspect ratio cards ---------------- */
function renderRatioDetails(ratioKey) {
  const info = window.STUDIO_CONFIG.aspectRatios[ratioKey];
  if (!info) return;
  els.ratioDetails.textContent =
    `${info.width}×${info.height} · ${info.pixel_volume.toLocaleString()} px · ${info.use_case}`;
}
els.ratioCards.addEventListener('click', (e) => {
  const card = e.target.closest('.ratio-card');
  if (!card) return;
  document.querySelectorAll('.ratio-card').forEach(c => c.classList.remove('selected'));
  card.classList.add('selected');
  selectedRatio = card.dataset.ratio;
  renderRatioDetails(selectedRatio);
});
renderRatioDetails(selectedRatio);

/* ---------------- payload inspector ---------------- */
els.inspectorToggle.addEventListener('click', () => {
  els.payloadInspector.hidden = !els.payloadInspector.hidden;
});

/* ---------------- toasts ---------------- */
function toast(message, kind = 'default') {
  const t = document.createElement('div');
  t.className = `toast ${kind}`;
  t.textContent = message;
  els.toastStack.appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

/* ---------------- pipeline monitor ---------------- */
const STAGE_STATUS_LABELS = {
  WAITING: 'Waiting', PROCESSING: 'Processing', SUCCESS: 'Success',
  RETRYING: 'Retrying', REJECTED: 'Rejected', FAILED: 'Failed',
};

function resetPipeline() {
  document.querySelectorAll('.stage').forEach(stage => {
    stage.className = 'stage';
    stage.querySelector('.stage-status').textContent = 'Waiting';
  });
}

function setStageStatus(stageName, status) {
  const el = document.querySelector(`.stage[data-stage="${stageName}"]`);
  if (!el) return;
  el.className = `stage ${status.toLowerCase()}`;
  el.querySelector('.stage-status').textContent = STAGE_STATUS_LABELS[status] || status;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function replayEvents(events) {
  for (const evt of events) {
    setStageStatus(evt.stage, evt.status);
    await sleep(evt.status === 'PROCESSING' ? 260 : 160);
  }
}

/* ---------------- result states ---------------- */
function showState(name) {
  const showResultLayout = ['image', 'skeleton', 'error'].includes(name);
  const isImage = name === 'image';
  const isError = name === 'error';

  if (els.emptyState) els.emptyState.hidden = name !== 'empty';
  if (els.skeletonState) els.skeletonState.hidden = name !== 'skeleton';
  if (els.errorState) els.errorState.hidden = !isError;
  if (els.imageResult) els.imageResult.hidden = name === 'empty';
  if (els.imageActions) els.imageActions.hidden = !isImage;
  if (els.resultMeta) els.resultMeta.hidden = !showResultLayout;
  if (els.technicalDetails) els.technicalDetails.hidden = name === 'empty';
  if (els.exportHub) els.exportHub.hidden = name === 'empty';
  if (els.resultImage) els.resultImage.hidden = !isImage;

  if (name === 'empty' && els.technicalDetails) {
    els.technicalDetails.removeAttribute('open');
  }
}

function renderError(code, message) {
  els.errorCode.textContent = code || 'ERROR';
  els.errorMessage.textContent = message || 'Something went wrong.';
  els.errorState.hidden = false;
  els.technicalDetails.hidden = false;
  els.technicalDetails.open = true;
  els.exportHub.hidden = false;
  els.resultMeta.hidden = false;
  els.imageResult.hidden = false;
  els.imageActions.hidden = true;
  els.resultImage.hidden = true;
  els.skeletonState.hidden = false;
}

function renderResult(data) {
  lastResult = data;
  els.resultImage.src = data.image_url;
  els.technicalDetails.open = true;
  els.metaPrompt.textContent = data.payload.prompt;
  els.metaResolution.textContent = `${data.integrity.width} × ${data.integrity.height}`;
  els.metaFilesize.textContent = `${(data.integrity.byte_size / 1024).toFixed(1)} KB`;
  els.metaAesthetic.textContent = `${data.qa.aesthetic.score} / 10`;
  els.metaSemantic.textContent = data.qa.semantic.evaluated
    ? `${data.qa.semantic.score} / 10`
    : 'Not evaluated (heuristic mode)';

  els.techGrid.innerHTML = '';
  const techFields = {
    'Request ID': data.request_id,
    'Provider': data.payload.model,
    'Aspect ratio': data.payload.aspect_ratio,
    'Generation attempt': data.attempts_used,
    'SHA-256': data.integrity.checksum,
    'Format': data.integrity.image_format,
    'Aesthetic method': data.qa.aesthetic.method,
    'Semantic method': data.qa.semantic.method,
  };
  for (const [k, v] of Object.entries(techFields)) {
    const row = document.createElement('div');
    row.innerHTML = `<span>${k}</span><br>${v ?? '—'}`;
    els.techGrid.appendChild(row);
  }

  showState('image');
}

/* ---------------- generate ---------------- */
async function runGenerate(endpoint = '/api/generate') {
  const payload = {
    prompt: els.prompt.value,
    negative_prompt: els.negativePrompt.value,
    aspect_ratio: selectedRatio,
    num_images: parseInt(els.numImages.value, 10),
    style_preset: els.stylePreset.value,
  };

  els.generateBtn.disabled = true;
  els.generateBtn.querySelector('.btn-spinner').hidden = false;
  resetPipeline();
  showState('skeleton');

  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    els.payloadInspector.textContent = JSON.stringify(data.payload || {}, null, 2);

    await replayEvents(data.events || []);

    if (!data.success) {
      renderError(data.error.code, data.error.message);
      toast(data.error.message, 'error');
      return;
    }

    renderResult(data);
    toast('Image generated and verified.', 'success');
  } catch (err) {
    renderError('NETWORK_ERROR', 'Could not reach the server. Is the Flask app running?');
    toast('Network error', 'error');
  } finally {
    els.generateBtn.disabled = false;
    els.generateBtn.querySelector('.btn-spinner').hidden = true;
  }
}

els.form.addEventListener('submit', (e) => {
  e.preventDefault();
  runGenerate('/api/generate');
});

els.btnRegenerate.addEventListener('click', () => runGenerate('/api/regenerate'));

/* ---------------- preview modal ---------------- */
els.btnPreview.addEventListener('click', () => {
  if (!lastResult) return;
  els.modalImage.src = lastResult.image_url;
  els.previewModal.hidden = false;
});
els.modalClose.addEventListener('click', () => { els.previewModal.hidden = true; });
els.previewModal.addEventListener('click', (e) => {
  if (e.target === els.previewModal) els.previewModal.hidden = true;
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') els.previewModal.hidden = true;
});

/* ---------------- download ---------------- */
els.btnDownload.addEventListener('click', () => {
  if (!lastResult) return;
  window.location.href = `/api/download/${lastResult.filename}`;
});

/* ---------------- export hub ---------------- */
els.exportCards.forEach(card => {
  card.addEventListener('click', async () => {
    if (!lastResult) { toast('Generate and accept an image first.', 'error'); return; }
    const kind = card.dataset.kind;
    try {
      const res = await fetch(`/api/export/${kind}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: lastResult.filename,
          metadata: { ...lastResult.payload, request_id: lastResult.request_id },
        }),
      });
      const data = await res.json();
      if (data.success) {
        toast(`Export package created for ${kind}.`, 'success');
      } else {
        toast(data.error.message, 'error');
      }
    } catch {
      toast('Export failed — network error.', 'error');
    }
  });
});

/* ---------------- nav / history ---------------- */
els.navBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    els.navBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const panel = btn.dataset.panel;
    els.panelStudio.hidden = panel !== 'studio';
    els.panelHistory.hidden = panel !== 'history';
    if (panel === 'history') loadHistory();
  });
});

async function loadHistory() {
  try {
    const res = await fetch('/api/history');
    const data = await res.json();
    els.historyGrid.innerHTML = '';
    if (!data.history || data.history.length === 0) {
      els.historyGrid.innerHTML = '<p class="history-empty">No generations yet — accepted images will appear here.</p>';
      return;
    }
    for (const item of data.history) {
      const card = document.createElement('div');
      card.className = 'history-card';
      card.innerHTML = `
        <img src="/api/assets/${item.filename}" alt="">
        <div class="history-card-body">
          <div>${item.aspect_ratio} · ${item.width}×${item.height}</div>
          <div>Aesthetic ${item.aesthetic_score}/10</div>
        </div>`;
      els.historyGrid.appendChild(card);
    }
  } catch {
    els.historyGrid.innerHTML = '<p class="history-empty">Could not load history.</p>';
  }
}
