/* views/tutorial-page.js —— 使用教程（概念 / 流程 / 登录抓取 / 执行模式 / FAQ / 安全） */
import { icon, pageHeadHtml, toastOk } from "../ui.js";
import { esc } from "../util.js";
import { FAQ_ITEMS, FLOW_STEPS } from "../tutorial-data.js";
import { showTutorialOverlay } from "../components/tutorial-overlay.js";

const SECTIONS = [
  { id: "concepts", num: "01", title: "概念速览" },
  { id: "flow", num: "02", title: "完整使用流程" },
  { id: "capture", num: "03", title: "登录抓取分步" },
  { id: "modes", num: "04", title: "三种执行模式" },
  { id: "faq", num: "05", title: "常见问题 FAQ" },
  { id: "safety", num: "06", title: "安全须知" },
];

const MODES = [
  {
    id: "append",
    title: "追加 append",
    color: "",
    desc: "不动现有靶机，把草稿接在最大编号后面。已经在列表里的队伍会自动跳过。",
    use: "适合在现有 35 个靶机基础上扩充，或者第一次只加几个试试。",
  },
  {
    id: "replace",
    title: "按序号替换 replace",
    color: "cyan",
    desc: "草稿第 1 个替换收藏標靶1、第 2 个替换收藏標靶2……当前多出来的编号保留；草稿比当前长则追加到末尾。",
    use: "适合精确调整某几个编号，例如只替换 3 号靶机。",
  },
  {
    id: "rebuild",
    title: "清空重排 rebuild",
    color: "amber",
    desc: "先删除当前全部靶机，再按草稿 1..N 全量重建，编号从 1 连续排列。",
    use: "最推荐：一次配好整套 35 个靶机时编号最干净，也能修复历史重复编号。",
  },
];

export async function render(root) {
  root.innerHTML = `
    ${pageHeadHtml({
      crumbs: [{ label: "使用教程" }],
      title: "使用教程",
      badge: "GUIDE",
      sub: "从登录抓取到执行注入的完整说明：概念、流程、三种执行模式区别与常见问题。首次使用建议先看一遍，或点右上角重播新手引导。",
      actions: `
        <button class="btn btn-ghost" type="button" data-act="replay">${icon("book", 14)} 重播新手引导</button>
        <button class="btn btn-cyan" type="button" data-nav="/capture">${icon("key", 14)} 去登录抓取</button>
      `,
    })}
    <div class="tut-cols">
      <nav class="tut-toc" data-toc>
        <div class="tut-toc-label">目录 // CONTENTS</div>
        ${SECTIONS.map(
          (section) =>
            `<a href="#${section.id}" data-toc-link="${section.id}"><span class="tt-num">${section.num}</span>${esc(section.title)}</a>`,
        ).join("")}
      </nav>
      <div class="tut-content">
        <section class="tut-section" id="concepts">
          <h2><span class="th-num">01</span>概念速览</h2>
          <div class="tut-card amber">
            <div class="tut-card-title">${icon("crosshair", 14)} 靶机工坊是什么？</div>
            <p>通过社区协议工具 <b>GFLH</b>，调用游戏官方接口把<b>任意「可收藏」敌方队伍</b>写进「靶机专训 → 收藏标靶」。靶机战斗不消耗资源，适合研究敌人、做演示或挑战练习。本应用把 <b>选关卡 / 选怪种 / 编排序列 / 执行 / 登录抓取</b> 全部可视化，所有数据来自本机游戏文件、完全离线。</p>
          </div>
          <h3>收藏标靶与 order_id</h3>
          <p><b>收藏标靶</b> = 一条敌方队伍快照，由 <span class="tut-code">enemy_team_id</span>（哪支队伍）和 <span class="tut-code">order_id</span>（显示序号）组成。</p>
          <ul>
            <li><b>order_id 就是游戏界面里的「收藏標靶N」序号</b>，范围 1..35；</li>
            <li>编号必须<b>连续且唯一</b>，否则会出现多个「收藏标靶1」或顺序错乱；</li>
            <li>只有 <span class="tut-code">enemy_team.targettrain_cancollect == "1"</span> 的队伍才能注入——图鉴里展示的队伍已经过滤过；</li>
            <li>序列最多 <b>35</b> 个，执行时按序列顺序对应编号。</li>
          </ul>
          <h3>sign 与登录凭证</h3>
          <p><b>sign</b> 是登录会话凭证，<b>每次登录游戏都会变</b>，过期后注入会失败，需要重新登录抓取。凭证只保存在本机<b>应用数据目录</b>（默认 <span class="tut-code">&lt;GF Forge&gt;/dataMiner/derived/targetforge</span>，可用环境变量 <span class="tut-code">TARGETFORGE_DATA_DIR</span> 覆盖）下的 <span class="tut-code">creds_latest.json</span>，不联网、不上传。</p>
          <h3>灰域怎么浏览？</h3>
          <p>灰域（campaign = -404）节点数量巨大，应用<b>不逐节点列举关卡</b>：只作为 1 个章节，内部按 <b>12 个区域</b>分组，点区域直接看队伍列表（支持搜索与分页）。没有固定关卡的队伍归入「无固定关卡」，保证 264 个可收藏怪种都能找到队伍。</p>
        </section>

        <section class="tut-section" id="flow">
          <h2><span class="th-num">02</span>完整使用流程</h2>
          <p>第一次使用，按下面顺序走一遍即可。最省事的路径是：<b>登录抓取 → 图鉴挑队伍 → 拖拽排序 → 演练预览 → 正式执行 → 大退重登</b>。</p>
          <div class="tut-flow">
            ${FLOW_STEPS.map(
              (step) => `
              <div class="tut-flow-item">
                <div class="tf-num">${esc(step.num)}</div>
                <b>${esc(step.title)}</b>
                <span>${esc(step.desc)}</span>
              </div>`,
            ).join("")}
          </div>
          <ol>
            <li><b>登录抓取</b>：点「开始抓取」→「设置代理并重启游戏」→ 在游戏里登录到主界面 → 等抓取到 uid / sign / 当前靶机 → 点「完成并关闭代理」。<b>sign 每次登录都会变，所以这一步通常每次使用前都要做。</b></li>
            <li><b>挑队伍</b>：在「关卡图鉴」按章节进入关卡看队伍，或在「怪种图鉴」按怪种看所有怪组。点队伍卡片看详情，点「加入序列」。</li>
            <li><b>编排序列</b>：右侧序列面板可直接拖动排序，也可以上移 / 下移 / 移除。显示 n/35 与总效能；顺序就是执行后的收藏標靶编号。</li>
            <li><b>预览执行</b>：点「执行注入」→ 选择模式（追加 / 按序号替换 / 清空重排）→ 先勾选<b>演练模式</b>看一遍删除 / 新增 / 保留 / 最终列表 → 确认无误后取消演练并正式执行。</li>
            <li><b>大退重登</b>：执行完成后游戏客户端不会自动刷新，必须强退游戏重新登录，然后在「靶机专训 → 收藏标靶」里查看结果。</li>
          </ol>
          <div class="tut-card cyan">
            <div class="tut-card-title">${icon("info", 14)} 小提示</div>
            <p>序列只是<b>草稿</b>，调整顺序 / 删除条目不会影响游戏；只有执行向导里确认执行才会真正写入。执行前的预览会显示「删除多少、新增多少、保留多少」，觉得不对随时返回修改。</p>
          </div>
        </section>

        <section class="tut-section" id="capture">
          <h2><span class="th-num">03</span>登录抓取分步</h2>
          <p>抓取的目标是拿到当前账号的 <b>uid + sign</b> 和游戏内现有收藏标靶列表。进入「登录抓取」页，按 1→6 步操作：</p>
          <ol>
            <li><b>开始抓取</b>：启动本地抓包代理，默认监听 <span class="tut-code">127.0.0.1:18080</span>（可在页面「抓包端口」里修改，范围 1024-65535）。日志里会显示代理已启动。</li>
            <li><b>设置代理并重启游戏</b>：应用会把系统代理指向你设置的端口（默认 <span class="tut-code">127.0.0.1:18080</span>），然后强杀游戏进程并重新启动。此操作会二次确认——请先回到安全界面。</li>
            <li><b>在游戏里登录</b>：正常登录，进入主界面即可，游戏会经过抓包代理。</li>
            <li><b>等待抓取</b>：右侧实时日志会依次显示「拿到 uid → 拿到 sign → 读取收藏标靶」。抓取页顶部状态与进度会同步变化。</li>
            <li><b>完成并关闭代理</b>：停止抓包代理、恢复系统代理，把凭证写入应用数据目录下的 <span class="tut-code">creds_latest.json</span>（默认 <span class="tut-code">&lt;GF Forge&gt;/dataMiner/derived/targetforge</span>，可用 <span class="tut-code">TARGETFORGE_DATA_DIR</span> 覆盖）。这一步很重要，否则游戏可能因为代理残留而无法联网。</li>
            <li><b>去编排 / 执行</b>：凭证就绪后即可挑队伍、执行注入。执行完成后同样要「大退重登」。</li>
          </ol>
          <div class="tut-card red">
            <div class="tut-card-title">${icon("alert", 14)} 注意事项</div>
            <ul style="margin:0;padding-left:18px;list-style:disc">
              <li>抓包端口<b>默认 18080，可配置</b>；8080 常被其它程序占用，建议避开。</li>
              <li>抓取期间游戏提示网络异常属正常现象；抓完点「完成并关闭代理」恢复。</li>
              <li>游戏进不去 / 网络异常时，先检查 Windows 系统代理是否已关闭。</li>
              <li><b>sign 每次登录都变</b>：重启游戏后要重新抓取，抓完尽快执行。</li>
              <li>顶栏的游戏进程 PID 由 <b>tasklist 按进程名 GrilsFrontLine.exe 搜索</b>得到，仅在本机展示，不会写死或上传。</li>
            </ul>
          </div>
        </section>

        <section class="tut-section" id="modes">
          <h2><span class="th-num">04</span>三种执行模式</h2>
          <p>执行向导里有三种主模式（外加一个独立的危险操作「清空全部」）。它们都以当前游戏内靶机为基准，区别是「怎么处理现有靶机」：</p>
          <div style="display:flex;flex-direction:column;gap:10px">
            ${MODES.map(
              (mode) => `
              <div class="tut-card ${mode.color}">
                <div class="tut-card-title">${icon("sliders", 14)} ${esc(mode.title)}</div>
                <p>${esc(mode.desc)}</p>
                <p style="color:var(--text-mute);font-size:11.5px">适用：${esc(mode.use)}</p>
              </div>`,
            ).join("")}
            <div class="tut-card red">
              <div class="tut-card-title">${icon("alert", 14)} 清空全部 clear（危险操作）</div>
              <p>只删除当前全部收藏标靶，不新增。入口单独放在「序列编排」页的危险操作区，需要二次确认。清空后<b>必须强退游戏</b>再重新登录，否则进入靶机界面可能卡死。</p>
            </div>
          </div>
          <div class="tut-card cyan">
            <div class="tut-card-title">${icon("eye", 14)} 强烈建议先演练</div>
            <p>执行向导里勾选「演练模式（dry-run）」只会生成计划并打印日志，<b>不发送任何请求</b>。先演练确认删除 / 新增 / 保留数量正确，再取消勾选正式执行。</p>
          </div>
        </section>

        <section class="tut-section" id="faq">
          <h2><span class="th-num">05</span>常见问题 FAQ</h2>
          <p>按现象快速排查。看完仍有问题，先重新登录抓取再试一次，多数错误都来自 sign 过期或当前靶机列表不同步。</p>
          <div class="faq-list" data-faq-list>
            ${FAQ_ITEMS.map(
              (item, index) => `
              <div class="faq-item" data-faq-item>
                <button class="faq-q" type="button">
                  <span class="fq-mark">Q${String(index + 1).padStart(2, "0")}</span>
                  <span>${esc(item.q)}</span>
                  <span class="fq-chev">${icon("chevronRight", 14)}</span>
                </button>
                <div class="faq-a">${item.a}</div>
              </div>`,
            ).join("")}
          </div>
        </section>

        <section class="tut-section" id="safety">
          <h2><span class="th-num">06</span>安全须知</h2>
          <div class="tut-card red">
            <div class="tut-card-title">${icon("shield", 14)} 凭证安全</div>
            <p>uid / sign 只保存在本机<b>应用数据目录</b>（默认 <span class="tut-code">&lt;GF Forge&gt;/dataMiner/derived/targetforge</span>，可用环境变量 <span class="tut-code">TARGETFORGE_DATA_DIR</span> 覆盖）下的 <span class="tut-code">creds_latest.json</span>，<b>不要提交到 git、不要外传</b>。该目录整体不纳入版本管理，可随时删除重建。</p>
          </div>
          <div class="tut-card amber">
            <div class="tut-card-title">${icon("lock", 14)} 本地运行</div>
            <ul style="margin:0;padding-left:18px;list-style:disc">
              <li>应用只监听 <span class="tut-code">127.0.0.1</span>，不对外网开放，不上传任何数据。</li>
              <li>不会自动联网、不会自动操作游戏进程；只有你点击对应按钮（开始抓取 / 执行注入 / 重启游戏）时才会动作。</li>
              <li>顶栏显示的游戏进程 PID 由本机 <span class="tut-code">tasklist</span> 按进程名 <span class="tut-code">GrilsFrontLine.exe</span> 搜索得到，仅在本机展示，不会上传、也不写死。</li>
              <li>「重启游戏」按钮会<b>强杀 GrilsFrontLine.exe</b> 并通过 Steam 重启，必须二次确认；请先回到安全界面再点。</li>
            </ul>
          </div>
          <div class="tut-card">
            <div class="tut-card-title">${icon("alert", 14)} 风险提示</div>
            <p>修改游戏数据属于社区工具行为，可能违反游戏服务条款，存在账号风险。请自行评估，仅用于单机研究 / 演示，不要用于商业用途或影响其他玩家。</p>
          </div>
        </section>
      </div>
    </div>
  `;

  bindEvents(root);
}

function bindEvents(root) {
  root.querySelector('[data-act="replay"]')?.addEventListener("click", () => {
    showTutorialOverlay();
    toastOk("已打开新手引导");
  });

  const tocLinks = root.querySelectorAll("[data-toc-link]");
  tocLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const target = root.querySelector(`#${link.dataset.tocLink}`);
      if (!target) return;
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      tocLinks.forEach((item) => item.classList.remove("active"));
      link.classList.add("active");
    });
  });
  tocLinks[0]?.classList.add("active");

  const list = root.querySelector("[data-faq-list]");
  if (list) {
    list.addEventListener("click", (event) => {
      const q = event.target.closest(".faq-q");
      if (!q) return;
      const item = q.closest("[data-faq-item]");
      const isOpen = item.classList.contains("open");
      list.querySelectorAll("[data-faq-item]").forEach((node) => node.classList.remove("open"));
      if (!isOpen) item.classList.add("open");
    });
    list.querySelector("[data-faq-item]")?.classList.add("open");
  }

  // 目录滚动高亮
  const content = root.querySelector(".tut-content");
  const mainEl = document.querySelector(".main");
  if (mainEl) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const id = entry.target.id;
          tocLinks.forEach((link) => link.classList.toggle("active", link.dataset.tocLink === id));
        });
      },
      { root: mainEl, rootMargin: "-20% 0px -70% 0px", threshold: 0 },
    );
    root.querySelectorAll(".tut-section").forEach((section) => observer.observe(section));
    const cleanupObserver = () => observer.disconnect();
    // 由 main 的路由清理调用
    import("../store.js").then(({ store }) => store.registerCleanup(cleanupObserver));
  }
}
