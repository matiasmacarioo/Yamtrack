// Keep Alpine and HTMX working together.
//
// HTMX swaps new DOM into the page without Alpine noticing, so any Alpine
// directive inside a swapped fragment would never initialise: x-cloak
// content would stay hidden, dropdowns would stop responding, and a binding
// such as the sidebar's :class would go dead after the first partial update.
//
// htmx:load fires for every inserted node, out-of-band swaps included, which
// makes it the right hook to hand that node back to Alpine. initTree walks
// the subtree and resolves directives against the surrounding Alpine scope,
// which is what a :class without its own x-data needs. The body is skipped:
// it is emitted once at startup, before Alpine has booted, and Alpine.start()
// initialises the initial page itself.

htmx.onLoad((content) => {
  const Alpine = window.Alpine;
  if (!Alpine || !content || content === document.body) {
    return;
  }

  Alpine.initTree(content);
});
