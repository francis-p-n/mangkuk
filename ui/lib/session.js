// The front door, shared by every signed-in page.
//
// This is not security. There is no server to authenticate against, so this
// only keeps the prototype's flow coherent; a real deployment authenticates
// before the page is ever served.
window.SDOC = window.SDOC || {};
window.SDOC.session = (function () {
  "use strict";

  function user() {
    try { return sessionStorage.getItem("sdoc-user"); } catch (e) { return null; }
  }

  // Called before render so an unauthenticated visitor never sees the data.
  function require() {
    if (user()) return true;
    location.replace("index.html");
    return false;
  }

  function signOut() {
    try { sessionStorage.removeItem("sdoc-user"); } catch (e) { /* fine */ }
    location.href = "index.html";
  }

  // The identity strip every signed-in page carries in its header.
  function mountHeader(el, { here } = {}) {
    if (!el) return;
    const link = (href, text) => here === href
      ? `<span class="btn plain is-here" aria-current="page">${text}</span>`
      : `<a class="btn plain" href="${href}">${text}</a>`;
    el.innerHTML =
      `<span class="signedin">${window.SDOC.fmt.esc(user() || "")}</span>` +
      link("home.html", "Today") +
      link("search.html", "Search") +
      `<a class="btn plain" href="welcome.html">Walkthrough</a>` +
      `<button type="button" class="btn plain" data-act="signout">Sign out</button>`;
    const out = el.querySelector('[data-act="signout"]');
    if (out) out.addEventListener("click", signOut);
  }

  return { user, require, signOut, mountHeader };
})();
