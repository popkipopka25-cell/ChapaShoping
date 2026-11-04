// ChapaShop — интерфейс сайта. Весь текст выводится через textContent — защита от XSS.
(() => {
const CART_KEY = "chapashop_cart_v1";
const state = { category: null, q: "", sort: "new", onlyAvail: false, cats: [], shop: {}, promo: "" };
const $ = (s) => document.querySelector(s);
const view = $("#view");

function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return e;
}

const TG = window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData ? window.Telegram.WebApp : null;
async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (TG) headers["X-Telegram-Init-Data"] = TG.initData;
  if (opts.body) headers["Content-Type"] = "application/json";
  const r = await fetch(path, Object.assign({}, opts, { headers }));
  if (!r.ok) { let d = ""; try { d = (await r.json()).detail; } catch {} const e = new Error(typeof d === "string" && d ? d : String(r.status)); e.status = r.status; throw e; }
  return r.json();
}
const fmtDate = (s) => new Date(s).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
const PAY_RU = { pending: "Ожидает оплаты", paid: "Оплачен", refunded: "Возврат", failed: "Ошибка оплаты" };
const stars = (n) => `${n} ⭐`;
function toast(t) { const el = $("#toast"); el.textContent = t; el.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove("show"), 1800); }

const cart = {
  read() { try { const v = JSON.parse(localStorage.getItem(CART_KEY) || "[]"); return Array.isArray(v) ? v.filter((x) => Number.isInteger(x.product_id) && Number.isInteger(x.quantity) && x.quantity > 0) : []; } catch { return []; } },
  write(items) { localStorage.setItem(CART_KEY, JSON.stringify(items)); updateBadge(); },
  qty(id) { return (this.read().find((x) => x.product_id === id) || {}).quantity || 0; },
  set(id, q) { const items = this.read().filter((x) => x.product_id !== id); if (q > 0) items.push({ product_id: id, quantity: Math.min(99, q) }); this.write(items); },
  add(id, q = 1) { this.set(id, this.qty(id) + q); },
  count() { return this.read().reduce((s, x) => s + x.quantity, 0); },
};
function updateBadge() {
  const n = cart.count();
  for (const b of [$("#cart-badge"), $("#cart-badge2")]) { b.hidden = !n; b.textContent = n > 99 ? "99+" : n; }
}

function productImage(p, cls = "img") {
  const box = h("div", { class: cls });
  if (p.image_url) box.append(h("img", { src: p.image_url, alt: p.name, loading: "lazy" }));
  else box.textContent = "★";
  return box;
}
function catName(id) { return (state.cats.find((c) => c.id === id) || {}).name || "Без категории"; }

function card(p) {
  const img = productImage(p);
  if (p.is_demo) img.append(h("span", { class: "pill", text: "Демо" }));
  if (!p.is_available) img.append(h("span", { class: "pill off", text: "Нет в наличии" }));
  
  const priceBlock = h("div", { class: "price" });
  if (p.old_price_stars && p.old_price_stars > p.price_stars) {
    priceBlock.append(h("span", { style: "text-decoration: line-through; color: #999; font-size: 14px; margin-right: 6px;" }, `${p.old_price_stars} ⭐`));
  }
  priceBlock.append(`${p.price_stars} ⭐`);

  const btn = h("button", { class: "btn btn-primary", disabled: !p.is_available, onclick: (e) => {
    e.preventDefault(); e.stopPropagation(); cart.add(p.id); toast("Добавлено в корзину");
  } }, p.is_available ? (p.price_stars === 0 ? "Забрать" : "В корзину") : "Нет в наличии");
  
  return h("a", { class: "card", href: `/product/${p.id}`, "data-link": true }, img,
    h("div", { class: "body" },
      priceBlock,
      h("div", { class: "name", text: p.name }),
      h("div", { class: "tag", text: catName(p.category_id) }),
      btn));
}

async function pageHome() {
  document.title = "ChapaShop";
  const grid = h("section", { class: "grid", id: "grid" }, ...Array.from({ length: 6 }, () => h("div", { class: "skel" })));
  const count = h("div", { class: "count" });
  const sort = h("select", { onchange: (e) => { state.sort = e.target.value; loadProducts(); } },
    ...[["new", "Сначала новые"], ["price_asc", "Дешевле"], ["price_desc", "Дороже"], ["name", "По названию"]]
      .map(([v, t]) => h("option", { value: v, selected: state.sort === v }, t)));
  const avail = h("input", { type: "checkbox", checked: state.onlyAvail, onchange: (e) => { state.onlyAvail = e.target.checked; loadProducts(); } });
  const cats = h("nav", { class: "cats" });
  const notice = state.shop.payments_enabled ? null : h("div", { class: "notice", text: "Тестовый режим: оплата пока не подключена, все товары — демо." });
  view.replaceChildren(
    h("section", { class: "hero" }, h("h1", { text: state.shop.shop_name || "ChapaShop" }), h("p", { text: state.shop.shop_description || "" })),
    notice || "", cats,
    h("div", { class: "toolbar" }, count, h("div", { class: "ctrls" }, h("label", { class: "chk" }, avail, "В наличии"), sort)),
    grid);

  function renderCats() {
    const mk = (label, slug) => h("button", { class: "cat" + (state.category === slug ? " on" : ""), onclick: () => { state.category = slug; renderCats(); loadProducts(); } }, label);
    cats.replaceChildren(mk("Все", null), ...state.cats.map((c) => mk(c.name, c.slug)));
  }
  async function loadProducts() {
    const p = new URLSearchParams({ sort: state.sort });
    if (state.q) p.set("q", state.q);
    if (state.category) p.set("category", state.category);
    if (state.onlyAvail) p.set("available", "true");
    try {
      const items = await api("/api/products?" + p);
      count.textContent = `Товаров: ${items.length}`;
      if (!items.length) return grid.replaceChildren(h("div", { class: "empty" }, "Ничего не найдено"));
      grid.replaceChildren(...items.map(card));
    } catch (e) { grid.replaceChildren(h("div", { class: "empty", text: "Ошибка загрузки: " + e.message })); }
  }
  pageHome.reload = loadProducts;
  renderCats(); loadProducts();
}

async function pageProduct(id) {
  view.replaceChildren(h("div", { class: "skel" }));
  let p;
  try { p = await api(`/api/products/${id}`); } catch { return view.replaceChildren(h("div", { class: "empty", text: "Товар не найден" })); }
  document.title = `${p.name} — ChapaShop`;
  let q = Math.max(1, cart.qty(p.id) || 1);
  const qn = h("span", { text: q });
  view.replaceChildren(
    h("div", { class: "crumbs" }, h("a", { href: "/", "data-link": true }, "Каталог"), " / ", catName(p.category_id)),
    h("section", { class: "pp" }, productImage(p),
      h("div", {}, h("h1", { text: p.name }), h("div", { class: "price" }, stars(p.price_stars)),
        h("span", { class: "status " + (p.is_available ? "ok" : "no"), text: p.is_available ? "В наличии" : "Нет в наличии" }),
        h("p", { class: "desc", text: p.description }),
        p.is_available ? h("div", { class: "buy-row" }, h("div", { class: "qty" }, h("button", { onclick: () => { q = Math.max(1, q - 1); qn.textContent = q; } }, "−"), qn, h("button", { onclick: () => { q = Math.min(99, q + 1); qn.textContent = q; } }, "+")),
          h("button", { class: "btn btn-primary", onclick: () => { cart.set(p.id, q); toast(`В корзине: ${q} шт.`); } }, "В корзину")) : "")));
}

async function pageCart() {
  document.title = "Корзина";
  const items = cart.read();
  if (!items.length) return view.replaceChildren(h("h2", { class: "title", text: "Корзина" }), h("div", { class: "empty" }, "Корзина пуста"));
  let quote;
  try { quote = await api("/api/cart/quote", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items, promo_code: state.promo }) }); } 
  catch { return view.replaceChildren(h("div", { class: "empty", text: "Не удалось пересчитать корзину" })); }
  if (quote.removed.length) { cart.write(items.filter((x) => !quote.removed.includes(x.product_id))); toast("Некоторые товары больше недоступны"); }

  const lines = quote.items.map((l) => {
    const step = (d) => { cart.set(l.product_id, l.quantity + d); pageCart(); };
    return h("div", { class: "line" + (l.available ? "" : " off") },
      h("div", { class: "img" }, "★"),
      h("div", {}, h("a", { class: "nm", href: `/product/${l.product_id}`, "data-link": true, text: l.name }),
        h("div", { class: "tag", text: l.available ? `${stars(l.price_stars)} за шт.` : "Нет в наличии" }),
        h("div", { class: "row" }, h("div", { class: "qty" }, h("button", { onclick: () => step(-1) }, "−"), h("span", { text: l.quantity }), h("button", { onclick: () => step(1) }, "+")), h("b", { text: stars(l.subtotal) })),
        h("button", { class: "rm", onclick: () => { cart.set(l.product_id, 0); pageCart(); } }, "Удалить")));
  });

  const err = h("div", { class: "err" });
  const saved = localStorage.getItem("chapashop_roblox") || "";
  const nick = h("input", { type: "text", maxlength: 20, placeholder: "Ваш Roblox ник", value: saved });
  const promoInput = h("input", { type: "text", placeholder: "Введите промокод", value: state.promo, style: "text-transform: uppercase;" });
  const promoBtn = h("button", { class: "btn ghost", style: "margin-top: 8px; padding: 6px 12px;", onclick: () => { state.promo = promoInput.value.trim().toUpperCase(); pageCart(); }}, "Применить");

  const checkout = h("button", { class: "btn btn-primary btn-block", onclick: async () => {
    const v = nick.value.trim();
    if (!/^[A-Za-z0-9_]{3,20}$/.test(v)) { err.textContent = "3–20 символов: латиница, цифры и _"; return; }
    err.textContent = ""; localStorage.setItem("chapashop_roblox", v);
    if (TG) {
      checkout.setAttribute("aria-disabled", "true");
      try {
        const o = await api("/api/orders", { method: "POST", body: JSON.stringify({ roblox_username: v, promo_code: state.promo, items: quote.items.filter((l) => l.available).map((l) => ({ product_id: l.product_id, quantity: l.quantity })) }) });
        cart.write([]); toast(`Заказ ${o.number} создан`); go(`/orders/${o.id}`);
      } catch (x) { err.textContent = x.message; checkout.removeAttribute("aria-disabled"); }
      return;
    }
    const bot = state.shop.bot_username;
    if (!bot) { toast("Telegram-бот ещё не подключён"); return; }
    window.open(`https://t.me/${encodeURIComponent(bot)}?start=shop`, "_blank", "noopener");
  } }, TG ? "Оформить заказ" : "Оформить в Telegram");

  view.replaceChildren(h("h2", { class: "title", text: "Корзина" }),
    h("div", { class: "cart" }, h("div", { class: "lines" }, lines),
      h("aside", { class: "summary" },
        h("div", { class: "r" }, h("span", { text: "Товаров" }), h("span", { text: `${quote.count} шт.` })),
        quote.discount_amount > 0 ? h("div", { class: "r", style: "color: #11a36a;" }, h("span", { text: "Скидка" }), h("span", { text: `-${quote.discount_amount} ⭐` })) : "",
        h("div", { class: "t" }, h("span", { text: "Итого" }), h("span", { text: stars(quote.total_stars) })),
        h("div", { class: "field", style: "margin-top: 10px; margin-bottom: 10px;" }, "Промокод", promoInput, promoBtn),
        h("label", { class: "field" }, "Roblox username", nick, err),
        checkout)));
}

function pageAbout() {
  document.title = "О магазине";
  const s = state.shop;
  view.replaceChildren(h("section", { class: "about" },
    h("h2", { text: s.shop_name || "ChapaShop" }), h("p", { text: s.shop_description || "" }),
    h("h3", { text: "Как проходит заказ" }), h("p", { text: "Выберите товары, укажите Roblox username и оплатите в Telegram Stars." }),
    h("h3", { text: "Контакты" }), h("p", { text: "Поддержка: @ChapikSupport" })));
}

function needTG() { view.replaceChildren(h("div", { class: "empty" }, "Доступно в Telegram Mini App.")); }
function statusChip(o) { const cls = o.status === "delivered" ? "ok" : o.status === "rejected" || o.status === "refunded" ? "no" : "wait"; return h("span", { class: "status " + cls, text: o.status_ru }); }

async function pageOrders() {
  if (!TG) return needTG();
  view.replaceChildren(h("h2", { class: "title", text: "Мои заказы" }), h("div", { class: "skel" }));
  let list;
  try { list = await api("/api/orders"); } catch (x) { return view.replaceChildren(h("div", { class: "empty", text: x.message })); }
  if (!list.length) return view.replaceChildren(h("h2", { class: "title", text: "Мои заказы" }), h("div", { class: "empty" }, "Заказов нет"));
  view.replaceChildren(h("h2", { class: "title", text: "Мои заказы" }), h("div", { class: "orders" },
    list.map((o) => h("a", { class: "order-row", href: `/orders/${o.id}`, "data-link": true },
      h("div", { class: "onum", text: o.number }),
      h("div", { class: "omid" }, h("div", { class: "oname", text: o.items.map((i) => `${i.name} ×${i.quantity}`).join(", ") }), h("div", { class: "tag", text: fmtDate(o.created_at) })),
      h("div", { class: "oend" }, h("b", { text: stars(o.total_stars) }), statusChip(o))))));
}

async function pageOrder(id) {
  if (!TG) return needTG();
  view.replaceChildren(h("div", { class: "skel" }));
  let o;
  try { o = await api(`/api/orders/${id}`); } catch { return view.replaceChildren(h("div", { class: "empty", text: "Заказ не найден" })); }
  view.replaceChildren(
    h("div", { class: "crumbs" }, h("a", { href: "/orders", "data-link": true }, "Заказы"), " / ", o.number),
    h("section", { class: "order-card" },
      h("div", { class: "order-head" }, h("div", { class: "big-num", text: o.number }), statusChip(o)),
      h("div", { class: "r" }, h("span", { text: "Roblox" }), h("span", { text: o.roblox_username })),
      h("h3", { text: "Товары" }),
      o.items.map((i) => h("div", { class: "r" }, h("span", { text: `${i.name} × ${i.quantity}` }), h("span", { text: stars(i.subtotal) }))),
      h("div", { class: "t" }, h("span", { text: "Итого" }), h("span", { text: stars(o.total_stars) })),
      o.server_link ? h("a", { class: "btn btn-primary btn-block", href: o.server_link, target: "_blank" }, "Зайти на сервер") : "",
      o.payment_status === "pending" && o.status === "awaiting_payment" ? h("button", { class: "btn btn-primary btn-block", onclick: async () => {
        try { const { invoice_link } = await api(`/api/orders/${o.id}/invoice`, { method: "POST" }); TG.openInvoice(invoice_link, (s) => { if (s === "paid") { toast("Оплачено!"); setTimeout(() => pageOrder(o.id), 1500); } }); } catch (x) { toast(x.message); }
      } }, `Оплатить ${o.total_stars} ⭐`) : "")));
}

async function pageProfile() {
  if (!TG) return needTG();
  let me;
  try { me = await api("/api/me"); state.me = me; } catch (x) { return view.replaceChildren(h("div", { class: "empty", text: x.message })); }
  const err = h("div", { class: "err" });
  const nick = h("input", { type: "text", maxlength: 20, value: me.roblox_username || "", placeholder: "Player_123" });
  view.replaceChildren(h("h2", { class: "title", text: "Профиль" }), h("section", { class: "order-card" },
    h("div", { class: "r" }, h("span", { text: "Telegram ID" }), h("span", { text: String(me.telegram_id) })),
    h("label", { class: "field" }, "Roblox username", nick, err),
    h("button", { class: "btn btn-primary btn-block", onclick: async () => {
      try { await api("/api/me/roblox", { method: "PUT", body: JSON.stringify({ roblox_username: nick.value.trim() }) }); toast("Сохранено"); }
      catch (x) { err.textContent = x.message; }
    } }, "Сохранить")));
}

function route() {
  const path = location.pathname;
  const m = path.match(/^\/product\/(\d+)$/);
  if (m) return pageProduct(+m[1]);
  if (path === "/cart") return pageCart();
  if (path === "/about") return pageAbout();
  const om = path.match(/^\/orders\/(\d+)$/);
  if (om) return pageOrder(+om[1]);
  if (path === "/orders") return pageOrders();
  if (path === "/profile") return pageProfile();
  return pageHome();
}
function go(url) { history.pushState(null, "", url); route(); }
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-link]");
  if (!a || e.metaKey || e.ctrlKey) return;
  e.preventDefault(); go(a.getAttribute("href"));
});
window.addEventListener("popstate", route);

(async () => {
  if (TG) { TG.ready(); TG.expand(); TG.BackButton.onClick(() => history.length > 1 ? history.back() : go("/")); }
  try { [state.cats, state.shop] = await Promise.all([api("/api/categories"), api("/api/shop")]); } catch {}
  route();
})();
})();
