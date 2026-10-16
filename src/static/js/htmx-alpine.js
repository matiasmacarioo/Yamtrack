// Keep Alpine and HTMX working together.
//
// HTMX swaps new DOM into the page without Alpine noticing, so any Alpine
// directive inside a swapped fragment would never initialise: x-cloak
// content would stay hidden and the dropdowns of the filter bar would stop
// responding after the first partial update.
//
// Walking the swapped subtree and starting only the components Alpine has
// not seen yet fixes that. Already-initialised components are stamped with
// _x_dataStack, so skipping them keeps this idempotent and safe to run after
// every single swap, including the ones that only append new items.

document.body.addEventListener("htmx:afterSwap", (event) => {
  const Alpine = window.Alpine;
  if (!Alpine) {
    return;
  }

  const target = event.detail.target;
  const components = [target, ...target.querySelectorAll("[x-data]")];

  for (const component of components) {
    if (component._x_dataStack) {
      continue;
    }

    Alpine.initTree(component);
  }
});
