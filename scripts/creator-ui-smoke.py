"""Networkless Playwright check of the actual dashboard sources with synthetic data.

Mount web sources at /web and a disposable output directory at /proof. Run using
the existing action-worker image; no host Node/Python dependencies are needed.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def main():
    assets = {
        "/": ("text/html", "index.html"),
        "/assets/app.css": ("text/css", "app.css"),
        "/assets/app.js": ("application/javascript", "app.js"),
    }
    errors = []
    drafts = []
    requests = []
    pilot_requests = []
    pilot_latest = [None]
    pilot_task = {
        "id": "synthetic-pilot-task", "kind": "marketing.creator_pilot",
        "status": "queued", "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(), "output": None,
    }
    allow_prepare = False
    draft = {
        "id": "synthetic-draft", "prospect_id": "synthetic-prospect",
        "campaign_id": "synthetic-campaign", "status": "queued", "task_status": "queued",
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(hours=12)).isoformat(),
        "quality_notes": [], "evidence": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1080})
        page.on("pageerror", lambda error: errors.append(str(error)))
        # Keep unrelated workspace refreshes out of this focused synthetic fixture.
        # Draft polling uses setTimeout and remains active.
        page.add_init_script("window.setInterval = () => 0;")

        def respond(route):
            path = urlparse(route.request.url).path
            if path in assets:
                mime, filename = assets[path]
                route.fulfill(content_type=mime, body=Path("/web", filename).read_text())
            elif path == "/v1/marketing/campaigns/synthetic-campaign/pilot-research":
                if route.request.method == "POST":
                    pilot_requests.append(route.request.post_data_json)
                    pilot_latest[0] = pilot_task
                route.fulfill(content_type="application/json", body=json.dumps(pilot_latest[0]))
            elif path == "/v1/marketing/prospects/synthetic-prospect":
                route.fulfill(content_type="application/json", body=json.dumps({
                    "id": "synthetic-prospect", "campaign_id": "synthetic-campaign",
                    "display_name": "A creator with Minecraft survival videos",
                    "contact_authorized_at": datetime.now(UTC).isoformat(), "suppressed_at": None,
                }))
            elif path == "/v1/marketing/prospects/synthetic-prospect/drafts":
                if route.request.method == "POST":
                    requests.append(route.request.post_data_json)
                    drafts[:] = [draft]
                    result = draft
                else:
                    result = drafts
                route.fulfill(content_type="application/json", body=json.dumps(result))
            elif path == "/v1/marketing/drafts/synthetic-draft/prepare":
                requests.append(route.request.post_data_json)
                route.fulfill(
                    status=200 if allow_prepare else 409, content_type="application/json",
                    body=json.dumps({"id": "synthetic-action"} if allow_prepare
                                    else {"detail": "Campaign changed. Generate a fresh draft."}),
                )
            else:
                route.fulfill(status=401, content_type="application/json",
                              body=json.dumps({"detail": "Synthetic unauthenticated fixture"}))

        page.route("**/*", respond)
        # A secure fixture origin exposes crypto.randomUUID, matching the actual
        # trusted loopback dashboard. Every request is still intercepted above.
        page.goto("https://fixture.test/")
        page.wait_for_function("typeof openCreatorRun === 'function'")
        page.evaluate("""() => {
          state.browserSession = true;
          state.csrfToken = 'synthetic-only';
          setConnection(true);
          state.campaigns = [{id:'synthetic-campaign',name:'Minecraft creator partnerships · demo',
            product_name:'FixtureCraft',product_url:'https://example.test/',
            privacy_url:'https://example.test/privacy',product_summary:'a Minecraft server directory',
            target_audience:'Minecraft creators',viewer_offer:'Explore servers',creator_offer:'Create content',
            sender_name:'Synthetic owner',paid_offer_enabled:true,outreach_mode:'paid',
            compensation_model:'revenue_share',revenue_share_percent:null,revenue_share_weeks:null,
            paid_offer_details:'Explore listed servers and create original content. Discuss a share of earnings and a period in weeks with the owner.',
            handoff_discord:'synthetic_owner',discovery_queries:['Minecraft survival','Minecraft SMP'],
            min_subscribers:0,max_subscribers:1000000000,max_video_age_days:120,
            results_per_query:25,search_pages_per_query:1,schedule_hours:24,relevance_language:'en',
            country_mode:'any',language_mode:'any',active:false,adaptive_mode:true}];
          state.creatorAutomation = {'synthetic-campaign':{run:null,pending_replies:[],
            readiness:{gmail_configured:false,smtp_configured:true}}};
          state.creatorPilot = {'synthetic-campaign':{task:null}};
          state.marketingResults = [{campaign_id:'synthetic-campaign',metrics:{discovered:42,
            emails_sent:4,initial_sent:3,replies:2,positive_replies:1,handoffs_sent:1},variants:[],suggestions:[],
            learning:{samples:{tagged_creators:3},reason:'Three creators asked for clearer terms. Test a terms-first introduction.',
              recommendations:[{tag:'unclear_revenue_share',creators:3,enough_evidence:true,message:'Explain the proposed percentage, earning window and attribution.'}],
              variants:[{variant:'terms_first',sent:3,positive:1}],caveat:'Synthetic demo. This is a copy hypothesis, not a proven improvement.'}}];
          renderAll(); switchView('campaigns');
        }""")
        assert page.get_by_text("Find the creators.").is_visible()
        assert page.get_by_text("Creator Gmail is not configured.", exact=False).is_visible()
        assert page.locator("#marketing-metric-signups").inner_text() == "1"
        page.get_by_text("What creators are teaching us", exact=False).click()
        assert page.get_by_text("Unclear Revenue Share", exact=False).is_visible()
        assert page.locator('#marketing-outcome-form input[name="feedback_tag"]').count() == 8
        assert page.locator('#marketing-outcome-form input[name="feedback_tag"]:checked').count() == 0
        assert page.evaluate("""() => {
          const form = document.querySelector('#marketing-outcome-form');
          form.querySelector('input[value="too_long"]').checked = true;
          const tags = reviewedFeedbackTags(form); form.reset();
          return tags.length === 1 && tags[0] === 'too_long';
        }""")
        assert page.evaluate("""() => !canPrepareCreatorHandoff({status:'interested',
          latest_message:{stage:'handoff',action_status:'queued'}})""")
        page.screenshot(path="/proof/creator-workflow-desktop.png", full_page=True)
        page.get_by_text("Research a creator shortlist", exact=True).click()
        pilot_limit = page.get_by_label("Creators to research", exact=True)
        assert pilot_limit.input_value() == "5" and pilot_limit.get_attribute("max") == "10"
        pilot_limit.fill("3")
        page.get_by_role("button", name="Research shortlist", exact=True).click()
        page.get_by_text("Shortlist research queued", exact=True).wait_for()
        assert len(pilot_requests) == 1 and pilot_requests[0]["limit"] == 3
        assert pilot_requests[0]["idempotency_key"]
        assert page.get_by_role("button", name="Research in progress…", exact=True).is_disabled()
        assert pilot_limit.input_value() == "3", "Batch setting was lost during refresh"
        pilot_task.update({
            "status": "succeeded",
            "output": {
                "researched": 3, "selected_count": 1, "requires_contact_review_count": 1,
                "failed": 1, "ranked": [{
                    "prospect_id": "synthetic-prospect", "display_name": "<img src=x> Creator",
                    "score": 78, "status": "selected", "subscriber_count": 12000,
                    "reasons": ["Minecraft survival uploads match the campaign."],
                    "gaps": ["Views are not an earnings forecast."],
                    "public_business_contact_count": 1, "contact_authorized": True,
                    "last_published_at": datetime.now(UTC).isoformat(),
                    "last_minecraft_published_at": datetime.now(UTC).isoformat(),
                    "latest_activity_url": "https://www.youtube.com/watch?v=synthetic",
                    "observed_language": "en", "language_source": "defaultAudioLanguage",
                    "contact_evidence": [{"excerpt": "Business: [contact removed]",
                                          "source_url": "https://www.youtube.com/@synthetic"}],
                }],
                "caveat": "Synthetic API research. No model calls or emails were made.",
            },
        })
        page.get_by_role("button", name="Refresh research status", exact=True).click()
        page.get_by_text("Shortlist ready for review", exact=True).wait_for()
        assert page.get_by_text("3 researched · 1 selected · 1 need contact review · 1 research failures", exact=True).is_visible()
        assert page.locator(".creator-pilot img").count() == 0
        assert page.get_by_text("Published language: en · declared audio language", exact=True).is_visible()
        assert page.get_by_role("link", name="Public contact source", exact=True).get_attribute("rel") == "noopener noreferrer"
        page.screenshot(path="/proof/creator-api-shortlist-desktop.png", full_page=True)
        page.set_viewport_size({"width": 375, "height": 812})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "API shortlist mobile overflow"
        page.evaluate("document.activeElement?.blur()")
        page.locator("#toast").wait_for(state="hidden")
        page.locator(".creator-pilot").evaluate("element => element.scrollIntoView({block:'start'})")
        page.screenshot(path="/proof/creator-api-shortlist-mobile.png")
        page.set_viewport_size({"width": 1440, "height": 1080})
        page.get_by_role("button", name="Draft introduction", exact=True).click()
        page.get_by_text("No AI draft yet", exact=True).wait_for()
        assert page.locator('#marketing-reply-form select[name="draft_method"]').input_value() == "ai"
        page.locator("#marketing-reply-dialog button[aria-label=Close]").click()
        pilot_task.update({"status": "failed", "output": None, "error_code": "PILOT_SOURCE_UNAVAILABLE"})
        page.get_by_role("button", name="Refresh research status", exact=True).click()
        page.get_by_text("Research did not complete", exact=True).wait_for()
        page.get_by_text("Research a creator shortlist", exact=True).click()
        page.get_by_role("button", name="Authorize outreach run", exact=True).click()
        assert page.locator("#creator-run-form input[name=authorize_run]").is_checked() is False
        page.locator("#creator-run-form input[name=authorize_run]").check()
        page.locator("#creator-run-form input[name=max_initials_per_day]").fill("4")
        assert page.locator("#creator-run-form input[name=authorize_run]").is_checked() is False
        page.locator("#creator-run-dialog button[aria-label=Close]").click()
        page.get_by_role("button", name="Create paid campaign", exact=True).click()
        assert page.locator("#campaign-form select[name=compensation_model]").input_value() == "revenue_share"
        assert page.locator("#campaign-form input[name=revenue_share_percent]").input_value() == ""
        assert page.locator("#campaign-form input[name=revenue_share_weeks]").input_value() == ""
        assert page.locator("#campaign-form input[name=handoff_discord]").input_value() == "karixai"
        page.locator("#campaign-dialog button[aria-label=Close]").click()
        page.get_by_role("button", name="Edit campaign", exact=True).click()
        assert page.locator("#campaign-form input[name=handoff_discord]").input_value() == "synthetic_owner"
        assert page.locator("#campaign-form select[name=compensation_model]").input_value() == "revenue_share"
        page.locator("#campaign-dialog button[aria-label=Close]").click()
        page.set_viewport_size({"width": 375, "height": 812})
        page.screenshot(path="/proof/creator-workflow-mobile.png", full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile overflow"
        page.get_by_role("button", name="Authorize outreach run", exact=True).click()
        assert page.locator("#creator-run-dialog").evaluate(
            "element => element.scrollWidth <= element.clientWidth"
        ), "Run dialog overflow"
        page.screenshot(path="/proof/creator-run-mobile.png")
        page.locator("#creator-run-dialog button[aria-label=Close]").click()
        page.set_viewport_size({"width": 1440, "height": 1080})
        page.evaluate("""() => {
          openMarketingReply({id:'synthetic-prospect', campaign_id:'synthetic-campaign',
            display_name:'A creator with Minecraft survival videos'}, 'initial');
        }""")
        method = page.locator('#marketing-reply-form select[name="draft_method"]')
        assert method.input_value() == "template"
        assert page.get_by_role("button", name="Prepare campaign template", exact=True).is_enabled()
        assert page.locator("#marketing-message-fields").is_hidden()
        method.select_option("manual")
        assert page.locator('#marketing-reply-form input[name="subject"]').is_visible()
        assert page.locator('#marketing-reply-form input[name="subject"]').get_attribute("required") is not None
        method.select_option("ai")
        page.get_by_text("No AI draft yet", exact=True).wait_for()
        assert page.get_by_role("button", name="Prepare exact AI email", exact=True).is_disabled()
        page.get_by_role("button", name="Generate personalized draft", exact=True).click()
        page.get_by_text("Draft queued", exact=True).wait_for()
        assert page.get_by_role("button", name="Draft in progress…", exact=True).is_disabled()
        assert len(requests) == 1 and requests[0]["idempotency_key"]
        page.locator("#marketing-reply-dialog button[aria-label=Close]").click()
        page.evaluate("""() => openMarketingReply({id:'synthetic-prospect',
          campaign_id:'synthetic-campaign',display_name:'A creator with Minecraft survival videos'}, 'initial')""")
        method.select_option("ai")
        page.get_by_text("Draft queued", exact=True).wait_for()
        assert len(requests) == 1, "Reopening a queued draft created another request"
        draft.update({
            "status": "ready", "task_status": "succeeded", "draft_digest": "synthetic-exact-digest",
            "source": "ollama", "selected_model": "synthetic-model",
            "subject": "A server exploration idea for your next Minecraft video",
            "body": "Hi creator,\n\nYour recorded survival series suggests an original server tour could fit. "
                    "Would you be open to discussing a share of attributable earnings and a period in weeks?",
            "quality_notes": ["Creator reference matches the recorded video.", "Terms remain a proposal."],
            "evidence": [{"id": "video-1", "title": "<img src=x> Survival series",
                          "url": "https://www.youtube.com/watch?v=synthetic"}],
            "learning_summary": {"reason": "Reviewed feedback asks for clearer attribution.",
                                 "samples": {"reviewed_creators": 3},
                                 "caveat": "This is a hypothesis, not a proven response-rate improvement."},
            "model_copy": {"rationale": "Connect the server directory to the recorded series.",
                           "reach_strategy": "small_pilot"},
        })
        page.get_by_role("button", name="Refresh draft status", exact=True).click()
        page.get_by_text("Ready for your review", exact=True).wait_for()
        assert page.get_by_role("button", name="Prepare exact AI email", exact=True).is_enabled()
        assert page.get_by_text("3 distinct creators with reviewed outcomes.", exact=True).is_visible()
        assert page.get_by_text("Written by synthetic-model", exact=False).is_visible()
        assert page.locator("#creator-ai-review img").count() == 0
        assert page.get_by_role("link", name="<img src=x> Survival series", exact=True).get_attribute("rel") == "noopener noreferrer"
        page.screenshot(path="/proof/creator-ai-draft-desktop.png")
        page.set_viewport_size({"width": 375, "height": 812})
        assert page.locator("#marketing-reply-dialog").evaluate(
            "element => element.scrollWidth <= element.clientWidth"
        ), "AI draft dialog overflow"
        page.screenshot(path="/proof/creator-ai-draft-mobile.png")
        draft["status"] = "stale"
        page.get_by_role("button", name="Refresh draft status", exact=True).click()
        page.get_by_text("Draft needs refreshing", exact=True).wait_for()
        assert page.get_by_role("button", name="Prepare exact AI email", exact=True).is_disabled()
        draft.update({"status": "failed", "task_status": "dead_letter", "error_code": "model_output_invalid"})
        page.get_by_role("button", name="Refresh draft status", exact=True).click()
        page.get_by_text("Draft did not pass", exact=True).wait_for()
        assert page.get_by_role("button", name="Prepare exact AI email", exact=True).is_disabled()
        draft.update({"status": "ready", "task_status": "succeeded", "error_code": None,
                      "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()})
        page.get_by_role("button", name="Refresh draft status", exact=True).click()
        page.get_by_text("Draft needs refreshing", exact=True).wait_for()
        assert page.get_by_role("button", name="Prepare exact AI email", exact=True).is_disabled()
        draft["expires_at"] = (datetime.now(UTC) + timedelta(hours=12)).isoformat()
        page.get_by_role("button", name="Refresh draft status", exact=True).click()
        page.get_by_text("Ready for your review", exact=True).wait_for()
        page.get_by_role("button", name="Prepare exact AI email", exact=True).click()
        page.get_by_text("Campaign changed. Generate a fresh draft.", exact=True).wait_for()
        assert page.locator("#marketing-reply-dialog").is_visible()
        assert requests[-1]["draft_digest"] == "synthetic-exact-digest"
        allow_prepare = True
        page.evaluate("""() => {
          loadData = async () => true;
          showActionReview = async (id) => { window.syntheticReviewedAction = id; };
        }""")
        page.get_by_role("button", name="Prepare exact AI email", exact=True).click()
        page.wait_for_function("window.syntheticReviewedAction === 'synthetic-action'")
        assert not page.locator("#marketing-reply-dialog").is_visible()
        assert len(requests) == 3, "Unexpected draft or preparation mutation"
        assert not errors, errors
        browser.close()
    print("Creator UI passed: desktop/mobile, revenue-share defaults, owner preservation, run consent reset, "
          "API shortlist queue/ranking/review/failure and escaped evidence, "
          "AI queued/ready/stale/failed states, escaped sources, exact-digest preparation, server conflict "
          "and separate template/manual paths; no console errors or overflow, all data synthetic, no network")


if __name__ == "__main__":
    main()
