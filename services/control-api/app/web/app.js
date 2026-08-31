"use strict";

const state = {
  token: "",
  status: null,
  inference: null,
  profiles: [],
  opportunities: [],
  tasks: [],
  audits: [],
  actions: [],
  campaigns: [],
  prospects: [],
  marketingResults: [],
  view: "overview",
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function node(tag, className = "", text = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== "") element.textContent = text;
  return element;
}

function button(text, className, action, id = "") {
  const element = node("button", className, text);
  element.type = "button";
  element.dataset.action = action;
  if (id) element.dataset.id = id;
  return element;
}

function empty(title, copy, panel = false) {
  const wrapper = node("div", `empty-state${panel ? " panel" : ""}`);
  wrapper.append(node("strong", "", title), node("p", "", copy));
  return wrapper;
}

function csv(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function formatDate(value) {
  if (!value) return "never";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function timeAgo(value) {
  if (!value) return "unknown time";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function titleCase(value) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function safeExternalUrl(value) {
  const parsed = new URL(value, window.location.origin);
  if (parsed.protocol !== "https:" && !(parsed.protocol === "http:" && parsed.hostname === "application-fixture")) throw new Error("Unsafe external URL was rejected");
  return parsed.toString();
}

async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const field = node("textarea");
  field.value = value;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.append(field);
  field.select();
  const copied = document.execCommand("copy");
  field.remove();
  if (!copied) throw new Error("Copy was blocked by the browser");
}

let toastTimer;
function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.hidden = true; }, 5000);
}

async function api(path, options = {}) {
  if (!state.token) throw new Error("Connect the workspace first");
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) {
    disconnect(false);
    throw new Error("The control token was rejected");
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    let details = null;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail?.message) {
        detail = body.detail.message;
        details = body.detail;
      }
    } catch (_error) { /* non-JSON error */ }
    const error = new Error(detail);
    error.details = details;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

function setConnection(connected, message = "") {
  const pulse = $("#rail-pulse");
  pulse.className = connected ? "pulse" : "pulse warning";
  $("#rail-status").textContent = connected ? "Control plane ready" : "Connect required";
  $("#rail-copy").textContent = connected ? "Live state is refreshing automatically." : "Your token stays only in memory until this tab reloads.";
  $("#connect-button").textContent = connected ? "Connected" : "Connect workspace";
  $("#metric-health").textContent = connected ? "Ready" : "Locked";
  $("#metric-health").className = connected ? "green" : "amber";
  $("#last-sync").textContent = message || (connected ? `Synced ${new Date().toLocaleTimeString()}` : "Not connected");
}

function disconnect(showMessage = true) {
  state.token = "";
  state.status = null;
  state.inference = null;
  state.profiles = [];
  state.opportunities = [];
  state.tasks = [];
  state.audits = [];
  state.actions = [];
  state.campaigns = [];
  state.prospects = [];
  state.marketingResults = [];
  setConnection(false);
  renderAll();
  if (showMessage) toast("Disconnected this browser tab");
}

async function loadData({ quiet = false } = {}) {
  if (!state.token) {
    setConnection(false);
    renderAll();
    return false;
  }
  try {
    const [status, inference, profiles, opportunities, tasks, audits, actions, campaigns, prospects, marketingResults] = await Promise.all([
      api("/v1/system/status"),
      api("/v1/inference/status"),
      api("/v1/career/profiles"),
      api("/v1/career/opportunities?limit=300"),
      api("/v1/tasks?limit=200"),
      api("/v1/audit-events?limit=100"),
      api("/v1/external-actions?limit=200"),
      api("/v1/marketing/campaigns"),
      api("/v1/marketing/prospects?limit=500"),
      api("/v1/marketing/results"),
    ]);
    Object.assign(state, { status, inference, profiles, opportunities, tasks, audits, actions, campaigns, prospects, marketingResults });
    setConnection(true);
    renderAll();
    return true;
  } catch (error) {
    setConnection(false, "Connection failed");
    if (!quiet) toast(error.message, true);
    return false;
  }
}

const viewCopy = {
  overview: ["Private agent workspace", "Turn intentions into <em>reviewable work.</em>", "Run continuous missions while every consequential action remains visible and controlled."],
  missions: ["Continuous operations", "Choose the <em>mission.</em>", "Activate, pause, or replace ongoing work without changing code."],
  opportunities: ["Career intelligence", "Review the <em>freshest fits.</em>", "Every result links back to the original job source and keeps its matching evidence."],
  campaigns: ["Measured distribution", "Grow with <em>evidence.</em>", "Discover relevant creators, review each contact, and adapt drafts only when outcomes support it."],
  approvals: ["Human control", "Decide before <em>impact.</em>", "Approve or reject high-risk tasks before they can enter execution."],
  tasks: ["Durable execution", "Assign and <em>inspect work.</em>", "Create safe one-off tasks and follow every transition in the audit trail."],
  settings: ["Security boundaries", "Keep the agent <em>private.</em>", "Understand where data lives, which tools are enabled, and what VPS hosting still requires."],
};

function switchView(view) {
  state.view = view;
  $$(".view").forEach((element) => element.classList.toggle("active", element.dataset.view === view));
  $$(".nav-item").forEach((element) => element.classList.toggle("active", element.dataset.viewTarget === view));
  const [eyebrow, title, lede] = viewCopy[view];
  $("#page-eyebrow").textContent = eyebrow;
  $("#page-title").replaceChildren();
  const parts = title.split(/<em>|<\/em>/);
  $("#page-title").append(document.createTextNode(parts[0]), node("em", "", parts[1] || ""), document.createTextNode(parts[2] || ""));
  $("#page-lede").textContent = lede;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderMetrics() {
  const activeMatches = state.opportunities.filter((item) => ["new", "shortlisted"].includes(item.status));
  const approvals = state.tasks.filter((item) => item.status === "pending_approval");
  const activeMissions = state.profiles.filter((item) => item.active);
  $("#metric-matches").textContent = state.token ? String(activeMatches.length) : "—";
  $("#metric-approvals").textContent = String(approvals.length);
  $("#metric-missions").textContent = String(activeMissions.length);
  $("#approval-badge").hidden = approvals.length === 0;
  $("#approval-badge").textContent = String(approvals.length);
}

function missionCard(profile, compact = false) {
  const card = node("article", `mission-card${profile.active ? "" : " inactive"}`);
  const row = node("div", "mission-row");
  const body = node("div");
  body.append(node("span", "tag", profile.active ? "Running mission" : "Paused mission"));
  body.append(node("h3", "", profile.name));
  body.append(node("p", "", `${profile.desired_titles.join(", ")} · ${profile.locations.join(", ") || "Any location"}`));
  const toggle = button("", `switch${profile.active ? " on" : ""}`, "toggle-profile", profile.id);
  toggle.setAttribute("aria-label", profile.active ? "Pause mission" : "Activate mission");
  row.append(body, toggle);
  card.append(row);
  const meta = node("div", "mission-meta");
  meta.append(
    node("span", "", `Freshness: ${profile.max_age_hours}h`),
    node("span", "", `Minimum score: ${profile.min_score}`),
    node("span", "", `Next scan: ${formatDate(profile.next_scan_at)}`),
    node("span", "", profile.resume_present ? `Résumé: ${profile.resume_characters.toLocaleString()} chars` : "Résumé missing"),
  );
  card.append(meta);
  if (!compact) {
    const actions = node("div", "mission-actions");
    actions.append(button("Scan now", "button compact", "scan-profile", profile.id), button("Edit mission", "text-button", "edit-profile", profile.id));
    card.append(actions);
  }
  return card;
}

function renderMissions() {
  const overview = $("#overview-missions");
  const full = $("#mission-list");
  overview.replaceChildren();
  full.replaceChildren();
  if (!state.profiles.length) {
    overview.append(empty("No live missions yet", "Create your first career mission to start scanning reviewed sources."));
    full.append(empty("No missions created", "Your first mission can watch fresh jobs and internships every six hours for free.", true));
    return;
  }
  state.profiles.slice(0, 2).forEach((profile) => overview.append(missionCard(profile, true)));
  state.profiles.forEach((profile) => full.append(missionCard(profile)));
}

function opportunityRow(opportunity) {
  const row = node("button", "job-row");
  row.type = "button";
  row.dataset.action = "view-opportunity";
  row.dataset.id = opportunity.id;
  const initials = opportunity.company.split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toUpperCase() || "J";
  row.append(node("span", "logo", initials));
  const copy = node("span");
  copy.append(node("strong", "", opportunity.title), node("small", "", `${opportunity.company} · ${opportunity.location || "Location not listed"} · ${timeAgo(opportunity.published_at)}`));
  row.append(copy, node("span", "score", `${opportunity.score}% fit`));
  return row;
}

function opportunityCard(opportunity) {
  const card = node("article", "panel opportunity-card");
  const top = node("div", "opportunity-top");
  const copy = node("div");
  copy.append(node("span", "company-line", `${opportunity.company} · ${titleCase(opportunity.source)}`), node("h3", "", opportunity.title), node("p", "", opportunity.location || "Location not listed"));
  top.append(copy, node("div", "opportunity-score", String(opportunity.score)));
  card.append(top);
  const meta = node("div", "opportunity-meta");
  meta.append(node("span", "chip status-chip", titleCase(opportunity.status)), node("span", "chip", timeAgo(opportunity.published_at)));
  if (opportunity.remote) meta.append(node("span", "chip", "Remote"));
  if (opportunity.employment_type) meta.append(node("span", "chip", titleCase(opportunity.employment_type)));
  if (opportunity.latest_draft) meta.append(node("span", "chip", "Draft ready"));
  card.append(meta);
  const reasons = node("ul", "reason-list");
  opportunity.score_reasons.slice(0, 3).forEach((reason) => reasons.append(node("li", "", reason)));
  card.append(reasons);
  const actions = node("div", "card-actions");
  actions.append(button("Inspect", "button compact", "view-opportunity", opportunity.id));
  if (opportunity.status !== "shortlisted") actions.append(button("Shortlist", "button compact", "shortlist-opportunity", opportunity.id));
  actions.append(button(opportunity.latest_draft ? "Regenerate draft" : "Generate private draft", "text-button", "draft-opportunity", opportunity.id));
  card.append(actions);
  return card;
}

function filteredOpportunities() {
  const profile = $("#opportunity-profile-filter").value;
  const status = $("#opportunity-status-filter").value;
  return state.opportunities.filter((item) => (!profile || item.profile_id === profile) && (!status || item.status === status));
}

function renderOpportunities() {
  const overview = $("#overview-opportunities");
  const full = $("#opportunity-list");
  overview.replaceChildren();
  full.replaceChildren();
  const active = state.opportunities.filter((item) => ["new", "shortlisted"].includes(item.status));
  if (!active.length) overview.append(empty("No fresh matches yet", state.profiles.length ? "Run a scan or wait for the next scheduled mission." : "Create a career mission first."));
  else active.slice(0, 5).forEach((item) => overview.append(opportunityRow(item)));
  const filtered = filteredOpportunities();
  $("#opportunity-count").textContent = `${filtered.length} opportunit${filtered.length === 1 ? "y" : "ies"}`;
  if (!filtered.length) full.append(empty("No opportunities in this view", "Change the filters or run a fresh scan.", true));
  else filtered.forEach((item) => full.append(opportunityCard(item)));
}

function renderProfileFilter() {
  const filter = $("#opportunity-profile-filter");
  const selected = filter.value;
  filter.replaceChildren(new Option("All missions", ""));
  state.profiles.forEach((profile) => filter.append(new Option(profile.name, profile.id)));
  if ([...filter.options].some((option) => option.value === selected)) filter.value = selected;
}

function renderApprovals() {
  const list = $("#approval-list");
  list.replaceChildren();
  const pending = state.tasks.filter((item) => item.status === "pending_approval");
  if (!pending.length) {
    list.append(empty("Nothing waiting", "High-impact tasks will stop here until you decide.", true));
    return;
  }
  pending.forEach((task) => {
    const card = node("article", "panel approval-card");
    const copy = node("div");
    const action = state.actions.find((item) => item.task_id === task.id);
    copy.append(node("h3", "", task.title), node("p", "", `${task.kind} · requested by ${task.requested_by} · ${formatDate(task.created_at)}`));
    if (action) copy.append(node("p", "", `${action.target_display} · expires ${formatDate(action.expires_at)} · hash ${action.context_hash.slice(0, 12)}…`));
    const actions = node("div", "card-actions");
    if (action) actions.append(button("Review exact action", "text-button", "review-action", action.id));
    actions.append(button("Reject", "button compact", "reject-task", task.id), button("Approve", "button compact primary", "approve-task", task.id));
    card.append(copy, actions);
    list.append(card);
  });
}

function showActionReview(id) {
  const action = state.actions.find((item) => item.id === id);
  if (!action) return;
  const root = $("#detail-content");
  root.replaceChildren(
    node("span", "tag amber-tag", "Exact approval packet"),
    node("h2", "", titleCase(action.action_type)),
    node("p", "", `${action.target_display} · expires ${formatDate(action.expires_at)}`),
  );
  const summary = node("dl", "action-summary");
  Object.entries(action.public_context).forEach(([key, value]) => {
    summary.append(node("dt", "", titleCase(key)), node("dd", "", typeof value === "string" ? value : JSON.stringify(value, null, 2)));
  });
  root.append(summary, node("p", "fine-print", `SHA-256 ${action.context_hash}. Approval is invalid if this packet changes.`));
  $("#detail-dialog").showModal();
}

function renderTasks() {
  const list = $("#task-list");
  list.replaceChildren();
  if (!state.tasks.length) {
    list.append(empty("No tasks loaded", state.token ? "Assign a task to begin." : "Connect to inspect durable task state."));
    return;
  }
  state.tasks.slice(0, 100).forEach((task) => {
    const row = node("article", "task-row");
    const copy = node("div");
    const title = node("h3");
    title.append(node("span", `status ${task.status}`, titleCase(task.status)), document.createTextNode(task.title));
    copy.append(title, node("p", "", `${task.kind} · attempt ${task.attempt_count}/${task.max_attempts} · ${timeAgo(task.created_at)}`));
    row.append(copy, button("Audit", "text-button", "view-audit", task.id));
    list.append(row);
  });
}

function renderActivity() {
  const list = $("#overview-activity");
  list.replaceChildren();
  if (!state.audits.length) {
    list.append(node("div", "event", ""));
    list.firstChild.append(node("strong", "", "No activity loaded"), node("p", "", state.token ? "Actions will appear here." : "Connect the workspace first."));
    return;
  }
  state.audits.slice(0, 8).forEach((event) => {
    const item = node("div", "event");
    item.append(node("strong", "", titleCase(event.action.replaceAll(".", " "))), node("p", "", `${event.actor_id} · ${event.execution_status} · ${timeAgo(event.occurred_at)}`));
    list.append(item);
  });
}

function marketingResult(campaignId) {
  return state.marketingResults.find((item) => item.campaign_id === campaignId) || {
    metrics: {},
    variants: [],
    suggestions: [],
  };
}

function renderMarketingMetrics() {
  const totals = state.marketingResults.reduce((summary, result) => {
    for (const key of ["discovered", "emails_sent", "replies", "initial_sent", "attributed_signups"]) {
      summary[key] += Number(result.metrics[key] || 0);
    }
    return summary;
  }, { discovered: 0, emails_sent: 0, replies: 0, initial_sent: 0, attributed_signups: 0 });
  const replyRate = totals.initial_sent ? (totals.replies / totals.initial_sent) * 100 : 0;
  $("#marketing-metric-found").textContent = totals.discovered.toLocaleString();
  $("#marketing-metric-sent").textContent = totals.emails_sent.toLocaleString();
  $("#marketing-metric-replies").textContent = `${replyRate.toFixed(1)}%`;
  $("#marketing-metric-signups").textContent = totals.attributed_signups.toLocaleString();
}

function campaignCard(campaign) {
  const result = marketingResult(campaign.id);
  const metrics = result.metrics;
  const card = node("article", `panel campaign-card${campaign.active ? "" : " inactive"}`);
  const top = node("div", "campaign-card-top");
  const copy = node("div");
  copy.append(
    node("span", "tag", campaign.active ? "Discovery running" : "Discovery paused"),
    node("h3", "", campaign.name),
    node("p", "", `${campaign.discovery_queries.join(" · ")} · ${campaign.min_subscribers.toLocaleString()}–${campaign.max_subscribers.toLocaleString()} subscribers`),
  );
  top.append(copy, node("span", "score", campaign.adaptive_mode ? "Adaptive drafts" : "Fixed A/B drafts"));
  card.append(top);

  const funnel = node("div", "funnel-list");
  const stages = [
    ["Found", metrics.discovered || 0],
    ["Introductions", metrics.initial_sent || 0],
    ["Replies", metrics.replies || 0],
    ["Positive", metrics.positive_replies || 0],
    ["Converted", metrics.converted || 0],
  ];
  const maximum = Math.max(1, ...stages.map((item) => Number(item[1])));
  stages.forEach(([label, value]) => {
    const row = node("div", "funnel-row");
    row.append(node("span", "", label));
    const track = node("span", "funnel-track");
    const level = Number(value) === 0 ? 0 : Math.max(1, Math.round((Number(value) / maximum) * 10));
    const fill = node("i", `funnel-fill level-${level}`);
    track.append(fill);
    row.append(track, node("strong", "", Number(value).toLocaleString()));
    funnel.append(row);
  });
  card.append(funnel);

  const learning = node("div", "campaign-learning");
  learning.append(node("strong", "", "Agent suggestions"));
  if (!result.suggestions.length) learning.append(node("p", "", "No change suggested yet. Keep recording real replies and conversions."));
  result.suggestions.slice(0, 3).forEach((suggestion) => {
    const item = node("div", `learning-item ${suggestion.priority}`);
    item.append(node("span", "", titleCase(suggestion.priority)), node("strong", "", suggestion.message), node("small", "", suggestion.evidence));
    learning.append(item);
  });
  card.append(learning);
  const actions = node("div", "card-actions");
  actions.append(
    button("Find creators", "button", "scan-campaign", campaign.id),
    button("Promotion kit", "button secondary", "promotion-kit", campaign.id),
    button("Edit campaign", "text-button", "edit-campaign", campaign.id),
  );
  card.append(actions, node("p", "fine-print", `Last discovery: ${formatDate(campaign.last_scan_at)} · next: ${formatDate(campaign.next_scan_at)}`));
  return card;
}

function renderCampaigns() {
  const list = $("#campaign-list");
  list.replaceChildren();
  if (!state.campaigns.length) {
    list.append(empty("No campaigns yet", "Create the KarixMC pilot, then add a restricted YouTube API key for official creator discovery.", true));
    return;
  }
  state.campaigns.forEach((campaign) => list.append(campaignCard(campaign)));
}

async function showPromotionKit(campaignId) {
  const content = $("#promotion-kit-content");
  content.replaceChildren(empty("Building kit", "Preparing deterministic copy and attribution links..."));
  $("#promotion-kit-dialog").showModal();
  try {
    const kit = await api(`/v1/marketing/campaigns/${encodeURIComponent(campaignId)}/promotion-kit`);
    content.replaceChildren();
    content.append(node("p", "promotion-reminder", kit.disclosure_reminder));

    const messages = node("section", "promotion-messages");
    messages.append(node("strong", "", "Reviewed campaign messages"));
    const list = node("ul");
    kit.key_messages.forEach((message) => list.append(node("li", "", message)));
    messages.append(list);
    content.append(messages);

    const fullKit = [];
    kit.assets.forEach((asset) => {
      const item = node("article", "promotion-asset");
      const heading = node("div", "promotion-asset-head");
      const copy = node("div");
      copy.append(node("span", "tag", asset.channel), node("h3", "", asset.title));
      const copyButton = node("button", "text-button", "Copy asset");
      copyButton.type = "button";
      const copyValue = `${asset.title}\n\n${asset.body}`;
      copyButton.addEventListener("click", async () => {
        try {
          await copyText(copyValue);
          toast(`${asset.channel} asset copied`);
        } catch (error) { toast(error.message, true); }
      });
      heading.append(copy, copyButton);
      item.append(
        heading,
        node("pre", "promotion-copy", asset.body),
        node("p", "fine-print", asset.guidance),
      );
      content.append(item);
      fullKit.push(`${asset.channel}\n${asset.title}\n\n${asset.body}\n\nGuidance: ${asset.guidance}`);
    });

    const allButton = node("button", "button primary", "Copy complete kit");
    allButton.type = "button";
    allButton.addEventListener("click", async () => {
      try {
        await copyText(`${kit.campaign_name}\n\n${fullKit.join("\n\n---\n\n")}`);
        toast("Complete promotion kit copied");
      } catch (error) { toast(error.message, true); }
    });
    const actions = node("div", "dialog-actions");
    actions.append(allButton);
    content.append(actions);
  } catch (error) {
    content.replaceChildren(empty("Could not build promotion kit", error.message));
  }
}

function renderMarketingFilters() {
  const filter = $("#marketing-campaign-filter");
  const selected = filter.value;
  filter.replaceChildren(new Option("All campaigns", ""));
  state.campaigns.forEach((campaign) => filter.append(new Option(campaign.name, campaign.id)));
  if ([...filter.options].some((option) => option.value === selected)) filter.value = selected;
}

function filteredProspects() {
  const campaignId = $("#marketing-campaign-filter").value;
  const status = $("#marketing-status-filter").value;
  return state.prospects.filter((item) => (!campaignId || item.campaign_id === campaignId) && (!status || item.status === status));
}

function prospectCard(prospect) {
  const campaign = state.campaigns.find((item) => item.id === prospect.campaign_id);
  const card = node("article", `panel prospect-card${prospect.suppressed_at ? " suppressed" : ""}`);
  const top = node("div", "prospect-card-top");
  const copy = node("div");
  copy.append(
    node("span", "company-line", `${titleCase(prospect.platform)} · ${campaign?.name || "Unknown campaign"}`),
    node("h3", "", prospect.display_name),
    node("p", "", prospect.audience_size === null ? "Audience size unavailable" : `${prospect.audience_size.toLocaleString()} audience`),
  );
  top.append(copy, node("div", "opportunity-score", String(prospect.relevance_score)));
  card.append(top);
  const meta = node("div", "opportunity-meta");
  meta.append(node("span", "chip status-chip", titleCase(prospect.status)));
  meta.append(node("span", "chip", prospect.contact_authorized_at ? "Contact reviewed" : "Contact review needed"));
  if (prospect.latest_message) meta.append(node("span", "chip", `${titleCase(prospect.latest_message.stage)} · ${titleCase(prospect.latest_message.action_status)}`));
  card.append(meta);
  if (prospect.latest_content_title) {
    const content = node("p", "prospect-evidence", `Recent match: ${prospect.latest_content_title}`);
    card.append(content);
  }
  const reasons = node("ul", "reason-list");
  prospect.relevance_reasons.slice(0, 3).forEach((reason) => reasons.append(node("li", "", reason)));
  card.append(reasons);
  const links = node("div", "prospect-links");
  const profile = node("a", "text-button", "Open public profile");
  try { profile.href = safeExternalUrl(prospect.profile_url); }
  catch (_error) { profile.removeAttribute("href"); profile.textContent = "Unsafe profile URL rejected"; }
  profile.target = "_blank";
  profile.rel = "noopener noreferrer";
  links.append(profile);
  if (prospect.contact_email) links.append(node("span", "fine-print", prospect.contact_email));
  card.append(links);

  const actions = node("div", "card-actions");
  if (!prospect.suppressed_at) actions.append(button(prospect.contact_authorized_at ? "Edit evidence" : "Review contact", "button", "edit-prospect", prospect.id));
  if (prospect.contact_authorized_at && ["discovered", "qualified"].includes(prospect.status)) {
    const blocked = prospect.latest_message && ["pending_approval", "queued", "executing", "succeeded", "ambiguous"].includes(prospect.latest_message.action_status) && prospect.latest_message.stage === "initial";
    if (!blocked) actions.append(button("Prepare introduction", "button primary", "plan-marketing-initial", prospect.id));
  }
  const answerRetryable = prospect.latest_message?.stage === "question_reply"
    && ["failed", "cancelled", "expired"].includes(prospect.latest_message.action_status);
  const newerQuestion = prospect.latest_outcome?.classification === "question"
    && (!prospect.latest_message || new Date(prospect.latest_outcome.created_at) > new Date(prospect.latest_message.created_at));
  const canAnswer = prospect.status === "question"
    && (prospect.latest_message?.stage !== "question_reply" || answerRetryable || newerQuestion);
  if (canAnswer) actions.append(button("Write manual answer", "button primary", "reply-prospect", prospect.id));
  if (prospect.status === "declined_unpaid") {
    const paidExists = prospect.latest_message?.stage === "paid_offer" && ["pending_approval", "queued", "executing", "succeeded", "ambiguous"].includes(prospect.latest_message.action_status);
    if (!paidExists) actions.append(button("Prepare final paid option", "button primary", "plan-marketing-paid", prospect.id));
  }
  if (prospect.sent_message_count > 0 && !["suppressed", "bounced"].includes(prospect.status)) actions.append(button(prospect.status === "converted" ? "Update results" : "Record reply or result", "text-button", "outcome-prospect", prospect.id));
  card.append(actions);
  if (prospect.suppression_reason) card.append(node("p", "notice", prospect.suppression_reason));
  return card;
}

function renderProspects() {
  const list = $("#prospect-list");
  list.replaceChildren();
  const prospects = filteredProspects();
  $("#marketing-prospect-count").textContent = `${prospects.length} creator${prospects.length === 1 ? "" : "s"}`;
  if (!prospects.length) {
    list.append(empty("No creators in this view", "Run discovery, add a prospect, or change the filters.", true));
    return;
  }
  prospects.forEach((prospect) => list.append(prospectCard(prospect)));
}

function renderInferenceStatus() {
  const latest = state.inference?.latest;
  const route = $("#inference-route");
  const usage = $("#inference-usage");
  if (!route || !usage) return;
  if (!latest) {
    route.textContent = "No verified route has run yet.";
    usage.textContent = "Configure the ignored .env key, restart the job worker, then run a harmless smoke or generate a draft.";
    return;
  }
  const model = latest.selected_model || "no model selected";
  route.textContent = `${titleCase(latest.provider)} · ${model} · ${titleCase(latest.status)}`;
  const remote = state.inference.openrouter_requests_today || 0;
  const local = state.inference.local_successes_today || 0;
  usage.textContent = `${remote} OpenRouter request${remote === 1 ? "" : "s"} today · ${local} local run${local === 1 ? "" : "s"} · ${state.inference.cost_today} recorded credits · ${latest.privacy_mode}`;
}

function renderAll() {
  renderMetrics();
  renderProfileFilter();
  renderMissions();
  renderOpportunities();
  renderApprovals();
  renderTasks();
  renderActivity();
  renderMarketingMetrics();
  renderMarketingFilters();
  renderCampaigns();
  renderProspects();
  renderInferenceStatus();
}

function profilePayload(profile, overrides = {}) {
  return {
    name: profile.name,
    candidate_name: profile.candidate_name,
    desired_titles: profile.desired_titles,
    skills: profile.skills,
    required_keywords: profile.required_keywords,
    excluded_keywords: profile.excluded_keywords,
    locations: profile.locations,
    remote_only: profile.remote_only,
    employment_types: profile.employment_types,
    max_age_hours: profile.max_age_hours,
    min_score: profile.min_score,
    schedule_minutes: profile.schedule_minutes,
    source_config: profile.source_config,
    application_identity: null,
    resume_text: null,
    auto_prepare: profile.auto_prepare,
    auto_prepare_min_score: profile.auto_prepare_min_score,
    max_auto_prepare_per_scan: profile.max_auto_prepare_per_scan,
    active: profile.active,
    actor: "dashboard:user",
    ...overrides,
  };
}

function openProfileDialog(profile = null) {
  if (!state.token) return $("#connect-dialog").showModal();
  const form = $("#profile-form");
  form.reset();
  form.elements.profile_id.value = profile?.id || "";
  $("#profile-dialog-title").textContent = profile ? "Edit career mission" : "Create a job-hunt mission";
  $("#resume-help").textContent = profile?.resume_present ? `A ${profile.resume_characters.toLocaleString()} character résumé is stored. Leave blank to keep it.` : "Paste plain text. Stored privately; never sent to job sources.";
  if (profile) {
    for (const name of ["name", "candidate_name", "max_age_hours", "min_score", "schedule_minutes", "auto_prepare_min_score", "max_auto_prepare_per_scan"]) form.elements[name].value = profile[name];
    for (const name of ["desired_titles", "skills", "required_keywords", "excluded_keywords", "locations"]) form.elements[name].value = profile[name].join(", ");
    form.elements.remote_only.checked = profile.remote_only;
    form.elements.active.checked = profile.active;
    form.elements.auto_prepare.checked = profile.auto_prepare;
    form.elements.arbeitnow.checked = Boolean(profile.source_config.arbeitnow);
    form.elements.ashby_boards.value = (profile.source_config.ashby_boards || []).join(", ");
    form.elements.greenhouse_boards.value = (profile.source_config.greenhouse_boards || []).join(", ");
    form.elements.lever_boards.value = (profile.source_config.lever_boards || []).join(", ");
    for (const name of ["first_name", "last_name", "email", "phone", "identity_location", "linkedin_url", "github_url"]) {
      const identityName = name === "identity_location" ? "location" : name;
      form.elements[name].value = profile.application_identity?.[identityName] || "";
    }
    $$("input[name='employment_types']", form).forEach((input) => { input.checked = profile.employment_types.includes(input.value); });
  }
  $("#profile-dialog").showModal();
}

async function saveProfile(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.profile_id.value;
  const identityValues = {
    first_name: form.elements.first_name.value.trim(),
    last_name: form.elements.last_name.value.trim(),
    email: form.elements.email.value.trim(),
    phone: form.elements.phone.value.trim() || null,
    location: form.elements.identity_location.value.trim() || null,
    linkedin_url: form.elements.linkedin_url.value.trim() || null,
    github_url: form.elements.github_url.value.trim() || null,
  };
  const applicationIdentity = identityValues.email ? identityValues : null;
  const payload = {
    name: form.elements.name.value.trim(),
    candidate_name: form.elements.candidate_name.value.trim(),
    desired_titles: csv(form.elements.desired_titles.value),
    skills: csv(form.elements.skills.value),
    required_keywords: csv(form.elements.required_keywords.value),
    excluded_keywords: csv(form.elements.excluded_keywords.value),
    locations: csv(form.elements.locations.value),
    remote_only: form.elements.remote_only.checked,
    employment_types: $$("input[name='employment_types']:checked", form).map((input) => input.value),
    max_age_hours: Number(form.elements.max_age_hours.value),
    min_score: Number(form.elements.min_score.value),
    schedule_minutes: Number(form.elements.schedule_minutes.value),
    source_config: { arbeitnow: form.elements.arbeitnow.checked, ashby_boards: csv(form.elements.ashby_boards.value), greenhouse_boards: csv(form.elements.greenhouse_boards.value), lever_boards: csv(form.elements.lever_boards.value) },
    application_identity: applicationIdentity,
    resume_text: form.elements.resume_text.value || (id ? null : ""),
    auto_prepare: form.elements.auto_prepare.checked,
    auto_prepare_min_score: Number(form.elements.auto_prepare_min_score.value),
    max_auto_prepare_per_scan: Number(form.elements.max_auto_prepare_per_scan.value),
    active: form.elements.active.checked,
    ...(id ? { actor: "dashboard:user" } : { requested_by: "dashboard:user" }),
  };
  try {
    await api(id ? `/v1/career/profiles/${id}` : "/v1/career/profiles", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
    $("#profile-dialog").close();
    toast(id ? "Career mission updated" : "Career mission created");
    await loadData({ quiet: true });
    switchView("missions");
  } catch (error) { toast(error.message, true); }
}

function openCampaignDialog(campaign = null) {
  if (!state.token) return $("#connect-dialog").showModal();
  const form = $("#campaign-form");
  form.reset();
  form.elements.campaign_id.value = campaign?.id || "";
  $("#campaign-dialog-title").textContent = campaign ? "Edit creator campaign" : "Create the KarixMC creator pilot";
  if (campaign) {
    for (const name of [
      "name", "sender_name", "product_name", "product_url", "privacy_url",
      "product_summary", "target_audience", "viewer_offer", "creator_offer",
      "paid_offer_details", "relevance_language", "region_code", "min_subscribers",
      "max_subscribers", "max_video_age_days", "results_per_query", "schedule_hours",
    ]) form.elements[name].value = campaign[name] ?? "";
    form.elements.discovery_queries.value = campaign.discovery_queries.join(", ");
    form.elements.paid_offer_enabled.checked = campaign.paid_offer_enabled;
    form.elements.adaptive_mode.checked = campaign.adaptive_mode;
    form.elements.active.checked = campaign.active;
  }
  $("#campaign-dialog").showModal();
}

async function saveCampaign(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.campaign_id.value;
  const payload = {
    name: form.elements.name.value.trim(),
    product_name: form.elements.product_name.value.trim(),
    product_url: form.elements.product_url.value.trim(),
    privacy_url: form.elements.privacy_url.value.trim(),
    product_summary: form.elements.product_summary.value.trim(),
    target_audience: form.elements.target_audience.value.trim(),
    viewer_offer: form.elements.viewer_offer.value.trim(),
    creator_offer: form.elements.creator_offer.value.trim(),
    paid_offer_enabled: form.elements.paid_offer_enabled.checked,
    paid_offer_details: form.elements.paid_offer_details.value.trim() || null,
    sender_name: form.elements.sender_name.value.trim(),
    discovery_queries: csv(form.elements.discovery_queries.value),
    relevance_language: form.elements.relevance_language.value.trim(),
    region_code: form.elements.region_code.value.trim().toUpperCase() || null,
    min_subscribers: Number(form.elements.min_subscribers.value),
    max_subscribers: Number(form.elements.max_subscribers.value),
    max_video_age_days: Number(form.elements.max_video_age_days.value),
    results_per_query: Number(form.elements.results_per_query.value),
    schedule_hours: Number(form.elements.schedule_hours.value),
    adaptive_mode: form.elements.adaptive_mode.checked,
    active: form.elements.active.checked,
    ...(id ? { actor: "dashboard:marketing" } : { requested_by: "dashboard:marketing" }),
  };
  try {
    await api(id ? `/v1/marketing/campaigns/${id}` : "/v1/marketing/campaigns", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
    $("#campaign-dialog").close();
    toast(id ? "Creator campaign updated" : "Creator campaign created");
    await loadData({ quiet: true });
    switchView("campaigns");
  } catch (error) { toast(error.message, true); }
}

function populateCampaignSelect(select, selected = "") {
  select.replaceChildren(new Option("Choose a campaign", ""));
  state.campaigns.forEach((campaign) => select.append(new Option(campaign.name, campaign.id)));
  select.value = selected;
}

function openProspectDialog(prospect = null) {
  if (!state.token) return $("#connect-dialog").showModal();
  if (!state.campaigns.length) {
    toast("Create a creator campaign first", true);
    return openCampaignDialog();
  }
  const form = $("#prospect-form");
  form.reset();
  form.elements.prospect_id.value = prospect?.id || "";
  populateCampaignSelect(form.elements.campaign_id, prospect?.campaign_id || state.campaigns[0].id);
  form.elements.campaign_id.disabled = Boolean(prospect);
  form.elements.platform.disabled = Boolean(prospect);
  $$(".new-prospect-only", form).forEach((element) => { element.hidden = Boolean(prospect); });
  $("#prospect-dialog-title").textContent = prospect ? "Review creator contact evidence" : "Add a creator prospect";
  if (prospect) {
    form.elements.platform.value = prospect.platform;
    form.elements.display_name.value = prospect.display_name;
    form.elements.profile_url.value = prospect.profile_url;
    form.elements.audience_size.value = prospect.audience_size ?? "";
    form.elements.contact_email.value = prospect.contact_email || "";
    form.elements.contact_source_url.value = prospect.contact_source_url || "";
    form.elements.contact_basis_note.value = prospect.contact_basis_note || "";
    form.elements.authorize_contact.checked = Boolean(prospect.contact_authorized_at);
  }
  $("#prospect-dialog").showModal();
}

async function saveProspect(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.prospect_id.value;
  const shared = {
    display_name: form.elements.display_name.value.trim(),
    profile_url: form.elements.profile_url.value.trim(),
    audience_size: form.elements.audience_size.value ? Number(form.elements.audience_size.value) : null,
    contact_email: form.elements.contact_email.value.trim() || null,
    contact_source_url: form.elements.contact_source_url.value.trim() || null,
    contact_basis_note: form.elements.contact_basis_note.value.trim() || null,
    authorize_contact: form.elements.authorize_contact.checked,
  };
  const payload = id ? { ...shared, actor: "dashboard:marketing" } : {
    ...shared,
    campaign_id: form.elements.campaign_id.value,
    platform: form.elements.platform.value,
    latest_content_title: form.elements.latest_content_title.value.trim() || null,
    latest_content_url: form.elements.latest_content_url.value.trim() || null,
    requested_by: "dashboard:marketing",
  };
  try {
    await api(id ? `/v1/marketing/prospects/${id}` : "/v1/marketing/prospects", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
    $("#prospect-dialog").close();
    toast(id ? "Creator evidence updated" : "Creator prospect added");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
}

async function scanCampaign(id) {
  try {
    await api(`/v1/marketing/campaigns/${id}/scan`, { method: "POST" });
    toast("Official YouTube creator discovery queued");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
}

async function planMarketingEmail(id, stage, subject = null, body = null) {
  try {
    await api(`/v1/marketing/prospects/${id}/email-plan`, { method: "POST", body: JSON.stringify({ stage, subject, body, actor: "dashboard:marketing", approval_window_minutes: 1440 }) });
    $("#marketing-reply-dialog").close();
    toast("Exact creator email is waiting for approval");
    await loadData({ quiet: true });
    switchView("approvals");
  } catch (error) { toast(error.message, true); }
}

function openMarketingReply(prospect) {
  const form = $("#marketing-reply-form");
  form.reset();
  form.elements.prospect_id.value = prospect.id;
  form.elements.subject.value = `Re: ${prospect.display_name} × KarixMC`;
  $("#marketing-reply-dialog").showModal();
}

function openMarketingOutcome(prospect) {
  const form = $("#marketing-outcome-form");
  form.reset();
  form.elements.prospect_id.value = prospect.id;
  if (prospect.status === "interested") form.elements.classification.value = "promotion_published";
  if (prospect.status === "converted") form.elements.classification.value = "converted";
  $("#marketing-outcome-dialog").showModal();
}

async function saveMarketingOutcome(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.prospect_id.value;
  const payload = {
    classification: form.elements.classification.value,
    note: form.elements.note.value.trim() || null,
    promotion_url: form.elements.promotion_url.value.trim() || null,
    attributed_views: Number(form.elements.attributed_views.value),
    attributed_clicks: Number(form.elements.attributed_clicks.value),
    attributed_signups: Number(form.elements.attributed_signups.value),
    attributed_server_owners: Number(form.elements.attributed_server_owners.value),
    viewer_points_issued: Number(form.elements.viewer_points_issued.value),
    actor: "dashboard:marketing",
  };
  try {
    await api(`/v1/marketing/prospects/${id}/outcomes`, { method: "POST", body: JSON.stringify(payload) });
    $("#marketing-outcome-dialog").close();
    toast(payload.classification === "do_not_contact" || payload.classification === "bounced" ? "Contact permanently suppressed" : "Creator outcome recorded");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
}

async function toggleProfile(id) {
  const profile = state.profiles.find((item) => item.id === id);
  if (!profile) return;
  try {
    await api(`/v1/career/profiles/${id}`, { method: "PUT", body: JSON.stringify(profilePayload(profile, { active: !profile.active })) });
    toast(profile.active ? "Mission paused" : "Mission activated");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
}

async function scanProfile(id) {
  try {
    await api(`/v1/career/profiles/${id}/scan`, { method: "POST" });
    toast("Fresh-job scan queued");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
}

async function updateOpportunity(id, status) {
  try {
    await api(`/v1/career/opportunities/${id}`, { method: "PATCH", body: JSON.stringify({ status, actor: "dashboard:user" }) });
    toast(`Opportunity marked ${status}`);
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
}

async function draftOpportunity(id) {
  try {
    await api(`/v1/career/opportunities/${id}/draft`, { method: "POST" });
    toast("Résumé-tailored draft queued on the verified free route");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
}

async function preflightOpportunity(id) {
  try {
    await api(`/v1/career/opportunities/${id}/preflight`, { method: "POST" });
    toast("Sandboxed application-form inspection queued");
    $("#detail-dialog").close();
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
}

function showApplicationAnswers(id, fields) {
  const form = $("#application-answer-form");
  form.reset();
  form.elements.opportunity_id.value = id;
  const container = $("#application-answer-fields");
  container.replaceChildren();
  fields.forEach((field) => {
    const label = node("label");
    label.append(node("span", "", field.label));
    let input;
    if (field.type === "checkbox") {
      input = document.createElement("input");
      input.type = "checkbox";
      label.className = "checkbox-row";
    } else if (field.options?.length) {
      input = document.createElement("select");
      input.append(new Option("Choose an answer", ""));
      field.options.forEach((option) => input.append(new Option(option, option)));
    } else {
      input = document.createElement(field.type === "textarea" ? "textarea" : "input");
    }
    input.dataset.fieldKey = field.key;
    input.required = true;
    label.append(input);
    container.append(label);
  });
  $("#application-answer-dialog").showModal();
}

async function planOpportunity(id, answers = {}) {
  try {
    await api(`/v1/career/opportunities/${id}/submit-plan`, { method: "POST", body: JSON.stringify({ answers, actor: "dashboard:career", approval_window_minutes: 60 }) });
    $("#detail-dialog").close();
    $("#application-answer-dialog").close();
    toast("Exact application packet is waiting for approval");
    await loadData({ quiet: true });
    switchView("approvals");
  } catch (error) {
    if (error.details?.missing_fields?.length) showApplicationAnswers(id, error.details.missing_fields);
    else toast(error.message, true);
  }
}

function showEmailDialog(id) {
  const opportunity = state.opportunities.find((item) => item.id === id);
  if (!opportunity) return;
  const form = $("#email-action-form");
  form.reset();
  form.elements.opportunity_id.value = id;
  form.elements.subject.value = `Application follow-up — ${opportunity.title}`;
  form.elements.body.value = `Hello,\n\nI recently applied for the ${opportunity.title} role at ${opportunity.company}. I would welcome the opportunity to discuss how my experience fits the position.\n\nBest regards`;
  $("#email-action-dialog").showModal();
}

function showOpportunity(id) {
  const opportunity = state.opportunities.find((item) => item.id === id);
  if (!opportunity) return;
  const root = $("#detail-content");
  root.replaceChildren(node("span", "tag", `${titleCase(opportunity.source)} · ${opportunity.score}% fit`), node("h2", "", opportunity.title), node("p", "", `${opportunity.company} · ${opportunity.location || "Location not listed"} · ${formatDate(opportunity.published_at)}`));
  const reasons = node("ul", "reason-list");
  opportunity.score_reasons.forEach((reason) => reasons.append(node("li", "", reason)));
  root.append(reasons, node("div", "detail-description", opportunity.description || "No description supplied by source."));
  if (opportunity.latest_draft) {
    const draft = opportunity.latest_draft;
    const box = node("section", "draft-box");
    box.append(node("span", "tag", "Private application draft"), node("h3", "", "Fit summary"), node("p", "", draft.fit_summary || ""));
    const evidence = node("ul");
    (draft.evidence || []).forEach((item) => evidence.append(node("li", "", item)));
    box.append(node("h3", "", "Evidence to emphasize"), evidence, node("h3", "", "Cover letter"), node("p", "", draft.cover_letter || ""));
    if ((draft.honest_gaps || []).length) {
      const gaps = node("ul");
      draft.honest_gaps.forEach((item) => gaps.append(node("li", "", item)));
      box.append(node("h3", "", "Honest gaps"), gaps);
    }
    root.append(box);
  }
  if (opportunity.latest_preflight) {
    const preflight = opportunity.latest_preflight;
    root.append(node("p", preflight.blocked_reason ? "notice" : "fine-print", preflight.blocked_reason ? `Browser adapter needs user handling: ${titleCase(preflight.blocked_reason)}` : `${preflight.fields.length} form fields inspected · final control “${preflight.submit_label}”`));
  }
  if (opportunity.latest_action) root.append(node("p", "fine-print", `Latest external action: ${titleCase(opportunity.latest_action.status)}`));
  const actions = node("div", "card-actions");
  const source = node("a", "button primary", "Open official application");
  try { source.href = safeExternalUrl(opportunity.apply_url); }
  catch (_error) { source.removeAttribute("href"); source.textContent = "Unsafe source URL rejected"; }
  source.target = "_blank";
  source.rel = "noopener noreferrer";
  actions.append(source, button("Generate private draft", "button", "draft-opportunity", id), button("Inspect application form", "button", "preflight-opportunity", id));
  if (opportunity.latest_draft && opportunity.latest_preflight && !opportunity.latest_preflight.blocked_reason) actions.append(button("Prepare exact submission", "button primary", "plan-opportunity", id));
  actions.append(button("Prepare follow-up email", "text-button", "email-opportunity", id), button("Mark applied after manual submission", "text-button", "applied-opportunity", id), button("Dismiss", "text-button danger-text", "dismiss-opportunity", id));
  root.append(actions);
  $("#detail-dialog").showModal();
}

async function decideTask(id, decision) {
  try {
    await api(`/v1/tasks/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, actor: "dashboard:approver", reason: "Decision recorded in Hermes Command Center" }) });
    toast(`Task ${decision}`);
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
}

async function showAudit(id) {
  const task = state.tasks.find((item) => item.id === id);
  $("#audit-title").textContent = task?.title || "Task history";
  const list = $("#audit-list");
  list.replaceChildren(empty("Loading", "Fetching durable audit events..."));
  $("#audit-dialog").showModal();
  try {
    const events = await api(`/v1/audit-events?task_id=${encodeURIComponent(id)}&limit=100`);
    list.replaceChildren();
    events.forEach((event) => {
      const item = node("div", "event");
      item.append(node("strong", "", titleCase(event.action.replaceAll(".", " "))), node("p", "", `${formatDate(event.occurred_at)} · ${event.actor_type}/${event.actor_id} · ${event.execution_status}`));
      list.append(item);
    });
    if (!events.length) list.append(empty("No audit events", "This task has no recorded events."));
  } catch (error) { list.replaceChildren(empty("Could not load audit", error.message)); }
}

async function assignTask(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const kind = form.elements.kind.value;
  const payload = kind === "foundation.wait" ? { seconds: Number(form.elements.seconds.value) } : { message: form.elements.message.value };
  try {
    await api("/v1/tasks", { method: "POST", body: JSON.stringify({ title: form.elements.title.value, kind, payload, risk_level: "low", requested_by: form.elements.requested_by.value, idempotency_key: `dashboard-${crypto.randomUUID()}` }) });
    toast("Task assigned");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
}

document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-view-target], [data-view-jump], [data-action]");
  if (!target) return;
  if (target.dataset.viewTarget) return switchView(target.dataset.viewTarget);
  if (target.dataset.viewJump) return switchView(target.dataset.viewJump);
  const { action, id } = target.dataset;
  if (action === "new-profile") return openProfileDialog();
  if (action === "edit-profile") return openProfileDialog(state.profiles.find((item) => item.id === id));
  if (action === "toggle-profile") return toggleProfile(id);
  if (action === "scan-profile") return scanProfile(id);
  if (action === "view-opportunity") return showOpportunity(id);
  if (action === "shortlist-opportunity") return updateOpportunity(id, "shortlisted");
  if (action === "dismiss-opportunity") { $("#detail-dialog").close(); return updateOpportunity(id, "dismissed"); }
  if (action === "applied-opportunity") { $("#detail-dialog").close(); return updateOpportunity(id, "applied"); }
  if (action === "draft-opportunity") { $("#detail-dialog").close(); return draftOpportunity(id); }
  if (action === "preflight-opportunity") return preflightOpportunity(id);
  if (action === "plan-opportunity") return planOpportunity(id);
  if (action === "email-opportunity") return showEmailDialog(id);
  if (action === "new-campaign") return openCampaignDialog();
  if (action === "edit-campaign") return openCampaignDialog(state.campaigns.find((item) => item.id === id));
  if (action === "scan-campaign") return scanCampaign(id);
  if (action === "promotion-kit") return showPromotionKit(id);
  if (action === "new-prospect") return openProspectDialog();
  if (action === "edit-prospect") return openProspectDialog(state.prospects.find((item) => item.id === id));
  if (action === "plan-marketing-initial") return planMarketingEmail(id, "initial");
  if (action === "plan-marketing-paid") return planMarketingEmail(id, "paid_offer");
  if (action === "reply-prospect") return openMarketingReply(state.prospects.find((item) => item.id === id));
  if (action === "outcome-prospect") return openMarketingOutcome(state.prospects.find((item) => item.id === id));
  if (action === "review-action") return showActionReview(id);
  if (action === "approve-task") return decideTask(id, "approved");
  if (action === "reject-task") return decideTask(id, "rejected");
  if (action === "view-audit") return showAudit(id);
});

$("#connect-button").addEventListener("click", () => $("#connect-dialog").showModal());
$("#settings-connect").addEventListener("click", () => $("#connect-dialog").showModal());
$("#disconnect-button").addEventListener("click", () => disconnect());
$("#connect-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = $("#token-input").value.trim();
  state.token = token;
  try {
    const connected = await loadData();
    if (!connected) throw new Error("Could not connect");
    $("#token-input").value = "";
    $("#connect-dialog").close();
    toast("Workspace connected");
  } catch (error) {
    disconnect(false);
    toast(error.message, true);
  }
});
$("#profile-form").addEventListener("submit", saveProfile);
$("#campaign-form").addEventListener("submit", saveCampaign);
$("#prospect-form").addEventListener("submit", saveProspect);
$("#marketing-outcome-form").addEventListener("submit", saveMarketingOutcome);
$("#marketing-reply-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  await planMarketingEmail(form.elements.prospect_id.value, "question_reply", form.elements.subject.value, form.elements.body.value);
});
$("#application-answer-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const answers = {};
  $$('[data-field-key]', form).forEach((input) => {
    answers[input.dataset.fieldKey] = input.type === "checkbox" ? input.checked : input.value;
  });
  await planOpportunity(form.elements.opportunity_id.value, answers);
});
$("#email-action-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await api("/v1/external-actions/email", { method: "POST", body: JSON.stringify({ recipient: form.elements.recipient.value, subject: form.elements.subject.value, body: form.elements.body.value, opportunity_id: form.elements.opportunity_id.value || null, actor: "dashboard:career", approval_window_minutes: 60 }) });
    $("#email-action-dialog").close();
    $("#detail-dialog").close();
    toast("Exact email is waiting for approval");
    await loadData({ quiet: true });
    switchView("approvals");
  } catch (error) { toast(error.message, true); }
});
$("#task-form").addEventListener("submit", assignTask);
$("#task-form").elements.kind.addEventListener("change", (event) => {
  const waiting = event.target.value === "foundation.wait";
  $("#task-message-field").hidden = waiting;
  $("#task-seconds-field").hidden = !waiting;
});
$("#refresh-button").addEventListener("click", () => loadData());
$("#opportunity-profile-filter").addEventListener("change", renderOpportunities);
$("#opportunity-status-filter").addEventListener("change", renderOpportunities);
$("#marketing-campaign-filter").addEventListener("change", renderProspects);
$("#marketing-status-filter").addEventListener("change", renderProspects);
$("#scan-now-button").addEventListener("click", async () => {
  const profiles = state.profiles.filter((item) => item.active);
  if (!profiles.length) return toast("Activate at least one career mission first", true);
  for (const profile of profiles) await scanProfile(profile.id);
});

renderAll();
setConnection(false);
setInterval(() => { if (state.token) loadData({ quiet: true }); }, 15000);
