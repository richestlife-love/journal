(() => {
  const data = JSON.parse(document.getElementById("data").textContent);
  const STATUS_LABEL = {
    done: "✓ Done",
    on_track: "→ On track",
    behind: "✗ Behind",
    failed: "⚠ Fetch failed",
  };
  const STATUS_RANK = { failed: 0, behind: 1, on_track: 2, done: 3 };

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
    if (diff < 3600) return `${Math.floor(diff / 60)} minutes ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`;
    if (diff < 86400 * 2) return "yesterday";
    return `${Math.floor(diff / 86400)} days ago`;
  }

  function fmtWindow(w) {
    const f = (iso) => new Date(iso).toLocaleString("en-SG", {
      timeZone: "Asia/Singapore", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
    });
    return `${f(w.start)} → ${f(w.end)} SGT`;
  }

  function fmtCountdown(endIso, now) {
    const ms = new Date(endIso).getTime() - now;
    if (ms <= 0) return "deadline passed";
    const h = Math.floor(ms / 3_600_000);
    const d = Math.floor(h / 24);
    return d > 0 ? `Deadline in ${d}d ${h % 24}h` : `Deadline in ${h}h`;
  }

  function memberRow(m, mode, isCurrent) {
    const tr = document.createElement("tr");
    if (m.fetch_failed) {
      tr.innerHTML = `<td>${m.name}</td><td class="count">?/7</td>` +
        `<td class="status-failed" title="${escapeHtml(m.fetch_failed)}">${STATUS_LABEL.failed}</td><td>—</td>`;
      return { tr, statusKey: "failed", count: -1 };
    }
    const w = isCurrent ? m.current : m.previous;
    const stats = w[mode];
    const count = stats.count;
    const status = stats.status;
    const warn = stats.dropped_rows > 0
      ? `<span class="warn" title="${stats.dropped_rows} entry fetch(es) failed; count is a lower bound">⚠</span>`
      : "";
    tr.innerHTML = `<td>${m.name}</td><td class="count">${count}/7${warn}</td>` +
      `<td class="status-${status}">${STATUS_LABEL[status]}</td>` +
      `<td>${fmtRelative(stats.last_submission, Date.now())}</td>`;
    return { tr, statusKey: status, count };
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function sortMembers(rows) {
    return rows.sort((a, b) => {
      const r = STATUS_RANK[a.statusKey] - STATUS_RANK[b.statusKey];
      if (r !== 0) return r;
      if (a.statusKey !== "done") {
        const c = a.count - b.count;
        if (c !== 0) return c;
      }
      return a.tr.firstChild.textContent.localeCompare(b.tr.firstChild.textContent);
    });
  }

  function renderTable(sectionId, members, mode, isCurrent) {
    const tbody = document.querySelector(`#${sectionId} tbody`);
    tbody.innerHTML = "";
    const rows = members.map((m) => memberRow(m, mode, isCurrent));
    sortMembers(rows).forEach((r) => tbody.appendChild(r.tr));
  }

  function render() {
    const mode = document.body.dataset.mode === "raw" ? "raw" : "dedup";
    document.getElementById("toggle-on").classList.toggle("active", mode === "dedup");
    document.getElementById("toggle-off").classList.toggle("active", mode === "raw");

    document.getElementById("refreshed").textContent = fmtRefreshed(data.refreshed_at);

    const cur = data.windows.current;
    const prev = data.windows.previous;
    document.querySelector("#current .window-meta").textContent =
      `${fmtWindow(cur)} • Day ${cur.day} of 7 (threshold ${cur.threshold}) • ${fmtCountdown(cur.end, Date.now())}`;
    document.querySelector("#previous .window-meta").textContent = fmtWindow(prev);

    renderTable("current", data.members, mode, true);
    renderTable("previous", data.members, mode, false);
  }

  document.getElementById("toggle-on").addEventListener("click", (e) => {
    e.preventDefault();
    document.body.dataset.mode = "dedup";
    render();
  });
  document.getElementById("toggle-off").addEventListener("click", (e) => {
    e.preventDefault();
    document.body.dataset.mode = "raw";
    render();
  });

  render();
})();
