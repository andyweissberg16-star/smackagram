/*
 * Sharing, for every surface that has something worth sharing.
 *
 * TWO PATHS, chosen by what the device can actually do:
 *
 *   1. NATIVE SHEET (navigator.share). On a phone this is the whole game -
 *      one tap opens Instagram, TikTok, WhatsApp, Messages, whatever they
 *      have installed, and it can carry the actual audio FILE rather than a
 *      link. No API integrations, no app review, no per-platform work.
 *
 *   2. PLATFORM BUTTONS. Desktop browsers mostly lack navigator.share, so
 *      they get explicit links per platform plus copy-to-clipboard.
 *
 * WHY NOT PLATFORM APIS: posting to Instagram or TikTok on a user's behalf
 * needs OAuth, app review and a business account each. The native sheet gets
 * the same outcome - their post, from their account - for none of that. The
 * APIs are only worth it for posting from OUR accounts automatically, which
 * is a separate problem.
 *
 * NOTE ON INSTAGRAM AND TIKTOK: neither accepts a plain link from a web share
 * on desktop, and neither has a web intent URL. They appear in the native
 * sheet on mobile, which is where people actually share. On desktop we tell
 * the truth rather than offering a button that silently does nothing.
 */
(function () {
  'use strict';

  var W = window;

  function canShareFiles() {
    return !!(navigator.canShare && navigator.share);
  }

  /* Fetches the audio so it can go into the share sheet as a real file.
     Falls back to link-only if the fetch fails - a cross-origin audio host
     without CORS will refuse, and a link is better than an error. */
  function fetchAudioFile(url, filename) {
    return fetch(url, {mode: 'cors'})
      .then(function (r) {
        if (!r.ok) throw new Error('fetch failed');
        return r.blob();
      })
      .then(function (blob) {
        return new File([blob], filename || 'smackagram.mp3', {type: blob.type || 'audio/mpeg'});
      });
  }

  /*
   * opts: { url, title, text, audioUrl, filename }
   * Returns a promise. Resolves 'shared' | 'cancelled' | 'unsupported'.
   */
  function nativeShare(opts) {
    if (!canShareFiles()) return Promise.resolve('unsupported');

    var payload = {
      title: opts.title || 'Smackagram',
      text: opts.text || '',
      url: opts.url,
    };

    /* Try with the file first - sharing the actual audio is far better than a
       link, because the recipient hears it without leaving the app. */
    var withFile = opts.audioUrl
      ? fetchAudioFile(opts.audioUrl, opts.filename).then(function (file) {
          var full = {files: [file], title: payload.title, text: payload.text};
          return navigator.canShare(full) ? full : payload;
        }).catch(function () { return payload; })
      : Promise.resolve(payload);

    return withFile
      .then(function (data) { return navigator.share(data); })
      .then(function () { return 'shared'; })
      .catch(function (e) {
        /* AbortError means they opened the sheet and backed out. That's a
           normal outcome, not a failure, and shouldn't show an error. */
        return (e && e.name === 'AbortError') ? 'cancelled' : 'unsupported';
      });
  }

  /* Desktop targets. Each is a documented web intent - no API keys, no
     account linking, opens a pre-filled composer in a new tab. */
  /* Brand marks as inline SVG. Platforms publish these for exactly this
     purpose, and an icon grid reads as a share sheet at a glance where a row
     of text buttons reads as a form. Each carries its brand colour on hover -
     recognition is the whole point of a logo. */
  var ICONS = {
    x: '<path d="M18.9 2h3.3l-7.2 8.3L23.4 22h-6.6l-5.2-6.8L5.6 22H2.3l7.7-8.8L1.9 2h6.8l4.7 6.2L18.9 2zm-1.2 18h1.8L7.4 3.8H5.5L17.7 20z"/>',
    facebook: '<path d="M24 12.07C24 5.4 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.68.24 2.68.24v2.97h-1.51c-1.49 0-1.96.93-1.96 1.89v2.25h3.33l-.53 3.49h-2.8V24C19.61 23.1 24 18.1 24 12.07z"/>',
    whatsapp: '<path d="M17.47 14.38c-.3-.15-1.75-.86-2.02-.96-.27-.1-.47-.15-.67.15-.2.3-.77.96-.94 1.16-.17.2-.35.22-.64.07-.3-.15-1.25-.46-2.39-1.47-.88-.79-1.48-1.76-1.65-2.06-.17-.3-.02-.46.13-.61.13-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.08-.15-.67-1.61-.92-2.21-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.79.37-.27.3-1.04 1.02-1.04 2.48 0 1.46 1.06 2.87 1.21 3.07.15.2 2.1 3.2 5.08 4.49.71.31 1.26.49 1.69.62.71.23 1.36.2 1.87.12.57-.09 1.75-.72 2-1.41.25-.69.25-1.28.17-1.41-.07-.13-.27-.2-.57-.35zM12.05 21.8h-.02c-1.77 0-3.5-.48-5.02-1.38l-.36-.21-3.73.98 1-3.64-.24-.37a9.86 9.86 0 01-1.51-5.26c0-5.45 4.44-9.89 9.9-9.89 2.64 0 5.12 1.03 6.99 2.9a9.82 9.82 0 012.89 6.99c0 5.46-4.44 9.9-9.9 9.9zM20.5 3.49A11.82 11.82 0 0012.05 0C5.5 0 .17 5.33.17 11.88c0 2.09.55 4.14 1.59 5.94L.07 24l6.33-1.66a11.85 11.85 0 005.65 1.44h.01c6.55 0 11.88-5.33 11.88-11.88 0-3.17-1.24-6.16-3.48-8.41z"/>',
    reddit: '<path d="M24 11.78a2.6 2.6 0 00-4.4-1.86 12.75 12.75 0 00-6.94-2.22l1.18-5.56 3.87.82a1.85 1.85 0 103.7-.12 1.85 1.85 0 00-3.5-.83l-4.32-.92a.44.44 0 00-.52.34l-1.31 6.19a12.76 12.76 0 00-7.02 2.22 2.6 2.6 0 10-2.87 4.26 5.1 5.1 0 00-.06.8c0 4.06 4.73 7.36 10.56 7.36s10.56-3.3 10.56-7.36a5.1 5.1 0 00-.06-.79A2.6 2.6 0 0024 11.78zM6.19 13.63a1.85 1.85 0 113.7 0 1.85 1.85 0 01-3.7 0zm10.33 4.88a6.9 6.9 0 01-4.5 1.4 6.9 6.9 0 01-4.5-1.4.46.46 0 01.65-.65 6 6 0 003.85 1.14 6 6 0 003.85-1.13.46.46 0 01.65.64zm-.16-3.03a1.85 1.85 0 111.85-1.85 1.85 1.85 0 01-1.85 1.85z"/>',
    telegram: '<path d="M23.07 3.3L19.6 20.5c-.26 1.16-.95 1.44-1.92.9l-5.3-3.9-2.56 2.47c-.28.28-.52.52-1.07.52l.38-5.4 9.83-8.88c.43-.38-.09-.6-.66-.22L6.15 13.6.92 11.96c-1.14-.36-1.16-1.14.24-1.69L21.6 2.35c.95-.35 1.78.22 1.47.95z"/>',
    sms: '<path d="M20 2H4a2 2 0 00-2 2v18l4-4h14a2 2 0 002-2V4a2 2 0 00-2-2zM7 9h10v2H7V9zm7 5H7v-2h7v2zm3-6H7V6h10v2z"/>',
    email: '<path d="M20 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V6a2 2 0 00-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/>',
    linkedin: '<path d="M4.98 3.5a2.5 2.5 0 11-.01 5 2.5 2.5 0 01.01-5zM3 9h4v12H3zM9 9h3.8v1.7h.05c.53-.95 1.83-1.95 3.76-1.95C20.5 8.75 21 11.1 21 14.1V21h-4v-6.1c0-1.45-.03-3.3-2.05-3.3-2.05 0-2.36 1.57-2.36 3.2V21H9z"/>',
    discord: '<path d="M19.3 5.3A16.5 16.5 0 0015.2 4l-.2.4a12.5 12.5 0 013.6 1.8 15.6 15.6 0 00-13.2 0 12.5 12.5 0 013.6-1.8L8.8 4a16.5 16.5 0 00-4.1 1.3C2.1 9.2 1.4 13 1.7 16.7a16.6 16.6 0 005 2.5l1.1-1.6a10.8 10.8 0 01-1.7-.8l.4-.3a11.9 11.9 0 0011 0l.4.3c-.5.3-1.1.6-1.7.8l1.1 1.6a16.6 16.6 0 005-2.5c.4-4.3-.7-8.1-2.9-11.4zM8.7 14.5c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2zm6.6 0c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2z"/>',
    instagram: '<path d="M12 2.2c3.2 0 3.6 0 4.9.07 1.2.05 1.8.25 2.2.42.6.22 1 .48 1.4.9.43.42.7.83.9 1.4.18.4.38 1 .43 2.2.06 1.3.07 1.7.07 4.9s0 3.6-.07 4.9c-.05 1.2-.25 1.8-.42 2.2-.22.6-.48 1-.9 1.4-.42.43-.83.7-1.4.9-.4.18-1 .38-2.2.43-1.3.06-1.7.07-4.9.07s-3.6 0-4.9-.07c-1.2-.05-1.8-.25-2.2-.42-.6-.22-1-.48-1.4-.9-.43-.42-.7-.83-.9-1.4-.18-.4-.38-1-.43-2.2C2.2 15.6 2.2 15.2 2.2 12s0-3.6.07-4.9c.05-1.2.25-1.8.42-2.2.22-.6.48-1 .9-1.4.42-.43.83-.7 1.4-.9.4-.18 1-.38 2.2-.43C8.4 2.2 8.8 2.2 12 2.2zm0 3.14A6.66 6.66 0 1018.66 12 6.66 6.66 0 0012 5.34zm0 10.99A4.33 4.33 0 1116.33 12 4.33 4.33 0 0112 16.33zm8.48-11.25a1.56 1.56 0 11-1.56-1.56 1.56 1.56 0 011.56 1.56z"/>',
    tiktok: '<path d="M16.6 5.82A4.28 4.28 0 0115.54 3h-3.09v12.4a2.59 2.59 0 01-2.59 2.5 2.59 2.59 0 010-5.18c.27 0 .53.04.77.12v-3.2a5.8 5.8 0 00-.77-.05A5.73 5.73 0 1016.6 15.3V9.01a7.35 7.35 0 004.29 1.37V7.3a4.29 4.29 0 01-4.29-1.48z"/>',
    twitch: '<path d="M4.3 2L2.6 6.2v14.3h5v3h3l3-3h4l5-5V2H4.3zm15.4 12.6l-3 3h-5l-3 3v-3H4.9V3.7h14.8v10.9zM15.9 7v5.4h-1.7V7h1.7zm-4.6 0v5.4H9.6V7h1.7z"/>',
  };

  function platformLinks(url, text) {
    var u = encodeURIComponent(url);
    var t = encodeURIComponent(text || '');
    return [
      {id: 'x',        label: 'X',        href: 'https://twitter.com/intent/tweet?url=' + u + '&text=' + t},
      {id: 'facebook', label: 'Facebook', href: 'https://www.facebook.com/sharer/sharer.php?u=' + u},
      {id: 'whatsapp', label: 'WhatsApp', href: 'https://wa.me/?text=' + t + '%20' + u},
      {id: 'reddit',   label: 'Reddit',   href: 'https://www.reddit.com/submit?url=' + u + '&title=' + t},
      {id: 'telegram', label: 'Telegram', href: 'https://t.me/share/url?url=' + u + '&text=' + t},
      {id: 'sms',      label: 'Text',     href: 'sms:?&body=' + t + '%20' + u},
      {id: 'linkedin', label: 'LinkedIn', href: 'https://www.linkedin.com/sharing/share-offsite/?url=' + u},
      {id: 'email',    label: 'Email',    href: 'mailto:?subject=' + t + '&body=' + u},

      // These four have NO web share URL. There is no link you can send
      // somebody that opens Instagram or TikTok with your URL already in a
      // post - the platforms simply do not offer one, and anything claiming
      // to is either an app-only intent or does not work at all.
      //
      // So they copy the link first and then open the app, which is the
      // only thing that genuinely works. The button says so.
      {id: 'discord',   label: 'Discord',   href: 'https://discord.com/app',        copyFirst: true},
      {id: 'instagram', label: 'Instagram', href: 'https://www.instagram.com/',     copyFirst: true},
      {id: 'tiktok',    label: 'TikTok',    href: 'https://www.tiktok.com/upload',  copyFirst: true},
      {id: 'twitch',    label: 'Twitch',    href: 'https://www.twitch.tv/',         copyFirst: true},
    ];
  }

  function copy(text) {
    if (navigator.clipboard && W.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    /* Older browsers and insecure contexts still need the textarea trick. */
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); resolve(); }
      catch (e) { reject(e); }
      finally { document.body.removeChild(ta); }
    });
  }

  /* ---- The sheet shown when there's no native one ---- */
  function openFallback(opts) {
    var existing = document.getElementById('smkShareSheet');
    if (existing) existing.remove();

    var wrap = document.createElement('div');
    wrap.id = 'smkShareSheet';
    wrap.innerHTML =
      '<div class="smk-share-scrim"></div>' +
      '<div class="smk-share-panel" role="dialog" aria-label="Share">' +
        '<p class="smk-share-title">Share this</p>' +
        '<div class="smk-share-grid">' +
          platformLinks(opts.url, opts.text).map(function (p) {
            p.href = p.href.replace(
              encodeURIComponent(opts.url),
              encodeURIComponent(tagUrl(opts.url.split('?')[0], p.id)));
            /* aria-label carries the name for screen readers, since the icon
               alone says nothing to one. */
            /* copyFirst platforms have no share URL at all, so the link
               is put on the clipboard before the app opens - otherwise
               somebody lands in Instagram with nothing to paste. */
            var cf = p.copyFirst ? ' data-copyfirst="1"' : '';
            var hint = p.copyFirst ? p.label + ' (copies the link first)' : p.label;
            return '<a class="smk-share-btn smk-' + p.id + '" href="' + p.href + '"' + cf +
                   ' target="_blank" rel="noopener" aria-label="' + hint + '" title="' + hint + '">' +
                   '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
                   ICONS[p.id] + '</svg></a>';
          }).join('') +
        '</div>' +
        '<div class="smk-share-copy">' +
          '<input type="text" readonly value="' + opts.url + '" id="smkShareUrl">' +
          '<button type="button" id="smkShareCopy">Copy</button>' +
        '</div>' +
        (opts.audioUrl
          ? '<a class="smk-share-dl" href="' + opts.audioUrl + '" download>Download the audio</a>'
          : '') +
        '<p class="smk-share-note">Instagram, TikTok, Discord and Twitch have no ' +
        'share link \u2014 those four copy this page\u2019s link and open the app, ' +
        'so you can paste it wherever you want it.</p>' +
        '<button type="button" class="smk-share-close" aria-label="Close">Close</button>' +
      '</div>';
    document.body.appendChild(wrap);

    /* Put the link on the clipboard before the app opens. The copy has to
       happen inside the click for the browser to allow it, so the default
       is prevented and the window opened afterwards by hand. */
    wrap.querySelectorAll('[data-copyfirst]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        var href = el.getAttribute('href');
        try { copy(opts.url); } catch (err) {}
        window.open(href, '_blank', 'noopener');
      });
    });

    function close() { wrap.remove(); }
    wrap.querySelector('.smk-share-scrim').addEventListener('click', close);
    wrap.querySelector('.smk-share-close').addEventListener('click', close);
    document.addEventListener('keydown', function esc(e) {
      if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
    });

    wrap.querySelector('#smkShareCopy').addEventListener('click', function () {
      var btn = this;
      copy(opts.url).then(function () {
        btn.textContent = 'Copied';
        setTimeout(function () { btn.textContent = 'Copy'; }, 1600);
      });
    });
  }

  /*
   * The single entry point. Tries the native sheet, falls back to ours.
   *
   *   smkShare({
   *     url: 'https://smackagram.com/smack/abc123',
   *     title: 'Andy got Smacked',
   *     text: 'Listen to what Smacky said',
   *     audioUrl: 'https://.../recording.mp3',   // optional
   *   })
   */
  /* Attribution that survives. The link back is the main mechanism, but a
     posted link can be stripped or reposted as a screenshot - naming the site
     in the TEXT means the credit travels with the words too. Kept short and
     honest; the native sheet always lets them edit before posting. */
  var TAIL = ' \u2014 smackagram.com';

  function withAttribution(text) {
    if (!text) return 'Sent with Smackagram' + TAIL;
    return text.indexOf('smackagram.com') !== -1 ? text : text + TAIL;
  }

  /* Tags the shared URL so arrivals are attributable. Without this there's no
     way to tell whether sharing brings anyone back, which means no way to know
     if any of this is worth keeping. Standard UTM parameters, so it also works
     if analytics gets added later. */
  function tagUrl(url, platform) {
    try {
      var u = new URL(url, W.location.origin);
      if (!u.searchParams.has('utm_source')) {
        u.searchParams.set('utm_source', platform || 'share');
        u.searchParams.set('utm_medium', 'social');
        u.searchParams.set('utm_campaign', 'user_share');
      }
      return u.toString();
    } catch (e) {
      return url;
    }
  }

  W.smkShare = function (opts) {
    opts = opts || {};
    if (!opts.url) opts.url = W.location.href;
    opts.text = withAttribution(opts.text);
    opts.url = tagUrl(opts.url, 'native');

    nativeShare(opts).then(function (result) {
      if (result === 'unsupported') openFallback(opts);
    });
  };

  /* Any element with data-smk-share becomes a share button. Keeps page
     templates free of wiring - they only describe WHAT is being shared. */
  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-smk-share]');
    if (!el) return;
    e.preventDefault();
    W.smkShare({
      url: el.getAttribute('data-smk-share'),
      title: el.getAttribute('data-smk-title') || document.title,
      text: el.getAttribute('data-smk-text') || '',
      audioUrl: el.getAttribute('data-smk-audio') || '',
      filename: el.getAttribute('data-smk-filename') || 'smackagram.mp3',
    });
  });
})();
