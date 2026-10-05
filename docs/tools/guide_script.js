(function () {
  var q = document.getElementById('q'), count = document.getElementById('count');
  if (!q) return;
  var cards = Array.prototype.slice.call(document.querySelectorAll('.endpoint'));
  var groups = Array.prototype.slice.call(document.querySelectorAll('section.apisec'));
  q.addEventListener('input', function () {
    var term = q.value.trim().toLowerCase(), shown = 0;
    cards.forEach(function (c) {
      var hit = !term || c.getAttribute('data-search').indexOf(term) > -1;
      c.classList.toggle('hide', !hit);
      if (hit) shown++;
    });
    groups.forEach(function (g) {
      g.classList.toggle('hide', !!term && !g.querySelector('.endpoint:not(.hide)'));
    });
    count.textContent = term ? shown + (shown === 1 ? ' endpoint' : ' endpoints') : '';
  });
})();
