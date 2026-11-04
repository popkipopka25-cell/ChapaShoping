// Панель владельца ChapaShop. Все данные выводятся через esc() — защита от XSS.
(() => {
  const $ = (s) => document.querySelector(s);
  const view = $("#view");
  let csrf = "";
  const STATUS = {awaiting_payment:"Ожидает оплаты",paid:"Оплачен",processing:"В обработке",awaiting_delivery:"Ожидает выдачи",delivered:"Выдан",rejected:"Отклонён",refunded:"Возврат оформлен"};
  const NEXT = {awaiting_payment:["paid", "rejected"],paid:["processing","awaiting_delivery","delivered","rejected"],processing:["awaiting_delivery","delivered","rejected"],awaiting_delivery:["processing","delivered","rejected"]};
  const ACTIONS = {login:"Вход",login_failed:"Неудачный вход",logout:"Выход",password_changed:"Смена пароля",order_status:"Статус заказа",order_server_link:"Ссылка на сервер",order_refund:"Возврат",product_create:"Новый товар",product_update:"Изменение товара",product_delete:"Удаление товара",settings_update:"Настройки",order_deliver:"Начата выдача",order_receipt_sent:"Отправлен чек",backup_create:"Резервная копия",backup_restore:"Восстановление из копии",promo_create:"Создан промокод"};
  const SETTING_RU = {shop_name:"Название магазина",shop_description:"Описание",primary_color:"Основной цвет",maintenance_mode:"Режим обслуживания (0/1)",contact_info:"Контакты",order_rules:"Правила заказа",bot_username:"Username бота (без @)"};

  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const dt = (s) => new Date(s).toLocaleString("ru-RU", {dateStyle:"short", timeStyle:"short"});
  const badge = (s) => `<span class="badge ${esc(s)}">${esc(STATUS[s] || s)}</span>`;
  const toast = (t) => { const el = $("#toast"); el.textContent = t; el.classList.add("on"); clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove("on"), 2600); };

  async function api(path, opts = {}) {
    const r = await fetch("/admin/api" + path, {
      method: opts.method || "GET", credentials: "same-origin",
      headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf},
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (r.status === 401 && path !== "/login") { showLogin(); throw new Error("Нужен вход"); }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      let msg = data.detail;
      if (Array.isArray(msg)) msg = msg.map((d) => (d.msg || "").replace("Value error, ", "")).join("; ");
      throw new Error(msg || "Ошибка " + r.status);
    }
    return data;
  }
  const run = (fn) => fn().catch((e) => toast(e.message));

  function showLogin() { $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); }
  function showApp() { $("#login").classList.add("hidden"); $("#app").classList.remove("hidden"); route(); }

  $("#loginForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    $("#loginErr").textContent = "";
    api("/login", {method:"POST", body:{username:f.get("username"), password:f.get("password")}})
      .then((d) => { csrf = d.csrf; e.target.reset(); showApp(); })
      .catch((err) => { $("#loginErr").textContent = err.message; });
  });
  $("#logout").onclick = () => run(async () => { await api("/logout", {method:"POST"}); csrf = ""; location.hash = ""; showLogin(); });
  document.querySelectorAll("#tabs a").forEach((a) => a.onclick = () => { location.hash = a.dataset.tab; });
  window.addEventListener("hashchange", route);

  function route() {
    const [tab, id] = (location.hash.slice(1) || "dash").split("/");
    document.querySelectorAll("#tabs a").forEach((a) => a.classList.toggle("on", a.dataset.tab === tab));
    const pages = {dash, orders: () => id ? order(id) : orders(), products, customers: () => id ? customer(id) : customers(), settings, audit, backup, ready, promos};
    run(pages[tab] || dash);
  }

  async function dash() {
    const s = await api("/stats");
    view.innerHTML = `<h2>Сводка</h2><div class="grid">
      <div class="card stat"><b>${s.orders_total}</b>Заказов</div>
      <div class="card stat"><b>${s.revenue_stars} ⭐</b>Получено</div>
      <div class="card stat"><b>${s.customers}</b>Покупателей</div>
      <div class="card stat"><b>${s.products}</b>Товаров</div></div>
      <h3 style="margin-top:18px">Заказы по статусам</h3><div class="grid">
      ${Object.keys(STATUS).map((k) => `<a class="card stat" href="#orders" data-st="${k}"><b>${s.by_status[k] || 0}</b>${STATUS[k]}</a>`).join("")}</div>`;
    view.querySelectorAll("[data-st]").forEach((a) => a.onclick = () => sessionStorage.setItem("st", a.dataset.st));
  }

  async function orders() {
    const st = sessionStorage.getItem("st") || ""; sessionStorage.removeItem("st");
    view.innerHTML = `<h2>Заказы</h2><div class="bar">
      <input id="oq" placeholder="Номер, Telegram ID или Roblox ник">
      <select id="ost"><option value="">Все статусы</option>${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${k === st ? "selected" : ""}>${v}</option>`).join("")}</select>
      </div><div id="olist" class="list"></div>`;
    const load = () => run(async () => {
      const p = new URLSearchParams({q: $("#oq").value, status: $("#ost").value});
      const rows = await api("/orders?" + p);
      $("#olist").innerHTML = rows.length ? rows.map((o) => `<a class="card row" href="#orders/${o.id}">
        <div><b>№${esc(o.number)}</b> · ${esc(o.roblox_username)}<div class="muted small">${dt(o.created_at)} · TG ${esc(o.telegram_id)}</div></div>
        <div style="text-align:right"><b>${o.total_stars} ⭐</b><div>${badge(o.status)}</div></div></a>`).join("") : `<p class="muted">Заказов нет</p>`;
    });
    let t; $("#oq").oninput = () => { clearTimeout(t); t = setTimeout(load, 300); };
    $("#ost").onchange = load; load();
  }

  async function order(id) {
    const o = await api("/orders/" + encodeURIComponent(id));
    const next = NEXT[o.status] || [];
    view.innerHTML = `<a class="back" href="#orders">← Все заказы</a>
      <h2>Заказ №${esc(o.number)} ${badge(o.status)}</h2>
      <div class="two"><div class="list">
        <div class="card"><h3>Товары</h3><table><tr><th>Товар</th><th>Цена</th><th>Кол-во</th><th>Сумма</th></tr>
          ${o.items.map((i) => `<tr><td>${esc(i.name)}</td><td>${i.price_stars}</td><td>${i.quantity}</td><td>${i.subtotal}</td></tr>`).join("")}
          <tr><th colspan="3">Итого</th><th>${o.total_stars} ⭐</th></tr></table></div>
        <div class="card"><h3>История статусов</h3><table>
          ${o.history.map((h) => `<tr><td class="small">${dt(h.at)}</td><td>${esc(h.new_ru)}<div class="muted small">${esc(h.by)}${h.comment ? " · " + esc(h.comment) : ""}</div></td></tr>`).join("")}</table></div>
        <div class="card"><h3>Платежи</h3>${o.payments.length ? `<table>${o.payments.map((p) => `<tr><td class="small">${dt(p.at)}</td><td>${p.amount} ⭐</td><td>${esc(p.status)}</td></tr><tr><td colspan="3" class="mono">${esc(p.charge_id)}</td></tr>`).join("")}</table>` : `<p class="muted">Оплаты пока нет</p>`}</div>
      </div><div class="list">
        <div class="card"><h3>Покупатель</h3>
          <div>Roblox: <b>${esc(o.roblox_username)}</b></div>
          <div>Telegram ID: ${esc(o.telegram_id)}</div>
          ${o.customer ? `<div>${esc(o.customer.first_name || "")} ${o.customer.username ? "@" + esc(o.customer.username) : ""}</div><a class="back" href="#customers/${o.customer.id}">Профиль покупателя →</a>` : ""}
          <div class="muted small">Создан ${dt(o.created_at)} · оплата: ${esc(o.payment_status)}</div></div>
        <div class="card"><h3>Сменить статус</h3>
          ${next.length ? `<select id="nst">${next.map((s) => `<option value="${s}">${STATUS[s]}</option>`).join("")}</select>
          <label>Комментарий (для отклонения — причина)</label><textarea id="ncm" maxlength="500"></textarea>
          <label class="check"><input type="checkbox" id="nnt" checked> Уведомить покупателя в Telegram</label>
          <button class="btn" id="nsave">Сохранить статус</button>` : `<p class="muted">Статус окончательный</p>`}</div>
        <div class="card"><h3>Ссылка на приватный сервер</h3>
          <input id="lnk" placeholder="https://www.roblox.com/share?..." value="${esc(o.server_link || "")}" maxlength="512">
          <label class="check"><input type="checkbox" id="lnt" checked> Отправить ссылку покупателю</label>
          <button class="btn" id="lsave">Сохранить ссылку</button></div>
        ${["paid","processing","awaiting_delivery"].includes(o.status) ? `<div class="card"><h3>Начать выдачу</h3><p class="muted small">Сохранит ссылку, поставит «Ожидает выдачи» и отправит ссылку покупателю.</p>
          <input id="dl" placeholder="https://www.roblox.com/share?..." value="${esc(o.server_link || "")}" maxlength="512">
          <div class="actions"><button class="btn" id="dgo">Отправить ссылку и начать выдачу</button></div></div>` : ""}
        ${["paid","refunded"].includes(o.payment_status) ? `<div class="card"><h3>Чек</h3><div class="actions">
          <a class="btn ghost" href="/admin/api/orders/${o.id}/receipt.pdf" target="_blank" rel="noopener">Открыть PDF</a>
          <button class="btn" id="rcp">Отправить покупателю</button></div></div>` : ""}
        ${o.payment_status === "paid" ? `<div class="card"><h3>Возврат</h3><p class="muted small">Stars вернутся покупателю через Telegram.</p><button class="btn danger" id="rf">Оформить возврат</button></div>` : ""}
      </div></div>`;
    const reload = () => order(id);
    if (next.length) $("#nsave").onclick = () => run(async () => {
      const r = await api(`/orders/${o.id}/status`, {method:"POST", body:{status:$("#nst").value, comment:$("#ncm").value || null, notify:$("#nnt").checked}});
      toast(r.notified ? "Статус сохранён, покупатель уведомлён" : "Статус сохранён"); reload();
    });
    $("#lsave").onclick = () => run(async () => {
      const r = await api(`/orders/${o.id}/server-link`, {method:"POST", body:{server_link:$("#lnk").value, notify:$("#lnt").checked}});
      toast(r.notified ? "Ссылка отправлена покупателю" : "Ссылка сохранена"); reload();
    });
    if ($("#dgo")) $("#dgo").onclick = () => run(async () => {
      const r = await api(`/orders/${o.id}/deliver`, {method:"POST", body:{server_link:$("#dl").value}});
      toast(r.notified ? "Ссылка отправлена, заказ ожидает выдачи" : "Сохранено (сообщение не отправлено)"); reload();
    });
    if ($("#rcp")) $("#rcp").onclick = () => run(async () => {
      const r = await api(`/orders/${o.id}/send-receipt`, {method:"POST"}); toast(r.notified ? "Чек отправлен" : "Чек не отправлен (бот не подключён)");
    });
    if ($("#rf")) $("#rf").onclick = () => confirm(`Вернуть ${o.total_stars} ⭐ покупателю?`) && run(async () => { await api(`/orders/${o.id}/refund`, {method:"POST"}); toast("Возврат оформлен"); reload(); });
  }

  async function products() {
    const {products: list, categories: cats} = await api("/products");
    const catName = Object.fromEntries(cats.map((c) => [c.id, c.name]));
    view.innerHTML = `<h2>Товары</h2><div class="bar"><input id="pq" placeholder="Поиск товара"><button class="btn" id="padd">+ Добавить</button></div>
      <div id="pform"></div><div id="plist" class="list"></div>`;
    const draw = () => {
      const q = $("#pq").value.toLowerCase();
      $("#plist").innerHTML = list.filter((p) => p.name.toLowerCase().includes(q)).map((p) => `<div class="card row" data-id="${p.id}">
        <div><b>${esc(p.name)}</b>${p.is_demo ? ' <span class="badge">Демо</span>' : ""}${p.is_hidden ? ' <span class="badge rejected">Скрыт</span>' : ""}${!p.is_available ? ' <span class="badge awaiting_payment">Нет в наличии</span>' : ""}
          <div class="muted small">${esc(catName[p.category_id] || "Без категории")}</div></div>
        <div style="text-align:right">
          ${p.old_price_stars ? `<div class="muted small" style="text-decoration:line-through;">${p.old_price_stars} ⭐</div>` : ''}
          <b style="color: ${p.price_stars === 0 ? '#11a36a' : 'inherit'}">${p.price_stars === 0 ? 'Бесплатно' : p.price_stars + ' ⭐'}</b>
        </div>
      </div>`).join("") || `<p class="muted">Нет товаров</p>`;
      $("#plist").querySelectorAll("[data-id]").forEach((el) => el.onclick = () => form(list.find((p) => p.id == el.dataset.id)));
    };
    const form = (p) => {
      p = p || {name:"", description:"", image_url:"", category_id:cats[0]?.id ?? null, price_stars:100, old_price_stars:null, is_available:true, is_hidden:false, is_demo:false};
      $("#pform").innerHTML = `<div class="card" style="margin-bottom:12px"><h3>${p.id ? "Редактирование" : "Новый товар"}</h3>
        <label>Название</label><input id="fn" maxlength="128" value="${esc(p.name)}">
        <label>Описание</label><textarea id="fd" maxlength="2000">${esc(p.description)}</textarea>
        <label>Картинка (https://…)</label><input id="fi" maxlength="512" value="${esc(p.image_url || "")}">
        <label>Категория</label><select id="fc"><option value="">Без категории</option>${cats.map((c) => `<option value="${c.id}" ${c.id === p.category_id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>
        <div style="display:flex; gap:10px;">
          <div style="flex:1;"><label>Цена, Stars</label><input id="fp" type="number" min="0" max="100000" value="${p.price_stars}"></div>
          <div style="flex:1;"><label>Старая цена (для акции)</label><input id="fop" type="number" min="0" max="100000" value="${p.old_price_stars || ""}"></div>
        </div>
        <label class="check"><input type="checkbox" id="fa" ${p.is_available ? "checked" : ""}> В наличии</label>
        <label class="check"><input type="checkbox" id="fh" ${p.is_hidden ? "checked" : ""}> Скрыть из магазина</label>
        <label class="check"><input type="checkbox" id="fm" ${p.is_demo ? "checked" : ""}> Пометка «Демо»</label>
        <div class="actions"><button class="btn" id="fs">Сохранить</button><button class="btn ghost" id="fx">Отмена</button>${p.id ? '<button class="btn danger" id="fdl">Удалить</button>' : ""}</div></div>`;
      $("#pform").scrollIntoView({behavior:"smooth"});
      $("#fx").onclick = () => { $("#pform").innerHTML = ""; };
      $("#fs").onclick = () => run(async () => {
        const body = {name:$("#fn").value.trim(), description:$("#fd").value, image_url:$("#fi").value.trim() || null,
          category_id:$("#fc").value ? +$("#fc").value : null, price_stars:+$("#fp").value,
          old_price_stars: $("#fop").value ? +$("#fop").value : null,
          is_available:$("#fa").checked, is_hidden:$("#fh").checked, is_demo:$("#fm").checked};
        await api(p.id ? "/products/" + p.id : "/products", {method: p.id ? "PUT" : "POST", body});
        toast("Товар сохранён"); products();
      });
      if (p.id) $("#fdl").onclick = () => confirm("Удалить товар? Старые заказы сохранятся.") && run(async () => { await api("/products/" + p.id, {method:"DELETE"}); toast("Товар удалён"); products(); });
    };
    $("#pq").oninput = draw; $("#padd").onclick = () => form(); draw();
  }

  async function customers() {
    view.innerHTML = `<h2>Покупатели</h2><div class="bar"><input id="cq" placeholder="Имя, @username, Roblox ник или Telegram ID"></div><div id="clist" class="list"></div>`;
    const load = () => run(async () => {
      const rows = await api("/customers?" + new URLSearchParams({q: $("#cq").value}));
      $("#clist").innerHTML = rows.map((u) => `<a class="card row" href="#customers/${u.id}">
        <div><b>${esc(u.first_name || "Без имени")}</b> ${u.username ? "@" + esc(u.username) : ""}<div class="muted small">TG ${esc(u.telegram_id)} · Roblox: ${esc(u.roblox_username || "—")}</div></div>
        <div style="text-align:right"><b>${u.spent_stars} ⭐</b><div class="muted small">${u.orders} заказ(ов)</div></div></a>`).join("") || `<p class="muted">Покупателей пока нет</p>`;
    });
    let t; $("#cq").oninput = () => { clearTimeout(t); t = setTimeout(load, 300); }; load();
  }

  async function customer(id) {
    const u = await api("/customers/" + encodeURIComponent(id));
    view.innerHTML = `<a class="back" href="#customers">← Все покупатели</a><h2>${esc(u.first_name || "Покупатель")} ${u.username ? "@" + esc(u.username) : ""}</h2>
      <div class="card" style="margin-bottom:12px">Telegram ID: ${esc(u.telegram_id)}<br>Roblox: <b>${esc(u.roblox_username || "—")}</b></div>
      <h3>Заказы</h3><div class="list">${u.orders.map((o) => `<a class="card row" href="#orders/${o.id}"><div><b>№${esc(o.number)}</b><div class="muted small">${dt(o.created_at)}</div></div><div style="text-align:right"><b>${o.total_stars} ⭐</b><div>${badge(o.status)}</div></div></a>`).join("") || '<p class="muted">Заказов нет</p>'}</div>`;
  }

  async function promos() {
    const list = await api("/promocodes");
    view.innerHTML = `<h2>Промокоды</h2>
      <div class="card" style="margin-bottom:12px">
        <h3>Создать промокод</h3>
        <label>Код (латиница)</label><input id="pc" placeholder="НАПРИМЕР: BLOG10" style="text-transform: uppercase;">
        <label>Скидка в %</label><input id="pd" type="number" min="1" max="100" value="10">
        <label>Макс. использований (оставь пустым для безлимита)</label><input id="pm" type="number" min="1">
        <div class="actions"><button class="btn" id="psave">Создать</button></div>
      </div>
      <div class="list">
        ${list.length ? list.map(p => `<div class="card row">
          <div><b>${esc(p.code)}</b> <span class="badge">${p.discount_percent}%</span>
          <div class="muted small">Использован: ${p.uses_count} раз ${p.max_uses ? 'из ' + p.max_uses : ''}</div></div>
          <button class="btn danger sm" onclick="if(confirm('Удалить?')) run(async()=>{ await api('/promocodes/${p.id}', {method:'DELETE'}); toast('Удален'); promos(); })">Удалить</button>
        </div>`).join("") : '<p class="muted">Промокодов пока нет</p>'}
      </div>`;
      
    $("#psave").onclick = () => run(async () => {
      await api("/promocodes", {method:"POST", body:{
        code: $("#pc").value, 
        discount_percent: +$("#pd").value,
        max_uses: $("#pm").value ? +$("#pm").value : null
      }});
      toast("Промокод создан"); promos();
    });
  }

  async function settings() {
    const {settings: s, secrets} = await api("/settings");
    const keys = Object.keys(s);
    view.innerHTML = `<h2>Настройки</h2><div class="two"><div class="card">
      ${keys.map((k) => `<label>${esc(SETTING_RU[k] || k)}</label>${(s[k].length > 60 || k.startsWith("text_") || k.startsWith("notify_")) ? `<textarea data-k="${esc(k)}" maxlength="4000">${esc(s[k])}</textarea>` : `<input data-k="${esc(k)}" maxlength="4000" value="${esc(s[k])}">`}`).join("")}
      <div class="actions"><button class="btn" id="ss">Сохранить настройки</button></div></div>
      <div class="list"><div class="card"><h3>Секреты сервера</h3><p class="muted small">Меняются только в Render → Environment.</p>
        ${Object.entries(secrets).map(([k, v]) => `<div>${esc(k)}: ${v ? "✅ настроен" : "❌ не задан"}</div>`).join("")}</div>
      <div class="card"><h3>Смена пароля</h3>
        <input id="op" type="password" placeholder="Старый пароль" autocomplete="current-password">
        <input id="np" type="password" placeholder="Новый пароль (от 8 символов)" autocomplete="new-password" style="margin-top:8px">
        <div class="actions"><button class="btn" id="cp">Сменить пароль</button></div></div></div></div>`;
    $("#ss").onclick = () => run(async () => {
      const values = {}; view.querySelectorAll("[data-k]").forEach((el) => values[el.dataset.k] = el.value);
      const r = await api("/settings", {method:"PUT", body:{values}});
      toast(r.changed.length ? "Сохранено: " + r.changed.length : "Изменений нет");
    });
    $("#cp").onclick = () => run(async () => {
      const r = await api("/password", {method:"POST", body:{old_password:$("#op").value, new_password:$("#np").value}});
      csrf = r.csrf; $("#op").value = $("#np").value = ""; toast("Пароль изменён");
    });
  }

  async function audit() {
    const rows = await api("/audit");
    view.innerHTML = `<h2>Журнал действий</h2><div class="card"><table><tr><th>Когда</th><th>Кто</th><th>Действие</th><th>Подробности</th></tr>
      ${rows.map((a) => `<tr><td class="small">${dt(a.at)}</td><td>${esc(a.actor)}</td><td>${esc(ACTIONS[a.action] || a.action)}${a.entity_id ? ` <span class="muted">#${esc(a.entity_id)}</span>` : ""}</td><td class="mono">${esc(a.details ? JSON.stringify(a.details) : "")}</td></tr>`).join("")}</table></div>`;
  }

  async function ready() {
    const r = await api("/preflight");
    const icon = (c) => c.ok ? "✅" : (c.critical ? "⛔" : "⚠️");
    view.innerHTML = `<h2>Готовность к запуску</h2>
      <div class="card"><h3>${r.ready ? "✅ Магазин готов к запуску" : "⛔ Не готов: " + esc(r.blockers.join(", "))}</h3>
        ${r.warnings.length ? `<p class="muted">Предупреждения: ${esc(r.warnings.join(", "))}</p>` : ""}
        <table>${r.checks.map((c) => `<tr><td>${icon(c)}</td><td><b>${esc(c.key)}</b><div class="muted small">${esc(c.message)}</div></td></tr>`).join("")}</table>
        <p class="muted small">Секреты задаются в Render → Environment, после изменения перезапустите сервис.</p>
        <button id="rchk">Проверить снова</button></div>`;
    $("#rchk").onclick = () => run(ready);
  }

  async function backup() {
    const ch = await api("/integrity");
    view.innerHTML = `<h2>Резервные копии и проверка</h2><div class="list">
      <div class="card"><h3>Проверка целостности</h3>
        <p>${ch.ok ? "✅ Проблем не найдено" : "⚠️ Найдено проблем: " + ch.problems.length} · заказов проверено: ${ch.orders_checked}</p>
        ${ch.payments_need_review ? `<p>Платежей на проверке: ${ch.payments_need_review}</p>` : ""}
        ${ch.problems.length ? `<table>${ch.problems.map((p) => `<tr><td>${p.order ? "№" + esc(p.order) : "—"}</td><td>${esc(p.issue)}</td></tr>`).join("")}</table>` : ""}</div>
      <div class="card"><h3>Скачать копию</h3><p class="muted small">Все товары, заказы, платежи, покупатели и настройки. Пароль владельца в копию не попадает.</p>
        <div class="actions"><button class="btn" id="bk">Скачать резервную копию</button></div></div>
      <div class="card"><h3>Восстановить из копии</h3><p class="muted small">Текущие данные будут заменены. Перед заменой сервер сам сохранит страховочную копию.</p>
        <input type="file" id="bf" accept="application/json,.json">
        <div class="actions"><button class="btn" id="br">Восстановить</button></div></div></div>`;
    $("#bk").onclick = () => run(async () => {
      const r = await fetch("/admin/api/backup", {credentials:"same-origin"});
      if (!r.ok) throw new Error("Ошибка " + r.status);
      const name = (r.headers.get("Content-Disposition") || "").match(/filename="(.+)"/)?.[1] || "chapashop_backup.json";
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a"); a.href = url; a.download = name; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000); toast("Копия скачана");
    });
    $("#br").onclick = () => run(async () => {
      const f = $("#bf").files[0]; if (!f) throw new Error("Выберите файл копии");
      if (!confirm("Заменить все данные магазина данными из копии?")) return;
      const r = await fetch("/admin/api/restore", {method:"POST", credentials:"same-origin",
        headers:{"Content-Type":"application/json","X-CSRF-Token":csrf,"X-Confirm-Restore":"YES"}, body: await f.text()});
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || "Ошибка " + r.status);
      toast("Восстановлено"); backup();
    });
  }

  api("/me").then((d) => { csrf = d.csrf; showApp(); }).catch(showLogin);
})();
