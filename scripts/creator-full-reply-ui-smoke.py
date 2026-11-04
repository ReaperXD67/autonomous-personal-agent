"""Network-disabled browser proof for private creator full-reply review.

Loads the actual web sources from /web. Every API response is synthetic; the
action-worker container has no network and writes screenshots only to /proof.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


def main():
    assets = {
        "/": ("text/html", "index.html"),
        "/assets/app.css": ("text/css", "app.css"),
        "/assets/app.js": ("application/javascript", "app.js"),
    }
    campaign = "synthetic-campaign"
    prefix = f"/v1/marketing/campaigns/{campaign}/replies/"
    digest = "a" * 64
    other_digest = "b" * 64
    body = (
        "Please explain the proposed revenue-share period before we discuss next steps.\n\n"
        + "This is synthetic context beyond the short provider preview. " * 18
        + '\n<img src=x onerror="window.untrustedReplyExecuted=true">'
        + "\n<script>window.untrustedReplyExecuted=true</script>"
        + "\n" + "unbroken" * 70
        + "\nEND OF COMPLETE SYNTHETIC MESSAGE"
    )
    summaries = {
        reply_id: {
            "id": reply_id, "campaign_id": campaign, "prospect_id": "synthetic-prospect",
            "sender": "creator@example.test", "subject": f"Synthetic reply {reply_id}",
            "snippet": "Short provider preview only.",
            "received_at": "2026-11-03T12:00:00Z", "body_status": "missing",
            "body_attempt_count": 0,
            "needs_review": reply_id != "reviewed",
        }
        for reply_id in [
            "complete", "incomplete", "late", "other", "polling", "reviewed", "recovery",
        ]
    }

    def detail(reply_id, complete=True):
        return {
            **summaries[reply_id], "body_status": "complete" if complete else "unavailable",
            "body_complete": complete, "body_format": "text/plain",
            "body_digest": other_digest if reply_id == "other" else digest,
            "body_text": "OTHER CONVERSATION BODY" if reply_id == "other" else body,
            "authored_text": "Synthetic authored-only estimate.",
            "authored_view_is_heuristic": True, "body_attempt_count": 1 if complete else 0,
        }

    modes = {"incomplete": "incomplete", "late": "hold", "polling": "reading"}
    reads, reviews, get_counts, errors, held = [], [], {}, [], []
    read_conflict = [True]
    draft_conflict = [True]
    retry_conflict = [True]
    retry_posts = []
    draft_posts, held_drafts = [], []
    draft_records, draft_counts, draft_modes = {}, {}, {}
    draft_body = (
        "Thanks for explaining your promotion policy. Please contact our owner on Discord "
        "at synthetic_owner to discuss whether the proposed earning-share model fits. "
        "No fee or commercial term has been agreed.\n"
        '<img src=x onerror="window.untrustedDraftExecuted=true">\n'
        + "longdraftword" * 45
    )

    def reply_draft(reply_id, status="ready"):
        return {
            "id": f"synthetic-draft-{reply_id}", "reply_id": reply_id,
            "campaign_id": campaign, "prospect_id": "synthetic-prospect",
            "task_id": "synthetic-curation-task", "status": status,
            "subject": "Synthetic response · not sent", "body": draft_body,
            "source": "ollama", "selected_model": "synthetic-local-model",
            "reply_body_digest": other_digest if reply_id == "other" else digest,
            "input_hash": "c" * 64, "draft_digest": "d" * 64,
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            "sending_authority": False, "contact_authorized": False, "context_current": True,
            "attempt_number": 1, "retry_of_id": None, "retry_eligible": False,
            "retry_available_at": None, "retry_block_reason": None,
        }

    unexpected = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1080})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("window.setInterval = () => 0;")

        def respond(route):
            path = urlparse(route.request.url).path
            if path in assets:
                mime, filename = assets[path]
                route.fulfill(content_type=mime, body=Path("/web", filename).read_text())
                return
            if path.startswith(prefix):
                suffix = path.removeprefix(prefix).split("/")
                reply_id = suffix[0]
                if reply_id not in summaries:
                    unexpected.append(path)
                    route.abort()
                    return
                if suffix[-1] == "drafts" and route.request.method == "GET":
                    draft_counts[reply_id] = draft_counts.get(reply_id, 0) + 1
                    if draft_modes.get(reply_id) == "hold":
                        held_drafts.append(route)
                        return
                    if draft_modes.get(reply_id) == "working" and draft_counts[reply_id] > 1:
                        draft_records[reply_id] = [reply_draft(reply_id)]
                        draft_modes[reply_id] = "ready"
                    if draft_modes.get(reply_id) == "recovering" and draft_counts[reply_id] > 1:
                        draft_records[reply_id][0]["status"] = "ready"
                        draft_modes[reply_id] = "recovered"
                    route.fulfill(json=draft_records.get(reply_id, []))
                    return
                if suffix[-1] == "retry" and route.request.method == "POST":
                    retry_posts.append({"failed_id": suffix[-2], **route.request.post_data_json})
                    if retry_conflict[0]:
                        route.fulfill(status=409, json={
                            "detail": "Synthetic recovery is not ready.",
                        })
                    else:
                        original = draft_records[reply_id][0]
                        original["retry_eligible"] = False
                        recovered = {**reply_draft(reply_id, status="queued"),
                                     "id": "synthetic-recovery-attempt", "attempt_number": 2,
                                     "retry_of_id": original["id"]}
                        draft_records[reply_id] = [recovered, original]
                        draft_modes[reply_id] = "recovering"
                        draft_counts[reply_id] = 0
                        route.fulfill(status=202, json=recovered)
                    return
                if suffix[-1] == "draft" and route.request.method == "POST":
                    draft_posts.append(route.request.post_data_json)
                    if draft_conflict[0]:
                        route.fulfill(status=409, json={
                            "detail": "Synthetic source changed. Refresh reply evidence.",
                        })
                    else:
                        draft_records[reply_id] = [reply_draft(reply_id, status="queued")]
                        draft_modes[reply_id] = "working"
                        draft_counts[reply_id] = 0
                        route.fulfill(status=202, json=draft_records[reply_id][0])
                    return
                if suffix[-1] == "review" and route.request.method == "POST":
                    reviews.append({"reply_id": reply_id, **route.request.post_data_json})
                    route.fulfill(json={"id": reply_id, "reviewed": True})
                    return
                if suffix[-1] == "read" and route.request.method == "POST":
                    reads.append(route.request.post_data_json)
                    if read_conflict[0]:
                        route.fulfill(status=409, json={
                            "detail": "Synthetic read cooldown; refresh detail.",
                        })
                    else:
                        modes[reply_id] = "reading"
                        get_counts[reply_id] = 0
                        route.fulfill(status=202, json={
                            "task": {"id": "synthetic-read-task", "status": "queued"},
                            "capture": {"body_status": "reading", "body_attempt_count": 1},
                        })
                    return
                if len(suffix) == 1 and route.request.method == "GET":
                    get_counts[reply_id] = get_counts.get(reply_id, 0) + 1
                    mode = modes.get(reply_id, "complete")
                    if mode == "hold":
                        held.append(route)
                        return
                    if mode == "error":
                        route.fulfill(status=500, json={"detail": "Synthetic detail unavailable."})
                        return
                    if mode == "reading" and reply_id != "polling" and get_counts[reply_id] > 1:
                        modes[reply_id] = "complete"
                        mode = "complete"
                    response = detail(reply_id, complete=mode == "complete")
                    if mode == "reading":
                        response.update(body_status="reading", body_attempt_count=1)
                    route.fulfill(json=response)
                    return
            # Only the initial session probe may be unauthenticated. No provider
            # URL or other dashboard endpoint belongs to this focused proof.
            if path != "/v1/auth/session":
                unexpected.append(path)
            route.fulfill(status=401, json={"detail": "Synthetic locked workspace"})

        page.route("**/*", respond)
        page.goto("https://fixture.test/")
        page.wait_for_function("typeof openCreatorMailReview === 'function'")
        page.wait_for_timeout(100)
        page.evaluate("""({campaign, summaries}) => {
          loadData = async () => {};
          state.browserSession = true;
          state.csrfToken = 'synthetic-only';
          setConnection(true);
          state.creatorAutomation = {[campaign]: {pending_replies:
            Object.values(summaries).filter(reply => reply.needs_review)}};
          state.prospects = [{id: 'synthetic-prospect', campaign_id: campaign,
            display_name: 'Synthetic creator', contact_email: 'creator@example.test'}];
        }""", {"campaign": campaign, "summaries": summaries})
        # A newer failed read survives queued/running work and configured
        # credentials. Only a later completed read clears the visible hold.
        page.evaluate("""campaign => {
          const data = state.creatorAutomation[campaign];
          data.readiness = {gmail_configured:true, smtp_configured:true};
          data.gmail_sync = {last_complete_at:'2026-11-03T12:00:00Z',
            last_failure_at:'2026-11-03T12:10:00Z', last_sync_at:'2026-11-03T12:15:00Z'};
          data.gmail_task = {status:'running', error_message:'RAW FAILURE MUST NOT APPEAR'};
          const panel = document.createElement('div'); panel.id='synthetic-sync-panel';
          panel.append(creatorAutomationPanel({id:campaign})); document.body.append(panel);
        }""", campaign)
        warning = page.locator("#synthetic-sync-panel .creator-gmail-failure")
        expect(warning).to_contain_text("New approvals are held")
        expect(warning).to_contain_text("Last complete read:")
        expect(warning).not_to_contain_text("RAW FAILURE")
        page.evaluate("""campaign => {
          state.creatorAutomation[campaign].gmail_task.status='queued';
          document.querySelector('#synthetic-sync-panel').replaceChildren(
            creatorAutomationPanel({id:campaign}));
        }""", campaign)
        expect(warning).to_contain_text("reading failed")
        page.evaluate("""campaign => {
          state.creatorAutomation[campaign].gmail_sync.last_complete_at='2026-11-03T12:20:00Z';
          document.querySelector('#synthetic-sync-panel').replaceChildren(
            creatorAutomationPanel({id:campaign}));
        }""", campaign)
        expect(warning).to_have_count(0)
        page.locator("#synthetic-sync-panel").evaluate("element => element.remove()")
        dialog = page.locator("#creator-mail-review-dialog")
        form = page.locator("#creator-mail-review-form")
        body_view = page.locator("#creator-mail-body")
        note = form.locator('[name="note"]')
        classification = form.locator('[name="classification"]')
        hidden_digest = form.locator('[name="body_digest"]')

        def open_reply(reply_id):
            page.evaluate("({campaign, reply}) => { void openCreatorMailReview(campaign, reply); }",
                          {"campaign": campaign, "reply": reply_id})
            expect(dialog).to_be_visible()

        def close_reply():
            dialog.get_by_role("button", name="Close", exact=True).click()
            expect(dialog).not_to_be_visible()
            expect(hidden_digest).to_have_value("")
            expect(body_view).to_have_text("")

        # Complete text, including content far beyond a provider preview, is
        # visible as inert plaintext. The authored estimate remains labelled.
        open_reply("complete")
        expect(body_view).to_have_text(body)
        expect(hidden_digest).to_have_value(digest)
        expect(classification.locator('[value="question"]')).to_have_js_property("disabled", False)
        assert not page.locator("#creator-mail-evidence img, #creator-mail-evidence script").count()
        assert page.evaluate("window.untrustedReplyExecuted === undefined")
        expect(page.locator("#creator-mail-authored-view summary")).to_contain_text("heuristic")
        note.fill("Keep this independently reviewed note.")
        page.locator("#creator-mail-refresh").click()
        expect(page.locator("#creator-mail-evidence")).to_have_attribute("aria-busy", "false")
        expect(note).to_have_value("Keep this independently reviewed note.")
        dialog.evaluate("element => { element.scrollTop = 0; }")
        page.screenshot(path="/proof/creator-full-reply-desktop.png")
        classification.select_option("question")
        form.get_by_role("button", name="Record reviewed reply").click()
        expect(dialog).not_to_be_visible()
        assert reviews[-1]["body_digest"] == digest
        assert reviews[-1]["classification"] == "question"
        assert reviews[-1]["note"] == "Keep this independently reviewed note."

        # An incomplete response deliberately contains bogus text/digest: neither
        # is accepted as complete evidence, even through a synthetic submit.
        open_reply("incomplete")
        expect(page.locator("#creator-mail-body-status")).to_contain_text("Preview only")
        expect(hidden_digest).to_have_value("")
        expect(page.locator("#creator-mail-full-text")).to_be_hidden()
        for value in ("interested", "question", "declined_unpaid"):
            option = classification.locator(f'[value="{value}"]')
            expect(option).to_have_js_property("disabled", True)
        conservative = classification.locator('[value="do_not_contact"]')
        expect(conservative).to_have_js_property("disabled", False)
        before = len(reviews)
        form.evaluate("""element => {
          element.elements.classification.value = 'interested';
          element.dispatchEvent(new Event('submit', {bubbles:true, cancelable:true}));
        }""")
        expect(form.locator(".form-feedback")).to_contain_text("complete reply")
        assert len(reviews) == before
        note.fill("Preserve this note through retries.")
        page.locator("#creator-mail-read").click()
        expect(page.locator("#creator-mail-body-error")).to_contain_text("cooldown")
        expect(note).to_have_value("Preserve this note through retries.")
        read_conflict[0] = False
        page.locator("#creator-mail-read").click()
        expect(body_view).to_have_text(body, timeout=8000)
        expect(hidden_digest).to_have_value(digest)
        expect(note).to_have_value("Preserve this note through retries.")
        assert reads == [{"actor": "dashboard:marketing"}] * 2
        assert get_counts["incomplete"] == 2
        close_reply()

        # A detail request for a closed conversation must never populate a new
        # modal; the new selection keeps its own body and exact digest.
        open_reply("late")
        expect(page.locator("#creator-mail-evidence")).to_have_attribute("aria-busy", "true")
        expect(hidden_digest).to_have_value("")
        page.wait_for_function("document.querySelector('#creator-mail-read').disabled")
        assert len(held) == 1
        close_reply()
        open_reply("other")
        expect(body_view).to_have_text("OTHER CONVERSATION BODY")
        held.pop().fulfill(json=detail("late"))
        page.wait_for_timeout(100)
        expect(body_view).to_have_text("OTHER CONVERSATION BODY")
        expect(hidden_digest).to_have_value(other_digest)
        close_reply()

        # Errors are local to the modal; a safe conservative review still works
        # without complete text, and successful refresh keeps operator notes.
        modes["incomplete"] = "error"
        open_reply("incomplete")
        expect(page.locator("#creator-mail-body-error")).to_contain_text("unavailable")
        note.fill("Review note survives detail recovery.")
        modes["incomplete"] = "complete"
        page.locator("#creator-mail-refresh").click()
        expect(hidden_digest).to_have_value(digest)
        expect(note).to_have_value("Review note survives detail recovery.")
        close_reply()
        modes["incomplete"] = "incomplete"
        open_reply("incomplete")
        expect(page.locator("#creator-mail-body-status")).to_contain_text("Preview only")
        classification.select_option("ignore")
        form.get_by_role("button", name="Record reviewed reply").click()
        expect(dialog).not_to_be_visible()
        assert reviews[-1]["classification"] == "ignore"
        assert reviews[-1]["body_digest"] is None

        # Polling remains local and bounded by the open modal. Closing it
        # cancels further detail checks rather than leaving background reads.
        open_reply("polling")
        expect(page.locator("#creator-mail-body-status")).to_contain_text("in progress")
        page.locator("#creator-mail-read").click()
        page.wait_for_timeout(100)
        close_reply()
        count_after_close = get_counts["polling"]
        page.wait_for_timeout(1700)
        assert get_counts["polling"] == count_after_close

        # Actual mobile layout: long unbroken plaintext wraps in a focusable,
        # scrollable region, and the dialog stays within the viewport.
        page.set_viewport_size({"width": 375, "height": 812})
        open_reply("complete")
        expect(body_view).to_have_text(body)
        expect(body_view).to_have_attribute("tabindex", "0")
        expect(page.locator("#creator-mail-body-status")).to_have_attribute("aria-live", "polite")
        dimensions = dialog.evaluate("""element => ({
          width:element.getBoundingClientRect().width,
          viewport:innerWidth, scroll:element.scrollWidth, client:element.clientWidth,
          bodyScroll:document.querySelector('#creator-mail-body').scrollWidth,
          bodyClient:document.querySelector('#creator-mail-body').clientWidth,
          button:document.querySelector('#creator-mail-read').getBoundingClientRect().height
        })""")
        assert dimensions["width"] <= dimensions["viewport"]
        assert dimensions["scroll"] <= dimensions["client"] + 1
        assert dimensions["bodyScroll"] <= dimensions["bodyClient"] + 1
        assert dimensions["button"] >= 44
        dialog.evaluate("element => { element.scrollTop = 0; }")
        page.screenshot(path="/proof/creator-full-reply-mobile.png")
        page.keyboard.press("Escape")
        expect(dialog).not_to_be_visible()
        expect(hidden_digest).to_have_value("")
        # Curation stays separately opted in and draft-only, even when current
        # contact authority is withdrawn. No review decision is inferred.
        page.set_viewport_size({"width": 1440, "height": 1080})
        open_reply("complete")
        expect(hidden_digest).to_have_value(digest)
        curate = page.locator("#creator-mail-curate")
        expect(curate).to_be_disabled()
        expect(curate).to_have_text("Reply drafting is off")
        page.evaluate("""campaign => {
          state.creatorAutomation[campaign].readiness.reply_draft_enabled = true;
          updateCreatorMailDraftControls();
        }""", campaign)
        expect(curate).to_be_enabled()
        note.fill("Keep both conversations on hold.")
        curate.click()
        expect(page.locator("#creator-mail-draft-error")).to_contain_text("source changed")
        expect(note).to_have_value("Keep both conversations on hold.")
        draft_conflict[0] = False
        review_count = len(reviews)
        curate.click()
        expect(page.locator("#creator-mail-draft-list pre")).to_have_text(draft_body, timeout=8000)
        expect(page.locator("#creator-mail-draft-list")).to_contain_text("Sending remains on hold")
        expect(curate).to_be_disabled()
        assert draft_posts == [{"actor": "dashboard:marketing", "body_digest": digest}] * 2
        page.evaluate("void curateCreatorMailDraft()")
        assert len(draft_posts) == 2, "Current draft must not queue a duplicate"
        # The source body may stay identical while frozen campaign context
        # changes. Server context validity, not the body hash alone, controls
        # whether another governed curation request is available.
        draft_records["complete"][0]["context_current"] = False
        page.locator("#creator-mail-drafts-refresh").click()
        expect(page.locator("#creator-mail-draft-list")).to_contain_text(
            "source or campaign context has changed"
        )
        expect(curate).to_be_enabled()
        draft_records["complete"][0]["context_current"] = True
        page.locator("#creator-mail-drafts-refresh").click()
        expect(curate).to_be_disabled()
        assert len(reviews) == review_count
        expect(classification).to_have_value("")
        assert not page.locator("#creator-mail-draft-list img").count()
        assert page.evaluate("window.untrustedDraftExecuted === undefined")
        page.locator("#creator-mail-draft-list summary").click()
        expect(page.locator("#creator-mail-draft-list")).to_contain_text(
            f"Reply body digest: {digest}"
        )
        expect(page.locator("#creator-mail-draft-list")).to_contain_text("Source: ollama")
        assert page.locator("#creator-mail-drafts button").count() == 2
        page.locator("#creator-mail-drafts").evaluate(
            "element => element.scrollIntoView({block:'start'})"
        )
        page.screenshot(path="/proof/creator-reply-draft-desktop.png")
        page.set_viewport_size({"width": 375, "height": 812})
        assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth + 1")
        draft_copy = page.locator("#creator-mail-draft-list pre")
        assert draft_copy.evaluate("element => element.scrollWidth <= element.clientWidth + 1")
        page.locator("#creator-mail-drafts").evaluate(
            "element => element.scrollIntoView({block:'start'})"
        )
        page.screenshot(path="/proof/creator-reply-draft-mobile.png")
        close_reply()

        # A delayed draft-list response cannot attach another conversation's
        # copy or source digest after the operator changes the modal selection.
        modes["late"] = "complete"
        draft_modes["late"] = "hold"
        draft_records["other"] = [reply_draft("other")]
        draft_records["other"][0]["body"] = "OTHER PRIVATE RESPONSE DRAFT"
        open_reply("late")
        expect(page.locator("#creator-mail-drafts")).to_have_attribute("aria-busy", "true")
        assert len(held_drafts) == 1
        close_reply()
        open_reply("other")
        expect(page.locator("#creator-mail-draft-list pre")).to_have_text(
            "OTHER PRIVATE RESPONSE DRAFT"
        )
        held_drafts.pop().fulfill(json=[reply_draft("late")])
        page.wait_for_timeout(100)
        expect(page.locator("#creator-mail-draft-list pre")).to_have_text(
            "OTHER PRIVATE RESPONSE DRAFT"
        )
        close_reply()

        # Reviewed replies are discoverable through metadata-only saved-draft
        # rows, even though they are absent from the pending-review shortlist.
        draft_records["reviewed"] = [reply_draft("reviewed")]
        page.evaluate("""({campaign, draft}) => {
          state.campaigns = [{id:campaign, name:'Synthetic campaign'}];
          state.creatorAutomation[campaign].reply_drafts = [draft];
          renderCreatorWork(); switchView('campaigns');
        }""", {"campaign": campaign, "draft": {
            key: value for key, value in draft_records["reviewed"][0].items()
            if key not in {"subject", "body", "selected_model", "source", "input_hash"}
        }})
        page.get_by_role("button", name="Inspect response draft", exact=True).click()
        expect(body_view).to_have_text(body)
        expect(page.locator("#creator-mail-draft-list pre")).to_have_text(draft_body)
        expect(classification).to_be_disabled()
        expect(form.get_by_role("button", name="Reply already reviewed")).to_be_disabled()
        modes["reviewed"] = "error"
        page.locator("#creator-mail-refresh").click()
        expect(page.locator("#creator-mail-body-error")).to_contain_text("unavailable")
        expect(classification).to_be_disabled()
        assert len(reviews) == review_count
        close_reply()

        # A retained local-model failure never retries merely because the modal
        # opens, a cooldown passes or saved status is refreshed. Only the exact
        # server eligibility projection reveals an explicit recovery action.
        original_failure = reply_draft("recovery", status="failed")
        original_failure.update({
            "source": None, "selected_model": None,
            "error_code": "CREATOR_REPLY_DRAFT_MODEL_UNAVAILABLE",
            "retry_available_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "retry_block_reason": "recovery_not_eligible",
        })
        draft_records["recovery"] = [original_failure]
        open_reply("recovery")
        expect(page.locator("#creator-mail-draft-list")).to_contain_text("Attempt 1 of 2")
        expect(page.locator("#creator-mail-draft-list")).to_contain_text(
            "normal draft request do not retry"
        )
        retry = page.get_by_role("button", name="Retry after model recovery", exact=True)
        expect(retry).to_have_count(0)
        page.locator("#creator-mail-drafts-refresh").click()
        expect(page.locator("#creator-mail-drafts")).to_have_attribute("aria-busy", "false")
        expect(retry).to_have_count(0)
        assert not retry_posts
        original_failure["retry_eligible"] = True
        original_failure["retry_block_reason"] = None
        page.locator("#creator-mail-drafts-refresh").click()
        expect(retry).to_be_enabled()
        note.fill("Owner still holds this conversation.")
        retry.click()
        expect(page.locator("#creator-mail-draft-error")).to_contain_text("not ready")
        expect(note).to_have_value("Owner still holds this conversation.")
        retry_conflict[0] = False
        retry.click()
        expect(page.locator("#creator-mail-draft-list pre")).to_have_text(draft_body, timeout=8000)
        expect(page.locator("#creator-mail-draft-list")).to_contain_text("Attempt 2 of 2")
        expect(page.locator("#creator-mail-draft-list")).to_contain_text("Attempt 1 of 2")
        expect(page.locator("#creator-mail-draft-list")).to_contain_text("retained first attempt")
        expect(page.locator("#creator-mail-draft-list h4")).to_have_text([
            "Ready · draft only, not sent", "Failed · draft only, not sent",
        ])
        expect(retry).to_have_count(0)
        expect(note).to_have_value("Owner still holds this conversation.")
        assert retry_posts == [{
            "failed_id": original_failure["id"], "actor": "dashboard:marketing",
            "body_digest": digest,
        }] * 2
        assert len(reviews) == review_count
        expect(classification).to_have_value("")
        assert all(not item["sending_authority"] for item in draft_records["recovery"])
        close_reply()
        assert not unexpected, unexpected
        assert not errors, errors
        browser.close()
    print("Creator full-reply UI proof passed: plaintext, digest review, retries, "
          "modal isolation, private draft-only curation, explicit recovery lineage, "
          "reviewed history, mobile.")


if __name__ == "__main__":
    main()
