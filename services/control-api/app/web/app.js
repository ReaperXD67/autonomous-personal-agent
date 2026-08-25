"use strict";

const state = {
  token: "",
  status: null,
  profiles: [],
  opportunities: [],
  tasks: [],
  audits: [],
  actions: [],
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
  state.profiles = [];
  state.opportunities = [];
  state.tasks = [];
  state.audits = [];
  state.actions = [];
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
    const [status, profiles, opportunities, tasks, audits, actions] = await Promise.all([
      api("/v1/system/status"),
      api("/v1/career/profiles"),
      api("/v1/career/opportunities?limit=300"),
      api("/v1/tasks?limit=200"),
      api("/v1/audit-events?limit=100"),
      api("/v1/external-actions?limit=200"),
    ]);
    Object.assign(state, { status, profiles, opportunities, tasks, audits, actions });
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

function renderAll() {
  renderMetrics();
  renderProfileFilter();
  renderMissions();
  renderOpportunities();
  renderApprovals();
  renderTasks();
  renderActivity();
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
    toast("Private résumé-tailored draft queued on local Qwen");
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
$("#scan-now-button").addEventListener("click", async () => {
  const profiles = state.profiles.filter((item) => item.active);
  if (!profiles.length) return toast("Activate at least one career mission first", true);
  for (const profile of profiles) await scanProfile(profile.id);
});

renderAll();
setConnection(false);
setInterval(() => { if (state.token) loadData({ quiet: true }); }, 15000);
