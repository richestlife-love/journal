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

  function fmtRefreshed(iso) {
    const d = new Date(iso);
    return `Refreshed ${d.toLocaleString("en-SG", {
      timeZone: "Asia/Singapore", year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
    })} SGT`;
  }

  function fmtRelative(iso, now) {
    if (!iso) return "—";
    const t = new Date(iso).getTime();
    const diff = (now - t) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 86400 * 2) {
      const t = new Date(iso).toLocaleTimeString("en-SG", {
        timeZone: "Asia/Singapore", hour: "2-digit", minute: "2-digit", hour12: false,
      });
      return `yesterday · ${t}`;
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

  function memberEntry(m, isCurrent, idx) {
    const li = document.createElement("li");
    li.className = "entry";
    li.style.setProperty("--i", idx);

    if (m.fetch_failed) {
      li.classList.add("status-failed");
      li.innerHTML =
        `<span class="num">${pad2(idx + 1)}</span>` +
        `<span class="name">${escapeHtml(m.name)}</span>` +
        `<span class="count"><span class="number">?/7</span></span>` +
        `<span class="status" data-tip="${escapeHtml(m.fetch_failed)}" title="${escapeHtml(m.fetch_failed)}">${STATUS_LABEL.failed} †</span>` +
        `<span class="last">—</span>`;
      return { li, statusKey: "failed", count: -1, name: m.name };
    }

    const stats = isCurrent ? m.current : m.previous;
    const { count, status, last_submission, dropped_rows } = stats;
    const warnMsg = `${dropped_rows} entry fetch(es) failed; skipped`;
    const warn = dropped_rows > 0
      ? ` <span class="warn" data-tip="${escapeHtml(warnMsg)}" title="${escapeHtml(warnMsg)}">⚠</span>`
      : "";

    li.classList.add(`status-${status}`);
    li.innerHTML =
      `<span class="num">${pad2(idx + 1)}</span>` +
      `<span class="name">${escapeHtml(m.name)}</span>` +
      `<span class="count"><span class="number">${count}/7</span>${track(count)}</span>` +
      `<span class="status">${STATUS_LABEL[status]}${warn}</span>` +
      `<span class="last">${fmtRelative(last_submission, Date.now())}</span>`;

    return { li, statusKey: status, count, name: m.name };
  }

  function sortEntries(rows) {
    return rows.sort((a, b) => {
      const r = STATUS_RANK[a.statusKey] - STATUS_RANK[b.statusKey];
      if (r !== 0) return r;
      if (a.statusKey !== "done") {
        const c = a.count - b.count;
        if (c !== 0) return c;
      }
      return a.name.localeCompare(b.name);
    });
  }

  function renderList(sectionId, members, isCurrent) {
    const ol = document.querySelector(`#${sectionId} [data-members]`);
    ol.innerHTML = "";
    const rows = members.map((m, i) => memberEntry(m, isCurrent, i));
    const sorted = sortEntries(rows);
    sorted.forEach((r, i) => {
      r.li.style.setProperty("--i", i);
      r.li.querySelector(".num").textContent = pad2(i + 1);
      ol.appendChild(r.li);
    });
  }

  function renderProgress(window, isCurrent) {
    const wrap = document.getElementById("progress");
    const pips = wrap.querySelector(".pips");
    const meta = wrap.querySelector(".progress-meta");

    pips.innerHTML = "";

    if (isCurrent) {
      const dayRaw = window.day;
      const day = dayRaw == null ? 0 : Math.max(0, Math.min(dayRaw, TOTAL_DAYS));
      for (let i = 1; i <= TOTAL_DAYS; i++) {
        const pip = document.createElement("span");
        pip.className = "pip";
        if (i < day) pip.classList.add("filled");
        else if (i === day) pip.classList.add("today");
        pips.appendChild(pip);
      }
      const dayPart = dayRaw == null ? "Window closed" : `Day ${dayRaw} of ${TOTAL_DAYS}`;
      meta.textContent = `${dayPart} · ${fmtCountdown(window.end, Date.now())}`;
    } else {
      for (let i = 1; i <= TOTAL_DAYS; i++) {
        const pip = document.createElement("span");
        pip.className = "pip filled";
        pips.appendChild(pip);
      }
      meta.textContent = "Week complete";
    }
  }

  let view = "current";

  function update() {
    const cur = data.windows.current;
    const prev = data.windows.previous;
    const isCurrent = view === "current";
    const w = isCurrent ? cur : prev;

    document.getElementById("week-head").textContent = isCurrent ? "This Week" : "Last Week";
    document.querySelector("#weeks .window-meta").textContent = fmtWindow(w);

    renderProgress(w, isCurrent);
    renderList("weeks", data.members, isCurrent);

    document.querySelector(".nav-arrow.prev").disabled = view === "previous";
    document.querySelector(".nav-arrow.next").disabled = view === "current";
  }

  document.querySelector(".nav-arrow.prev").addEventListener("click", () => {
    if (view === "current") { view = "previous"; update(); }
  });
  document.querySelector(".nav-arrow.next").addEventListener("click", () => {
    if (view === "previous") { view = "current"; update(); }
  });

  document.getElementById("refreshed").textContent = fmtRefreshed(data.refreshed_at);
  update();
})();
