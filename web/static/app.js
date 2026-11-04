// ===== Тестовые данные =====
const order = {
  number: "05244",
  status: "paid", // paid | processing | waiting | rejected | done
  createdAt: "2026-11-04T09:15:00",
  buyer: { roblox: "SuperBuilder_2010", telegramId: "542198763" },
  items: [
    { name: "Divine Dragon", note: "Pet · Adopt Me", price: 50, qty: 1 },
    { name: "Mega Neon Unicorn", note: "Pet · Adopt Me", price: 35, qty: 2 },
    { name: "Ride Potion", note: "Item", price: 10, qty: 3 },
  ],
};

const STATUSES = {
  paid: "Оплачен",
  processing: "В обработке",
  waiting: "Ожидает выдачи",
  rejected: "Отклонён",
  done: "Выдан",
};

// ===== Вспомогательные функции =====
const $ = (id) => document.getElementById(id);
const stars = (n) => `${n.toLocaleString("ru-RU")} ⭐`;
const total = () => order.items.reduce((s, i) => s + i.price * i.qty, 0);

function formatDate(iso) {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

let toastTimer;
function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}

// ===== Отрисовка =====
function renderStatus() {
  const badge = $("orderStatus");
  badge.className = `badge ${order.status}`;
  badge.textContent = STATUSES[order.status];

  const finished = order.status === "rejected" || order.status === "done";
  ["sendLinkBtn", "completeBtn", "rejectBtn"].forEach((id) => ($(id).disabled = finished));
}

function render() {
  $("orderNumber").textContent = order.number;
  $("orderDate").textContent = formatDate(order.createdAt);
  $("robloxUser").textContent = order.buyer.roblox;
  $("telegramId").textContent = order.buyer.telegramId;

  $("itemsBody").innerHTML = order.items
    .map(
      (i) => `
      <tr>
        <td>${i.name}<span class="sub">${i.note}</span></td>
        <td>${stars(i.price)}</td>
        <td>${i.qty}</td>
        <td><b>${stars(i.price * i.qty)}</b></td>
      </tr>`
    )
    .join("");

  $("orderTotal").textContent = stars(total());
  renderStatus();
}

// ===== Действия =====
const notifySuffix = () =>
  $("notifyTg").checked ? " Покупатель уведомлён в Telegram." : "";

$("sendLinkBtn").addEventListener("click", () => {
  const input = $("serverLink");
  const link = input.value.trim();
  if (!/^https?:\/\/.+/i.test(link)) {
    input.classList.add("error");
    input.focus();
    toast("Вставьте корректную ссылку на приватный сервер");
    return;
  }
  input.classList.remove("error");
  order.status = "waiting";
  renderStatus();
  toast("Ссылка отправлена." + notifySuffix());
});

$("serverLink").addEventListener("input", (e) => e.target.classList.remove("error"));

$("completeBtn").addEventListener("click", () => {
  if (!confirm(`Подтвердить выдачу заказа №${order.number}?`)) return;
  order.status = "done";
  renderStatus();
  toast("Заказ выдан." + notifySuffix());
});

$("rejectBtn").addEventListener("click", () => {
  const reason = prompt("Причина отклонения заказа:", "");
  if (reason === null) return;
  order.status = "rejected";
  renderStatus();
  toast("Заказ отклонён." + notifySuffix());
});

$("pdfBtn").addEventListener("click", () => {
  // Открывает окно печати — выберите «Сохранить как PDF»
  window.print();
});

$("backBtn").addEventListener("click", () => {
  toast("Здесь будет переход к списку заказов");
});

// Запуск
render();
