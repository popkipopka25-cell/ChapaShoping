// Панель владельца ChapaShop — красивый дизайн + реальные данные
(() => {
  const $ = (s) => document.querySelector(s);
  let csrf = "";

  // Показываем форму входа или админку
  function showLogin() { $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); }
  function showApp() { $("#login").classList.add("hidden"); $("#app").classList.remove("hidden"); }

  // Проверка авторизации
  fetch("/admin/api/me", { credentials: "same-origin" })
    .then(r => { if (r.ok) return r.json(); throw new Error(); })
    .then(data => { csrf = data.csrf; showApp(); loadFirstOrder(); })
    .catch(() => showLogin());

  // Вход
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
      showApp(); loadFirstOrder();
    } catch (err) {
      $("#loginErr").textContent = err.message;
    }
  });

  // Загрузка первого заказа из базы
  async function loadFirstOrder() {
    try {
      const r = await fetch("/admin/api/orders?limit=1", { credentials: "same-origin" });
      const orders = await r.json();
      if (!orders.length) {
        $("#orderNumber").textContent = "Нет заказов";
        return;
      }
      renderOrder(orders[0].id);
    } catch { $("#orderNumber").textContent = "Ошибка"; }
  }

  // Отрисовка заказа
  async function renderOrder(id) {
    const r = await fetch(`/admin/api/orders/${id}`, { credentials: "same-origin" });
    const o = await r.json();
    
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

    // Обработчики кнопок
    $("#completeBtn").onclick = async () => {
      if (!confirm("Выдать заказ?")) return;
      await fetch(`/admin/api/orders/${id}/status`, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ status: "delivered", notify: true })
      });
      renderOrder(id);
    };

    $("#rejectBtn").onclick = async () => {
      const reason = prompt("Причина отклонения:");
      if (!reason) return;
      await fetch(`/admin/api/orders/${id}/status`, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ status: "rejected", comment: reason, notify: true })
      });
      renderOrder(id);
    };

    $("#sendLinkBtn").onclick = async () => {
      const link = $("#serverLink").value;
      if (!link.startsWith("https://")) return alert("Нужна ссылка https://");
      await fetch(`/admin/api/orders/${id}/deliver`, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ server_link: link })
      });
      renderOrder(id);
    };

    $("#pdfBtn").onclick = () => {
      window.open(`/admin/api/orders/${id}/receipt.pdf`, "_blank");
    };
    
    $("#backBtn").onclick = () => location.reload();
  }
})();
