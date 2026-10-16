let state = null;
let automationTimer = null;
let automationGeneration = 0;
let talkTimer = null;

const $ = id => document.getElementById(id);
const money = n => {
  const value = Number(n || 0);
  return value.toLocaleString(undefined, { style: "currency", currency: "USD", minimumFractionDigits: Number.isInteger(value) ? 0 : 2, maximumFractionDigits: 2 });
};
const titleCase = s => String(s || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
const randomDelay = () => 2000 + Math.floor(Math.random() * 2001);
const pick = items => items[Math.floor(Math.random() * items.length)];

function escapeHtml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function showToast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => el.classList.add("hidden"), 3000);
}

function showTalk(text) {
  const el = $("tableTalk");
  el.textContent = text || "Table is quiet…";
  el.classList.toggle("quiet", !text);
  clearTimeout(talkTimer);
  if (text) talkTimer = setTimeout(() => {
    el.textContent = "Table is quiet…";
    el.classList.add("quiet");
  }, 4800);
}

function humanSpeech(action) {
  const name = state?.players?.[state.human_index]?.name || "You";
  const lines = {
    hit: ["Hit me.", "One more card.", "I'll hit."],
    stand: ["I'll stand.", "That's enough, stand.", "I stay."],
    double: ["Double down.", "I'll double.", "Double it."],
    split: ["I'll split them.", "Split.", "Let's make two hands."],
  };
  return `${name}: “${pick(lines[action] || [titleCase(action) + "."])}”`;
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Request failed");
  return payload;
}

function cardHtml(card) {
  if (!card) return `<div class="card card-back"><span>♠</span></div>`;
  return `<div class="card ${card.color === "red" ? "red" : ""}"><span>${escapeHtml(card.rank_text)}</span><span class="suit">${escapeHtml(card.suit)}</span></div>`;
}

function renderDealer() {
  const d = state.dealer || { cards: [], total: 0, revealed: false };
  $("dealerCards").innerHTML = d.cards.map(cardHtml).join("");
  $("dealerTotal").textContent = d.revealed ? `Total ${d.total}` : `Showing ${d.total}`;
}

function renderPlayers() {
  const grid = $("playersGrid");
  grid.innerHTML = "";
  state.players.forEach(p => {
    const seat = document.createElement("div");
    seat.className = `player-seat ${p.is_current ? "current" : ""} ${!p.is_bot ? "human" : ""} ${p.broke ? "broke" : ""}`;
    const tags = p.is_bot ? `<span class="tag">CPU</span>` : `<span class="tag you">YOU</span>`;
    const profile = p.is_bot ? `<div class="profile">${escapeHtml(p.bot_profile || "Basic")} AI</div>` : `<div class="profile">Manual player</div>`;
    let hands = p.hands.map((h, idx) => `
      <div class="hand ${h.is_current ? "current-hand" : ""}">
        ${p.hands.length > 1 ? `<div class="profile">Hand ${idx + 1}</div>` : ""}
        <div class="cards">${h.cards.map(cardHtml).join("")}</div>
        <div class="hand-meta"><span>${h.total}${h.soft ? " soft" : ""}</span><span>Bet ${money(h.bet)}</span><span>${titleCase(h.status)}</span></div>
        ${h.outcome ? `<div class="outcome">${escapeHtml(h.outcome)}</div>` : ""}
      </div>`).join("");
    if (!hands) hands = `<div class="profile">Sitting out</div>`;
    seat.innerHTML = `
      <div class="seat-head"><span class="seat-name">${escapeHtml(p.name)}</span>${tags}</div>
      ${profile}
      <div class="bankroll">Bankroll ${money(p.stack)}</div>
      <div class="hands">${hands}</div>`;
    grid.appendChild(seat);
  });
}

function actionButton(label, action, cls = "") {
  return `<button type="button" class="action-btn ${cls}" data-action="${action}">${label}</button>`;
}

function renderActions() {
  const controls = $("actionControls");
  const title = $("turnTitle");
  const summary = $("actionSummary");
  const nextBox = $("nextRoundBox");
  controls.innerHTML = "";
  nextBox.classList.add("hidden");

  if (state.human_broke) {
    title.textContent = "You are out of bankroll";
    summary.textContent = "Start a new game to play again.";
    return;
  }

  if (state.phase === "complete") {
    title.textContent = "Round complete";
    const human = state.players[state.human_index];
    summary.textContent = `Your bankroll: ${money(human.stack)}. ${$("autoNext").checked ? "The next round will deal automatically." : "Choose your next wager when ready."}`;
    const maxBet = Math.max(1, Number(human.stack || 1));
    $("nextBet").max = String(maxBet);
    if (Number($("nextBet").value) > maxBet) $("nextBet").value = String(maxBet);
    if (!$("autoNext").checked) nextBox.classList.remove("hidden");
    return;
  }

  if (state.phase === "dealer_turn") {
    title.textContent = "Dealer's turn";
    summary.textContent = "The dealer is playing automatically and stands on soft 17.";
    controls.innerHTML = `<div class="thinking"><span></span><span></span><span></span></div>`;
    return;
  }

  const current = state.current_player_index == null ? null : state.players[state.current_player_index];
  if (!current) {
    title.textContent = "Resolving round…";
    return;
  }
  if (current.is_bot) {
    title.textContent = `${current.name} is deciding…`;
    summary.textContent = `${current.bot_profile || "Basic"} AI is playing automatically.`;
    controls.innerHTML = `<div class="thinking"><span></span><span></span><span></span></div>`;
    return;
  }

  title.textContent = "Your turn";
  const legal = state.legal || { actions: [] };
  summary.textContent = `Hand total ${legal.hand_total}${legal.soft ? " (soft)" : ""} · Bet ${money(legal.bet)} · Bankroll ${money(legal.stack)}`;
  let html = "";
  if (legal.actions.includes("hit")) html += actionButton("Hit", "hit", "primary-action");
  if (legal.actions.includes("stand")) html += actionButton("Stand", "stand");
  if (legal.actions.includes("double")) html += actionButton("Double", "double");
  if (legal.actions.includes("split")) html += actionButton("Split", "split");
  controls.innerHTML = html;
  controls.querySelectorAll("[data-action]").forEach(button => {
    button.addEventListener("click", async () => {
      const action = button.dataset.action;
      showTalk(humanSpeech(action));
      controls.querySelectorAll("button").forEach(b => b.disabled = true);
      try {
        state = await api("/api/action", { method: "POST", body: JSON.stringify({ action }) });
        render();
        scheduleAutomation();
      } catch (err) {
        showToast(err.message);
        renderActions();
      }
    });
  });
}

function renderLog() {
  const lines = state.hand_log || [];
  $("handLog").innerHTML = lines.length
    ? lines.slice().reverse().map(x => `<div class="log-line">${escapeHtml(x)}</div>`).join("")
    : `<div class="log-empty">No actions yet.</div>`;
}

function renderResult() {
  const box = $("resultBox");
  const results = state.last_result || [];
  if (!results.length) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.innerHTML = results.map(x => `<div>${escapeHtml(x)}</div>`).join("");
  box.classList.remove("hidden");
}

function render() {
  if (!state || !state.configured) {
    $("setupView").classList.remove("hidden");
    $("gameView").classList.add("hidden");
    $("newGameTop").classList.add("hidden");
    return;
  }
  $("setupView").classList.add("hidden");
  $("gameView").classList.remove("hidden");
  $("newGameTop").classList.remove("hidden");
  $("roundNo").textContent = `#${state.round_number}`;
  $("phase").textContent = titleCase(state.phase);
  $("minBet").textContent = money(state.minimum_bet);
  $("shoe").textContent = `${state.shoe_remaining} cards`;
  renderDealer();
  renderPlayers();
  renderActions();
  renderLog();
  renderResult();
}

function cancelAutomation() {
  automationGeneration += 1;
  if (automationTimer) clearTimeout(automationTimer);
  automationTimer = null;
}

function scheduleAutomation() {
  if (!state || !state.configured) return;
  if (automationTimer) clearTimeout(automationTimer);
  automationTimer = null;
  const generation = automationGeneration;
  if (state.human_broke) return;

  const autoActor = state.current_player_is_bot || state.phase === "dealer_turn";
  if (autoActor) {
    automationTimer = setTimeout(async () => {
      if (generation !== automationGeneration) return;
      try {
        state = await api("/api/auto-step", { method: "POST", body: "{}" });
        if (state.auto_action?.speech) showTalk(state.auto_action.speech);
        render();
        scheduleAutomation();
      } catch (err) {
        showToast(err.message);
      }
    }, randomDelay());
    return;
  }

  if (state.phase === "complete" && $("autoNext").checked) {
    automationTimer = setTimeout(async () => {
      if (generation !== automationGeneration) return;
      const human = state.players[state.human_index];
      let bet = Number($("nextBet").value || state.last_human_bet || state.minimum_bet);
      bet = Math.min(bet, Number(human.stack));
      if (bet <= 0) return;
      try {
        state = await api("/api/new-round", { method: "POST", body: JSON.stringify({ bet }) });
        render();
        scheduleAutomation();
      } catch (err) {
        showToast(err.message);
      }
    }, randomDelay());
  }
}

async function createGame(event) {
  event.preventDefault();
  cancelAutomation();
  const minimumBet = Number($("minimumBet").value);
  const defaultBet = Number($("defaultBet").value);
  if (defaultBet < minimumBet) {
    showToast("Default bet must be at least the table minimum.");
    return;
  }
  const payload = {
    player_count: Number($("playerCount").value),
    human_name: $("humanName").value.trim() || "You",
    starting_stack: Number($("startingStack").value),
    minimum_bet: minimumBet,
    default_bet: defaultBet,
  };
  $("autoNext").checked = $("autoNextSetup").checked;
  $("nextBet").value = String(defaultBet);
  try {
    state = await api("/api/setup", { method: "POST", body: JSON.stringify(payload) });
    render();
    scheduleAutomation();
  } catch (err) {
    showToast(err.message);
  }
}

async function dealRound() {
  cancelAutomation();
  const bet = Number($("nextBet").value);
  try {
    state = await api("/api/new-round", { method: "POST", body: JSON.stringify({ bet }) });
    render();
    scheduleAutomation();
  } catch (err) {
    showToast(err.message);
  }
}

function resetToSetup() {
  if (state && state.round_number > 0 && !confirm("Start a new blackjack game? Current bankrolls will be cleared.")) return;
  cancelAutomation();
  state = null;
  showTalk("");
  render();
}

$("setupForm").addEventListener("submit", createGame);
$("newRound").addEventListener("click", dealRound);
$("newGameTop").addEventListener("click", resetToSetup);
$("autoNext").addEventListener("change", () => { renderActions(); scheduleAutomation(); });

api("/api/state").then(payload => {
  state = payload;
  if (state?.configured) $("nextBet").value = String(state.last_human_bet || state.minimum_bet || 10);
  render();
  scheduleAutomation();
}).catch(err => showToast(err.message));
