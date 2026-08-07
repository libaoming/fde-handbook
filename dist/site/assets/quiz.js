/* 检索式自测组件：立即反馈（tight loop）；选项等长以免格式泄露答案（/teach 规则）。
   数据内嵌于 <section class="quiz" data-quiz="...">，格式：
   [{"q":"题干","opts":["A","B","C"],"answer":1,"why":"回看指引"}] */
(function () {
  document.querySelectorAll("section.quiz").forEach(function (sec) {
    if (sec.dataset.done) return;
    sec.dataset.done = "1";
    var data;
    try { data = JSON.parse(sec.dataset.quiz); } catch (e) { return; }
    var body = sec.querySelector(".quiz-body");
    data.forEach(function (item, qi) {
      var q = document.createElement("div");
      q.className = "q";
      var p = document.createElement("p");
      p.textContent = (qi + 1) + ". " + item.q;
      q.appendChild(p);
      item.opts.forEach(function (opt, oi) {
        var b = document.createElement("button");
        b.className = "opt";
        b.textContent = opt;
        b.addEventListener("click", function () {
          if (q.classList.contains("answered")) return;
          q.classList.add("answered");
          q.querySelectorAll(".opt").forEach(function (x, xi) {
            if (xi === item.answer) x.classList.add("right");
          });
          if (oi !== item.answer) b.classList.add("wrong");
        });
        q.appendChild(b);
      });
      var why = document.createElement("p");
      why.className = "why";
      why.textContent = "→ " + item.why;
      q.appendChild(why);
      body.appendChild(q);
    });
  });
})();
