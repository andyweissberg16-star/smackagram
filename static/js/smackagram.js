// Shared helpers. Loaded from _nav.html, so it is available on every page.
(function () {
  // Marks the specific field that caused a validation error, rather than only
  // showing a message somewhere else on the page. Does three things:
  //   - aria-invalid, so a screen reader says "invalid entry" on the field
  //   - a red border via CSS, so a sighted user can see WHICH field
  //   - moves focus there, so the fix is one keystroke away
  // The mark clears itself as soon as the person starts typing.
  window.smkInvalid = function (el) {
    if (!el) return;
    el.setAttribute('aria-invalid', 'true');
    try { el.focus({ preventScroll: false }); } catch (e) { el.focus(); }
    var clear = function () {
      el.removeAttribute('aria-invalid');
      el.removeEventListener('input', clear);
      el.removeEventListener('change', clear);
    };
    el.addEventListener('input', clear);
    el.addEventListener('change', clear);
  };

  // Convenience: mark the first of several fields that is empty.
  window.smkInvalidFirstEmpty = function () {
    for (var i = 0; i < arguments.length; i++) {
      var el = document.getElementById(arguments[i]);
      if (el && !String(el.value || '').trim()) { window.smkInvalid(el); return; }
    }
    var first = document.getElementById(arguments[0]);
    if (first) window.smkInvalid(first);
  };
})();

// ---------------------------------------------------------------------------
// Site-wide team autocomplete.
// Smack Chat had this and nothing else did. Any <input data-team-search>
// gets a filtered dropdown of real teams with the league abbreviation, so
// people stop guessing at spellings and we get clean team names back.
//
// Selecting fills the input and fires input+change, so whatever the page
// already does on those events (Locked & Loaded runs its game search) still
// happens. Nothing is auto-submitted.
// ---------------------------------------------------------------------------
(function () {
  var cache = null, inflight = null;

  function loadTeams() {
    if (cache) return Promise.resolve(cache);
    if (inflight) return inflight;
    // The ?v= tag is a cache-buster. A browser that already stored this
    // list keeps it for as long as the original max-age promised, no
    // matter what header we send afterwards. Changing the URL is the
    // only thing that reliably gets people onto new data. Bump this
    // number whenever the team list changes.
    inflight = fetch('/api/teams/all?v=2')
      .then(function (r) { return r.json(); })
      .then(function (d) { cache = (d && d.teams) || []; return cache; })
      .catch(function () { cache = []; return cache; });
    return inflight;
  }

  function score(team, q) {
    var name = team.name.toLowerCase();
    var short = (team.short || '').toLowerCase();
    var code = (team.code || '').toLowerCase();
    var aliases = team.aliases || [];
    if (name === q || short === q || code === q) return 0;
    if (name.indexOf(q) === 0) return 1;
    if (short.indexOf(q) === 0 || code.indexOf(q) === 0) return 2;
    // any word in the full name starting with the query - this is what makes
    // typing "new" surface the New York Yankees rather than nothing at all
    var words = name.split(/\s+/);
    for (var i = 0; i < words.length; i++) {
      if (words[i].indexOf(q) === 0) return 3;
    }
    for (var a = 0; a < aliases.length; a++) {
      if (aliases[a].indexOf(q) === 0) return 4;
    }
    if (name.indexOf(q) > -1) return 5;
    for (var b = 0; b < aliases.length; b++) {
      if (aliases[b].indexOf(q) > -1) return 6;   // "crimson" -> Alabama
    }
    return -1;
  }

  function attach(input) {
    if (input.dataset.smkBound) return;
    input.dataset.smkBound = '1';
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-autocomplete', 'list');

    var wrap = document.createElement('div');
    wrap.className = 'smk-ac-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var list = document.createElement('div');
    list.className = 'smk-ac-list';
    list.setAttribute('role', 'listbox');
    list.hidden = true;
    wrap.appendChild(list);

    var items = [], active = -1, suppress = false;

    function close() {
      list.hidden = true; list.innerHTML = ''; items = []; active = -1;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
    }

    function choose(t) {
      input.value = t.name;
      close();
      // Dispatching 'input' is what lets the page react (Locked & Loaded runs
      // its game search off it) - but our own listener hears it too and would
      // immediately reopen the dropdown on the name we just picked. Both
      // dispatches are synchronous, so a flag around them is enough.
      suppress = true;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      suppress = false;
      input.focus();
    }

    function highlight(i) {
      for (var n = 0; n < items.length; n++) {
        items[n].el.classList.toggle('is-active', n === i);
      }
      active = i;
      if (i > -1) {
        input.setAttribute('aria-activedescendant', items[i].el.id);
        items[i].el.scrollIntoView({ block: 'nearest' });
      }
    }

    function render(matches, total) {
      list.innerHTML = ''; items = []; active = -1;
      if (!matches.length) { close(); return; }
      matches.forEach(function (t, i) {
        var row = document.createElement('div');
        row.className = 'smk-ac-item';
        row.id = 'smk-ac-' + (input.id || 'x') + '-' + i;
        row.setAttribute('role', 'option');
        var nm = document.createElement('span');
        nm.className = 'smk-ac-name'; nm.textContent = t.name;
        var lg = document.createElement('span');
        lg.className = 'smk-ac-league'; lg.textContent = t.league_label || t.league;
        row.appendChild(nm); row.appendChild(lg);
        row.addEventListener('mousedown', function (e) { e.preventDefault(); choose(t); });
        row.addEventListener('mouseenter', function () { highlight(i); });
        list.appendChild(row);
        items.push({ el: row, team: t });
      });
      if (total && total > matches.length) {
        var more = document.createElement('div');
        more.className = 'smk-ac-more';
        more.textContent = '+' + (total - matches.length) + ' more - keep typing to narrow it down';
        list.appendChild(more);
      }
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
    }

    function search() {
      if (suppress) return;
      var q = input.value.trim().toLowerCase();
      if (q.length < 2) { close(); return; }
      loadTeams().then(function (teams) {
        if (input.value.trim().toLowerCase() !== q) return;
        var scored = [];
        for (var i = 0; i < teams.length; i++) {
          var s = score(teams[i], q);
          if (s > -1) scored.push({ t: teams[i], s: s });
        }
        scored.sort(function (a, b) { return a.s - b.s || a.t.name.localeCompare(b.t.name); });
        render(scored.slice(0, 20).map(function (x) { return x.t; }), scored.length);
      });
    }

    input.addEventListener('focus', loadTeams);
    input.addEventListener('input', search);
    input.addEventListener('blur', function () { setTimeout(close, 120); });
    input.addEventListener('keydown', function (e) {
      if (list.hidden || !items.length) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); highlight((active + 1) % items.length); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); highlight((active - 1 + items.length) % items.length); }
      else if (e.key === 'Enter' && active > -1) { e.preventDefault(); choose(items[active].team); }
      else if (e.key === 'Escape') { close(); }
    });
  }

  function init() {
    var els = document.querySelectorAll('input[data-team-search]');
    for (var i = 0; i < els.length; i++) attach(els[i]);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
