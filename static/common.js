function getElement(id) {
  return document.getElementById(id);
}

function getJsonFromStorage(key) {
  try {
    return JSON.parse(localStorage.getItem(key));
  } catch {
    return null;
  }
}

function saveJsonToStorage(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function goToUrl(url) {
  window.location.href = url;
}

function createListHtml(items) {
  if (!items || items.length === 0) return '<p>No items</p>';
  return '<ul>' + items.map(i => `<li>${i}</li>`).join('') + '</ul>';
}
