const DATA_RECORDS = {
  "products": [
    {
      "id": "coffee-aurora-bloom",
      "name": "Aurora Bloom",
      "price": "$19.50",
      "roastLevel": "Light",
      "tastingNotes": "meyer lemon, jasmine, honey",
      "rating": "4.8",
      "bagSize": "12 oz",
      "origin": "Ethiopia Gedeb"
    },
    {
      "id": "coffee-maple-cinder",
      "name": "Maple Cinder",
      "price": "$18.00",
      "roastLevel": "Medium",
      "tastingNotes": "toffee, baked apple, hazelnut",
      "rating": "4.7",
      "bagSize": "12 oz",
      "origin": "Guatemala Huehuetenango"
    },
    {
      "id": "coffee-night-terrace",
      "name": "Night Terrace",
      "price": "$17.50",
      "roastLevel": "Dark",
      "tastingNotes": "dark chocolate, clove, molasses",
      "rating": "4.9",
      "bagSize": "12 oz",
      "origin": "Sumatra Takengon"
    },
    {
      "id": "coffee-sunline-house",
      "name": "Sunline House",
      "price": "$16.50",
      "roastLevel": "Medium",
      "tastingNotes": "caramel, orange peel, almond",
      "rating": "4.6",
      "bagSize": "12 oz",
      "origin": "Colombia Huila"
    },
    {
      "id": "coffee-copper-peak-decaf",
      "name": "Copper Peak Decaf",
      "price": "$18.50",
      "roastLevel": "Medium",
      "tastingNotes": "cocoa nib, red apple, brown sugar",
      "rating": "4.5",
      "bagSize": "12 oz",
      "origin": "Peru Cajamarca"
    },
    {
      "id": "coffee-orchard-dawn",
      "name": "Orchard Dawn",
      "price": "$20.00",
      "roastLevel": "Light",
      "tastingNotes": "peach, bergamot, cane sugar",
      "rating": "4.9",
      "bagSize": "12 oz",
      "origin": "Kenya Kirinyaga"
    },
    {
      "id": "coffee-hearth-song",
      "name": "Hearth Song",
      "price": "$17.00",
      "roastLevel": "Dark",
      "tastingNotes": "cacao, walnut, dried cherry",
      "rating": "4.7",
      "bagSize": "12 oz",
      "origin": "Brazil Sul de Minas"
    },
    {
      "id": "coffee-river-stone-espresso",
      "name": "River Stone Espresso",
      "price": "$19.00",
      "roastLevel": "Medium-Dark",
      "tastingNotes": "fig, bittersweet chocolate, praline",
      "rating": "4.8",
      "bagSize": "12 oz",
      "origin": "Seasonal blend"
    }
  ],
  "cartItems": [
    {
      "id": "cart-aurora-bloom",
      "name": "Aurora Bloom",
      "price": "$19.50",
      "quantity": 1,
      "roastLevel": "Light",
      "bagSize": "12 oz"
    },
    {
      "id": "cart-night-terrace",
      "name": "Night Terrace",
      "price": "$17.50",
      "quantity": 2,
      "roastLevel": "Dark",
      "bagSize": "12 oz"
    }
  ],
  "cartSummary": [
    {
      "id": "cart-summary",
      "name": "Cart Summary",
      "itemCount": 3,
      "subtotal": "$54.50"
    }
  ],
  "searchResults": [
    {
      "id": "featured-results",
      "name": "Featured Coffee Results",
      "count": 8
    }
  ]
};

const STORAGE_KEY = "stone-and-steam-cart";
const productRecords = DATA_RECORDS.products;
const productRecordMap = new Map(productRecords.map((product) => [product.id, product]));
const roastSortOrder = {
  Light: 0,
  Medium: 1,
  "Medium-Dark": 2,
  Dark: 3
};
const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD"
});
const addButtonMarkup = new WeakMap();
const addButtonTimers = new WeakMap();

const searchForm = document.querySelector(".site-search");
const searchInput = document.querySelector(".site-search-input");
const cartToggle = document.querySelector(".header-cart-toggle");
const cartCount = document.querySelector(".header-cart-count");
const roastFilterForm = document.querySelector(".roast-filter-panel");
const lightFilterButton = document.querySelector(".filter-light-roast");
const mediumFilterButton = document.querySelector(".filter-medium-roast");
const darkFilterButton = document.querySelector(".filter-dark-roast");
const resultsCount = document.querySelector(".featured-results-count");
const sortForm = document.querySelector(".featured-sort-bar");
const sortSelect = document.querySelector(".featured-sort-select");
const featuredGrid = document.querySelector(".featured-coffee-grid-list");
const productCards = Array.from(document.querySelectorAll(".featured-coffee-card"));
const addToCartButtons = Array.from(document.querySelectorAll(".featured-coffee-add-to-cart"));
const cardContainer = productCards[0] ? productCards[0].parentElement : null;
const cartDrawer = document.querySelector("#cart-drawer");
const cartDrawerPanel = document.querySelector("#cart-drawer-panel");
const cartCloseButton = cartDrawerPanel ? cartDrawerPanel.querySelector('button[aria-label="Close cart drawer"]') : null;
const cartSummarySection = cartDrawerPanel ? cartDrawerPanel.querySelector('section[aria-labelledby="cart-summary-title"]') : null;
const cartList = cartSummarySection ? cartSummarySection.querySelector("ul") : null;
const cartSummaryParagraphs = cartSummarySection ? Array.from(cartSummarySection.querySelectorAll("p")) : [];
const subtotalText = cartSummaryParagraphs[cartSummaryParagraphs.length - 2] || null;
const itemsText = cartSummaryParagraphs[cartSummaryParagraphs.length - 1] || null;
const initialCardOrder = productCards.map((card) => card.dataset.id);
const focusableSelector = [
  'a[href]',
  'button:not([aria-disabled="true"])',
  'input:not([type="hidden"])',
  'select',
  'textarea',
  '[tabindex]:not([tabindex="-1"])'
].join(", ");

const handleImmediateAddToCart = (event) => {
  const button = event.currentTarget;

  if (button.getAttribute("aria-disabled") === "true") {
    return;
  }

  event.preventDefault();
  event.stopImmediatePropagation();

  const card = button.closest(".featured-coffee-card");
  const productId = card ? card.dataset.id : "";

  if (!productId || !productRecordMap.has(productId)) {
    return;
  }

  window.clearTimeout(addButtonTimers.get(button));
  addProductToCart(productId);
  updateButtonState(button, "added");

  const resetTimer = window.setTimeout(() => {
    updateButtonState(button, "default");
    addButtonTimers.delete(button);
  }, 1200);

  addButtonTimers.set(button, resetTimer);
};

addToCartButtons.forEach((button) => {
  button.addEventListener("click", handleImmediateAddToCart, { capture: true });
});

let resultsFeedbackTimer = 0;
let lastFocusedElement = null;
let cartIsOpen = false;
let activeRoastFilter = "";
let currentSortValue = sortSelect ? sortSelect.value : "featured";
let cartState = loadCartState();

function parsePrice(priceText) {
  return Number.parseFloat(priceText.replace("$", ""));
}

function formatCurrency(amount) {
  return currencyFormatter.format(amount);
}

function normalizeSearchValue(value) {
  return value.trim().toLowerCase();
}

function loadCartState() {
  try {
    const storedCart = window.localStorage.getItem(STORAGE_KEY);

    if (storedCart) {
      const parsedCart = JSON.parse(storedCart);

      if (Array.isArray(parsedCart)) {
        return parsedCart.reduce((cartMap, entry) => {
          const product = productRecordMap.get(entry.productId);
          const quantity = Number.parseInt(String(entry.quantity), 10);

          if (product && quantity > 0) {
            cartMap.set(entry.productId, quantity);
          }

          return cartMap;
        }, new Map());
      }
    }
  } catch (error) {
    console.warn("Unable to load cart from localStorage.", error);
  }

  return DATA_RECORDS.cartItems.reduce((cartMap, item) => {
    const product = productRecords.find((record) => record.name === item.name);

    if (product && item.quantity > 0) {
      cartMap.set(product.id, item.quantity);
    }

    return cartMap;
  }, new Map());
}

function saveCartState() {
  try {
    const serializableCart = Array.from(cartState.entries()).map(([productId, quantity]) => ({
      productId,
      quantity
    }));

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(serializableCart));
  } catch (error) {
    console.warn("Unable to save cart to localStorage.", error);
  }
}

function getCartItemCount() {
  return Array.from(cartState.values()).reduce((sum, quantity) => sum + quantity, 0);
}

function getCartSubtotal() {
  return Array.from(cartState.entries()).reduce((sum, [productId, quantity]) => {
    const product = productRecordMap.get(productId);

    return product ? sum + parsePrice(product.price) * quantity : sum;
  }, 0);
}

function getVisibleProductIds() {
  return productCards
    .filter((card) => !card.hidden)
    .map((card) => card.dataset.id)
    .filter(Boolean);
}

function getSortLabel(sortValue) {
  if (sortValue === "price-asc") {
    return "price: low to high";
  }

  if (sortValue === "roast") {
    return "roast level";
  }

  return "featured";
}

function setResultsCountText(count, message) {
  if (!resultsCount) {
    return;
  }

  const baseText = `${count} ${count === 1 ? "coffee" : "coffees"}`;

  window.clearTimeout(resultsFeedbackTimer);

  if (message) {
    resultsCount.textContent = `${baseText} — ${message}`;
    resultsFeedbackTimer = window.setTimeout(() => {
      resultsCount.textContent = baseText;
    }, 1400);
    return;
  }

  resultsCount.textContent = baseText;
}

function updateFilterButtonStates() {
  const filterButtons = [
    { element: lightFilterButton, roast: "Light" },
    { element: mediumFilterButton, roast: "Medium" },
    { element: darkFilterButton, roast: "Dark" }
  ];

  filterButtons.forEach(({ element, roast }) => {
    if (!element) {
      return;
    }

    const isActive = activeRoastFilter === roast;
    element.setAttribute("aria-pressed", String(isActive));
    element.setAttribute("data-state", isActive ? "active" : "default");
  });
}

function productMatchesFilters(product, query) {
  const matchesRoast = activeRoastFilter ? product.roastLevel === activeRoastFilter : true;

  if (!matchesRoast) {
    return false;
  }

  if (!query) {
    return true;
  }

  const searchableText = [product.name, product.tastingNotes, product.roastLevel]
    .join(" ")
    .toLowerCase();

  return searchableText.includes(query);
}

function getSortedCardIds() {
  const cardsWithProducts = initialCardOrder
    .map((productId, index) => ({
      product: productRecordMap.get(productId),
      productId,
      index
    }))
    .filter(({ product }) => Boolean(product));

  if (currentSortValue === "price-asc") {
    return cardsWithProducts
      .slice()
      .sort((left, right) => {
        const priceDifference = parsePrice(left.product.price) - parsePrice(right.product.price);

        return priceDifference || left.index - right.index;
      })
      .map(({ productId }) => productId);
  }

  if (currentSortValue === "roast") {
    return cardsWithProducts
      .slice()
      .sort((left, right) => {
        const leftOrder = roastSortOrder[left.product.roastLevel] ?? Number.MAX_SAFE_INTEGER;
        const rightOrder = roastSortOrder[right.product.roastLevel] ?? Number.MAX_SAFE_INTEGER;

        return leftOrder - rightOrder || left.index - right.index;
      })
      .map(({ productId }) => productId);
  }

  return initialCardOrder.slice();
}

function reorderProductCards() {
  if (!cardContainer) {
    return;
  }

  const cardMap = new Map(productCards.map((card) => [card.dataset.id, card]));
  const sortedIds = getSortedCardIds();

  sortedIds.forEach((productId) => {
    const card = cardMap.get(productId);

    if (card) {
      cardContainer.appendChild(card);
    }
  });
}

function applyProductDisplay(options) {
  const settings = options || {};
  const query = searchInput ? normalizeSearchValue(searchInput.value) : "";

  reorderProductCards();

  productCards.forEach((card) => {
    const productId = card.dataset.id;
    const product = productId ? productRecordMap.get(productId) : null;
    const isVisible = product ? productMatchesFilters(product, query) : false;

    card.hidden = !isVisible;
    card.setAttribute("aria-hidden", String(!isVisible));
  });

  updateFilterButtonStates();

  const visibleCount = getVisibleProductIds().length;
  const sortMessage = settings.announceSort ? `sorted by ${getSortLabel(currentSortValue)}` : "";

  setResultsCountText(visibleCount, sortMessage);
}

function setAddToCartButtonContent(button, label) {
  const iconMarkup = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M5 12h14"></path><path d="M12 5v14"></path></svg>';

  if (label === "Add to cart") {
    button.innerHTML = addButtonMarkup.get(button) || `${iconMarkup} Add to cart`;
    return;
  }

  button.innerHTML = `${iconMarkup} ${label}`;
}

function renderCartDrawer() {
  if (!cartList || !subtotalText || !itemsText) {
    return;
  }

  cartList.innerHTML = "";

  const cartEntries = Array.from(cartState.entries());

  if (cartEntries.length === 0) {
    const emptyItem = document.createElement("li");
    const emptyArticle = document.createElement("article");
    const emptyHeading = document.createElement("h4");
    const emptyCopy = document.createElement("p");

    emptyHeading.textContent = "Your cart is empty";
    emptyCopy.textContent = "Add a coffee bag to see it here.";
    emptyArticle.append(emptyHeading, emptyCopy);
    emptyItem.appendChild(emptyArticle);
    cartList.appendChild(emptyItem);
  } else {
    cartEntries.forEach(([productId, quantity]) => {
      const product = productRecordMap.get(productId);

      if (!product) {
        return;
      }

      const item = document.createElement("li");
      const article = document.createElement("article");
      const title = document.createElement("h4");
      const roast = document.createElement("p");
      const bagSize = document.createElement("p");
      const quantityText = document.createElement("p");
      const price = document.createElement("p");

      article.id = `cart-item-${product.id}`;
      article.setAttribute("data-id", product.id);
      title.textContent = product.name;
      roast.textContent = `${product.roastLevel} roast`;
      bagSize.textContent = product.bagSize;
      quantityText.textContent = `Quantity: ${quantity}`;
      price.textContent = product.price;

      article.append(title, roast, bagSize, quantityText, price);
      item.appendChild(article);
      cartList.appendChild(item);
    });
  }

  subtotalText.textContent = `Subtotal: ${formatCurrency(getCartSubtotal())}`;
  itemsText.textContent = `Items in cart: ${getCartItemCount()}`;
}

function updateCartCount() {
  if (!cartCount) {
    return;
  }

  cartCount.textContent = String(getCartItemCount());
}

function syncCartUI() {
  saveCartState();
  updateCartCount();
  renderCartDrawer();
}

function getFocusableElements(container) {
  if (!container) {
    return [];
  }

  return Array.from(container.querySelectorAll(focusableSelector)).filter((element) => {
    const htmlElement = element;
    return !htmlElement.hidden && htmlElement.getAttribute("aria-hidden") !== "true";
  });
}

function openCartDrawer() {
  if (!cartDrawer || !cartDrawerPanel || !cartToggle) {
    return;
  }

  lastFocusedElement = document.activeElement;
  cartIsOpen = true;
  cartDrawer.hidden = false;
  cartDrawer.setAttribute("aria-hidden", "false");
  cartDrawerPanel.setAttribute("role", "dialog");
  cartDrawerPanel.setAttribute("aria-modal", "true");
  cartDrawerPanel.setAttribute("tabindex", "-1");
  cartToggle.setAttribute("aria-expanded", "true");
  cartToggle.setAttribute("data-state", "open");
  document.body.style.overflow = "hidden";

  const focusTargets = getFocusableElements(cartDrawerPanel);
  const initialFocusTarget = focusTargets[0] || cartDrawerPanel;

  initialFocusTarget.focus();
}

function closeCartDrawer() {
  if (!cartDrawer || !cartDrawerPanel || !cartToggle) {
    return;
  }

  cartIsOpen = false;
  cartDrawer.hidden = true;
  cartDrawer.setAttribute("aria-hidden", "true");
  cartToggle.setAttribute("aria-expanded", "false");
  cartToggle.setAttribute("data-state", "closed");
  document.body.style.overflow = "";

  if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
    lastFocusedElement.focus();
  } else {
    cartToggle.focus();
  }
}

function trapDrawerFocus(event) {
  if (!cartIsOpen || event.key !== "Tab" || !cartDrawerPanel) {
    return;
  }

  const focusTargets = getFocusableElements(cartDrawerPanel);

  if (focusTargets.length === 0) {
    event.preventDefault();
    cartDrawerPanel.focus();
    return;
  }

  const firstElement = focusTargets[0];
  const lastElement = focusTargets[focusTargets.length - 1];

  if (event.shiftKey && document.activeElement === firstElement) {
    event.preventDefault();
    lastElement.focus();
    return;
  }

  if (!event.shiftKey && document.activeElement === lastElement) {
    event.preventDefault();
    firstElement.focus();
  }
}

function handleDrawerKeydown(event) {
  if (!cartIsOpen) {
    return;
  }

  if (event.key === "Escape") {
    event.preventDefault();
    closeCartDrawer();
    return;
  }

  trapDrawerFocus(event);
}

function updateButtonState(button, state) {
  button.setAttribute("data-state", state);

  if (state === "loading") {
    button.setAttribute("aria-disabled", "true");
    button.setAttribute("aria-label", "Adding coffee bag to cart");
    setAddToCartButtonContent(button, "Adding…");
    return;
  }

  if (state === "added") {
    button.setAttribute("aria-disabled", "true");
    button.setAttribute("aria-label", "Added to cart");
    setAddToCartButtonContent(button, "Added to cart");
    return;
  }

  button.setAttribute("aria-disabled", "false");
  button.setAttribute("aria-label", "Add coffee bag to cart");
  setAddToCartButtonContent(button, "Add to cart");
}

function addProductToCart(productId) {
  const currentQuantity = cartState.get(productId) || 0;
  cartState.set(productId, currentQuantity + 1);
  syncCartUI();
}

function handleAddToCart(event) {
  const button = event.currentTarget;

  if (button.getAttribute("aria-disabled") === "true") {
    return;
  }

  const card = button.closest(".featured-coffee-card");
  const productId = card ? card.dataset.id : "";

  if (!productId || !productRecordMap.has(productId)) {
    return;
  }

  window.clearTimeout(addButtonTimers.get(button));
  updateButtonState(button, "loading");

  const loadingTimer = window.setTimeout(() => {
    addProductToCart(productId);
    updateButtonState(button, "added");

    const resetTimer = window.setTimeout(() => {
      updateButtonState(button, "default");
      addButtonTimers.delete(button);
    }, 1200);

    addButtonTimers.set(button, resetTimer);
  }, 250);

  addButtonTimers.set(button, loadingTimer);
}

function handleSearchSubmit(event) {
  event.preventDefault();
  applyProductDisplay();
}

function handleSearchInput() {
  applyProductDisplay();
}

function setActiveRoastFilter(roastLevel) {
  activeRoastFilter = roastLevel;
  applyProductDisplay();
}

function handleRoastFilterSubmit(event) {
  event.preventDefault();
  applyProductDisplay();
}

function handleSortSubmit(event) {
  event.preventDefault();
  currentSortValue = sortSelect ? sortSelect.value : "featured";
  applyProductDisplay({ announceSort: true });
}

function handleSortChange() {
  currentSortValue = sortSelect ? sortSelect.value : "featured";
  applyProductDisplay({ announceSort: true });
}

function initializeAddToCartButtons() {
  addToCartButtons.forEach((button) => {
    addButtonMarkup.set(button, button.innerHTML);
    updateButtonState(button, button.getAttribute("data-state") || "default");
    button.addEventListener("click", handleAddToCart);
  });
}

function initializeCartDrawer() {
  if (!cartDrawer || !cartDrawerPanel || !cartToggle || !cartCloseButton) {
    return;
  }

  cartDrawer.setAttribute("aria-hidden", "true");
  cartToggle.addEventListener("click", () => {
    if (cartToggle.getAttribute("aria-disabled") === "true") {
      return;
    }

    if (cartIsOpen) {
      closeCartDrawer();
      return;
    }

    openCartDrawer();
  });

  cartCloseButton.addEventListener("click", () => {
    closeCartDrawer();
  });

  cartDrawer.addEventListener("click", (event) => {
    if (event.target === cartDrawer) {
      closeCartDrawer();
    }
  });

  document.addEventListener("keydown", handleDrawerKeydown);
}

function initializeFilteringAndSorting() {
  if (searchForm) {
    searchForm.addEventListener("submit", handleSearchSubmit);
  }

  if (searchInput) {
    searchInput.addEventListener("input", handleSearchInput);
  }

  if (roastFilterForm) {
    roastFilterForm.addEventListener("submit", handleRoastFilterSubmit);
  }

  if (lightFilterButton) {
    lightFilterButton.addEventListener("click", () => {
      setActiveRoastFilter("Light");
    });
  }

  if (mediumFilterButton) {
    mediumFilterButton.addEventListener("click", () => {
      setActiveRoastFilter("Medium");
    });
  }

  if (darkFilterButton) {
    darkFilterButton.addEventListener("click", () => {
      setActiveRoastFilter("Dark");
    });
  }

  if (sortForm) {
    sortForm.addEventListener("submit", handleSortSubmit);
  }

  if (sortSelect) {
    sortSelect.setAttribute("aria-describedby", "featured-results-announcement");
    sortSelect.addEventListener("change", handleSortChange);
  }

  if (resultsCount) {
    resultsCount.id = "featured-results-announcement";
  }
}

function initializeStorefront() {
  if (!featuredGrid || productCards.length === 0) {
    return;
  }

  initializeFilteringAndSorting();
  initializeAddToCartButtons();
  initializeCartDrawer();
  syncCartUI();
  updateFilterButtonStates();
  applyProductDisplay();
}

initializeStorefront();