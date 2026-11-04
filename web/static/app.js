// ChapaShop — простой и надежный интерфейс
(() => {
  const view = document.querySelector("#view");
  
  // Просто выводим товары текстом
  async function load() {
    view.innerHTML = "<p style='padding:20px;'>Загрузка...</p>";
    try {
      const res = await fetch("/api/products");
      if (!res.ok) throw new Error("Сервер вернул " + res.status);
      const items = await res.json();
      
      if (items.length === 0) {
        view.innerHTML = "<p style='padding:20px;'>Товаров нет (база пустая).</p>";
        return;
      }
      
      let html = "<div style='padding:20px;'><h2>Список товаров с сервера:</h2><ul style='list-style:none;'>";
      for (let p of items) {
        html += `<li style='margin-bottom:10px; padding:10px; background:#fff; border-radius:8px; border:1px solid #ddd;'>
          <b>${p.name}</b><br>
          Цена: ${p.price_stars} ⭐<br>
          Статус: ${p.is_available ? "В наличии" : "Нет в наличии"}
        </li>`;
      }
      html += "</ul></div>";
      view.innerHTML = html;
      
    } catch (e) {
      view.innerHTML = `<p style='padding:20px; color:red;'>Ошибка: ${e.message}</p>`;
    }
  }

  // Запуск
  load();
})();
