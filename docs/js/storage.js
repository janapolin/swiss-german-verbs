/** localStorage wrapper — all keys are namespaced under "swissverb:". */

const NS = 'swissverb';

// --- profiles ---

export function getProfiles() {
  return JSON.parse(localStorage.getItem(`${NS}:profiles`) ?? '[]');
}

export function saveProfiles(names) {
  localStorage.setItem(`${NS}:profiles`, JSON.stringify(names));
}

export function getActiveProfile() {
  return localStorage.getItem(`${NS}:active`) ?? null;
}

export function setActiveProfile(name) {
  localStorage.setItem(`${NS}:active`, name);
}

// --- per-profile settings ---

export function getSettings(profile) {
  const raw = localStorage.getItem(`${NS}:${profile}:settings`);
  return raw ? JSON.parse(raw) : null;
}

export function saveSettings(profile, settings) {
  localStorage.setItem(`${NS}:${profile}:settings`, JSON.stringify(settings));
}

// --- review state (one key per card) ---

export function loadState(profile, cardKey) {
  const raw = localStorage.getItem(`${NS}:${profile}:state:${cardKey}`);
  return raw ? JSON.parse(raw) : null;
}

export function saveState(profile, cardKey, state) {
  localStorage.setItem(`${NS}:${profile}:state:${cardKey}`, JSON.stringify(state));
}

// --- review log (append-only array, used for daily-goal counter) ---

export function appendLog(profile, entry) {
  const key = `${NS}:${profile}:log`;
  const log = JSON.parse(localStorage.getItem(key) ?? '[]');
  log.push(entry);
  localStorage.setItem(key, JSON.stringify(log));
}

export function getLog(profile) {
  return JSON.parse(localStorage.getItem(`${NS}:${profile}:log`) ?? '[]');
}

// --- flags (user-reported conjugation issues) ---

export function getFlags(profile) {
  return JSON.parse(localStorage.getItem(`${NS}:${profile}:flags`) ?? '[]');
}

export function addFlag(profile, flag) {
  const key = `${NS}:${profile}:flags`;
  const flags = JSON.parse(localStorage.getItem(key) ?? '[]');
  // replace existing flag for same card, or append
  const idx = flags.findIndex(f => f.cardKey === flag.cardKey);
  if (idx >= 0) flags[idx] = flag; else flags.push(flag);
  localStorage.setItem(key, JSON.stringify(flags));
}

// --- profile rename ---

export function renameProfile(oldName, newName) {
  // Collect all keys that belong to oldName
  const prefix = `${NS}:${oldName}:`;
  const newPrefix = `${NS}:${newName}:`;
  const pairs = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k && k.startsWith(prefix)) {
      pairs.push([k, newPrefix + k.slice(prefix.length), localStorage.getItem(k)]);
    }
  }
  pairs.forEach(([oldKey, newKey, val]) => {
    localStorage.setItem(newKey, val);
    localStorage.removeItem(oldKey);
  });

  const profiles = getProfiles().map(p => (p === oldName ? newName : p));
  saveProfiles(profiles);
  if (getActiveProfile() === oldName) setActiveProfile(newName);
}

// --- profile deletion ---

export function deleteProfile(name) {
  const prefix = `${NS}:${name}:`;
  const toRemove = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k && k.startsWith(prefix)) toRemove.push(k);
  }
  toRemove.forEach(k => localStorage.removeItem(k));

  saveProfiles(getProfiles().filter(p => p !== name));
  if (getActiveProfile() === name) localStorage.removeItem(`${NS}:active`);
}
