// Keep Alpine and HTMX working together.
//
// HTMX swaps new DOM into the page without Alpine noticing, so any Alpine
// directive inside a swapped fragment would never initialise: x-cloak
// content would stay hidden and the dropdowns would stop responding after
// the first partial update.
//
// Walking the page and starting only the components Alpine has not seen yet
// fixes that. Already-initialised components are stamped with _x_dataStack,
// so skipping them keeps this idempotent and safe to run after every swap.
//
// The walk starts from the body rather than from the event target on
// purpose: an outerHTML swap removes the element it replaced, so the target
// reported by the event can already be detached by the time this runs.

document.body.addEventListener("htmx:afterSwap", () => {
  const Alpine = window.Alpine;
  if (!Alpine) {
    return;
  }

  for (const component of document.body.querySelectorAll("[x-data]")) {
    if (!component._x_dataStack) {
      Alpine.initTree(component);
    }
  }
});
