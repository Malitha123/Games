let state = null;
let automationTimer = null;
let automationGeneration = 0;
let talkTimer = null;

const $ = id => document.getElementById(id);
const money = n => `$${Number(n || 0).toLocaleString()}`;
const titleCase = s => String(s || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());


function randomDelay() {
  return 2000 + Math.floor(Math.random() * 2001);
}

function pick(items) {
  return items[Math.floor(Math.random() * items.length)];
}

function speechForAction(name, action, amount = null) {
  const moneyAmount = amount == null ? null : money(amount);
  const lines = {
    check: ["I'll check.", "Check.", "Nothing from me, check."],
    call: ["I'll call.", "Call.", "Alright, I'm in."],
    fold: ["I'll fold.", "I'm out.", "Not this one, I fold."],
    bet: moneyAmount ? [`I'll bet ${moneyAmount}.`, `${moneyAmount}.`, `Let's put ${moneyAmount} in.`] : ["I'll bet."],
    raise: moneyAmount ? [`Raise to ${moneyAmount}.`, `Let's make it ${moneyAmount}.`, `I'll raise, ${moneyAmount}.`] : ["I'll raise."],
    all_in: ["All in.", "I'm all in.", "Everything goes in."],
  };
  return `${name}: “${pick(lines[action] || [titleCase(action) + '.'])}”`;
}

function showTableTalk(text) {
  const el = $("tableTalk");
  if (!el) return;
  el.textContent = text || "Table is quiet…";
  el.classList.toggle("quiet", !text);
  clearTimeout(talkTimer);
  if (text) talkTimer = setTimeout(() => {
    el.textContent = "Table is quiet…";
    el.classList.add("quiet");
  }, 4500);
}

function showToast(message, ok = false) {
  const el = $("toast");
  el.textContent = message;
  el.classList.remove("hidden", "ok");
  if (ok) el.classList.add("ok");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => el.classList.add("hidden"), 2800);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Request failed");
  return payload;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function cardHtml(card, hidden = false) {
  if (hidden || !card) return `<div class="card card-back"><span>♠</span></div>`;
  return `<div class="card ${card.color === "red" ? "red" : ""}"><span class="rank">${card.rank_text}</span><span class="suit">${card.suit}</span></div>`;
}

function playerPosition(index, count) {
  const angle = (-90 + (360 / count) * index) * Math.PI / 180;
  return { x: 50 + 43 * Math.cos(angle), y: 50 + 41 * Math.sin(angle) };
}

function renderPlayers() {
  const layer = $("playersLayer");
  layer.innerHTML = "";
  const count = state.players.length;

  state.players.forEach((p, i) => {
    const pos = playerPosition(i, count);
    const seat = document.createElement("div");
    seat.className = `player-seat ${p.is_current ? "current" : ""} ${p.folded ? "folded" : ""} ${p.stack === 0 ? "busted" : ""} ${p.is_bot ? "cpu-seat" : "human-seat"}`;
    seat.style.left = `${pos.x}%`;
    seat.style.top = `${pos.y}%`;

    const tags = [];
    if (!p.is_bot) tags.push(`<span class="tag human-tag">YOU</span>`);
    else tags.push(`<span class="tag cpu-tag">CPU</span>`);
    if (p.is_button) tags.push(`<span class="tag dealer">D</span>`);
    if (p.is_small_blind) tags.push(`<span class="tag">SB</span>`);
    if (p.is_big_blind) tags.push(`<span class="tag">BB</span>`);
    if (p.all_in) tags.push(`<span class="tag danger">ALL-IN</span>`);
    if (p.folded) tags.push(`<span class="tag muted">FOLD</span>`);

    let cards = "";
    if (p.in_hand && p.hole) {
      cards = `<div class="hole-cards">${p.hole.map(c => cardHtml(c)).join("")}</div>`;
    } else if (p.in_hand) {
      cards = `<div class="hole-cards">${cardHtml(null, true)}${cardHtml(null, true)}</div>`;
    }

    const profile = p.is_bot && p.bot_profile ? `<div class="bot-profile">${escapeHtml(p.bot_profile)} AI</div>` : "";
    seat.innerHTML = `
      <div class="seat-tags">${tags.join("")}</div>
      ${cards}
      <div class="seat-name">${escapeHtml(p.name)}</div>
      ${profile}
      <div class="seat-stack">${money(p.stack)}</div>
      ${p.bet_round ? `<div class="seat-bet">Bet ${money(p.bet_round)}</div>` : ""}
    `;
    layer.appendChild(seat);
  });
}

function renderCommunity() {
  const cards = [...state.community];
  $("community").innerHTML = cards.map(c => cardHtml(c)).join("") +
    Array.from({ length: 5 - cards.length }, () => `<div class="card placeholder"></div>`).join("");
}

function actionButton(label, action, cls = "") {
  return `<button class="action-btn ${cls}" type="button" data-action="${action}">${label}</button>`;
}

function renderActions() {
  const controls = $("actionControls");
  const summary = $("actionSummary");
  const newHand = $("newHand");
  const turnTitle = $("turnTitle");
  controls.innerHTML = "";
  summary.innerHTML = "";
  newHand.classList.add("hidden");

  if (state.game_over) {
    turnTitle.textContent = `${state.game_winner || "Winner"} wins the game`;
    summary.textContent = state.game_winner === state.players[state.human_index]?.name
      ? "You won the table."
      : "The table has one player with chips remaining.";
    return;
  }

  if (state.human_eliminated) {
    turnTitle.textContent = "You are out of chips";
    summary.textContent = "Start a new game to play again.";
    return;
  }

  if (state.can_start_hand) {
    if ($("autoNext").checked) {
      turnTitle.textContent = "Next hand dealing automatically…";
      summary.textContent = "You can turn off Auto deal if you want to pause between hands.";
    } else {
      turnTitle.textContent = "Hand complete";
      summary.textContent = "Review the result, then deal when ready.";
      newHand.classList.remove("hidden");
    }
    return;
  }

  const current = state.current_player_index == null ? null : state.players[state.current_player_index];
  if (!current) {
    turnTitle.textContent = "Resolving hand…";
    return;
  }

  if (current.is_bot) {
    turnTitle.textContent = `${current.name} is thinking…`;
    summary.textContent = `${current.bot_profile || "Computer"} AI is choosing an action automatically.`;
    controls.innerHTML = `<div class="thinking"><span></span><span></span><span></span></div>`;
    return;
  }

  turnTitle.textContent = "Your turn";
  const legal = state.legal || { actions: [] };
  const bits = [`Current bet: ${money(legal.current_bet || 0)}`];
  if ((legal.to_call || 0) > 0) bits.push(`To call: ${money(legal.to_call)}`);
  bits.push(`Your stack: ${money(current.stack)}`);
  summary.textContent = bits.join("  •  ");

  const actions = legal.actions || [];
  let html = "";
  if (actions.includes("fold")) html += actionButton("Fold", "fold", "danger-btn");
  if (actions.includes("check")) html += actionButton("Check", "check");
  if (actions.includes("call")) html += actionButton(`Call ${money(Math.min(legal.to_call, current.stack))}`, "call", "accent-btn");

  if (actions.includes("bet") || actions.includes("raise")) {
    const action = actions.includes("bet") ? "bet" : "raise";
    const min = Math.max(1, Number(legal.min_raise_to || 1));
    const max = Number(legal.max_raise_to || current.stack);
    html += `
      <div class="amount-control">
        <label>${action === "bet" ? "Bet to" : "Raise to"}</label>
        <input id="raiseAmount" type="number" min="${min}" max="${max}" step="1" value="${min}" />
        <button class="action-btn accent-btn" type="button" data-action="${action}">${titleCase(action)}</button>
      </div>
    `;
  }
  if (actions.includes("all_in")) html += actionButton(`All-in ${money(current.stack)}`, "all_in", "allin-btn");
  controls.innerHTML = html;

  controls.querySelectorAll("[data-action]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const action = btn.dataset.action;
      let amount = null;
      if (action === "bet" || action === "raise") amount = Number($("raiseAmount").value);
      const actorName = state.players[state.human_index]?.name || "You";
      let spokenAmount = amount;
      if (action === "call") spokenAmount = Math.min(Number(state.legal?.to_call || 0), Number(state.players[state.human_index]?.stack || 0));
      showTableTalk(speechForAction(actorName, action, spokenAmount));
      disableActionButtons();
      try {
        state = await api("/api/action", { method: "POST", body: JSON.stringify({ action, amount }) });
        render();
        scheduleAutomation();
      } catch (err) {
        showToast(err.message);
        renderActions();
      }
    });
  });
}

function disableActionButtons() {
  $("actionControls").querySelectorAll("button,input").forEach(el => el.disabled = true);
}

function renderLog() {
  const items = state.hand_log || [];
  $("handLog").innerHTML = items.length
    ? items.slice().reverse().map(line => `<div class="log-line">${escapeHtml(line)}</div>`).join("")
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
  $("handNo").textContent = `#${state.hand_number}`;
  $("street").textContent = titleCase(state.street);
  $("dealerDisplay").textContent = state.dealer_display;
  $("blinds").textContent = `${money(state.small_blind)} / ${money(state.big_blind)}`;
  $("pot").textContent = money(state.pot);

  renderPlayers();
  renderCommunity();
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

  if (state.game_over || state.human_eliminated) return;

  if (state.current_player_is_bot) {
    automationTimer = setTimeout(async () => {
      if (generation !== automationGeneration) return;
      try {
        state = await api("/api/bot-step", { method: "POST", body: "{}" });
        if (state.bot_action) {
          showTableTalk(speechForAction(state.bot_action.player, state.bot_action.action, state.bot_action.amount));
        }
        render();
        scheduleAutomation();
      } catch (err) {
        showToast(err.message);
      }
    }, randomDelay());
    return;
  }

  if (state.can_start_hand && $("autoNext").checked) {
    automationTimer = setTimeout(async () => {
      if (generation !== automationGeneration) return;
      try {
        state = await api("/api/new-hand", { method: "POST", body: "{}" });
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
  const payload = {
    player_count: Number($("playerCount").value),
    human_name: $("humanName").value.trim() || "You",
    starting_stack: Number($("startingStack").value),
    small_blind: Number($("smallBlind").value),
    big_blind: Number($("bigBlind").value),
    dealer_mode: document.querySelector('input[name="dealerMode"]:checked').value,
  };
  $("autoNext").checked = $("autoNextSetup").checked;
  try {
    state = await api("/api/setup", { method: "POST", body: JSON.stringify(payload) });
    render();
    scheduleAutomation();
  } catch (err) {
    showToast(err.message);
  }
}

async function dealHand() {
  cancelAutomation();
  try {
    state = await api("/api/new-hand", { method: "POST", body: "{}" });
    render();
    scheduleAutomation();
  } catch (err) {
    showToast(err.message);
  }
}

function resetToSetup() {
  if (state && state.hand_number > 0 && !confirm("Start a new game? Current chip stacks and hand history will be cleared.")) return;
  cancelAutomation();
  state = null;
  render();
}

$("setupForm").addEventListener("submit", createGame);
$("newHand").addEventListener("click", dealHand);
$("newGameTop").addEventListener("click", resetToSetup);
$("autoNext").addEventListener("change", () => {
  renderActions();
  scheduleAutomation();
});

api("/api/state")
  .then(payload => {
    state = payload;
    render();
    scheduleAutomation();
  })
  .catch(err => showToast(err.message));
