// workout.js — PulseFit AI Workout Trainer
// APIs: /api/workout/start  /api/workout/frame  /api/workout/stop
//       /api/history/save  (saves session to Flask after stop)

// ══════════════════════════════════════════════════════════════
// CONFIG
// ══════════════════════════════════════════════════════════════
const FRAME_MS     = 120;
let REPS_PER_SET = 12;

const OK_WORDS   = ['good', 'great', 'perfect', 'squeeze', 'complete', 'well done', 'done'];
const WARN_WORDS = ['tuck', 'keep', 'relax', 'lock', 'lift', 'pin', 'step',
                    "don't", 'dont', 'all the way', 'full', 'cheat', 'back'];
const ERR_WORDS  = ["can't see", "can't", 'error', 'fail', 'unable', 'denied'];

// ══════════════════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════════════════
let selectedExercise = 'tricep_pushdown';
let isRunning        = false;
let repCount         = 0;
let setCount         = 0;
let lastReps         = 0;
let lastFeedback     = '';
let elapsedSeconds   = 0;
let timerHandle      = null;
let frameHandle      = null;
let cameraStream     = null;

// ══════════════════════════════════════════════════════════════
// DOM REFERENCES
// ══════════════════════════════════════════════════════════════
const videoEl      = document.getElementById('webcam-view');
const camOverlay   = document.getElementById('cam-overlay');
const cameraCard   = document.getElementById('camera-card');
const liveBadge    = document.getElementById('live-badge');
const repOverlay   = document.getElementById('rep-overlay');
const repBig       = document.getElementById('rep-count-big');
const statReps     = document.getElementById('stat-reps');
const statSets     = document.getElementById('stat-sets');
const boxReps      = document.getElementById('box-reps');
const boxSets      = document.getElementById('box-sets');
const timerDisp    = document.getElementById('timer-display');
const fbBubble     = document.getElementById('feedback-bubble');
const fbIcon       = document.getElementById('fb-icon');
const fbText       = document.getElementById('feedback-text');
const fbHistory    = document.getElementById('feedback-history');
const statusPill   = document.getElementById('status-pill');
const statusLabel  = document.getElementById('status-label');
const btnStart     = document.getElementById('btn-start');
const btnStop      = document.getElementById('btn-stop');
const setFlash     = document.getElementById('set-flash');

// ══════════════════════════════════════════════════════════════
// EXERCISE SELECT
// ══════════════════════════════════════════════════════════════
function selectExercise(key, el) {
  if (isRunning) return;
  document.querySelectorAll('.ex-btn').forEach(b => b.classList.remove('selected'));
  el.classList.add('selected');
  selectedExercise = key;
}

// ══════════════════════════════════════════════════════════════
// TIMER
// ══════════════════════════════════════════════════════════════
function startTimer() {
  elapsedSeconds = 0;
  timerDisp.classList.add('running');
  timerHandle = setInterval(() => {
    elapsedSeconds++;
    timerDisp.textContent =
      `${pad2(Math.floor(elapsedSeconds / 60))}:${pad2(elapsedSeconds % 60)}`;
  }, 1000);
}
function stopTimer() {
  clearInterval(timerHandle);
  timerHandle = null;
  timerDisp.classList.remove('running');
}
function pad2(n)       { return String(n).padStart(2, '0'); }
function formatTime(s) { return `${Math.floor(s / 60)}:${pad2(s % 60)}`; }

// ══════════════════════════════════════════════════════════════
// UI HELPERS
// ══════════════════════════════════════════════════════════════
function setStatus(state) {
  statusPill.className = `status-pill ${state}`;
  statusLabel.textContent = { idle: 'Idle', running: 'Live', done: 'Done' }[state] || state;
}

function classifyFeedback(text) {
  const t = text.toLowerCase();
  if (ERR_WORDS.some(w  => t.includes(w))) return 'err';
  if (OK_WORDS.some(w   => t.includes(w))) return 'ok';
  if (WARN_WORDS.some(w => t.includes(w))) return 'warn';
  return 'warn';
}

const ICONS = { ok: '✅', warn: '⚠️', err: '❌', info: '🤖' };

function setFeedback(text, type = 'warn') {
  if (text === lastFeedback) return;
  lastFeedback = text;
  fbText.textContent = text;
  fbIcon.textContent = ICONS[type] || '🤖';
  fbBubble.className = `feedback-bubble ${type}`;
  const li = document.createElement('li');
  li.textContent = text;
  fbHistory.prepend(li);
  if (fbHistory.children.length > 30) fbHistory.lastElementChild.remove();
}

function popEl(el) {
  el.classList.remove('pop');
  void el.offsetWidth;
  el.classList.add('pop');
  setTimeout(() => el.classList.remove('pop'), 200);
}

function setReps(reps) {
  if (reps === repCount) return;
  repCount = reps;
  popEl(repBig);
  popEl(statReps);
  repBig.textContent   = reps;
  statReps.textContent = reps;

  if (reps > 0 && reps % REPS_PER_SET === 0 && reps !== lastReps) {
    setCount++;
    statSets.textContent = setCount;
    popEl(statSets);
    setFlash.classList.remove('show');
    void setFlash.offsetWidth;
    setFlash.classList.add('show');
    boxSets.classList.add('highlight');
    setTimeout(() => boxSets.classList.remove('highlight'), 1500);
    setFeedback(`Set ${setCount} complete — rest up! 🎉`, 'ok');
  }
  lastReps = reps;
  boxReps.classList.add('highlight');
  setTimeout(() => boxReps.classList.remove('highlight'), 600);
}

// ══════════════════════════════════════════════════════════════
// CAMERA
// ══════════════════════════════════════════════════════════════
async function openCamera() {
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
      audio: false,
    });
    videoEl.srcObject = cameraStream;
    await videoEl.play();
    camOverlay.classList.add('hidden');
    cameraCard.classList.add('live');
    return true;
  } catch (err) {
    const msg = err.name === 'NotAllowedError'
      ? "Camera access denied — please allow camera permissions."
      : "Could not access camera. Make sure it's connected.";
    setFeedback(msg, 'err');
    return false;
  }
}

function closeCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach(t => t.stop());
    cameraStream = null;
  }
  videoEl.srcObject = null;
  cameraCard.classList.remove('live');
}

// ══════════════════════════════════════════════════════════════
// FRAME CAPTURE & SEND
// ══════════════════════════════════════════════════════════════
function captureAndSend() {
  if (!isRunning) return;
  const canvas  = document.createElement('canvas');
  canvas.width  = 640;
  canvas.height = 480;
  const ctx = canvas.getContext('2d');
  ctx.translate(640, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(videoEl, 0, 0, 640, 480);

  canvas.toBlob(async (blob) => {
    if (!blob || !isRunning) return;
    const form = new FormData();
    form.append('frame', blob, 'frame.jpg');
    try {
      const res  = await fetch('/api/workout/frame', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) return;
      setReps(data.reps ?? repCount);
      const fb = (data.feedback || '').trim();
      if (fb) setFeedback(fb, classifyFeedback(fb));
    } catch { /* network blip */ }
  }, 'image/jpeg', 0.75);
}

// ══════════════════════════════════════════════════════════════
// START
// ══════════════════════════════════════════════════════════════
async function startWorkout() {
  const camOk = await openCamera();
  if (!camOk) return;

  let res, data;
  try {
    res  = await fetch('/api/workout/start', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ exercise: selectedExercise }),
    });
    data = await res.json();
  } catch {
    setFeedback('Could not reach the server.', 'err');
    closeCamera();
    return;
  }

  if (!res.ok) {
    setFeedback(data.error || 'Failed to start workout.', 'err');
    closeCamera();
    return;
  }

  isRunning    = true;
  repCount     = 0;
  setCount     = 0;
  lastReps     = 0;
  lastFeedback = '';

  repBig.textContent   = '0';
  statReps.textContent = '0';
  statSets.textContent = '0';
  fbHistory.innerHTML  = '';

  liveBadge.classList.add('visible');
  repOverlay.classList.add('visible');
  btnStart.disabled = true;
  btnStop.disabled  = false;
  document.querySelectorAll('.ex-btn').forEach(b => b.disabled = true);

  setStatus('running');
  startTimer();
  setFeedback('Get into position — session started!', 'info');
  frameHandle = setInterval(captureAndSend, FRAME_MS);
}

// ══════════════════════════════════════════════════════════════
// STOP
// ══════════════════════════════════════════════════════════════
async function stopWorkout() {
  isRunning = false;
  clearInterval(frameHandle); frameHandle = null;
  stopTimer();
  closeCamera();

  liveBadge.classList.remove('visible');
  repOverlay.classList.remove('visible');
  camOverlay.classList.remove('hidden');

  btnStart.disabled = false;
  btnStop.disabled  = true;
  document.querySelectorAll('.ex-btn').forEach(b => {
    const tag = b.querySelector('.ex-tag');
    if (tag && tag.textContent.trim().toLowerCase() !== 'soon') b.disabled = false;
  });

  setStatus('done');
  setFeedback('Session complete — well done! 💪', 'ok');

  // Show modal IMMEDIATELY with current counts — no waiting
  showModal({ exercise: selectedExercise, reps: repCount });

  // Stop server + save history in background
  fetch('/api/workout/stop', { method: 'POST' })
    .then(r => r.json())
    .then(data => { if (data.summary) saveToHistory(data.summary); })
    .catch(() => saveToHistory(null));
}

// ══════════════════════════════════════════════════════════════
// HISTORY SAVE — sends completed session to /api/history/save
// so it's stored server-side and immediately visible on /history
// ══════════════════════════════════════════════════════════════
async function saveToHistory(summary) {
  try {
    await fetch('/api/history/save', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        exercise: summary?.exercise || selectedExercise,
        reps:     summary?.reps    ?? repCount,
        sets:     setCount,
        duration: formatTime(elapsedSeconds),
      }),
    });
  } catch {
    // Non-critical — doesn't break the workout flow
    console.warn('[PulseFit] History save failed.');
  }
}

// ══════════════════════════════════════════════════════════════
// RESET
// ══════════════════════════════════════════════════════════════
function resetSession() {
  if (isRunning) return;
  repCount       = 0;
  setCount       = 0;
  elapsedSeconds = 0;
  lastFeedback   = '';

  repBig.textContent    = '0';
  statReps.textContent  = '0';
  statSets.textContent  = '0';
  timerDisp.textContent = '00:00';

  fbHistory.innerHTML = '';
  fbText.textContent  = 'Select an exercise and press Start to begin.';
  fbIcon.textContent  = '🤖';
  fbBubble.className  = 'feedback-bubble';
  camOverlay.classList.remove('hidden');
  boxReps.classList.remove('highlight');
  boxSets.classList.remove('highlight');
  setStatus('idle');
}

// ══════════════════════════════════════════════════════════════
// MODAL
// ══════════════════════════════════════════════════════════════
function showModal(summary) {
  const exName = (summary?.exercise || selectedExercise)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());

  document.getElementById('modal-exercise-name').textContent = exName;
  document.getElementById('modal-reps').textContent     = summary?.reps ?? repCount;
  document.getElementById('modal-sets').textContent     = setCount;
  document.getElementById('modal-duration').textContent = formatTime(elapsedSeconds);
  document.getElementById('modal-backdrop').hidden = false;
}

function closeModal() {
  document.getElementById('modal-backdrop').hidden = true;
  resetSession();
}