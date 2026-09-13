"use strict";

const state = {
  token: "",
  browserSession: false,
  csrfToken: "",
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
  workflows: [],
  plans: [],
  readiness: null,
  communications: null,
  view: "overview",
};

function isConnected() {
  return Boolean(state.token || state.browserSession);
}

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
  if (!isConnected()) throw new Error("Connect the workspace first");
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  const method = String(options.method || "GET").toUpperCase();
  if (state.browserSession && !["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("X-Hermes-CSRF", state.csrfToken);
  }
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  if (response.status === 401 || response.status === 403) {
    disconnect(false);
    throw new Error("The private browser session was rejected");
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    let details = null;
    try {
      const body = await response.json();
      if (Array.isArray(body.detail)) {
        const issues = body.detail.slice(0, 8).map((issue) => {
          const field = (issue.loc || []).filter((part) => typeof part === "string" && /^[a-z_]{1,60}$/i.test(part) && part !== "body").join(".");
          const messages = { missing: "This field is required.", string_too_short: "Add more detail to this field.", string_too_long: "Shorten this value.", int_parsing: "Enter a whole number.", greater_than_equal: "Increase this value to the allowed minimum.", less_than_equal: "Reduce this value to the allowed maximum.", url_parsing: "Enter a complete web address.", uuid_parsing: "Select a saved item.", literal_error: "Choose one of the available options.", extra_forbidden: "Remove this unsupported field." };
          return { field, message: messages[issue.type] || "Check this value and try again." };
        });
        detail = issues.map((issue) => `${titleCase(issue.field.replaceAll(".", " ")) || "Form"}: ${issue.message}`).join(" ");
        details = { validation: issues };
      } else if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail?.message) {
        detail = body.detail.message;
        details = body.detail;
      }
    } catch (_error) { /* non-JSON error */ }
    const error = new Error(detail);
    error.details = details;
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

function setConnection(connected, message = "") {
  const pulse = $("#rail-pulse");
  pulse.className = connected ? "pulse" : "pulse warning";
  $("#rail-status").textContent = connected ? "Workspace connected" : "Connect required";
  $("#rail-copy").textContent = connected ? "Live state is refreshing automatically." : "Launch with the helper for automatic private authentication.";
  $("#connect-button").textContent = connected ? "Connected" : "Connect workspace";
  $("#metric-health").textContent = connected ? "Connected" : "Locked";
  $("#metric-health").className = connected ? "green" : "amber";
  $("#last-sync").textContent = message || (connected ? `Synced ${new Date().toLocaleTimeString()}` : "Not connected");
}

function disconnect(showMessage = true) {
  state.token = "";
  state.browserSession = false;
  state.csrfToken = "";
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
  state.workflows = [];
  state.plans = [];
  state.readiness = null;
  state.communications = null;
  selectedPlanId = null;
  $("#workflow-dialog").close();
  setConnection(false);
  renderAll();
  if (showMessage) toast("Disconnected this browser tab");
}

async function logoutBrowserSession() {
  if (state.browserSession) {
    try {
      await api("/v1/auth/logout", { method: "POST" });
    } catch (_error) { /* the local state is cleared even if the session expired */ }
  }
  disconnect();
}

async function initializeConnection() {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const bootstrap = fragment.get("bootstrap");
  if (bootstrap !== null) {
    window.history.replaceState(null, document.title, `${window.location.pathname}${window.location.search}`);
  }

  try {
    let response;
    if (bootstrap && /^[A-Za-z0-9_-]{32,128}$/.test(bootstrap)) {
      response = await fetch("/v1/auth/browser-session", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: bootstrap }),
      });
    } else {
      response = await fetch("/v1/auth/session", { credentials: "same-origin" });
    }
    if (!response.ok) throw new Error("No active browser session");
    const session = await response.json();
    if (session.mode !== "browser_session" || !session.csrf_token) {
      throw new Error("No browser session was returned");
    }
    state.browserSession = true;
    state.csrfToken = session.csrf_token;
    await loadData();
    if (bootstrap) toast("Private browser session connected automatically");
  } catch (_error) {
    disconnect(false);
  }
}

async function loadData({ quiet = false } = {}) {
  if (!isConnected()) {
    setConnection(false);
    renderAll();
    return false;
  }
  try {
    const [status, inference, profiles, opportunities, tasks, audits, actions, campaigns, prospects, marketingResults, workflows, plans, readiness, communications] = await Promise.all([
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
      api("/v1/workflows"),
      api("/v1/plans"),
      api("/v1/readiness/features"),
      api("/v1/communications/status"),
    ]);
    Object.assign(state, { status, inference, profiles, opportunities, tasks, audits, actions, campaigns, prospects, marketingResults, workflows, plans, readiness, communications });
    $("#connection-notice").hidden = true;
    setConnection(true);
    renderAll();
    return true;
  } catch (error) {
    setConnection(false, "Connection failed");
    $("#connection-notice").textContent = "Could not refresh the workspace. Your form edits are kept. Check the connection, then use Refresh to try again.";
    $("#connection-notice").hidden = false;
    if (!quiet) toast(error.message, true);
    return false;
  }
}

const viewCopy = {
  overview: ["", "Your next step, <em>made clear.</em>", "Give Hermes a goal, review its plan, and follow the work from here."],
  goals: ["", "A goal becomes <em>a plan.</em>", "Describe what you need. Review the proposed steps before any of them start."],
  readiness: ["", "Know what is <em>ready to use.</em>", "Configuration, recorded evidence, and the next setup step in one place."],
  missions: ["Continuous operations", "Choose the <em>mission.</em>", "Activate, pause, or replace ongoing work without changing code."],
  workflows: ["Coordinated autonomy", "Plan. Execute. <em>Verify.</em>", "Turn a multi-step objective into durable work with dependencies, result checks, and a clear stopping point."],
  opportunities: ["", "Your <em>job inbox.</em>", "Compare fresh matches, prepare truthful drafts, and decide what to apply for."],
  campaigns: ["Measured distribution", "Grow with <em>evidence.</em>", "Discover relevant creators, review each contact, and adapt drafts only when outcomes support it."],
  approvals: ["Human control", "Decide before <em>impact.</em>", "Approve or reject high-risk tasks before they can enter execution."],
  tasks: ["Durable execution", "Assign and <em>inspect work.</em>", "Create safe one-off tasks and follow every transition in the audit trail."],
  settings: ["", "Settings <em>and help.</em>", "Manage your private connection and understand how models, discovery, and approvals work."],
};

function switchView(view, { history = true, focus = true } = {}) {
  if (!Object.hasOwn(viewCopy, view)) return;
  state.view = view;
  $$(".view").forEach((element) => element.classList.toggle("active", element.dataset.view === view));
  $$(".nav-item").forEach((element) => {
    element.classList.toggle("active", element.dataset.viewTarget === view);
    if (element.dataset.viewTarget === view) element.setAttribute("aria-current", "page");
    else element.removeAttribute("aria-current");
  });
  const [, title, lede] = viewCopy[view];
  $("#page-title").replaceChildren();
  const parts = title.split(/<em>|<\/em>/);
  $("#page-title").append(document.createTextNode(parts[0]), node("em", "", parts[1] || ""), document.createTextNode(parts[2] || ""));
  $("#page-lede").textContent = lede;
  if (history && window.location.hash !== `#view=${view}`) window.history.pushState({ view }, "", `#view=${view}`);
  if (focus) $("#page-title").focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

const navigationItems = [
  { label: "Start here", description: "Your next action and recent work", view: "overview" },
  { label: "Goal planner", description: "Describe a goal, review a proposal, start its steps", view: "goals" },
  { label: "Workflows", description: "Run recipes and follow dependent steps", view: "workflows" },
  { label: "Career missions", description: "Create and schedule job searches", view: "missions" },
  { label: "Job inbox", description: "Review matches, drafts, and application forms", view: "opportunities" },
  { label: "Creator campaigns", description: "Discover creators and prepare outreach", view: "campaigns" },
  { label: "Approvals", description: "Review each exact email or application", view: "approvals" },
  { label: "Feature readiness", description: "Setup requirements and recorded verification", view: "readiness" },
  { label: "Tasks & history", description: "Inspect task results and audit events", view: "tasks" },
  { label: "Settings & help", description: "Private connection and model routing", view: "settings" },
  { label: "Create a career mission", description: "Set target roles, skills, and locations", action: "new-profile" },
  { label: "Create a creator campaign", description: "Define a product and audience", action: "new-campaign" },
  { label: "Try a local planning demo", description: "Fixed example, no model or external service", action: "goal-demo" },
];
const guidanceActions = new Set(["new-profile", "new-campaign", "new-prospect", "goal-demo"]);
let commandMatches = [];
let commandIndex = 0;
let selectedPlanId = null;
let goalSubmission = null;
const adoptingPlans = new Set();

function drawIcons() {
  const paths = {
    home: "M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9",
    goal: "M4 20V4m0 0h14l-3 5 3 5H4",
    workflow: "M4 4h6v6H4zM14 14h6v6h-6zM7 10v7h7M10 7h7v7",
    search: "M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13Zm5-1 5 5",
    inbox: "M4 4h16l2 10v6H2v-6L4 4Zm-2 10h6l2 3h4l2-3h6",
    people: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM2 21v-2a7 7 0 0 1 14 0v2M17 4a4 4 0 0 1 0 8m2 3a6 6 0 0 1 3 5",
    check: "m5 12 4 4L19 6M21 12v8H3V4h12",
    readiness: "M12 3 3 7v6c0 4 9 8 9 8s9-4 9-8V7l-9-4Zm-4 9 3 3 5-6",
    history: "M3 10a9 9 0 1 1 1 7M3 3v7h7M12 7v6l4 2",
    settings: "M4 7h16M4 17h16M8 4v6M16 14v6",
    menu: "M4 6h16M4 12h16M4 18h16",
  };
  $$('[data-icon]').forEach((holder) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    for (const [key, value] of Object.entries({ viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.6", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(key, value);
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", paths[holder.dataset.icon] || paths.menu);
    svg.append(path);
    holder.replaceChildren(svg);
  });
}

function openCommand() {
  const dialog = $("#command-dialog");
  if (dialog.open) return;
  $("#command-search").value = "";
  renderCommands();
  dialog.showModal();
  $("#command-search").focus();
}

function renderCommands() {
  const query = $("#command-search").value.trim().toLowerCase();
  commandMatches = navigationItems.filter((item) => `${item.label} ${item.description}`.toLowerCase().includes(query));
  commandIndex = 0;
  const list = $("#command-results");
  list.replaceChildren();
  commandMatches.forEach((item, index) => {
    const entry = button("", "command-result", "run-command", String(index));
    entry.id = `command-option-${index}`;
    entry.setAttribute("role", "option");
    entry.append(node("strong", "", item.label), node("small", "", item.description));
    list.append(entry);
  });
  if (!commandMatches.length) list.append(empty("No matching pages or actions", "Try “jobs”, “plan”, “email”, or “setup”."));
  selectCommand(0);
}

function selectCommand(index) {
  commandIndex = Math.max(0, Math.min(index, commandMatches.length - 1));
  $$(".command-result").forEach((item, position) => item.setAttribute("aria-selected", String(position === commandIndex)));
  const selected = $(`#command-option-${commandIndex}`);
  if (selected) {
    $("#command-search").setAttribute("aria-activedescendant", selected.id);
    selected.scrollIntoView({ block: "nearest" });
  } else $("#command-search").removeAttribute("aria-activedescendant");
}

function runCommand(index) {
  const command = commandMatches[index];
  if (!command) return;
  $("#command-dialog").close();
  if (command.view) return switchView(command.view);
  runGuidanceAction(command.action);
}

function runGuidanceAction(action) {
  if (action === "new-profile") return openProfileDialog();
  if (action === "new-campaign") return openCampaignDialog();
  if (action === "new-prospect") return openProspectDialog();
  if (action === "goal-demo") { switchView("goals"); fillGoalExample("demo"); }
}

function restoreView() {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  if (fragment.has("bootstrap")) return;
  const view = fragment.get("view") || "overview";
  switchView(Object.hasOwn(viewCopy, view) ? view : "overview", { history: false, focus: false });
}

function renderNextAction() {
  const target = $("#next-action");
  target.replaceChildren();
  const approvalCount = state.tasks.filter((task) => task.status === "pending_approval").length;
  const readyPlans = state.plans.filter((plan) => plan.status === "ready");
  const running = state.workflows.filter((workflow) => ["running", "cancelling"].includes(workflow.status));
  let title = "Start with a small win";
  let copy = "Try a local example to see a proposal turn into checked, traceable work. It needs no model or provider account.";
  let label = "Try the local demo";
  let view = "goals";
  let action = "goal-demo";
  if (!isConnected()) { title = "Connect your private workspace"; copy = "Open Hermes with the dashboard launcher to sign in automatically, or use manual recovery login."; label = "Connect workspace"; action = "connect-workspace"; }
  else if (approvalCount) { title = `${approvalCount} action${approvalCount === 1 ? " needs" : "s need"} your review`; copy = "Check the exact recipient, destination, and contents before allowing an email or application to proceed."; label = "Review approvals"; view = "approvals"; action = ""; }
  else if (readyPlans.length) { title = "A proposal is ready to review"; copy = "Inspect its scope, steps, and limitations. Work starts only when you choose Start plan."; label = "Review the proposal"; action = ""; selectedPlanId ||= readyPlans[0].id; }
  else if (running.length) { title = "Your workflows are in progress"; copy = "Follow each step and its result checks. You can request a stop at any time."; label = "Follow the work"; view = "workflows"; action = ""; }
  else if (state.opportunities.some((item) => item.status === "new")) { title = "Fresh matches are waiting"; copy = "Compare your new job matches, shortlist the relevant ones, then prepare a draft or a reviewed plan."; label = "Open job inbox"; view = "opportunities"; action = ""; }
  target.append(node("h2", "", title), node("p", "", copy));
  const actions = node("div", "card-actions");
  const primary = button(label, "button primary", action || "navigate", view);
  actions.append(primary, button("Explore features", "text-button", "navigate", "readiness"));
  target.append(actions);
}

function renderReadiness() {
  const list = $("#feature-list");
  const open = new Set($$("details[open]", list).map((element) => element.dataset.feature));
  list.replaceChildren();
  const features = state.readiness?.features || [];
  if (!features.length) { list.append(empty("Feature status is not loaded", isConnected() ? "Refresh to load configuration checks and recorded evidence." : "Connect your workspace to see setup requirements and recorded results.")); return; }
  features.forEach((feature) => {
    const status = ["verified", "configured", "needs_setup", "unavailable"].includes(feature.status) ? feature.status : "unavailable";
    const row = node("article", "feature-row");
    const heading = node("div", "feature-heading");
    heading.append(node("h2", "", feature.title), node("span", `status ${status}`, titleCase(status)));
    const main = node("div", "feature-main");
    main.append(heading, node("p", "", feature.summary), node("p", "feature-reason", feature.reason || "No recorded proof is available yet."));
    const details = node("details", "feature-details");
    details.dataset.feature = feature.id;
    details.open = open.has(feature.id);
    details.append(node("summary", "", "Setup and evidence"));
    const requirements = node("ul", "requirements");
    (feature.requirements || []).forEach((requirement) => {
      const item = node("li", requirement.met ? "met" : "missing");
      item.append(node("span", "", requirement.met ? "Present" : "Needed"), document.createTextNode(requirement.label));
      requirements.append(item);
    });
    details.append(requirements);
    if (feature.evidence) {
      details.append(node("p", "field-help", `Recorded check: ${formatDate(feature.evidence.completed_at)}. This proves that recorded run; it does not guarantee future availability.`));
      if (feature.evidence.task_id) details.append(button("Inspect recorded task", "text-button", "view-audit", feature.evidence.task_id));
      if (feature.evidence.check_id) details.append(node("p", "field-help", `Check: ${titleCase(feature.evidence.check_id.replaceAll("-", " "))}`));
      if (state.readiness.last_report?.stale) details.append(node("p", "field-help", "This report is more than 24 hours old. Run a fresh check before relying on it."));
    } else details.append(node("p", "field-help", "No successful check is recorded here yet. A configured connection still needs an end-to-end check."));
    main.append(details);
    row.append(main);
    const next = feature.next_action;
    if (next && Object.hasOwn(viewCopy, next.view)) {
      const action = guidanceActions.has(next.action) ? next.action : "navigate";
      row.append(button(next.label || "Open feature", "button compact", action, next.view));
    }
    list.append(row);
  });
}

function syncSelectOptions(select, entries, placeholder, multiple = false) {
  const signature = JSON.stringify(entries);
  if (select.dataset.entries === signature) return;
  const selected = new Set([...select.selectedOptions].map((option) => option.value));
  select.replaceChildren();
  if (!multiple) select.append(new Option(placeholder, ""));
  entries.forEach(([value, label]) => select.append(new Option(label, value, false, selected.has(value))));
  select.dataset.entries = signature;
}

function renderGoalContext() {
  const form = $("#goal-form");
  syncSelectOptions(form.elements.profile_id, state.profiles.map((item) => [item.id, item.name]), "No mission selected");
  syncSelectOptions(form.elements.campaign_id, state.campaigns.map((item) => [item.id, item.name]), "No campaign selected");
  const profileId = form.elements.profile_id.value;
  syncSelectOptions(form.elements.opportunity_ids, state.opportunities.filter((item) => item.profile_id === profileId && !["dismissed", "applied"].includes(item.status)).map((item) => [item.id, `${item.title} · ${item.company}`]), "", true);
  const demo = form.elements.mode.value === "demo";
  for (const name of ["profile_id", "campaign_id", "opportunity_ids"]) form.elements[name].disabled = demo;
  form.elements.opportunity_ids.disabled = demo || !profileId;
  $("#goal-context").hidden = demo;
  $("#goal-privacy").textContent = demo ? "The local demo uses a fixed example. It sends no goal text to a model or external provider." : "Model planning may send your goal and available action descriptions to the configured hosted provider. Saved résumé, job and contact text and record IDs are not sent by the planner. Keep secrets and unnecessary personal data out of your goal.";
}

function fillGoalExample(kind) {
  const form = $("#goal-form");
  const examples = { career: "Prepare truthful application drafts and inspect the forms for the jobs I select below.", creator: "Research relevant creators for the campaign I select below, so I can review their public profiles.", demo: "Show how a reviewed plan runs a safe local example and checks the results." };
  form.elements.goal.value = examples[kind] || examples.demo;
  form.elements.mode.value = kind === "demo" ? "demo" : "model";
  clearFormError(form);
  renderGoalContext();
  form.elements.goal.focus();
}

function renderPlans() {
  renderGoalContext();
  const list = $("#plan-list");
  list.replaceChildren();
  if (!state.plans.length) list.append(empty("No proposals yet", "Your proposed plans will stay here so you can return to them."));
  state.plans.slice(0, 12).forEach((plan) => {
    const item = button("", "plan-history-item", "select-plan", plan.id);
    item.classList.toggle("selected", plan.id === selectedPlanId);
    item.append(node("span", `status ${plan.status}`, titleCase(plan.status)), node("strong", "", plan.goal), node("small", "", timeAgo(plan.created_at)));
    list.append(item);
  });
  const plan = state.plans.find((item) => item.id === selectedPlanId) || state.plans[0];
  if (plan) { selectedPlanId = plan.id; renderPlanReview(plan); }
  else $("#plan-review").replaceChildren(node("h2", "", "Your plan will appear here"), node("p", "", "Describe a goal, select any saved items it needs, and request a proposal. You can inspect every step before starting."));
}

function renderPlanReview(plan) {
  const review = $("#plan-review");
  review.replaceChildren();
  const heading = node("div", "plan-review-heading");
  heading.append(node("h2", "", plan.status === "ready" ? "Review your proposed plan" : plan.status === "adopted" ? "This plan has started" : plan.status === "queued" ? "Preparing your proposal" : "Your proposal needs attention"), node("span", `status ${plan.status}`, titleCase(plan.status)));
  review.append(heading, node("p", "plan-goal", plan.goal));
  if (plan.status === "queued") review.append(node("p", "", "Hermes is considering the selected context and available actions. The proposal will appear here automatically; its steps have not started."));
  if (plan.summary) review.append(node("p", "", plan.summary));
  if (plan.source) review.append(node("p", "plan-source", plan.source === "template" ? "Local demo · fixed template · no model used" : "Model-generated proposal · review the scope and limitations"));
  const spec = plan.workflow_spec;
  if (spec?.steps?.length) {
    const context = node("div", "plan-context");
    context.append(node("h3", "", "This plan will use"));
    const records = new Map();
    spec.steps.forEach((step) => {
      const payload = step.payload || {};
      for (const [field, label, entries, describe] of [
        ["profile_id", "Mission", state.profiles, (item) => item.name],
        ["opportunity_id", "Job", state.opportunities, (item) => `${item.title} · ${item.company}`],
        ["campaign_id", "Campaign", state.campaigns, (item) => item.name],
      ]) {
        if (!payload[field]) continue;
        const record = entries.find((item) => item.id === payload[field]);
        records.set(`${field}:${payload[field]}`, `${label}: ${record ? describe(record) : payload[field]}`);
      }
    });
    if (records.size) records.forEach((label) => context.append(node("p", "", label)));
    else context.append(node("p", "", "Local example actions; no saved records."));
    review.append(context);
    const steps = node("ol", "proposal-steps");
    spec.steps.forEach((step) => {
      const item = node("li");
      item.append(node("strong", "", step.title));
      const titles = new Map(spec.steps.map((item) => [item.key, item.title]));
      const dependency = step.depends_on?.length ? `After: ${step.depends_on.map((key) => titles.get(key) || key).join(", ")}` : "Starts first";
      item.append(node("small", "", `${dependency} · ${Object.keys(step.expect_output || {}).length} result check${Object.keys(step.expect_output || {}).length === 1 ? "" : "s"}`));
      steps.append(item);
    });
    review.append(steps, node("p", "field-help", `${spec.steps.length} steps · up to ${spec.max_parallel || 1} in parallel · ${Math.round((spec.timeout_seconds || 3600) / 60)} minute limit`));
  }
  if (plan.limitations?.length) {
    const limitations = node("div", "plan-limitations");
    limitations.append(node("h3", "", "Before you start"));
    const list = node("ul");
    plan.limitations.forEach((limitation) => list.append(node("li", "", limitation)));
    limitations.append(list);
    review.append(limitations);
  }
  const actions = node("div", "card-actions");
  const expired = plan.expires_at && new Date(plan.expires_at).getTime() <= Date.now();
  if (expired && plan.status === "ready") review.append(node("p", "field-help", "This proposal has expired. Revise the goal to request a fresh plan."));
  if (plan.status === "ready" && !expired && plan.plan_digest && spec) {
    const start = button(adoptingPlans.has(plan.id) ? "Starting plan…" : "Start plan", "button primary", "adopt-plan", plan.id);
    start.disabled = adoptingPlans.has(plan.id);
    actions.append(start);
    review.append(node("p", "field-help", "Starting creates a workflow for these steps. Emails and application submissions still require their own exact approval."));
  }
  if (plan.workflow_id) actions.append(button("Follow this workflow", "button primary", "view-planned-workflow", plan.workflow_id));
  if (plan.task_id) actions.append(button("Planning history", "text-button", "view-audit", plan.task_id));
  if (["failed", "unsupported"].includes(plan.status) || (expired && plan.status === "ready")) actions.append(button("Revise the goal", "button", "revise-goal", plan.id));
  review.append(actions);
}

async function proposeGoal(event) {
  event.preventDefault();
  const form = event.currentTarget;
  if (!beginFormWork(form, "Preparing proposal…")) return;
  try {
    const ids = [...form.elements.opportunity_ids.selectedOptions].map((option) => option.value);
    if (ids.length > 3 && form.elements.mode.value !== "demo") throw new Error("Select at most three jobs for one plan.");
    const payload = { goal: form.elements.goal.value.trim(), requested_by: "dashboard:user", mode: form.elements.mode.value, opportunity_ids: form.elements.mode.value === "demo" ? [] : ids };
    if (payload.mode !== "demo" && form.elements.profile_id.value) payload.profile_id = form.elements.profile_id.value;
    if (payload.mode !== "demo" && form.elements.campaign_id.value) payload.campaign_id = form.elements.campaign_id.value;
    const fingerprint = JSON.stringify(payload);
    if (goalSubmission?.fingerprint !== fingerprint) goalSubmission = { fingerprint, key: `dashboard-plan-${crypto.randomUUID()}` };
    payload.idempotency_key = goalSubmission.key;
    const plan = await api("/v1/plans", { method: "POST", body: JSON.stringify(payload) });
    goalSubmission = null;
    selectedPlanId = plan.id;
    state.plans = [plan, ...state.plans.filter((item) => item.id !== plan.id)];
    renderPlans();
    toast("Proposal requested. Review it here before starting.");
  } catch (error) { showFormError(form, error); }
  finally { endFormWork(form); }
}

async function adoptPlan(id) {
  const plan = state.plans.find((item) => item.id === id);
  if (!plan || plan.status !== "ready" || adoptingPlans.has(id)) return;
  adoptingPlans.add(id);
  renderPlans();
  try {
    const workflow = await api(`/v1/plans/${encodeURIComponent(id)}/adopt`, { method: "POST", body: JSON.stringify({ actor: "dashboard:user", plan_digest: plan.plan_digest }) });
    plan.status = "adopted";
    plan.workflow_id = workflow.id;
    state.workflows = [workflow, ...state.workflows.filter((item) => item.id !== workflow.id)];
    renderPlans();
    renderWorkflows();
    switchView("workflows");
    await showWorkflow(workflow.id);
    toast("Plan started. Follow its steps and result checks.");
  } catch (error) { toast(`${error.message} Refresh the proposal before trying again.`, true); }
  finally { adoptingPlans.delete(id); renderPlans(); }
}

function renderMetrics() {
  const activeMatches = state.opportunities.filter((item) => ["new", "shortlisted"].includes(item.status));
  const approvals = state.tasks.filter((item) => item.status === "pending_approval");
  const activeMissions = state.profiles.filter((item) => item.active);
  $("#metric-matches").textContent = isConnected() ? String(activeMatches.length) : "—";
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

const decidingTasks = new Set();
let actionReviewId = null;
let actionReviewRecord = null;
let actionReviewSignature = "";

function emailActionState(status) {
  return {
    pending_approval: ["Needs approval", "Review the complete message before approving this one email."],
    queued: ["Queued", "Approved and waiting for the email worker. Check its history for progress."],
    executing: ["Sending", "The worker is attempting this approved message. Wait for the recorded result."],
    succeeded: ["SMTP accepted", "The mail server accepted this message. Inbox delivery is unconfirmed; record an actual reply or bounce when observed."],
    ambiguous: ["Send outcome uncertain", "Hermes cannot confirm whether the message was accepted. Check provider records before taking further action. Do not resend blindly; automatic resend is blocked."],
    failed: ["Not completed", "Review the task history and email setup before preparing another message."],
    expired: ["Approval expired", "This packet can no longer be approved. Prepare a fresh message if it is still relevant."],
    cancelled: ["Cancelled", "This action was cancelled. Review its task history before preparing another message."],
    rejected: ["Rejected", "This message was rejected and will not be sent by this action."],
  }[status] || [titleCase(status) || "Status unavailable", "Open the task history to inspect the recorded state."];
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
    if (action) actions.append(button(action.action_type === "communications.email_send" ? "Review email" : "Review exact action", "button compact primary", "review-action", action.id));
    else if (["communications.email_send", "career.application_submit"].includes(task.kind)) actions.append(button("Refresh exact packet", "button compact", "refresh-workspace"));
    else actions.append(button("Approve", "button compact primary", "approve-task", task.id));
    actions.append(button("Reject", "button compact", "reject-task", task.id));
    $$('button', actions).forEach((item) => { item.disabled = decidingTasks.has(task.id); });
    card.append(copy, actions);
    list.append(card);
  });
}

function renderActionReview(action) {
  const expired = new Date(action.expires_at).getTime() <= Date.now();
  const signature = JSON.stringify([action, expired, decidingTasks.has(action.task_id)]);
  if (signature === actionReviewSignature) return;
  actionReviewSignature = signature;
  actionReviewRecord = action;
  const root = $("#detail-content");
  const email = action.action_type === "communications.email_send";
  const [statusLabel, statusHelp] = emailActionState(action.status);
  root.replaceChildren(
    node("span", "tag amber-tag", "Exact approval packet"),
    node("h2", "", email ? "Review this one email" : titleCase(action.action_type)),
    node("p", "", `${action.target_display} · expires ${formatDate(action.expires_at)}`),
  );
  if (email) root.append(node("p", `email-action-status ${action.status}`, statusLabel), node("p", "fine-print", statusHelp));
  const summary = node("dl", "action-summary");
  Object.entries(action.public_context).forEach(([key, value]) => {
    summary.append(node("dt", "", titleCase(key)), node("dd", "", typeof value === "string" ? value : JSON.stringify(value, null, 2)));
  });
  root.append(summary, node("p", "fine-print", `SHA-256 ${action.context_hash}. Approval is invalid if this packet changes.`));
  if (action.executed_at) root.append(node("p", "fine-print", `${email ? "SMTP acceptance recorded" : "Executed"}: ${formatDate(action.executed_at)}`));
  if (action.external_reference) root.append(node("p", "email-reference", `${email ? "Message reference" : "External reference"}: ${action.external_reference}`));
  const actions = node("div", "card-actions");
  if (action.status === "pending_approval") {
    if (expired) root.append(node("p", "notice", "This packet has expired. Prepare a fresh action instead of approving this one."));
    const approve = button(decidingTasks.has(action.task_id) ? "Recording decision…" : email ? "Approve this email" : "Approve this action", "button primary", "approve-task", action.task_id);
    approve.disabled = expired || decidingTasks.has(action.task_id);
    const reject = button("Reject", "button", "reject-task", action.task_id);
    reject.disabled = decidingTasks.has(action.task_id);
    actions.append(approve, reject);
    root.append(node("p", "fine-print", email ? "Approval authorizes the worker to send only the recipient, subject and body shown above. It does not authorize a later message." : "Approval authorizes only the exact action shown above."));
  }
  actions.append(button(email ? "View send history" : "Task history", "text-button", "view-audit", action.task_id));
  root.append(actions);
}

async function showActionReview(id) {
  actionReviewId = id;
  actionReviewRecord = null;
  actionReviewSignature = "";
  $("#detail-content").replaceChildren(empty("Loading exact action", "Fetching the saved packet and its current state…"));
  if (!$("#detail-dialog").open) $("#detail-dialog").showModal();
  try {
    const action = await api(`/v1/external-actions/${encodeURIComponent(id)}`);
    if (actionReviewId !== id || !$("#detail-dialog").open) return;
    state.actions = [action, ...state.actions.filter((item) => item.id !== id)];
    renderActionReview(action);
  } catch (_error) {
    if (actionReviewId === id && $("#detail-dialog").open) $("#detail-content").replaceChildren(empty("Could not load this action", "Refresh the workspace and try again. The saved task history remains available from the prospect."));
  }
}

function renderTasks() {
  const list = $("#task-list");
  list.replaceChildren();
  if (!state.tasks.length) {
    list.append(empty("No tasks loaded", isConnected() ? "Assign a task to begin." : "Connect to inspect durable task state."));
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

const workflowKinds = new Set(["foundation.echo", "foundation.wait", "career.search", "career.application_draft", "career.application_preflight", "marketing.creator_discovery"]);
const workflowCancellations = new Set();
let workflowDetailId = null;
let workflowSubmission = null;
let workflowSubmitting = false;

function demoWorkflowSteps() {
  return [
    { key: "start", title: "Verify the starting signal", kind: "foundation.echo", payload: { message: "WORKFLOW_READY" }, depends_on: [], expect_output: { echo: "WORKFLOW_READY" } },
    { key: "pause", title: "Run a cooperative wait", kind: "foundation.wait", payload: { seconds: 3 }, depends_on: ["start"], expect_output: { waited_seconds: 3 } },
    { key: "check", title: "Verify the parallel branch", kind: "foundation.echo", payload: { message: "BRANCH_CHECKED" }, depends_on: ["start"], expect_output: { echo: "BRANCH_CHECKED" } },
    { key: "finish", title: "Finish after both branches pass", kind: "foundation.echo", payload: { message: "WORKFLOW_COMPLETE" }, depends_on: ["pause", "check"], expect_output: { echo: "WORKFLOW_COMPLETE" } },
  ];
}

function applicationWorkflowSteps() {
  const id = $("#workflow-form").elements.opportunity_id.value;
  const opportunity = state.opportunities.find((item) => item.id === id);
  if (!opportunity) throw new Error("Choose a saved opportunity before starting this recipe.");
  return [
    { key: "draft", title: "Prepare an evidence-based application draft", kind: "career.application_draft", payload: { profile_id: opportunity.profile_id, opportunity_id: opportunity.id }, depends_on: [], expect_output: { draft_created: true } },
    { key: "preflight", title: "Inspect the application form", kind: "career.application_preflight", payload: { opportunity_id: opportunity.id }, depends_on: ["draft"], expect_output: { blocked_reason: null } },
  ];
}

function workflowSteps() {
  const form = $("#workflow-form");
  if (form.elements.recipe.value === "application") return applicationWorkflowSteps();
  if (form.elements.recipe.value !== "custom") return demoWorkflowSteps();
  let steps;
  try { steps = JSON.parse(form.elements.steps_json.value); }
  catch (_error) { throw new Error("Steps must be valid JSON. Start with the example and check its commas and quotes."); }
  if (!Array.isArray(steps) || steps.length < 1 || steps.length > 32) throw new Error("Use an array with 1–32 steps.");
  const keys = new Set();
  for (const step of steps) {
    if (!step || typeof step !== "object" || Array.isArray(step) || typeof step.key !== "string" || !/^[A-Za-z][A-Za-z0-9_-]{0,39}$/.test(step.key)) throw new Error("Each step needs a key starting with a letter, up to 40 letters, numbers, underscores, or hyphens.");
    if (keys.has(step.key)) throw new Error(`Step key “${step.key}” is repeated.`);
    keys.add(step.key);
    if (typeof step.title !== "string" || !step.title.trim() || step.title.length > 200) throw new Error(`Step “${step.key}” needs a title of 1–200 characters.`);
    if (!workflowKinds.has(step.kind)) throw new Error(`Step “${step.key}” must use an enabled workflow capability: ${[...workflowKinds].join(", ")}.`);
    if (!step.payload || typeof step.payload !== "object" || Array.isArray(step.payload)) throw new Error(`Step “${step.key}” needs a payload object.`);
    if (step.depends_on !== undefined && (!Array.isArray(step.depends_on) || step.depends_on.some((key) => typeof key !== "string"))) throw new Error(`Step “${step.key}” needs an array of dependency keys.`);
    if (step.expect_output !== undefined && (!step.expect_output || typeof step.expect_output !== "object" || Array.isArray(step.expect_output) || Object.values(step.expect_output).some((value) => value !== null && !["string", "number", "boolean"].includes(typeof value)))) throw new Error(`Step “${step.key}” result checks must be an object of exact scalar values, such as {"draft_created": true}.`);
  }
  const visited = new Set();
  const visiting = new Set();
  const byKey = new Map(steps.map((step) => [step.key, step]));
  function visit(key) {
    if (visiting.has(key)) throw new Error("Step dependencies contain a cycle. Every branch needs a starting point.");
    if (visited.has(key)) return;
    visiting.add(key);
    for (const dependency of byKey.get(key).depends_on || []) {
      if (!keys.has(dependency)) throw new Error(`Step “${key}” refers to missing dependency “${dependency}”.`);
      visit(dependency);
    }
    visiting.delete(key);
    visited.add(key);
  }
  steps.forEach((step) => visit(step.key));
  return steps;
}

function renderWorkflowOpportunityOptions() {
  const select = $("#workflow-form").elements.opportunity_id;
  const selected = select.value;
  const options = state.opportunities.filter((item) => !["dismissed", "applied"].includes(item.status) || item.id === selected);
  const signature = JSON.stringify(options.map((item) => [item.id, item.title, item.company]));
  if (select.dataset.options === signature) return;
  select.dataset.options = signature;
  select.replaceChildren(new Option(options.length ? "Choose an opportunity" : "Create a mission and scan for opportunities first", ""));
  options.forEach((item) => select.append(new Option(`${item.title} · ${item.company}`, item.id)));
  select.value = selected;
}

function updateWorkflowRecipe() {
  const form = $("#workflow-form");
  const recipe = form.elements.recipe.value;
  const application = recipe === "application";
  const custom = recipe === "custom";
  $("#workflow-opportunity-field").hidden = !application;
  form.elements.opportunity_id.disabled = !application;
  form.elements.opportunity_id.required = application;
  $("#workflow-custom-fields").hidden = !custom;
  form.elements.steps_json.disabled = !custom;
  form.elements.steps_json.required = custom;
  if (custom && !form.elements.steps_json.value) form.elements.steps_json.value = JSON.stringify(demoWorkflowSteps(), null, 2);
  const titles = { demo: "Verified parallel demo", application: "Prepare an application", custom: "Custom workflow" };
  if (Object.values(titles).includes(form.elements.title.value)) form.elements.title.value = titles[recipe];
  $("#workflow-recipe-help").textContent = application
    ? "Generate a résumé-based draft, then inspect the selected application form. The run passes only when a draft exists and inspection reports no blocking reason."
    : custom
      ? "Compose enabled research and preparation capabilities. Each step has a stable key; depends_on lists the steps that must pass first."
      : "A harmless four-step run: verify a message, run two branches, then check the final result. No model or provider account needed.";
  const preview = $("#workflow-plan-preview");
  preview.replaceChildren();
  if (!custom) {
    const titles = application ? ["Draft application", "Check form"] : ["Verify signal", "Wait + check in parallel", "Verify completion"];
    preview.append(node("strong", "", "Recipe path"));
    const list = node("ol");
    titles.forEach((title) => list.append(node("li", "", title)));
    preview.append(list);
  }
  preview.hidden = custom;
}

function workflowProgress(workflow) {
  const done = workflow.steps.filter((step) => step.status === "succeeded").length;
  const wrapper = node("div", "workflow-progress");
  const progress = node("progress");
  progress.max = workflow.steps.length || 1;
  progress.value = done;
  progress.setAttribute("aria-label", `${workflow.title}: ${done} of ${workflow.steps.length} steps passed`);
  wrapper.append(progress, node("span", "", `${done} / ${workflow.steps.length} passed`));
  return wrapper;
}

function workflowCancelButton(workflow) {
  const cancelling = workflow.status === "cancelling" || workflowCancellations.has(workflow.id);
  const element = button(cancelling ? "Stopping…" : "Stop workflow", "text-button danger-text", "cancel-workflow", workflow.id);
  element.disabled = cancelling;
  return element;
}

function workflowCard(workflow) {
  const card = node("article", "panel workflow-card");
  const heading = node("div", "workflow-card-head");
  const title = node("h3", "", workflow.title);
  heading.append(title, node("span", `status ${workflow.status}`, titleCase(workflow.status)));
  card.append(heading);
  if (workflow.objective) card.append(node("p", "workflow-objective", workflow.objective));
  card.append(workflowProgress(workflow));
  const next = workflow.steps.filter((step) => step.status === "dispatched");
  const failed = workflow.steps.find((step) => step.status === "failed");
  if (failed) card.append(node("p", "workflow-run-note red", `${failed.title}: ${titleCase(failed.error_code || "step failed")}`));
  else if (next.length) card.append(node("p", "workflow-run-note", `In progress: ${next.map((step) => step.title).join(" · ")}`));
  else if (workflow.status === "running") card.append(node("p", "workflow-run-note", "Waiting for the coordinator to advance ready steps."));
  const meta = node("p", "workflow-meta", `${workflow.max_parallel} parallel max · ${Math.round(workflow.timeout_seconds / 60)} min limit · ${timeAgo(workflow.created_at)}`);
  const actions = node("div", "card-actions");
  actions.append(button("Inspect steps", "button compact", "view-workflow", workflow.id));
  if (["running", "cancelling"].includes(workflow.status)) actions.append(workflowCancelButton(workflow));
  card.append(meta, actions);
  return card;
}

function renderWorkflowDetails(workflow) {
  $("#workflow-detail-title").textContent = workflow.title;
  const content = $("#workflow-detail-content");
  content.replaceChildren(node("span", `status ${workflow.status}`, titleCase(workflow.status)));
  if (workflow.objective) content.append(node("p", "workflow-objective", workflow.objective));
  content.append(workflowProgress(workflow));
  const metadata = node("dl", "action-summary");
  const entries = [["Started", formatDate(workflow.created_at)], ["Deadline", formatDate(workflow.deadline_at)], ["Requested by", workflow.requested_by], ["Concurrency", `Up to ${workflow.max_parallel} steps`]];
  if (workflow.completed_at) entries.push(["Completed", formatDate(workflow.completed_at)]);
  entries.forEach(([name, value]) => metadata.append(node("dt", "", name), node("dd", "", value)));
  content.append(metadata);
  const steps = node("ol", "workflow-steps");
  workflow.steps.forEach((step) => {
    const item = node("li", `workflow-step ${step.status}`);
    const head = node("div", "workflow-step-head");
    head.append(node("h3", "", step.title), node("span", `status ${step.status}`, titleCase(step.status)));
    item.append(head, node("p", "workflow-meta", `${step.key} · ${step.kind} · ${titleCase(step.risk_level)} risk`));
    const dependencies = step.depends_on?.length ? `Requires: ${step.depends_on.join(", ")}` : "Starting step · no dependencies";
    item.append(node("p", "workflow-dependencies", dependencies));
    const checks = Object.entries(step.expect_output || {});
    if (checks.length) {
      const checkList = node("ul", "workflow-checks");
      checks.forEach(([key, value]) => {
        const label = step.status === "succeeded" ? "Passed" : "Expected";
        checkList.append(node("li", "", `${label}: ${key} = ${JSON.stringify(value)}`));
      });
      item.append(checkList);
    }
    if (step.error_code) item.append(node("p", "workflow-step-error", titleCase(step.error_code)));
    if (step.task_id) {
      const link = button("Task audit", "text-button", "view-audit", step.task_id);
      link.setAttribute("aria-label", `View task audit for ${step.title}`);
      const task = node("div", "workflow-task-link");
      task.append(link, node("span", "", `Task: ${titleCase(step.task_status || "queued")}`));
      item.append(task);
    }
    steps.append(item);
  });
  content.append(steps);
  if (["running", "cancelling"].includes(workflow.status)) {
    const footer = node("div", "dialog-actions");
    footer.append(workflowCancelButton(workflow));
    content.append(footer);
  }
}

function renderWorkflows() {
  renderWorkflowOpportunityOptions();
  const filter = $("#workflow-status-filter").value;
  const workflows = state.workflows.filter((workflow) => !filter
    || (filter === "active" && ["running", "cancelling"].includes(workflow.status))
    || (filter === "attention" && ["failed", "timed_out"].includes(workflow.status))
    || workflow.status === filter);
  const list = $("#workflow-list");
  list.replaceChildren();
  $("#workflow-count").textContent = `${workflows.length} workflow${workflows.length === 1 ? "" : "s"}`;
  if (workflows.length) workflows.forEach((workflow) => list.append(workflowCard(workflow)));
  else list.append(empty(filter ? "No matching workflows" : "No workflows yet", isConnected() ? "Start the demo or choose a recipe to coordinate your next task." : "Connect the workspace to load and start durable workflows.", true));
  if ($("#workflow-dialog").open && workflowDetailId) {
    const selected = state.workflows.find((workflow) => workflow.id === workflowDetailId);
    if (selected) renderWorkflowDetails(selected);
  }
}

async function showWorkflow(id) {
  workflowDetailId = id;
  const content = $("#workflow-detail-content");
  $("#workflow-detail-title").textContent = "Workflow details";
  content.replaceChildren(empty("Loading workflow", "Fetching its durable steps and result checks…"));
  $("#workflow-dialog").showModal();
  try {
    const workflow = await api(`/v1/workflows/${encodeURIComponent(id)}`);
    if (workflowDetailId === id && $("#workflow-dialog").open) renderWorkflowDetails(workflow);
  } catch (error) {
    if (workflowDetailId === id) content.replaceChildren(empty("Could not load workflow", error.message));
  }
}

async function cancelWorkflow(id) {
  if (workflowCancellations.has(id)) return;
  workflowCancellations.add(id);
  renderWorkflows();
  try {
    const workflow = await api(`/v1/workflows/${encodeURIComponent(id)}/cancel`, { method: "POST", body: JSON.stringify({ actor: "dashboard:user", reason: "Stopped from the workflow dashboard" }) });
    const index = state.workflows.findIndex((item) => item.id === id);
    if (index !== -1) state.workflows[index] = workflow;
    toast(workflow.status === "cancelled" ? "Workflow stopped" : "Workflow stop requested; active tasks are being interrupted.");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
  finally { workflowCancellations.delete(id); renderWorkflows(); }
}

async function createWorkflow(event) {
  event.preventDefault();
  if (workflowSubmitting) return;
  const form = event.currentTarget;
  const submit = $("#workflow-submit");
  const feedback = $("#workflow-form-status");
  feedback.hidden = true;
  try {
    const payload = { title: form.elements.title.value.trim(), objective: form.elements.objective.value.trim(), requested_by: form.elements.requested_by.value.trim(), max_parallel: Number(form.elements.max_parallel.value), timeout_seconds: Number(form.elements.timeout_seconds.value), steps: workflowSteps() };
    if (!payload.title || !payload.requested_by) throw new Error("Enter a workflow title and requester.");
    const fingerprint = JSON.stringify(payload);
    if (workflowSubmission?.fingerprint !== fingerprint) workflowSubmission = { fingerprint, key: `dashboard-workflow-${crypto.randomUUID()}` };
    payload.idempotency_key = workflowSubmission.key;
    workflowSubmitting = true;
    submit.disabled = true;
    submit.textContent = "Starting…";
    const workflow = await api("/v1/workflows", { method: "POST", body: JSON.stringify(payload) });
    workflowSubmission = null;
    state.workflows = [workflow, ...state.workflows.filter((item) => item.id !== workflow.id)];
    $("#workflow-status-filter").value = "";
    renderWorkflows();
    feedback.textContent = `Started “${workflow.title}”. Inspect its steps to follow the result checks.`;
    feedback.classList.remove("error");
    feedback.hidden = false;
    toast("Workflow started");
    await loadData({ quiet: true });
  } catch (error) {
    feedback.textContent = error.message;
    feedback.classList.add("error");
    feedback.hidden = false;
  } finally {
    workflowSubmitting = false;
    submit.disabled = false;
    submit.textContent = "Start workflow";
  }
}

function renderActivity() {
  const list = $("#overview-activity");
  list.replaceChildren();
  if (!state.audits.length) {
    list.append(node("div", "event", ""));
    list.firstChild.append(node("strong", "", "No activity loaded"), node("p", "", isConnected() ? "Actions will appear here." : "Connect the workspace first."));
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

let smtpCheckSubmitting = false;
let smtpCheckError = "";
let communicationsSignature = "";
const smtpCheckActiveStates = new Set(["queued", "running", "retry_wait", "cancel_requested"]);

function renderCommunications() {
  const communications = state.communications;
  const signature = JSON.stringify([communications, smtpCheckSubmitting, smtpCheckError, isConnected()]);
  if (signature === communicationsSignature) return;
  communicationsSignature = signature;
  const transport = communications?.transport;
  const known = ["disabled", "mailpit", "smtp"].includes(transport);
  const label = transport === "mailpit" ? "Local test inbox · Mailpit" : transport === "smtp" ? "External SMTP selected" : transport === "disabled" ? "Email disabled" : "Email status unavailable";
  const explanation = !known ? "Connect and refresh to load the configured email transport."
    : transport === "mailpit" ? "Mailpit captures messages locally. It cannot reach creator inboxes."
    : transport === "disabled" ? "Configure your SMTP provider before preparing a creator email."
    : communications.sender_configured ? "A sender is configured. Check the worker connection, then review each exact email before sending."
    : "The sender is missing. Complete local SMTP setup before preparing an email.";
  const banner = $("#campaign-email-guidance");
  banner.replaceChildren(node("strong", "", label), node("span", "", explanation), button("Email setup and checks", "text-button", "open-email-setup"));
  const status = $("#email-transport-status");
  status.replaceChildren(node("strong", "", label), node("p", "", explanation), node("p", "fine-print", "These settings describe the control API. They do not prove that an existing worker loaded them."));

  const check = communications?.latest_check;
  const result = $("#email-check-status");
  result.replaceChildren();
  if (!check) result.append(node("strong", "", "No connection check recorded"), node("p", "fine-print", "After setup and worker restart, run a check to record whether the worker can connect."));
  else {
    const pending = smtpCheckActiveStates.has(check.status);
    const passed = check.status === "succeeded" && check.output?.checked === true;
    result.append(node("strong", "", pending ? "Connection check in progress" : passed ? "Last connection check passed" : "Last connection check did not pass"));
    if (check.completed_at) result.append(node("p", "fine-print", `Recorded ${formatDate(check.completed_at)}. This proves only the connection used by that worker at that time.`));
    if (passed) {
      const checkedTransport = check.output.transport === "mailpit" ? "Local Mailpit connection" : check.output.transport === "smtp" ? "External SMTP connection" : "Mail connection";
      const authenticated = check.output.authenticated === true ? "login accepted" : "no login used";
      result.append(node("p", "fine-print", `${checkedTransport}; ${authenticated}. No email was sent.`));
    } else if (!pending) result.append(node("p", "fine-print", "Review the local SMTP settings and restart the worker before checking again. No email was sent by this check."));
    if (check.id) result.append(button("Connection check history", "text-button", "view-audit", check.id));
  }
  if (smtpCheckError) result.append(node("p", "notice", smtpCheckError));
  $$('[data-action="check-smtp"]').forEach((item) => {
    const pending = smtpCheckSubmitting || smtpCheckActiveStates.has(check?.status);
    item.disabled = !isConnected() || !known || transport === "disabled" || pending;
    item.textContent = pending ? "Checking connection…" : "Check SMTP connection";
  });
}

async function checkSmtpConnection() {
  if (smtpCheckSubmitting || smtpCheckActiveStates.has(state.communications?.latest_check?.status)) return;
  if (!isConnected() || !["mailpit", "smtp"].includes(state.communications?.transport)) return;
  smtpCheckSubmitting = true;
  smtpCheckError = "";
  renderCommunications();
  try {
    const task = await api("/v1/communications/smtp-check", { method: "POST", body: JSON.stringify({ requested_by: "dashboard:user" }) });
    state.communications.latest_check = { id: task.id, status: task.status, completed_at: null, output: null, error_code: null };
    state.tasks = [task, ...state.tasks.filter((item) => item.id !== task.id)];
    toast("Connection check queued. It sends no email.");
    renderTasks();
  } catch (_error) {
    smtpCheckError = "The connection check could not be queued. Refresh the workspace and review local SMTP setup before trying again.";
  } finally {
    smtpCheckSubmitting = false;
    renderCommunications();
  }
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
  if (prospect.latest_message) meta.append(node("span", "chip", `${titleCase(prospect.latest_message.stage)} · ${emailActionState(prospect.latest_message.action_status)[0]}`));
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
  if (prospect.latest_message?.action_id) actions.append(button("Review message", "text-button", "review-action", prospect.latest_message.action_id));
  if (prospect.latest_message?.task_id) actions.append(button("View send history", "text-button", "view-audit", prospect.latest_message.task_id));
  card.append(actions);
  if (prospect.latest_message) card.append(node("p", prospect.latest_message.action_status === "ambiguous" ? "notice" : "fine-print", emailActionState(prospect.latest_message.action_status)[1]));
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
  renderCommunications();
  renderNextAction();
  renderReadiness();
  renderPlans();
  renderMetrics();
  renderProfileFilter();
  renderMissions();
  renderOpportunities();
  renderApprovals();
  renderTasks();
  renderWorkflows();
  renderActivity();
  renderMarketingMetrics();
  renderMarketingFilters();
  renderCampaigns();
  renderProspects();
  renderInferenceStatus();
  if (actionReviewId && $("#detail-dialog").open) {
    const action = state.actions.find((item) => item.id === actionReviewId) || actionReviewRecord;
    if (action) renderActionReview(action);
  }
}

function clearFormError(form) {
  $(".form-feedback", form)?.remove();
  $$('[aria-invalid="true"]', form).forEach((input) => input.removeAttribute("aria-invalid"));
}

function showFormError(form, error) {
  clearFormError(form);
  const feedback = node("div", "form-feedback");
  feedback.setAttribute("role", "alert");
  feedback.append(node("strong", "", "Check the form and try again"), node("p", "", error.message || "The request did not complete. Your edits are kept."));
  const issues = error.details?.validation || [];
  for (const issue of issues) {
    const input = form.elements.namedItem(issue.field.split(".").at(-1));
    if (input instanceof HTMLElement) {
      input.setAttribute("aria-invalid", "true");
      let parent = input.parentElement;
      while (parent && parent !== form) { if (parent.tagName === "DETAILS") parent.open = true; parent = parent.parentElement; }
    }
  }
  const anchor = $(".dialog-actions", form) || $('button[type="submit"]', form);
  form.insertBefore(feedback, anchor?.parentElement === form ? anchor : null);
  feedback.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function beginFormWork(form, label = "Saving…") {
  if (form.dataset.busy === "true") return false;
  clearFormError(form);
  form.dataset.busy = "true";
  form.setAttribute("aria-busy", "true");
  $$('button[type="submit"]', form).forEach((button) => {
    button.dataset.idleLabel = button.textContent;
    button.disabled = true;
    button.textContent = label;
  });
  return true;
}

function endFormWork(form) {
  form.dataset.busy = "false";
  form.removeAttribute("aria-busy");
  $$('button[type="submit"]', form).forEach((button) => {
    button.disabled = false;
    button.textContent = button.dataset.idleLabel || "Save";
  });
}

async function guardedSubmit(event, handler) {
  event.preventDefault();
  const form = event.currentTarget;
  if (!beginFormWork(form)) return;
  try { await handler(event); }
  catch (error) { showFormError(form, error); }
  finally { endFormWork(form); }
}

function progressiveForm(form, groups) {
  const grid = $(":scope > .form-grid", form);
  if (!grid) return;
  for (const group of groups) {
    const details = node("details", "form-section span-2");
    const summary = node("summary", "", group.title);
    summary.append(node("span", "", group.description));
    const body = node("div", "form-grid form-section-body");
    for (const name of group.fields) {
      const input = form.querySelector(`[name="${name}"]`);
      if (!input) continue;
      let target = input.closest("fieldset") || input.closest("label");
      if (target && !body.contains(target)) body.append(target);
    }
    details.append(summary, body);
    grid.append(details);
  }
  const instruction = node("p", "form-introduction", "Start with the essentials. Expand the sections below when you need more control.");
  grid.before(instruction);
}

function initializeForms() {
  progressiveForm($("#profile-form"), [
    { title: "Match preferences", description: "Freshness, fit, and employment type", fields: ["required_keywords", "excluded_keywords", "max_age_hours", "min_score", "employment_types"] },
    { title: "Search sources", description: "Public feeds and employer boards", fields: ["arbeitnow"] },
    { title: "Application details", description: "Identity for form preparation", fields: ["first_name"] },
    { title: "Schedule and automatic preparation", description: "Choose when work may run", fields: ["schedule_minutes", "active", "auto_prepare"] },
  ]);
  $("#profile-form").elements.resume_text.rows = 5;
  progressiveForm($("#campaign-form"), [
    { title: "Offers and audience", description: "Check the claims each draft may use", fields: ["target_audience", "viewer_offer", "creator_offer", "paid_offer_enabled", "paid_offer_details"] },
    { title: "Creator discovery", description: "Search terms, audience size, and location", fields: ["discovery_queries", "relevance_language", "region_code", "min_subscribers", "max_subscribers", "max_video_age_days", "results_per_query"] },
    { title: "Schedule and draft learning", description: "Discovery frequency and measured adaptation", fields: ["schedule_hours", "adaptive_mode"] },
  ]);
  $$('dialog button[value="cancel"]').forEach((close) => {
    close.type = "button";
    close.addEventListener("click", () => close.closest("dialog").close());
  });
  $$('dialog form > .tag').forEach((tag) => { if (tag.nextElementSibling?.tagName === "H2") tag.remove(); });
  $$('form').forEach((form) => {
    form.addEventListener("reset", () => clearFormError(form));
    form.addEventListener("invalid", (event) => {
      let parent = event.target.parentElement;
      while (parent && parent !== form) { if (parent.tagName === "DETAILS") parent.open = true; parent = parent.parentElement; }
    }, true);
  });
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
  if (!isConnected()) return $("#connect-dialog").showModal();
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
  } catch (error) { showFormError(form, error); }
}

function openCampaignDialog(campaign = null) {
  if (!isConnected()) return $("#connect-dialog").showModal();
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
  } catch (error) { showFormError(form, error); }
}

function populateCampaignSelect(select, selected = "") {
  select.replaceChildren(new Option("Choose a campaign", ""));
  state.campaigns.forEach((campaign) => select.append(new Option(campaign.name, campaign.id)));
  select.value = selected;
}

function openProspectDialog(prospect = null) {
  if (!isConnected()) return $("#connect-dialog").showModal();
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
  } catch (error) { showFormError(form, error); }
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
  } catch (error) {
    if ($("#marketing-reply-dialog").open) showFormError($("#marketing-reply-form"), error);
    else toast(error.message, true);
  }
}

function openMarketingReply(prospect, stage = "question_reply") {
  if (!prospect) return;
  const form = $("#marketing-reply-form");
  form.reset();
  const initial = stage === "initial";
  form.elements.prospect_id.value = prospect.id;
  form.elements.stage.value = stage;
  form.elements.subject.value = initial ? "" : `Re: ${prospect.display_name} × KarixMC`;
  form.elements.subject.required = !initial;
  form.elements.body.required = !initial;
  $("#marketing-message-title").textContent = initial ? `Introduce your campaign to ${prospect.display_name}` : "Answer the creator's question";
  $("#marketing-message-guidance").textContent = initial ? "Use the campaign introduction, or write a specific subject and body below. Keep claims and offers factual. You will review the complete packet before approving any send." : "Answer only what you know. The exact message will wait for approval.";
  $("#marketing-message-fields").open = !initial;
  $("#marketing-message-fields summary").hidden = !initial;
  $("#marketing-message-custom-help").hidden = !initial;
  $('button[type="submit"]', form).textContent = initial ? "Prepare introduction for review" : "Prepare exact answer";
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
  } catch (error) { showFormError(form, error); }
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
  actionReviewId = null;
  actionReviewRecord = null;
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
  if (decidingTasks.has(id)) return;
  const action = state.actions.find((item) => item.task_id === id) || (actionReviewRecord?.task_id === id ? actionReviewRecord : null);
  if (decision === "approved" && action) {
    if (actionReviewId !== action.id || !$("#detail-dialog").open) return showActionReview(action.id);
    if (action.status !== "pending_approval" || new Date(action.expires_at).getTime() <= Date.now()) {
      toast("This packet cannot be approved. Refresh and review its current state.", true);
      return;
    }
  }
  decidingTasks.add(id);
  renderApprovals();
  if (actionReviewRecord && $("#detail-dialog").open) renderActionReview(actionReviewRecord);
  try {
    await api(`/v1/tasks/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, actor: "dashboard:approver", reason: "Decision recorded in Hermes Command Center" }) });
    toast(decision === "approved" && action?.action_type === "communications.email_send" ? "This one email is approved and queued. Follow its send history for the result." : `Task ${decision}`);
    await loadData({ quiet: true });
    if (actionReviewId && $("#detail-dialog").open) await showActionReview(actionReviewId);
  } catch (error) { toast(error.message, true); }
  finally {
    decidingTasks.delete(id);
    renderApprovals();
    if (actionReviewRecord && $("#detail-dialog").open) renderActionReview(actionReviewRecord);
  }
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
  } catch (error) { showFormError(form, error); }
}

document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-view-target], [data-view-jump], [data-action]");
  if (!target) return;
  if (target.dataset.viewTarget) return switchView(target.dataset.viewTarget);
  if (target.dataset.viewJump) return switchView(target.dataset.viewJump);
  const { action, id } = target.dataset;
  if (action === "open-command") return openCommand();
  if (action === "close-command") return $("#command-dialog").close();
  if (action === "run-command") return runCommand(Number(id));
  if (action === "navigate") return switchView(id);
  if (action === "connect-workspace") return $("#connect-dialog").showModal();
  if (action === "refresh-workspace") return loadData();
  if (action === "goal-demo") return runGuidanceAction(action);
  if (action === "goal-example") return fillGoalExample(id);
  if (action === "select-plan") { selectedPlanId = id; renderPlans(); return; }
  if (action === "adopt-plan") return adoptPlan(id);
  if (action === "view-planned-workflow") { switchView("workflows"); return showWorkflow(id); }
  if (action === "revise-goal") {
    const plan = state.plans.find((item) => item.id === id);
    if (plan) { $("#goal-form").elements.goal.value = plan.goal; $("#goal-form").elements.goal.focus(); }
    return;
  }
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
  if (action === "plan-marketing-initial") return openMarketingReply(state.prospects.find((item) => item.id === id), "initial");
  if (action === "plan-marketing-paid") return planMarketingEmail(id, "paid_offer");
  if (action === "reply-prospect") return openMarketingReply(state.prospects.find((item) => item.id === id));
  if (action === "outcome-prospect") return openMarketingOutcome(state.prospects.find((item) => item.id === id));
  if (action === "review-action") return showActionReview(id);
  if (action === "open-email-setup") {
    switchView("settings");
    $("#email-setup-card").scrollIntoView({ block: "start" });
    $("#email-setup-card").focus({ preventScroll: true });
    return;
  }
  if (action === "check-smtp") return checkSmtpConnection();
  if (action === "approve-task") return decideTask(id, "approved");
  if (action === "reject-task") return decideTask(id, "rejected");
  if (action === "view-audit") return showAudit(id);
  if (action === "view-workflow") return showWorkflow(id);
  if (action === "cancel-workflow") return cancelWorkflow(id);
  if (action === "close-workflow") return $("#workflow-dialog").close();
});

$("#connect-button").addEventListener("click", () => $("#connect-dialog").showModal());
$("#settings-connect").addEventListener("click", () => $("#connect-dialog").showModal());
$("#disconnect-button").addEventListener("click", logoutBrowserSession);
$("#connect-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = $("#token-input").value.trim();
  if (state.browserSession) {
    try {
      await api("/v1/auth/logout", { method: "POST" });
    } catch (_error) { /* recovery login can continue after an expired session */ }
  }
  state.browserSession = false;
  state.csrfToken = "";
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
$("#profile-form").addEventListener("submit", (event) => guardedSubmit(event, saveProfile));
$("#campaign-form").addEventListener("submit", (event) => guardedSubmit(event, saveCampaign));
$("#prospect-form").addEventListener("submit", (event) => guardedSubmit(event, saveProspect));
$("#marketing-outcome-form").addEventListener("submit", (event) => guardedSubmit(event, saveMarketingOutcome));
$("#marketing-reply-form").addEventListener("submit", (event) => guardedSubmit(event, async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const subject = form.elements.subject.value.trim();
  const body = form.elements.body.value.trim();
  if (Boolean(subject) !== Boolean(body)) {
    $("#marketing-message-fields").open = true;
    showFormError(form, new Error("Fill both the subject and body, or leave both blank to use the campaign introduction."));
    (subject ? form.elements.body : form.elements.subject).focus();
    return;
  }
  await planMarketingEmail(form.elements.prospect_id.value, form.elements.stage.value, subject || null, body || null);
}));
$("#application-answer-form").addEventListener("submit", (event) => guardedSubmit(event, async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const answers = {};
  $$('[data-field-key]', form).forEach((input) => {
    answers[input.dataset.fieldKey] = input.type === "checkbox" ? input.checked : input.value;
  });
  await planOpportunity(form.elements.opportunity_id.value, answers);
}));
$("#email-action-form").addEventListener("submit", (event) => guardedSubmit(event, async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await api("/v1/external-actions/email", { method: "POST", body: JSON.stringify({ recipient: form.elements.recipient.value, subject: form.elements.subject.value, body: form.elements.body.value, opportunity_id: form.elements.opportunity_id.value || null, actor: "dashboard:career", approval_window_minutes: 60 }) });
    $("#email-action-dialog").close();
    $("#detail-dialog").close();
    toast("Exact email is waiting for approval");
    await loadData({ quiet: true });
    switchView("approvals");
  } catch (error) { showFormError(form, error); }
}));
$("#task-form").addEventListener("submit", (event) => guardedSubmit(event, assignTask));
$("#goal-form").addEventListener("submit", proposeGoal);
$("#goal-form").elements.mode.addEventListener("change", renderGoalContext);
$("#goal-form").elements.profile_id.addEventListener("change", renderGoalContext);
$("#command-search").addEventListener("input", renderCommands);
$("#command-search").addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); selectCommand(commandIndex + (event.key === "ArrowDown" ? 1 : -1)); }
  if (event.key === "Enter") { event.preventDefault(); runCommand(commandIndex); }
});
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    if (!$("dialog[open]") || $("#command-dialog").open) openCommand();
  }
});
window.addEventListener("popstate", restoreView);
window.addEventListener("hashchange", restoreView);
$("#workflow-form").addEventListener("submit", createWorkflow);
$("#workflow-form").elements.recipe.addEventListener("change", updateWorkflowRecipe);
$("#workflow-status-filter").addEventListener("change", renderWorkflows);
$("#workflow-refresh").addEventListener("click", () => loadData());
$("#workflow-dialog").addEventListener("close", () => { workflowDetailId = null; });
$("#detail-dialog").addEventListener("close", () => {
  if (!$("#detail-dialog").open) { actionReviewId = null; actionReviewRecord = null; actionReviewSignature = ""; }
});
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

drawIcons();
initializeForms();
restoreView();
updateWorkflowRecipe();
renderAll();
setConnection(false);
initializeConnection();
setInterval(() => { if (isConnected()) loadData({ quiet: true }); }, 15000);
