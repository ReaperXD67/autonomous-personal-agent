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
  prospectTotal: null,
  prospectOffset: 0,
  prospectLoadNotice: "",
  creatorCoverage: null,
  creatorAutomation: {},
  creatorPilot: {},
  marketingResults: [],
  workflows: [],
  plans: [],
  readiness: null,
  communications: null,
  careerAutopilot: null,
  careerTracking: null,
  view: "overview",
};
let prospectRequestVersion = 0;
let coverageRequestVersion = 0;
let creatorAutomationVersion = 0;
let creatorPilotVersion = 0;
const creatorRunBusy = new Set();
const creatorPilotBusy = new Set();
const creatorPilotRequestKeys = new Map();
const creatorPilotLimits = new Map();
let loadingMoreProspects = false;
const exportingCampaigns = new Set();

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

async function api(path, options = {}, responseType = "json") {
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
  if (responseType === "blob") return response.blob();
  if (responseType === "page") {
    const total = response.headers.get("X-Total-Count");
    return { rows: await response.json(), total: total !== null && /^\d+$/.test(total) ? Number(total) : null };
  }
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
  state.prospectTotal = null;
  state.prospectOffset = 0;
  state.prospectLoadNotice = "";
  state.creatorCoverage = null;
  state.creatorAutomation = {};
  state.creatorPilot = {};
  creatorAutomationVersion += 1;
  creatorPilotVersion += 1;
  prospectRequestVersion += 1;
  coverageRequestVersion += 1;
  state.marketingResults = [];
  state.careerAutopilot = null;
  state.careerTracking = null;
  state.workflows = [];
  state.plans = [];
  state.readiness = null;
  state.communications = null;
  selectedPlanId = null;
  resetCreatorDraftReview();
  $("#marketing-reply-dialog").close();
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
  const prospectVersion = ++prospectRequestVersion;
  try {
    const [status, inference, profiles, opportunities, tasks, audits, actions, campaigns, prospectPage, marketingResults, workflows, plans, readiness, communications, careerAutopilot, careerTracking] = await Promise.all([
      api("/v1/system/status"),
      api("/v1/inference/status"),
      api("/v1/career/profiles"),
      api("/v1/career/opportunities?limit=300"),
      api("/v1/tasks?limit=200"),
      api("/v1/audit-events?limit=100"),
      api("/v1/external-actions?limit=200"),
      api("/v1/marketing/campaigns"),
      api("/v1/marketing/prospects?limit=250&offset=0", {}, "page"),
      api("/v1/marketing/results"),
      api("/v1/workflows"),
      api("/v1/plans"),
      api("/v1/readiness/features"),
      api("/v1/communications/status"),
      api("/v1/career/autopilot").catch((error) => ({ error: error.message, runs: [], readiness: [], sources: [] })),
      api("/v1/career/tracking?limit=100").catch((error) => ({ error: error.message, applications: [], review_candidates: [], sync: [] })),
    ]);
    if (prospectVersion !== prospectRequestVersion || !isConnected()) return false;
    if (state.prospectOffset > 250) state.prospectLoadNotice = "Live refresh returned to the first 250 records so contact and outreach states stay current. Load more again or export the complete campaign.";
    else if (!quiet) state.prospectLoadNotice = "";
    Object.assign(state, { status, inference, profiles, opportunities, tasks, audits, actions, campaigns, prospects: prospectPage.rows, prospectTotal: prospectPage.total, prospectOffset: prospectPage.rows.length, marketingResults, workflows, plans, readiness, communications, careerAutopilot, careerTracking });
    $("#connection-notice").hidden = true;
    setConnection(true);
    renderAll();
    loadCreatorCoverage();
    loadCreatorAutomation();
    loadCreatorPilots();
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
  missions: ["", "Set the scope. <em>Press Play.</em>", "Hunt fresh roles, prepare or submit within reviewed limits, and keep every application traceable."],
  workflows: ["Coordinated autonomy", "Plan. Execute. <em>Verify.</em>", "Turn a multi-step objective into durable work with dependencies, result checks, and a clear stopping point."],
  opportunities: ["", "Your <em>job inbox.</em>", "Compare fresh matches, prepare truthful drafts, and decide what to apply for."],
  campaigns: ["", "Find the creators. <em>You close the deal.</em>", "Research Minecraft channels, start a relevant paid conversation, and hand interested creators back to you."],
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
  { label: "Creator campaigns", description: "Research YouTube creators, contacts, and collaboration ideas", view: "campaigns" },
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

const careerRunChanges = new Set();
const careerMailSyncs = new Set();
const careerApplyHosts = ["boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.ashbyhq.com", "jobs.lever.co", "jobs.eu.lever.co"];

function careerRun(profileId) {
  return (state.careerAutopilot?.runs || []).filter((run) => run.profile_id === profileId)
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))[0] || null;
}

function renderCareerReadiness() {
  const root = $("#career-readiness");
  const wasOpen = $("details", root)?.open || false;
  root.replaceChildren();
  if (!isConnected()) { root.append(node("p", "fine-print", "Connect to check mission prerequisites and source availability.")); return; }
  if (state.careerAutopilot?.error) { root.append(node("p", "notice", "Run readiness could not be loaded. Refresh the workspace before starting a mission.")); return; }
  const ready = state.careerAutopilot?.readiness || [];
  root.append(node("p", "", `${ready.filter((item) => item.can_prepare).length} mission(s) meet preparation requirements · ${ready.filter((item) => item.can_apply).length} meet automatic-application requirements. Configuration is not proof of a successful external application.`));
  const details = node("details", "career-source-status");
  details.open = wasOpen;
  details.append(node("summary", "", "Source connections and current readiness"));
  (state.careerAutopilot?.sources || []).forEach((source) => {
    const row = node("div", "career-source-row");
    row.append(node("strong", "", `${source.name} · ${titleCase(source.status)}`), node("p", "", source.description));
    if (source.url) row.append(researchLink("Open source", source.url));
    details.append(row);
  });
  root.append(details);
}

function openCareerPlay(profileId) {
  if (!isConnected()) return $("#connect-dialog").showModal();
  const profile = state.profiles.find((item) => item.id === profileId);
  if (!profile) return;
  const form = $("#career-play-form");
  form.reset();
  clearFormError(form);
  form.elements.profile_id.value = profile.id;
  const previous = careerRun(profile.id);
  form.elements.max_age_hours.value = previous?.max_age_hours || profile.max_age_hours || 72;
  form.elements.min_score.value = previous?.min_score ?? profile.auto_prepare_min_score ?? 75;
  form.elements.max_applications_per_day.value = previous?.max_applications_per_day || 3;
  $("#career-play-title").textContent = `Play ${profile.name}`;
  $("#career-play-description").textContent = `${profile.desired_titles.join(", ")} · ${profile.locations.join(", ") || "Any configured location"}. The saved résumé, identity, and source settings define this run.`;
  const hosts = $("#career-host-options");
  hosts.replaceChildren();
  careerApplyHosts.forEach((host) => {
    const label = node("label", "checkbox-row");
    const input = node("input");
    input.type = "checkbox";
    input.name = "allowed_hosts";
    input.value = host;
    input.checked = previous?.allowed_hosts?.length ? previous.allowed_hosts.includes(host) : true;
    label.append(input, document.createTextNode(host));
    hosts.append(label);
  });
  updateCareerPlayScope();
  $("#career-play-dialog").showModal();
}

function updateCareerPlayScope() {
  const form = $("#career-play-form");
  const apply = form.elements.mode.value === "apply";
  const readiness = (state.careerAutopilot?.readiness || []).find((item) => item.profile_id === form.elements.profile_id.value);
  form.elements.include_cold_email.disabled = !readiness?.smtp_configured;
  if (!readiness?.smtp_configured) form.elements.include_cold_email.checked = false;
  const includeEmail = form.elements.include_cold_email.checked;
  $("#career-email-scope-help").textContent = readiness?.smtp_configured
    ? state.communications?.transport === "mailpit"
      ? "The current transport is the local Mailpit test inbox. These emails cannot reach employers. The same freshness, fit, shared daily limits, and one-application-per-job guard still apply."
      : "Uses the same freshness, fit, and daily limits, your saved résumé and portfolio, and configured SMTP. One application per job across ATS and email. SMTP acceptance does not prove inbox delivery."
    : "Hiring email is unavailable until SMTP is configured. It only supports one unambiguous hiring address explicitly published in the matched job description.";
  const hosts = $$('input[name="allowed_hosts"]:checked', form).map((input) => input.value);
  $("#career-allowed-hosts").hidden = !apply;
  $("#career-apply-consent").hidden = !apply;
  form.elements.authorize_apply.required = apply;
  const scope = $("#career-play-scope");
  scope.replaceChildren(node("strong", "", apply ? "Review the automatic-application scope" : "Preparation scope"));
  scope.append(node("p", "", apply
    ? `Submit at most ${form.elements.max_applications_per_day.value} applications per rolling 24 hours, at ${form.elements.min_score.value}+ fit, for listings no older than ${form.elements.max_age_hours.value} hours. Authorization lasts ${form.elements.expires_in_hours.value} hours and covers ${hosts.join(", ") || "no ATS hosts"}${includeEmail ? " plus application emails to one unambiguous hiring address explicitly published in each matched job" : " only"}. ATS and email share the cap and one-application-per-job guard.`
    : `Find and prepare relevant applications at ${form.elements.min_score.value}+ fit for listings no older than ${form.elements.max_age_hours.value} hours.${includeEmail ? " Include hiring-email drafts only for explicitly published job contacts." : ""} This run lasts ${form.elements.expires_in_hours.value} hours. Final submissions and sends wait for separate review.`));
  const preparationLimit = Math.min(20, Math.max(0, Number(form.elements.max_applications_per_day.value) || 0) * 2);
  scope.append(node("p", "fine-print", `Preparation is counted separately: up to ${preparationLimit} job preparations for this run and 20 across this mission's runs per rolling 24 hours. Failed attempts count toward preparation limits. Pressing Play again does not reset those limits or the application allowance.`));
  const ready = apply ? readiness?.can_apply : readiness?.can_prepare;
  if (!ready) scope.append(node("p", "notice", "This mission does not yet meet the selected mode's requirements. Check its résumé, application identity, reviewed sources, and feature readiness before pressing Play."));
  const submit = $('button[type="submit"]', form);
  submit.textContent = apply ? "Authorize scope and Play" : "Play preparation";
  submit.disabled = !ready;
}

async function startCareerRun(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.profile_id.value;
  try {
    const answers = JSON.parse(form.elements.answers.value.trim() || "{}");
    if (!answers || typeof answers !== "object" || Array.isArray(answers)) throw new Error("Screening answers must be a JSON object with the inspected field names.");
    const allowedHosts = $$('input[name="allowed_hosts"]:checked', form).map((input) => input.value);
    const includeEmail = !form.elements.include_cold_email.disabled && form.elements.include_cold_email.checked;
    if (form.elements.mode.value === "apply" && (!form.elements.authorize_apply.checked || (!allowedHosts.length && !includeEmail))) throw new Error("Select at least one reviewed destination or the optional hiring-email route, then explicitly authorize this scope.");
    careerRunChanges.add(id);
    await api(`/v1/career/profiles/${encodeURIComponent(id)}/play`, { method: "POST", body: JSON.stringify({
      actor: "dashboard:career", mode: form.elements.mode.value, max_applications_per_day: Number(form.elements.max_applications_per_day.value),
      min_score: Number(form.elements.min_score.value), max_age_hours: Number(form.elements.max_age_hours.value),
      allowed_hosts: allowedHosts, expires_in_hours: Number(form.elements.expires_in_hours.value), answers, include_cold_email: includeEmail,
    }) });
    $("#career-play-dialog").close();
    toast(form.elements.mode.value === "apply" ? "Scoped application run started. Follow its applications and stop it with Pause." : "Preparation run started. Final applications still wait for review.");
    await loadData({ quiet: true });
  } catch (error) { showFormError(form, error instanceof SyntaxError ? new Error("Screening answers are not valid JSON. Use an object such as {} or leave the field blank.") : error); }
  finally { careerRunChanges.delete(id); renderMissions(); }
}

async function pauseCareerRun(id) {
  if (careerRunChanges.has(id)) return;
  careerRunChanges.add(id);
  renderMissions();
  try {
    await api(`/v1/career/profiles/${encodeURIComponent(id)}/pause`, { method: "POST", body: JSON.stringify({ actor: "dashboard:career" }) });
    toast("Mission paused. Work already submitted remains in the application history.");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
  finally { careerRunChanges.delete(id); renderMissions(); }
}

async function syncCareerMail(id) {
  if (careerMailSyncs.has(id) || careerMailPending(id)) return;
  careerMailSyncs.add(id);
  renderMissions();
  try {
    await api(`/v1/career/profiles/${encodeURIComponent(id)}/mail-sync`, { method: "POST" });
    toast("Read-only labeled-mail sync queued. Review inferred replies in the application tracker.");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
  finally { careerMailSyncs.delete(id); renderMissions(); }
}

function careerMailPending(profileId) {
  return state.tasks.some((task) => task.kind === "career.gmail_sync" && task.payload?.profile_id === profileId && ["pending_approval", "queued", "running"].includes(task.status));
}

function missionCard(profile, compact = false) {
  const run = careerRun(profile.id);
  const running = run?.state === "running" && Date.parse(run.expires_at) > Date.now();
  const card = node("article", `mission-card${profile.active ? "" : " inactive"}`);
  const row = node("div", "mission-row");
  const body = node("div");
  body.append(node("span", "tag", running ? run.mode === "apply" ? "Automatic applications running" : "Preparation running" : profile.active ? "Scheduled search" : "Paused mission"));
  body.append(node("h3", "", profile.name));
  body.append(node("p", "", `${profile.desired_titles.join(", ")} · ${profile.locations.join(", ") || "Any location"}`));
  const toggle = button(profile.active || running ? "Pause" : "Play", `button compact${profile.active || running ? "" : " primary"}`, profile.active || running ? "pause-career" : "play-career", profile.id);
  toggle.setAttribute("aria-label", `${profile.active || running ? "Pause" : "Play"} ${profile.name}`);
  toggle.disabled = careerRunChanges.has(profile.id);
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
  if (run) card.append(node("p", "career-run-summary", `${running ? "Current scope" : `Last run: ${titleCase(run.state === "running" ? "expired" : run.state)}`} · ${run.min_score}+ fit · ${run.max_age_hours}h freshness · ${run.used_today || 0}/${run.max_applications_per_day} application reservations in 24h · ${run.include_cold_email ? "ATS + published hiring email" : "selected ATS hosts"} · expires ${researchDate(run.expires_at)}`));
  if (run && Number.isFinite(run.preparation_used_today)) card.append(node("p", "fine-print", `Preparation attempts in 24h: ${run.run_preparation_used_today}/${run.run_preparation_limit_24h} for this run · ${run.preparation_used_today}/${run.preparation_limit_24h} across this mission. Preparation does not consume application reservations.`));
  if (run?.preparation_limit_reason) card.append(node("p", "notice", run.preparation_limit_reason));
  if (run?.last_error) card.append(node("p", "notice", `Run needs attention: ${run.last_error}`));
  if (!compact) {
    const readiness = (state.careerAutopilot?.readiness || []).find((item) => item.profile_id === profile.id);
    const checks = node("div", "career-mission-checks");
    for (const [label, present] of [["Résumé", profile.resume_present], ["Application identity", readiness?.identity_complete], ["Portfolio", readiness?.portfolio_present], ["Reviewed sources", readiness?.sources_enabled]]) {
      checks.append(node("span", "chip", `${label}: ${present === undefined ? "not checked" : present ? "present" : label === "Portfolio" ? "not supplied" : "needed"}`));
    }
    card.append(checks);
    const sources = profile.source_config || {};
    const sourceNames = [sources.arbeitnow ? "Arbeitnow" : "", sources.remotive ? "Remotive (24h delay)" : "", ...["ashby", "greenhouse", "lever", "lever_eu"].map((name) => (sources[`${name}_boards`] || []).length ? `${titleCase(name)}: ${sources[`${name}_boards`].join(", ")}` : "")].filter(Boolean);
    card.append(node("p", "fine-print", `Configured discovery: ${sourceNames.join(" · ") || "No source configured"}`));
    const actions = node("div", "mission-actions");
    actions.append(button("Scan now", "button compact", "scan-profile", profile.id), button("Edit mission", "text-button", "edit-profile", profile.id), button("View applications", "text-button", "career-applications", profile.id));
    const sync = button(careerMailPending(profile.id) ? "Gmail sync in progress…" : "Check labeled Gmail replies", "text-button", "sync-career-mail", profile.id);
    sync.disabled = !readiness?.gmail_configured || careerMailSyncs.has(profile.id) || careerMailPending(profile.id);
    actions.append(sync);
    card.append(actions);
    const lastSync = (state.careerTracking?.sync || []).find((item) => item.profile_id === profile.id);
    card.append(node("p", "fine-print", readiness?.gmail_configured ? `Read-only Gmail label: ${lastSync?.label_name || "Hermes/Careers"} · last sync ${researchDate(lastSync?.last_sync_at)}. Replies are inferred until reviewed.` : "Gmail reply tracking is not configured. You can record verified replies and interview times manually."));
    const items = (state.careerAutopilot?.items || []).filter((item) => item.run_id === run?.id);
    if (items.length) {
      const details = node("details", "career-run-items pipeline-timeline");
      details.dataset.profileId = profile.id;
      details.append(node("summary", "", `Preparation and review · ${items.length} job${items.length === 1 ? "" : "s"}`));
      const entries = node("ol");
      items.slice(0, 10).forEach((item) => {
        const entry = node("li");
        entry.append(node("strong", "", `${item.title} · ${item.company}`), node("p", "fine-print", `${titleCase(item.state)}${item.reason ? ` · ${item.reason}` : ""}`));
        if (state.opportunities.some((opportunity) => opportunity.id === item.opportunity_id)) entry.append(button("Inspect job", "text-button", "view-opportunity", item.opportunity_id));
        if (item.action_id) entry.append(button("View exact action", "text-button", "review-action", item.action_id));
        entries.append(entry);
      });
      details.append(entries);
      card.append(details);
    }
  }
  return card;
}

function renderMissions() {
  renderCareerReadiness();
  const overview = $("#overview-missions");
  const full = $("#mission-list");
  const expanded = new Set($$(".career-run-items[open]", full).map((item) => item.dataset.profileId));
  overview.replaceChildren();
  full.replaceChildren();
  if (!state.profiles.length) {
    overview.append(empty("No live missions yet", "Create your first career mission to start scanning reviewed sources."));
    full.append(empty("No missions created", "Your first mission can watch fresh jobs and internships every six hours for free.", true));
    return;
  }
  state.profiles.slice(0, 2).forEach((profile) => overview.append(missionCard(profile, true)));
  state.profiles.forEach((profile) => full.append(missionCard(profile)));
  $$(".career-run-items", full).forEach((item) => { item.open = expanded.has(item.dataset.profileId); });
}

function opportunityDateLabel(opportunity) {
  if (opportunity.published_at_basis === "updated") return `Updated ${timeAgo(opportunity.published_at)} · publication unverified`;
  if (opportunity.published_at_basis !== "published") return "Publication date unverified";
  return `Published ${timeAgo(opportunity.published_at)}`;
}

function opportunityRow(opportunity) {
  const row = node("button", "job-row");
  row.type = "button";
  row.dataset.action = "view-opportunity";
  row.dataset.id = opportunity.id;
  const initials = opportunity.company.split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toUpperCase() || "J";
  row.append(node("span", "logo", initials));
  const copy = node("span");
  copy.append(node("strong", "", opportunity.title), node("small", "", `${opportunity.company} · ${opportunity.location || "Location not listed"} · ${opportunityDateLabel(opportunity)}`));
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
  meta.append(node("span", "chip status-chip", titleCase(opportunity.status)), node("span", "chip", opportunityDateLabel(opportunity)));
  const profile = state.profiles.find((item) => item.id === opportunity.profile_id);
  if (profile && opportunity.published_at_basis === "published" && Date.now() - Date.parse(opportunity.published_at) > profile.max_age_hours * 3600000) meta.append(node("span", "chip status-chip", "Outside freshness window · history"));
  if (opportunity.remote) meta.append(node("span", "chip", "Remote"));
  if (opportunity.employment_type) meta.append(node("span", "chip", titleCase(opportunity.employment_type)));
  if (opportunity.latest_draft) meta.append(node("span", "chip", "Draft ready"));
  card.append(meta);
  const reasons = node("ul", "reason-list");
  opportunity.score_reasons.slice(0, 3).forEach((reason) => reasons.append(node("li", "", reason)));
  card.append(reasons);
  card.append(careerQualityEvidence(opportunity, true));
  if (opportunity.source === "remotive") card.append(researchLink("View the original Remotive listing", opportunity.source_url));
  const actions = node("div", "card-actions");
  actions.append(button("Inspect", "button compact", "view-opportunity", opportunity.id));
  if (opportunity.status !== "shortlisted") actions.append(button("Shortlist", "button compact", "shortlist-opportunity", opportunity.id));
  actions.append(button(opportunity.latest_draft ? "Regenerate draft" : "Generate private draft", "text-button", "draft-opportunity", opportunity.id));
  actions.append(button("Record application update", "text-button", "career-event", opportunity.id));
  card.append(actions);
  return card;
}

function filteredOpportunities() {
  const profile = $("#opportunity-profile-filter").value;
  const status = $("#opportunity-status-filter").value;
  const search = $("#opportunity-search").value.trim().toLocaleLowerCase();
  const age = Number($("#opportunity-age-filter").value);
  const quality = $("#opportunity-quality-filter").value;
  return state.opportunities.filter((item) => (!profile || item.profile_id === profile) && (!status || item.status === status)
    && (!quality || item.quality?.disposition === quality)
    && (!search || `${item.title} ${item.company} ${item.source}`.toLocaleLowerCase().includes(search))
    && (!age || (item.published_at_basis === "published" && Date.now() - Date.parse(item.published_at) <= age * 3600000)));
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
  renderCareerTracking();
  renderCareerAttention();
}

function careerQualityEvidence(opportunity, compact = false) {
  const quality = opportunity.quality;
  const root = node(compact ? "details" : "section", "career-quality");
  if (!quality) { root.append(node("p", "fine-print", "Job-risk checks unavailable. Inspect the original listing.")); return root; }
  root.classList.toggle("review-required", quality.disposition === "review_required");
  root.append(node(compact ? "summary" : "h3", "", quality.disposition === "review_required" ? "Job-risk signals · review required" : "No strong job-risk flags found"));
  const list = node("ul");
  (quality.signals || []).forEach((signal) => list.append(node("li", "", signal.message)));
  if (list.childElementCount) root.append(list);
  root.append(node("p", "fine-print", quality.limitations || "Automated checks cannot prove an employer or listing is genuine."));
  return root;
}

function renderCareerAttention() {
  const root = $("#career-attention-list");
  root.replaceChildren();
  const profileId = $("#opportunity-profile-filter").value;
  const tracking = state.careerTracking;
  if (!tracking || tracking.error) { root.append(node("p", "fine-print", "Refresh to load application decisions and reply evidence.")); return; }
  const applications = (tracking.applications || []).filter((item) => !profileId || item.profile_id === profileId);
  const priorities = { offer: 0, interview: 1, shortlisted: 2 };
  const decisions = applications.filter((item) => item.status in priorities || item.needs_review)
    .sort((a, b) => (priorities[a.status] ?? 3) - (priorities[b.status] ?? 3) || Date.parse(b.updated_at) - Date.parse(a.updated_at));
  decisions.slice(0, 6).forEach((application) => {
    const row = node("article", "career-attention-item");
    const copy = node("div");
    copy.append(node("strong", "", `${titleCase(application.status)} · ${application.company} · ${application.title}`));
    copy.append(node("p", "fine-print", application.needs_review ? "Mailbox signal needs review against the original reply." : application.status === "interview" ? "Check the confirmed time and prepare for the interview." : "Review the recorded outcome and decide your next step."));
    row.append(copy, button("Review outcome", "button compact", "career-event", application.opportunity_id));
    root.append(row);
  });
  const signals = (tracking.review_candidates || []).map((signal, index) => ({ signal, index })).filter(({ signal }) => !profileId || signal.profile_id === profileId);
  signals.slice(0, Math.max(0, 8 - decisions.length)).forEach(({ signal, index }) => {
    const row = node("article", "career-attention-item");
    const copy = node("div");
    copy.append(node("strong", "", signal.subject || "Unmatched application reply"), node("p", "fine-print", `Suggested ${titleCase(signal.suggested_status)} · application match needs review.`));
    row.append(copy, button("Match reply", "button compact", "review-career-mail", String(index)));
    root.append(row);
  });
  const total = decisions.length + signals.length;
  $("#career-attention-count").textContent = `${total} decision${total === 1 ? "" : "s"} in loaded application history`;
  if (!total) root.append(node("p", "fine-print", "No shortlist, interview, offer, or uncertain reply needs attention in this view."));
  if (total > root.childElementCount) root.append(node("p", "fine-print", "More evidence is available in the application tracker below."));
}

function renderProfileFilter() {
  const filter = $("#opportunity-profile-filter");
  const selected = filter.value;
  filter.replaceChildren(new Option("All missions", ""));
  state.profiles.forEach((profile) => filter.append(new Option(profile.name, profile.id)));
  if ([...filter.options].some((option) => option.value === selected)) filter.value = selected;
}

function renderCareerTracking() {
  const tracking = state.careerTracking;
  const list = $("#career-pipeline-list");
  const expanded = new Set($$("details[open]", list).map((item) => item.dataset.opportunityId));
  const summary = $("#career-pipeline-summary");
  const review = $("#career-mail-review");
  const suggestions = $("#career-tracking-suggestions");
  list.replaceChildren(); summary.replaceChildren(); review.replaceChildren(); suggestions.replaceChildren();
  if (!tracking || tracking.error) {
    list.append(empty("Application tracking is not loaded", isConnected() ? "Refresh to load durable application outcomes and mailbox review signals." : "Connect your workspace to load application history."));
    return;
  }
  const profileId = $("#opportunity-profile-filter").value;
  const applications = (tracking.applications || []).filter((item) => !profileId || item.profile_id === profileId);
  const signals = (tracking.review_candidates || []).map((signal, index) => ({ signal, index })).filter(({ signal }) => !profileId || signal.profile_id === profileId);
  const counts = [["Tracked", applications.length], ["Replies", applications.filter((item) => item.status === "recruiter_reply").length], ["Shortlisted", applications.filter((item) => item.status === "shortlisted").length], ["Interviews", applications.filter((item) => item.status === "interview").length], ["Offers", applications.filter((item) => item.status === "offer").length], ["Needs review", signals.length + applications.filter((item) => item.needs_review).length]];
  counts.forEach(([label, count]) => summary.append(node("span", "chip", `${label}: ${count}`)));
  if (!applications.length) list.append(empty("No tracked applications in this view", "Applications appear here after submission or a reviewed manual update. Select a mission to focus its history."));
  applications.forEach((application) => {
    const row = node("article", "pipeline-entry");
    const header = node("div", "pipeline-entry-head");
    const title = node("div");
    title.append(node("h3", "", `${application.title} · ${application.company}`), node("p", "", `${titleCase(application.status)} · ${titleCase(application.status_source || "recorded")} · updated ${researchDate(application.updated_at)}`));
    header.append(title, button("Record update", "button compact", "career-event", application.opportunity_id));
    row.append(header);
    const opportunity = state.opportunities.find((item) => item.id === application.opportunity_id);
    if (opportunity) row.append(node("p", "fine-print", `${titleCase(opportunity.source)} · ${opportunityDateLabel(opportunity)} · ${opportunity.score}/100 fit at discovery`));
    if (application.needs_review) row.append(node("p", "pipeline-review-note", "Inferred status — review the message evidence before relying on it."));
    if (application.meeting_at) row.append(node("p", "pipeline-meeting", `Interview / meeting: ${researchDate(application.meeting_at)}`));
    else if (application.status === "interview") row.append(node("p", "pipeline-review-note", "Interview signal recorded; date and time still need review."));
    if (application.evidence) row.append(node("p", "fine-print", application.evidence));
    const details = node("details", "pipeline-timeline");
    details.dataset.opportunityId = application.opportunity_id;
    details.open = expanded.has(application.opportunity_id);
    details.append(node("summary", "", "Status timeline and source evidence"));
    const timeline = node("ol");
    if (application.applied_at) timeline.append(node("li", "", `Submission recorded · ${researchDate(application.applied_at)}`));
    (application.events || []).forEach((event) => {
      const entry = node("li");
      entry.append(node("strong", "", `${titleCase(event.status)} · ${researchDate(event.occurred_at)}`), node("p", "fine-print", `${titleCase(event.source)} · confidence ${event.confidence ?? "not recorded"}${event.needs_review ? " · review needed" : ""}`));
      if (event.evidence) entry.append(node("p", "", event.evidence));
      if (event.meeting_at) entry.append(node("p", "fine-print", `Meeting: ${researchDate(event.meeting_at)}`));
      timeline.append(entry);
    });
    if (!timeline.childElementCount) timeline.append(node("li", "", "No dated events recorded yet."));
    details.append(timeline, researchLink("Open original application", application.apply_url));
    row.append(details);
    list.append(row);
  });
  if (signals.length) {
    review.append(node("h3", "", "Mailbox signals that need a match"), node("p", "fine-print", "These labeled messages have not been safely linked to an application. Review the evidence and choose the correct role."));
    signals.forEach(({ signal, index }) => {
      const row = node("article", "mail-signal");
      row.append(node("h4", "", signal.subject || "No subject"), node("p", "fine-print", `${signal.sender || "Sender unavailable"} · ${researchDate(signal.received_at)} · suggested ${titleCase(signal.suggested_status)}`));
      if (signal.snippet) row.append(node("p", "", signal.snippet));
      if (signal.match_reason || signal.evidence) row.append(node("p", "fine-print", signal.match_reason || signal.evidence));
      row.append(button("Review and link to an application", "button compact", "review-career-mail", String(index)));
      review.append(row);
    });
  }
  if ((tracking.suggestions || []).length) {
    suggestions.append(node("h3", "", "Next steps from recorded outcomes"));
    const notes = node("ul");
    tracking.suggestions.forEach((suggestion) => notes.append(node("li", "", suggestion)));
    suggestions.append(notes);
  }
}

function openCareerEvent(opportunityId = null, signalIndex = null) {
  const form = $("#career-event-form");
  form.reset();
  clearFormError(form);
  const signal = signalIndex === null ? null : state.careerTracking?.review_candidates?.[signalIndex];
  const context = $("#career-event-context");
  context.replaceChildren();
  form.elements.gmail_message_id.value = signal?.gmail_message_id || "";
  const choices = new Map(state.opportunities.filter((item) => !signal || (item.profile_id === signal.profile_id && item.applied_at)).map((item) => [item.id, `${item.title} · ${item.company}`]));
  (state.careerTracking?.applications || []).filter((item) => !signal || item.profile_id === signal.profile_id).forEach((item) => choices.set(item.opportunity_id, `${item.title} · ${item.company}`));
  form.elements.opportunity_id.replaceChildren(new Option("Choose the matching application", ""));
  choices.forEach((label, id) => form.elements.opportunity_id.append(new Option(label, id)));
  form.elements.opportunity_id.value = opportunityId || "";
  if (signal) {
    context.append(node("strong", "", "Inferred mailbox signal — verify the application and status"), node("p", "", signal.subject || "No subject"), node("p", "fine-print", `${signal.sender || "Unknown sender"} · ${researchDate(signal.received_at)}`), node("p", "", signal.snippet || signal.evidence || "No excerpt recorded."));
    if ([...form.elements.status.options].some((option) => option.value === signal.suggested_status)) form.elements.status.value = signal.suggested_status;
    if (!choices.size) context.append(node("p", "notice", "Record the matching job as submitted before linking this mailbox signal."));
  } else {
    const application = state.careerTracking?.applications?.find((item) => item.opportunity_id === opportunityId);
    if (application && [...form.elements.status.options].some((option) => option.value === application.status)) form.elements.status.value = application.status;
  }
  context.append(node("p", "fine-print", `Entered times use ${Intl.DateTimeFormat().resolvedOptions().timeZone || "your browser's local time zone"}. Leave an unconfirmed meeting time blank.`));
  updateCareerEventChoices();
  $("#career-event-dialog").showModal();
}

function updateCareerEventChoices() {
  const form = $("#career-event-form");
  const id = form.elements.opportunity_id.value;
  const submitted = state.opportunities.some((item) => item.id === id && item.applied_at)
    || (state.careerTracking?.applications || []).some((item) => item.opportunity_id === id);
  [...form.elements.status.options].forEach((option) => { option.disabled = Boolean(id && !submitted && option.value !== "submitted"); });
  if (id && !submitted) form.elements.status.value = "submitted";
  form.elements.meeting_at.disabled = form.elements.status.value !== "interview";
  if (form.elements.meeting_at.disabled) form.elements.meeting_at.value = "";
}

async function saveCareerEvent(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.opportunity_id.value;
  const payload = { status: form.elements.status.value, note: form.elements.note.value.trim(), actor: "dashboard:career" };
  try {
    if (form.elements.occurred_at.value) payload.occurred_at = new Date(form.elements.occurred_at.value).toISOString();
    if (form.elements.status.value === "interview" && form.elements.meeting_at.value) payload.meeting_at = new Date(form.elements.meeting_at.value).toISOString();
    if (form.elements.gmail_message_id.value) payload.gmail_message_id = form.elements.gmail_message_id.value;
    await api(`/v1/career/opportunities/${encodeURIComponent(id)}/events`, { method: "POST", body: JSON.stringify(payload) });
    $("#career-event-dialog").close();
    toast("Reviewed application update recorded");
    await loadData({ quiet: true });
  } catch (error) { showFormError(form, error); }
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
  const task = state.tasks.find((item) => item.id === action.task_id);
  root.replaceChildren(
    node("span", "tag amber-tag", "Exact approval packet"),
    node("h2", "", email ? "Review this one email" : titleCase(action.action_type)),
    node("p", "", `${action.target_display} · expires ${formatDate(action.expires_at)}`),
  );
  if (email) root.append(node("p", `email-action-status ${action.status}`, statusLabel), node("p", "fine-print", statusHelp));
  if (email && action.status === "queued" && task && new Date(task.next_attempt_at).getTime() > Date.now()) {
    root.append(node("p", "notice", `Paced send time: ${formatDate(task.next_attempt_at)}. Hermes will not release this email before that time.`));
  }
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
    root.append(node("p", "fine-print", email ? "Approval authorizes only the recipient, subject and body shown above. External SMTP is released through durable rate limits, so approving several messages cannot create an immediate burst." : "Approval authorizes only the exact action shown above."));
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
  if (communications?.pacing?.enabled) {
    const pacing = communications.pacing;
    status.append(node("p", "fine-print", `Durable pacing: at least ${Math.ceil(pacing.minimum_interval_seconds / 60)} minutes between messages, ${Math.ceil(pacing.same_domain_interval_seconds / 60)} minutes to the same recipient domain, no more than ${pacing.hourly_limit} per rolling hour or ${pacing.daily_limit} per rolling 24 hours, plus up to ${Math.ceil(pacing.jitter_seconds / 60)} minutes of jitter.`));
  }

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

function creatorHandoffLabel(campaign) {
  return [campaign.handoff_email, campaign.handoff_discord ? `Discord: ${campaign.handoff_discord}` : ""].filter(Boolean).join(" · ") || "No owner contact configured";
}

async function loadCreatorPilots(campaignId = null) {
  if (!isConnected()) return;
  const version = ++creatorPilotVersion;
  const campaigns = state.campaigns.filter((campaign) => !campaignId || campaign.id === campaignId);
  const results = await Promise.all(campaigns.map(async (campaign) => {
    try { return [campaign.id, { task: await api(`/v1/marketing/campaigns/${encodeURIComponent(campaign.id)}/pilot-research`) }]; }
    catch (error) { return [campaign.id, { error: error.message }]; }
  }));
  if (version !== creatorPilotVersion || !isConnected()) return;
  Object.assign(state.creatorPilot, Object.fromEntries(results));
  renderCampaigns();
}

function creatorPilotPanel(campaign) {
  const panel = node("details", "creator-pilot");
  panel.dataset.campaignId = campaign.id;
  panel.append(node("summary", "", "Research a creator shortlist"));
  panel.append(node("p", "fine-print", "Refresh saved creators through the YouTube API and rank the evidence. No model tokens, contact authorization or emails are used by this step."));
  const data = state.creatorPilot[campaign.id];
  const task = data?.task;
  const pending = task && ["queued", "running", "retry_scheduled", "pending_approval"].includes(task.status);
  const controls = node("div", "creator-pilot-controls");
  const label = node("label", "", "Creators to research");
  const limit = node("input");
  Object.assign(limit, { type: "number", min: "1", max: "10", step: "1", value: String(creatorPilotLimits.get(campaign.id) || 5), required: true });
  limit.name = "creator_pilot_limit";
  limit.disabled = Boolean(pending) || creatorPilotBusy.has(campaign.id);
  limit.addEventListener("input", () => creatorPilotLimits.set(campaign.id, limit.value));
  label.append(limit);
  const start = button(pending ? "Research in progress…" : "Research shortlist", "button", "research-creator-pilot", campaign.id);
  start.disabled = !data || Boolean(pending) || creatorPilotBusy.has(campaign.id);
  const refresh = button("Refresh research status", "text-button", "refresh-creator-pilot", campaign.id);
  refresh.disabled = creatorPilotBusy.has(campaign.id);
  controls.append(label, start, refresh);
  panel.append(controls, node("p", "fine-print", "At most ten saved creators and three recent uploads each. Start with Find Minecraft creators if the campaign has no research yet."));
  const status = node("div", "creator-pilot-status");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  if (data?.error) status.append(node("p", "notice", `Could not load research: ${data.error}`));
  else if (!data) status.append(node("p", "fine-print", "Loading saved research status…"));
  else if (!task) status.append(node("p", "fine-print", "No shortlist research has run for this campaign yet."));
  else {
    const title = pending ? task.status === "running" ? "Researching public channel evidence…" : "Shortlist research queued"
      : task.status === "succeeded" ? "Shortlist ready for review" : "Research did not complete";
    status.append(node("strong", "", title), node("p", "fine-print", `Updated ${formatDate(task.updated_at || task.created_at)}. Drafting and sending remain separate decisions.`));
    if (!pending && task.status !== "succeeded") status.append(node("p", "fine-print", `Inspect the task before trying again.${task.error_code ? ` Reason: ${titleCase(task.error_code)}.` : ""}`));
    status.append(button("Inspect research task", "text-button", "view-audit", task.id));
  }
  panel.append(status);
  const report = task?.output;
  if (Array.isArray(report?.ranked)) {
    panel.append(node("p", "fine-print", `${report.researched || 0} researched · ${report.selected_count || 0} selected · ${report.requires_contact_review_count || 0} need contact review · ${report.failed || 0} research failures`));
    const list = node("ol", "creator-pilot-results");
    for (const result of report.ranked) {
      const row = node("li", "creator-pilot-result");
      row.append(node("strong", "", result.display_name || "Recorded creator"));
      row.append(node("p", "fine-print", `${titleCase(result.status)} · score ${result.score ?? "unknown"} · ${result.subscriber_count == null ? "subscriber count unknown" : `${Number(result.subscriber_count).toLocaleString()} recorded subscribers`}`));
      for (const reason of result.reasons || []) row.append(node("p", "fine-print", reason));
      if (result.last_published_at) row.append(researchLink(`Published activity: ${researchDate(result.last_published_at)}`, result.latest_activity_url));
      if (result.last_minecraft_published_at) row.append(node("p", "fine-print", `Observed Minecraft publication: ${researchDate(result.last_minecraft_published_at)}`));
      if (result.observed_language) {
        const source = { defaultAudioLanguage: "declared audio language", defaultLanguage: "declared video language" }[result.language_source] || "public video metadata";
        row.append(node("p", "fine-print", `Published language: ${result.observed_language} · ${source}`));
      }
      for (const gap of result.gaps || []) row.append(node("p", "notice", gap));
      row.append(node("p", "fine-print", `${result.public_business_contact_count || 0} public business-contact candidates · ${result.contact_authorized ? "contact already reviewed" : "contact review required"}`));
      for (const evidence of result.contact_evidence || []) {
        if (evidence.excerpt) row.append(node("blockquote", "source-excerpt", evidence.excerpt));
        if (evidence.source_url) row.append(researchLink("Public contact source", evidence.source_url));
      }
      const next = button(result.status === "selected" && result.contact_authorized ? "Draft introduction" : "Review creator evidence", "text-button", "review-pilot-prospect", result.prospect_id);
      next.dataset.campaignId = campaign.id;
      next.dataset.prepareDraft = String(result.status === "selected" && result.contact_authorized);
      row.append(next);
      list.append(row);
    }
    panel.append(list);
    if (report.caveat) panel.append(node("p", "fine-print", report.caveat));
  }
  return panel;
}

async function researchCreatorPilot(campaignId) {
  if (creatorPilotBusy.has(campaignId)) return;
  const panel = $$(".creator-pilot").find((item) => item.dataset.campaignId === campaignId);
  const input = $('input[name="creator_pilot_limit"]', panel);
  if (!input.reportValidity()) return;
  const limit = Number(input.value);
  if (!creatorPilotRequestKeys.has(campaignId)) creatorPilotRequestKeys.set(campaignId, crypto.randomUUID());
  creatorPilotBusy.add(campaignId);
  renderCampaigns();
  try {
    const task = await api(`/v1/marketing/campaigns/${encodeURIComponent(campaignId)}/pilot-research`, {
      method: "POST", body: JSON.stringify({ actor: "dashboard:marketing", idempotency_key: creatorPilotRequestKeys.get(campaignId), limit }),
    });
    creatorPilotRequestKeys.delete(campaignId);
    if (!isConnected() || !state.campaigns.some((campaign) => campaign.id === campaignId)) return;
    state.creatorPilot[campaignId] = { task };
    toast("API research queued. Review the ranked sources when it completes.");
  } catch (error) {
    if (isConnected()) state.creatorPilot[campaignId] = { ...state.creatorPilot[campaignId], error: error.message };
  }
  finally { creatorPilotBusy.delete(campaignId); renderCampaigns(); }
}

async function reviewPilotProspect(prospectId, campaignId, prepareDraft) {
  try {
    const prospect = await api(`/v1/marketing/prospects/${encodeURIComponent(prospectId)}`);
    if (!isConnected() || !state.campaigns.some((campaign) => campaign.id === campaignId)) return;
    if (prospect.campaign_id !== campaignId) throw new Error("The creator no longer belongs to this campaign. Refresh research.");
    if (prepareDraft && prospect.contact_authorized_at && !prospect.suppressed_at) {
      openMarketingReply(prospect, "initial");
      $("#marketing-reply-form").elements.draft_method.value = "ai";
      updateMarketingDraftMode();
      loadCreatorDraftReview();
    } else openProspectDialog(prospect);
  } catch (error) { toast(error.message, true); }
}

async function loadCreatorAutomation() {
  if (!isConnected()) return;
  const version = ++creatorAutomationVersion;
  const results = await Promise.all(state.campaigns.map(async (campaign) => {
    try { return [campaign.id, await api(`/v1/marketing/campaigns/${campaign.id}/automation`)]; }
    catch (error) { return [campaign.id, { error: error.message }]; }
  }));
  if (version !== creatorAutomationVersion || !isConnected()) return;
  state.creatorAutomation = Object.fromEntries(results);
  renderCampaigns();
  renderCreatorWork();
}

function creatorAutomationPanel(campaign) {
  const panel = node("div", "creator-automation");
  const data = state.creatorAutomation[campaign.id];
  if (!data) { panel.append(node("p", "fine-print", "Loading outreach run status…")); return panel; }
  if (data.error) { panel.append(node("p", "notice", data.error)); return panel; }
  const run = data.run;
  const active = run?.state === "running" && new Date(run.expires_at) > new Date();
  panel.append(node("strong", "", active ? "Automatic outreach is running" : run ? `Run ${run.state === "running" ? "expired" : titleCase(run.state).toLowerCase()}` : "Automatic outreach is off"));
  if (run) {
    panel.append(node("p", "fine-print", `${run.used_today || 0} / ${run.max_initials_per_day} introductions authorized in 24h · expires ${formatDate(run.expires_at)}`));
    panel.append(node("p", "fine-print", run.auto_handoff ? "Owner handoff enabled after reviewed interest." : "Handoff emails require individual approval."));
    if (run.reason) panel.append(node("p", "fine-print", run.reason));
  }
  const controls = node("div", "card-actions");
  const toggle = button(active ? "Pause outreach" : "Authorize outreach run", active ? "button" : "button primary", active ? "pause-creator-run" : "start-creator-run", campaign.id);
  toggle.disabled = creatorRunBusy.has(campaign.id) || (!active && !data.readiness?.smtp_configured);
  controls.append(toggle);
  const sync = button("Check creator replies", "text-button", "sync-creator-replies", campaign.id);
  sync.disabled = !data.readiness?.gmail_configured || creatorRunBusy.has(campaign.id);
  controls.append(sync);
  panel.append(controls, node("p", "fine-print", data.readiness?.gmail_configured ? `Gmail label read configured · last sync ${formatDate(data.gmail_sync?.last_sync_at)} · ${data.pending_reply_count || 0} replies need review.` : "Creator Gmail is not configured. Record replies manually; no mailbox is being monitored."));
  if (!data.readiness?.smtp_configured) panel.append(node("p", "notice", "Configure a sending transport in Email setup before authorizing a run."));
  return panel;
}

function renderCreatorWork() {
  const queue = $("#creator-work-queue");
  const inbox = $("#creator-reply-inbox");
  queue.replaceChildren(); inbox.replaceChildren();
  const interested = state.prospects.filter(canPrepareCreatorHandoff);
  const questions = state.prospects.filter((item) => item.status === "question" && !item.suppressed_at);
  const contacts = state.prospects.filter((item) => !item.suppressed_at && hasUnreviewedContact(item));
  for (const [label, items, action, cta] of [["Ready for your handoff", interested, "plan-marketing-handoff", "Prepare handoff"], ["Questions to answer", questions, "reply-prospect", "Write answer"], ["Public contacts to review", contacts, "edit-prospect", "Review contact"]]) {
    const section = node("div", "creator-decision-group");
    section.append(node("h3", "", `${label} · ${items.length}`));
    items.slice(0, 3).forEach((prospect) => {
      const row = node("div", "creator-decision-row");
      row.append(node("span", "", prospect.display_name), button(cta, "text-button", action, prospect.id));
      section.append(row);
    });
    if (!items.length) section.append(node("p", "fine-print", "Nothing waiting in the loaded shortlist."));
    queue.append(section);
  }
  for (const campaign of state.campaigns) {
    const data = state.creatorAutomation[campaign.id];
    if (!data?.pending_replies?.length) continue;
    const section = node("section", "creator-reply-group");
    section.append(node("h3", "", `${campaign.name} · reply review`));
    for (const reply of data.pending_replies) {
      const row = node("article", "creator-mail-row");
      row.append(node("strong", "", reply.subject || "No subject"), node("p", "fine-print", `${reply.sender} · ${formatDate(reply.received_at)}`), node("p", "", reply.snippet || "No excerpt available. Open the original in your mailbox."), node("p", "fine-print", `${titleCase(reply.suggested_classification)} suggestion · ${reply.match_reason}`));
      const review = button("Review reply", "button", "review-creator-mail", reply.id);
      review.dataset.campaignId = campaign.id;
      row.append(review); section.append(row);
    }
    if (data.pending_reply_count > data.pending_replies.length) section.append(node("p", "fine-print", `Showing ${data.pending_replies.length} of ${data.pending_reply_count} replies. Review these to load earlier replies.`));
    inbox.append(section);
  }
}

function openCreatorRun(campaignId) {
  const campaign = state.campaigns.find((item) => item.id === campaignId);
  if (!campaign) return;
  const form = $("#creator-run-form"); form.reset(); clearFormError(form);
  form.elements.campaign_id.value = campaignId;
  const context = $("#creator-run-context"); context.replaceChildren();
  context.append(node("strong", "", campaign.name), node("p", "", campaign.paid_offer_details), node("p", "fine-print", `Owner contact: ${creatorHandoffLabel(campaign)}`));
  $("#creator-run-dialog").showModal();
}

async function saveCreatorRun(event) {
  const form = event.currentTarget;
  if (!form.elements.authorize_run.checked) throw new Error("Confirm the displayed sending scope before starting.");
  await api(`/v1/marketing/campaigns/${form.elements.campaign_id.value}/automation/start`, { method: "POST", body: JSON.stringify({ actor: "dashboard:marketing", max_initials_per_day: Number(form.elements.max_initials_per_day.value), expires_in_hours: Number(form.elements.expires_in_hours.value), auto_handoff: form.elements.auto_handoff.checked }) });
  $("#creator-run-dialog").close(); toast("Limited creator run authorized"); await loadData({ quiet: true });
}

async function creatorRunAction(campaignId, action) {
  if (creatorRunBusy.has(campaignId)) return;
  creatorRunBusy.add(campaignId); renderCampaigns();
  try {
    await api(`/v1/marketing/campaigns/${campaignId}/${action === "pause" ? "automation/pause" : "replies/sync"}`, { method: "POST", body: JSON.stringify({ actor: "dashboard:marketing" }) });
    toast(action === "pause" ? "Outreach authority paused" : "Creator reply check queued");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
  finally { creatorRunBusy.delete(campaignId); renderCampaigns(); }
}

function openCreatorMailReview(campaignId, replyId) {
  const reply = state.creatorAutomation[campaignId]?.pending_replies?.find((item) => item.id === replyId);
  if (!reply) return;
  const form = $("#creator-mail-review-form"); form.reset(); clearFormError(form);
  form.elements.campaign_id.value = campaignId; form.elements.reply_id.value = replyId;
  form.elements.prospect_id.replaceChildren(new Option("Choose the matching creator", ""));
  state.prospects.filter((item) => item.campaign_id === campaignId && item.contact_email?.toLowerCase() === reply.sender.toLowerCase()).forEach((item) => form.elements.prospect_id.append(new Option(item.display_name, item.id)));
  if (reply.prospect_id && !Array.from(form.elements.prospect_id.options).some((option) => option.value === reply.prospect_id)) form.elements.prospect_id.append(new Option("Matched creator outside loaded shortlist", reply.prospect_id));
  form.elements.prospect_id.value = reply.prospect_id || "";
  form.elements.prospect_id.required = true;
  const context = $("#creator-mail-review-context"); context.replaceChildren();
  context.append(node("strong", "", reply.subject), node("p", "fine-print", `${reply.sender} · ${formatDate(reply.received_at)}`), node("p", "", reply.snippet), node("p", "notice", "This is a metadata excerpt, not the full email. Confirm the complete message in your mailbox before recording interest."));
  if (reply.suggested_feedback_tags?.length) context.append(node("p", "fine-print", `Possible feedback to check: ${reply.suggested_feedback_tags.map(titleCase).join(", ")}. Confirm only what the creator actually said below.`));
  $("#creator-mail-review-dialog").showModal();
}

function canPrepareCreatorHandoff(prospect) {
  const exists = prospect.latest_message?.stage === "handoff"
    && ["pending_approval", "queued", "executing", "succeeded", "ambiguous"].includes(prospect.latest_message.action_status);
  return prospect.status === "interested" && !prospect.suppressed_at && !exists;
}

async function saveCreatorMailReview(event) {
  const form = event.currentTarget;
  await api(`/v1/marketing/campaigns/${form.elements.campaign_id.value}/replies/${form.elements.reply_id.value}/review`, { method: "POST", body: JSON.stringify({ actor: "dashboard:marketing", prospect_id: form.elements.prospect_id.value || null, classification: form.elements.classification.value, note: form.elements.note.value.trim(), feedback_tags: reviewedFeedbackTags(form) }) });
  $("#creator-mail-review-dialog").close(); toast("Reply review recorded"); await loadData({ quiet: true });
}

function renderMarketingMetrics() {
  const totals = state.marketingResults.reduce((summary, result) => {
    for (const key of ["discovered", "emails_sent", "replies", "initial_sent", "handoffs_sent"]) {
      summary[key] += Number(result.metrics[key] || 0);
    }
    return summary;
  }, { discovered: 0, emails_sent: 0, replies: 0, initial_sent: 0, handoffs_sent: 0 });
  const replyRate = totals.initial_sent ? (totals.replies / totals.initial_sent) * 100 : 0;
  $("#marketing-metric-found").textContent = totals.discovered.toLocaleString();
  $("#marketing-metric-sent").textContent = totals.emails_sent.toLocaleString();
  $("#marketing-metric-replies").textContent = `${replyRate.toFixed(1)}%`;
  $("#marketing-metric-signups").textContent = totals.handoffs_sent.toLocaleString();
}

function campaignCard(campaign) {
  const result = marketingResult(campaign.id);
  const metrics = result.metrics;
  const card = node("article", `panel campaign-card${campaign.active ? "" : " inactive"}`);
  const top = node("div", "campaign-card-top");
  const copy = node("div");
  copy.append(
    node("span", "chip", campaign.outreach_mode === "paid" ? "Paid partnerships" : "Community pilot"),
    node("h3", "", campaign.name),
    node("p", "", `${campaign.discovery_queries.join(" · ")} · ${campaign.min_subscribers.toLocaleString()}–${campaign.max_subscribers.toLocaleString()} subscribers`),
  );
  top.append(copy);
  card.append(top);

  const funnel = node("div", "funnel-list");
  const stages = [
    ["Found", metrics.discovered || 0],
    ["Introductions", metrics.initial_sent || 0],
    ["Replies", metrics.replies || 0],
    ["Positive", metrics.positive_replies || 0],
    [campaign.outreach_mode === "paid" ? "Handed over" : "Converted", campaign.outreach_mode === "paid" ? metrics.handoffs_sent || 0 : metrics.converted || 0],
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
  if (campaign.outreach_mode === "paid") {
    card.append(node("p", "campaign-brief", campaign.paid_offer_details || "Add a paid collaboration brief."));
    card.append(node("p", "fine-print", `Owner handoff: ${creatorHandoffLabel(campaign)}. You agree the scope, compensation, and next steps.`));
    card.append(creatorAutomationPanel(campaign));
  }
  const countryRule = campaign.country_mode === "strict" ? `Requires declared ${campaign.target_country}` : campaign.country_mode === "prefer" ? `Prefers ${campaign.target_country}` : "Any country";
  const languageRule = campaign.language_mode === "strict" ? `requires published ${campaign.target_language}` : campaign.language_mode === "prefer" ? `prefers ${campaign.target_language}` : "any published language";
  card.append(node("p", "fine-print", `${countryRule} · ${languageRule}`));
  if (campaign.last_discovery_summary && Number.isFinite(campaign.last_discovery_summary.reviewed)) {
    const summary = campaign.last_discovery_summary;
    card.append(node("p", "fine-print", `Last selection: ${summary.reviewed} reviewed · ${summary.selected || 0} selected · ${summary.excluded || 0} excluded by targeting`));
    const coverage = node("details", "discovery-coverage");
    coverage.append(node("summary", "", "Last discovery coverage"));
    const lines = node("dl", "coverage-facts");
    const facts = [
      ["Search pages fetched", summary.search_pages], ["Search results examined", summary.search_results],
      ["Repeated channels removed", summary.duplicate_channels], ["Queries with more pages available", summary.queries_page_limited],
      ["Excluded: country unknown", summary.excluded_country_unknown], ["Excluded: other declared country", summary.excluded_country_mismatch],
      ["Excluded: language unknown", summary.excluded_language_unknown], ["Excluded: other published language", summary.excluded_language_mismatch],
      ["Optional enrichment failures", summary.enrichment_failures],
    ];
    facts.filter(([, value]) => Number.isFinite(value)).forEach(([label, value]) => {
      const pair = node("div");
      pair.append(node("dt", "", label), node("dd", "", Number(value).toLocaleString()));
      lines.append(pair);
    });
    coverage.append(lines, node("p", "fine-print", "A bounded search sample, not a count of every matching channel on YouTube. Country declarations do not establish nationality or viewer location."));
    if (summary.search_budget_exhausted || summary.quota_exhausted || summary.rate_limited) coverage.append(node("p", "notice", "A discovery budget or provider limit stopped this run. Its coverage is partial."));
    if (summary.search_failures || summary.pagination_errors) coverage.append(node("p", "notice", "Some search pages could not be read. Inspect the task history before relying on this run's coverage."));
    card.append(coverage);
  }

  const learning = node("div", "campaign-learning");
  learning.append(node("strong", "", "Agent suggestions"));
  if (!result.suggestions.length) learning.append(node("p", "", "No change suggested yet. Keep recording real replies and conversions."));
  result.suggestions.slice(0, 3).forEach((suggestion) => {
    const item = node("div", `learning-item ${suggestion.priority}`);
    item.append(node("span", "", titleCase(suggestion.priority)), node("strong", "", suggestion.message), node("small", "", suggestion.evidence));
    learning.append(item);
  });
  card.append(learning);
  if (campaign.outreach_mode === "paid" && result.learning?.samples) {
    const report = result.learning;
    const feedback = node("details", "campaign-learning");
    feedback.append(node("summary", "", `What creators are teaching us · ${report.samples.tagged_creators} with reviewed feedback`));
    feedback.append(node("p", "", report.reason));
    if (!campaign.adaptive_mode) feedback.append(node("p", "notice", "Adaptive copy is disabled. Insights remain visible; new drafts use balanced assignment."));
    report.recommendations.forEach((recommendation) => {
      const item = node("div", "learning-item creator-learning-item");
      item.append(node("strong", "", `${titleCase(recommendation.tag)} · ${recommendation.creators} creator${recommendation.creators === 1 ? "" : "s"}`), node("p", "", recommendation.message), node("small", "", recommendation.enough_evidence ? "Repeated feedback; test this change." : "Early observation; too few creators to adapt on this tag alone."));
      feedback.append(item);
    });
    if (!report.recommendations.length) feedback.append(node("p", "fine-print", "Record objections from actual replies. Silence does not tell us why a creator declined."));
    report.variants.forEach((variant) => feedback.append(node("p", "fine-print", `${titleCase(variant.variant)}: ${variant.sent} introductions · ${variant.positive} interested creators`)));
    feedback.append(node("p", "fine-print", report.caveat));
    card.append(feedback);
  }
  const actions = node("div", "card-actions");
  actions.append(
    button("Find Minecraft creators", "button", "scan-campaign", campaign.id),
    button("Promotion kit", "button secondary", "promotion-kit", campaign.id),
    button("Edit campaign", "text-button", "edit-campaign", campaign.id),
    button("Export full campaign CSV", "text-button", "export-campaign", campaign.id),
  );
  card.append(actions, node("p", "fine-print", `${campaign.active ? "Discovery scheduled" : "Discovery paused"} · last: ${formatDate(campaign.last_scan_at)} · next: ${formatDate(campaign.next_scan_at)}`));
  if (campaign.outreach_mode === "paid") card.append(creatorPilotPanel(campaign));
  return card;
}

function renderCampaigns() {
  const list = $("#campaign-list");
  const pilotOpen = new Set($$(".creator-pilot[open]", list).map((panel) => panel.dataset.campaignId));
  list.replaceChildren();
  if (!state.campaigns.length) {
    list.append(empty("Start your first paid creator campaign", "Add a truthful product brief and your email or Discord. Then research Minecraft creators and review their public business contacts.", true));
    return;
  }
  state.campaigns.forEach((campaign) => list.append(campaignCard(campaign)));
  $$(".creator-pilot", list).forEach((panel) => { panel.open = pilotOpen.has(panel.dataset.campaignId); });
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

async function loadCreatorCoverage() {
  const campaignId = $("#marketing-campaign-filter").value;
  const version = ++coverageRequestVersion;
  if (!campaignId || !isConnected()) {
    state.creatorCoverage = null;
    renderCreatorCoverage();
    return;
  }
  if (state.creatorCoverage?.campaignId !== campaignId) state.creatorCoverage = { campaignId, loading: true };
  renderCreatorCoverage();
  try {
    const data = await api(`/v1/marketing/campaigns/${encodeURIComponent(campaignId)}/prospects/coverage`);
    if (version !== coverageRequestVersion || !isConnected()) return;
    state.creatorCoverage = { campaignId, data };
  } catch (error) {
    if (version !== coverageRequestVersion) return;
    state.creatorCoverage = { campaignId, error: error.message };
  }
  renderCreatorCoverage();
}

function renderCreatorCoverage() {
  const content = $("#creator-coverage");
  const campaignId = $("#marketing-campaign-filter").value;
  const campaign = state.campaigns.find((item) => item.id === campaignId);
  const exportButton = $("#marketing-export-all");
  exportButton.disabled = !campaign || exportingCampaigns.has(campaignId);
  exportButton.textContent = exportingCampaigns.has(campaignId) ? "Preparing full CSV…" : "Export full campaign CSV";
  content.replaceChildren();
  if (!campaign) {
    content.append(node("p", "", "Select a campaign to see its complete saved coverage and export every YouTube creator matching its current target."));
    return;
  }
  const coverage = state.creatorCoverage;
  content.append(node("strong", "", `${campaign.name} · complete saved coverage`));
  if (coverage?.campaignId !== campaignId || coverage.loading) content.append(node("p", "", "Loading campaign totals…"));
  else if (coverage.error) content.append(node("p", "notice", `Coverage could not be loaded: ${coverage.error}. Use Refresh to try again.`));
  else {
    const data = coverage.data;
    const facts = node("dl", "coverage-facts");
    [["Saved YouTube creators", data.total], ["Match current target", data.eligible], ["With public contact", data.with_public_contact], ["No public contact", data.without_public_contact], ["Authorized contacts", data.authorized], ["Suppressed contacts", data.suppressed], ["Need research refresh", data.needs_refresh], ["Outside target", data.excluded], ["Country unknown, all saved", data.country_unknown]].forEach(([label, value]) => {
      const pair = node("div");
      pair.append(node("dt", "", label), node("dd", "", Number(value || 0).toLocaleString()));
      facts.append(pair);
    });
    content.append(facts);
    if (data.with_historical_contact) content.append(node("p", "fine-print", `${data.with_historical_contact} creators also have earlier source observations; ${data.historical_contact_only || 0} have historical contacts only. These need a fresh source check and are separate from current contact totals.`));
  }
  content.append(node("p", "fine-print", "Contact and refresh totals cover current-target matches. Full CSV includes matches with and without contacts, plus review and suppression status. The filters below apply only to the loaded view."));
}

async function loadMoreProspects() {
  if (loadingMoreProspects || !isConnected()) return;
  const version = prospectRequestVersion;
  const offset = state.prospectOffset;
  loadingMoreProspects = true;
  renderProspects();
  try {
    const page = await api(`/v1/marketing/prospects?limit=250&offset=${offset}`, {}, "page");
    if (version !== prospectRequestVersion || !isConnected()) return;
    const merged = new Map(state.prospects.map((item) => [item.id, item]));
    page.rows.forEach((item) => merged.set(item.id, item));
    state.prospects = [...merged.values()];
    state.prospectOffset = offset + page.rows.length;
    state.prospectTotal = page.total;
    state.prospectLoadNotice = page.rows.length ? "Loaded view expanded. Automatic refresh returns to the first 250 records; full campaign CSV always includes every current match." : "No further records were returned. Refresh if discovery is still running.";
  } catch (error) { toast(`Could not load more creators: ${error.message}`, true); }
  finally { loadingMoreProspects = false; renderProspects(); }
}

async function exportCampaignProspects(campaignId) {
  const campaign = state.campaigns.find((item) => item.id === campaignId);
  if (!campaign || exportingCampaigns.has(campaignId)) return;
  exportingCampaigns.add(campaignId);
  renderCreatorCoverage();
  try {
    const content = await api(`/v1/marketing/campaigns/${encodeURIComponent(campaignId)}/prospects/export.csv`, {}, "blob");
    downloadCreatorCsv(content, `youtube-${campaign.name.replace(/[^a-z0-9_-]+/gi, "-").slice(0, 70)}-full-${new Date().toISOString().slice(0, 10)}.csv`);
    toast("Full campaign CSV downloaded: every current-target YouTube match, including creators without a public contact");
  } catch (error) { toast(`Could not export campaign: ${error.message}`, true); }
  finally { exportingCampaigns.delete(campaignId); renderCreatorCoverage(); }
}

function currentCreatorTarget(prospect) {
  const campaign = state.campaigns.find((item) => item.id === prospect.campaign_id);
  const geography = prospect.intelligence?.geography || {};
  const language = String(geography.language_code || "").toLowerCase();
  const targetLanguage = String(campaign?.target_language || "").toLowerCase();
  const countryMatches = Boolean(campaign?.target_country && geography.country_code === campaign.target_country);
  const languageMatches = Boolean(language && targetLanguage && (language === targetLanguage || language.startsWith(`${targetLanguage}-`)));
  return {
    eligible: Boolean(campaign) && (campaign.country_mode !== "strict" || countryMatches) && (campaign.language_mode !== "strict" || languageMatches),
    preference: Number(campaign?.country_mode === "prefer" && countryMatches) + Number(campaign?.language_mode === "prefer" && languageMatches),
  };
}

function creatorQuality(prospect) {
  const intelligence = prospect.intelligence || {};
  const researched = typeof intelligence.researched_at === "string" && /(?:Z|[+-]\d{2}:\d{2})$/i.test(intelligence.researched_at) ? Date.parse(intelligence.researched_at) : NaN;
  const datedVideos = researchItems(intelligence, "recent_videos")
    .filter((video) => !["unverified_reference", "search_result_only"].includes(video.metadata_status))
    .map((video) => Date.parse(video.published_at)).filter((date) => Number.isFinite(date) && date <= Date.now());
  const newestSample = datedVideos.length ? Math.max(...datedVideos) : null;
  const ageDays = newestSample === null ? null : Math.floor((Date.now() - newestSample) / 86400000);
  const incomplete = intelligence.enrichment_status !== "complete";
  const needsRefresh = !Number.isFinite(researched) || researched > Date.now() || Date.now() - researched > 30 * 86400000 || incomplete;
  const contactState = prospect.suppressed_at ? "suppressed" : prospect.contact_authorized_at && prospect.contact_email ? "authorized" : prospectContactCandidates(prospect).length ? "candidate" : "missing";
  return { ageDays, needsRefresh, contactState, incomplete };
}

function setCreatorSegment(segment) {
  $("#marketing-target-filter").value = "eligible";
  $("#marketing-contact-filter").value = segment === "contacts" ? "candidate" : segment === "missing" ? "missing" : "";
  $("#marketing-evidence-filter").value = segment === "refresh" ? "refresh" : "";
  $("#marketing-status-filter").value = "";
  $("#marketing-fit-filter").value = "";
  $("#marketing-activity-filter").value = "";
  $("#marketing-platform-filter").value = "youtube";
  $("#marketing-search").value = "";
  renderProspects();
}

function filteredProspects() {
  const campaignId = $("#marketing-campaign-filter").value;
  const status = $("#marketing-status-filter").value;
  const platform = $("#marketing-platform-filter").value;
  const contact = $("#marketing-contact-filter").value;
  const target = $("#marketing-target-filter").value;
  const minFit = Number($("#marketing-fit-filter").value || 0);
  const activity = $("#marketing-activity-filter").value;
  const evidence = $("#marketing-evidence-filter").value;
  const terms = $("#marketing-search").value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const prospects = state.prospects.filter((item) => {
    if ((campaignId && item.campaign_id !== campaignId) || (status && item.status !== status) || (platform && item.platform !== platform)) return false;
    const geography = item.intelligence?.geography || {};
    const currentTarget = currentCreatorTarget(item);
    if (target === "eligible" && !currentTarget.eligible) return false;
    if (target === "poland" && geography.country_code !== "PL") return false;
    if (target === "unknown" && geography.country_code) return false;
    if (target === "excluded" && currentTarget.eligible) return false;
    const candidates = prospectContactCandidates(item);
    const quality = creatorQuality(item);
    const authorized = Boolean(item.contact_authorized_at && !item.suppressed_at);
    if (contact === "candidate" && (!candidates.length || authorized || item.suppressed_at)) return false;
    if (contact === "authorized" && !authorized) return false;
    if (contact === "missing" && quality.contactState !== "missing") return false;
    if (contact === "history" && !researchItems(item.intelligence, "contact_history").length) return false;
    const intelligence = item.intelligence || {};
    if (Number(item.relevance_score || 0) < minFit) return false;
    if (activity === "unknown" && quality.ageDays !== null) return false;
    if (activity && activity !== "unknown" && (quality.ageDays === null || quality.ageDays > Number(activity))) return false;
    if (evidence === "refresh" && !quality.needsRefresh) return false;
    if (evidence === "partial" && !quality.incomplete) return false;
    if (evidence === "high" && intelligence.confidence !== "high") return false;
    const searchable = [item.display_name, item.contact_email, item.profile_url, item.latest_content_title, intelligence.channel_summary,
      geography.country_code, geography.language_code, intelligence.personalized_hook,
      ...researchItems(intelligence, "topics"), ...candidates.map((candidate) => candidate.email),
      ...researchItems(intelligence, "recent_videos").map((video) => video.title),
      ...researchItems(intelligence, "collaboration_ideas").map((idea) => `${idea.title} ${idea.concept}`)].join(" ").toLocaleLowerCase();
    return terms.every((term) => searchable.includes(term));
  });
  const sort = $("#marketing-sort").value;
  return prospects.sort((left, right) => {
    let order = 0;
    if (sort === "name") order = left.display_name.localeCompare(right.display_name);
    if (sort === "audience") order = Number(right.audience_size || 0) - Number(left.audience_size || 0);
    if (sort === "recent") order = (Date.parse(right.intelligence?.researched_at) || 0) - (Date.parse(left.intelligence?.researched_at) || 0);
    if (sort === "contact") order = Number(hasUnreviewedContact(right)) - Number(hasUnreviewedContact(left));
    if (sort === "fit") order = currentCreatorTarget(right).preference - currentCreatorTarget(left).preference;
    return order || Number(right.relevance_score || 0) - Number(left.relevance_score || 0) || left.display_name.localeCompare(right.display_name);
  });
}

function researchItems(intelligence, key) {
  return Array.isArray(intelligence?.[key]) ? intelligence[key].filter((item) => item !== null && item !== undefined) : [];
}

function prospectContactCandidates(prospect) {
  const candidates = researchItems(prospect.intelligence, "contact_candidates").map((candidate) => ({ ...candidate, origin: "discovered" }));
  if (!prospect.contact_authorized_at && prospect.contact_email && prospect.contact_source_url) {
    candidates.push({
      email: prospect.contact_email,
      source_url: prospect.contact_source_url,
      evidence: prospect.contact_basis_note || "",
      observed_at: null,
      status: "unreviewed",
      origin: "recorded",
    });
  }
  const seen = new Set();
  return candidates.filter((candidate) => {
    const email = typeof candidate.email === "string" ? candidate.email.trim().toLowerCase() : "";
    if (!email || seen.has(email)) return false;
    seen.add(email);
    return true;
  });
}

function hasUnreviewedContact(prospect) {
  return !prospect.suppressed_at && !prospect.contact_authorized_at && prospectContactCandidates(prospect).length > 0;
}

function researchDate(value) {
  return value && Number.isFinite(Date.parse(value)) ? formatDate(value) : "Not recorded";
}

function researchLink(label, value) {
  const link = node("a", "text-button", label);
  try {
    if (typeof value !== "string" || !/^https:\/\//i.test(value)) throw new Error("Missing public source");
    const parsed = new URL(value);
    if (parsed.username || parsed.password) throw new Error("Embedded credentials rejected");
    link.href = safeExternalUrl(value);
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  } catch (_error) {
    link.textContent = `${label} unavailable`;
    link.className = "fine-print";
  }
  return link;
}

function creatorResearchPending(prospectId) {
  return state.tasks.some((task) => task.kind === "marketing.creator_discovery"
    && task.payload?.prospect_id === prospectId
    && ["pending_approval", "queued", "running"].includes(task.status));
}

function researchButton(prospect, label) {
  const pending = creatorResearchPending(prospect.id) || researchingProspects.has(prospect.id);
  const control = button(pending ? "Research in progress…" : label, "button compact", "research-prospect", prospect.id);
  control.disabled = pending;
  return control;
}

function prospectResearch(prospect) {
  const intelligence = prospect.intelligence || {};
  const candidates = prospectContactCandidates(prospect);
  const details = node("details", "creator-dossier");
  details.dataset.prospectId = prospect.id;
  details.append(node("summary", "", "Research dossier · evidence and ideas"));
  const body = node("div", "dossier-body");
  if (!intelligence.researched_at && !candidates.length) {
    body.append(node("p", "", "This creator has no research dossier yet. Run research to look for published business contacts, recent content, audience fit, and collaboration ideas."));
    if (prospect.platform === "youtube" && !prospect.suppressed_at) body.append(researchButton(prospect, "Research this creator"));
    details.append(body);
    return details;
  }
  body.append(node("p", "fine-print", `Researched ${researchDate(intelligence.researched_at)} · ${titleCase(intelligence.confidence || "unknown")} evidence confidence · ${titleCase(intelligence.enrichment_status || "partial")} research`));
  if (intelligence.channel_summary) body.append(node("p", "", intelligence.channel_summary));
  if (intelligence.geography) {
    const geography = intelligence.geography;
    const selection = node("section", "dossier-section");
    selection.append(node("h4", "", "Country and language evidence"), node("p", "", `At research time: ${geography.selection_reason || "No selection reason recorded."}`));
    selection.append(node("p", "", geography.country_code ? `Channel declares ${geography.country_code}. This is not audience geography or nationality.` : "Channel country not declared; no country inferred."));
    if (geography.country_source_url) selection.append(researchLink("Country source", geography.country_source_url));
    selection.append(node("p", "", geography.language_code ? `Published language: ${geography.language_code} · ${titleCase(geography.language_source)}` : "Published language unavailable; no language inferred from the channel name."));
    if (geography.language_source_url) selection.append(researchLink("Language source", geography.language_source_url));
    body.append(selection);
  }
  const topics = researchItems(intelligence, "topics");
  if (topics.length) {
    const list = node("div", "opportunity-meta");
    topics.slice(0, 8).forEach((topic) => list.append(node("span", "chip", topic)));
    body.append(list);
  }

  const contacts = node("section", "dossier-section");
  contacts.append(node("h4", "", "Published business contacts"));
  if (!candidates.length) contacts.append(node("p", "", "No public business email found in the checked sources. This does not mean the creator has no contact route."));
  candidates.forEach((candidate, index) => {
    const item = node("div", "dossier-contact");
    item.append(node("strong", "", candidate.email || "Address unavailable"), node("span", "chip status-chip", `${titleCase(candidate.origin)} · unreviewed`));
    if (candidate.evidence) item.append(candidate.origin === "recorded"
      ? node("p", "fine-print", `Recorded note (source not re-observed): ${candidate.evidence}`)
      : node("blockquote", "source-excerpt", candidate.evidence));
    const actions = node("div", "dossier-source-actions");
    actions.append(researchLink("Open published source", candidate.source_url), node("small", "fine-print", `Observed ${researchDate(candidate.observed_at)}`));
    if (!prospect.suppressed_at) {
      const review = button("Review this contact", "button compact", "review-candidate", prospect.id);
      review.dataset.candidateIndex = String(index);
      actions.append(review);
    }
    item.append(actions);
    contacts.append(item);
  });
  body.append(contacts);

  const history = researchItems(intelligence, "contact_history");
  if (history.length) {
    const archive = node("section", "dossier-section");
    archive.append(node("h4", "", "Earlier contact observations"), node("p", "fine-print", "These source observations came from earlier research. The current samples do not reverify them. Recheck the source before contact review; earlier evidence does not authorize outreach."));
    history.slice(0, 20).forEach((candidate) => {
      const item = node("div", "dossier-contact");
      item.append(node("strong", "", candidate.email || "Address unavailable"), node("span", "chip", "Historical · unreviewed"));
      if (candidate.evidence) item.append(node("blockquote", "source-excerpt", candidate.evidence));
      item.append(researchLink("Recheck original source", candidate.source_url), node("p", "fine-print", `First observed ${researchDate(candidate.observed_at)} · last observed ${researchDate(candidate.last_seen_at)}`));
      archive.append(item);
    });
    body.append(archive);
  }

  const fit = researchItems(intelligence, "fit_breakdown");
  if (fit.length) {
    const section = node("section", "dossier-section");
    section.append(node("h4", "", "Why this creator fits"));
    const list = node("dl", "fit-breakdown");
    fit.forEach((criterion) => {
      const row = node("div");
      row.append(node("dt", "", `${titleCase(criterion.criterion)} · ${criterion.points}/${criterion.max_points}`), node("dd", "", criterion.evidence || "No supporting evidence recorded."));
      list.append(row);
    });
    section.append(list);
    body.append(section);
  }

  const videos = researchItems(intelligence, "recent_videos");
  if (videos.length) {
    const section = node("section", "dossier-section");
    section.append(node("h4", "", "Recent content evidence"));
    videos.slice(0, 5).forEach((video) => {
      const item = node("div", "dossier-video");
      item.append(researchLink(video.title || "Open video", video.url));
      const counts = [["views", video.view_count], ["likes", video.like_count], ["comments", video.comment_count]]
        .filter(([, count]) => typeof count === "number" && Number.isFinite(count))
        .map(([label, count]) => `${count.toLocaleString()} ${label}`);
      item.append(node("p", "fine-print", [researchDate(video.published_at), ...counts].join(" · ")));
      section.append(item);
    });
    body.append(section);
  }

  const ideas = researchItems(intelligence, "collaboration_ideas");
  if (ideas.length || intelligence.personalized_hook) {
    const section = node("section", "dossier-section");
    section.append(node("h4", "", "Collaboration ideas to develop"), node("p", "fine-print", "Draft suggestions based on available evidence. Confirm product availability, creator interest, and any offer before using them."));
    ideas.slice(0, 4).forEach((idea) => {
      const item = node("div", "dossier-idea");
      item.append(node("strong", "", idea.title), node("p", "", idea.concept), node("p", "fine-print", `Why it fits: ${idea.why_fit}`));
      section.append(item);
    });
    if (intelligence.personalized_hook) {
      section.append(node("h4", "", "Suggested opening"), node("blockquote", "source-excerpt", intelligence.personalized_hook));
      const copy = button("Copy suggested opening", "text-button", "copy-creator-hook", prospect.id);
      section.append(copy);
    }
    body.append(section);
  }
  const gaps = researchItems(intelligence, "gaps");
  if (gaps.length) {
    const section = node("section", "dossier-section research-gaps");
    section.append(node("h4", "", "What still needs checking"));
    const list = node("ul");
    gaps.forEach((gap) => list.append(node("li", "", gap)));
    section.append(list);
    body.append(section);
  }
  if (prospect.platform === "youtube" && !prospect.suppressed_at) body.append(researchButton(prospect, "Refresh research"));
  details.append(body);
  return details;
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
  const score = node("div", "creator-fit", String(prospect.relevance_score));
  score.append(node("small", "", "fit / 100"));
  top.append(copy, score);
  card.append(top);
  const meta = node("div", "opportunity-meta");
  meta.append(node("span", "chip status-chip", titleCase(prospect.status)));
  const candidates = prospectContactCandidates(prospect);
  const quality = creatorQuality(prospect);
  meta.append(node("span", "chip", prospect.suppressed_at ? "Contact suppressed" : prospect.contact_authorized_at ? "Authorized contact" : candidates.length ? `${candidates.length} published contact${candidates.length === 1 ? "" : "s"} to review` : "No public contact found"));
  if (prospect.intelligence?.confidence) meta.append(node("span", "chip", `${titleCase(prospect.intelligence.confidence)} evidence confidence`));
  const geography = prospect.intelligence?.geography;
  meta.append(node("span", "chip", geography?.country_code ? `Channel declares ${geography.country_code}` : "Country not declared"));
  if (!currentCreatorTarget(prospect).eligible) meta.append(node("span", "chip status-chip", "Outside current target · saved history"));
  if (prospect.latest_message) meta.append(node("span", "chip", `${titleCase(prospect.latest_message.stage)} · ${emailActionState(prospect.latest_message.action_status)[0]}`));
  card.append(meta);
  const readiness = node("div", "creator-readiness");
  const nextStep = quality.contactState === "suppressed" ? "Outreach blocked" : !currentCreatorTarget(prospect).eligible ? "Review target mismatch" : quality.contactState === "candidate" ? "Review public contact evidence" : quality.needsRefresh || quality.incomplete ? "Refresh missing or older research" : quality.contactState === "authorized" ? "Contact reviewed · inspect outreach status" : "Research available · public contact missing";
  readiness.append(node("strong", "", nextStep), node("span", "", `${quality.ageDays === null ? "No dated video sample" : `Newest dated sample published ${quality.ageDays} days ago`} · ${quality.needsRefresh ? "Research incomplete, missing, or over 30 days old" : `Researched ${researchDate(prospect.intelligence?.researched_at)}`}`));
  card.append(readiness);
  if (prospect.latest_content_title) {
    const content = node("p", "prospect-evidence", `Content sample: ${prospect.latest_content_title}`);
    card.append(content);
  }
  const reasons = node("ul", "reason-list");
  (prospect.relevance_reasons || []).slice(0, 3).forEach((reason) => reasons.append(node("li", "", reason)));
  card.append(reasons);
  if (hasUnreviewedContact(prospect)) card.append(node("p", "candidate-preview", `Published contact: ${candidates[0].email} · ${candidates[0].origin}, unreviewed`));
  card.append(prospectResearch(prospect));
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
  if (!prospect.suppressed_at) actions.append(button(prospect.contact_authorized_at ? "Edit evidence" : candidates.length ? "Review contact" : "Add contact evidence", "button", "edit-prospect", prospect.id));
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
  if (prospect.status === "declined_unpaid" && campaign?.outreach_mode !== "paid") {
    const paidExists = prospect.latest_message?.stage === "paid_offer" && ["pending_approval", "queued", "executing", "succeeded", "ambiguous"].includes(prospect.latest_message.action_status);
    if (!paidExists) actions.append(button("Prepare final paid option", "button primary", "plan-marketing-paid", prospect.id));
  }
  if (canPrepareCreatorHandoff(prospect)) actions.append(button("Prepare owner handoff", "button primary", "plan-marketing-handoff", prospect.id));
  if (prospect.status === "handed_off") card.append(node("p", "notice", "Handed over to the owner. Hermes has stopped this conversation."));
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
  const expanded = new Set($$(".creator-dossier[open]", list).map((item) => item.dataset.prospectId));
  list.replaceChildren();
  const prospects = filteredProspects();
  const unreviewed = prospects.filter(hasUnreviewedContact).length;
  $("#marketing-prospect-count").textContent = `${prospects.length} matching loaded creator${prospects.length === 1 ? "" : "s"} · ${unreviewed} public contacts to review`;
  $("#marketing-load-count").textContent = `${state.prospects.length.toLocaleString()} of ${state.prospectTotal === null ? "an unknown number of" : state.prospectTotal.toLocaleString()} saved records loaded across campaigns. Search and segments apply to these records.`;
  $("#marketing-load-notice").textContent = state.prospectLoadNotice;
  $("#marketing-load-notice").hidden = !state.prospectLoadNotice;
  const loadMore = $("#marketing-load-more");
  loadMore.hidden = state.prospectTotal !== null && state.prospectOffset >= state.prospectTotal;
  loadMore.disabled = !isConnected() || loadingMoreProspects;
  loadMore.textContent = loadingMoreProspects ? "Loading creators…" : "Load next 250 creators";
  $("#marketing-export").disabled = !prospects.length;
  if (!prospects.length) {
    list.append(empty("No loaded creators match these filters", state.prospectTotal > state.prospectOffset ? "Load more records, clear the filters, or export the full campaign. Additional saved creators have not been loaded yet." : "Clear the filters, refresh research, or run discovery with your country rules. All saved history also includes excluded creators.", true));
    return;
  }
  prospects.forEach((prospect) => list.append(prospectCard(prospect)));
  $$(".creator-dossier", list).forEach((item) => { item.open = expanded.has(item.dataset.prospectId); });
}

function exportProspects() {
  const prospects = filteredProspects();
  if (!prospects.length) return toast("No creators in this view to export", true);
  const rows = [["Creator", "Platform", "Profile URL", "Fit score", "Audience", "Declared country", "Published language", "Matches current target", "Research confidence", "Research date", "Authorized business email", "Authorized contact source", "Published unreviewed emails", "Unreviewed contact origins", "Contact evidence sources", "Recent video", "Collaboration ideas", "Suggested opening", "Research gaps", "Outreach status", "Historical contacts (recheck)", "Historical source evidence and dates"]];
  prospects.forEach((prospect) => {
    const intelligence = prospect.intelligence || {};
    const candidates = prospectContactCandidates(prospect);
    const authorized = Boolean(prospect.contact_authorized_at && !prospect.suppressed_at);
    rows.push([prospect.display_name, prospect.platform, prospect.profile_url, prospect.relevance_score, prospect.audience_size,
      intelligence.geography?.country_code || "unknown", intelligence.geography?.language_code || "unknown", currentCreatorTarget(prospect).eligible,
      intelligence.confidence, intelligence.researched_at, authorized ? prospect.contact_email : "", authorized ? prospect.contact_source_url : "",
      candidates.map((item) => item.email).join("; "), candidates.map((item) => item.origin).join("; "), candidates.map((item) => item.source_url).join("; "), prospect.latest_content_url,
      researchItems(intelligence, "collaboration_ideas").map((item) => `${item.title}: ${item.concept}`).join(" | "), intelligence.personalized_hook,
      researchItems(intelligence, "gaps").join(" | "), prospect.status,
      researchItems(intelligence, "contact_history").map((item) => item.email).join("; "),
      JSON.stringify(researchItems(intelligence, "contact_history"))]);
  });
  const encodeCell = (value) => {
    let text = String(value ?? "");
    // Spreadsheet importers can evaluate quoted cells; neutralize formula prefixes too.
    if (/^[\s\u0000-\u001f\u007f\uFEFF]*[=+\-@]/u.test(text) || /^[\u0000-\u001f\u007f]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  };
  const content = "\uFEFF" + rows.map((row) => row.map(encodeCell).join(",")).join("\r\n");
  downloadCreatorCsv(new Blob([content], { type: "text/csv;charset=utf-8" }), `youtube-loaded-view-${new Date().toISOString().slice(0, 10)}.csv`);
  toast(`Exported ${prospects.length} loaded creators with research and contact-review status`);
}

function downloadCreatorCsv(content, filename) {
  const url = URL.createObjectURL(content);
  const link = node("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
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
  renderCreatorCoverage();
  renderCreatorWork();
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
  ["#marketing-outcome-form", "#creator-mail-review-form"].forEach((selector) => addFeedbackFields($(selector)));
  $("#career-event-form").elements.status.append(new Option("Needs further review", "needs_review"));
  progressiveForm($("#profile-form"), [
    { title: "Match preferences", description: "Freshness, fit, and employment type", fields: ["required_keywords", "excluded_keywords", "max_age_hours", "min_score", "employment_types"] },
    { title: "Search sources", description: "Public feeds and employer boards", fields: ["arbeitnow"] },
    { title: "Application details", description: "Identity for form preparation", fields: ["first_name"] },
    { title: "Schedule and automatic preparation", description: "Choose when work may run", fields: ["schedule_minutes", "active", "auto_prepare"] },
  ]);
  $("#profile-form").elements.resume_text.rows = 5;
  progressiveForm($("#campaign-form"), [
    { title: "Offers and audience", description: "Check the claims each draft may use", fields: ["target_audience", "viewer_offer", "creator_offer", "paid_offer_enabled", "paid_offer_details"] },
    { title: "Creator discovery", description: "Country rules, published language, audience size, and search coverage", fields: ["targeting_preset", "discovery_queries", "relevance_language", "region_code", "min_subscribers", "max_subscribers", "max_video_age_days", "results_per_query", "search_pages_per_query"] },
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
  careerSourceRequest += 1;
  $("#career-source-resolve").disabled = false;
  $("#career-source-result").textContent = "";
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
    form.elements.remotive.checked = Boolean(profile.source_config.remotive);
    form.elements.ashby_boards.value = (profile.source_config.ashby_boards || []).join(", ");
    form.elements.greenhouse_boards.value = (profile.source_config.greenhouse_boards || []).join(", ");
    form.elements.lever_boards.value = (profile.source_config.lever_boards || []).join(", ");
    form.elements.lever_eu_boards.value = (profile.source_config.lever_eu_boards || []).join(", ");
    for (const name of ["first_name", "last_name", "email", "phone", "identity_location", "linkedin_url", "github_url", "portfolio_url"]) {
      const identityName = name === "identity_location" ? "location" : name;
      form.elements[name].value = profile.application_identity?.[identityName] || "";
    }
    $$("input[name='employment_types']", form).forEach((input) => { input.checked = profile.employment_types.includes(input.value); });
  }
  $("#profile-dialog").showModal();
}

let careerSourceRequest = 0;
async function resolveCareerSource() {
  const form = $("#profile-form");
  const input = form.elements.career_source_url;
  const result = $("#career-source-result");
  const submit = $("#career-source-resolve");
  const url = input.value.trim();
  if (!url) { result.textContent = "Paste an employer's Ashby, Greenhouse, or Lever URL first."; input.focus(); return; }
  const request = ++careerSourceRequest;
  const profileId = form.elements.profile_id.value;
  submit.disabled = true;
  result.textContent = "Checking the board URL…";
  try {
    const source = await api("/v1/career/sources/resolve", { method: "POST", body: JSON.stringify({ url }) });
    if (request !== careerSourceRequest || !$("#profile-dialog").open || form.elements.profile_id.value !== profileId || input.value.trim() !== url) return;
    const allowedKeys = new Set(["ashby_boards", "greenhouse_boards", "lever_boards", "lever_eu_boards"]);
    if (!allowedKeys.has(source.source_config_key)) throw new Error("The resolved source is not supported by this form.");
    const field = form.elements[source.source_config_key];
    field.value = [...new Set([...csv(field.value), source.board])].join(", ");
    result.textContent = `${titleCase(source.provider)} board added to this form. ${source.notice} Save the mission to enable discovery.`;
  } catch (error) {
    if (request === careerSourceRequest && $("#profile-dialog").open) result.textContent = error.message;
  } finally { if (request === careerSourceRequest) submit.disabled = false; }
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
    portfolio_url: form.elements.portfolio_url.value.trim() || null,
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
    source_config: { arbeitnow: form.elements.arbeitnow.checked, remotive: form.elements.remotive.checked, ashby_boards: csv(form.elements.ashby_boards.value), greenhouse_boards: csv(form.elements.greenhouse_boards.value), lever_boards: csv(form.elements.lever_boards.value), lever_eu_boards: csv(form.elements.lever_eu_boards.value) },
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
  clearFormError(form);
  $("#campaign-dialog-title").textContent = campaign ? "Edit creator campaign" : "Create a creator partnership";
  if (campaign) {
    for (const name of [
      "name", "sender_name", "product_name", "product_url", "privacy_url",
      "product_summary", "target_audience", "viewer_offer", "creator_offer",
      "paid_offer_details", "outreach_mode", "handoff_name", "handoff_email", "handoff_discord",
      "compensation_model", "revenue_share_percent", "revenue_share_weeks", "revenue_share_basis",
      "relevance_language", "region_code", "min_subscribers",
      "max_subscribers", "max_video_age_days", "results_per_query", "schedule_hours",
    ]) form.elements[name].value = campaign[name] ?? "";
    form.elements.discovery_queries.value = campaign.discovery_queries.join(", ");
    form.elements.paid_offer_enabled.checked = campaign.paid_offer_enabled;
    form.elements.adaptive_mode.checked = campaign.adaptive_mode;
    form.elements.active.checked = campaign.active;
    for (const name of ["country_mode", "language_mode"]) form.elements[name].value = campaign[name] || "any";
    form.elements.search_pages_per_query.value = campaign.search_pages_per_query || 1;
    form.elements.target_country.value = campaign.target_country || "";
    form.elements.target_language.value = campaign.target_language || "";
    form.elements.targeting_preset.value = "custom";
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
    outreach_mode: form.elements.outreach_mode.value,
    compensation_model: form.elements.compensation_model.value,
    revenue_share_percent: form.elements.revenue_share_percent.value ? Number(form.elements.revenue_share_percent.value) : null,
    revenue_share_weeks: form.elements.revenue_share_weeks.value ? Number(form.elements.revenue_share_weeks.value) : null,
    revenue_share_basis: form.elements.revenue_share_basis.value.trim() || null,
    handoff_name: form.elements.handoff_name.value.trim() || null,
    handoff_email: form.elements.handoff_email.value.trim() || null,
    handoff_discord: form.elements.handoff_discord.value.trim() || null,
    sender_name: form.elements.sender_name.value.trim(),
    discovery_queries: csv(form.elements.discovery_queries.value),
    relevance_language: form.elements.relevance_language.value.trim(),
    region_code: form.elements.region_code.value.trim().toUpperCase() || null,
    country_mode: form.elements.country_mode.value,
    target_country: form.elements.target_country.value.trim().toUpperCase() || null,
    language_mode: form.elements.language_mode.value,
    target_language: form.elements.target_language.value.trim() || null,
    min_subscribers: Number(form.elements.min_subscribers.value),
    max_subscribers: Number(form.elements.max_subscribers.value),
    max_video_age_days: Number(form.elements.max_video_age_days.value),
    results_per_query: Number(form.elements.results_per_query.value),
    search_pages_per_query: Number(form.elements.search_pages_per_query.value),
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

function openProspectDialog(prospect = null, candidateIndex = null) {
  if (!isConnected()) return $("#connect-dialog").showModal();
  if (!state.campaigns.length) {
    toast("Create a creator campaign first", true);
    return openCampaignDialog();
  }
  const form = $("#prospect-form");
  form.reset();
  clearFormError(form);
  const candidateContext = $("#contact-candidate-context");
  candidateContext.replaceChildren();
  candidateContext.hidden = true;
  form.elements.prospect_id.value = prospect?.id || "";
  populateCampaignSelect(form.elements.campaign_id, prospect?.campaign_id || state.campaigns[0].id);
  form.elements.campaign_id.disabled = Boolean(prospect);
  form.elements.platform.replaceChildren(new Option("YouTube", "youtube"));
  if (prospect && prospect.platform !== "youtube") form.elements.platform.append(new Option(`${titleCase(prospect.platform)} · saved history`, prospect.platform));
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
  if (prospect && candidateIndex === null && hasUnreviewedContact(prospect)) {
    const recordedEmail = (prospect.contact_email || "").trim().toLowerCase();
    const recordedIndex = prospectContactCandidates(prospect).findIndex((candidate) => candidate.email.trim().toLowerCase() === recordedEmail);
    candidateIndex = Math.max(0, recordedIndex);
  }
  if (prospect && candidateIndex !== null) {
    const candidate = prospectContactCandidates(prospect)[candidateIndex];
    if (candidate) {
      form.elements.contact_email.value = candidate.email || "";
      form.elements.contact_source_url.value = candidate.source_url || "";
      form.elements.contact_basis_note.value = "";
      form.elements.authorize_contact.checked = false;
      candidateContext.hidden = false;
      candidateContext.append(node("strong", "", `${titleCase(candidate.origin)} contact · not authorized`), node("p", "", "Review the creator's published source and write your own basis before authorizing contact."));
      if (candidate.evidence) candidateContext.append(candidate.origin === "recorded"
        ? node("p", "fine-print", `Recorded note (source not re-observed): ${candidate.evidence}`)
        : node("blockquote", "source-excerpt", candidate.evidence));
      candidateContext.append(researchLink("Open published source", candidate.source_url), node("p", "fine-print", `Observed ${researchDate(candidate.observed_at)}`));
    }
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

const researchingProspects = new Set();
async function researchProspect(id) {
  if (researchingProspects.has(id) || creatorResearchPending(id)) return;
  researchingProspects.add(id);
  const controls = $$('[data-action="research-prospect"]').filter((item) => item.dataset.id === id);
  controls.forEach((control) => { control.disabled = true; control.textContent = "Queueing research…"; });
  try {
    await api(`/v1/marketing/prospects/${encodeURIComponent(id)}/research`, { method: "POST" });
    toast("Creator research queued. Evidence will update when the task completes.");
    await loadData({ quiet: true });
  } catch (error) { toast(error.message, true); }
  finally {
    researchingProspects.delete(id);
    controls.forEach((control) => { control.disabled = false; control.textContent = "Refresh research"; });
    renderProspects();
  }
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
  resetCreatorDraftReview();
  const form = $("#marketing-reply-form");
  form.reset();
  clearFormError(form);
  const initial = stage === "initial";
  const campaign = state.campaigns.find((item) => item.id === prospect.campaign_id);
  form.elements.prospect_id.value = prospect.id;
  form.elements.stage.value = stage;
  form.elements.subject.value = initial ? "" : `Re: ${prospect.display_name} × KarixMC`;
  form.elements.draft_method.value = initial ? "template" : "manual";
  $('option[value="ai"]', form.elements.draft_method).disabled = campaign?.outreach_mode !== "paid";
  $("#marketing-message-title").textContent = initial ? `Introduce your campaign to ${prospect.display_name}` : "Answer the creator's question";
  $("#marketing-message-guidance").textContent = initial ? "Choose a template, request an AI draft, or write your own. Each route prepares one exact email for review before sending. Creator interest is never guaranteed." : "Answer only what you know. The exact message will wait for approval.";
  updateMarketingDraftMode();
  $("#marketing-reply-dialog").showModal();
}

let creatorDraftRecord = null;
let creatorDraftVersion = 0;
let creatorDraftTimer = null;
let creatorDraftLoading = false;
let creatorDraftError = "";
let creatorDraftLoaded = false;
const creatorDraftRequestKeys = new Map();

function resetCreatorDraftReview() {
  creatorDraftVersion += 1;
  clearTimeout(creatorDraftTimer);
  creatorDraftTimer = null;
  creatorDraftRecord = null;
  creatorDraftLoading = false;
  creatorDraftError = "";
  creatorDraftLoaded = false;
}

function creatorDraftIsCurrent(version, prospectId) {
  return version === creatorDraftVersion && $("#marketing-reply-dialog").open
    && $("#marketing-reply-form").elements.prospect_id.value === prospectId && isConnected();
}

function creatorDraftCanPrepare() {
  return creatorDraftRecord?.status === "ready" && Boolean(creatorDraftRecord.draft_digest)
    && Date.parse(creatorDraftRecord.expires_at) > Date.now() && !creatorDraftLoading && !creatorDraftError;
}

function updateMarketingDraftMode() {
  const form = $("#marketing-reply-form");
  const initial = form.elements.stage.value === "initial";
  const method = initial ? form.elements.draft_method.value : "manual";
  const manual = method === "manual";
  $("#marketing-draft-method-field").hidden = !initial;
  $("#creator-ai-draft").hidden = method !== "ai";
  $("#marketing-message-fields").hidden = !manual;
  $("#marketing-message-fields").open = manual;
  $("#marketing-message-fields summary").hidden = true;
  $("#marketing-message-custom-help").hidden = !initial;
  form.elements.subject.required = manual;
  form.elements.body.required = manual;
  const submit = $('button[type="submit"]', form);
  if (form.dataset.busy !== "true") {
    submit.textContent = !initial ? "Prepare exact answer" : method === "ai" ? "Prepare exact AI email" : manual ? "Prepare my introduction" : "Prepare campaign template";
    submit.disabled = method === "ai" && !creatorDraftCanPrepare();
  }
  if (method === "ai") renderCreatorDraftReview();
}

function renderCreatorDraftReview() {
  const status = $("#creator-ai-status");
  const review = $("#creator-ai-review");
  const draft = creatorDraftRecord;
  status.replaceChildren();
  review.replaceChildren();
  const pending = draft?.status === "queued";
  const expired = draft?.status === "ready" && !(Date.parse(draft.expires_at) > Date.now());
  const headline = creatorDraftError ? "Draft could not be loaded"
    : creatorDraftLoading ? "Checking the draft…"
    : !draft ? "No AI draft yet"
    : draft.status === "prepared" ? "Exact email prepared"
    : expired || draft.status === "stale" ? "Draft needs refreshing"
    : draft.status === "ready" ? "Ready for your review"
    : pending ? draft.task_status === "running" ? "Writing and checking the introduction…" : "Draft queued"
    : "Draft did not pass";
  status.append(node("strong", "", headline));
  const explanation = creatorDraftError || (!draft ? "Generate an introduction from the recorded evidence. Nothing is sent by drafting."
    : draft.status === "prepared" ? "This draft is already linked to an exact email. Open that message to inspect its approval and delivery status."
    : expired || draft.status === "stale" ? "The draft expired or its campaign/contact context changed. Generate a fresh draft before preparing an email."
    : draft.status === "ready" ? "Read the complete copy and check the sources below. Preparing creates an approval packet; it does not send."
    : pending ? "You can close this dialog and return later. Progress is saved; the draft cannot send an email."
    : `No email was prepared. ${draft.error_code ? `Reason: ${titleCase(draft.error_code)}. ` : ""}Review the research and model setup, then try again or choose the campaign template.`);
  status.append(node("p", "fine-print", explanation));
  const generate = $("#creator-ai-generate");
  generate.disabled = creatorDraftLoading || Boolean(pending);
  generate.textContent = creatorDraftLoading ? "Please wait…" : pending ? "Draft in progress…" : draft ? "Generate a fresh draft" : "Generate personalized draft";
  $("#creator-ai-refresh").disabled = creatorDraftLoading;
  if (!draft) return;
  if (draft.source || draft.selected_model) review.append(node("p", "fine-print", `Written by ${draft.selected_model || "model not recorded"} · ${titleCase(draft.source || "source unavailable")} · ${researchDate(draft.created_at)}`));
  if (draft.subject && draft.body) {
    const copy = node("section", "creator-ai-copy");
    copy.setAttribute("aria-label", "Exact AI draft");
    copy.append(node("strong", "", draft.subject), node("p", "", draft.body));
    review.append(copy);
  }
  if (draft.learning_summary) {
    const learning = draft.learning_summary;
    review.append(node("h3", "", "How reviewed feedback shaped this draft"),
      node("p", "", learning.reason || "No reviewed pattern is available yet."),
      node("p", "fine-print", `${Number(learning.samples?.reviewed_creators || 0)} distinct creators with reviewed outcomes.`));
    if (learning.caveat) review.append(node("p", "fine-print", learning.caveat));
  }
  if (draft.model_copy?.rationale || draft.model_copy?.reach_strategy) {
    review.append(node("h3", "", "Why this approach"));
    if (draft.model_copy.rationale) review.append(node("p", "", draft.model_copy.rationale));
    const reachGuidance = {
      small_pilot: "Observed subscriber count suggests a focused pilot. It does not predict views or determine compensation.",
      format_choice: "Offer room for the creator to choose a suitable format. Subscriber count does not predict views or determine compensation.",
      unknown_reach: "Subscriber evidence is unavailable. The draft must not assume reach or commercial value.",
    };
    if (draft.model_copy.reach_strategy) review.append(node("p", "fine-print", reachGuidance[draft.model_copy.reach_strategy] || titleCase(draft.model_copy.reach_strategy)));
  }
  if (Array.isArray(draft.quality_notes) && draft.quality_notes.length) {
    review.append(node("h3", "", "Checks and review notes"));
    const notes = node("ul", "reason-list");
    draft.quality_notes.forEach((note) => notes.append(node("li", "", note)));
    review.append(notes);
  }
  if (Array.isArray(draft.evidence) && draft.evidence.length) {
    review.append(node("h3", "", "Sources behind the introduction"));
    const sources = node("ul", "creator-ai-sources");
    draft.evidence.forEach((source) => {
      const item = node("li");
      item.append(researchLink(source.title || source.id || "Open source", source.url));
      sources.append(item);
    });
    review.append(sources);
  }
  if (draft.status === "ready" && !expired) review.append(node("p", "fine-print", `Review valid until ${researchDate(draft.expires_at)}. Creator, contact and campaign evidence are checked again when preparing.`));
  if (draft.action_id) review.append(button("Review prepared email", "button", "review-creator-draft-action", draft.action_id));
}

function scheduleCreatorDraftRefresh() {
  clearTimeout(creatorDraftTimer);
  if ($("#marketing-reply-dialog").open && $("#marketing-reply-form").elements.draft_method.value === "ai"
      && creatorDraftRecord?.status === "queued" && !creatorDraftError) {
    creatorDraftTimer = setTimeout(() => loadCreatorDraftReview(), 5000);
  }
}

async function loadCreatorDraftReview() {
  if (creatorDraftLoading || !$("#marketing-reply-dialog").open) return;
  const prospectId = $("#marketing-reply-form").elements.prospect_id.value;
  const version = creatorDraftVersion;
  creatorDraftLoading = true;
  creatorDraftError = "";
  updateMarketingDraftMode();
  try {
    const drafts = await api(`/v1/marketing/prospects/${encodeURIComponent(prospectId)}/drafts`);
    if (!creatorDraftIsCurrent(version, prospectId)) return;
    creatorDraftRecord = drafts[0] || null;
    creatorDraftLoaded = true;
  } catch (error) {
    if (creatorDraftIsCurrent(version, prospectId)) creatorDraftError = error.message;
  } finally {
    if (creatorDraftIsCurrent(version, prospectId)) {
      creatorDraftLoading = false;
      updateMarketingDraftMode();
      scheduleCreatorDraftRefresh();
    }
  }
}

async function generateCreatorDraft() {
  if (creatorDraftLoading) return;
  const form = $("#marketing-reply-form");
  if (!$("#marketing-reply-dialog").open || form.elements.stage.value !== "initial" || form.elements.draft_method.value !== "ai") return;
  const prospectId = form.elements.prospect_id.value;
  const version = creatorDraftVersion;
  clearTimeout(creatorDraftTimer);
  creatorDraftLoading = true;
  creatorDraftError = "";
  if (!creatorDraftRequestKeys.has(prospectId)) creatorDraftRequestKeys.set(prospectId, crypto.randomUUID());
  updateMarketingDraftMode();
  try {
    const draft = await api(`/v1/marketing/prospects/${encodeURIComponent(prospectId)}/drafts`, {
      method: "POST", body: JSON.stringify({ actor: "dashboard:marketing", idempotency_key: creatorDraftRequestKeys.get(prospectId) }),
    });
    creatorDraftRequestKeys.delete(prospectId);
    if (!creatorDraftIsCurrent(version, prospectId)) return;
    creatorDraftRecord = draft;
    creatorDraftLoaded = true;
    toast("AI draft queued. Review the result here before preparing an email.");
  } catch (error) {
    if (creatorDraftIsCurrent(version, prospectId)) creatorDraftError = error.message;
  } finally {
    if (creatorDraftIsCurrent(version, prospectId)) {
      creatorDraftLoading = false;
      updateMarketingDraftMode();
      scheduleCreatorDraftRefresh();
    }
  }
}

async function prepareCreatorDraft() {
  if (!creatorDraftCanPrepare()) throw new Error("Load a current, successfully checked AI draft before preparing it.");
  const draft = creatorDraftRecord;
  const version = creatorDraftVersion;
  const action = await api(`/v1/marketing/drafts/${encodeURIComponent(draft.id)}/prepare`, {
    method: "POST", body: JSON.stringify({ actor: "dashboard:marketing", draft_digest: draft.draft_digest, approval_window_minutes: 1440 }),
  });
  const stillReviewing = creatorDraftIsCurrent(version, draft.prospect_id);
  if (stillReviewing) $("#marketing-reply-dialog").close();
  toast("Exact AI email prepared for approval. Nothing has been sent.");
  await loadData({ quiet: true });
  if (stillReviewing) {
    switchView("approvals");
    if (action.id) await showActionReview(action.id);
  }
}

function openMarketingOutcome(prospect) {
  const form = $("#marketing-outcome-form");
  form.reset();
  form.elements.prospect_id.value = prospect.id;
  if (prospect.status === "interested") form.elements.classification.value = "promotion_published";
  if (prospect.status === "converted") form.elements.classification.value = "converted";
  $("#marketing-outcome-dialog").showModal();
}

function addFeedbackFields(form) {
  const fields = node("fieldset", "creator-feedback-fields");
  fields.append(node("legend", "", "What could the outreach do better?"), node("p", "fine-print", "Optional. Select only objections supported by the creator's reply. These teach future drafts; they never change payment terms."));
  const labels = { too_generic: "Too generic", unclear_offer: "Offer is unclear", unclear_revenue_share: "Revenue share is unclear", prefers_fixed_fee: "Prefers a fixed fee", weak_content_fit: "Poor fit for their content", unclear_attribution: "Attribution is unclear", too_long: "Message is too long", unclear_next_step: "Next step is unclear" };
  for (const [value, text] of Object.entries(labels)) {
    const label = node("label", "checkbox-row");
    const input = document.createElement("input"); input.type = "checkbox"; input.name = "feedback_tag"; input.value = value;
    label.append(input, document.createTextNode(text)); fields.append(label);
  }
  $(".dialog-actions", form).before(fields);
}

function reviewedFeedbackTags(form) {
  return $$('input[name="feedback_tag"]:checked', form).map((input) => input.value);
}

async function saveMarketingOutcome(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.prospect_id.value;
  if (form.elements.classification.value === "interested" && !form.elements.note.value.trim()) {
    throw new Error("Add a brief note confirming the creator's interest before the owner handoff.");
  }
  const payload = {
    classification: form.elements.classification.value,
    note: form.elements.note.value.trim() || null,
    feedback_tags: reviewedFeedbackTags(form),
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
  root.replaceChildren(node("span", "tag", `${titleCase(opportunity.source)} · ${opportunity.score}% fit`), node("h2", "", opportunity.title), node("p", "", `${opportunity.company} · ${opportunity.location || "Location not listed"} · ${opportunityDateLabel(opportunity)}`));
  const reasons = node("ul", "reason-list");
  opportunity.score_reasons.forEach((reason) => reasons.append(node("li", "", reason)));
  root.append(reasons, node("div", "detail-description", opportunity.description || "No description supplied by source."));
  root.append(careerQualityEvidence(opportunity));
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
    const decided = await api(`/v1/tasks/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, actor: "dashboard:approver", reason: "Decision recorded in Hermes Command Center" }) });
    const paced = decision === "approved" && action?.action_type === "communications.email_send" && new Date(decided.next_attempt_at).getTime() > Date.now() + 2000;
    toast(paced ? `This email is approved and paced for ${formatDate(decided.next_attempt_at)}.` : decision === "approved" && action?.action_type === "communications.email_send" ? "This one email is approved and queued. Follow its send history for the result." : `Task ${decision}`);
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
  if (action === "resolve-career-source") return resolveCareerSource();
  if (action === "edit-profile") return openProfileDialog(state.profiles.find((item) => item.id === id));
  if (action === "toggle-profile") return toggleProfile(id);
  if (action === "play-career") return openCareerPlay(id);
  if (action === "pause-career") return pauseCareerRun(id);
  if (action === "sync-career-mail") return syncCareerMail(id);
  if (action === "career-event") return openCareerEvent(id);
  if (action === "review-career-mail") return openCareerEvent(null, Number(id));
  if (action === "career-applications") {
    $("#opportunity-profile-filter").value = id;
    renderOpportunities();
    switchView("opportunities");
    $("#career-pipeline-title").scrollIntoView({ block: "start" });
    return;
  }
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
  if (action === "research-creator-pilot") return researchCreatorPilot(id);
  if (action === "refresh-creator-pilot") return loadCreatorPilots(id);
  if (action === "review-pilot-prospect") return reviewPilotProspect(id, target.dataset.campaignId, target.dataset.prepareDraft === "true");
  if (action === "promotion-kit") return showPromotionKit(id);
  if (action === "new-prospect") return openProspectDialog();
  if (action === "edit-prospect") return openProspectDialog(state.prospects.find((item) => item.id === id));
  if (action === "review-candidate") return openProspectDialog(state.prospects.find((item) => item.id === id), Number(target.dataset.candidateIndex));
  if (action === "research-prospect") return researchProspect(id);
  if (action === "export-prospects") return exportProspects();
  if (action === "export-campaign") return exportCampaignProspects(id);
  if (action === "export-selected-campaign") return exportCampaignProspects($("#marketing-campaign-filter").value);
  if (action === "load-more-prospects") return loadMoreProspects();
  if (action === "creator-segment") return setCreatorSegment(id);
  if (action === "copy-creator-hook") {
    const hook = state.prospects.find((item) => item.id === id)?.intelligence?.personalized_hook;
    if (!hook) return toast("No suggested opening is available", true);
    try { await copyText(hook); toast("Suggested opening copied for your review"); }
    catch (error) { toast(error.message, true); }
    return;
  }
  if (action === "plan-marketing-initial") return openMarketingReply(state.prospects.find((item) => item.id === id), "initial");
  if (action === "generate-creator-draft") return generateCreatorDraft();
  if (action === "refresh-creator-draft") return loadCreatorDraftReview();
  if (action === "review-creator-draft-action") { $("#marketing-reply-dialog").close(); return showActionReview(id); }
  if (action === "plan-marketing-paid") return planMarketingEmail(id, "paid_offer");
  if (action === "plan-marketing-handoff") return planMarketingEmail(id, "handoff");
  if (action === "start-creator-run") return openCreatorRun(id);
  if (action === "pause-creator-run") return creatorRunAction(id, "pause");
  if (action === "sync-creator-replies") return creatorRunAction(id, "sync");
  if (action === "review-creator-mail") return openCreatorMailReview(target.dataset.campaignId, id);
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
$("#career-play-form").addEventListener("submit", async (event) => {
  await guardedSubmit(event, startCareerRun);
  if ($("#career-play-dialog").open) updateCareerPlayScope();
});
$("#career-event-form").addEventListener("submit", (event) => guardedSubmit(event, saveCareerEvent));
$("#career-event-form").elements.opportunity_id.addEventListener("change", updateCareerEventChoices);
$("#career-event-form").elements.status.addEventListener("change", (event) => {
  const meeting = $("#career-event-form").elements.meeting_at;
  meeting.disabled = event.target.value !== "interview";
  if (meeting.disabled) meeting.value = "";
});
$("#career-play-form").addEventListener("input", (event) => {
  if (event.target !== $("#career-play-form").elements.authorize_apply) $("#career-play-form").elements.authorize_apply.checked = false;
  if ($("#career-play-form").dataset.busy !== "true") updateCareerPlayScope();
});
$("#career-play-form").elements.mode.addEventListener("change", () => {
  $("#career-play-form").elements.authorize_apply.checked = false;
  updateCareerPlayScope();
});
$("#campaign-form").addEventListener("submit", (event) => guardedSubmit(event, saveCampaign));
$("#creator-run-form").addEventListener("submit", (event) => guardedSubmit(event, saveCreatorRun));
$("#creator-run-form").addEventListener("input", (event) => { if (event.target.name !== "authorize_run") event.currentTarget.elements.authorize_run.checked = false; });
$("#creator-mail-review-form").addEventListener("submit", (event) => guardedSubmit(event, saveCreatorMailReview));
$("#creator-mail-review-form").elements.classification.addEventListener("change", (event) => { $("#creator-mail-review-form").elements.prospect_id.required = event.target.value !== "ignore"; });
$("#prospect-form").addEventListener("submit", (event) => guardedSubmit(event, saveProspect));
$("#marketing-outcome-form").addEventListener("submit", (event) => guardedSubmit(event, saveMarketingOutcome));
$("#marketing-reply-form").addEventListener("submit", (event) => guardedSubmit(event, async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const initial = form.elements.stage.value === "initial";
  if (initial && form.elements.draft_method.value === "ai") return prepareCreatorDraft();
  if (initial && form.elements.draft_method.value === "template") return planMarketingEmail(form.elements.prospect_id.value, "initial");
  const subject = form.elements.subject.value.trim();
  const body = form.elements.body.value.trim();
  if (!subject || !body) {
    $("#marketing-message-fields").open = true;
    showFormError(form, new Error("Fill both the subject and body, or select the campaign template for an introduction."));
    (subject ? form.elements.body : form.elements.subject).focus();
    return;
  }
  await planMarketingEmail(form.elements.prospect_id.value, form.elements.stage.value, subject || null, body || null);
}).finally(updateMarketingDraftMode));
$("#marketing-reply-form").elements.draft_method.addEventListener("change", () => {
  clearFormError($("#marketing-reply-form"));
  clearTimeout(creatorDraftTimer);
  updateMarketingDraftMode();
  if ($("#marketing-reply-form").elements.draft_method.value === "ai") {
    if (!creatorDraftLoaded || creatorDraftError) loadCreatorDraftReview();
    else scheduleCreatorDraftRefresh();
  }
});
$("#marketing-reply-dialog").addEventListener("close", () => {
  if (!$("#marketing-reply-dialog").open) resetCreatorDraftReview();
});
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
$("#opportunity-search").addEventListener("input", renderOpportunities);
$("#opportunity-age-filter").addEventListener("change", renderOpportunities);
$("#opportunity-quality-filter").addEventListener("change", renderOpportunities);
$("#marketing-campaign-filter").addEventListener("change", () => { renderProspects(); loadCreatorCoverage(); });
$("#marketing-status-filter").addEventListener("change", renderProspects);
$("#marketing-contact-filter").addEventListener("change", renderProspects);
$("#marketing-platform-filter").addEventListener("change", renderProspects);
$("#marketing-target-filter").addEventListener("change", renderProspects);
$("#marketing-sort").addEventListener("change", renderProspects);
$("#marketing-search").addEventListener("input", renderProspects);
for (const id of ["marketing-fit-filter", "marketing-activity-filter", "marketing-evidence-filter"]) $("#" + id).addEventListener("change", renderProspects);
$("#campaign-form").elements.targeting_preset.addEventListener("change", (event) => {
  const preset = event.target.value;
  if (preset === "custom") return;
  const form = $("#campaign-form");
  form.elements.country_mode.value = preset === "poland_strict" ? "strict" : preset === "poland_prefer" ? "prefer" : "any";
  form.elements.target_country.value = preset === "global" ? "" : "PL";
  form.elements.language_mode.value = preset === "global" ? "any" : "prefer";
  form.elements.target_language.value = preset === "global" ? "" : "pl";
  if (preset !== "global") { form.elements.region_code.value = "PL"; form.elements.relevance_language.value = "pl"; }
});
for (const name of ["country_mode", "target_country", "language_mode", "target_language"]) {
  $("#campaign-form").elements[name].addEventListener("change", () => { $("#campaign-form").elements.targeting_preset.value = "custom"; });
}
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
