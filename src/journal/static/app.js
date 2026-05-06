(() => {
  const data = JSON.parse(document.getElementById("data").textContent);

  const STATUS_LABEL = {
    done: "Complete",
    on_track: "On track",
    behind: "Behind",
    failed: "Error",
  };
  const STATUS_RANK = { failed: 0, behind: 1, on_track: 2, done: 3 };
  const TOTAL_DAYS = 7;

  const refreshedEl = document.getElementById("refreshed");
  const titleLabelEl = document.querySelector("#week-head .title-label");
  const titleChipEl = document.querySelector(".section-head-text .title-chip");
  const titleMetaEl = document.querySelector(".section-head-text .title-meta");
  const membersOl = document.querySelector("#weeks [data-members]");
  const prevBtn = document.querySelector(".nav-arrow.prev");
  const nextBtn = document.querySelector(".nav-arrow.next");

  function fmtRefreshed(iso) {
    const d = new Date(iso);
    return `Refreshed on ${d.toLocaleString("en-SG", {
      timeZone: "Asia/Singapore", year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
    })} SGT`;
  }

  function fmtRelative(iso, now) {
    if (!iso) return "—";
    const ms = new Date(iso).getTime();
    const diff = (now - ms) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 86400 * 2) {
      const timeStr = new Date(iso).toLocaleTimeString("en-SG", {
        timeZone: "Asia/Singapore", hour: "2-digit", minute: "2-digit", hour12: false,
      });
      return `yesterday · ${timeStr}`;
    }
    return `${Math.floor(diff / 86400)}d ago`;
  }

  function fmtRange(w) {
    const SG = { timeZone: "Asia/Singapore" };
    const start = new Date(w.start);
    const end = new Date(w.end);
    const startMonth = start.toLocaleDateString("en-SG", { ...SG, month: "short" });
    const endMonth = end.toLocaleDateString("en-SG", { ...SG, month: "short" });
    const startDay = start.toLocaleDateString("en-SG", { ...SG, day: "numeric" });
    const endDay = end.toLocaleDateString("en-SG", { ...SG, day: "numeric" });
    const startStr = `${startMonth} ${startDay}`;
    const endStr = startMonth === endMonth ? endDay : `${endMonth} ${endDay}`;
    return `${startStr} – ${endStr}`;
  }

  function fmtCountdown(endIso, now) {
    const ms = new Date(endIso).getTime() - now;
    if (ms <= 0) return "Ended";
    const m = Math.floor(ms / 60_000);
    const h = Math.floor(m / 60);
    const d = Math.floor(h / 24);
    if (d > 0) return `Ends in ${d}d ${h % 24}h`;
    if (h > 0) return `Ends in ${h}h ${m % 60}m`;
    return `Ends in ${m}m`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function pad2(n) { return String(n).padStart(2, "0"); }

  function track(count, total = TOTAL_DAYS) {
    const filled = Math.max(0, Math.min(count, total));
    let html = "";
    for (let i = 0; i < total; i++) {
      html += `<span class="dot${i < filled ? " filled" : ""}"></span>`;
    }
    return `<span class="track" aria-hidden="true">${html}</span>`;
  }

  function memberEntry(m, isCurrent, now, animate) {
    const li = document.createElement("li");
    li.className = animate ? "entry settle" : "entry";

    if (m.fetch_failed) {
      li.classList.add("status-failed");
      li.innerHTML =
        `<span class="num"></span>` +
        `<span class="name">${escapeHtml(m.name)}</span>` +
        `<span class="count"><span class="number">?/7</span></span>` +
        `<span class="status" data-tip="${escapeHtml(m.fetch_failed)}">${STATUS_LABEL.failed} †</span>` +
        `<span class="last">—</span>`;
      return { li, statusKey: "failed", count: -1, lastMs: Infinity, m };
    }

    const stats = isCurrent ? m.current : m.previous;
    const { count, status, last_submission, dropped_rows } = stats;
    const warnMsg = `${dropped_rows} entry fetch(es) failed; skipped`;
    const warn = dropped_rows > 0
      ? ` <span class="warn" data-tip="${escapeHtml(warnMsg)}">⚠</span>`
      : "";

    li.classList.add(`status-${status}`);
    li.innerHTML =
      `<span class="num"></span>` +
      `<span class="name">${escapeHtml(m.name)}</span>` +
      `<span class="count"><span class="number">${count}/7</span>${track(count)}</span>` +
      `<span class="status">${STATUS_LABEL[status]}${warn}</span>` +
      `<span class="last">${fmtRelative(last_submission, now)}</span>`;

    const lastMs = last_submission ? new Date(last_submission).getTime() : Infinity;
    return { li, statusKey: status, count, lastMs, m };
  }

  function sortEntries(rows) {
    return rows.sort((a, b) => {
      const c = b.count - a.count;
      if (c !== 0) return c;
      return a.lastMs - b.lastMs;
    });
  }

  function renderList(members, isCurrent, now, animate) {
    const rows = sortEntries(members.map((m) => memberEntry(m, isCurrent, now, animate)));
    const frag = document.createDocumentFragment();
    rows.forEach((r, i) => {
      r.li.style.setProperty("--i", i);
      r.li.querySelector(".num").textContent = pad2(i + 1);
      frag.appendChild(r.li);
    });
    membersOl.replaceChildren(frag);
  }

  let view = "current";
  let firstPaint = true;

  function update() {
    const isCurrent = view === "current";
    const win = isCurrent ? data.windows.current : data.windows.previous;
    const now = Date.now();

    titleLabelEl.textContent = isCurrent ? "This Week" : "Last Week";
    titleMetaEl.textContent = fmtRange(win);
    const showCountdown = isCurrent && win.day != null;
    titleChipEl.hidden = !showCountdown;
    titleChipEl.textContent = showCountdown ? fmtCountdown(win.end, now) : "";

    renderList(data.members, isCurrent, now, firstPaint);
    firstPaint = false;

    prevBtn.disabled = !isCurrent;
    nextBtn.disabled = isCurrent;
  }

  prevBtn.addEventListener("click", () => {
    if (view === "current") { view = "previous"; update(); }
  });
  nextBtn.addEventListener("click", () => {
    if (view === "previous") { view = "current"; update(); }
  });

  refreshedEl.textContent = fmtRefreshed(data.refreshed_at);
  update();
})();
