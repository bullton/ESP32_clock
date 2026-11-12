/* ============================================================
   墨水屏控制台 · 交互
   ============================================================ */
(function () {
  "use strict";

  var VIEWS = {
    overview: { title: "概览", sub: "设备与服务状态一览", eyebrow: "墨水屏时钟" },
    screen: { title: "画面", sub: "1× / 2× / 像素与布局视图", eyebrow: "墨水屏时钟" },
    content: { title: "内容", sub: "底栏文本与符号面板", eyebrow: "墨水屏时钟" },
    system: { title: "系统", sub: "布局、接口与实时数据", eyebrow: "墨水屏时钟" },
    account: { title: "账号", sub: "登录密码与会话", eyebrow: "墨水屏时钟" }
  };

  var state = {
    view: "overview",
    mode: "preview",
    auto: true,
    zoomed: false,
    dirty: false,
    original: "",
    savedAt: "",
    palette: null,
    paletteGroup: null,
    blobUrl: null,
    nextAt: 0,
    count: 0,
    timer: null,
    previewTimer: null,
    analyzeTimer: null,
    info: null
  };

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* ------------------------------------------------------------
     视图切换
     ------------------------------------------------------------ */

  function applyView() {
    var name = (location.hash || "").replace(/^#/, "");
    if (!VIEWS[name]) name = "overview";
    state.view = name;

    $$(".view").forEach(function (section) {
      section.hidden = section.dataset.view !== name;
    });

    $$(".nav-item").forEach(function (link) {
      if (link.dataset.view === name) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });

    var meta = VIEWS[name];
    $("#page-title").textContent = meta.title;
    $("#page-sub").textContent = meta.sub;
    $("#page-eyebrow").textContent = meta.eyebrow;

    if (name === "overview") loadOverview();
    if (name === "screen") refreshScreen(false);
    if (name === "content") {
      if (!state.palette) loadPalette();
      refreshEditPreview();
    }
    if (name === "system") { loadLayout(); loadJson(); }
    if (name === "account") loadAccount();
  }

  window.addEventListener("hashchange", applyView);

  /* ------------------------------------------------------------
     顶部/侧边时间
     ------------------------------------------------------------ */

  function tickClock() {
    var now = new Date();
    var hh = String(now.getHours()).padStart(2, "0");
    var mm = String(now.getMinutes()).padStart(2, "0");
    $("#side-clock").textContent = hh + ":" + mm;

    if (state.nextAt && state.auto) {
      var left = Math.max(0, Math.round((state.nextAt - Date.now()) / 1000));
      $("#head-refresh").textContent = "下次刷新 " + left + "s";
      $("#scr-next").textContent = left + " 秒";
    }
  }

  setInterval(tickClock, 1000);
  tickClock();

  /* ------------------------------------------------------------
     服务健康
     ------------------------------------------------------------ */

  function setService(ok, text) {
    var dot = $("#side-dot");
    dot.classList.toggle("is-ok", ok === true);
    dot.classList.toggle("is-bad", ok === false);
    $("#side-status-text").textContent = text;

    var badge = $("#ov-service");
    if (badge) {
      badge.textContent = text;
      badge.className = "badge " + (ok ? "badge-ok" : "badge-bad");
    }
  }

  function checkHealth() {
    return fetch("/api/health", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function () { setService(true, "服务正常"); return true; })
      .catch(function () { setService(false, "服务不可达"); return false; });
  }

  /* ------------------------------------------------------------
     概览
     ------------------------------------------------------------ */

  function loadOverview() {
    checkHealth();

    fetch("/api/info", { cache: "no-store" })
      .then(function (r) {
        if (r.status === 401) throw new Error("登录已过期");
        if (!r.ok) throw new Error("数据不可用");
        return r.json();
      })
      .then(function (payload) {
        state.info = payload;
        var cur = payload.current || {};
        var temp = cur.temp != null ? cur.temp + "°C" : "—";
        $("#ov-weather").textContent = (cur.cond_cn || cur.cond || "—") + " · " + temp + (cur.humidity != null ? " · 湿度 " + cur.humidity + "%" : "");

        var warn = payload.weather_warning || {};
        var details = warn.details || [];
        $("#ov-warning").textContent = details.length ? details.length + " 条生效警告" : "无生效警告";

        var bottom = payload.bottom || "";
        var launchLine = bottom.split("\n")[0] || "";
        $("#ov-launch").textContent = launchLine.indexOf("发射") >= 0 ? launchLine : "暂无数据";

        $("#ov-source").textContent = "HKO · OpenWeatherMap";
        $("#ov-updated").textContent = new Date().toLocaleTimeString("zh-CN");
      })
      .catch(function (err) {
        ["ov-weather", "ov-warning", "ov-launch", "ov-source"].forEach(function (id) {
          $(("#" + id)).textContent = "数据不可用";
        });
        $("#ov-updated").textContent = err.message || "加载失败";
      });

    refreshScreen(false);
  }

  $("#ov-refresh").addEventListener("click", function () {
    refreshScreen(true);
    loadOverview();
  });

  $$("[data-goto]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      location.hash = "#" + btn.dataset.goto;
    });
  });

  /* ------------------------------------------------------------
     画面
     ------------------------------------------------------------ */

  function refreshScreen(flash) {
    var img = $("#scr-img");
    var ovImg = $("#ov-screen");
    var started = performance.now();

    if (flash) $("#scr-overlay").hidden = false;

    fetch("/api/screen.png?_=" + Date.now(), { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        if (state.blobUrl) URL.revokeObjectURL(state.blobUrl);
        state.blobUrl = url;

        if (img) img.src = url;
        if (ovImg) ovImg.src = url;

        var ms = Math.round(performance.now() - started);
        state.count += 1;
        state.nextAt = Date.now() + 60000;

        $("#scr-updated").textContent = new Date().toLocaleTimeString("zh-CN");
        $("#scr-size").textContent = (blob.size / 1024).toFixed(1) + " KB";
        $("#scr-ms").textContent = ms + " ms";
        $("#scr-count").textContent = String(state.count);
        $("#ov-screen-meta").textContent = "更新于 " + new Date().toLocaleTimeString("zh-CN") + " · " + (blob.size / 1024).toFixed(1) + " KB";

        if (state.mode === "pixel") drawPixel(blob);
        if (state.mode === "compare") refreshCompare();
      })
      .catch(function (err) {
        $("#scr-updated").textContent = "失败：" + err.message;
        $("#ov-screen-meta").textContent = "画面加载失败";
      })
      .finally(function () {
        $("#scr-overlay").hidden = true;
      });
  }

  function refreshCompare() {
    var stamp = "?_=" + Date.now();
    $("#cmp-raw").src = "/api/screen_raw.png" + stamp;
    $("#cmp-2x").src = "/api/screen_2x.png" + stamp;
    $("#cmp-epd").src = "/api/screen.png" + stamp;
  }

  function drawPixel(blob) {
    if (!blob || !state.blobUrl) return;
    var canvas = $("#pixel-canvas");
    var img = new Image();
    img.onload = function () {
      var scale = 4;
      canvas.width = 400 * scale;
      canvas.height = 300 * scale;
      var ctx = canvas.getContext("2d");
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    };
    img.src = state.blobUrl;
  }

  function setMode(mode) {
    state.mode = mode;
    $$("[data-mode]").forEach(function (btn) {
      btn.setAttribute("aria-pressed", btn.dataset.mode === mode ? "true" : "false");
    });
    $("#mode-preview").hidden = mode !== "preview";
    $("#mode-compare").hidden = mode !== "compare";
    $("#mode-pixel").hidden = mode !== "pixel";
    $("#mode-layout").hidden = mode !== "layout";

    if (mode === "pixel") {
      if (state.blobUrl) {
        fetch(state.blobUrl).then(function (r) { return r.blob(); }).then(drawPixel);
      } else {
        refreshScreen(false);
      }
    }
    if (mode === "compare") refreshCompare();
    if (mode === "layout") { loadLayout(); $("#layout-img").src = "/api/screen.png?_=" + Date.now(); }
  }

  $$("[data-mode]").forEach(function (btn) {
    btn.addEventListener("click", function () { setMode(btn.dataset.mode); });
  });

  $("#scr-refresh").addEventListener("click", function () {
    refreshScreen(true);
    if (state.mode === "layout") loadLayout();
  });

  $("#scr-auto").addEventListener("click", function () {
    state.auto = !state.auto;
    $("#scr-auto").setAttribute("aria-pressed", state.auto ? "true" : "false");
    $("#scr-auto").textContent = "自动刷新：" + (state.auto ? "开" : "关");
    if (!state.auto) {
      state.nextAt = 0;
      $("#head-refresh").textContent = "自动刷新已暂停";
      $("#scr-next").textContent = "已暂停";
    } else {
      state.nextAt = Date.now() + 60000;
    }
  });

  $("#scr-zoom").addEventListener("click", function () {
    state.zoomed = !state.zoomed;
    $("#scr-frame").classList.toggle("zoomed", state.zoomed);
    $("#scr-zoom").setAttribute("aria-pressed", state.zoomed ? "true" : "false");
    $("#scr-zoom").textContent = state.zoomed ? "恢复 1×" : "放大 1.5×";
  });

  $("#pixel-canvas").addEventListener("click", function () {
    if (state.blobUrl) {
      fetch(state.blobUrl).then(function (r) { return r.blob(); }).then(drawPixel);
    }
  });

  setInterval(function () {
    if (state.auto && document.visibilityState === "visible") {
      if (state.view === "screen" || state.view === "overview") refreshScreen(false);
    }
  }, 60000);

  /* ------------------------------------------------------------
     布局
     ------------------------------------------------------------ */

  function loadLayout() {
    fetch("/api/debug/layout", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (layout) {
        var body = $("#layout-body");
        body.innerHTML = "";
        Object.keys(layout.zones || {}).forEach(function (name) {
          var zone = layout.zones[name];
          var tr = document.createElement("tr");
          var td1 = document.createElement("td");
          td1.textContent = name;
          var td2 = document.createElement("td");
          td2.textContent = String(zone.y);
          var td3 = document.createElement("td");
          td3.textContent = String(zone.h != null ? zone.h : "—");
          tr.appendChild(td1);
          tr.appendChild(td2);
          tr.appendChild(td3);
          body.appendChild(tr);
        });

        var canvas = layout.canvas || {};
        $("#layout-canvas").textContent = canvas.W + " × " + canvas.H + " · 边距 " + canvas.margin;

        var dividers = layout.dividers || {};
        $("#layout-dividers").textContent = Object.keys(dividers).map(function (k) {
          return k + "=" + dividers[k];
        }).join("  ");

        drawZoneTags(layout);
      })
      .catch(function () {
        $("#layout-body").innerHTML = '<tr><td colspan="3" class="table-empty">读取失败，请重试</td></tr>';
      });
  }

  function drawZoneTags(layout) {
    var layer = $("#zone-layer");
    if (!layer) return;
    layer.innerHTML = "";
    var H = (layout.canvas && layout.canvas.H) || 300;

    Object.keys(layout.zones || {}).forEach(function (name) {
      var zone = layout.zones[name];
      var tag = document.createElement("span");
      tag.className = "zone-tag";
      tag.textContent = name + " " + zone.y;
      tag.style.top = (zone.y / H * 100) + "%";
      layer.appendChild(tag);
    });

    var dividers = layout.dividers || {};
    Object.keys(dividers).forEach(function (name) {
      var y = dividers[name];
      var line = document.createElement("span");
      line.className = "zone-line";
      line.style.top = (y / H * 100) + "%";
      layer.appendChild(line);

      var tag = document.createElement("span");
      tag.className = "zone-tag is-divider";
      tag.textContent = name + " " + y;
      tag.style.top = (y / H * 100) + "%";
      layer.appendChild(tag);
    });
  }

  $("#layout-refresh").addEventListener("click", loadLayout);

  /* ------------------------------------------------------------
     系统 · JSON
     ------------------------------------------------------------ */

  function loadJson() {
    var view = $("#json-view");
    view.textContent = "加载中…";
    fetch("/api/info", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (payload) {
        view.textContent = JSON.stringify(payload, null, 2);
      })
      .catch(function () {
        view.textContent = "读取失败";
      });
  }

  $("#json-refresh").addEventListener("click", loadJson);

  $("#json-copy").addEventListener("click", function () {
    var text = $("#json-view").textContent || "";
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        $("#json-copy").textContent = "已复制";
        setTimeout(function () { $("#json-copy").textContent = "复制 JSON"; }, 1500);
      });
    }
  });

  /* ------------------------------------------------------------
     内容编辑
     ------------------------------------------------------------ */

  var TEMPLATES = {
    reminder: "今日提醒\n记得给花浇水，晚上一起散步。",
    birthday: "妈妈生日快到了 🎂\n记得准备礼物和蛋糕。",
    weather: "出门记得带伞 ☔\n天气转凉，注意添衣。",
    blank: ""
  };

  function setMessage(el, text, kind) {
    el.textContent = text;
    el.classList.remove("is-ok", "is-bad");
    if (kind) el.classList.add(kind);
  }

  function updateMeta() {
    var value = $("#content-input").value;
    var chars = Array.from(value).length;
    var lines = value === "" ? 0 : value.split("\n").length;
    $("#content-lines").textContent = lines + " 行";
    $("#content-chars").textContent = chars + " 字";

    state.dirty = value !== state.original;
    $("#saved-hint").textContent = state.dirty ? "有未保存修改" : (state.savedAt ? "已保存 " + state.savedAt : "未加载");

    scheduleAnalyze(value);
  }

  function scheduleAnalyze(value) {
    clearTimeout(state.analyzeTimer);
    state.analyzeTimer = setTimeout(function () {
      fetch("/api/console/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: value })
      })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .then(function (res) {
          var el = $("#content-compat");
          var down = (res.downgraded || []).length;
          var bad = (res.unsupported || []).length;
          el.classList.toggle("is-warn", down + bad > 0);
          if (!down && !bad) {
            el.textContent = "符号均可在屏幕上显示";
          } else if (bad) {
            el.textContent = bad + " 个字符无法显示，将显示为 ·";
          } else {
            el.textContent = down + " 个表情将显示为文字";
          }
        })
        .catch(function () {
          $("#content-compat").textContent = "兼容性检查不可用";
        });
    }, 350);
  }

  function loadContent() {
    fetch("/api/bottom_content", { cache: "no-store" })
      .then(function (r) {
        if (r.status === 401) throw new Error("登录已过期");
        return r.ok ? r.json() : Promise.reject();
      })
      .then(function (res) {
        var text = res.content || "";
        state.original = text;
        $("#content-input").value = text;
        state.dirty = false;
        $("#saved-hint").textContent = text ? "已加载" : "当前为空";
        updateMeta();
        refreshEditPreview();
      })
      .catch(function () {
        setMessage($("#content-msg"), "读取现有内容失败", "is-bad");
        $("#saved-hint").textContent = "读取失败";
      });
  }

  $("#content-input").addEventListener("input", function () {
    updateMeta();
    clearTimeout(state.previewTimer);
    state.previewTimer = setTimeout(refreshEditPreview, 500);
  });

  function refreshEditPreview() {
    var content = $("#content-input").value;
    $("#preview-spinner").hidden = false;
    $("#preview-state").textContent = "渲染中";

    fetch("/api/console/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: content })
    })
      .then(function (r) { return r.ok ? r.blob() : Promise.reject(); })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        $("#edit-preview").src = url;
        $("#preview-state").textContent = "已更新";
      })
      .catch(function () {
        $("#preview-state").textContent = "渲染失败";
      })
      .finally(function () {
        $("#preview-spinner").hidden = true;
      });
  }

  /* 符号面板 */

  function loadPalette() {
    fetch("/api/console/palette", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (data) {
        state.palette = data;
        state.paletteGroup = data.groups[0] && data.groups[0].id;
        renderPaletteTabs();
        renderPaletteGrid();
        $("#palette-note").textContent = data.note || "";
      })
      .catch(function () {
        $("#palette-note").textContent = "符号表加载失败，可直接用键盘输入。";
      });
  }

  function renderPaletteTabs() {
    var tabs = $("#palette-tabs");
    tabs.innerHTML = "";
    state.palette.groups.forEach(function (group, index) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("role", "tab");
      btn.dataset.group = group.id;
      btn.setAttribute("aria-selected", index === 0 ? "true" : "false");
      btn.textContent = group.name;
      btn.addEventListener("click", function () {
        state.paletteGroup = group.id;
        $$("#palette-tabs button").forEach(function (b) {
          b.setAttribute("aria-selected", b === btn ? "true" : "false");
        });
        renderPaletteGrid();
      });
      tabs.appendChild(btn);
    });
  }

  function renderPaletteGrid() {
    var grid = $("#palette-grid");
    var query = ($("#palette-search").value || "").trim().toLowerCase();
    var group = (state.palette.groups || []).filter(function (g) {
      return g.id === state.paletteGroup;
    })[0];

    grid.innerHTML = "";
    if (!group) return;

    var items = group.items.filter(function (item) {
      if (!query) return true;
      var hay = (item.ch + " " + (item.fallback || "")).toLowerCase();
      return hay.indexOf(query) >= 0;
    });

    if (!items.length) {
      var empty = document.createElement("p");
      empty.className = "palette-empty";
      empty.textContent = "这个分类里没有匹配的符号。";
      grid.appendChild(empty);
      return;
    }

    items.forEach(function (item) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "palette-item";
      btn.title = item.fallback ? (item.ch + " → " + item.fallback) : item.ch;
      btn.setAttribute("aria-label", "插入 " + item.ch + (item.fallback ? "（显示为 " + item.fallback + "）" : ""));

      var glyph = document.createElement("span");
      glyph.textContent = item.ch;
      btn.appendChild(glyph);

      if (item.fallback) {
        var small = document.createElement("small");
        small.textContent = item.fallback;
        btn.appendChild(small);
      }
      if (Array.from(item.ch).length > 1) btn.classList.add("is-wide");

      btn.addEventListener("click", function () { insertText(item.ch); });
      grid.appendChild(btn);
    });
  }

  $("#palette-search").addEventListener("input", function () {
    if (state.palette) renderPaletteGrid();
  });

  function insertText(text) {
    var area = $("#content-input");
    var start = area.selectionStart;
    var end = area.selectionEnd;
    area.value = area.value.slice(0, start) + text + area.value.slice(end);
    var caret = start + text.length;
    area.focus();
    area.setSelectionRange(caret, caret);
    updateMeta();
    clearTimeout(state.previewTimer);
    state.previewTimer = setTimeout(refreshEditPreview, 500);
  }

  $("#btn-save").addEventListener("click", function () {
    var btn = $("#btn-save");
    var content = $("#content-input").value;
    btn.disabled = true;
    setMessage($("#content-msg"), "正在保存…", "");

    fetch("/api/bottom_content", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: content })
    })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
      .then(function () {
        state.original = content;
        state.dirty = false;
        state.savedAt = new Date().toLocaleTimeString("zh-CN");
        $("#saved-hint").textContent = "已保存 " + state.savedAt;
        setMessage($("#content-msg"), "已保存，设备下一次刷新时生效。", "is-ok");
        refreshEditPreview();
      })
      .catch(function (err) {
        setMessage($("#content-msg"), "保存失败：" + err.message, "is-bad");
      })
      .finally(function () {
        btn.disabled = false;
      });
  });

  $("#btn-reset").addEventListener("click", function () {
    if (state.dirty && !window.confirm("放弃未保存的修改？")) return;
    loadContent();
    setMessage($("#content-msg"), "已还原为服务器上的内容。", "");
  });

  $("#btn-clear").addEventListener("click", function () {
    if (!$("#content-input").value) return;
    if (!window.confirm("清空编辑器内容？（仍需保存才会生效）")) return;
    $("#content-input").value = "";
    updateMeta();
    refreshEditPreview();
  });

  $$("[data-template]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var text = TEMPLATES[btn.dataset.template];
      if (text === undefined) return;
      if (state.dirty && TEXT_IS_CUSTOM() && !window.confirm("覆盖当前未保存的内容？")) return;
      $("#content-input").value = text;
      updateMeta();
      refreshEditPreview();
    });
  });

  function TEXT_IS_CUSTOM() {
    return $("#content-input").value.trim() !== "";
  }

  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
      if (state.view !== "content") return;
      e.preventDefault();
      $("#btn-save").click();
    }
  });

  window.addEventListener("beforeunload", function (e) {
    if (!state.dirty) return;
    e.preventDefault();
    e.returnValue = "";
  });

  /* ------------------------------------------------------------
     账号
     ------------------------------------------------------------ */

  function loadAccount() {
    fetch("/api/account", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (data) {
        $("#acct-login-at").textContent = data.login_at || "—";
        $("#acct-mode").textContent = data.password_hint || "—";
        if (data.env_managed) {
          $("#acct-env-warning").hidden = false;
          ["pw-old", "pw-new", "pw-confirm", "pw-submit"].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.disabled = true;
          });
        }
      })
      .catch(function () {
        $("#acct-login-at").textContent = "读取失败";
      });
  }

  $("#password-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var oldPw = $("#pw-old").value;
    var newPw = $("#pw-new").value;
    var confirmPw = $("#pw-confirm").value;
    var msg = $("#pw-msg");

    if (!oldPw) { setMessage(msg, "请输入原密码", "is-bad"); $("#pw-old").focus(); return; }
    if (newPw.length < 6) { setMessage(msg, "新密码至少 6 位", "is-bad"); $("#pw-new").focus(); return; }
    if (newPw !== confirmPw) { setMessage(msg, "两次输入的新密码不一致", "is-bad"); $("#pw-confirm").focus(); return; }

    var btn = $("#pw-submit");
    btn.disabled = true;
    setMessage(msg, "正在更新…", "");

    fetch("/api/account/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old: oldPw, new: newPw })
    })
      .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
      .then(function (res) {
        if (!res.ok || !res.data.ok) throw new Error(res.data.message || "更新失败");
        setMessage(msg, res.data.message || "密码已更新", "is-ok");
        $("#password-form").reset();
      })
      .catch(function (err) {
        setMessage(msg, err.message, "is-bad");
      })
      .finally(function () {
        btn.disabled = false;
      });
  });

  /* ------------------------------------------------------------
     初始化
     ------------------------------------------------------------ */

  applyView();
  checkHealth();
  setInterval(checkHealth, 30000);
  loadContent();
})();
