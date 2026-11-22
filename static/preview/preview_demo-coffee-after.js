(() => {
  'use strict';

  const SELECTORS = {
    headerSearch: '.header-search',
    headerSearchInput: '.header-search-input',
    headerCartToggle: '.header-cart-toggle',
    headerCartCount: '.header-cart-count',
    roastFilterLight: '.roast-filter-light',
    roastFilterMedium: '.roast-filter-medium',
    roastFilterDark: '.roast-filter-dark',
    featuredBeanCard: '.featured-bean-card',
    featuredBeanAdd: '.featured-bean-add',
    listingFilterPanel: '.listing-filter-panel',
    filterCategory: '.filter-category',
    filterPriceRange: '.filter-price-range',
    filterBrand: '.filter-brand',
    listingSortBar: '.listing-sort-bar',
    listingResultsCount: '.listing-results-count',
    listingSortSelect: '.listing-sort-select',
    coffeeProductGrid: '.coffee-product-grid',
    coffeeProductCard: '.coffee-product-card',
    coffeeProductAdd: '.coffee-product-add',
    listingPagination: '.listing-pagination',
    paginationPrev: '.pagination-prev',
    paginationPage1: '.pagination-page-1',
    paginationPage2: '.pagination-page-2',
    paginationNext: '.pagination-next',
    cartDrawerPanel: '.cart-drawer-panel',
    miniCartClose: '.mini-cart-close',
    miniCartItems: '.mini-cart-items',
    miniCartItem: '.mini-cart-item',
    miniCartItemQuantity: '.mini-cart-item-quantity',
    miniCartQuantityDecrement: '.mini-cart-quantity-decrement',
    miniCartQuantityValue: '.mini-cart-quantity-value',
    miniCartQuantityIncrement: '.mini-cart-quantity-increment',
    miniCartItemRemove: '.mini-cart-item-remove',
    miniCartSubtotal: '.mini-cart-subtotal',
    miniCartCheckout: '.mini-cart-checkout',
    checkoutPanel: '.checkout-panel',
    checkoutSteps: '.checkout-steps',
    checkoutForm: '.checkout-form',
    checkoutSubmit: '.checkout-submit',
    paymentForm: '.payment-form',
    paymentSubmit: '.payment-submit',
    checkoutOrderSummary: '.checkout-order-summary',
    checkoutOrderTotal: '.checkout-order-total',
    checkoutConfirmation: '.checkout-confirmation',
    siteHeader: '.site-header'
  };

  const getStorefrontCartDrawerRefs = () => ({
    cartToggle: document.querySelector(SELECTORS.headerCartToggle),
    cartPanel: document.querySelector(SELECTORS.cartDrawerPanel),
    cartClose: document.querySelector(SELECTORS.miniCartClose),
    roastFilterLight: document.querySelector(SELECTORS.roastFilterLight)
  });

  const syncStorefrontCartDrawerState = (isOpen) => {
    const refs = getStorefrontCartDrawerRefs();
    const { cartToggle, cartPanel } = refs;

    if (cartToggle && cartToggle.hasAttribute('aria-expanded')) {
      cartToggle.setAttribute('aria-expanded', String(isOpen));
    }

    if (cartPanel && cartPanel.hasAttribute('aria-hidden')) {
      cartPanel.setAttribute('aria-hidden', String(!isOpen));
    }

    if (cartPanel && cartPanel.hasAttribute('data-state')) {
      cartPanel.setAttribute('data-state', isOpen ? 'open' : 'closed');
    }

    if (cartPanel) {
      cartPanel.style.pointerEvents = isOpen ? 'auto' : 'none';
    }
  };

  const isStorefrontCartDrawerOpen = () => {
    const refs = getStorefrontCartDrawerRefs();
    const { cartToggle, cartPanel } = refs;

    if (cartToggle && cartToggle.getAttribute('aria-expanded') === 'true') {
      return true;
    }

    if (cartPanel && cartPanel.getAttribute('aria-hidden') === 'false') {
      return true;
    }

    return Boolean(cartPanel && cartPanel.getAttribute('data-state') === 'open');
  };

  const closeStorefrontCartDrawer = (options = {}) => {
    const shouldReturnFocus = Boolean(options.returnFocus);
    const refs = getStorefrontCartDrawerRefs();
    const { cartToggle, cartPanel, cartClose } = refs;

    if (!cartToggle && !cartPanel) {
      return;
    }

    if (cartClose && isStorefrontCartDrawerOpen()) {
      cartClose.click();
    } else if (
      cartToggle &&
      isStorefrontCartDrawerOpen() &&
      typeof cartToggle.click === 'function'
    ) {
      cartToggle.click();
    }

    syncStorefrontCartDrawerState(false);

    if (shouldReturnFocus && cartToggle) {
      cartToggle.focus();
    }
  };

  const isWithinElement = (target, element) => (
    Boolean(target) &&
    Boolean(element) &&
    (target === element || element.contains(target))
  );

  const handleStorefrontCartDismissal = (target) => {
    const refs = getStorefrontCartDrawerRefs();
    const { cartToggle, cartPanel } = refs;

    if (!isStorefrontCartDrawerOpen() || !cartPanel) {
      syncStorefrontCartDrawerState(false);
      return;
    }

    if (isWithinElement(target, cartToggle)) {
      return;
    }

    if (target === cartPanel || !isWithinElement(target, cartPanel)) {
      closeStorefrontCartDrawer();
    }
  };

  document.addEventListener('pointerdown', (event) => {
    handleStorefrontCartDismissal(event.target);
  }, true);

  document.addEventListener('focusin', (event) => {
    handleStorefrontCartDismissal(event.target);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && isStorefrontCartDrawerOpen()) {
      closeStorefrontCartDrawer({ returnFocus: true });
    }
  });

  const storefrontCartRefs = getStorefrontCartDrawerRefs();

  if (storefrontCartRefs.cartToggle) {
    storefrontCartRefs.cartToggle.addEventListener('click', () => {
      window.requestAnimationFrame(() => {
        syncStorefrontCartDrawerState(isStorefrontCartDrawerOpen());
      });
    });
  }

  if (storefrontCartRefs.cartClose) {
    storefrontCartRefs.cartClose.addEventListener('click', () => {
      window.requestAnimationFrame(() => {
        syncStorefrontCartDrawerState(isStorefrontCartDrawerOpen());
      });
    });
  }

  if (storefrontCartRefs.roastFilterLight) {
    storefrontCartRefs.roastFilterLight.addEventListener('pointerdown', () => {
      closeStorefrontCartDrawer();
    }, true);

    storefrontCartRefs.roastFilterLight.addEventListener('focus', () => {
      closeStorefrontCartDrawer();
    });
  }

  syncStorefrontCartDrawerState(isStorefrontCartDrawerOpen());

  const STORAGE_KEYS = {
    cart: 'hearthside-roasters-cart',
    order: 'hearthside-roasters-last-order'
  };

  const SHIPPING_FEE = 6;
  const PAGE_SIZE = 4;

  const records = [
    {
      id: 'coffee-001',
      name: 'Dark Tide Ethiopia',
      price: '$21.00',
      category: 'Single Origin',
      brand: 'Hearthside Roasters',
      roastLevel: 'Light',
      tastingNotes: 'meyer lemon, jasmine, peach tea',
      rating: '4.8',
      bagSize: '12 oz',
      process: 'Washed',
      origin: 'Yirgacheffe, Ethiopia',
      retailPrice: '$26.00',
      brewMethods: 'V60, Chemex, AeroPress',
      materials: 'Compostable high-barrier bag with tin tie',
      altText: 'Dark Tide Ethiopia whole bean coffee bag placeholder'
    },
    {
      id: 'coffee-002',
      name: 'Red Clay Colombia',
      price: '$19.50',
      category: 'Single Origin',
      brand: 'Hearthside Roasters',
      roastLevel: 'Medium',
      tastingNotes: 'red apple, panela, cocoa nib',
      rating: '4.7',
      bagSize: '12 oz',
      process: 'Washed',
      origin: 'Huila, Colombia',
      retailPrice: '$24.00',
      brewMethods: 'Drip, Kalita, French press',
      materials: 'Compostable high-barrier bag with tin tie',
      altText: 'Red Clay Colombia whole bean coffee bag placeholder'
    },
    {
      id: 'coffee-003',
      name: 'Night Harbor Sumatra',
      price: '$20.00',
      category: 'Single Origin',
      brand: 'Hearthside Roasters',
      roastLevel: 'Dark',
      tastingNotes: "cedar, baker's chocolate, molasses",
      rating: '4.6',
      bagSize: '12 oz',
      process: 'Wet-hulled',
      origin: 'Aceh, Sumatra',
      retailPrice: '$25.00',
      brewMethods: 'French press, espresso, moka pot',
      materials: 'Compostable high-barrier bag with tin tie',
      altText: 'Night Harbor Sumatra whole bean coffee bag placeholder'
    },
    {
      id: 'coffee-004',
      name: 'House Line Blend',
      price: '$17.00',
      category: 'Blend',
      brand: 'Hearthside Roasters',
      roastLevel: 'Medium',
      tastingNotes: 'caramel, toasted almond, orange zest',
      rating: '4.9',
      bagSize: '12 oz',
      process: 'Mixed washed and natural lots',
      origin: 'Brazil and Guatemala',
      retailPrice: '$22.00',
      brewMethods: 'Drip, batch brew, espresso',
      materials: 'Compostable high-barrier bag with tin tie',
      altText: 'House Line Blend whole bean coffee bag placeholder'
    },
    {
      id: 'coffee-005',
      name: 'Pine & Cherry Decaf',
      price: '$18.50',
      category: 'Decaf',
      brand: 'Hearthside Roasters',
      roastLevel: 'Medium',
      tastingNotes: 'cherry cola, cacao, walnut',
      rating: '4.5',
      bagSize: '12 oz',
      process: 'EA decaf',
      origin: 'Popayán, Colombia',
      retailPrice: '$23.00',
      brewMethods: 'Drip, pour over, espresso',
      materials: 'Compostable high-barrier bag with tin tie',
      altText: 'Pine & Cherry Decaf whole bean coffee bag placeholder'
    },
    {
      id: 'coffee-006',
      name: 'Sun Room Guatemala',
      price: '$22.00',
      category: 'Single Origin',
      brand: 'Guest Lot',
      roastLevel: 'Light',
      tastingNotes: 'pear, honey, chamomile',
      rating: '4.8',
      bagSize: '12 oz',
      process: 'Washed',
      origin: 'Huehuetenango, Guatemala',
      retailPrice: '$27.00',
      brewMethods: 'V60, Origami, AeroPress',
      materials: 'Compostable high-barrier bag with tin tie',
      altText: 'Sun Room Guatemala whole bean coffee bag placeholder'
    },
    {
      id: 'coffee-007',
      name: 'Maple Street Espresso',
      price: '$18.00',
      category: 'Blend',
      brand: 'Hearthside Roasters',
      roastLevel: 'Dark',
      tastingNotes: 'brown sugar, bittersweet chocolate, dried fig',
      rating: '4.7',
      bagSize: '12 oz',
      process: 'Seasonal espresso blend',
      origin: 'Peru and Brazil',
      retailPrice: '$23.00',
      brewMethods: 'Espresso, moka pot, cappuccino',
      materials: 'Compostable high-barrier bag with tin tie',
      altText: 'Maple Street Espresso whole bean coffee bag placeholder'
    },
    {
      id: 'coffee-008',
      name: 'Bloom Kenya',
      price: '$23.50',
      category: 'Single Origin',
      brand: 'Guest Lot',
      roastLevel: 'Light',
      tastingNotes: 'blackcurrant, grapefruit, hibiscus',
      rating: '4.9',
      bagSize: '12 oz',
      process: 'Washed',
      origin: 'Nyeri, Kenya',
      retailPrice: '$29.00',
      brewMethods: 'Pour over, AeroPress, iced filter',
      materials: 'Compostable high-barrier bag with tin tie',
      altText: 'Bloom Kenya whole bean coffee bag placeholder'
    },
    {
      id: 'cart-summary',
      name: 'Cart Summary',
      itemCount: '3',
      subtotal: '$64.00',
      orderTotal: '$70.00'
    },
    {
      id: 'listing-meta',
      name: 'Listing Meta',
      resultCount: '8'
    }
  ];

  const productById = new Map(
    records
      .filter((record) => record.id.startsWith('coffee-'))
      .map((record) => [record.id, record])
  );
  const productByName = new Map(
    records
      .filter((record) => record.id.startsWith('coffee-'))
      .map((record) => [record.name, record])
  );
  const defaultProductOrder = records
    .filter((record) => record.id.startsWith('coffee-'))
    .map((record) => record.id);

  const filterState = {
    search: '',
    roast: 'all',
    category: 'all',
    price: 'all',
    brand: 'all',
    sort: 'relevance',
    page: 1,
    paginationActive: false
  };

  const checkoutState = {
    shipping: null,
    payment: null
  };

  let ui;
  let cart;
  let liveRegion;
  let focusTrapCleanup = null;
  let lastCartTrigger = null;
  let lastCheckoutTrigger = null;

  function init() {
    ui = {
      headerSearch: document.querySelector(SELECTORS.headerSearch),
      headerSearchInput: document.querySelector(SELECTORS.headerSearchInput),
      headerCartToggle: document.querySelector(SELECTORS.headerCartToggle),
      headerCartCount: document.querySelector(SELECTORS.headerCartCount),
      roastFilterLight: document.querySelector(SELECTORS.roastFilterLight),
      roastFilterMedium: document.querySelector(SELECTORS.roastFilterMedium),
      roastFilterDark: document.querySelector(SELECTORS.roastFilterDark),
      featuredAddButtons: Array.from(document.querySelectorAll(SELECTORS.featuredBeanAdd)),
      filterPanel: document.querySelector(SELECTORS.listingFilterPanel),
      filterCategory: document.querySelector(SELECTORS.filterCategory),
      filterPriceRange: document.querySelector(SELECTORS.filterPriceRange),
      filterBrand: document.querySelector(SELECTORS.filterBrand),
      listingResultsCount: document.querySelector(SELECTORS.listingResultsCount),
      listingSortSelect: document.querySelector(SELECTORS.listingSortSelect),
      coffeeProductGrid: document.querySelector(SELECTORS.coffeeProductGrid),
      coffeeAddButtons: Array.from(document.querySelectorAll(SELECTORS.coffeeProductAdd)),
      productCards: Array.from(document.querySelectorAll(SELECTORS.coffeeProductCard)),
      paginationPrev: document.querySelector(SELECTORS.paginationPrev),
      paginationPage1: document.querySelector(SELECTORS.paginationPage1),
      paginationPage2: document.querySelector(SELECTORS.paginationPage2),
      paginationNext: document.querySelector(SELECTORS.paginationNext),
      cartDrawer: document.querySelector(SELECTORS.cartDrawerPanel),
      miniCartClose: document.querySelector(SELECTORS.miniCartClose),
      miniCartItems: document.querySelector(SELECTORS.miniCartItems),
      miniCartSubtotal: document.querySelector(SELECTORS.miniCartSubtotal),
      miniCartCheckout: document.querySelector(SELECTORS.miniCartCheckout),
      checkoutPanel: document.querySelector(SELECTORS.checkoutPanel),
      checkoutSteps: document.querySelector(SELECTORS.checkoutSteps),
      checkoutForm: document.querySelector(SELECTORS.checkoutForm),
      checkoutSubmit: document.querySelector(SELECTORS.checkoutSubmit),
      paymentForm: document.querySelector(SELECTORS.paymentForm),
      paymentSubmit: document.querySelector(SELECTORS.paymentSubmit),
      checkoutOrderSummary: document.querySelector(SELECTORS.checkoutOrderSummary),
      checkoutOrderTotal: document.querySelector(SELECTORS.checkoutOrderTotal),
      checkoutConfirmation: document.querySelector(SELECTORS.checkoutConfirmation),
      headerPrimaryNav: document.querySelector(`${SELECTORS.siteHeader} nav[aria-label="Primary"]`),
      checkoutTitle: document.querySelector('#checkout-title'),
      confirmationTitle: document.querySelector('#confirmation-title'),
      reviewCartButton: document.querySelector('[aria-controls="checkout-stage-review-cart"]'),
      reviewCartBody: document.querySelector('#checkout-stage-review-cart'),
      customerDetailsButton: document.querySelector('[aria-controls="checkout-stage-customer-details"]'),
      customerDetailsBody: document.querySelector('#checkout-stage-customer-details'),
      reviewOrderButton: document.querySelector('[aria-controls="checkout-stage-review-order"]'),
      reviewOrderBody: document.querySelector('#checkout-stage-review-order'),
      paymentButton: document.querySelector('[aria-controls="checkout-stage-payment"]'),
      paymentBody: document.querySelector('#checkout-stage-payment'),
      reviewCartLinks: Array.from(document.querySelectorAll('#checkout-stage-review-cart a'))
    };

    if (!ui.headerSearch || !ui.coffeeProductGrid || !ui.cartDrawer || !ui.checkoutPanel) {
      return;
    }

    liveRegion = createLiveRegion();
    cart = loadCartFromStorageOrMarkup();

    bindSearch();
    bindRoastFilters();
    bindListingFilters();
    bindSort();
    bindPagination();
    bindAddToCartButtons();
    bindCartDrawer();
    bindCheckout();
    bindValidation();

    renderCart();
    applyProductPresentation();
    closeCartDrawer({ restoreFocus: false });
    ui.checkoutPanel.hidden = true;
    resetCheckoutView();
  }

  function bindSearch() {
    ui.headerSearch.addEventListener('submit', (event) => {
      event.preventDefault();
      filterState.search = ui.headerSearchInput.value.trim().toLowerCase();
      resetListingToFirstPage();
      applyProductPresentation({ moveFocusToGrid: true });
    });

    ui.headerSearchInput.addEventListener('input', () => {
      filterState.search = ui.headerSearchInput.value.trim().toLowerCase();
      resetListingToFirstPage();
      applyProductPresentation();
    });
  }

  function bindRoastFilters() {
    ui.roastFilterLight.addEventListener('click', (event) => {
      event.preventDefault();
      filterState.roast = 'Light';
      resetListingToFirstPage();
      applyProductPresentation({ moveFocusToGrid: true });
    });

    ui.roastFilterMedium.addEventListener('click', (event) => {
      event.preventDefault();
      filterState.roast = 'Medium';
      resetListingToFirstPage();
      applyProductPresentation({ moveFocusToGrid: true });
    });

    ui.roastFilterDark.addEventListener('click', (event) => {
      event.preventDefault();
      filterState.roast = 'Dark';
      resetListingToFirstPage();
      applyProductPresentation({ moveFocusToGrid: true });
    });
  }

  function bindListingFilters() {
    const filterForm = ui.filterPanel.querySelector('form');

    if (filterForm) {
      filterForm.addEventListener('submit', (event) => {
        event.preventDefault();
        syncFilterStateFromControls();
        resetListingToFirstPage();
        applyProductPresentation({ moveFocusToGrid: true });
      });
    }

    ui.filterCategory.addEventListener('change', () => {
      syncFilterStateFromControls();
      resetListingToFirstPage();
      applyProductPresentation();
    });

    ui.filterPriceRange.addEventListener('change', () => {
      syncFilterStateFromControls();
      resetListingToFirstPage();
      applyProductPresentation();
    });

    ui.filterBrand.addEventListener('change', () => {
      syncFilterStateFromControls();
      resetListingToFirstPage();
      applyProductPresentation();
    });
  }

  function bindSort() {
    ui.listingSortSelect.addEventListener('change', () => {
      filterState.sort = ui.listingSortSelect.value;
      if (filterState.paginationActive) {
        filterState.page = 1;
      }
      applyProductPresentation();
    });
  }

  function bindPagination() {
    ui.paginationPrev.addEventListener('click', (event) => {
      event.preventDefault();
      if (isAriaDisabled(ui.paginationPrev)) {
        return;
      }
      filterState.paginationActive = true;
      filterState.page = Math.max(1, filterState.page - 1);
      applyProductPresentation({ moveFocusToGrid: true });
    });

    ui.paginationPage1.addEventListener('click', (event) => {
      event.preventDefault();
      filterState.paginationActive = true;
      filterState.page = 1;
      applyProductPresentation({ moveFocusToGrid: true });
    });

    ui.paginationPage2.addEventListener('click', (event) => {
      event.preventDefault();
      if (isAriaDisabled(ui.paginationPage2)) {
        return;
      }
      filterState.paginationActive = true;
      filterState.page = 2;
      applyProductPresentation({ moveFocusToGrid: true });
    });

    ui.paginationNext.addEventListener('click', (event) => {
      event.preventDefault();
      if (isAriaDisabled(ui.paginationNext)) {
        return;
      }
      const totalPages = getTotalPages(getFilteredProducts().length);
      filterState.paginationActive = true;
      filterState.page = Math.min(totalPages, filterState.page + 1);
      applyProductPresentation({ moveFocusToGrid: true });
    });
  }

  function bindAddToCartButtons() {
    ui.featuredAddButtons.forEach((button) => {
      button.addEventListener('click', () => {
        if (isAriaDisabled(button)) {
          return;
        }
        const card = button.closest(SELECTORS.featuredBeanCard);
        addCardProductToCart(card, button);
      });
    });

    ui.coffeeAddButtons.forEach((button) => {
      button.addEventListener('click', () => {
        if (isAriaDisabled(button)) {
          return;
        }
        const card = button.closest(SELECTORS.coffeeProductCard);
        addCardProductToCart(card, button);
      });
    });
  }

  function bindCartDrawer() {
    ui.headerCartToggle.addEventListener('click', () => {
      if (isAriaDisabled(ui.headerCartToggle)) {
        return;
      }
      openCartDrawer(ui.headerCartToggle);
    });

    ui.miniCartClose.addEventListener('click', () => {
      closeCartDrawer({ restoreFocus: true });
    });

    ui.miniCartItems.addEventListener('click', (event) => {
      const decrementButton = event.target.closest(SELECTORS.miniCartQuantityDecrement);
      const incrementButton = event.target.closest(SELECTORS.miniCartQuantityIncrement);
      const removeButton = event.target.closest(SELECTORS.miniCartItemRemove);
      const item = event.target.closest(SELECTORS.miniCartItem);

      if (!item) {
        return;
      }

      if (decrementButton) {
        if (isAriaDisabled(decrementButton)) {
          return;
        }
        updateCartItemQuantity(item.getAttribute('data-id'), -1);
      }

      if (incrementButton) {
        if (isAriaDisabled(incrementButton)) {
          return;
        }
        updateCartItemQuantity(item.getAttribute('data-id'), 1);
      }

      if (removeButton) {
        if (isAriaDisabled(removeButton)) {
          return;
        }
        removeCartItem(item.getAttribute('data-id'));
      }
    });

    document.addEventListener('click', (event) => {
      if (ui.cartDrawer.hidden) {
        return;
      }
      const clickedInsideDrawer = ui.cartDrawer.contains(event.target);
      const clickedTrigger = ui.headerCartToggle.contains(event.target);
      if (!clickedInsideDrawer && !clickedTrigger) {
        closeCartDrawer({ restoreFocus: false });
      }
    });
  }

  function bindCheckout() {
    ui.miniCartCheckout.addEventListener('click', () => {
      if (isAriaDisabled(ui.miniCartCheckout)) {
        announce('Your cart is empty. Add a coffee before checkout.');
        return;
      }
      openCheckoutFlow(ui.miniCartCheckout);
    });

    ui.reviewCartLinks.forEach((link) => {
      link.addEventListener('click', (event) => {
        event.preventDefault();
        openCheckoutStage('customerDetails', { focusTarget: ui.checkoutForm.querySelector('#checkout-email') });
      });
    });

    [
      ['reviewCart', ui.reviewCartButton],
      ['customerDetails', ui.customerDetailsButton],
      ['reviewOrder', ui.reviewOrderButton],
      ['payment', ui.paymentButton]
    ].forEach(([stageName, button]) => {
      button.addEventListener('click', () => {
        if (isAriaDisabled(button)) {
          return;
        }
        if (stageName === 'reviewOrder') {
          updateCheckoutSummary();
        }
        openCheckoutStage(stageName, { focusTarget: button });
      });
    });

    ui.checkoutForm.addEventListener('submit', (event) => {
      event.preventDefault();
      handleCheckoutSubmit();
    });

    ui.paymentForm.addEventListener('submit', (event) => {
      event.preventDefault();
      handlePaymentSubmit();
    });

    ui.checkoutPanel.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !ui.checkoutPanel.hidden) {
        event.preventDefault();
        closeCheckoutFlow({ restoreFocus: true });
      }
    });
  }

  function bindValidation() {
    const shippingFields = [
      ui.checkoutForm.querySelector('#checkout-email'),
      ui.checkoutForm.querySelector('#checkout-full-name'),
      ui.checkoutForm.querySelector('#checkout-address')
    ];

    const paymentFields = [
      ui.paymentForm.querySelector('#payment-card-number'),
      ui.paymentForm.querySelector('#payment-expiry'),
      ui.paymentForm.querySelector('#payment-cvc')
    ];

    shippingFields.forEach((field) => bindFieldValidation(field));
    paymentFields.forEach((field) => bindFieldValidation(field));
  }

  function bindFieldValidation(field) {
    field.addEventListener('blur', () => {
      validateField(field);
    });

    field.addEventListener('input', () => {
      if (field.getAttribute('aria-invalid') === 'true') {
        validateField(field);
      }
    });
  }

  function syncFilterStateFromControls() {
    filterState.category = ui.filterCategory.value;
    filterState.price = ui.filterPriceRange.value;
    filterState.brand = ui.filterBrand.value;
  }

  function resetListingToFirstPage() {
    filterState.page = 1;
  }

  function addCardProductToCart(card, button) {
    if (!card) {
      return;
    }

    const productId = card.getAttribute('data-id');
    const product = productById.get(productId);

    if (!product) {
      return;
    }

    const currentQuantity = cart.get(product.id) || 0;
    cart.set(product.id, currentQuantity + 1);
    persistCart();
    renderCart();
    showButtonFeedback(button, 'Added to cart');
    announce(`${product.name} added to cart.`);
  }

  function updateCartItemQuantity(productId, amount) {
    const currentQuantity = cart.get(productId) || 0;
    const nextQuantity = currentQuantity + amount;

    if (nextQuantity <= 0) {
      cart.delete(productId);
    } else {
      cart.set(productId, nextQuantity);
    }

    persistCart();
    renderCart();
    announce('Cart updated.');
  }

  function removeCartItem(productId) {
    const product = productById.get(productId);
    cart.delete(productId);
    persistCart();
    renderCart();
    announce(product ? `${product.name} removed from cart.` : 'Item removed from cart.');
  }

  function renderCart() {
    const count = getCartItemCount();
    const subtotal = getCartSubtotal();
    const total = getOrderTotal();

    ui.headerCartCount.textContent = String(count);
    ui.headerCartCount.dataset.state = count === 0 ? 'empty' : 'default';
    ui.miniCartSubtotal.textContent = formatCurrency(subtotal);
    ui.miniCartSubtotal.dataset.state = 'default';
    ui.checkoutOrderTotal.textContent = formatCurrency(total);
    ui.checkoutOrderTotal.dataset.state = 'default';

    setAriaDisabled(ui.miniCartCheckout, count === 0);
    ui.headerCartToggle.setAttribute('aria-label', count === 0 ? 'Open cart drawer' : `Open cart drawer with ${count} item${count === 1 ? '' : 's'}`);

    const itemsTitle = ui.miniCartItems.querySelector('#mini-cart-items-title');
    const existingItems = Array.from(ui.miniCartItems.querySelectorAll(SELECTORS.miniCartItem));
    existingItems.forEach((item) => item.remove());

    const emptyState = ui.miniCartItems.querySelector('[data-empty-cart]');
    if (emptyState) {
      emptyState.remove();
    }

    if (count === 0) {
      const emptyMessage = document.createElement('p');
      emptyMessage.setAttribute('data-empty-cart', 'true');
      emptyMessage.textContent = 'Your cart is empty. Add a coffee to get started.';
      ui.miniCartItems.appendChild(emptyMessage);
    } else {
      cart.forEach((quantity, productId) => {
        const product = productById.get(productId);
        if (!product) {
          return;
        }
        ui.miniCartItems.appendChild(createMiniCartItem(product, quantity));
      });
    }

    if (itemsTitle) {
      ui.miniCartItems.insertBefore(itemsTitle, ui.miniCartItems.firstChild);
    }

    updateCheckoutSummary();
    updateCheckoutAvailability();
  }

  function createMiniCartItem(product, quantity) {
    const article = document.createElement('article');
    article.className = 'mini-cart-item';
    article.setAttribute('data-component', 'cart-item');
    article.setAttribute('data-id', product.id);

    const placeholder = document.createElement('div');
    placeholder.className = 'product-image-placeholder';
    placeholder.textContent = product.name;

    const title = document.createElement('h4');
    title.textContent = product.name;

    const details = document.createElement('p');
    details.textContent = `${product.bagSize} · ${product.roastLevel} roast`;

    const priceWrapper = document.createElement('p');
    const price = document.createElement('span');
    price.className = 'mini-cart-item-price';
    price.setAttribute('data-component', 'product-price');
    price.textContent = product.price;
    priceWrapper.appendChild(price);

    const quantityControl = document.createElement('div');
    quantityControl.className = 'mini-cart-item-quantity';
    quantityControl.setAttribute('data-component', 'quantity-selector');

    const decrement = document.createElement('button');
    decrement.className = 'mini-cart-quantity-decrement';
    decrement.type = 'button';
    decrement.setAttribute('aria-label', 'Decrease quantity');
    decrement.textContent = '−';

    const value = document.createElement('span');
    value.className = 'mini-cart-quantity-value';
    value.setAttribute('aria-live', 'polite');
    value.setAttribute('data-state', 'default');
    value.textContent = String(quantity);

    const increment = document.createElement('button');
    increment.className = 'mini-cart-quantity-increment';
    increment.type = 'button';
    increment.setAttribute('aria-label', 'Increase quantity');
    increment.textContent = '+';

    quantityControl.appendChild(decrement);
    quantityControl.appendChild(value);
    quantityControl.appendChild(increment);

    const remove = document.createElement('button');
    remove.className = 'mini-cart-item-remove';
    remove.type = 'button';
    remove.setAttribute('aria-label', 'Remove item from cart');
    remove.textContent = 'Remove';

    article.appendChild(placeholder);
    article.appendChild(title);
    article.appendChild(details);
    article.appendChild(priceWrapper);
    article.appendChild(quantityControl);
    article.appendChild(remove);

    return article;
  }

  function updateCheckoutSummary() {
    const count = getCartItemCount();
    const subtotal = getCartSubtotal();
    const total = getOrderTotal();
    const itemsText = count === 1 ? '1 bag' : `${count} bags`;

    let itemCountLine = ui.checkoutOrderSummary.querySelector('[data-checkout-items]');
    if (!itemCountLine) {
      itemCountLine = document.createElement('p');
      itemCountLine.setAttribute('data-checkout-items', 'true');
      ui.checkoutOrderSummary.insertBefore(itemCountLine, ui.checkoutOrderTotal.parentElement);
    }
    itemCountLine.textContent = `Items: ${itemsText}`;

    let subtotalLine = ui.checkoutOrderSummary.querySelector('[data-checkout-subtotal]');
    if (!subtotalLine) {
      subtotalLine = document.createElement('p');
      subtotalLine.setAttribute('data-checkout-subtotal', 'true');
      ui.checkoutOrderSummary.insertBefore(subtotalLine, ui.checkoutOrderTotal.parentElement);
    }
    subtotalLine.textContent = `Subtotal: ${formatCurrency(subtotal)}`;

    let shippingLine = ui.checkoutOrderSummary.querySelector('[data-checkout-shipping]');
    if (!shippingLine) {
      shippingLine = document.createElement('p');
      shippingLine.setAttribute('data-checkout-shipping', 'true');
      ui.checkoutOrderSummary.insertBefore(shippingLine, ui.checkoutOrderTotal.parentElement);
    }
    shippingLine.textContent = `Shipping: ${count === 0 ? '$0.00' : formatCurrency(SHIPPING_FEE)}`;

    ui.checkoutOrderTotal.textContent = formatCurrency(total);

    const shippingSummary = ensureStageSummary(ui.customerDetailsBody.closest('section'), 'customer-details-summary');
    shippingSummary.hidden = !checkoutState.shipping;
    if (checkoutState.shipping) {
      shippingSummary.textContent = `${checkoutState.shipping.fullName} · ${checkoutState.shipping.email} · ${checkoutState.shipping.address}`;
    }

    const paymentSummary = ensureStageSummary(ui.paymentBody.closest('section'), 'payment-summary');
    paymentSummary.hidden = !checkoutState.payment;
    if (checkoutState.payment) {
      paymentSummary.textContent = `Demo card ending in ${checkoutState.payment.lastFour}`;
    }
  }

  function updateCheckoutAvailability() {
    const empty = getCartItemCount() === 0;
    setAriaDisabled(ui.reviewCartButton, empty);
    setAriaDisabled(ui.customerDetailsButton, empty);
    setAriaDisabled(ui.reviewOrderButton, empty);
    setAriaDisabled(ui.paymentButton, empty);
  }

  function applyProductPresentation(options = {}) {
    const moveFocusToGrid = options.moveFocusToGrid === true;
    const sortedFilteredProducts = getFilteredProducts();
    const allCardsById = new Map(ui.productCards.map((card) => [card.getAttribute('data-id'), card]));

    sortedFilteredProducts.forEach((product) => {
      const card = allCardsById.get(product.id);
      if (card) {
        ui.coffeeProductGrid.appendChild(card);
      }
    });

    const filteredIds = sortedFilteredProducts.map((product) => product.id);
    const totalPages = getTotalPages(filteredIds.length);

    if (filterState.paginationActive) {
      filterState.page = Math.min(filterState.page, totalPages);
    }

    const visibleIds = filterState.paginationActive
      ? filteredIds.slice((filterState.page - 1) * PAGE_SIZE, filterState.page * PAGE_SIZE)
      : filteredIds;

    ui.productCards.forEach((card) => {
      const shouldShow = visibleIds.includes(card.getAttribute('data-id'));
      card.hidden = !shouldShow;
      card.setAttribute('aria-hidden', shouldShow ? 'false' : 'true');
    });

    ui.listingResultsCount.textContent = String(visibleIds.length);
    ui.listingResultsCount.dataset.state = visibleIds.length === 0 ? 'empty' : 'default';
    updatePaginationState(filteredIds.length, totalPages);

    if (moveFocusToGrid) {
      ui.coffeeProductGrid.setAttribute('tabindex', '-1');
      ui.coffeeProductGrid.focus();
    }
  }

  function getFilteredProducts() {
    const matchingProducts = records.filter(
      (record) => record.id.startsWith('coffee-') && productMatchesFilters(record)
    );
    const sortedProducts = matchingProducts.slice();

    sortedProducts.sort((left, right) => {
      if (filterState.sort === 'price-asc') {
        return parseCurrency(left.price) - parseCurrency(right.price);
      }
      if (filterState.sort === 'price-desc') {
        return parseCurrency(right.price) - parseCurrency(left.price);
      }
      if (filterState.sort === 'newest') {
        return extractNumericId(right.id) - extractNumericId(left.id);
      }
      return defaultProductOrder.indexOf(left.id) - defaultProductOrder.indexOf(right.id);
    });

    return sortedProducts;
  }

  function productMatchesFilters(product) {
    const searchHaystack = `${product.name} ${product.roastLevel} ${product.tastingNotes}`.toLowerCase();
    const roastMatch = filterState.roast === 'all' || product.roastLevel === filterState.roast;
    const searchMatch = filterState.search === '' || searchHaystack.includes(filterState.search);
    const categoryToken = getCategoryToken(product.category);
    const brandToken = getBrandToken(product.brand);
    const categoryMatch = filterState.category === 'all' || categoryToken === filterState.category;
    const brandMatch = filterState.brand === 'all' || brandToken === filterState.brand;
    const priceMatch = matchesPriceRange(product.price, filterState.price);

    return roastMatch && searchMatch && categoryMatch && brandMatch && priceMatch;
  }

  function matchesPriceRange(priceValue, selectedRange) {
    const price = parseCurrency(priceValue);

    if (selectedRange === 'all') {
      return true;
    }
    if (selectedRange === 'under-20') {
      return price < 20;
    }
    if (selectedRange === '20-25') {
      return price >= 20 && price <= 25;
    }
    if (selectedRange === 'over-25') {
      return price > 25;
    }

    return true;
  }

  function updatePaginationState(totalItems, totalPages) {
    const currentPage = filterState.paginationActive ? filterState.page : 1;
    const hasMultiplePages = totalPages > 1;

    if (currentPage === 1) {
      ui.paginationPage1.setAttribute('aria-current', 'page');
      ui.paginationPage2.removeAttribute('aria-current');
    } else {
      ui.paginationPage1.removeAttribute('aria-current');
      ui.paginationPage2.setAttribute('aria-current', 'page');
    }

    setAriaDisabled(ui.paginationPrev, currentPage <= 1);
    setAriaDisabled(ui.paginationNext, !hasMultiplePages || currentPage >= totalPages);
    setAriaDisabled(ui.paginationPage2, !hasMultiplePages);

    ui.paginationPage1.hidden = totalItems === 0;
    ui.paginationPage2.hidden = totalPages < 2;
  }

  function openCartDrawer(trigger) {
    lastCartTrigger = trigger;
    ui.cartDrawer.hidden = false;
    ui.cartDrawer.setAttribute('aria-hidden', 'false');
    ui.cartDrawer.setAttribute('data-state', 'open');
    ui.headerCartToggle.setAttribute('aria-expanded', 'true');

    if (focusTrapCleanup) {
      focusTrapCleanup();
    }

    focusTrapCleanup = trapFocus(ui.cartDrawer, () => {
      closeCartDrawer({ restoreFocus: true });
    });

    const focusTarget = ui.cartDrawer.querySelector(SELECTORS.miniCartClose);
    if (focusTarget) {
      focusTarget.focus();
    }
  }

  function closeCartDrawer(options = {}) {
    const restoreFocus = options.restoreFocus !== false;

    ui.cartDrawer.hidden = true;
    ui.cartDrawer.setAttribute('aria-hidden', 'true');
    ui.cartDrawer.setAttribute('data-state', 'closed');
    ui.headerCartToggle.setAttribute('aria-expanded', 'false');

    if (focusTrapCleanup) {
      focusTrapCleanup();
      focusTrapCleanup = null;
    }

    if (restoreFocus && lastCartTrigger) {
      lastCartTrigger.focus();
    }
  }

  function openCheckoutFlow(trigger) {
    lastCheckoutTrigger = trigger;
    closeCartDrawer({ restoreFocus: false });
    resetCheckoutView();
    ui.checkoutPanel.hidden = false;
    ui.checkoutConfirmation.hidden = true;
    ui.checkoutConfirmation.setAttribute('data-state', 'hidden');
    setCheckoutChromeVisibility(false);
    updateCheckoutSummary();
    ui.checkoutTitle.setAttribute('tabindex', '-1');
    ui.checkoutTitle.focus();
    announce('Checkout opened.');
  }

  function closeCheckoutFlow(options = {}) {
    const restoreFocus = options.restoreFocus !== false;
    resetCheckoutView();
    ui.checkoutPanel.hidden = true;
    setCheckoutChromeVisibility(true);

    if (restoreFocus && lastCheckoutTrigger) {
      lastCheckoutTrigger.focus();
    }
  }

  function resetCheckoutView() {
    ui.checkoutConfirmation.hidden = true;
    ui.checkoutConfirmation.setAttribute('data-state', 'hidden');
    openCheckoutStage('reviewCart', { focusTarget: null, suppressFocus: true });
    setCheckoutStepState('shipping');
    ui.checkoutTitle.setAttribute('tabindex', '-1');
  }

  function openCheckoutStage(stageName, options = {}) {
    const suppressFocus = options.suppressFocus === true;
    const stageMap = {
      reviewCart: {
        button: ui.reviewCartButton,
        body: ui.reviewCartBody,
        state: 'shipping'
      },
      customerDetails: {
        button: ui.customerDetailsButton,
        body: ui.customerDetailsBody,
        state: 'shipping'
      },
      reviewOrder: {
        button: ui.reviewOrderButton,
        body: ui.reviewOrderBody,
        state: 'review'
      },
      payment: {
        button: ui.paymentButton,
        body: ui.paymentBody,
        state: 'payment'
      }
    };

    Object.values(stageMap).forEach((stage) => {
      stage.button.setAttribute('aria-expanded', 'false');
      stage.body.hidden = true;
    });

    const activeStage = stageMap[stageName];
    activeStage.button.setAttribute('aria-expanded', 'true');
    activeStage.body.hidden = false;
    setCheckoutStepState(activeStage.state);

    if (!suppressFocus) {
      const focusTarget = options.focusTarget || activeStage.button;
      if (focusTarget) {
        focusTarget.focus();
      }
    }
  }

  function setCheckoutStepState(state) {
    ui.checkoutSteps.setAttribute('data-state', state);
  }

  function handleCheckoutSubmit() {
    const fields = [
      ui.checkoutForm.querySelector('#checkout-email'),
      ui.checkoutForm.querySelector('#checkout-full-name'),
      ui.checkoutForm.querySelector('#checkout-address')
    ];

    const valid = fields.every((field) => validateField(field));
    if (!valid) {
      announce('Please complete the required shipping details.');
      const invalidField = fields.find((field) => field.getAttribute('aria-invalid') === 'true');
      if (invalidField) {
        invalidField.focus();
      }
      return;
    }

    checkoutState.shipping = {
      email: fields[0].value.trim(),
      fullName: fields[1].value.trim(),
      address: fields[2].value.trim().replace(/\s+/g, ' ')
    };

    updateCheckoutSummary();
    openCheckoutStage('payment', { focusTarget: ui.paymentForm.querySelector('#payment-card-number') });
    announce('Shipping details saved. Continue to payment.');
  }

  function handlePaymentSubmit() {
    if (getCartItemCount() === 0) {
      announce('Your cart is empty. Add a coffee before placing an order.');
      return;
    }

    const fields = [
      ui.paymentForm.querySelector('#payment-card-number'),
      ui.paymentForm.querySelector('#payment-expiry'),
      ui.paymentForm.querySelector('#payment-cvc')
    ];

    const valid = fields.every((field) => validateField(field));
    if (!valid) {
      announce('Please correct the payment details before placing the demo order.');
      const invalidField = fields.find((field) => field.getAttribute('aria-invalid') === 'true');
      if (invalidField) {
        invalidField.focus();
      }
      return;
    }

    const sanitizedCardNumber = fields[0].value.replace(/\D/g, '');
    checkoutState.payment = {
      lastFour: sanitizedCardNumber.slice(-4)
    };

    updateCheckoutSummary();

    const order = {
      id: `demo-order-${Date.now()}`,
      status: 'submitted',
      submittedAt: new Date().toISOString(),
      items: Array.from(cart.entries()).map(([productId, quantity]) => {
        const product = productById.get(productId);
        return {
          id: product.id,
          name: product.name,
          quantity,
          price: product.price,
          roastLevel: product.roastLevel,
          bagSize: product.bagSize
        };
      }),
      customer: checkoutState.shipping,
      payment: {
        lastFour: checkoutState.payment.lastFour,
        type: 'demo'
      },
      subtotal: formatCurrency(getCartSubtotal()),
      shipping: formatCurrency(getCartItemCount() === 0 ? 0 : SHIPPING_FEE),
      total: formatCurrency(getOrderTotal()),
      message: 'Demo transaction only. No payment was processed.'
    };

    try {
      localStorage.setItem(STORAGE_KEYS.order, JSON.stringify(order));
    } catch (error) {
      announce('Unable to save order details locally, but your demo order confirmation is still shown.');
    }

    renderOrderConfirmation(order);
    cart.clear();
    persistCart();
    renderCart();
    setCheckoutStepState('confirmation');
    announce('Order placed. This is a demo transaction and no payment was processed.');
  }

  function renderOrderConfirmation(order) {
    ui.checkoutConfirmation.hidden = false;
    ui.checkoutConfirmation.setAttribute('data-state', 'visible');

    const existingDynamic = Array.from(ui.checkoutConfirmation.querySelectorAll('[data-confirmation-dynamic]'));
    existingDynamic.forEach((node) => node.remove());

    const summary = document.createElement('p');
    summary.setAttribute('data-confirmation-dynamic', 'true');
    summary.textContent = `Demo order ${order.id} placed for ${order.customer.fullName}.`;

    const total = document.createElement('p');
    total.setAttribute('data-confirmation-dynamic', 'true');
    total.textContent = `Order total: ${order.total}.`;

    const address = document.createElement('p');
    address.setAttribute('data-confirmation-dynamic', 'true');
    address.textContent = `Shipping to: ${order.customer.address}.`;

    const demo = document.createElement('p');
    demo.setAttribute('data-confirmation-dynamic', 'true');
    demo.textContent = 'This is a demo transaction. No payment was processed and no shipment will be created.';

    const continueButton = document.createElement('button');
    continueButton.type = 'button';
    continueButton.setAttribute('data-confirmation-dynamic', 'true');
    continueButton.textContent = 'Continue shopping';
    continueButton.addEventListener('click', () => {
      closeCheckoutFlow({ restoreFocus: true });
    });

    ui.checkoutConfirmation.appendChild(summary);
    ui.checkoutConfirmation.appendChild(total);
    ui.checkoutConfirmation.appendChild(address);
    ui.checkoutConfirmation.appendChild(demo);
    ui.checkoutConfirmation.appendChild(continueButton);
    ui.confirmationTitle.setAttribute('tabindex', '-1');
    ui.confirmationTitle.focus();
  }

  function validateField(field) {
    const value = field.value.trim();
    let message = '';

    if (field.id === 'checkout-email') {
      if (value === '') {
        message = 'Enter your email address.';
      } else if (!field.validity.valid) {
        message = 'Enter a valid email address.';
      }
    }

    if (field.id === 'checkout-full-name') {
      if (value.length < 2) {
        message = 'Enter your full name.';
      }
    }

    if (field.id === 'checkout-address') {
      if (value.length < 10) {
        message = 'Enter a complete shipping address.';
      }
    }

    if (field.id === 'payment-card-number') {
      const digits = value.replace(/\D/g, '');
      if (digits.length < 12 || digits.length > 19) {
        message = 'Enter a valid card number for this demo checkout.';
      }
    }

    if (field.id === 'payment-expiry') {
      if (!/^(0[1-9]|1[0-2])\/[0-9]{2}$/.test(value)) {
        message = 'Enter the expiration date as MM/YY.';
      }
    }

    if (field.id === 'payment-cvc') {
      if (!/^[0-9]{3,4}$/.test(value)) {
        message = 'Enter a 3 or 4 digit security code.';
      }
    }

    setFieldError(field, message);
    return message === '';
  }

  function setFieldError(field, message) {
    const messageId = `${field.id}-error`;
    let errorNode = document.getElementById(messageId);

    if (!errorNode) {
      errorNode = document.createElement('p');
      errorNode.id = messageId;
      errorNode.setAttribute('aria-live', 'polite');
      field.parentElement.appendChild(errorNode);
    }

    if (message) {
      field.setAttribute('aria-invalid', 'true');
      field.setAttribute('aria-describedby', messageId);
      errorNode.textContent = message;
      errorNode.hidden = false;
    } else {
      field.setAttribute('aria-invalid', 'false');
      errorNode.textContent = '';
      errorNode.hidden = true;
      if (field.getAttribute('aria-describedby') === messageId) {
        field.removeAttribute('aria-describedby');
      }
    }
  }

  function ensureStageSummary(section, key) {
    let summary = section.querySelector(`[data-summary-for="${key}"]`);
    if (!summary) {
      summary = document.createElement('p');
      summary.setAttribute('data-summary-for', key);
      const heading = section.querySelector('h3');
      heading.insertAdjacentElement('afterend', summary);
    }
    return summary;
  }

  function setCheckoutChromeVisibility(visible) {
    if (ui.headerPrimaryNav) {
      ui.headerPrimaryNav.hidden = !visible;
    }
    if (ui.headerSearch) {
      ui.headerSearch.hidden = !visible;
    }
  }

  function loadCartFromStorageOrMarkup() {
    const storedCart = loadStoredCart();
    if (storedCart.size > 0) {
      return storedCart;
    }

    const parsedCart = new Map();
    const initialItems = Array.from(document.querySelectorAll(`${SELECTORS.miniCartItems} ${SELECTORS.miniCartItem}`));

    initialItems.forEach((item) => {
      const title = item.querySelector('h4');
      const quantityNode = item.querySelector(SELECTORS.miniCartQuantityValue);
      if (!title || !quantityNode) {
        return;
      }

      const product = productByName.get(title.textContent.trim());
      const quantity = Number.parseInt(quantityNode.textContent.trim(), 10);
      if (product && Number.isFinite(quantity) && quantity > 0) {
        parsedCart.set(product.id, quantity);
      }
    });

    return parsedCart;
  }

  function loadStoredCart() {
    try {
      const raw = localStorage.getItem(STORAGE_KEYS.cart);
      if (!raw) {
        return new Map();
      }

      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return new Map();
      }

      const nextCart = new Map();
      parsed.forEach((entry) => {
        if (
          entry &&
          typeof entry.id === 'string' &&
          productById.has(entry.id) &&
          Number.isFinite(entry.quantity) &&
          entry.quantity > 0
        ) {
          nextCart.set(entry.id, entry.quantity);
        }
      });

      return nextCart;
    } catch (error) {
      return new Map();
    }
  }

  function persistCart() {
    try {
      const serialized = Array.from(cart.entries()).map(([id, quantity]) => ({ id, quantity }));
      localStorage.setItem(STORAGE_KEYS.cart, JSON.stringify(serialized));
    } catch (error) {
      announce('Unable to save the cart locally.');
    }
  }

  function getCartItemCount() {
    return Array.from(cart.values()).reduce((sum, quantity) => sum + quantity, 0);
  }

  function getCartSubtotal() {
    return Array.from(cart.entries()).reduce((sum, [productId, quantity]) => {
      const product = productById.get(productId);
      if (!product) {
        return sum;
      }
      return sum + parseCurrency(product.price) * quantity;
    }, 0);
  }

  function getOrderTotal() {
    const itemCount = getCartItemCount();
    const shipping = itemCount === 0 ? 0 : SHIPPING_FEE;
    return getCartSubtotal() + shipping;
  }

  function createLiveRegion() {
    const region = document.createElement('div');
    region.setAttribute('aria-live', 'polite');
    region.setAttribute('aria-atomic', 'true');
    Object.assign(region.style, {
      position: 'absolute',
      width: '1px',
      height: '1px',
      padding: '0',
      margin: '-1px',
      overflow: 'hidden',
      clip: 'rect(0, 0, 0, 0)',
      whiteSpace: 'nowrap',
      border: '0'
    });
    document.body.appendChild(region);
    return region;
  }

  function announce(message) {
    liveRegion.textContent = '';
    window.setTimeout(() => {
      liveRegion.textContent = message;
    }, 10);
  }

  function showButtonFeedback(button, message) {
    const originalText = button.textContent;
    button.textContent = message;
    button.setAttribute('aria-label', message);
    window.setTimeout(() => {
      button.textContent = originalText;
      button.setAttribute('aria-label', 'Add coffee to cart');
    }, 1200);
  }

  function trapFocus(container, onEscape) {
    const handleKeydown = (event) => {
      if (event.key === 'Escape') {
        onEscape();
        return;
      }

      if (event.key !== 'Tab') {
        return;
      }

      const focusable = getFocusableElements(container);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeydown);
    return () => {
      document.removeEventListener('keydown', handleKeydown);
    };
  }

  function getFocusableElements(container) {
    return Array.from(
      container.querySelectorAll(
        'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
    ).filter((element) => !element.hidden && !isAriaDisabled(element) && isVisible(element));
  }

  function isVisible(element) {
    return Boolean(element.offsetWidth || element.offsetHeight || element.getClientRects().length);
  }

  function setAriaDisabled(element, disabled) {
    element.setAttribute('aria-disabled', disabled ? 'true' : 'false');
  }

  function isAriaDisabled(element) {
    return element.getAttribute('aria-disabled') === 'true';
  }

  function getCategoryToken(category) {
    if (category === 'Single Origin') {
      return 'single-origin';
    }
    if (category === 'Blend') {
      return 'blend';
    }
    return 'decaf';
  }

  function getBrandToken(brand) {
    if (brand === 'Hearthside Roasters') {
      return 'hearthside-roasters';
    }
    if (brand === 'Guest Lot') {
      return 'guest-lot';
    }
    return 'all';
  }

  function parseCurrency(value) {
    return Number.parseFloat(value.replace(/[^0-9.]/g, ''));
  }

  function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(value);
  }

  function extractNumericId(id) {
    return Number.parseInt(id.replace(/[^0-9]/g, ''), 10);
  }

  function getTotalPages(itemCount) {
    return Math.max(1, Math.ceil(itemCount / PAGE_SIZE));
  }

  init();
})();