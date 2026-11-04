// Панель владельца ChapaShop
(() => {
  const $ = (s) => document.querySelector(s);
  let csrf = "";

  // Показываем форму входа или админку
  function showLogin() { $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); }
  function showApp() { $("#login").classList.add("hidden"); $("#app").classList.remove("hidden"); }

  // Проверка, авторизован ли админ
  fetch("/admin/api/me", { credentials: "same-origin" })
    .then(r => { if (r.ok) return r.json(); throw new Error(); })
    .then(data => { csrf = data.csrf; showApp(); })
    .catch(() => showLogin());

  // Отправка формы входа
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
      showApp();
    } catch (err) {
      $("#loginErr").textContent = err.message;
    }
  });

  // --- НОВЫЙ ДИЗАЙН (Тестовые данные) ---
  const order = {
    number: "05244", status: "paid", createdAt: new Date().toISOString(),
    buyer: { roblox: "SuperBuilder_2010", telegramId: "542198763" },
    items: [
      { name: "Divine Dragon", note: "Pet", price: 50, qty: 1 },
      { name: "Mega Neon Unicorn", note: "Pet", price: 35, qty: 2 },
    ],
  };
  const STATUSES = { paid: "Оплачен", processing: "В обработке", waiting: "Ожидает выдачи", rejected: "Отклонён", done: "Выдан" };

  function render() {
    $("#orderNumber").textContent = order.number;
    $("#orderDate").textContent = new Date(order.createdAt).toLocaleString("ru-RU");
    $("#robloxUser").textContent = order.buyer.roblox;
    $("#telegramId").textContent = order.buyer.telegramId;

    const badge = $("#orderStatus");
    badge.className = `badge ${order.status}`;
    badge.textContent = STATUSES[order.status] || order.status;

    $("#itemsBody").innerHTML = order.items.map(i => `
      <tr>
        <td>${i.name}<span class="sub">${i.note}</span></td>
        <td>${i.price} ⭐</td>
        <td>${i.qty}</td>
        <td><b>${i.price * i.qty} ⭐</b></td>
      </tr>`).join("");
    
    const total = order.items.reduce((s, i) => s + i.price * i.qty, 0);
    $("#orderTotal").textContent = `${total} ⭐`;
  }
  render();
  
  $("#backBtn").onclick = () => location.href = "/admin";
})();
