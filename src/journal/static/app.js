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
  const weekHeadEl = document.getElementById("week-head");
  const windowMetaEl = document.querySelector("#weeks .window-meta");
  const progressEl = document.getElementById("progress");
  const pipsEl = progressEl.querySelector(".pips");
  const progressMetaEl = progressEl.querySelector(".progress-meta");
  const membersOl = document.querySelector("#weeks [data-members]");
  const prevBtn = document.querySelector(".nav-arrow.prev");
  const nextBtn = document.querySelector(".nav-arrow.next");

  function fmtRefreshed(iso) {
    const d = new Date(iso);
    return `Refreshed ${d.toLocaleString("en-SG", {
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

  function fmtWindow(w) {
    const startStr = new Date(w.start).toLocaleDateString("en-SG", {
      timeZone: "Asia/Singapore", month: "short", day: "numeric",
    });
    const endStr = new Date(w.end).toLocaleDateString("en-SG", {
      timeZone: "Asia/Singapore", year: "numeric", month: "short", day: "numeric",
    });
    return `${startStr} – ${endStr}`;
  }

  function fmtCountdown(endIso, now) {
    const ms = new Date(endIso).getTime() - now;
    if (ms <= 0) return "deadline passed";
    const h = Math.floor(ms / 3_600_000);
    const d = Math.floor(h / 24);
    return d > 0 ? `${d}d ${h % 24}h to deadline` : `${h}h to deadline`;
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
      return { li, statusKey: "failed", count: -1, m };
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

    return { li, statusKey: status, count, m };
  }

  function sortEntries(rows) {
    return rows.sort((a, b) => {
      const r = STATUS_RANK[a.statusKey] - STATUS_RANK[b.statusKey];
      if (r !== 0) return r;
      if (a.statusKey !== "done") {
        const c = a.count - b.count;
        if (c !== 0) return c;
      }
      return a.m.name.localeCompare(b.m.name);
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

  function renderProgress(win, isCurrent, now) {
    pipsEl.innerHTML = "";
    const dayRaw = isCurrent ? win.day : null;
    // Sentinel TOTAL_DAYS + 1 makes every pip "filled" for the previous-week view.
    const day = isCurrent
      ? (dayRaw == null ? 0 : Math.max(0, Math.min(dayRaw, TOTAL_DAYS)))
      : TOTAL_DAYS + 1;
    for (let i = 1; i <= TOTAL_DAYS; i++) {
      const pip = document.createElement("span");
      pip.className = "pip";
      if (i < day) pip.classList.add("filled");
      else if (i === day) pip.classList.add("today");
      pipsEl.appendChild(pip);
    }
    if (!isCurrent) {
      progressMetaEl.textContent = "Week complete";
    } else {
      const dayPart = dayRaw == null ? "Window closed" : `Day ${dayRaw} of ${TOTAL_DAYS}`;
      progressMetaEl.textContent = `${dayPart} · ${fmtCountdown(win.end, now)}`;
    }
  }

  let view = "current";
  let firstPaint = true;

  function update() {
    const isCurrent = view === "current";
    const win = isCurrent ? data.windows.current : data.windows.previous;
    const now = Date.now();

    weekHeadEl.textContent = isCurrent ? "This Week" : "Last Week";
    windowMetaEl.textContent = fmtWindow(win);

    renderProgress(win, isCurrent, now);
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
