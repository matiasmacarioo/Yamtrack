// Rules for the navigations that swap #main-content instead of the whole page.
//
// The contract is simple: a navigation answer always carries #main-content.
// Pages that live outside the shell (the sign-in screen after the session has
// expired, the admin) break it, and an empty swap would look like a dead link,
// which is worse than the page reload we were trying to avoid. Detecting the
// missing fragment before the swap hands the request back to the browser, so
// those links keep behaving exactly as they always did.

document.body.addEventListener("htmx:beforeSwap", (event) => {
  const target = event.detail.target;

  // Only guard the main-content navigations; partial swaps into the grid or
  // the modals have nothing to do with this rule.
  if (!target || target.id !== "main-content" || event.detail.isError) {
    return;
  }

  const xhr = event.detail.xhr;
  const body = (xhr && xhr.responseText) || "";

  if (body.includes('id="main-content"')) {
    return;
  }

  event.preventDefault();

  // Asking for the path again replays the redirect the browser would have
  // followed anyway. Without it, reloading the current page is still correct:
  // if the session expired that URL cannot be served as a fragment either.
  window.location.assign(event.detail.requestConfig?.path || window.location.href);
});
