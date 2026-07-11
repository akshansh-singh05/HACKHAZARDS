const API_BASE = (() => {
  const configuredBase = window.API_BASE_URL || window.__API_BASE_URL__;
  if (configuredBase) {
    return String(configuredBase).replace(/\/$/, "");
  }
  return "/api";
})();
const TOKEN_KEY = "sst_token";

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

const searchInput = document.getElementById("searchInput");
const categoryFilters = document.getElementById("categoryFilters");
const minPriceInput = document.getElementById("minPriceInput");
const maxPriceInput = document.getElementById("maxPriceInput");
const clearPriceFilter = document.getElementById("clearPriceFilter");
const priceFilterError = document.getElementById("priceFilterError");
const minScoreSlider = document.getElementById("minScoreSlider");
const maxScoreSlider = document.getElementById("maxScoreSlider");
const scoreFilterValue = document.getElementById("scoreFilterValue");
const clearScoreFilter = document.getElementById("clearScoreFilter");
const scoreFilterError = document.getElementById("scoreFilterError");
const productsGrid = document.getElementById("productsGrid");
const productTemplate = document.getElementById("productTemplate");
const carbonSaved = document.getElementById("carbonSaved");
const waterSaved = document.getElementById("waterSaved");
const totalCo2 = document.getElementById("totalCo2");
const totalWater = document.getElementById("totalWater");
const purchaseCount = document.getElementById("purchaseCount");
const forecastSummary = document.getElementById("forecastSummary");
const badgesGrid = document.getElementById("badgesGrid");
const badgeCount = document.getElementById("badgeCount");
const badgeTemplate = document.getElementById("badgeTemplate");
const favoritesList = document.getElementById("favoritesList");
const historyList = document.getElementById("historyList");
const historyClearAllButton = document.getElementById("historyClearAllButton");
const exportPurchaseHistoryButton = document.getElementById("exportPurchaseHistoryButton");
const exportMonthlyImpactButton = document.getElementById("exportMonthlyImpactButton");
const exportPdfReportButton = document.getElementById("exportPdfReportButton");
const demoRunButton = document.getElementById("demoRunButton");
const demoStatus = document.getElementById("demoStatus");
const suggestionsList = document.getElementById("searchSuggestions");
const productModal = document.getElementById("productModal");
const modalClose = document.getElementById("modalClose");
const modalName = document.getElementById("modalName");
const modalDescription = document.getElementById("modalDescription");
const modalMetrics = document.getElementById("modalMetrics");
const modalBreakdown = document.getElementById("modalBreakdown");
const modalTip = document.getElementById("modalTip");
const modalRelated = document.getElementById("modalRelated");
const modalBuy = document.getElementById("modalBuy");
const modalAddToCart = document.getElementById("modalAddToCart");
const modalFavorite = document.getElementById("modalFavorite");

const modalRatingSummary = document.getElementById("modalRatingSummary");
const modalReviewsList = document.getElementById("modalReviewsList");
const reviewStarsInput = document.getElementById("reviewStarsInput");
const reviewTextInput = document.getElementById("reviewTextInput");
const reviewFormError = document.getElementById("reviewFormError");
const reviewSubmitButton = document.getElementById("reviewSubmitButton");
const reviewDeleteButton = document.getElementById("reviewDeleteButton");

const cartsList = document.getElementById("cartsList");
const cartCount = document.getElementById("cartCount");
const cartTotalItems = document.getElementById("cartTotalItems");
const cartTotalPrice = document.getElementById("cartTotalPrice");
const cartBuyNowButton = document.getElementById("cartBuyNowButton");

const authOverlay = document.getElementById("authOverlay");
const authForm = document.getElementById("authForm");
const authTitle = document.getElementById("authTitle");
const authError = document.getElementById("authError");
const authNameField = document.getElementById("authNameField");
const authName = document.getElementById("authName");
const authEmail = document.getElementById("authEmail");
const authPassword = document.getElementById("authPassword");
const authSubmit = document.getElementById("authSubmit");
const authToggle = document.getElementById("authToggle");
const appShell = document.getElementById("appShell");
const accountGreeting = document.getElementById("accountGreeting");
const logoutButton = document.getElementById("logoutButton");

let authMode = "login"; // or "signup"

let activeCategory = "all";
let dashboardChart;
let forecastChart;
let favoritesSet = new Set();

// --- Purchase History display filter -----------------------------------
//
// "Remove" / "Clear All" only hide rows from this view. They never call the
// API, never touch purchase records, and never affect totals, badges, or
// charts (those are all computed server-side from the real purchases table
// and refetched independently). Hidden ids are namespaced per user and kept
// in localStorage purely so the display choice survives a page reload.
let currentUserId = null;
let latestHistory = [];
let hiddenHistoryIds = new Set();

function hiddenHistoryStorageKey() {
  return `sst_hidden_history_${currentUserId ?? "guest"}`;
}

function loadHiddenHistoryIds() {
  try {
    const raw = localStorage.getItem(hiddenHistoryStorageKey());
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch (error) {
    return new Set();
  }
}

function saveHiddenHistoryIds() {
  try {
    localStorage.setItem(hiddenHistoryStorageKey(), JSON.stringify([...hiddenHistoryIds]));
  } catch (error) {
    // Storage may be unavailable (private mode, quota); this is a display-only
    // convenience, so failing silently is fine.
  }
}

function formatNumber(value, suffix) {
  return `${Number(value).toFixed(1)} ${suffix}`;
}

function formatPrice(value) {
  return `$${Number(value).toFixed(2)}`;
}

// --- Star rating helpers ----------------------------------------------------

function starGlyphs(value) {
  const rounded = Math.round(Number(value) || 0);
  const filled = Math.max(0, Math.min(5, rounded));
  return "★".repeat(filled) + "☆".repeat(5 - filled);
}

function formatRatingSummary(averageRating, reviewCount) {
  if (!reviewCount) {
    return `${starGlyphs(0)} <span class="rating-empty">No reviews yet</span>`;
  }
  const count = Number(reviewCount);
  return `${starGlyphs(averageRating)} <span class="rating-value">${Number(averageRating).toFixed(1)}</span> <span class="rating-count">(${count} review${count === 1 ? "" : "s"})</span>`;
}

function formatReviewDate(isoString) {
  if (!isoString) return "";
  return isoString.slice(0, 10);
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

// Tracks the star value currently selected in the review form (0 = none picked yet).
let selectedReviewRating = 0;

function renderStarInput(selected) {
  if (!reviewStarsInput) return;
  selectedReviewRating = selected;
  reviewStarsInput.innerHTML = "";
  for (let value = 1; value <= 5; value += 1) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "star-button";
    btn.dataset.value = String(value);
    btn.setAttribute("role", "radio");
    btn.setAttribute("aria-checked", value === selected ? "true" : "false");
    btn.setAttribute("aria-label", `${value} star${value === 1 ? "" : "s"}`);
    btn.textContent = value <= selected ? "★" : "☆";
    btn.addEventListener("click", () => renderStarInput(value));
    reviewStarsInput.appendChild(btn);
  }
}

// Populates the reviews list + review form for the product currently open in the modal.
function renderReviewsSection(prod, productId) {
  if (modalRatingSummary) {
    modalRatingSummary.innerHTML = formatRatingSummary(prod.average_rating || 0, prod.review_count || 0);
  }

  if (modalReviewsList) {
    const reviews = Array.isArray(prod.reviews) ? prod.reviews : [];
    if (reviews.length === 0) {
      modalReviewsList.innerHTML = '<p class="empty-state">No reviews yet. Be the first to share your thoughts.</p>';
    } else {
      modalReviewsList.innerHTML = reviews
        .map(
          (review) => `
            <div class="review-item">
              <div class="review-item-head">
                <strong>${escapeHtml(review.user_name)}${review.user_id === currentUserId ? ' <span class="review-you-tag">(You)</span>' : ""}</strong>
                <span class="review-stars">${starGlyphs(review.rating)}</span>
              </div>
              ${review.review_text ? `<p class="review-text">${escapeHtml(review.review_text)}</p>` : ""}
              <div class="review-meta">${formatReviewDate(review.updated_at || review.created_at)}</div>
            </div>
          `
        )
        .join("");
    }
  }

  const userReview = prod.user_review;
  renderStarInput(userReview ? userReview.rating : 0);
  if (reviewTextInput) {
    reviewTextInput.value = userReview ? userReview.review_text || "" : "";
  }
  if (reviewFormError) {
    reviewFormError.textContent = "";
  }
  if (reviewDeleteButton) {
    reviewDeleteButton.hidden = !userReview;
  }
  if (reviewSubmitButton) {
    reviewSubmitButton.textContent = userReview ? "Update review" : "Submit review";

    reviewSubmitButton.onclick = async () => {
      if (!selectedReviewRating) {
        if (reviewFormError) reviewFormError.textContent = "Please select a star rating.";
        return;
      }
      reviewSubmitButton.disabled = true;
      const originalLabel = reviewSubmitButton.textContent;
      reviewSubmitButton.textContent = "Saving…";
      try {
        await fetchJSON(`${API_BASE}/products/${productId}/reviews`, {
          method: "POST",
          body: JSON.stringify({
            rating: selectedReviewRating,
            review_text: reviewTextInput ? reviewTextInput.value.trim() : "",
          }),
        });
        if (reviewFormError) reviewFormError.textContent = "";
        await loadProductDetail(productId);
        await loadProducts();
      } catch (err) {
        if (reviewFormError) reviewFormError.textContent = err.message;
      } finally {
        reviewSubmitButton.disabled = false;
        reviewSubmitButton.textContent = originalLabel;
      }
    };
  }

  if (reviewDeleteButton) {
    reviewDeleteButton.onclick = async () => {
      reviewDeleteButton.disabled = true;
      try {
        await fetchJSON(`${API_BASE}/products/${productId}/reviews`, { method: "DELETE" });
        await loadProductDetail(productId);
        await loadProducts();
      } catch (err) {
        if (reviewFormError) reviewFormError.textContent = err.message;
      } finally {
        reviewDeleteButton.disabled = false;
      }
    };
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function setDemoStatus(message) {
  if (demoStatus) {
    demoStatus.textContent = message;
  }
}

async function fetchJSON(url, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    clearToken();
    showAuthOverlay("Your session expired. Please log in again.");
    throw new Error("Session expired");
  }
  if (!response.ok) {
    let message = "Request failed";
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      message = (await response.text()) || message;
    }
    throw new Error(message);
  }
  return response.json();
}

async function downloadFile(url, fallbackFilename) {
  const token = getToken();
  const headers = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(url, { headers });
  if (response.status === 401) {
    clearToken();
    showAuthOverlay("Your session expired. Please log in again.");
    throw new Error("Session expired");
  }
  if (!response.ok) {
    let message = "Export failed";
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      message = (await response.text()) || message;
    }
    throw new Error(message);
  }

  // Prefer the filename the server suggests via Content-Disposition, falling
  // back to a sensible default if it's missing for any reason.
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : fallbackFilename;

  const blob = await response.blob();
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}

function renderFilters(categories) {
  const items = ["all", ...categories];
  categoryFilters.innerHTML = items
    .map(
      (category) => `
        <button class="filter-button ${category === activeCategory ? "active" : ""}" data-category="${category}">
          ${category === "all" ? "All" : category}
        </button>
      `
    )
    .join("");

  categoryFilters.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      activeCategory = button.dataset.category;
      renderFilters(categories);
      loadProducts();
    });
  });
}

function renderProducts(products) {
  productsGrid.innerHTML = "";
  if (products.length === 0) {
    productsGrid.innerHTML = "<p class='empty-state'>No products match that search. Try clearing the filter or searching another item.</p>";
    return;
  }

  products.forEach((product) => {
    const card = productTemplate.content.cloneNode(true);
    card.querySelector(".category").textContent = product.category;
    card.querySelector(".score").textContent = `Score ${product.sustainability_score}/100`;
    card.querySelector(".name").textContent = product.name;
    const cardRating = card.querySelector(".card-rating");
    if (cardRating) {
      cardRating.innerHTML = formatRatingSummary(product.average_rating || 0, product.review_count || 0);
    }
    card.querySelector(".description").textContent = product.description;
    card.querySelectorAll(".metric")[0].textContent = `CO2: ${formatNumber(product.carbon_kg, "kg")}`;
    card.querySelectorAll(".metric")[1].textContent = `Water: ${formatNumber(product.water_liters, "L")}`;
    const priceMetric = card.querySelectorAll(".metric")[2];
    if (priceMetric) {
      priceMetric.textContent = `Price: ${formatPrice(product.price)}`;
    }

    const article = card.querySelector(".product-card");
    if (article) {
      article.dataset.productId = product.id;
    }

    const favBtn = card.querySelector(".favorite-button");
    const cartBtn = card.querySelector(".cart-button");
    const button = card.querySelector(".buy-button");
    if (favBtn) {
      if (favoritesSet.has(String(product.id))) {
        favBtn.classList.add("active");
        favBtn.textContent = "♥";
      }
      favBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          if (favoritesSet.has(String(product.id))) {
            await fetchJSON(`${API_BASE}/favorites`, {
              method: "DELETE",
              body: JSON.stringify({ product_id: product.id }),
            });
            favoritesSet.delete(String(product.id));
            favBtn.classList.remove("active");
            favBtn.textContent = "♡";
          } else {
            await fetchJSON(`${API_BASE}/favorites`, {
              method: "POST",
              body: JSON.stringify({ product_id: product.id }),
            });
            favoritesSet.add(String(product.id));
            favBtn.classList.add("active");
            favBtn.textContent = "♥";
          }
        } catch (err) {
          alert(`Favorite error: ${err.message}`);
        }
      });
    }
    if (cartBtn) {
      cartBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        await addToCart(product.id, cartBtn);
      });
    }
    button.addEventListener("click", async (e) => {
      e.stopPropagation();
      button.disabled = true;
      button.textContent = "Purchased";
      try {
        await fetchJSON(`${API_BASE}/purchases`, {
          method: "POST",
          body: JSON.stringify({ product_id: product.id, quantity: 1 }),
        });
        await loadDashboard();
      } catch (error) {
        button.disabled = false;
        button.textContent = "Buy Now";
        alert(`Could not complete purchase: ${error.message}`);
      }
    });

    productsGrid.appendChild(card);
  });
}

// --- Cart logic -----------------------------------------------------------
// Add to Cart only ever touches the Carts section (/api/cart). It never
// creates a purchase, so Purchase History is untouched until a "Buy Now"
// action (either on a product card, the product modal, or the Carts
// section itself) explicitly checks the cart out.

async function addToCart(productId, triggerButton) {
  const originalLabel = triggerButton ? triggerButton.textContent : null;
  if (triggerButton) {
    triggerButton.disabled = true;
    triggerButton.textContent = "Added!";
  }
  try {
    const cart = await fetchJSON(`${API_BASE}/cart`, {
      method: "POST",
      body: JSON.stringify({ product_id: productId, quantity: 1 }),
    });
    renderCart(cart);
  } catch (error) {
    alert(`Could not add to cart: ${error.message}`);
  } finally {
    if (triggerButton) {
      setTimeout(() => {
        triggerButton.disabled = false;
        triggerButton.textContent = originalLabel;
      }, 700);
    }
  }
}

function renderCart(cart) {
  const items = Array.isArray(cart?.items) ? cart.items : [];
  const totalItems = cart?.total_items ?? 0;
  const totalPrice = cart?.total_price ?? 0;

  if (cartCount) {
    cartCount.textContent = `${totalItems} item${totalItems === 1 ? "" : "s"}`;
  }
  if (cartTotalItems) {
    cartTotalItems.textContent = String(totalItems);
  }
  if (cartTotalPrice) {
    cartTotalPrice.textContent = formatPrice(totalPrice);
  }
  if (cartBuyNowButton) {
    cartBuyNowButton.disabled = items.length === 0;
  }

  if (!cartsList) return;

  if (items.length === 0) {
    cartsList.innerHTML = '<p class="empty-state">Your cart is empty. Use "Add to Cart" on a product to save it here.</p>';
    return;
  }

  cartsList.innerHTML = items
    .map(
      (item) => `
        <div class="account-item">
          <div>
            <strong>${item.name}</strong>
            <div class="account-meta">Qty ${item.quantity} • ${formatPrice(item.price)} each • Total ${formatPrice(item.total_price)}</div>
            <div class="account-meta">${item.category}</div>
          </div>
          <button class="link-button" data-product-id="${item.product_id}" data-action="remove">Remove</button>
        </div>
      `
    )
    .join("");

  cartsList.querySelectorAll("[data-action='remove']").forEach((button) => {
    button.addEventListener("click", async () => {
      const productId = Number(button.dataset.productId);
      if (!productId) return;
      try {
        const cart = await fetchJSON(`${API_BASE}/cart`, {
          method: "DELETE",
          body: JSON.stringify({ product_id: productId }),
        });
        renderCart(cart);
      } catch (error) {
        alert(`Could not remove item: ${error.message}`);
      }
    });
  });
}

async function loadCart() {
  const cart = await fetchJSON(`${API_BASE}/cart`);
  renderCart(cart);
  return cart;
}

async function checkoutCart() {
  if (!cartBuyNowButton) return;
  cartBuyNowButton.disabled = true;
  const originalLabel = cartBuyNowButton.textContent;
  cartBuyNowButton.textContent = "Processing…";
  try {
    await fetchJSON(`${API_BASE}/cart/checkout`, { method: "POST" });
    // Buy Now moves cart items into Purchase History: refresh both.
    await Promise.all([loadCart(), loadDashboard()]);
  } catch (error) {
    alert(`Checkout failed: ${error.message}`);
  } finally {
    cartBuyNowButton.textContent = originalLabel;
  }
}

cartBuyNowButton?.addEventListener("click", checkoutCart);

function renderFavorites(favorites) {
  if (!favoritesList) return;
  favoritesSet = new Set(Array.isArray(favorites) ? favorites.map((item) => String(item.id)) : []);
  if (!Array.isArray(favorites) || favorites.length === 0) {
    favoritesList.innerHTML = '<p class="empty-state">No favorites yet. Tap the heart on a product to save it here.</p>';
    return;
  }

  favoritesList.innerHTML = favorites
    .map(
      (item) => `
        <div class="account-item">
          <div>
            <strong>${item.name}</strong>
            <div class="account-meta">${item.category} • ${formatPrice(item.price)} • Score ${item.sustainability_score}/100</div>
          </div>
          <button class="link-button" data-product-id="${item.id}">View</button>
        </div>
      `
    )
    .join("");

  favoritesList.querySelectorAll(".link-button").forEach((button) => {
    button.addEventListener("click", () => {
      const productId = Number(button.dataset.productId);
      if (productId) loadProductDetail(productId);
    });
  });
}

function renderHistory(history) {
  if (!historyList) return;
  latestHistory = Array.isArray(history) ? history : [];
  const visible = latestHistory.filter((item) => !hiddenHistoryIds.has(item.purchase_id));

  if (historyClearAllButton) {
    historyClearAllButton.disabled = visible.length === 0;
  }

  if (visible.length === 0) {
    historyList.innerHTML =
      latestHistory.length === 0
        ? '<p class="empty-state">No purchase history yet. Add a product to see it here.</p>'
        : '<p class="empty-state">Purchase history view is cleared. Your saved stats, badges, and charts are unaffected.</p>';
    return;
  }

  historyList.innerHTML = visible
    .map(
      (item) => `
        <div class="account-item">
          <div>
            <strong>${item.name}</strong>
            <div class="account-meta">Qty ${item.quantity} • ${formatPrice(item.price)} each • Total ${formatPrice(item.total_price)}</div>
            <div class="account-meta">${item.category} • ${item.purchased_at.slice(0, 10)}</div>
          </div>
          <div class="account-item-actions">
            <button class="link-button" data-product-id="${item.product_id}">View</button>
            <button class="remove-button" data-purchase-id="${item.purchase_id}" title="Remove from this list only">Remove</button>
          </div>
        </div>
      `
    )
    .join("");

  historyList.querySelectorAll(".link-button").forEach((button) => {
    button.addEventListener("click", () => {
      const productId = Number(button.dataset.productId);
      if (productId) loadProductDetail(productId);
    });
  });

  historyList.querySelectorAll(".remove-button").forEach((button) => {
    button.addEventListener("click", () => {
      const purchaseId = Number(button.dataset.purchaseId);
      if (!purchaseId) return;
      hiddenHistoryIds.add(purchaseId);
      saveHiddenHistoryIds();
      renderHistory(latestHistory);
    });
  });
}

historyClearAllButton?.addEventListener("click", () => {
  latestHistory.forEach((item) => hiddenHistoryIds.add(item.purchase_id));
  saveHiddenHistoryIds();
  renderHistory(latestHistory);
});

exportPurchaseHistoryButton?.addEventListener("click", async () => {
  exportPurchaseHistoryButton.disabled = true;
  const originalLabel = exportPurchaseHistoryButton.textContent;
  exportPurchaseHistoryButton.textContent = "Exporting…";
  try {
    await downloadFile(`${API_BASE}/export/purchase-history.csv`, "purchase_history.csv");
  } catch (error) {
    alert(error.message || "Could not export purchase history.");
  } finally {
    exportPurchaseHistoryButton.disabled = false;
    exportPurchaseHistoryButton.textContent = originalLabel;
  }
});

exportMonthlyImpactButton?.addEventListener("click", async () => {
  exportMonthlyImpactButton.disabled = true;
  const originalLabel = exportMonthlyImpactButton.textContent;
  exportMonthlyImpactButton.textContent = "Exporting…";
  try {
    await downloadFile(`${API_BASE}/export/monthly-impact.csv`, "monthly_sustainability_impact.csv");
  } catch (error) {
    alert(error.message || "Could not export monthly impact data.");
  } finally {
    exportMonthlyImpactButton.disabled = false;
    exportMonthlyImpactButton.textContent = originalLabel;
  }
});

exportPdfReportButton?.addEventListener("click", async () => {
  exportPdfReportButton.disabled = true;
  const originalLabel = exportPdfReportButton.textContent;
  exportPdfReportButton.textContent = "Generating…";
  try {
    await downloadFile(`${API_BASE}/export/sustainability-report.pdf`, "sustainability_report.pdf");
  } catch (error) {
    alert(error.message || "Could not generate the sustainability report.");
  } finally {
    exportPdfReportButton.disabled = false;
    exportPdfReportButton.textContent = originalLabel;
  }
});

function renderBadges(badges, summary) {
  if (badgeCount) {
    const earned = summary?.earned ?? badges.filter((b) => b.earned).length;
    const total = summary?.total ?? badges.length;
    badgeCount.textContent = `${earned} / ${total} earned`;
  }

  if (!badgesGrid) return;

  if (!Array.isArray(badges) || badges.length === 0) {
    badgesGrid.innerHTML = '<p class="empty-state">Badges will appear here as you shop greener.</p>';
    return;
  }

  badgesGrid.innerHTML = "";
  // Show earned badges first, then locked, each sorted by threshold within its category.
  const sorted = [...badges].sort((a, b) => {
    if (a.earned !== b.earned) return a.earned ? -1 : 1;
    if (a.category !== b.category) return a.category.localeCompare(b.category);
    return a.threshold - b.threshold;
  });

  sorted.forEach((badge) => {
    const node = badgeTemplate.content.cloneNode(true);
    const card = node.querySelector(".badge-card");
    card.classList.add(badge.earned ? "earned" : "locked");
    card.title = badge.earned
      ? `Earned: ${badge.current_value} / ${badge.threshold} ${badge.unit}`
      : `${badge.current_value} / ${badge.threshold} ${badge.unit} (${badge.progress}%)`;

    node.querySelector(".badge-icon").textContent = badge.icon;
    node.querySelector(".badge-name").textContent = badge.name;
    node.querySelector(".badge-description").textContent = badge.description;
    node.querySelector(".badge-progress-fill").style.width = `${Math.min(100, badge.progress)}%`;
    node.querySelector(".badge-progress-label").textContent = badge.earned
      ? `Unlocked • ${badge.current_value} ${badge.unit}`
      : `${badge.current_value} / ${badge.threshold} ${badge.unit}`;
    node.querySelector(".badge-status").textContent = badge.earned ? "✅" : "🔒";

    badgesGrid.appendChild(node);
  });
}

// Delegated click handler: only used to open the product detail modal when a
// card is clicked somewhere other than one of its action buttons. Actual
// button behavior (favorite / add to cart / buy now) is wired directly on
// each button in renderProducts, so it isn't duplicated here.
productsGrid.addEventListener("click", async (ev) => {
  const isActionButton = ev.target.closest?.(".buy-button, .favorite-button, .cart-button");
  if (isActionButton) return; // handled by the button's own listener

  const article = ev.target.closest?.(".product-card");
  if (article) {
    const pid = article.dataset?.productId;
    if (pid) {
      await loadProductDetail(Number(pid));
    }
  }
});

// product detail modal helpers
async function loadProductDetail(productId) {
  try {
    const prod = await fetchJSON(`${API_BASE}/products/${productId}`);
    modalName.textContent = prod.name;
    modalDescription.textContent = prod.description;
    modalMetrics.innerHTML = `CO2: ${formatNumber(prod.carbon_kg, 'kg')} • Water: ${formatNumber(prod.water_liters, 'L')}`;
    const co2Saved = prod.details?.impact_breakdown?.co2_saved_vs_category_baseline ?? 0;
    const waterSaved = prod.details?.impact_breakdown?.water_saved_vs_category_baseline ?? 0;
    modalBreakdown.textContent = `Impact vs typical ${prod.category} item: saves ${co2Saved.toFixed(2)} kg CO2 and ${waterSaved.toFixed(2)} L water.`;
    modalTip.textContent = `Tip: ${prod.details?.tip || "Choose lower-impact options when possible."}`;

    if (Array.isArray(prod.details?.related_products) && modalRelated) {
      modalRelated.innerHTML = prod.details.related_products
        .map(
          (rel) =>
            `<li><button class="related-link" data-product-id="${rel.id}">${rel.name}</button> (${formatNumber(rel.carbon_kg, 'kg CO2')}, ${formatNumber(rel.water_liters, 'L')})</li>`
        )
        .join("");
    } else if (modalRelated) {
      modalRelated.innerHTML = "<li>No related products found.</li>";
    }

    renderReviewsSection(prod, productId);

    modalBuy.onclick = async () => {
      try {
        await fetchJSON(`${API_BASE}/purchases`, { method: 'POST', body: JSON.stringify({ product_id: productId, quantity: 1 }) });
        await loadDashboard();
        hideModal();
      } catch (err) {
        alert(`Could not complete purchase: ${err.message}`);
      }
    };
    if (modalAddToCart) {
      modalAddToCart.onclick = async () => {
        await addToCart(productId, modalAddToCart);
      };
    }
    modalFavorite.onclick = async () => {
      try {
        if (favoritesSet.has(String(productId))) {
          await fetchJSON(`${API_BASE}/favorites`, { method: 'DELETE', body: JSON.stringify({ product_id: productId }) });
          favoritesSet.delete(String(productId));
          modalFavorite.textContent = '♡ Favorite';
        } else {
          await fetchJSON(`${API_BASE}/favorites`, { method: 'POST', body: JSON.stringify({ product_id: productId }) });
          favoritesSet.add(String(productId));
          modalFavorite.textContent = '♥ Favorited';
        }
        await loadProducts();
      } catch (err) {
        alert(`Favorite error: ${err.message}`);
      }
    };
    showModal();

    modalRelated?.querySelectorAll(".related-link").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nextId = Number(btn.dataset.productId);
        if (nextId) {
          loadProductDetail(nextId);
        }
      });
    });
  } catch (err) {
    alert(`Could not load product: ${err.message}`);
  }
}

function showModal() {
  if (!productModal) return;
  productModal.setAttribute('aria-hidden', 'false');
}

function hideModal() {
  if (!productModal) return;
  productModal.setAttribute('aria-hidden', 'true');
}

modalClose?.addEventListener('click', hideModal);
productModal?.addEventListener('click', (ev) => {
  if (ev.target === productModal) hideModal();
});

function drawDashboardChart(months, co2Values, waterValues) {
  const ctx = document.getElementById("dashboardChart");
  if (dashboardChart) {
    dashboardChart.destroy();
  }
  dashboardChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: months,
      datasets: [
        {
          label: "CO2 (kg)",
          data: co2Values,
          backgroundColor: "rgba(47, 125, 90, 0.78)",
        },
        {
          label: "Water (L)",
          data: waterValues,
          backgroundColor: "rgba(157, 107, 63, 0.65)",
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "bottom" } },
      scales: { y: { beginAtZero: true } },
    },
  });
}

function drawForecastChart(months, co2Values, waterValues) {
  const ctx = document.getElementById("forecastChart");
  if (forecastChart) {
    forecastChart.destroy();
  }
  forecastChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: months,
      datasets: [
        {
          label: "Predicted CO2 (kg)",
          data: co2Values,
          borderColor: "rgba(47, 125, 90, 1)",
          backgroundColor: "rgba(47, 125, 90, 0.1)",
          tension: 0.35,
        },
        {
          label: "Predicted water (L)",
          data: waterValues,
          borderColor: "rgba(157, 107, 63, 1)",
          backgroundColor: "rgba(157, 107, 63, 0.1)",
          tension: 0.35,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "bottom" } },
    },
  });
}

function getPriceFilterValues() {
  const minRaw = minPriceInput ? minPriceInput.value.trim() : "";
  const maxRaw = maxPriceInput ? maxPriceInput.value.trim() : "";
  const minPrice = minRaw === "" ? null : Number(minRaw);
  const maxPrice = maxRaw === "" ? null : Number(maxRaw);
  return { minRaw, maxRaw, minPrice, maxPrice };
}

function validatePriceFilter({ minRaw, maxRaw, minPrice, maxPrice }) {
  if (minRaw !== "" && (Number.isNaN(minPrice) || minPrice < 0)) {
    return "Min price must be a number 0 or greater.";
  }
  if (maxRaw !== "" && (Number.isNaN(maxPrice) || maxPrice < 0)) {
    return "Max price must be a number 0 or greater.";
  }
  if (minPrice !== null && maxPrice !== null && minPrice > maxPrice) {
    return "Min price must not be greater than max price.";
  }
  return "";
}

function updateClearPriceFilterVisibility() {
  if (!clearPriceFilter) return;
  const hasValue = (minPriceInput && minPriceInput.value.trim() !== "") || (maxPriceInput && maxPriceInput.value.trim() !== "");
  clearPriceFilter.hidden = !hasValue;
}

// --- Sustainability score slider filter -------------------------------------

const SCORE_MIN = 1;
const SCORE_MAX = 100;

function getScoreFilterValues() {
  const minScore = minScoreSlider ? Number(minScoreSlider.value) : SCORE_MIN;
  const maxScore = maxScoreSlider ? Number(maxScoreSlider.value) : SCORE_MAX;
  return { minScore, maxScore };
}

function isScoreFilterActive({ minScore, maxScore }) {
  return minScore > SCORE_MIN || maxScore < SCORE_MAX;
}

function updateScoreFilterDisplay() {
  const { minScore, maxScore } = getScoreFilterValues();
  if (scoreFilterValue) {
    scoreFilterValue.textContent = `${minScore} – ${maxScore}`;
  }
  if (clearScoreFilter) {
    clearScoreFilter.hidden = !isScoreFilterActive({ minScore, maxScore });
  }
}

// Two independent sliders can't cross each other, so nudge the other handle
// along whenever the user drags one past it — this keeps min <= max without
// needing a single fused dual-handle control.
function clampScoreSliders(source) {
  if (!minScoreSlider || !maxScoreSlider) return;
  const minVal = Number(minScoreSlider.value);
  const maxVal = Number(maxScoreSlider.value);
  if (minVal > maxVal) {
    if (source === "min") {
      maxScoreSlider.value = String(minVal);
    } else {
      minScoreSlider.value = String(maxVal);
    }
  }
}

async function loadProducts() {
  const query = searchInput.value.trim();
  const priceValues = getPriceFilterValues();
  const validationError = validatePriceFilter(priceValues);

  updateClearPriceFilterVisibility();
  updateScoreFilterDisplay();

  if (priceFilterError) {
    priceFilterError.textContent = validationError;
  }
  if (validationError) {
    // Don't hit the API with an invalid range; let the user fix it first.
    return;
  }

  const { minScore, maxScore } = getScoreFilterValues();
  const scoreActive = isScoreFilterActive({ minScore, maxScore });

  const params = new URLSearchParams();
  if (query) params.set("query", query);
  if (activeCategory !== "all") params.set("category", activeCategory);
  if (priceValues.minPrice !== null) params.set("min_price", String(priceValues.minPrice));
  if (priceValues.maxPrice !== null) params.set("max_price", String(priceValues.maxPrice));
  if (scoreActive) {
    params.set("min_sustainability_score", String(minScore));
    params.set("max_sustainability_score", String(maxScore));
  }

  try {
    const products = await fetchJSON(`${API_BASE}/products?${params.toString()}`);
    renderProducts(products);
    if (scoreFilterError) scoreFilterError.textContent = "";
  } catch (error) {
    if (priceFilterError) {
      priceFilterError.textContent = error.message;
    }
    if (scoreFilterError) {
      scoreFilterError.textContent = error.message;
    }
  }
}

async function loadDashboard() {
  const dashboard = await fetchJSON(`${API_BASE}/dashboard`);
  const predictions = await fetchJSON(`${API_BASE}/predictions`);
  const favorites = Array.isArray(dashboard.favorites) ? dashboard.favorites : [];
  const history = Array.isArray(dashboard.history) ? dashboard.history : [];

  carbonSaved.textContent = formatNumber(dashboard.totals.co2_saved, "kg");
  waterSaved.textContent = formatNumber(dashboard.totals.water_saved, "L");
  totalCo2.textContent = formatNumber(dashboard.totals.carbon_kg, "kg");
  totalWater.textContent = formatNumber(dashboard.totals.water_liters, "L");
  purchaseCount.textContent = String(dashboard.purchase_count);

  const months = dashboard.monthly.map((item) => item.month);
  const co2Values = dashboard.monthly.map((item) => item.co2);
  const waterValues = dashboard.monthly.map((item) => item.water);
  drawDashboardChart(months.length ? months : ["No data"], co2Values.length ? co2Values : [0], waterValues.length ? waterValues : [0]);

  renderFavorites(favorites);
  renderHistory(history);
  renderBadges(Array.isArray(dashboard.badges) ? dashboard.badges : [], dashboard.badge_summary);

  // Beginner-friendly forecast block.
  const friendly = predictions.friendly || null;
  forecastSummary.innerHTML = `
    <div style="font-size:1.05rem;font-weight:600">Next month</div>
    <div style="display:flex;gap:1.5rem;align-items:baseline;margin-top:0.3rem">
      <div style="font-size:1.35rem;color:#2f7d5a">${formatNumber(predictions.next_month.co2, 'kg CO2')}</div>
      <div style="font-size:1.35rem;color:#9d6b3f">${formatNumber(predictions.next_month.water, 'L')}</div>
    </div>
    <div style="margin-top:0.5rem;color:#444">${friendly ? friendly.summary : predictions.insight}</div>
    ${friendly ? `
      <div style="margin-top:0.6rem;display:flex;gap:1rem;flex-wrap:wrap">
        <div style="background:#eef6ef;padding:6px 8px;border-radius:6px">CO2: ${friendly.co2.next_month} kg • ${friendly.co2.change_pct}%</div>
        <div style="background:#f7efe6;padding:6px 8px;border-radius:6px">Water: ${friendly.water.next_month} L • ${friendly.water.change_pct}%</div>
        <div style="background:#fff7e6;padding:6px 8px;border-radius:6px">Confidence: CO2 ${friendly.co2.confidence}, Water ${friendly.water.confidence}</div>
      </div>
      <div style="margin-top:0.6rem"><strong>Quick tips:</strong> ${friendly.quick_tips[0]} ${friendly.quick_tips[1] ? '• ' + friendly.quick_tips[1] : ''}</div>
      <button id="explainBtn" style="margin-top:0.5rem;background:transparent;border:0;color:#0b66d0;cursor:pointer;padding:0">What does this mean?</button>
      <div id="explainBox" style="display:none;margin-top:0.5rem;color:#333;background:#f9f9f9;padding:8px;border-radius:6px">
        <div><strong>In plain words:</strong> The numbers show our best guess for next month based on what you bought recently. The confidence tells you how sure the model is — <em>High</em> means fairly certain, <em>Low</em> means the range could be wide.</div>
        <div style="margin-top:6px">Use the quick tips to try 1 change this month (e.g., pick one reusable item) and check how the forecast updates.</div>
      </div>
      ${predictions.quarter_projection && predictions.quarter_projection[0] ? `
        <div style="margin-top:0.6rem;color:#666">95% likely range (next month): CO2 ${predictions.quarter_projection[0].co2_ci[0]}–${predictions.quarter_projection[0].co2_ci[1]} kg, Water ${predictions.quarter_projection[0].water_ci[0]}–${predictions.quarter_projection[0].water_ci[1]} L</div>
      ` : ''}
    ` : `
      <div style="margin-top:0.5rem">${predictions.insight}</div>
    `}
  `;

  // Attach explainer toggle
  const explainBtn = document.getElementById('explainBtn');
  const explainBox = document.getElementById('explainBox');
  if (explainBtn && explainBox) {
    explainBtn.addEventListener('click', () => {
      explainBox.style.display = explainBox.style.display === 'none' ? 'block' : 'none';
    });
  }

  drawForecastChart(
    predictions.quarter_projection.map((item) => item.month),
    predictions.quarter_projection.map((item) => item.co2),
    predictions.quarter_projection.map((item) => item.water)
  );
}

async function runGuidedDemo() {
  if (!demoRunButton) {
    return;
  }

  demoRunButton.disabled = true;
  setDemoStatus("Step 1 of 4: showing greener shopping choices.");

  searchInput.value = "coffee";
  searchInput.dispatchEvent(new Event("input", { bubbles: true }));
  await sleep(650);

  setDemoStatus("Step 2 of 4: focusing on the food category.");
  activeCategory = "food";
  const categories = await fetchJSON(`${API_BASE}/categories`);
  renderFilters(categories);
  await loadProducts();
  await sleep(650);

  setDemoStatus("Step 3 of 4: adding a product to the history.");
  const firstBuyButton = document.querySelector(".product-card .buy-button");
  if (firstBuyButton) {
    firstBuyButton.click();
    await sleep(850);
  }

  setDemoStatus("Step 4 of 4: moving to the dashboard and forecast.");
  document.getElementById("forecastSummary")?.scrollIntoView({ behavior: "smooth", block: "center" });
  await sleep(700);

  setDemoStatus("Demo complete. The dashboard now shows live impact updates.");
  demoRunButton.disabled = false;
}

async function init() {
  try {
    const categories = await fetchJSON(`${API_BASE}/categories`);
    renderFilters(categories);
    // load favorites and suggestions in parallel with initial app data
    const [prods] = await Promise.all([
      fetchJSON(`${API_BASE}/products`),
      loadDashboard(),
      loadCart(),
    ]);
    // build suggestions list
    if (suggestionsList && Array.isArray(prods)) {
      suggestionsList.innerHTML = prods.map((p) => `<option value="${p.name}"></option>`).join('');
    }
    // render products and dashboard (products already fetched above so call loadProducts to respect filters)
    await Promise.all([loadProducts(), loadDashboard()]);
  } catch (error) {
    productsGrid.innerHTML = `<p>Could not load app data: ${error.message}</p>`;
  }

  // Make sure search input and demo button exist before wiring events
  if (searchInput) {
    searchInput.addEventListener("input", () => loadProducts());
  }

  if (minPriceInput) {
    minPriceInput.addEventListener("input", () => loadProducts());
  }
  if (maxPriceInput) {
    maxPriceInput.addEventListener("input", () => loadProducts());
  }
  clearPriceFilter?.addEventListener("click", () => {
    if (minPriceInput) minPriceInput.value = "";
    if (maxPriceInput) maxPriceInput.value = "";
    if (priceFilterError) priceFilterError.textContent = "";
    updateClearPriceFilterVisibility();
    loadProducts();
  });

  if (minScoreSlider) {
    minScoreSlider.addEventListener("input", () => {
      clampScoreSliders("min");
      loadProducts();
    });
  }
  if (maxScoreSlider) {
    maxScoreSlider.addEventListener("input", () => {
      clampScoreSliders("max");
      loadProducts();
    });
  }
  clearScoreFilter?.addEventListener("click", () => {
    if (minScoreSlider) minScoreSlider.value = String(SCORE_MIN);
    if (maxScoreSlider) maxScoreSlider.value = String(SCORE_MAX);
    if (scoreFilterError) scoreFilterError.textContent = "";
    loadProducts();
  });

  // Make the 'Live search' hero badge act as a quick focus/control for search
  const liveBadge = document.querySelector(".hero-badges span");
  if (liveBadge && searchInput) {
    liveBadge.style.cursor = "pointer";
    liveBadge.addEventListener("click", () => {
      searchInput.focus();
      // small visual cue: clear and trigger a refresh
      searchInput.value = "";
      loadProducts();
    });
  }

  demoRunButton?.addEventListener("click", runGuidedDemo);
}

function showAuthOverlay(message = "") {
  appShell.hidden = true;
  authOverlay.setAttribute("aria-hidden", "false");
  authError.textContent = message;
}

function hideAuthOverlay() {
  authOverlay.setAttribute("aria-hidden", "true");
  appShell.hidden = false;
}

function setAuthMode(mode) {
  authMode = mode;
  authError.textContent = "";
  if (mode === "signup") {
    authTitle.textContent = "Sign up";
    authNameField.hidden = false;
    authName.required = true;
    authPassword.autocomplete = "new-password";
    authSubmit.textContent = "Sign up";
    authToggle.textContent = "Already have an account? Log in";
  } else {
    authTitle.textContent = "Log in";
    authNameField.hidden = true;
    authName.required = false;
    authPassword.autocomplete = "current-password";
    authSubmit.textContent = "Log in";
    authToggle.textContent = "Need an account? Sign up";
  }
}

authToggle?.addEventListener("click", () => {
  setAuthMode(authMode === "login" ? "signup" : "login");
});

authForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  authError.textContent = "";
  authSubmit.disabled = true;
  const originalLabel = authSubmit.textContent;
  authSubmit.textContent = authMode === "signup" ? "Signing up…" : "Logging in…";

  try {
    const endpoint = authMode === "signup" ? "/auth/signup" : "/auth/login";
    const payload =
      authMode === "signup"
        ? { name: authName.value.trim(), email: authEmail.value.trim(), password: authPassword.value }
        : { email: authEmail.value.trim(), password: authPassword.value };

    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Something went wrong");
    }

    setToken(data.token);
    authForm.reset();
    await enterApp(data.user);
  } catch (error) {
    authError.textContent = error.message;
  } finally {
    authSubmit.disabled = false;
    authSubmit.textContent = originalLabel;
  }
});

logoutButton?.addEventListener("click", () => {
  clearToken();
  showAuthOverlay();
  setAuthMode("login");
});

async function enterApp(user) {
  if (accountGreeting) {
    accountGreeting.textContent = `Hi, ${user.name}`;
  }
  currentUserId = user.id;
  hiddenHistoryIds = loadHiddenHistoryIds();
  hideAuthOverlay();
  try {
    await init();
  } catch (error) {
    productsGrid.innerHTML = `<p>Could not load app data: ${error.message}</p>`;
  }
}

async function bootstrap() {
  const token = getToken();
  if (!token) {
    showAuthOverlay();
    return;
  }
  try {
    const user = await fetchJSON(`${API_BASE}/auth/me`);
    await enterApp(user);
  } catch (error) {
    clearToken();
    showAuthOverlay();
  }
}

bootstrap();
