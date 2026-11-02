const $ = (selector) => document.querySelector(selector);

const projectForm = $("#project-form");
const keywordInput = $("#keyword");
const formMessage = $("#form-message");
const projectList = $("#project-list");
const emptyProjects = $("#empty-projects");
const refreshProjectsButton = $("#refresh-projects");
const openedProject = $("#opened-project");
const openedKeyword = $("#opened-keyword");
const openedCreatedAt = $("#opened-created-at");
const searchSubmitButton = $("#search-submit");
const searchMessage = $("#search-message");
const captureProgress = $("#capture-progress");
const captureProgressLabel = $("#capture-progress-label");
const captureElapsed = $("#capture-elapsed");
const resultsSection = $("#results-section");
const resultsSummary = $("#results-summary");
const priceDistribution = $("#price-distribution");
const priceDistributionTime = $("#price-distribution-time");
const priceDistributionMetrics = $("#price-distribution-metrics");
const priceDistributionChart = $("#price-distribution-chart");
const samePriceGroups = $("#same-price-groups");
const distributionConclusions = $("#distribution-conclusions");
const distributionSelection = $("#distribution-selection");
const distributionSelectionCopy = $("#distribution-selection-copy");
const clearDistributionSelectionButton = $("#clear-distribution-selection");
const capturePageSummary = $("#capture-page-summary");
const captureNextPageButton = $("#capture-next-page");
const monitorKeywordButton = $("#monitor-keyword");
const monitorPageControl = $("#monitor-page-control");
const monitorPageCount = $("#monitor-page-count");
const exportSnapshotButton = $("#export-snapshot");
const productResults = $("#product-results");
const emptyResults = $("#empty-results");
const resultFilters = $("#result-filters");
const resultQuery = $("#result-query");
const minimumPrice = $("#minimum-price");
const maximumPrice = $("#maximum-price");
const platformFilter = $("#platform-filter");
const resultSort = $("#result-sort");
const clearFiltersButton = $("#clear-filters");
const filteredResultsSummary = $("#filtered-results-summary");
const resultPagination = $("#result-pagination");
const imagePreview = $("#image-preview");
const imagePreviewPicture = $("#image-preview-picture");
const imagePreviewTitle = $("#image-preview-title");
const imagePreviewDownload = $("#image-preview-download");
const historySection = $("#history-section");
const historyMessage = $("#history-message");
const historyList = $("#history-list");
const olderSnapshotSelect = $("#older-snapshot");
const newerSnapshotSelect = $("#newer-snapshot");
const compareSnapshotsButton = $("#compare-snapshots");
const diffResults = $("#diff-results");
const searchLauncher = $("#search-launcher");
const searchWorkspace = $("#search-workspace");
const monitorWorkspace = $("#monitor-workspace");
const settingsWorkspace = $("#settings-workspace");
const sidebarProjects = $(".sidebar-projects");
const pageEyebrow = $("#page-eyebrow");
const pageTitle = $("#page-title");
const pageSubtitle = $("#page-subtitle");
const searchNavigation = $('.nav-item[href="#search-workspace"]');
const competitorNavigation = $('.nav-item[href="#competitor-workspace"]');
const monitorNavigation = $('.nav-item[href="#monitor-workspace"]');
const settingsNavigation = $('.nav-item[href="#settings-workspace"]');

const competitorWorkspace = $("#competitor-workspace");
const competitorUrlForm = $("#competitor-url-form");
const competitorUrlInput = $("#competitor-url");
const prepareCompetitorButton = $("#prepare-competitor");
const competitorMessage = $("#competitor-message");
const competitorSkuForm = $("#competitor-sku-form");
const competitorSkuFields = $("#competitor-sku-fields");
const competitorCaptureStatus = $("#competitor-capture-status");
const competitorCaptureTitle = $("#competitor-capture-title");
const captureCompetitorSkuButton = $("#capture-competitor-sku");
const competitorLoginHelp = $("#competitor-login-help");
const reopenCollectorBrowserButton = $("#reopen-collector-browser");
const resumeCompetitorCaptureButton = $("#resume-competitor-capture");
const openCollectorAccountButton = $("#open-collector-account");
const clearCollectorLoginButton = $("#clear-collector-login");
const competitorCommandBar = $("#competitor-command-bar");
const competitorCommandSummary = $("#competitor-command-summary");
const monitorCompetitorButton = $("#monitor-competitor");
const exportCompetitorPackageButton = $("#export-competitor-package");
const backToResultsButton = $("#back-to-results");
const competitorDetail = $("#competitor-detail");
const competitorRecordList = $("#competitor-record-list");
const competitorRecordEmpty = $("#competitor-record-empty");
const competitorRecordCount = $("#competitor-record-count");
const refreshCompetitorRecordsButton = $("#refresh-competitor-records");

const monitorScheduleForm = $("#monitor-schedule-form");
const monitorRunTime = $("#monitor-run-time");
const monitorEnabled = $("#monitor-enabled");
const saveMonitorScheduleButton = $("#save-monitor-schedule");
const runMonitorNowButton = $("#run-monitor-now");
const monitorMessage = $("#monitor-message");
const monitorChangeCount = $("#monitor-change-count");
const monitorChangeMeta = $("#monitor-change-meta");
const monitorChangeList = $("#monitor-change-list");
const monitorChangeEmpty = $("#monitor-change-empty");
const monitorKeywordCount = $("#monitor-keyword-count");
const monitorKeywordPanel = $("#monitor-keyword-panel");
const monitorKeywordList = $("#monitor-keyword-list");
const monitorKeywordEmpty = $("#monitor-keyword-empty");
const monitorCompetitorCount = $("#monitor-competitor-count");
const monitorCompetitorList = $("#monitor-competitor-list");
const monitorCompetitorEmpty = $("#monitor-competitor-empty");
const monitorShopCount = $("#monitor-shop-count");
const monitorShopList = $("#monitor-shop-list");
const monitorShopEmpty = $("#monitor-shop-empty");
const manualShopMonitorForm = $("#manual-shop-monitor-form");
const manualShopUrl = $("#manual-shop-url");
const addManualShopMonitorButton = $("#add-manual-shop-monitor");
const manualShopMessage = $("#manual-shop-message");
const monitorRunList = $("#monitor-run-list");
const monitorRunEmpty = $("#monitor-run-empty");

const aiSettingsForm = $("#ai-settings-form");
const aiApiKeyInput = $("#ai-api-key");
const saveAiSettingsButton = $("#save-ai-settings");
const testAiSettingsButton = $("#test-ai-settings");
const aiSettingsMessage = $("#ai-settings-message");
const aiPresetIdInput = $("#ai-preset-id");
const aiProviderOptions = $("#ai-provider-options");
const aiKeyLabel = $("#ai-key-label");
const aiSaveStatus = $("#ai-save-status");
const aiSaveProvider = $("#ai-save-provider");

const licenseStatusMessage = $("#license-status-message");
const licenseStatusBadge = $("#license-status-badge");
const licensePlanLabel = $("#license-plan-label");
const licenseExpiresAt = $("#license-expires-at");
const licenseRemainingDays = $("#license-remaining-days");
const licenseDeviceSuffix = $("#license-device-suffix");
const licenseRequestLabel = $("#license-request-label");
const licenseRequestCode = $("#license-request-code");
const licenseActivationCode = $("#license-activation-code");
const copyLicenseRequestButton = $("#copy-license-request");
const submitLicenseCodeButton = $("#submit-license-code");
const refreshLicenseStatusButton = $("#refresh-license-status");
const licenseSettingsMessage = $("#license-settings-message");
const licenseActivationBlock = $("#license-activation-block");

const competitorArchive = $("#competitor-archive");

let openedProjectId = null;
let openedSnapshotId = null;
let openedSearchResults = [];
let currentResultPage = 1;
let selectedDistributionItemIds = null;
let preparedCompetitorItemId = null;
let captureStartedAt = null;
let captureElapsedTimer = null;
let imagePreviewTimer = null;
let competitorCaptureTimer = null;
let aiPresets = [];
let activeCompetitorPayload = null;
const RESULTS_PER_PAGE = 20;

const toastElement = $("#toast");
const toastText = $("#toast-text");
const toastAction = $("#toast-action");
const toastClose = $("#toast-close");
let toastTimer = null;

function hideToast() {
  if (toastTimer) {
    clearTimeout(toastTimer);
    toastTimer = null;
  }
  toastElement.hidden = true;
  toastAction.hidden = true;
  toastAction.onclick = null;
}

function showToast(message, { actionLabel = "", onAction = null, duration = 12000 } = {}) {
  if (toastTimer) {
    clearTimeout(toastTimer);
    toastTimer = null;
  }
  toastText.textContent = message;
  if (actionLabel && typeof onAction === "function") {
    toastAction.textContent = actionLabel;
    toastAction.hidden = false;
    toastAction.onclick = () => {
      onAction();
      hideToast();
    };
  } else {
    toastAction.hidden = true;
    toastAction.onclick = null;
  }
  toastElement.hidden = false;
  if (duration > 0) {
    toastTimer = setTimeout(hideToast, duration);
  }
}

toastClose.addEventListener("click", hideToast);

const guideCompetitorButton = $("#guide-go-competitor");
const guideMonitorButton = $("#guide-go-monitor");
if (guideCompetitorButton) guideCompetitorButton.addEventListener("click", () => showCompetitorView());
if (guideMonitorButton) guideMonitorButton.addEventListener("click", () => showMonitorView());

async function revealLocalFolder(kind) {
  try {
    const response = await fetch("/api/system/reveal-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind }),
    });
    await readResponseJson(response);
  } catch (error) {
    showToast(`打开文件夹失败：${error.message}`, { duration: 8000 });
  }
}

function notifyExportStarted(fileHint) {
  showToast(
    `${fileHint} 已开始下载，请到浏览器的下载目录查看。`,
    {
      actionLabel: "打开下载文件夹",
      onAction: () => revealLocalFolder("downloads"),
      duration: 15000,
    },
  );
}

async function readResponseJson(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    if (!response.ok) throw new Error(`请求失败（${response.status}）`);
  }
  if (!response.ok) {
    const detail = payload?.detail;
    const error = new Error(detail?.message || detail || payload?.message || `请求失败（${response.status}）`);
    error.code = detail?.code || payload?.code || "request_failed";
    error.status = response.status;
    throw error;
  }
  return payload;
}

function displayTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? (value || "") : date.toLocaleString("zh-CN", { hour12: false });
}

function setActiveNavigation(name) {
  const mapping = { search: searchNavigation, competitor: competitorNavigation, monitor: monitorNavigation, settings: settingsNavigation };
  for (const [key, element] of Object.entries(mapping)) {
    element.classList.toggle("active", key === name);
    if (key === name) element.setAttribute("aria-current", "page");
    else element.removeAttribute("aria-current");
  }
}

const VIEW_HASHES = {
  search: "#search-workspace",
  competitor: "#competitor-workspace",
  monitor: "#monitor-workspace",
  settings: "#settings-workspace",
};

function syncViewHash(name) {
  const targetHash = VIEW_HASHES[name];
  if (window.location.hash !== targetHash) window.history.replaceState(null, "", targetHash);
}

function showSearchView({ syncHash = true } = {}) {
  sidebarProjects.hidden = false;
  monitorWorkspace.hidden = true;
  settingsWorkspace.hidden = true;
  searchWorkspace.hidden = false;
  searchLauncher.hidden = false;
  resultsSection.hidden = false;
  historySection.hidden = false;
  competitorWorkspace.hidden = true;
  pageEyebrow.textContent = "淘宝市场采集";
  pageTitle.textContent = "采集市场数据";
  pageSubtitle.textContent = "输入关键词直接采集，历史结果自动保存。";
  setActiveNavigation("search");
  if (syncHash) syncViewHash("search");
}

function showCompetitorView({ syncHash = true } = {}) {
  sidebarProjects.hidden = true;
  monitorWorkspace.hidden = true;
  settingsWorkspace.hidden = true;
  searchWorkspace.hidden = true;
  searchLauncher.hidden = true;
  competitorWorkspace.hidden = false;
  pageEyebrow.textContent = "淘宝竞品采集";
  pageTitle.textContent = "采集与管理竞品资料";
  pageSubtitle.textContent = "采集竞品关键信息与价格变化，完整图片和评价素材统一打包导出。";
  setActiveNavigation("competitor");
  if (syncHash) syncViewHash("competitor");
  loadCompetitorRecords().catch((error) => { competitorMessage.textContent = error.message; });
}

function showSettingsView({ syncHash = true } = {}) {
  sidebarProjects.hidden = true;
  monitorWorkspace.hidden = true;
  competitorWorkspace.hidden = true;
  searchLauncher.hidden = true;
  searchWorkspace.hidden = true;
  settingsWorkspace.hidden = false;
  pageEyebrow.textContent = "本机设置";
  pageTitle.textContent = "设置";
  pageSubtitle.textContent = "管理软件授权和模型接入；Key 与数据都只保存在本机。";
  setActiveNavigation("settings");
  if (syncHash) syncViewHash("settings");
  loadLicenseStatus().catch((error) => { licenseSettingsMessage.textContent = error.message; });
}

function showMonitorView({ syncHash = true } = {}) {
  sidebarProjects.hidden = true;
  searchLauncher.hidden = true;
  searchWorkspace.hidden = true;
  competitorWorkspace.hidden = true;
  settingsWorkspace.hidden = true;
  monitorWorkspace.hidden = false;
  pageEyebrow.textContent = "本机定时采集";
  pageTitle.textContent = "监控中心";
  pageSubtitle.textContent = "每日自动采集已选择的关键词和竞品，结果继续保存到历史记录。";
  setActiveNavigation("monitor");
  if (syncHash) syncViewHash("monitor");
  loadMonitorCenter().catch((error) => { monitorMessage.textContent = error.message; });
}

function showViewFromHash() {
  const hash = window.location.hash;
  if (hash === VIEW_HASHES.competitor) return showCompetitorView({ syncHash: false });
  if (hash === VIEW_HASHES.monitor) return showMonitorView({ syncHash: false });
  if (hash === VIEW_HASHES.settings) return showSettingsView({ syncHash: false });
  if (hash === "#results-section" || hash === "#history-section") return showSearchView({ syncHash: false });
  showSearchView();
}

function navigateToView(name) {
  const targetHash = VIEW_HASHES[name];
  if (window.location.hash === targetHash) return showViewFromHash();
  window.location.hash = targetHash;
}

searchNavigation.addEventListener("click", (event) => { event.preventDefault(); navigateToView("search"); });
competitorNavigation.addEventListener("click", (event) => { event.preventDefault(); navigateToView("competitor"); });
monitorNavigation.addEventListener("click", (event) => { event.preventDefault(); navigateToView("monitor"); });
settingsNavigation.addEventListener("click", (event) => { event.preventDefault(); navigateToView("settings"); });
window.addEventListener("hashchange", showViewFromHash);
backToResultsButton.addEventListener("click", () => {
  competitorDetail.hidden = true;
  competitorRecordList.closest("section").scrollIntoView({ behavior: "smooth", block: "start" });
});

function showOpenedProject(project) {
  openedProjectId = project.id;
  openedKeyword.textContent = project.keyword;
  openedCreatedAt.textContent = project.created_at ? `首次搜索：${displayTime(project.created_at)}` : "";
  openedProject.hidden = false;
  $(".empty-workspace-copy").hidden = true;
  keywordInput.value = project.keyword;
  for (const button of projectList.querySelectorAll("button[data-project-id]")) {
    button.classList.toggle("active", Number(button.dataset.projectId) === openedProjectId);
  }
  showSearchView();
}

function startCaptureProgress(label = "正在调用淘宝客户端并保存结果") {
  captureStartedAt = Date.now();
  captureProgress.classList.remove("complete");
  captureProgress.hidden = false;
  captureProgressLabel.textContent = label;
  if (captureElapsedTimer) window.clearInterval(captureElapsedTimer);
  captureElapsedTimer = window.setInterval(() => {
    captureElapsed.textContent = `已等待 ${Math.floor((Date.now() - captureStartedAt) / 1000)} 秒`;
  }, 1000);
}

function stopCaptureProgress() {
  if (captureElapsedTimer) window.clearInterval(captureElapsedTimer);
  captureElapsedTimer = null;
  captureProgress.hidden = true;
}

function finishCaptureProgress(label = "采集完成，结果已经保存") {
  if (captureElapsedTimer) window.clearInterval(captureElapsedTimer);
  captureElapsedTimer = null;
  captureProgress.classList.add("complete");
  captureProgressLabel.textContent = label;
  captureElapsed.textContent = `用时 ${Math.floor((Date.now() - captureStartedAt) / 1000)} 秒`;
  window.setTimeout(() => { captureProgress.hidden = true; captureProgress.classList.remove("complete"); }, 2400);
}

function canonicalProductUrl(result) {
  const productUrl = String(result.product_url || "").trim();
  const itemId = String(result.item_id || "").trim();
  const skuId = String(result.sku_id || "").trim();
  try {
    const parsed = new URL(productUrl);
    if (parsed.hostname === "click.simba.taobao.com" && /^\d+$/.test(itemId)) {
      const canonical = new URL("https://item.taobao.com/item.htm");
      canonical.searchParams.set("id", itemId);
      if (/^\d+$/.test(skuId)) canonical.searchParams.set("skuId", skuId);
      return canonical.toString();
    }
    if (/^\d+$/.test(skuId) && !parsed.searchParams.has("skuId")) parsed.searchParams.set("skuId", skuId);
    return parsed.toString();
  } catch (_error) { return productUrl; }
}

function buyerProductUrl(result) {
  return String(result.buyer_url || "").trim() || canonicalProductUrl(result);
}

function productImageDownloadUrl(result) {
  return `/api/product-image?${new URLSearchParams({ image_url: result.image_url, item_id: result.item_id || "product" })}`;
}

function hideImagePreview() { imagePreview.hidden = true; }
function scheduleImagePreviewHide() {
  if (imagePreviewTimer) window.clearTimeout(imagePreviewTimer);
  imagePreviewTimer = window.setTimeout(hideImagePreview, 160);
}
function showImagePreview(anchor, result) {
  if (!result.image_url) return;
  if (imagePreviewTimer) window.clearTimeout(imagePreviewTimer);
  imagePreviewPicture.src = result.image_url;
  imagePreviewPicture.alt = result.title || "商品主图";
  imagePreviewTitle.textContent = result.title || "商品主图";
  imagePreviewDownload.href = productImageDownloadUrl(result);
  const rect = anchor.getBoundingClientRect();
  imagePreview.style.top = `${Math.min(window.innerHeight - 380, Math.max(12, rect.top - 80))}px`;
  imagePreview.style.left = `${Math.min(window.innerWidth - 340, rect.right + 12)}px`;
  imagePreview.hidden = false;
}
imagePreview.addEventListener("mouseenter", () => { if (imagePreviewTimer) window.clearTimeout(imagePreviewTimer); });
imagePreview.addEventListener("mouseleave", scheduleImagePreviewHide);
window.addEventListener("scroll", hideImagePreview, { passive: true });

function platformLabel(value) {
  return ({ taobao: "淘宝", tmall: "天猫", unknown: "未识别" })[value] || "未识别";
}

function createProductRow(result) {
  const row = document.createElement("tr");
  row.className = "product-row";
  const rank = document.createElement("td");
  rank.className = "rank";
  rank.textContent = String(result.display_rank).padStart(2, "0");
  const imageCell = document.createElement("td");
  if (result.image_url) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "product-image-frame";
    const image = document.createElement("img");
    image.src = result.image_url;
    image.alt = result.title || "商品图";
    image.loading = "lazy";
    button.append(image);
    button.addEventListener("mouseenter", () => showImagePreview(button, result));
    button.addEventListener("mouseleave", scheduleImagePreviewHide);
    button.addEventListener("click", () => showImagePreview(button, result));
    imageCell.append(button);
  } else imageCell.textContent = "无图";
  const product = document.createElement("td");
  product.className = "product-copy";
  const heading = document.createElement("h4");
  const url = canonicalProductUrl(result);
  const buyerUrl = buyerProductUrl(result);
  if (buyerUrl) {
    const link = document.createElement("a");
    link.href = buyerUrl; link.target = "_blank"; link.rel = "noopener";
    link.textContent = result.title || "未采集到标题";
    heading.append(link);
  } else heading.textContent = result.title || "未采集到标题";
  product.append(heading);
  const labels = [result.payment_text, result.origin_text, result.promotion_text, result.logistics_text].filter(Boolean);
  if (labels.length) {
    const tags = document.createElement("p");
    tags.className = "product-market-meta";
    for (const text of labels) { const tag = document.createElement("span"); tag.textContent = text; tags.append(tag); }
    product.append(tags);
  }
  const shop = document.createElement("td"); shop.textContent = result.shop_name || "店铺信息缺失";
  const platform = document.createElement("td");
  const badge = document.createElement("span"); badge.className = `platform-badge ${result.platform_type}`; badge.textContent = platformLabel(result.platform_type); platform.append(badge);
  const price = document.createElement("td"); price.className = "price numeric-column"; price.textContent = result.display_price ? `¥${result.display_price}` : "—";
  const action = document.createElement("td");
  action.className = "product-actions";
  const collect = document.createElement("button"); collect.type = "button"; collect.className = "product-action-button product-collect-button"; collect.textContent = "采集详情";
  collect.addEventListener("click", () => openCompetitorFromResult(result));
  const monitor = document.createElement("button"); monitor.type = "button"; monitor.className = "product-action-button product-monitor-button"; monitor.textContent = "监控单品";
  monitor.disabled = !url;
  monitor.addEventListener("click", async () => {
    if (!openedProjectId || !url) return;
    monitor.disabled = true;
    monitor.textContent = "正在加入…";
    try {
      const response = await fetch(`/api/projects/${openedProjectId}/monitor/competitor`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_url: url, item_id: String(result.item_id || ""), label: result.title || result.item_id }),
      });
      const payload = await readResponseJson(response);
      monitor.textContent = "单品已监控";
      monitor.classList.add("active");
      searchMessage.textContent = payload.message;
    } catch (error) {
      monitor.disabled = false;
      monitor.textContent = "监控单品";
      searchMessage.textContent = error.message;
    }
  });
  const monitorShop = document.createElement("button"); monitorShop.type = "button"; monitorShop.className = "product-action-button product-shop-monitor-button"; monitorShop.textContent = "监控店铺";
  monitorShop.disabled = !result.shop_url;
  monitorShop.title = result.shop_url ? "每日对比店铺商品列表，发现上新和疑似下架" : "当前搜索结果未提供店铺链接";
  monitorShop.addEventListener("click", async () => {
    if (!openedProjectId || !result.shop_url) return;
    monitorShop.disabled = true;
    monitorShop.textContent = "正在加入…";
    try {
      const payload = await readResponseJson(await fetch(`/api/projects/${openedProjectId}/monitor/shop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shop_url: result.shop_url, shop_name: result.shop_name || "淘宝店铺" }),
      }));
      monitorShop.textContent = "店铺已监控";
      monitorShop.classList.add("active");
      searchMessage.textContent = payload.message;
    } catch (error) {
      monitorShop.disabled = false;
      monitorShop.textContent = "监控店铺";
      searchMessage.textContent = error.message;
    }
  });
  action.append(collect, monitor, monitorShop);
  row.append(rank, imageCell, product, shop, platform, price, action);
  return row;
}

function numericPrice(result) {
  const value = Number.parseFloat(result.display_price);
  return Number.isFinite(value) ? value : null;
}

function formatDistributionPrice(value) {
  if (!Number.isFinite(Number(value))) return "—";
  return `¥${Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}

function formatPaymentHeat(value) {
  const heat = Number(value);
  if (!Number.isFinite(heat)) return "热度缺失";
  if (heat >= 10000) return `${Number((heat / 10000).toFixed(1))}万+`;
  if (heat >= 1000) return `${Number((heat / 1000).toFixed(1))}千+`;
  return `${heat}+`;
}

function selectDistributionItems(itemIds, label) {
  selectedDistributionItemIds = new Set(itemIds.map(String));
  currentResultPage = 1;
  distributionSelectionCopy.textContent = `${label} · 已定位 ${selectedDistributionItemIds.size} 件商品`;
  distributionSelection.hidden = false;
  renderFilteredResults();
  resultFilters.scrollIntoView({ behavior: "smooth", block: "start" });
}

function createSvgElement(name, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  return element;
}

function renderPriceDistribution(distribution, capturedAt) {
  const clusters = distribution?.clusters || [];
  priceDistribution.hidden = !clusters.length;
  if (!clusters.length) return;

  const price = distribution.price;
  const heat = distribution.payment_heat;
  const band = distribution.mainstream_price_band;
  priceDistributionTime.textContent = `采集时间 ${displayTime(capturedAt)}`;
  const metrics = [
    ["有效价格", `${price.valid_count} / ${distribution.sample_count} 件`],
    ["价格中位数", formatDistributionPrice(price.median)],
    ["价格跨度", `${formatDistributionPrice(price.minimum)} — ${formatDistributionPrice(price.maximum)}`],
    ["付款热度覆盖", `${heat.known_count} / ${price.valid_count} 件（${heat.coverage_percent}%）`],
  ];
  priceDistributionMetrics.replaceChildren(...metrics.map(([label, value]) => {
    const card = document.createElement("div");
    const caption = document.createElement("span"); caption.textContent = label;
    const strong = document.createElement("strong"); strong.textContent = value;
    card.append(caption, strong); return card;
  }));

  const width = 920;
  const height = 360;
  const left = 72;
  const right = 894;
  const top = 24;
  const knownBottom = 278;
  const missingY = 312;
  const axisY = 326;
  const minimumPriceValue = Number(price.minimum);
  const maximumPriceValue = Number(price.maximum);
  const useLogPrice = maximumPriceValue / minimumPriceValue >= 12;
  const priceTransform = (value) => useLogPrice ? Math.log10(value) : value;
  const transformedMin = priceTransform(minimumPriceValue);
  const transformedMax = priceTransform(maximumPriceValue);
  const x = (value) => transformedMax === transformedMin
    ? (left + right) / 2
    : left + ((priceTransform(value) - transformedMin) / (transformedMax - transformedMin)) * (right - left);

  const knownHeats = clusters.map((cluster) => cluster.payment_heat_lower_bound).filter((value) => value !== null).map(Number);
  const minimumHeat = knownHeats.length ? Math.min(...knownHeats) : 0;
  const maximumHeat = knownHeats.length ? Math.max(...knownHeats) : 0;
  const heatTransform = (value) => Math.log10(Number(value) + 1);
  const transformedHeatMin = heatTransform(minimumHeat);
  const transformedHeatMax = heatTransform(maximumHeat);
  const y = (value) => {
    if (value === null) return missingY;
    if (transformedHeatMax === transformedHeatMin) return (top + knownBottom) / 2;
    return knownBottom - ((heatTransform(value) - transformedHeatMin) / (transformedHeatMax - transformedHeatMin)) * (knownBottom - top);
  };

  const svg = createSvgElement("svg", { viewBox: `0 0 ${width} ${height}`, "aria-hidden": "true" });
  if (band) {
    const bandStart = x(band.minimum);
    const bandEnd = x(band.maximum);
    svg.append(createSvgElement("rect", {
      x: Math.min(bandStart, bandEnd), y: top, width: Math.max(2, Math.abs(bandEnd - bandStart)),
      height: axisY - top, class: "distribution-mainstream-band",
    }));
  }

  const yTicks = knownHeats.length
    ? [...new Set([minimumHeat, Math.round(Math.sqrt((minimumHeat + 1) * (maximumHeat + 1)) - 1), maximumHeat])].sort((a, b) => a - b)
    : [];
  for (const tick of yTicks) {
    const tickY = y(tick);
    svg.append(createSvgElement("line", { x1: left, y1: tickY, x2: right, y2: tickY, class: "distribution-grid-line" }));
    const label = createSvgElement("text", { x: left - 10, y: tickY + 4, "text-anchor": "end", class: "distribution-axis-label" });
    label.textContent = formatPaymentHeat(tick); svg.append(label);
  }
  svg.append(createSvgElement("line", { x1: left, y1: missingY, x2: right, y2: missingY, class: "distribution-missing-line" }));
  const missingLabel = createSvgElement("text", { x: left - 10, y: missingY + 4, "text-anchor": "end", class: "distribution-axis-label" });
  missingLabel.textContent = "缺失"; svg.append(missingLabel);
  svg.append(createSvgElement("line", { x1: left, y1: axisY, x2: right, y2: axisY, class: "distribution-axis-line" }));

  for (let index = 0; index < 5; index += 1) {
    const ratio = index / 4;
    const transformedValue = transformedMin + (transformedMax - transformedMin) * ratio;
    const value = useLogPrice ? 10 ** transformedValue : transformedValue;
    const tickX = left + (right - left) * ratio;
    svg.append(createSvgElement("line", { x1: tickX, y1: axisY, x2: tickX, y2: axisY + 5, class: "distribution-axis-line" }));
    const label = createSvgElement("text", { x: tickX, y: axisY + 21, "text-anchor": "middle", class: "distribution-axis-label" });
    label.textContent = formatDistributionPrice(value); svg.append(label);
  }

  const medianX = x(Number(price.median));
  svg.append(createSvgElement("line", { x1: medianX, y1: top, x2: medianX, y2: axisY, class: "distribution-median-line" }));
  const medianLabel = createSvgElement("text", { x: medianX + 5, y: top + 12, class: "distribution-median-label" });
  medianLabel.textContent = "中位数"; svg.append(medianLabel);

  for (const cluster of clusters) {
    const point = createSvgElement("g", { class: "distribution-point", tabindex: "0", role: "button" });
    const pointX = x(Number(cluster.price));
    const pointY = y(cluster.payment_heat_lower_bound);
    const radius = cluster.product_count > 1 ? 11 : 6;
    const circle = createSvgElement("circle", {
      cx: pointX, cy: pointY, r: radius,
      class: cluster.payment_heat_lower_bound === null ? "distribution-dot missing" : "distribution-dot",
    });
    const title = createSvgElement("title");
    title.textContent = `${formatDistributionPrice(cluster.price)} · ${formatPaymentHeat(cluster.payment_heat_lower_bound)} · ${cluster.product_count}件/${cluster.shop_count}店`;
    point.append(title, circle);
    if (cluster.product_count > 1) {
      const count = createSvgElement("text", { x: pointX, y: pointY + 3, "text-anchor": "middle", class: "distribution-cluster-count" });
      count.textContent = `×${cluster.product_count}`; point.append(count);
    }
    const activate = () => selectDistributionItems(
      cluster.item_ids,
      `${formatDistributionPrice(cluster.price)} · ${formatPaymentHeat(cluster.payment_heat_lower_bound)}`,
    );
    point.addEventListener("click", activate);
    point.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(); } });
    svg.append(point);
  }

  const xCaption = createSvgElement("text", { x: (left + right) / 2, y: height - 5, "text-anchor": "middle", class: "distribution-axis-caption" });
  xCaption.textContent = useLogPrice ? "搜索展示价（价格跨度较大，横轴已压缩）" : "搜索展示价";
  const yCaption = createSvgElement("text", { x: 13, y: (top + knownBottom) / 2, transform: `rotate(-90 13 ${(top + knownBottom) / 2})`, "text-anchor": "middle", class: "distribution-axis-caption" });
  yCaption.textContent = "页面付款热度（对数轴）";
  svg.append(xCaption, yCaption);
  priceDistributionChart.replaceChildren(svg);

  samePriceGroups.replaceChildren();
  const concentrated = distribution.same_price_groups || [];
  if (!concentrated.length) {
    const empty = document.createElement("p"); empty.className = "same-price-empty"; empty.textContent = "当前没有多个商品处在完全相同的展示价。"; samePriceGroups.append(empty);
  } else {
    for (const group of concentrated.slice(0, 5)) {
      const button = document.createElement("button"); button.type = "button";
      const value = document.createElement("strong"); value.textContent = formatDistributionPrice(group.price);
      const count = document.createElement("span"); count.textContent = `${group.product_count} 件 / ${group.shop_count} 店`;
      button.append(value, count);
      button.addEventListener("click", () => selectDistributionItems(group.item_ids, `${formatDistributionPrice(group.price)} 同价商品`));
      samePriceGroups.append(button);
    }
  }

  const conclusions = [
    `本次共 ${distribution.sample_count} 件商品，其中 ${price.valid_count} 件有有效展示价，${price.missing_or_invalid_count} 件价格待确认。`,
    `最低 ${formatDistributionPrice(price.minimum)}，最高 ${formatDistributionPrice(price.maximum)}，价格中位数 ${formatDistributionPrice(price.median)}。`,
  ];
  if (band) conclusions.push(`中间 50% 商品集中在 ${formatDistributionPrice(band.minimum)}—${formatDistributionPrice(band.maximum)}，共 ${band.product_count} 件 / ${band.shop_count} 店。`);
  if (concentrated.length) conclusions.push(`最集中的同价点是 ${formatDistributionPrice(concentrated[0].price)}，共 ${concentrated[0].product_count} 件 / ${concentrated[0].shop_count} 店。`);
  conclusions.push(`付款热度覆盖 ${heat.known_count} / ${price.valid_count} 件；缺失数据不按 0 计算。`);
  distributionConclusions.replaceChildren(...conclusions.map((copy) => { const item = document.createElement("li"); item.textContent = copy; return item; }));
}

function filteredResults() {
  const query = resultQuery.value.trim().toLowerCase();
  const minimum = Number.parseFloat(minimumPrice.value);
  const maximum = Number.parseFloat(maximumPrice.value);
  const selectedPlatform = platformFilter.value;
  const rows = openedSearchResults.filter((result) => {
    const price = numericPrice(result);
    if (selectedDistributionItemIds && !selectedDistributionItemIds.has(String(result.item_id))) return false;
    if (query && !`${result.title || ""} ${result.shop_name || ""}`.toLowerCase().includes(query)) return false;
    if (Number.isFinite(minimum) && (price === null || price < minimum)) return false;
    if (Number.isFinite(maximum) && (price === null || price > maximum)) return false;
    return selectedPlatform === "all" || result.platform_type === selectedPlatform;
  });
  if (resultSort.value !== "rank") rows.sort((a, b) => (numericPrice(a) ?? Infinity) - (numericPrice(b) ?? Infinity));
  if (resultSort.value === "price-descending") rows.reverse();
  return rows;
}
function renderPagination(total) {
  const pages = Math.ceil(total / RESULTS_PER_PAGE);
  resultPagination.replaceChildren();
  resultPagination.hidden = pages <= 1;
  for (let page = 1; page <= pages; page += 1) {
    const button = document.createElement("button"); button.type = "button"; button.dataset.page = page; button.textContent = page;
    if (page === currentResultPage) button.classList.add("active");
    resultPagination.append(button);
  }
}
function renderFilteredResults() {
  const rows = filteredResults();
  const pages = Math.max(1, Math.ceil(rows.length / RESULTS_PER_PAGE));
  if (currentResultPage > pages) currentResultPage = pages;
  const start = (currentResultPage - 1) * RESULTS_PER_PAGE;
  productResults.replaceChildren(...rows.slice(start, start + RESULTS_PER_PAGE).map(createProductRow));
  filteredResultsSummary.textContent = `当前显示 ${rows.length} 件 / 共 ${openedSearchResults.length} 件`;
  emptyResults.hidden = rows.length > 0;
  if (!rows.length) emptyResults.textContent = "没有符合当前筛选条件的商品。";
  renderPagination(rows.length);
}
function resetFilters() {
  resultQuery.value = ""; minimumPrice.value = ""; maximumPrice.value = ""; platformFilter.value = "all"; resultSort.value = "rank";
  selectedDistributionItemIds = null;
  distributionSelection.hidden = true;
  currentResultPage = 1;
}

async function revealSearchResults(snapshot) {
  openedSnapshotId = snapshot.snapshot_id;
  openedSearchResults = snapshot.results || [];
  resetFilters();
  monitorKeywordButton.hidden = !openedSearchResults.length;
  monitorPageControl.hidden = !openedSearchResults.length;
  exportSnapshotButton.hidden = !openedSearchResults.length;
  resultFilters.hidden = !openedSearchResults.length;
  resultsSummary.textContent = `共采集 ${snapshot.result_count} 件 · ${displayTime(snapshot.captured_at)}`;
  const pages = Number(snapshot.captured_page_count || 1);
  capturePageSummary.textContent = `已采集 ${pages} 页`;
  capturePageSummary.hidden = false;
  captureNextPageButton.dataset.nextPage = snapshot.next_page_number || pages + 1;
  captureNextPageButton.hidden = !snapshot.can_collect_next_page;
  captureNextPageButton.disabled = false;
  captureNextPageButton.textContent = "采集下一页";
  renderPriceDistribution(snapshot.price_distribution, snapshot.captured_at);
  renderFilteredResults();
  searchMessage.textContent = `本次 ${snapshot.result_count} 件商品已经保存。`;
}

function snapshotLabel(snapshot) { return `${displayTime(snapshot.captured_at)} · ${snapshot.result_count} 条`; }
function renderSearchHistory(snapshots) {
  historyList.replaceChildren(); olderSnapshotSelect.replaceChildren(); newerSnapshotSelect.replaceChildren(); diffResults.replaceChildren();
  historyMessage.textContent = snapshots.length ? `已保存 ${snapshots.length} 次` : "尚无历史记录";
  for (const snapshot of snapshots) {
    const item = document.createElement("li"); const button = document.createElement("button");
    button.type = "button"; button.className = "history-card"; button.textContent = snapshotLabel(snapshot);
    button.addEventListener("click", () => reopenSavedSnapshot(snapshot.snapshot_id)); item.append(button); historyList.append(item);
    for (const select of [olderSnapshotSelect, newerSnapshotSelect]) { const option = document.createElement("option"); option.value = snapshot.snapshot_id; option.textContent = snapshotLabel(snapshot); select.append(option); }
  }
  compareSnapshotsButton.disabled = snapshots.length < 2;
  if (snapshots.length >= 2) { olderSnapshotSelect.value = snapshots.at(-1).snapshot_id; newerSnapshotSelect.value = snapshots[0].snapshot_id; }
}
async function loadSearchHistory(projectId) {
  const response = await fetch(`/api/projects/${projectId}/searches`); const data = await readResponseJson(response); renderSearchHistory(data.snapshots); return data.snapshots;
}
async function reopenSavedSnapshot(snapshotId) {
  try { const response = await fetch(`/api/projects/${openedProjectId}/searches/${snapshotId}`); await revealSearchResults(await readResponseJson(response)); showSearchView(); }
  catch (error) { historyMessage.textContent = error.message; }
}

function appendDiff(title, entries, labeler) {
  const section = document.createElement("section"); section.className = "diff-group";
  const heading = document.createElement("h4"); heading.textContent = `${title} ${entries.length}`;
  const list = document.createElement("ul");
  for (const entry of entries) { const item = document.createElement("li"); item.textContent = labeler(entry); list.append(item); }
  if (!entries.length) { const item = document.createElement("li"); item.textContent = "无"; list.append(item); }
  section.append(heading, list); diffResults.append(section);
}
function renderDiff(data) {
  diffResults.replaceChildren();
  appendDiff("新增", data.added, (x) => `${x.title || x.item_id} · 新排名 ${x.display_rank}`);
  appendDiff("消失", data.removed, (x) => `${x.title || x.item_id} · 原排名 ${x.display_rank}`);
  appendDiff("排名变化", data.rank_changes, (x) => `${x.title || x.item_id} · ${x.old_rank} → ${x.new_rank}`);
  appendDiff("展示价变化", data.price_changes, (x) => `${x.title || x.item_id} · ¥${x.old_price ?? "缺失"} → ¥${x.new_price ?? "缺失"}`);
  if (data.payment_changes?.length) appendDiff("付款人数变化", data.payment_changes, (x) => `${x.title || x.item_id} · ${x.old_value || "缺失"} → ${x.new_value || "缺失"}`);
  if (data.promotion_changes?.length) appendDiff("优惠变化", data.promotion_changes, (x) => `${x.title || x.item_id} · ${x.old_value || "无"} → ${x.new_value || "无"}`);
  if (data.logistics_changes?.length) appendDiff("物流服务变化", data.logistics_changes, (x) => `${x.title || x.item_id} · ${x.old_value || "无"} → ${x.new_value || "无"}`);
  if (data.shop_changes?.length) appendDiff("店铺变化", data.shop_changes, (x) => `${x.title || x.item_id} · ${x.old_value || "缺失"} → ${x.new_value || "缺失"}`);
  if (data.image_changes?.length) appendDiff("主图变化", data.image_changes, (x) => `${x.title || x.item_id} · 主图已更换`);
}

function renderProjects(projects) {
  projectList.replaceChildren(); emptyProjects.hidden = projects.length > 0;
  for (const project of projects) {
    const item = document.createElement("li"); const button = document.createElement("button");
    button.type = "button"; button.className = "project-card"; button.dataset.projectId = project.id; button.textContent = project.keyword;
    button.addEventListener("click", () => reopenProject(project.id)); item.append(button); projectList.append(item);
  }
}
async function loadProjects() { const response = await fetch("/api/projects"); renderProjects((await readResponseJson(response)).projects); }
async function reopenProject(projectId) {
  try {
    const project = await readResponseJson(await fetch(`/api/projects/${projectId}`)); showOpenedProject(project);
    const snapshots = await loadSearchHistory(project.id); if (snapshots.length) await reopenSavedSnapshot(snapshots[0].snapshot_id);
  } catch (error) { formMessage.textContent = error.message; }
}

async function runSearch() {
  searchSubmitButton.disabled = true; searchSubmitButton.textContent = "采集中…"; startCaptureProgress("正在采集淘宝第 1 页…");
  searchMessage.textContent = "正在读取淘宝第一页；如弹出登录或验证，请先完成扫码。";
  try {
    const response = await fetch(`/api/projects/${openedProjectId}/searches`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    await revealSearchResults(await readResponseJson(response)); finishCaptureProgress(); await loadSearchHistory(openedProjectId); await loadProjects();
  } catch (error) { stopCaptureProgress(); searchMessage.textContent = error.message; resultsSummary.textContent = "本次失败"; }
  finally { searchSubmitButton.disabled = false; searchSubmitButton.textContent = "开始搜索"; }
}

projectForm.addEventListener("submit", async (event) => {
  event.preventDefault(); formMessage.textContent = ""; const keyword = keywordInput.value.trim();
  if (!keyword) { formMessage.textContent = "请输入要搜索的关键词。"; return; }
  try {
    const project = await readResponseJson(await fetch("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ keyword }) }));
    showOpenedProject(project); await loadSearchHistory(project.id); await runSearch();
  } catch (error) { stopCaptureProgress(); formMessage.textContent = error.message; }
});

captureNextPageButton.addEventListener("click", async () => {
  const page = Number(captureNextPageButton.dataset.nextPage || 2);
  captureNextPageButton.disabled = true;
  captureNextPageButton.textContent = `正在采集第 ${page} 页…`;
  capturePageSummary.textContent = `正在采集第 ${page} 页…`;
  capturePageSummary.hidden = false;
  searchMessage.textContent = `正在打开淘宝第 ${page} 页并读取商品，请稍候。`;
  startCaptureProgress(`正在采集淘宝第 ${page} 页…`);
  try {
    const response = await fetch(`/api/projects/${openedProjectId}/searches/${openedSnapshotId}/next-page`, { method: "POST" });
    const result = await readResponseJson(response);
    if (["login_required", "blocked", "failed"].includes(result.status)) {
      stopCaptureProgress();
      searchMessage.textContent = result.message;
      capturePageSummary.textContent = `第 ${page} 页采集失败`;
      captureNextPageButton.disabled = false;
      captureNextPageButton.textContent = "重新采集下一页";
      return;
    }
    await revealSearchResults(result.snapshot);
    finishCaptureProgress(`淘宝第 ${page} 页采集完成`);
    searchMessage.textContent = result.message;
    await loadSearchHistory(openedProjectId);
  } catch (error) {
    stopCaptureProgress();
    searchMessage.textContent = error.message;
    capturePageSummary.textContent = `第 ${page} 页采集失败`;
    captureNextPageButton.disabled = false;
    captureNextPageButton.textContent = "重新采集下一页";
  }
});

for (const control of [resultQuery, minimumPrice, maximumPrice, platformFilter, resultSort]) {
  control.addEventListener("input", () => { currentResultPage = 1; renderFilteredResults(); });
  control.addEventListener("change", () => { currentResultPage = 1; renderFilteredResults(); });
}
resultPagination.addEventListener("click", (event) => { const button = event.target.closest("button[data-page]"); if (!button) return; currentResultPage = Number(button.dataset.page); renderFilteredResults(); });
clearFiltersButton.addEventListener("click", () => { resetFilters(); renderFilteredResults(); });
clearDistributionSelectionButton.addEventListener("click", () => {
  selectedDistributionItemIds = null;
  distributionSelection.hidden = true;
  currentResultPage = 1;
  renderFilteredResults();
});
refreshProjectsButton.addEventListener("click", () => loadProjects().catch((error) => { formMessage.textContent = error.message; }));
exportSnapshotButton.addEventListener("click", () => {
  if (!openedSnapshotId) return;
  window.location.assign(`/api/projects/${openedProjectId}/searches/${openedSnapshotId}/export.xlsx`);
  notifyExportStarted("市场数据 XLSX");
});
compareSnapshotsButton.addEventListener("click", async () => {
  const older_snapshot_id = Number(olderSnapshotSelect.value); const newer_snapshot_id = Number(newerSnapshotSelect.value);
  if (older_snapshot_id === newer_snapshot_id) { historyMessage.textContent = "请选择两条不同的历史记录。"; return; }
  try { const query = new URLSearchParams({ older_snapshot_id, newer_snapshot_id }); renderDiff(await readResponseJson(await fetch(`/api/projects/${openedProjectId}/search-diff?${query}`))); }
  catch (error) { historyMessage.textContent = error.message; }
});

function renderSkuFields(dimensions) {
  competitorSkuFields.replaceChildren();
  for (const [dimensionIndex, dimension] of dimensions.entries()) {
    const label = document.createElement("label"); label.className = "sku-field"; const span = document.createElement("span"); span.textContent = dimension.label;
    const select = document.createElement("select"); select.dataset.dimension = dimension.label;
    for (const [index, option] of (dimension.options || []).entries()) { const item = document.createElement("option"); item.value = index; item.textContent = option.value; item.dataset.value = option.value; select.append(item); }
    label.append(span, select); competitorSkuFields.append(label);
  }
  competitorSkuForm.hidden = !dimensions.length;
}

function archiveGroup(title, body, { open = false, className = "" } = {}) {
  const details = document.createElement("details");
  details.className = `competitor-archive-group ${className}`.trim();
  details.open = open;
  const summary = document.createElement("summary");
  summary.textContent = title;
  details.append(summary, body);
  return details;
}

function competitorImageGrid(items, label, className = "") {
  const grid = document.createElement("div");
  grid.className = `competitor-image-grid ${className}`.trim();
  for (const [index, item] of items.entries()) {
    const figure = document.createElement("figure");
    const image = document.createElement("img");
    image.src = item.url || item.image_url;
    image.loading = index < 5 ? "eager" : "lazy";
    image.alt = item.related_text || `${label}${index + 1}`;
    const caption = document.createElement("figcaption");
    const text = document.createElement("span");
    text.textContent = item.related_text || `${label} ${index + 1}`;
    const link = document.createElement("a");
    link.href = image.src;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "查看原图";
    caption.append(text, link);
    figure.append(image, caption);
    grid.append(figure);
  }
  return grid;
}

function competitorRecordAction(label, className, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", handler);
  return button;
}

async function openSavedCompetitor(itemId) {
  competitorMessage.textContent = "正在打开已保存的竞品资料…";
  try {
    const payload = await readResponseJson(await fetch(`/api/competitors/${itemId}`));
    const snapshot = payload.snapshot || {};
    const archive = snapshot.archive || {};
    const dimensions = archive.sku_catalog?.dimensions || [];
    preparedCompetitorItemId = String(itemId);
    competitorUrlInput.value = payload.outbound_url || payload.record?.resolved_url || snapshot.page_url || "";
    renderSkuFields(dimensions);
    renderCompetitorIntelligence(payload);
    competitorCaptureTitle.textContent = snapshot.title || `商品 ${itemId}`;
    competitorCaptureStatus.textContent = "已加载历史竞品资料";
    competitorMessage.textContent = "已打开竞品价格资料；完整素材可直接下载 ZIP。";
    competitorDetail.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    competitorMessage.textContent = error.message;
  }
}

async function deleteSavedCompetitor(record) {
  const title = record.title || `商品 ${record.item_id}`;
  if (!window.confirm(`确定删除《${title}》的竞品记录吗？\n\n对应竞品监控会同时停止，市场搜索中的商品数据不会受到影响。`)) return;
  try {
    const result = await readResponseJson(await fetch(`/api/competitors/${record.item_id}`, { method: "DELETE" }));
    if (String(preparedCompetitorItemId || "") === String(record.item_id)) {
      preparedCompetitorItemId = null;
      competitorDetail.hidden = true;
      competitorArchive.hidden = true;
      competitorCommandBar.hidden = true;
    }
    competitorMessage.textContent = result.message || "竞品记录已删除。";
    await loadCompetitorRecords();
  } catch (error) {
    competitorMessage.textContent = error.message;
  }
}

function renderCompetitorRecords(records) {
  competitorRecordList.replaceChildren();
  competitorRecordCount.textContent = `${records.length} 项`;
  competitorRecordEmpty.hidden = records.length > 0;
  for (const record of records) {
    const row = document.createElement("tr");
    const imageCell = document.createElement("td");
    if (record.main_image_url) {
      const image = document.createElement("img");
      image.className = "competitor-record-thumb";
      image.src = record.main_image_url;
      image.alt = record.title || "竞品主图";
      image.loading = "lazy";
      imageCell.append(image);
    } else {
      const placeholder = document.createElement("span");
      placeholder.className = "competitor-record-thumb placeholder";
      placeholder.textContent = "无图";
      imageCell.append(placeholder);
    }
    const productCell = document.createElement("td");
    const title = document.createElement("a");
    title.className = "competitor-record-title";
    title.href = record.buyer_url || record.source_url || record.resolved_url || `https://item.taobao.com/item.htm?id=${record.item_id}`;
    title.target = "_blank";
    title.rel = "noopener";
    title.textContent = record.title || `商品 ${record.item_id}`;
    const detail = document.createElement("small");
    detail.textContent = [record.shop_name, `商品ID ${record.item_id}`].filter(Boolean).join(" · ");
    productCell.append(title, detail);
    const priceCell = document.createElement("td");
    priceCell.textContent = record.visible_price_text ? `¥${String(record.visible_price_text).replace(/^¥|^￥/, "")}` : "页面未提供";
    const timeCell = document.createElement("td");
    timeCell.textContent = displayTime(record.last_captured_at);
    const countCell = document.createElement("td");
    countCell.textContent = `${record.snapshot_count || 0} 次`;
    const actionsCell = document.createElement("td");
    actionsCell.className = "competitor-record-actions";
    const view = competitorRecordAction("查看资料", "record-action", () => openSavedCompetitor(record.item_id));
    const recapture = competitorRecordAction("重新采集", "record-action", () => {
      competitorUrlInput.value = record.resolved_url;
      prepareCompetitor(record.resolved_url);
    });
    const exportLink = document.createElement("a");
    exportLink.className = "record-action";
    exportLink.href = `/api/competitors/${record.item_id}/export.zip`;
    exportLink.textContent = "导出 ZIP";
    const remove = competitorRecordAction("删除", "record-action danger", () => deleteSavedCompetitor(record));
    actionsCell.append(view, recapture, exportLink, remove);
    row.append(imageCell, productCell, priceCell, timeCell, countCell, actionsCell);
    competitorRecordList.append(row);
  }
}

async function loadCompetitorRecords() {
  const payload = await readResponseJson(await fetch("/api/competitors"));
  renderCompetitorRecords(payload.records || []);
  return payload.records || [];
}

refreshCompetitorRecordsButton.addEventListener("click", () => {
  loadCompetitorRecords().catch((error) => { competitorMessage.textContent = error.message; });
});

function renderLegacyCompetitorArchive(prepared) {
  const archive = prepared.product_archive || {};
  const fields = archive.product_fields || {};
  const images = Array.isArray(archive.images) ? archive.images : [];
  const dimensions = archive.sku_catalog?.dimensions || [];
  const reviews = archive.reviews || {};
  const questions = archive.questions || {};
  const mainImages = images.filter((item) => item.kind === "main").slice(0, 5);
  const skuImages = images.filter((item) => item.kind === "sku");
  const detailImages = images.filter((item) => item.kind === "detail");
  // The target-SKU form belongs to the SKU archive group. Detach it before
  // rebuilding the archive so the same live form and its event handler survive.
  competitorSkuForm.remove();
  competitorArchive.replaceChildren();

  const header = document.createElement("header");
  header.className = "competitor-archive-header";
  const headerCopy = document.createElement("div");
  const eyebrow = document.createElement("p"); eyebrow.className = "eyebrow"; eyebrow.textContent = "已保存的竞品资料";
  const title = document.createElement("h4"); title.textContent = archive.title || prepared.title || "商品详情";
  const summary = document.createElement("p"); summary.className = "competitor-product-archive-summary";
  summary.textContent = `${mainImages.length} 张主图 · ${skuImages.length} 张 SKU 图 · ${detailImages.length} 张详情图 · ${(reviews.items || []).length} 条评价`;
  headerCopy.append(eyebrow, title, summary);
  header.append(headerCopy);

  const facts = document.createElement("div"); facts.className = "competitor-product-facts";
  for (const [label, value] of [["当前价格", fields.price_text || prepared.visible_price_text], ["店铺", fields.shop_name || prepared.shop_name], ["付款/销量", fields.payment_text || fields.sold_text], ["发货地", fields.origin_text]]) {
    const card = document.createElement("article"); const name = document.createElement("span"); name.textContent = label; const content = document.createElement("strong"); content.textContent = value || "页面未提供"; card.append(name, content); facts.append(card);
  }
  competitorArchive.append(header, facts);

  if (mainImages.length) {
    competitorArchive.append(archiveGroup(`主图图集 · ${mainImages.length} 张`, competitorImageGrid(mainImages, "主图", "main-image-grid"), { open: true, className: "main-gallery-group" }));
  } else {
    const missing = document.createElement("p"); missing.className = "archive-missing-note"; missing.textContent = "本次没有识别到顶部商品图集，可重新抓取；不会用详情图冒充主图。";
    competitorArchive.append(archiveGroup("主图图集 · 暂未识别", missing, { open: true, className: "main-gallery-group" }));
  }

  if (dimensions.length || skuImages.length) {
    const skuContent = document.createElement("div"); skuContent.className = "competitor-sku-options";
    for (const dimension of dimensions) {
      const section = document.createElement("section");
      const heading = document.createElement("h6"); heading.textContent = dimension.label;
      const optionGrid = document.createElement("div"); optionGrid.className = "sku-option-grid";
      const hasImages = (dimension.options || []).some((option) => option.image_url);
      section.className = hasImages ? "sku-dimension has-images" : "sku-dimension text-only";
      for (const option of dimension.options || []) {
        const optionCard = document.createElement("article");
        if (option.image_url) { const picture = document.createElement("img"); picture.src = option.image_url; picture.loading = "lazy"; picture.alt = option.value; optionCard.append(picture); }
        const optionName = document.createElement("span"); optionName.textContent = option.value; optionCard.append(optionName); optionGrid.append(optionCard);
      }
      section.append(heading, optionGrid); skuContent.append(section);
    }
    if (!dimensions.length && skuImages.length) skuContent.append(competitorImageGrid(skuImages, "SKU 图"));
    if (dimensions.length) {
      const targetHeading = document.createElement("div");
      targetHeading.className = "sku-target-heading";
      const targetTitle = document.createElement("strong"); targetTitle.textContent = "选择目标 SKU（可选）";
      const targetCopy = document.createElement("span"); targetCopy.textContent = "需要准确规格价格时再选择；不影响资料包导出。";
      targetHeading.append(targetTitle, targetCopy);
      skuContent.append(targetHeading, competitorSkuForm);
    }
    competitorArchive.append(archiveGroup(`SKU 规格 · ${dimensions.length} 个维度 / ${skuImages.length} 张 SKU 图`, skuContent, { open: true, className: "sku-archive-group" }));
  }
  if (detailImages.length) competitorArchive.append(archiveGroup(`详情页图片 · ${detailImages.length} 张`, competitorImageGrid(detailImages, "详情图")));

  if ((reviews.items || []).length) {
    const reviewWrap = document.createElement("div");
    const tags = document.createElement("div"); tags.className = "competitor-review-tags";
    for (const tag of reviews.tags || []) { const chip = document.createElement("span"); chip.textContent = tag; tags.append(chip); }
    const list = document.createElement("ol"); list.className = "competitor-review-list";
    const reviewItems = reviews.items || [];
    const renderReviewRows = (showAll = false) => {
      list.replaceChildren();
      for (const item of (showAll ? reviewItems : reviewItems.slice(0, 10))) {
        const row = document.createElement("li"); const text = document.createElement("p"); text.textContent = item.content; const context = document.createElement("small"); context.textContent = [item.sku, item.date].filter(Boolean).join(" · "); row.append(text, context);
        if ((item.images || []).length) row.append(competitorImageGrid(item.images.map((url) => ({ url })), "评价图", "review-image-grid"));
        list.append(row);
      }
    };
    const toolbar = document.createElement("div"); toolbar.className = "competitor-review-toolbar";
    const reviewStatus = document.createElement("div");
    const reviewCount = document.createElement("strong"); reviewCount.textContent = `已保存 ${reviewItems.length} 条评价`;
    const reviewHint = document.createElement("span"); reviewHint.textContent = "可分批继续采集，已保存内容不会丢失。";
    reviewStatus.append(reviewCount, reviewHint);
    const continueButton = document.createElement("button");
    continueButton.type = "button";
    continueButton.className = "secondary competitor-continue-reviews";
    continueButton.textContent = "继续采集更多评价";
    continueButton.addEventListener("click", async () => {
      if (!preparedCompetitorItemId) return;
      continueButton.disabled = true;
      continueButton.textContent = "正在采集下一批…";
      reviewHint.textContent = "正在读取后续评价页，可能需要几十秒。";
      try {
        const response = await fetch(`/api/competitors/${preparedCompetitorItemId}/continue`, { method: "POST" });
        const continued = await readResponseJson(response);
        renderCompetitorArchive(continued);
        competitorMessage.textContent = continued.added_review_count
          ? `新增 ${continued.added_review_count} 条评价，当前累计 ${continued.review_count} 条。`
          : "本次没有发现新的评价，已保留现有数据。";
      } catch (error) {
        reviewHint.textContent = error.message;
        competitorLoginHelp.hidden = !["taobao_browser_login_required", "taobao_login_required"].includes(error.code);
      } finally {
        continueButton.disabled = false;
        continueButton.textContent = "继续采集更多评价";
      }
    });
    toolbar.append(reviewStatus, continueButton);
    renderReviewRows(false); reviewWrap.append(toolbar, tags, list);
    if (reviewItems.length > 10) { const more = document.createElement("button"); more.type = "button"; more.className = "secondary competitor-show-all"; more.textContent = `查看全部 ${reviewItems.length} 条`; more.addEventListener("click", () => { const expanded = more.dataset.expanded === "true"; more.dataset.expanded = String(!expanded); renderReviewRows(!expanded); more.textContent = expanded ? `查看全部 ${reviewItems.length} 条` : "收起评价"; }); reviewWrap.append(more); }
    competitorArchive.append(archiveGroup(`${reviews.total_text || "评价"} · 已保存 ${reviewItems.length} 条`, reviewWrap));
  }
  if ((questions.items || []).length) {
    const list = document.createElement("ol"); list.className = "competitor-question-list";
    for (const item of questions.items) { const row = document.createElement("li"); const question = document.createElement("strong"); question.textContent = item.question; const answer = document.createElement("p"); answer.textContent = (item.answers || []).join("；") || "暂无回答样本"; row.append(question, answer); list.append(row); }
    competitorArchive.append(archiveGroup(`问大家 · ${(questions.items || []).length} 条`, list));
  }
  competitorArchive.hidden = false;
  competitorDetail.hidden = false;
  competitorCommandSummary.textContent = `${mainImages.length} 张主图、${skuImages.length} 张 SKU 图、${detailImages.length} 张详情图、${(reviews.items || []).length} 条评价`;
  competitorCommandBar.hidden = false;
}

function competitorMoney(value) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (Number.isFinite(numeric)) return `¥${numeric.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
  const text = String(value).trim();
  return /^[¥￥]/.test(text) ? text : `¥${text}`;
}

function competitorPaymentDisplay(value, currentPrice) {
  const text = String(value || "").trim();
  if (!text) return "";
  const numericPrice = Number(currentPrice);
  if (!Number.isFinite(numericPrice)) return text;
  const pricePrefix = String(numericPrice);
  if (!text.startsWith(pricePrefix)) return text;
  const remainder = text.slice(pricePrefix.length);
  return /^\d+(?:\.\d+)?(?:万|\+|人|已售)/.test(remainder) ? remainder : text;
}

function competitorTrendSummary(points) {
  const values = points.map((point) => Number(point.price_value)).filter(Number.isFinite);
  const current = values.at(-1);
  const previous = values.length > 1 ? values.at(-2) : null;
  return {
    current,
    previous,
    change: previous === null ? null : Number((current - previous).toFixed(2)),
    minimum: values.length ? Math.min(...values) : null,
    maximum: values.length ? Math.max(...values) : null,
  };
}

function competitorDateLabel(value, detailed = false) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "未知时间";
  return detailed
    ? date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

function filterCompetitorTrendPoints(points, days) {
  if (!days || points.length < 2) return points;
  const newest = new Date(points.at(-1).captured_at).getTime();
  if (!Number.isFinite(newest)) return points;
  const cutoff = newest - (days - 1) * 24 * 60 * 60 * 1000;
  const filtered = points.filter((point) => {
    const timestamp = new Date(point.captured_at).getTime();
    return !Number.isFinite(timestamp) || timestamp >= cutoff;
  });
  return filtered.length ? filtered : points.slice(-1);
}

function renderCompetitorPriceTrend(container, priceHistory, selectedDays = 30) {
  container.replaceChildren();
  const allPoints = Array.isArray(priceHistory?.points) ? priceHistory.points : [];
  const points = filterCompetitorTrendPoints(allPoints, selectedDays);
  const heading = document.createElement("div");
  heading.className = "competitor-trend-heading";
  const headingCopy = document.createElement("div");
  const title = document.createElement("h5"); title.textContent = priceHistory?.label || "价格趋势";
  const basis = document.createElement("p"); basis.textContent = priceHistory?.basis === "page_visible" ? "按每次采集时页面直接展示的价格统计，不等同于指定 SKU 到手价。" : "按已确认的目标 SKU 实价统计。";
  headingCopy.append(title, basis);
  const ranges = document.createElement("div"); ranges.className = "competitor-trend-ranges";
  for (const [label, days] of [["7天", 7], ["30天", 30], ["90天", 90], ["全部", null]]) {
    const button = document.createElement("button");
    button.type = "button"; button.className = "secondary"; button.textContent = label;
    button.classList.toggle("active", days === selectedDays);
    button.addEventListener("click", () => renderCompetitorPriceTrend(container, priceHistory, days));
    ranges.append(button);
  }
  heading.append(headingCopy, ranges);
  container.append(heading);

  if (!points.length) {
    const empty = document.createElement("div");
    empty.className = "competitor-trend-empty";
    empty.innerHTML = "<strong>还没有可绘制的价格记录</strong><span>完成下一次采集后，这里会开始形成价格曲线。</span>";
    container.append(empty);
    return;
  }

  const summary = competitorTrendSummary(points);
  const metrics = document.createElement("div"); metrics.className = "competitor-price-metrics";
  const changeText = summary.change === null ? "待下次采集" : `${summary.change > 0 ? "+" : ""}${competitorMoney(summary.change)}`;
  for (const [label, value, tone] of [
    ["当前", competitorMoney(summary.current), "current"],
    ["较上次", changeText, summary.change > 0 ? "up" : summary.change < 0 ? "down" : "flat"],
    ["区间最低", competitorMoney(summary.minimum), ""],
    ["区间最高", competitorMoney(summary.maximum), ""],
  ]) {
    const card = document.createElement("article"); if (tone) card.dataset.tone = tone;
    const caption = document.createElement("span"); caption.textContent = label;
    const valueNode = document.createElement("strong"); valueNode.textContent = value;
    card.append(caption, valueNode); metrics.append(card);
  }
  container.append(metrics);

  const chart = document.createElement("div"); chart.className = "competitor-trend-chart";
  const width = 820, height = 270, left = 58, right = 800, top = 24, bottom = 222;
  const values = points.map((point) => Number(point.price_value));
  let minimum = Math.min(...values), maximum = Math.max(...values);
  const padding = maximum === minimum ? Math.max(maximum * .04, 1) : (maximum - minimum) * .12;
  minimum -= padding; maximum += padding;
  const xFor = (index) => points.length === 1 ? (left + right) / 2 : left + (right - left) * index / (points.length - 1);
  const yFor = (value) => bottom - (bottom - top) * (value - minimum) / (maximum - minimum);
  const svg = createSvgElement("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${priceHistory?.label || "价格"}历史趋势` });
  for (let tick = 0; tick < 4; tick += 1) {
    const ratio = tick / 3;
    const y = top + (bottom - top) * ratio;
    const price = maximum - (maximum - minimum) * ratio;
    svg.append(createSvgElement("line", { x1: left, y1: y, x2: right, y2: y, class: "competitor-trend-grid" }));
    const label = createSvgElement("text", { x: left - 10, y: y + 4, "text-anchor": "end", class: "competitor-trend-axis" });
    label.textContent = `¥${Number(price.toFixed(2))}`; svg.append(label);
  }
  if (points.length > 1) {
    const path = points.map((point, index) => `${index ? "L" : "M"} ${xFor(index)} ${yFor(point.price_value)}`).join(" ");
    svg.append(createSvgElement("path", { d: path, class: "competitor-trend-line" }));
  }
  for (const [index, point] of points.entries()) {
    const dot = createSvgElement("circle", { cx: xFor(index), cy: yFor(point.price_value), r: 5, class: "competitor-trend-dot" });
    const tooltip = createSvgElement("title"); tooltip.textContent = `${competitorDateLabel(point.captured_at, true)} · ${competitorMoney(point.price_value)}`;
    dot.append(tooltip); svg.append(dot);
  }
  const labelIndexes = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
  for (const index of labelIndexes) {
    const label = createSvgElement("text", { x: xFor(index), y: bottom + 27, "text-anchor": "middle", class: "competitor-trend-axis" });
    label.textContent = competitorDateLabel(points[index].captured_at); svg.append(label);
  }
  chart.append(svg);
  if (points.length === 1) {
    const hint = document.createElement("p"); hint.textContent = "当前只有 1 次有效采集，暂时无法判断涨跌趋势。"; chart.append(hint);
  }
  container.append(chart);
}

function renderSkuPriceHistory(skuHistory) {
  if (!activeCompetitorPayload) return;
  competitorSkuForm.remove();
  competitorArchive.replaceChildren();
  const header = document.createElement("header"); header.className = "sku-price-detail-header";
  const back = document.createElement("button"); back.type = "button"; back.className = "secondary"; back.textContent = "← 返回竞品概览";
  back.addEventListener("click", () => renderCompetitorIntelligence(activeCompetitorPayload));
  const copy = document.createElement("div");
  const eyebrow = document.createElement("p"); eyebrow.className = "eyebrow"; eyebrow.textContent = "目标 SKU 价格历史";
  const title = document.createElement("h4"); title.textContent = skuHistory.label;
  copy.append(eyebrow, title); header.append(back, copy); competitorArchive.append(header);
  const trend = document.createElement("section"); trend.className = "competitor-price-panel sku-price-panel";
  renderCompetitorPriceTrend(trend, { ...skuHistory, basis: "target_sku", label: "目标 SKU 实价" }, 30);
  competitorArchive.append(trend);
}

function competitorFactCard(label, value) {
  const card = document.createElement("article");
  const caption = document.createElement("span"); caption.textContent = label;
  const content = document.createElement("strong"); content.textContent = value || "页面未提供";
  card.append(caption, content); return card;
}

function renderCompetitorIntelligence(payload) {
  activeCompetitorPayload = payload;
  const snapshot = payload.snapshot || {};
  const archive = snapshot.archive || {};
  const fields = archive.product_fields || {};
  const images = Array.isArray(archive.images) ? archive.images : [];
  const dimensions = archive.sku_catalog?.dimensions || [];
  const reviews = archive.reviews || {};
  const pageHistory = payload.history?.page_price || { basis: "page_visible", label: "页面可见价", points: [] };
  const skuHistories = payload.history?.sku_prices || [];
  const outboundUrl = payload.outbound_url || payload.record?.source_url || payload.record?.resolved_url || snapshot.page_url;
  competitorSkuForm.remove();
  competitorArchive.replaceChildren();

  const hero = document.createElement("header"); hero.className = "competitor-intelligence-hero";
  const imageUrl = snapshot.main_image_url || images.find((item) => item.kind === "main")?.url;
  if (imageUrl) {
    const image = document.createElement("img"); image.src = imageUrl; image.alt = snapshot.title || fields.title || "竞品主图"; hero.append(image);
  }
  const identity = document.createElement("div"); identity.className = "competitor-intelligence-identity";
  const eyebrow = document.createElement("p"); eyebrow.className = "eyebrow"; eyebrow.textContent = "竞品价格情报";
  const title = document.createElement("h4");
  if (outboundUrl) {
    const link = document.createElement("a"); link.href = outboundUrl; link.target = "_blank"; link.rel = "noopener";
    link.textContent = fields.title || snapshot.title || `商品 ${payload.item_id}`; title.append(link);
  } else title.textContent = fields.title || snapshot.title || `商品 ${payload.item_id}`;
  const meta = document.createElement("p"); meta.className = "competitor-intelligence-meta";
  meta.textContent = [fields.shop_name || snapshot.shop_name, `商品 ID ${payload.item_id}`, `更新于 ${displayTime(snapshot.captured_at)}`].filter(Boolean).join(" · ");
  identity.append(eyebrow, title, meta); hero.append(identity);
  if (outboundUrl) {
    const outbound = document.createElement("a"); outbound.className = "competitor-outbound-link"; outbound.href = outboundUrl; outbound.target = "_blank"; outbound.rel = "noopener"; outbound.textContent = "打开淘宝原页 ↗"; hero.append(outbound);
  }
  competitorArchive.append(hero);

  const facts = document.createElement("div"); facts.className = "competitor-product-facts competitor-summary-grid";
  const currentPagePrice = pageHistory.summary?.current;
  facts.append(
    competitorFactCard("页面可见价", competitorMoney(currentPagePrice ?? fields.price_text ?? snapshot.visible_price_text)),
    competitorFactCard("付款 / 销量", competitorPaymentDisplay(fields.payment_text || fields.sold_text || snapshot.sold_text, currentPagePrice)),
    competitorFactCard("发货地区", fields.origin_text),
    competitorFactCard("发货与物流", (fields.logistics || []).join(" · ") || snapshot.shop_shipping_text),
  );
  competitorArchive.append(facts);

  const tags = [...new Set([...(fields.promotions || []), ...(fields.services || []), ...(fields.logistics || []), ...(snapshot.services || [])].filter(Boolean))];
  if (tags.length) {
    const tagPanel = document.createElement("section"); tagPanel.className = "competitor-tag-panel";
    const label = document.createElement("strong"); label.textContent = "优惠与服务";
    const chips = document.createElement("div"); chips.className = "competitor-promotion-chips";
    for (const text of tags) { const chip = document.createElement("span"); chip.textContent = text; chips.append(chip); }
    tagPanel.append(label, chips); competitorArchive.append(tagPanel);
  }

  const pricePanel = document.createElement("section"); pricePanel.className = "competitor-price-panel";
  renderCompetitorPriceTrend(pricePanel, pageHistory, 30); competitorArchive.append(pricePanel);

  if (skuHistories.length || dimensions.length) {
    const skuSection = document.createElement("section"); skuSection.className = "competitor-sku-intelligence";
    const skuHeading = document.createElement("div"); skuHeading.className = "competitor-section-heading";
    const skuCopy = document.createElement("div");
    const skuTitle = document.createElement("h5"); skuTitle.textContent = "目标 SKU 价格";
    const skuHint = document.createElement("p"); skuHint.textContent = "每个已确认 SKU 单独形成价格历史，不与页面可见价混算。";
    skuCopy.append(skuTitle, skuHint); skuHeading.append(skuCopy); skuSection.append(skuHeading);
    if (skuHistories.length) {
      const list = document.createElement("div"); list.className = "competitor-sku-history-list";
      for (const skuHistory of skuHistories) {
        const row = document.createElement("article"); row.className = "competitor-sku-history-row";
        const copy = document.createElement("div");
        const name = document.createElement("strong"); name.textContent = skuHistory.label;
        const time = document.createElement("span"); time.textContent = `${skuHistory.points.length} 次采集 · 最近 ${competitorDateLabel(skuHistory.points.at(-1)?.captured_at, true)}`;
        copy.append(name, time);
        const price = document.createElement("strong"); price.className = "competitor-sku-latest-price"; price.textContent = competitorMoney(skuHistory.summary?.current);
        const open = document.createElement("button"); open.type = "button"; open.className = "secondary"; open.textContent = "查看价格历史";
        open.addEventListener("click", () => renderSkuPriceHistory(skuHistory));
        row.append(copy, price, open); list.append(row);
      }
      skuSection.append(list);
    }
    if (dimensions.length) {
      const captureHeading = document.createElement("div"); captureHeading.className = "sku-target-heading";
      const captureTitle = document.createElement("strong"); captureTitle.textContent = skuHistories.length ? "继续采集其他目标 SKU" : "选择目标 SKU（可选）";
      const captureCopy = document.createElement("span"); captureCopy.textContent = "只在需要确认具体规格实价时使用。";
      captureHeading.append(captureTitle, captureCopy); skuSection.append(captureHeading, competitorSkuForm);
    }
    competitorArchive.append(skuSection);
  }

  const counts = {
    main: images.filter((item) => item.kind === "main").length,
    sku: images.filter((item) => item.kind === "sku").length,
    detail: images.filter((item) => item.kind === "detail").length,
    review: (reviews.items || []).length,
  };
  const exportNote = document.createElement("section"); exportNote.className = "competitor-export-note";
  const exportCopy = document.createElement("div");
  const exportTitle = document.createElement("strong"); exportTitle.textContent = "完整素材已整理到 ZIP 资料包";
  const exportHint = document.createElement("span"); exportHint.textContent = `主图 ${counts.main} 张 · SKU 图 ${counts.sku} 张 · 详情图 ${counts.detail} 张 · 已保存评价 ${counts.review} 条；页面不再重复展开素材。`;
  exportCopy.append(exportTitle, exportHint);
  const exportLink = document.createElement("a"); exportLink.href = `/api/competitors/${payload.item_id}/export.zip`; exportLink.className = "record-action"; exportLink.textContent = "下载完整资料包 ZIP";
  exportNote.append(exportCopy, exportLink); competitorArchive.append(exportNote);

  competitorArchive.hidden = false;
  competitorDetail.hidden = false;
  competitorCommandSummary.textContent = `页面可见价 ${pageHistory.points?.length || 0} 次记录 · ${skuHistories.length} 个目标 SKU 历史`;
  competitorCommandBar.hidden = false;
}

function renderCompetitorArchive(prepared) {
  renderCompetitorIntelligence(prepared.snapshot ? prepared : {
    item_id: prepared.item_id,
    snapshot: { ...prepared, archive: prepared.product_archive || {} },
    outbound_url: prepared.page_url,
    history: { page_price: { basis: "page_visible", label: "页面可见价", points: [] }, sku_prices: [] },
  });
}

function setCompetitorCapturing(active) {
  if (competitorCaptureTimer) window.clearInterval(competitorCaptureTimer);
  competitorCaptureTimer = null;
  if (!active) return;
  const startedAt = Date.now();
  competitorCaptureTimer = window.setInterval(() => {
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    competitorMessage.textContent = `正在读取商品详情（已等待 ${seconds} 秒）。如看到扫码页，请先完成登录；最长等待约 90 秒。`;
  }, 1000);
}

async function prepareCompetitor(productUrl) {
  if (!productUrl) return;
  preparedCompetitorItemId = null;
  competitorDetail.hidden = true;
  competitorArchive.hidden = true;
  competitorCommandBar.hidden = true;
  competitorLoginHelp.hidden = true;
  prepareCompetitorButton.disabled = true;
  prepareCompetitorButton.textContent = "正在采集…";
  competitorMessage.textContent = "正在打开专属采集浏览器并读取商品详情，最长等待约 90 秒。";
  setCompetitorCapturing(true);
  try {
    const response = await fetch("/api/competitors/prepare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ product_url: productUrl }) });
    const prepared = await readResponseJson(response);
    setCompetitorCapturing(false);
    preparedCompetitorItemId = prepared.item_id;
    await loadCompetitorRecords();
    await openSavedCompetitor(prepared.item_id);
    competitorCaptureStatus.textContent = (prepared.dimensions || []).length ? "资料已保存，可选目标 SKU" : "商品资料已保存";
    competitorMessage.textContent = "采集完成：价格情报已更新，完整素材已整理进 ZIP。";
  } catch (error) {
    competitorMessage.textContent = error.message;
    competitorLoginHelp.hidden = !["taobao_browser_login_required", "taobao_login_required"].includes(error.code);
  } finally {
    setCompetitorCapturing(false);
    prepareCompetitorButton.disabled = false;
    prepareCompetitorButton.textContent = "识别并采集";
  }
}
function openCompetitorFromResult(result) { competitorUrlInput.value = canonicalProductUrl(result); showCompetitorView(); prepareCompetitor(competitorUrlInput.value); }
async function openMonitoredCompetitor(task) {
  competitorUrlInput.value = task.product_url || (task.item_id ? `https://item.taobao.com/item.htm?id=${task.item_id}` : "");
  preparedCompetitorItemId = null;
  competitorArchive.hidden = true;
  competitorCommandBar.hidden = true;
  competitorLoginHelp.hidden = true;
  renderSkuFields([]);
  showCompetitorView();
  competitorCaptureTitle.textContent = task.label || "竞品资料";
  competitorCaptureStatus.textContent = "正在读取已保存资料…";
  competitorMessage.textContent = "正在打开该监控商品的最新竞品资料。";
  try {
    const payload = await readResponseJson(await fetch(`/api/competitors/${task.item_id}`));
    const snapshot = payload.snapshot || {};
    const archive = snapshot.archive || {};
    const dimensions = archive.sku_catalog?.dimensions || [];
    preparedCompetitorItemId = String(task.item_id);
    renderSkuFields(dimensions);
    renderCompetitorIntelligence(payload);
    competitorCaptureTitle.textContent = snapshot.title || task.label || "竞品资料";
    competitorCaptureStatus.textContent = "已加载历史竞品资料";
    competitorMessage.textContent = "已打开监控商品的价格情报；完整素材可下载 ZIP。";
  } catch (error) {
    preparedCompetitorItemId = null;
    competitorArchive.hidden = true;
    competitorCommandBar.hidden = true;
    competitorCaptureStatus.textContent = "尚未采集详情";
    competitorMessage.textContent = "已带入商品链接。该商品尚未保存详情，请点击“抓取商品信息”建立竞品资料。";
  }
}
function collectMonitoredCompetitor(task) {
  openCompetitorFromResult(task);
}
competitorUrlForm.addEventListener("submit", (event) => { event.preventDefault(); prepareCompetitor(competitorUrlInput.value.trim()); });
reopenCollectorBrowserButton.addEventListener("click", () => prepareCompetitor(competitorUrlInput.value.trim()));
resumeCompetitorCaptureButton.addEventListener("click", () => prepareCompetitor(competitorUrlInput.value.trim()));
openCollectorAccountButton.addEventListener("click", async () => {
  openCollectorAccountButton.disabled = true;
  competitorMessage.textContent = "正在打开专属采集浏览器…";
  try {
    const result = await readResponseJson(await fetch("/api/collector/account-browser", { method: "POST" }));
    competitorMessage.textContent = result.message;
  } catch (error) { competitorMessage.textContent = error.message; }
  finally { openCollectorAccountButton.disabled = false; }
});
clearCollectorLoginButton.addEventListener("click", async () => {
  const confirmed = window.confirm("只清除本工具专属采集浏览器里的淘宝登录状态。\n\n请先关闭专属采集浏览器；系统默认浏览器和淘宝客户端不会受影响。确定继续吗？");
  if (!confirmed) return;
  clearCollectorLoginButton.disabled = true;
  competitorMessage.textContent = "正在清除本工具登录状态…";
  try {
    const result = await readResponseJson(await fetch("/api/collector/login-profile", { method: "DELETE" }));
    competitorMessage.textContent = `${result.message} 点击“打开采集账号”即可登录新账号。`;
  } catch (error) { competitorMessage.textContent = error.message; }
  finally { clearCollectorLoginButton.disabled = false; }
});
competitorSkuForm.addEventListener("submit", async (event) => {
  event.preventDefault(); if (!preparedCompetitorItemId) return;
  const selected_options = [...competitorSkuFields.querySelectorAll("select")].map((select) => ({ dimension: select.dataset.dimension, value: select.selectedOptions[0].dataset.value, index: Number(select.value) }));
  captureCompetitorSkuButton.disabled = true; captureCompetitorSkuButton.textContent = "正在读取实价…";
  try {
    const response = await fetch(`/api/competitors/${preparedCompetitorItemId}/capture`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ selected_options }) });
    await readResponseJson(response);
    await openSavedCompetitor(preparedCompetitorItemId);
    competitorCaptureStatus.textContent = "目标 SKU 已保存"; competitorMessage.textContent = "SKU 实价已保存，并已更新该 SKU 的独立价格历史。";
  } catch (error) { competitorMessage.textContent = error.message; }
  finally { captureCompetitorSkuButton.disabled = false; captureCompetitorSkuButton.textContent = "确认目标 SKU 并读取实价"; }
});
exportCompetitorPackageButton.addEventListener("click", () => {
  if (!preparedCompetitorItemId) return;
  window.location.assign(`/api/competitors/${preparedCompetitorItemId}/export.zip`);
  notifyExportStarted("竞品资料包 ZIP");
});

function monitorTaskTypeLabel(taskType) { return ({ competitor: "单品", shop: "店铺", keyword: "关键词" })[taskType] || taskType; }
function monitorRunStatusLabel(status) {
  return ({ success: "成功", partial: "部分失败", failed: "失败", skipped: "已跳过", running: "执行中" })[status] || status;
}
function monitorPriorityLabel(priority) { return priority === "high" ? "重点" : "关注"; }
function createMonitorTaskCard(task) {
  const row = document.createElement("li");
  row.className = `monitor-task-card ${task.task_type}`;
  if (task.task_type === "competitor" && task.image_url) {
    const image = document.createElement("img"); image.className = "monitor-task-thumb"; image.src = task.image_url; image.alt = task.label || "竞品主图"; image.loading = "lazy"; row.append(image);
  } else if (task.task_type === "shop") {
    const mark = document.createElement("span"); mark.className = "monitor-shop-mark"; mark.textContent = "店"; row.append(mark);
  }
  const copy = document.createElement("div"); copy.className = "monitor-task-copy";
  const type = document.createElement("span"); type.className = "monitor-type"; type.textContent = monitorTaskTypeLabel(task.task_type);
  let title;
  if (task.task_type === "competitor") {
    title = document.createElement("button"); title.type = "button"; title.className = "monitor-title-button"; title.textContent = task.label;
    title.addEventListener("click", () => openMonitoredCompetitor(task));
  } else if (task.task_type === "shop" && task.shop_url) {
    title = document.createElement("a"); title.className = "monitor-title-link"; title.href = task.shop_url; title.target = "_blank"; title.rel = "noreferrer"; title.textContent = task.label;
  } else {
    title = document.createElement("strong"); title.textContent = task.label;
  }
  const detail = document.createElement("small");
  if (task.task_type === "competitor") detail.textContent = [task.shop_name, task.price_text ? `¥${task.price_text}` : "", task.payment_text].filter(Boolean).join(" · ") || `商品ID ${task.item_id}`;
  else if (task.task_type === "shop") detail.textContent = task.captured_at ? `本次监测到 ${task.result_count || 0} 件 · ${displayTime(task.captured_at)}` : "等待首次采集并建立店铺商品基线";
  else detail.textContent = `每日采集 ${task.page_count || 1} 页 · ${task.keyword}`;
  copy.append(type, title, detail);
  if (task.task_type === "competitor" && task.item_id) {
    const id = document.createElement("span"); id.className = "monitor-task-id"; id.textContent = `商品ID ${task.item_id}`; copy.append(id);
  }
  if (task.task_type === "shop") {
    const recentItems = (task.recent_new_products || []).length ? task.recent_new_products : (task.preview_products || []);
    if (recentItems.length) {
    const recent = document.createElement("div"); recent.className = "shop-recent-new";
    const recentTitle = document.createElement("span"); recentTitle.className = "shop-recent-title";
    recentTitle.textContent = (task.recent_new_products || []).length
      ? `最近发现 ${task.recent_new_count || recentItems.length} 件新品`
      : `本次商品预览 · 前 ${recentItems.length} 件`;
    const products = document.createElement("div"); products.className = "shop-recent-products";
    for (const product of recentItems) {
      const link = document.createElement("a"); link.href = product.product_url || "#"; link.target = "_blank"; link.rel = "noreferrer"; link.title = product.title || "查看新品";
      if (product.image_url) { const image = document.createElement("img"); image.src = product.image_url; image.alt = product.title || "新品主图"; image.loading = "lazy"; link.append(image); }
      const productCopy = document.createElement("span"); productCopy.className = "shop-preview-copy";
      const name = document.createElement("b"); name.textContent = product.title || `商品 ${product.item_id}`; productCopy.append(name);
      if (product.price_text) { const price = document.createElement("em"); price.textContent = `¥${product.price_text}`; productCopy.append(price); }
      link.append(productCopy); products.append(link);
    }
    recent.append(recentTitle, products); copy.append(recent);
    }
  }
  const actions = document.createElement("div"); actions.className = "monitor-task-actions";
  if (task.task_type === "competitor") {
    const open = document.createElement("button"); open.type = "button"; open.className = "monitor-open-button"; open.textContent = "查看竞品资料";
    open.addEventListener("click", () => openMonitoredCompetitor(task)); actions.append(open);
    const collect = document.createElement("button"); collect.type = "button"; collect.className = "monitor-collect-button"; collect.textContent = "竞品采集";
    collect.title = "重新打开采集浏览器，抓取该商品的最新完整详情";
    collect.addEventListener("click", () => collectMonitoredCompetitor(task)); actions.append(collect);
  } else if (task.task_type === "shop" && task.shop_url) {
    const open = document.createElement("a"); open.className = "monitor-open-link"; open.href = task.shop_url; open.target = "_blank"; open.rel = "noreferrer"; open.textContent = "进入店铺 ↗"; actions.append(open);
  }
  const remove = document.createElement("button"); remove.type = "button"; remove.className = "text-button monitor-remove-button"; remove.textContent = "移除";
  remove.addEventListener("click", async () => {
    remove.disabled = true;
    try { await readResponseJson(await fetch(`/api/monitor/tasks/${task.id}`, { method: "DELETE" })); await loadMonitorCenter(); }
    catch (error) { monitorMessage.textContent = error.message; remove.disabled = false; }
  });
  actions.append(remove);
  row.append(copy, actions);
  return row;
}
function renderMonitorCenter(data) {
  const settings = data.settings || {};
  const tasks = data.tasks || [];
  const runs = data.runs || [];
  const changes = data.important_changes || [];
  const summary = data.monitor_summary || {};
  monitorRunTime.value = settings.run_time || "10:00";
  monitorEnabled.checked = Boolean(settings.enabled);
  monitorChangeCount.textContent = `${changes.length} 条`;
  monitorChangeCount.classList.toggle("active", changes.length > 0);
  monitorChangeMeta.textContent = summary.run_count_today
    ? `今天已执行 ${summary.run_count_today} 次 · 最近 ${displayTime(summary.latest_run_at)}`
    : (summary.latest_run_at ? `今天尚未执行 · 上次 ${displayTime(summary.latest_run_at)}` : "今天尚未执行监控。");
  monitorChangeList.replaceChildren();
  for (const change of changes) {
    const row = document.createElement("li");
    row.className = `monitor-change-item ${change.priority === "high" ? "high" : "medium"}`;
    const rail = document.createElement("div"); rail.className = "monitor-change-rail";
    const priority = document.createElement("span"); priority.className = "monitor-change-priority"; priority.textContent = monitorPriorityLabel(change.priority);
    const category = document.createElement("span"); category.className = "monitor-change-category"; category.textContent = change.category || "变化";
    rail.append(priority, category);
    const copy = document.createElement("div"); copy.className = "monitor-change-copy";
    const context = document.createElement("small"); context.textContent = `${monitorTaskTypeLabel(change.task_type)} · ${change.task_label || "监控项"}`;
    const title = document.createElement("strong"); title.textContent = change.title || change.task_label || "监控对象";
    const detail = document.createElement("p"); detail.textContent = change.summary || "检测到重要变化";
    const reason = document.createElement("span"); reason.textContent = change.reason || "建议打开原商品核对。";
    copy.append(context, title, detail, reason);
    row.append(rail, copy);
    if (change.product_url) {
      const link = document.createElement("a"); link.href = change.product_url; link.target = "_blank"; link.rel = "noreferrer"; link.textContent = "查看商品 ↗"; link.className = "monitor-change-link"; row.append(link);
    }
    monitorChangeList.append(row);
  }
  monitorChangeEmpty.hidden = changes.length > 0;
  const keywordTasks = tasks.filter((task) => task.task_type === "keyword");
  const competitorTasks = tasks.filter((task) => task.task_type === "competitor");
  const shopTasks = tasks.filter((task) => task.task_type === "shop");
  monitorKeywordPanel.hidden = keywordTasks.length === 0; monitorKeywordCount.textContent = `${keywordTasks.length} 项`; monitorKeywordList.replaceChildren(...keywordTasks.map(createMonitorTaskCard)); monitorKeywordEmpty.hidden = keywordTasks.length > 0;
  monitorCompetitorCount.textContent = `${competitorTasks.length} 项`; monitorCompetitorList.replaceChildren(...competitorTasks.map(createMonitorTaskCard)); monitorCompetitorEmpty.hidden = competitorTasks.length > 0;
  monitorShopCount.textContent = `${shopTasks.length} 项`; monitorShopList.replaceChildren(...shopTasks.map(createMonitorTaskCard)); monitorShopEmpty.hidden = shopTasks.length > 0;
  monitorRunList.replaceChildren();
  for (const run of runs) {
    const row = document.createElement("li");
    const copy = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = `${monitorRunStatusLabel(run.status)} · ${displayTime(run.started_at)}`;
    const detail = document.createElement("small"); detail.textContent = `${run.success_count} 项成功 · ${run.failure_count} 项失败${run.error_text ? ` · ${run.error_text}` : ""}`;
    copy.append(title, detail); row.append(copy); monitorRunList.append(row);
  }
  monitorRunEmpty.hidden = runs.length > 0;
}
async function loadMonitorCenter() {
  const data = await readResponseJson(await fetch("/api/monitor"));
  renderMonitorCenter(data);
  return data;
}

monitorKeywordButton.addEventListener("click", async () => {
  if (!openedProjectId) return;
  monitorKeywordButton.disabled = true;
  try {
    const page_count = Number(monitorPageCount.value || 1);
    const result = await readResponseJson(await fetch(`/api/projects/${openedProjectId}/monitor/keyword`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page_count }) }));
    searchMessage.textContent = result.message;
  } catch (error) { searchMessage.textContent = error.message; }
  finally { monitorKeywordButton.disabled = false; }
});
monitorCompetitorButton.addEventListener("click", async () => {
  if (!preparedCompetitorItemId) return;
  monitorCompetitorButton.disabled = true;
  try {
    const result = await readResponseJson(await fetch(`/api/competitors/${preparedCompetitorItemId}/monitor`, { method: "POST" }));
    competitorMessage.textContent = result.message;
  } catch (error) { competitorMessage.textContent = error.message; }
  finally { monitorCompetitorButton.disabled = false; }
});
manualShopMonitorForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const shopUrl = manualShopUrl.value.trim();
  if (!shopUrl) return;
  addManualShopMonitorButton.disabled = true;
  addManualShopMonitorButton.textContent = "正在添加…";
  manualShopMessage.textContent = "正在校验店铺链接…";
  try {
    const added = await readResponseJson(await fetch("/api/monitor/shop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shop_url: shopUrl }),
    }));
    manualShopMessage.textContent = "店铺已加入，正在打开淘宝采集浏览器建立基线…";
    const captured = await readResponseJson(await fetch(`/api/monitor/tasks/${added.task_id}/capture-shop`, { method: "POST" }));
    manualShopMessage.textContent = captured.message || "店铺基线采集完成";
    manualShopUrl.value = "";
    await loadMonitorCenter();
  } catch (error) {
    manualShopMessage.textContent = error.message;
    await loadMonitorCenter();
  } finally {
    addManualShopMonitorButton.disabled = false;
    addManualShopMonitorButton.textContent = "添加并采集";
  }
});
monitorScheduleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  saveMonitorScheduleButton.disabled = true;
  monitorMessage.textContent = "正在更新 Windows 定时任务…";
  try {
    const result = await readResponseJson(await fetch("/api/monitor/schedule", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: monitorEnabled.checked, run_time: monitorRunTime.value }),
    }));
    renderMonitorCenter({ settings: result.settings, tasks: [], runs: [] });
    await loadMonitorCenter();
    monitorMessage.textContent = monitorEnabled.checked ? `每日 ${monitorRunTime.value} 监控已启用。` : "每日监控已关闭。";
  } catch (error) { monitorMessage.textContent = error.message; }
  finally { saveMonitorScheduleButton.disabled = false; }
});
runMonitorNowButton.addEventListener("click", async () => {
  runMonitorNowButton.disabled = true;
  runMonitorNowButton.textContent = "正在执行…";
  monitorMessage.textContent = "正在依次采集监控项；如淘宝要求登录，请完成扫码。";
  try {
    const result = await readResponseJson(await fetch("/api/monitor/run-now", { method: "POST" }));
    renderMonitorCenter(result);
    monitorMessage.textContent = result.success ? "本次监控执行完成。" : "本次有采集失败，请查看执行记录。";
  } catch (error) { monitorMessage.textContent = error.message; }
  finally { runMonitorNowButton.disabled = false; runMonitorNowButton.textContent = "立即执行一次"; }
});

function selectedPreset() { return aiPresets.find((preset) => preset.id === aiPresetIdInput.value); }

function renderLicenseStatus(status) {
  const usable = Boolean(status.can_use);
  const isDevelopment = status.status === "development_bypass";
  const isCommunity = status.status === "community" || Boolean(status.is_community_build);
  if (licenseActivationBlock) licenseActivationBlock.hidden = isCommunity;
  if (isCommunity) {
    licenseStatusBadge.className = "license-status-badge active";
    licenseStatusBadge.textContent = "开源社区版";
    licenseStatusMessage.textContent = status.message || "开源社区版：全部本机功能可直接使用。";
    licensePlanLabel.textContent = status.plan_label || "开源社区版";
    licenseExpiresAt.textContent = status.expires_at_text || "长期有效";
    licenseRemainingDays.textContent = "不限";
    licenseDeviceSuffix.textContent = "—";
    if (licenseSettingsMessage) {
      licenseSettingsMessage.textContent = "开源社区版无需激活码；数据、图片与导出文件都只保存在你自己的电脑上。";
    }
    return;
  }
  licenseStatusBadge.className = `license-status-badge ${usable ? "active" : "inactive"}`;
  licenseStatusBadge.textContent = isDevelopment ? "开发模式" : usable ? "已激活" : status.status === "expired" ? "已到期" : "未激活";
  licenseStatusMessage.textContent = status.message || "";
  licensePlanLabel.textContent = status.plan_label || (isDevelopment ? "开发验收" : "尚未开通");
  licenseExpiresAt.textContent = status.expires_at_text || "—";
  licenseRemainingDays.textContent = status.expires_at ? `${status.remaining_days || 0} 天` : "—";
  licenseDeviceSuffix.textContent = status.installation_id_suffix || "—";
  licenseRequestCode.value = status.request_code || "";
  licenseRequestLabel.textContent = status.request_type === "renewal" ? "续期申请码" : "设备申请码";
  submitLicenseCodeButton.textContent = status.request_type === "renewal" ? "提交续期码" : "提交激活码";
  submitLicenseCodeButton.dataset.requestType = status.request_type || "activation";
}

async function loadLicenseStatus() {
  const status = await readResponseJson(await fetch("/api/license/status"));
  renderLicenseStatus(status);
  return status;
}

async function copyLicenseRequest() {
  const value = licenseRequestCode.value.trim();
  if (!value) { licenseSettingsMessage.textContent = "申请码尚未生成，请刷新状态。"; return; }
  try {
    await navigator.clipboard.writeText(value);
    licenseSettingsMessage.textContent = "申请码已复制，可以发给管理员生成激活码。";
  } catch (_) {
    licenseRequestCode.focus(); licenseRequestCode.select();
    document.execCommand("copy");
    licenseSettingsMessage.textContent = "申请码已复制。";
  }
}

async function submitLicenseCode() {
  const code = licenseActivationCode.value.trim();
  if (!code) { licenseSettingsMessage.textContent = "请先粘贴完整激活码。"; return; }
  const renewal = submitLicenseCodeButton.dataset.requestType === "renewal";
  submitLicenseCodeButton.disabled = true;
  licenseSettingsMessage.textContent = renewal ? "正在验证续期码…" : "正在验证激活码…";
  try {
    const status = await readResponseJson(await fetch(renewal ? "/api/license/redeem" : "/api/license/activate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    }));
    licenseActivationCode.value = "";
    renderLicenseStatus(status);
    licenseSettingsMessage.textContent = renewal ? "续期成功。" : "激活成功。";
  } catch (error) {
    licenseSettingsMessage.textContent = error.message;
  } finally {
    submitLicenseCodeButton.disabled = false;
  }
}
function renderAiProviders() {
  aiProviderOptions.replaceChildren();
  for (const preset of aiPresets) {
    const label = document.createElement("label"); label.className = "provider-option";
    const radio = document.createElement("input"); radio.type = "radio"; radio.name = "ai-provider"; radio.value = preset.id; radio.checked = preset.id === aiPresetIdInput.value;
    const copy = document.createElement("span"); const strong = document.createElement("strong"); strong.textContent = preset.name; const small = document.createElement("small"); small.textContent = preset.model; copy.append(strong, small); label.append(radio, copy);
    radio.addEventListener("change", () => { aiPresetIdInput.value = preset.id; aiKeyLabel.textContent = `${preset.name} API Key`; }); aiProviderOptions.append(label);
  }
}
async function loadAiSettings() {
  const response = await fetch("/api/settings/ai");
  if (response.status === 204) return;
  const settings = await readResponseJson(response); aiPresetIdInput.value = settings.preset_id || aiPresetIdInput.value; renderAiProviders(); aiSaveStatus.hidden = false; aiSaveProvider.textContent = `${settings.provider_name || "模型"} 已接入`; testAiSettingsButton.disabled = false;
}
async function loadAiPresets() {
  const data = await readResponseJson(await fetch("/api/settings/ai/presets")); aiPresets = data.presets || []; aiPresetIdInput.value = data.default_preset_id || aiPresetIdInput.value; renderAiProviders();
}
aiSettingsForm.addEventListener("submit", async (event) => {
  event.preventDefault(); saveAiSettingsButton.disabled = true;
  try {
    const settings = await readResponseJson(await fetch("/api/settings/ai", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ preset_id: aiPresetIdInput.value, api_key: aiApiKeyInput.value }) }));
    aiSaveStatus.hidden = false; aiSaveProvider.textContent = `${settings.provider_name || selectedPreset()?.name || "模型"} 已接入`; aiSettingsMessage.textContent = "模型配置已保存在本机。"; aiApiKeyInput.value = ""; testAiSettingsButton.disabled = false;
  } catch (error) { aiSettingsMessage.textContent = error.message; }
  finally { saveAiSettingsButton.disabled = false; }
});
testAiSettingsButton.addEventListener("click", async () => {
  testAiSettingsButton.disabled = true; aiSettingsMessage.textContent = "正在测试模型连接…";
  try { const result = await readResponseJson(await fetch("/api/settings/ai/test", { method: "POST" })); aiSettingsMessage.textContent = result.message || "模型连接正常。"; }
  catch (error) { aiSettingsMessage.textContent = error.message; }
  finally { testAiSettingsButton.disabled = false; }
});
copyLicenseRequestButton.addEventListener("click", copyLicenseRequest);
submitLicenseCodeButton.addEventListener("click", submitLicenseCode);
refreshLicenseStatusButton.addEventListener("click", () => loadLicenseStatus().catch((error) => { licenseSettingsMessage.textContent = error.message; }));

resultFilters.addEventListener("submit", (event) => event.preventDefault());
showViewFromHash();
Promise.all([loadProjects(), loadAiPresets().then(loadAiSettings)]).catch((error) => { formMessage.textContent = error.message; });
