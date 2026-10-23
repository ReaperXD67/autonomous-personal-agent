"""Networkless browser proof of career decisions, risk evidence and source intake.

Run in the existing action-worker image with /web read-only and /proof writable.
All data is synthetic; no provider, account or model request leaves the browser.
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
    errors, resolutions = [], []
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
            elif path == "/v1/career/sources/resolve":
                resolutions.append(route.request.post_data_json)
                unsupported = "linkedin.com" in resolutions[-1]["url"]
                route.fulfill(
                    status=422 if unsupported else 200, content_type="application/json",
                    body=json.dumps({"detail": "Open the employer application link first."}
                                    if unsupported else {
                                        "provider": "lever", "board": "synthetic",
                                        "source_config_key": "lever_eu_boards",
                                        "notice": "Adds the entire employer board.",
                                    }),
                )
            else:
                route.fulfill(status=401, content_type="application/json",
                              body=json.dumps({"detail": "Synthetic fixture"}))

        page.route("**/*", respond)
        page.goto("https://hermes.test/")
        page.evaluate("""() => {
          state.browserSession = true; state.csrfToken = 'synthetic'; setConnection(true);
          state.profiles = [{id:'mission',name:'Synthetic internship hunt',max_age_hours:72}];
          const base = {profile_id:'mission',source:'ashby',status:'new',company:'Example Labs',
            location:'Remote',published_at:new Date().toISOString(),published_at_basis:'published',
            score:90,score_reasons:['Recorded skill match'],source_url:'https://jobs.ashbyhq.com/example/role',
            apply_url:'https://jobs.ashbyhq.com/example/role',description:'Synthetic role only.'};
          const quality = {disposition:'no_strong_flags',authenticity:'unverified',signals:[],
            limitations:'Heuristic checks cannot prove an employer or vacancy is genuine or still open.'};
          state.opportunities = [{...base,id:'clean',title:'Software intern',quality},
            {...base,id:'flagged',title:'Suspicious fee request',quality:{...quality,
              disposition:'review_required',signals:[{severity:'block',message:'Posting requests an applicant fee or purchase'}]}}];
          state.careerTracking = {applications:[
            {opportunity_id:'clean',profile_id:'mission',company:'Example Labs',title:'Software intern',
              status:'shortlisted',updated_at:new Date().toISOString(),needs_review:true,events:[]},
            {opportunity_id:'interview',profile_id:'mission',company:'Interview Labs',title:'Intern',
              status:'interview',updated_at:new Date().toISOString(),needs_review:true,events:[]},
            {opportunity_id:'offer',profile_id:'mission',company:'Offer Labs',title:'<img src=x> Intern',
              status:'offer',updated_at:new Date().toISOString(),needs_review:true,events:[]}],
            review_candidates:[{profile_id:'mission',subject:'Please confirm your interview',
              suggested_status:'interview',snippet:'Synthetic uncertain match',received_at:new Date().toISOString()}]};
          renderProfileFilter(); renderOpportunities(); switchView('opportunities');
        }""")
        assert page.locator("#career-attention-count").inner_text().startswith("4 decisions")
        assert page.locator(".career-attention-item").first.inner_text().startswith("Offer")
        assert page.locator("#career-attention-list img").count() == 0
        assert "Shortlisted: 1" in page.locator("#career-pipeline-summary").inner_text()
        page.get_by_label("Filter by job-risk checks").select_option("review_required")
        assert page.locator("#opportunity-list .opportunity-card").count() == 1
        page.get_by_text("Job-risk signals · review required", exact=True).click()
        assert page.get_by_text("Posting requests an applicant fee or purchase", exact=True).is_visible()
        page.get_by_label("Filter by job-risk checks").select_option("")
        page.screenshot(path="/proof/career-decisions-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path="/proof/career-decisions-mobile.png", full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1080})
        page.evaluate("openProfileDialog()")
        page.locator("#profile-form summary").filter(has_text="Search sources").click()
        page.get_by_label("Employer board or job URL", exact=True).fill(
            "https://jobs.eu.lever.co/synthetic/role")
        page.get_by_role("button", name="Add board from URL", exact=True).click()
        page.get_by_text("Lever board added to this form.", exact=False).wait_for()
        assert page.get_by_label("Lever EU board names or URLs", exact=True).input_value() == "synthetic"
        page.get_by_label("Employer board or job URL", exact=True).fill("https://www.linkedin.com/jobs/view/123")
        page.get_by_role("button", name="Add board from URL", exact=True).click()
        page.get_by_text("Open the employer application link first.", exact=True).wait_for()
        assert page.get_by_label("Lever EU board names or URLs", exact=True).input_value() == "synthetic"
        assert len(resolutions) == 2
        assert not errors, errors
        browser.close()
    print("CAREER_UI_OK: priority outcomes, escaped text, risk filters, mobile layout, board import/error")


if __name__ == "__main__":
    main()
