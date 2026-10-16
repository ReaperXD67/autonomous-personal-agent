"""Networkless Playwright check of the actual dashboard sources with synthetic data.

Mount web sources at /web and a disposable output directory at /proof. Run using
the existing action-worker image; no host Node/Python dependencies are needed.
"""

import json
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
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1080})
        page.on("pageerror", lambda error: errors.append(str(error)))

        def respond(route):
            path = urlparse(route.request.url).path
            if path in assets:
                mime, filename = assets[path]
                route.fulfill(content_type=mime, body=Path("/web", filename).read_text())
            else:
                route.fulfill(status=401, content_type="application/json",
                              body=json.dumps({"detail": "Synthetic unauthenticated fixture"}))

        page.route("**/*", respond)
        page.goto("http://fixture.test/")
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
        assert not errors, errors
        browser.close()
    print("Creator UI passed: desktop/mobile, revenue-share defaults, owner contact preservation, explicit run consent reset, no console errors or overflow; all data synthetic, no network")


if __name__ == "__main__":
    main()
