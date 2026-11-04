// Панель владельца ChapaShop — ТЕСТОВЫЙ ДИЗАЙН (проверка)
(() => {
  const $ = (s) => document.querySelector(s);
  let csrf = "";

  // Форма входа/выхода
  function showLogin() { $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); }
  function showApp() { $("#login").classList.add("hidden"); $("#app").classList.remove("hidden"); }

  fetch("/admin/api/me", { credentials: "same-origin" })
    .then(r => { if (r.ok) return r.json(); throw new Error(); })
    .then(data => { csrf = data.csrf; showApp(); renderTestOrder(); })
    .catch(() => showLogin());

  $("#loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    $("#loginErr").textContent = "";
    try {
      const r = await fetch("/admin/api/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: f.get("username"), password: f.get("password") })
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "Ошибка входа");
      csrf = data.csrf;
      showApp(); renderTestOrder();
    } catch (err) {
      $("#loginErr").textContent = err.message;
    }
  });

  // --- ЗАГРУЖАЕМ ТЕСТОВЫЙ ЗАКАЗ ---
  function renderTestOrder() {
    const o = {
      number: "05244",
      status: "paid",
      created_at: new Date().toISOString(),
      roblox_username: "SuperBuilder_2010",
      telegram_id: "542198763",
      total_stars: 120,
      items: [
        { name: "Divine Dragon", price_stars: 50, quantity: 1, subtotal: 50 },
        { name: "Mega Neon Unicorn", price_stars: 35, quantity: 2, subtotal: 70 }
      ]
    };
    
    // Левая колонка
    $("#orderNumber").textContent = o.number;
    $("#orderDate").textContent = new Date(o.created_at).toLocaleString("ru-RU");
    $("#robloxUser").textContent = o.roblox_username;
    $("#telegramId").textContent = o.telegram_id;
    
    // Бейдж статуса
    const badge = $("#orderStatus");
    badge.className = `badge ${o.status}`;
    const statusMap = { paid: "Оплачен", processing: "В обработке", awaiting_delivery: "Ожидает выдачи", delivered: "Выдан", rejected: "Отклонён" };
    badge.textContent = statusMap[o.status] || o.status;

    // Таблица товаров
    $("#itemsBody").innerHTML = o.items.map(i => `
      <tr>
        <td>${i.name}</td>
        <td>${i.price_stars} ⭐</td>
        <td>${i.quantity}</td>
        <td><b>${i.subtotal} ⭐</b></td>
      </tr>`).join("");
    $("#orderTotal").textContent = `${o.total_stars} ⭐`;
  }
  
  $("#backBtn").onclick = () => location.reload();
})();
