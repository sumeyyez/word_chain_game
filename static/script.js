const TIME_LIMIT = 12; // saniye

const chainDisplay = document.getElementById("chainDisplay");
const playerScoreEl = document.getElementById("playerScore");
const aiScoreEl = document.getElementById("aiScore");
const turnsEl = document.getElementById("turns");
const mistakesEl = document.getElementById("mistakes");
const requiredLetterEl = document.getElementById("requiredLetter");
const wordInput = document.getElementById("wordInput");
const submitBtn = document.getElementById("submitBtn");
const newGameBtn = document.getElementById("newGameBtn");
const messageBox = document.getElementById("messageBox");
const timerBar = document.getElementById("timerBar");
const timerText = document.getElementById("timerText");
const gameOverOverlay = document.getElementById("gameOverOverlay");
const finalScores = document.getElementById("finalScores");
const winnerText = document.getElementById("winnerText");
const playAgainBtn = document.getElementById("playAgainBtn");
const startOverlay = document.getElementById("startOverlay");
const startEnBtn = document.getElementById("startEnBtn");
const startTrBtn = document.getElementById("startTrBtn");

let currentLanguage = "en";

let timerInterval = null;
let timeLeft = TIME_LIMIT;
let requestInFlight = false;

function renderChain(chain) {
  chainDisplay.innerHTML = "";
  if (!chain || chain.length === 0) {
    chainDisplay.innerHTML = '<span class="placeholder">Ilk kelimeyi girerek zinciri baslat</span>';
    return;
  }
  const recent = chain.slice(-12);
  recent.forEach((word, idx) => {
    if (idx > 0) {
      const arrow = document.createElement("span");
      arrow.className = "chain-arrow";
      arrow.textContent = "→";
      chainDisplay.appendChild(arrow);
    }
    const span = document.createElement("span");
    // Oyuncu kelimeleri cift indeksli (0,2,4...), AI kelimeleri tek indeksli
    const globalIdx = chain.length - recent.length + idx;
    span.className = "chain-word " + (globalIdx % 2 === 0 ? "player" : "ai");
    span.textContent = word.toUpperCase();
    chainDisplay.appendChild(span);
  });
}

function renderState(state) {
  playerScoreEl.textContent = state.player_score;
  aiScoreEl.textContent = state.ai_score;
  turnsEl.textContent = state.turns;
  mistakesEl.textContent = state.mistakes;
  renderChain(state.chain);

  const required = state.chain.length > 0 ? state.chain[state.chain.length - 1].slice(-1).toUpperCase() : null;
  requiredLetterEl.textContent = required || "?";

  if (state.game_over) {
    showGameOver(state);
    stopTimer();
    setInputEnabled(false);
  }
}

function showMessage(text, type) {
  messageBox.textContent = text || "";
  messageBox.className = "message" + (type ? " " + type : "");
}

function setInputEnabled(enabled) {
  wordInput.disabled = !enabled;
  submitBtn.disabled = !enabled;
  if (enabled) wordInput.focus();
}

function showGameOver(state) {
  finalScores.textContent = `Sen: ${state.player_score}  |  AI: ${state.ai_score}`;
  let winner = "Berabere";
  if (state.player_score > state.ai_score) winner = "Sen kazandin!";
  else if (state.ai_score > state.player_score) winner = "AI kazandi!";
  winnerText.textContent = winner;
  gameOverOverlay.classList.remove("hidden");
}

function hideGameOver() {
  gameOverOverlay.classList.add("hidden");
}

function startTimer() {
  stopTimer();
  timeLeft = TIME_LIMIT;
  updateTimerUI();
  timerInterval = setInterval(() => {
    timeLeft -= 0.1;
    if (timeLeft <= 0) {
      timeLeft = 0;
      updateTimerUI();
      stopTimer();
      handleTimeout();
      return;
    }
    updateTimerUI();
  }, 100);
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

function updateTimerUI() {
  const pct = Math.max(0, (timeLeft / TIME_LIMIT) * 100);
  timerBar.style.width = pct + "%";
  timerText.textContent = Math.ceil(timeLeft);
  if (pct < 25) {
    timerBar.style.background = "linear-gradient(90deg, #ff5d6c, #ff9b6c)";
  } else if (pct < 55) {
    timerBar.style.background = "linear-gradient(90deg, #ffcd5c, #ffe08a)";
  } else {
    timerBar.style.background = "linear-gradient(90deg, #3ddc97, #ffcd5c)";
  }
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

async function handleTimeout() {
  if (requestInFlight) return;
  requestInFlight = true;
  setInputEnabled(false);
  showMessage("Sure doldu, kontrol ediliyor...", "warn");
  try {
    const state = await postJSON("/api/submit_word", { timed_out: true });
    showMessage(state.message, state.message_type);
    renderState(state);
  } catch (e) {
    showMessage("Baglanti hatasi, tekrar dene.", "error");
  } finally {
    requestInFlight = false;
    if (!gameOverOverlay.classList.contains("hidden")) return;
    setInputEnabled(true);
    startTimer();
  }
}

async function handleSubmit() {
  if (requestInFlight) return;
  const word = wordInput.value.trim();
  if (!word) return;

  requestInFlight = true;
  stopTimer();
  setInputEnabled(false);
  showMessage("Kontrol ediliyor...", "");

  try {
    const state = await postJSON("/api/submit_word", { word });
    showMessage(state.message, state.message_type);
    renderState(state);
    wordInput.value = "";
  } catch (e) {
    showMessage("Baglanti hatasi, tekrar dene.", "error");
  } finally {
    requestInFlight = false;
    if (!gameOverOverlay.classList.contains("hidden")) return;
    setInputEnabled(true);
    startTimer();
  }
}

async function startNewGame(language) {
  if (language) currentLanguage = language;
  stopTimer();
  hideGameOver();
  showMessage("", "");
  wordInput.value = "";
  const state = await postJSON("/api/new_game", { language: currentLanguage });
  renderState(state);
  setInputEnabled(true);
  startTimer();
}

submitBtn.addEventListener("click", handleSubmit);
wordInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") handleSubmit();
});
newGameBtn.addEventListener("click", () => startNewGame());
playAgainBtn.addEventListener("click", () => startNewGame());

startEnBtn.addEventListener("click", () => {
  startOverlay.classList.add("hidden");
  startNewGame("en");
});
startTrBtn.addEventListener("click", () => {
  startOverlay.classList.add("hidden");
  startNewGame("tr");
});