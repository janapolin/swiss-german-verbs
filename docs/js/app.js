import { gradeCard, masteryRating, today } from './scheduler.js';
import {
  getProfiles, saveProfiles, getActiveProfile, setActiveProfile,
  getSettings, saveSettings, loadState, saveState, appendLog,
  getLog, getFlags, addFlag, renameProfile, deleteProfile,
} from './storage.js';
import { loadVerbs, getVerbById, defaultSettings, pickNextCard, countReviewsToday } from './session.js';

const DAILY_GOAL = 50;
const TENSE_LABELS = { present: 'Present', perfect: 'Past (Perfect)', future: 'Future', konj2: 'Would (Konj. II)' };
const PERSON_LABELS = { sg1: 'I', sg2: 'you', sg3: 'he', pl: 'we' };

let verbs = null;
let activeProfile = null;
let settings = null;
let currentCard = null;
let verbFilter = 'all';

// --- initialization ---

async function init() {
  try {
    verbs = await loadVerbs();
  } catch (e) {
    document.body.innerHTML = `<div class="page"><p class="muted">Failed to load verb data: ${e.message}</p></div>`;
    return;
  }

  activeProfile = getActiveProfile();
  if (!activeProfile || !getProfiles().includes(activeProfile)) {
    showProfilePicker();
  } else {
    settings = getSettings(activeProfile) ?? defaultSettings(verbs);
    showPractice();
  }
}

// --- screen routing ---

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(el => { el.style.display = 'none'; });
  const el = document.getElementById(`screen-${name}`);
  if (el) el.style.display = '';
  const nav = document.getElementById('bottom-nav');
  if (nav) nav.style.display = name === 'profile' ? 'none' : '';
  document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
  const active = document.querySelector(`[data-nav="${name}"]`);
  if (active) active.classList.add('active');
}

function toast(msg) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => {
    t.classList.add('fade-out');
    t.addEventListener('transitionend', () => t.remove());
  }, 1600);
}

// --- profile picker ---

function showProfilePicker() {
  showScreen('profile');
  const profiles = getProfiles();
  const list = document.getElementById('profile-list');
  list.innerHTML = profiles.map(name =>
    `<li><button class="profile-button" data-profile="${esc(name)}">${esc(name)}</button></li>`
  ).join('');
  list.querySelectorAll('.profile-button').forEach(btn => {
    btn.addEventListener('click', () => selectProfile(btn.dataset.profile));
  });
}

function selectProfile(name) {
  setActiveProfile(name);
  activeProfile = name;
  settings = getSettings(name) ?? defaultSettings(verbs);
  showPractice();
}

function createProfile(name) {
  name = name.trim();
  if (!name) return;
  const profiles = getProfiles();
  if (!profiles.includes(name)) { profiles.push(name); saveProfiles(profiles); }
  selectProfile(name);
}

// --- practice screen ---

async function showPractice() {
  showScreen('practice');
  currentCard = pickNextCard(activeProfile, verbs, settings);
  renderCard();
  updateProgress();
}

function renderCard() {
  const container = document.getElementById('card-container');
  if (!currentCard) {
    container.innerHTML = `
      <div class="flashcard flashcard-empty">
        <p class="card-pronoun">🎉</p>
        <p>You're all caught up!</p>
        <p class="muted">Check back later, or enable more verbs/tenses in Settings.</p>
      </div>`;
    return;
  }
  const tense = currentCard.tense;
  container.innerHTML = `
    <div class="prompt">
      <p class="prompt-infinitive placeholder" data-role="infinitive">${esc(currentCard.infinitive)}</p>
      <p class="prompt-gloss">${esc(currentCard.gloss)}</p>
    </div>
    <div class="flashcard" id="flashcard">
      <span class="tense-pill tense-${tense}">${esc(currentCard.tense_label)}</span>
      <p class="card-pronoun">${esc(currentCard.pronoun)}</p>
      <p class="card-answer placeholder" data-role="answer">${esc(currentCard.answer)}</p>
      <div class="card-bottom">
        <div class="card-action card-hint" data-role="hint">Tap to show answer</div>
        <div class="card-grades placeholder" data-role="grades">
          <div class="grade-form">
            <button class="grade-btn grade-hard" data-grade="hard">Hard</button>
            <button class="grade-btn grade-good" data-grade="good">Easy</button>
          </div>
        </div>
      </div>
    </div>
    <p class="flag-row hidden" id="flag-row">
      <button class="flag-btn" id="flag-btn">⚑ Flag this card</button>
    </p>`;

  container.querySelector('[data-role="hint"]').addEventListener('click', revealCard);
  container.querySelectorAll('.grade-btn').forEach(btn => {
    btn.addEventListener('click', () => submitGrade(btn.dataset.grade));
  });
  document.getElementById('flag-btn').addEventListener('click', flagCurrentCard);
}

function revealCard() {
  ['[data-role="infinitive"]', '[data-role="answer"]', '[data-role="grades"]'].forEach(sel => {
    document.querySelector(sel)?.classList.remove('placeholder');
  });
  document.querySelector('[data-role="hint"]')?.classList.add('placeholder');

  const card = document.getElementById('flashcard');
  if (card) {
    card.classList.add('flipping');
    card.addEventListener('animationend', function h() { card.classList.remove('flipping'); card.removeEventListener('animationend', h); });
  }
  document.getElementById('flag-row')?.classList.remove('hidden');
}

function submitGrade(gradeStr) {
  if (!currentCard) return;
  const existing = loadState(activeProfile, currentCard.cardKey);
  const next = gradeCard(existing, gradeStr, today());
  saveState(activeProfile, currentCard.cardKey, next);
  appendLog(activeProfile, { cardKey: currentCard.cardKey, grade: gradeStr, reviewedAt: new Date().toISOString() });
  currentCard = pickNextCard(activeProfile, verbs, settings);
  renderCard();
  updateProgress();
}

function updateProgress() {
  const reviewsToday = countReviewsToday(activeProfile);
  const pct = Math.min(reviewsToday / DAILY_GOAL * 100, 100);
  const fill = document.getElementById('progress-fill');
  const label = document.getElementById('progress-label');
  const met = document.getElementById('progress-goal-met');
  if (fill) fill.style.width = `${pct}%`;
  if (label) label.textContent = `Daily goal  ${reviewsToday} / ${DAILY_GOAL}`;
  if (met) met.classList.toggle('hidden', reviewsToday < DAILY_GOAL);
}

// --- flag a card ---

function flagCurrentCard() {
  if (!currentCard) return;
  const note = prompt('Optional note (e.g. "participle looks wrong"):', '') ?? '';
  addFlag(activeProfile, {
    cardKey: currentCard.cardKey,
    infinitive: currentCard.infinitive,
    tenseLabel: currentCard.tense_label,
    personLabel: PERSON_LABELS[currentCard.person] ?? currentCard.person,
    answer: currentCard.answer,
    note: note.trim(),
    flaggedAt: today(),
  });
  toast('Flagged for review');
}

// --- verbs screen ---

function showVerbs() {
  verbFilter = 'all';
  showScreen('verbs');
  renderVerbList();
}

function renderVerbList() {
  const enabled = new Set(settings.enabledVerbs);
  let list = verbs;
  if (verbFilter === 'enabled') list = verbs.filter(v => enabled.has(v.id));
  if (verbFilter === 'disabled') list = verbs.filter(v => !enabled.has(v.id));

  document.querySelectorAll('.verb-filter-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.filter === verbFilter);
  });

  const ul = document.getElementById('verb-list');
  ul.innerHTML = list.map(verb => `
    <li class="verb-list-item-row" id="verb-row-${verb.id}">
      <a href="#" class="verb-list-link" data-verb-id="${verb.id}">
        <span class="verb-infinitive">${esc(verb.infinitive)}</span>
        <span class="verb-gloss muted">${esc(verb.gloss)}</span>
      </a>
      <label class="toggle-switch verb-toggle">
        <input type="checkbox" ${enabled.has(verb.id) ? 'checked' : ''} data-verb-id="${verb.id}">
        <span class="toggle-slider"></span>
      </label>
    </li>`).join('');

  ul.querySelectorAll('.verb-list-link').forEach(a => {
    a.addEventListener('click', e => { e.preventDefault(); showVerbDetail(Number(a.dataset.verbId)); });
  });
  ul.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', () => toggleVerb(Number(cb.dataset.verbId), cb.checked));
  });
}

function toggleVerb(verbId, enabled) {
  const ids = new Set(settings.enabledVerbs);
  enabled ? ids.add(verbId) : ids.delete(verbId);
  settings = { ...settings, enabledVerbs: [...ids] };
  saveSettings(activeProfile, settings);
}

function setAllVerbs(enabled) {
  settings = { ...settings, enabledVerbs: enabled ? verbs.map(v => v.id) : [] };
  saveSettings(activeProfile, settings);
  renderVerbList();
}

// --- verb detail screen ---

function showVerbDetail(verbId) {
  const verb = getVerbById(verbs, verbId);
  if (!verb) return;
  showScreen('verb-detail');

  const tenseOrder = ['present', 'perfect', 'future', 'konj2'];
  const personOrder = ['sg1', 'sg2', 'sg3', 'pl'];

  const byTense = {};
  for (const [key, card] of Object.entries(verb.cards)) {
    (byTense[card.tense] ??= {})[card.person] = { ...card, cardKey: key };
  }

  let sections = '';
  for (const tense of tenseOrder) {
    if (!byTense[tense]) continue;
    sections += `<div class="tense-section"><h2><span class="tense-pill tense-${tense}">${TENSE_LABELS[tense]}</span></h2>
      <table class="conjugation-table">`;
    for (const person of personOrder) {
      const card = byTense[tense][person];
      if (!card) continue;
      const state = loadState(activeProfile, card.cardKey);
      const r = masteryRating(state);
      const stars = [0, 1, 2].map(i => `<span class="star ${i < r ? 'star-filled' : 'star-empty'}">★</span>`).join('');
      sections += `<tr>
        <td class="muted">${PERSON_LABELS[person]}</td>
        <td class="answer-cell">${esc(card.answer)}</td>
        <td class="rating-cell">${stars}</td>
      </tr>`;
    }
    sections += `</table></div>`;
  }

  document.getElementById('verb-detail-content').innerHTML = `
    <div class="verb-detail-header">
      <a href="#" class="back-link" id="back-to-verbs">← Verbs</a>
    </div>
    <h1>${esc(verb.infinitive)}</h1>
    <p class="muted">${esc(verb.gloss)}</p>
    ${verb.separable_prefix ? `<p class="muted">Separable prefix: <code>${esc(verb.separable_prefix)}-</code></p>` : ''}
    ${verb.notes ? `<p class="verb-notes">${esc(verb.notes)}</p>` : ''}
    ${sections}`;

  document.getElementById('back-to-verbs').addEventListener('click', e => { e.preventDefault(); showVerbs(); });
}

// --- settings screen ---

function showSettings() {
  showScreen('settings');
  renderSettings();
}

function renderSettings() {
  document.getElementById('settings-profile-name').textContent = activeProfile;
  const renameInput = document.getElementById('rename-input');
  if (renameInput) renameInput.value = '';

  // Tense toggles
  const tenseList = document.getElementById('tense-toggle-list');
  tenseList.innerHTML = ['present', 'perfect', 'future', 'konj2'].map(t => `
    <li class="toggle-row">
      <span>${TENSE_LABELS[t]}</span>
      <label class="toggle-switch">
        <input type="checkbox" data-tense="${t}" ${settings.tenses.includes(t) ? 'checked' : ''}>
        <span class="toggle-slider"></span>
      </label>
    </li>`).join('');
  tenseList.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', () => {
      const tenses = settings.tenses.filter(t => t !== cb.dataset.tense);
      if (cb.checked) tenses.push(cb.dataset.tense);
      settings = { ...settings, tenses };
      saveSettings(activeProfile, settings);
    });
  });

  // Profile switcher
  renderProfileSwitcher();

  // Stats
  const log = getLog(activeProfile);
  const todayStr = today();
  const statsEl = document.getElementById('profile-stats');
  if (statsEl) {
    const totalReviews = log.length;
    const todayReviews = log.filter(e => e.reviewedAt.startsWith(todayStr)).length;
    const cardsSeen = new Set(log.map(e => e.cardKey)).size;
    statsEl.innerHTML = `
      <ul class="profile-stats-list">
        <li><span>Total reviews</span><span>${totalReviews}</span></li>
        <li><span>Today</span><span>${todayReviews}</span></li>
        <li><span>Cards seen</span><span>${cardsSeen}</span></li>
      </ul>`;
  }

  renderFlags();
}

function renderProfileSwitcher() {
  const profiles = getProfiles();
  const list = document.getElementById('profile-switch-list');
  if (!list) return;
  const others = profiles.filter(p => p !== activeProfile);
  list.innerHTML = others.length
    ? others.map(p => `<button class="profile-button" data-profile="${esc(p)}">${esc(p)}</button>`).join('')
    : '<p class="muted" style="margin:0">No other profiles.</p>';
  list.querySelectorAll('.profile-button').forEach(btn => {
    btn.addEventListener('click', () => selectProfile(btn.dataset.profile));
  });
}

function renderFlags() {
  const flags = getFlags(activeProfile);
  const section = document.getElementById('flags-section');
  if (!section) return;
  if (!flags.length) {
    section.innerHTML = '<p class="muted">No flagged cards.</p>';
    return;
  }
  section.innerHTML = `
    <ul class="toggle-list">${flags.map(f => `
      <li class="toggle-row" style="flex-direction:column;align-items:flex-start;gap:0.2rem;">
        <strong>${esc(f.infinitive)} / ${esc(f.tenseLabel)} / ${esc(f.personLabel)}</strong>
        <span class="muted">Answer: ${esc(f.answer)}</span>
        ${f.note ? `<span class="muted">"${esc(f.note)}"</span>` : ''}
        <span class="muted" style="font-size:0.75rem">${esc(f.flaggedAt)}</span>
      </li>`).join('')}
    </ul>
    <button class="settings-save-button" id="copy-report-btn" style="margin-top:0.75rem;">Copy report</button>`;
  document.getElementById('copy-report-btn').addEventListener('click', copyFlagReport);
}

function copyFlagReport() {
  const flags = getFlags(activeProfile);
  const lines = [`Flagged conjugation report — ${activeProfile} — ${today()}`, '---'];
  flags.forEach(f => {
    lines.push(`Card: ${f.infinitive} / ${f.tenseLabel} / ${f.personLabel}`);
    lines.push(`Answer shown: ${f.answer}`);
    if (f.note) lines.push(`Note: ${f.note}`);
    lines.push('');
  });
  navigator.clipboard.writeText(lines.join('\n')).then(() => {
    toast('Report copied to clipboard');
  }).catch(() => {
    toast('Could not access clipboard');
  });
}

// --- helpers ---

function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// --- event wiring ---

document.addEventListener('DOMContentLoaded', () => {
  // Profile picker — main create button
  document.getElementById('create-profile-btn')?.addEventListener('click', () => {
    createProfile(document.getElementById('new-profile-input').value);
    document.getElementById('new-profile-input').value = '';
  });
  document.getElementById('new-profile-input')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      createProfile(e.target.value);
      e.target.value = '';
    }
  });

  // Bottom nav
  document.querySelector('[data-nav="practice"]')?.addEventListener('click', showPractice);
  document.querySelector('[data-nav="verbs"]')?.addEventListener('click', showVerbs);
  document.querySelector('[data-nav="settings"]')?.addEventListener('click', showSettings);

  // Verbs filter tabs
  document.querySelectorAll('.verb-filter-tab').forEach(tab => {
    tab.addEventListener('click', e => { e.preventDefault(); verbFilter = tab.dataset.filter; renderVerbList(); });
  });

  // Verbs bulk actions
  document.getElementById('enable-all-btn')?.addEventListener('click', () => setAllVerbs(true));
  document.getElementById('disable-all-btn')?.addEventListener('click', () => setAllVerbs(false));

  // Settings — rename
  document.getElementById('rename-profile-btn')?.addEventListener('click', () => {
    const newName = document.getElementById('rename-input')?.value?.trim();
    if (!newName || newName === activeProfile) return;
    if (getProfiles().includes(newName)) { toast('A profile with that name already exists.'); return; }
    renameProfile(activeProfile, newName);
    activeProfile = newName;
    settings = getSettings(activeProfile) ?? defaultSettings(verbs);
    renderSettings();
    toast(`Renamed to "${newName}"`);
  });

  // Settings — delete
  document.getElementById('delete-profile-btn')?.addEventListener('click', () => {
    if (!confirm(`Delete profile "${activeProfile}" and all its progress? This cannot be undone.`)) return;
    deleteProfile(activeProfile);
    activeProfile = null;
    showProfilePicker();
  });

  // Settings — create new profile from settings screen
  document.getElementById('create-profile-settings-btn')?.addEventListener('click', () => {
    createProfile(document.getElementById('new-profile-input-settings').value);
    document.getElementById('new-profile-input-settings').value = '';
  });
  document.getElementById('new-profile-input-settings')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      createProfile(e.target.value);
      e.target.value = '';
    }
  });

  init();
});
