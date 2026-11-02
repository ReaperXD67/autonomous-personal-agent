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
    errors, resolutions, profile_writes = [], [], []
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
                payload = resolutions[-1]
                linkedin = "linkedin.com" in payload["url"]
                yc = "ycombinator.com" in payload["url"]
                unsupported = linkedin and not payload.get("employer_url")
                smart = "smartrecruiters.com" in payload["url"]
                result = {
                    "provider": "smartrecruiters" if smart else "lever",
                    "board": "synthetic",
                    "source_config_key": "smartrecruiters_boards" if smart else "lever_eu_boards",
                    "notice": "Adds the entire employer board.",
                }
                if linkedin:
                    result.update(
                        provider="ashby", source_config_key="ashby_boards",
                        discovery_platform="linkedin",
                        discovery_url="https://www.linkedin.com/jobs/view/123",
                        employer_url="https://jobs.ashbyhq.com/synthetic/role",
                        notice="Saved paired reference; public employer discovery only.",
                    )
                elif yc:
                    result.update(
                        provider="yc", source_config_key="yc_companies", board="synthetic-yc",
                        notice="Public discovery only. Apply manually on YC; no account connection.",
                    )
                route.fulfill(
                    status=422 if unsupported else 200, content_type="application/json",
                    body=json.dumps({"detail": "Open the employer application link first."}
                                    if unsupported else result),
                )
            elif path in {"/v1/career/profiles", "/v1/career/profiles/mission"} and route.request.method in {"POST", "PUT"}:
                profile_writes.append({"method": route.request.method, "payload": route.request.post_data_json})
                route.fulfill(content_type="application/json", body=json.dumps({"id": "mission"}))
            else:
                route.fulfill(status=401, content_type="application/json",
                              body=json.dumps({"detail": "Synthetic fixture"}))

        page.route("**/*", respond)
        page.goto("https://hermes.test/")
        page.evaluate("""() => {
          state.browserSession = true; state.csrfToken = 'synthetic'; setConnection(true);
          state.profiles = [{id:'mission',name:'Synthetic internship hunt',candidate_name:'Example Candidate',
            desired_titles:['Software intern'],skills:['Python'],required_keywords:[],excluded_keywords:[],
            locations:['India'],remote_only:false,employment_types:['Intern'],max_age_hours:72,min_score:75,
            schedule_minutes:360,active:false,auto_prepare:false,auto_prepare_min_score:75,
            max_auto_prepare_per_scan:3,resume_present:true,resume_characters:140,
            source_config:{arbeitnow:true,remotive:false,ashby_boards:['saved-board'],
              yc_companies:['saved-yc'],discovery_leads:[{platform:'yc',
                source_url:'https://www.ycombinator.com/companies/saved-yc/jobs/abc-intern',
                employer_url:'https://jobs.ashbyhq.com/saved-board/role'}]}}];
          state.careerAutopilot = {runs:[],readiness:[],sources:[{id:'yc',name:'Y Combinator',
            status:'manual',description:'Public company discovery with exact publication evidence.',
            url:'https://www.ycombinator.com/jobs'}]};
          const fit = {version:2,score:89,components:{title:{points:45,max:45},
            skills:{points:44,max:55,matched:['Python','React','SQL','Docker'],unobserved:['Java']}},
            hard_filters:{eligible:true,reasons:[]},limitations:'Heuristic fit is not a hiring probability.'};
          const base = {profile_id:'mission',source:'ashby',status:'new',company:'Example Labs',
            location:'Remote',published_at:new Date().toISOString(),published_at_basis:'published',
            score:90,score_reasons:['Recorded skill match'],source_url:'https://jobs.ashbyhq.com/example/role',
            apply_url:'https://jobs.ashbyhq.com/example/role',description:'Synthetic role only.',fit_report:fit};
          const quality = {disposition:'no_strong_flags',authenticity:'unverified',signals:[],
            limitations:'Heuristic checks cannot prove an employer or vacancy is genuine or still open.'};
          const draft = {fit_summary:'Synthetic fit',evidence:['Saved résumé quotation'],
            cover_letter:'Synthetic cover letter',honest_gaps:[],quality_report:{version:1,
              disposition:'checks_passed',word_count:3,evidence_count:1,verified_evidence_count:1,
              findings:[],limitations:'Narrow checks do not approve an application.'}};
          const eligibility = {disposition:'review_required',findings:[{
            code:'mandatory_tenure_unverified',reason:'UNTRUSTED REASON MUST NOT RENDER',
            requirement_excerpt:'Must have <img src=x onerror="window.requirementExecuted=true"> 3 years of professional Python experience.'}],
            resume_text:'PRIVATE RESUME MUST NOT RENDER'};
          state.opportunities = [{...base,id:'clean',title:'Software intern',quality,latest_draft:draft,eligibility},
            {...base,id:'flagged',title:'Suspicious fee request',quality:{...quality,
              disposition:'review_required',signals:[{severity:'block',message:'Posting requests an applicant fee or purchase'}]}},
            {...base,id:'yc-role',source:'yc',title:'YC software intern',quality,latest_draft:draft,
              source_url:'https://www.ycombinator.com/companies/synthetic-yc/jobs/abc-intern',
              apply_url:'https://www.ycombinator.com/companies/synthetic-yc/jobs/abc-intern',
              eligibility:{disposition:'no_blocking_requirement',findings:[],requirements:[{excerpt:'Current students may apply.'}]}}];
          state.careerTracking = {applications:[
            {opportunity_id:'clean',profile_id:'mission',company:'Example Labs',title:'Software intern',
              status:'shortlisted',updated_at:new Date().toISOString(),needs_review:true,events:[]},
            {opportunity_id:'interview',profile_id:'mission',company:'Interview Labs',title:'Intern',
              status:'interview',updated_at:new Date().toISOString(),needs_review:true,events:[]},
            {opportunity_id:'offer',profile_id:'mission',company:'Offer Labs',title:'<img src=x> Intern',
              status:'offer',updated_at:new Date().toISOString(),needs_review:true,events:[]}],
            review_candidates:[{profile_id:'mission',subject:'Please confirm your interview',
              suggested_status:'interview',snippet:'Synthetic uncertain match',received_at:new Date().toISOString()}]};
          renderProfileFilter(); renderMissions(); renderOpportunities(); switchView('opportunities');
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
        page.locator("#opportunity-list .opportunity-card").first.get_by_role(
            "button", name="Inspect", exact=True).click()
        assert "Current fit evidence · 89/100" in page.locator("#detail-content").inner_text()
        assert page.get_by_text("Draft evidence checks passed", exact=True).is_visible()
        eligibility = page.locator("#detail-content .career-eligibility")
        assert "Mandatory qualifications · review required" in eligibility.inner_text()
        assert "Explicit résumé evidence does not establish this tenure." in eligibility.inner_text()
        assert '<img src=x onerror="window.requirementExecuted=true">' in eligibility.inner_text()
        assert "PRIVATE RESUME" not in eligibility.inner_text()
        assert "UNTRUSTED REASON" not in eligibility.inner_text()
        assert eligibility.locator("img").count() == 0
        assert page.evaluate("window.requirementExecuted === undefined")
        page.locator("#detail-dialog").evaluate("dialog => dialog.close()")
        page.evaluate("showOpportunity('yc-role')")
        assert "no blocking requirement found" in page.locator("#detail-content .career-eligibility").inner_text()
        assert "YC account applications are not connected" in page.locator("#detail-content").inner_text()
        assert page.locator('#detail-content [data-action="preflight-opportunity"]').count() == 0
        assert page.locator('#detail-content [data-action="plan-opportunity"]').count() == 0
        assert page.get_by_role("link", name="Open official application", exact=True).get_attribute("href").startswith("https://www.ycombinator.com/")
        page.locator("#detail-dialog").evaluate("dialog => dialog.close()")
        page.evaluate("""() => {
          state.tasks = [{kind:'career.search',status:'succeeded',payload:{profile_id:'mission'},
            created_at:new Date().toISOString(),output:{fetched:12,matched:2,sources_attempted:3,
            sources_succeeded:3,filter_counts:{outside_freshness_window:8,location_mismatch:2,matched:2}}}];
          document.querySelector('#career-attention-list').append(careerScanEvidence('mission'));
        }""")
        page.locator("#career-attention-list").get_by_text("Latest search coverage and exclusions", exact=True).click()
        assert page.get_by_text("Outside freshness window: 8", exact=True).is_visible()
        page.evaluate("switchView('missions')")
        assert "YC (manual applications): saved-yc" in page.locator("#mission-list").inner_text()
        assert "India work authorization: unknown." in page.locator("#mission-list").inner_text()
        page.get_by_text("Source connections and current readiness", exact=True).click()
        assert "YC account applications are not connected" in page.locator("#career-readiness").inner_text()
        page.get_by_text("Saved discovery references · 1", exact=True).click()
        assert page.locator("#mission-list").get_by_role("link", name="YC reference 1", exact=True).get_attribute("rel") == "noopener noreferrer"

        # Isolate form persistence from the unrelated multi-service dashboard refresh.
        # The real native submit handler and HTTP POST/PUT requests still run below.
        page.evaluate("loadData = async () => true; openProfileDialog(state.profiles[0])")
        page.locator("#profile-form summary").filter(has_text="Search sources").click()
        assert page.locator('[name="yc_companies"]').input_value() == "saved-yc"
        assert page.locator('[name="india_authorized_without_sponsorship"]').input_value() == ""
        assert page.locator("#career-source-leads").get_by_role("link", name="YC reference 1", exact=True).count() == 1
        page.get_by_label("Employer board or job URL", exact=True).fill(
            "https://jobs.eu.lever.co/synthetic/role")
        page.get_by_role("button", name="Add board from URL", exact=True).click()
        page.get_by_text("Lever board added to this form.", exact=False).wait_for()
        assert page.get_by_label("Lever EU board names or URLs", exact=True).input_value() == "synthetic"
        page.get_by_label("Employer board or job URL", exact=True).fill(
            "https://jobs.smartrecruiters.com/synthetic/role")
        page.get_by_role("button", name="Add board from URL", exact=True).click()
        page.get_by_text("SmartRecruiters board added to this form.", exact=False).wait_for()
        assert page.get_by_label("SmartRecruiters company boards or URLs").input_value() == "synthetic"
        page.get_by_label("Employer board or job URL", exact=True).fill("https://www.linkedin.com/jobs/view/123")
        page.get_by_role("button", name="Add board from URL", exact=True).click()
        page.get_by_text("Open the employer application link first.", exact=True).wait_for()
        assert page.get_by_label("Lever EU board names or URLs", exact=True).input_value() == "synthetic"
        assert page.locator("#career-source-leads li").count() == 1
        page.locator('[name="career_employer_url"]').fill("https://jobs.ashbyhq.com/synthetic/role?ref=linkedin")
        page.get_by_role("button", name="Add board from URL", exact=True).click()
        page.get_by_text("Ashby board added to this form.", exact=False).wait_for()
        assert page.locator("#career-source-leads li").count() == 2
        assert page.locator("#career-source-leads").get_by_role("link", name="LinkedIn reference 2", exact=True).get_attribute("href") == "https://www.linkedin.com/jobs/view/123"
        page.get_by_role("button", name="Add board from URL", exact=True).click()
        page.get_by_text("Ashby board added to this form.", exact=False).wait_for()
        assert page.locator("#career-source-leads li").count() == 2
        assert resolutions[-1]["employer_url"].endswith("?ref=linkedin")
        page.locator('[name="career_employer_url"]').fill("")
        page.get_by_label("Employer board or job URL", exact=True).fill("https://www.ycombinator.com/companies/synthetic-yc/jobs")
        page.get_by_role("button", name="Add board from URL", exact=True).click()
        page.get_by_text("YC company added to this form.", exact=False).wait_for()
        assert page.locator('[name="yc_companies"]').input_value() == "saved-yc, synthetic-yc"
        assert page.locator("#career-source-leads li").count() == 2
        assert len(resolutions) == 6
        page.locator("#profile-form summary").filter(has_text="Application details").click()
        india = page.locator('[name="india_authorized_without_sponsorship"]')
        india.select_option("true")

        # One bounded screenshot pass covers the changed controls at both sizes.
        for label, viewport in (("desktop", {"width": 1440, "height": 1080}),
                                ("mobile", {"width": 390, "height": 844})):
            page.set_viewport_size(viewport)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert page.locator("#profile-dialog").evaluate("dialog => dialog.scrollWidth <= dialog.clientWidth")
            for surface, selector in (("sources", '[name="career_source_url"]'),
                                      ("yc", '[name="yc_companies"]'),
                                      ("authorization", '[name="india_authorized_without_sponsorship"]')):
                page.locator(selector).scroll_into_view_if_needed()
                page.screenshot(path=f"/proof/career-{surface}-{label}.png", full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1080})
        page.get_by_role("button", name="Save mission", exact=True).click()
        page.wait_for_function("!document.querySelector('#profile-dialog').open")
        saved = profile_writes[-1]["payload"]
        assert profile_writes[-1]["method"] == "PUT"
        assert saved["eligibility_facts"]["india_authorized_without_sponsorship"] is True
        assert saved["source_config"]["yc_companies"] == ["saved-yc", "synthetic-yc"]
        assert saved["source_config"]["ashby_boards"] == ["saved-board", "synthetic"]
        assert saved["source_config"]["discovery_leads"] == [
            {"platform": "yc", "source_url": "https://www.ycombinator.com/companies/saved-yc/jobs/abc-intern",
             "employer_url": "https://jobs.ashbyhq.com/saved-board/role"},
            {"platform": "linkedin", "source_url": "https://www.linkedin.com/jobs/view/123",
             "employer_url": "https://jobs.ashbyhq.com/synthetic/role"},
        ]
        page.evaluate("payload => {state.profiles[0] = {...state.profiles[0], ...payload}; openProfileDialog(state.profiles[0]);}", saved)
        assert india.input_value() == "true"
        page.get_by_role("button", name="Remove LinkedIn reference 2", exact=True).click()
        assert page.locator('[name="ashby_boards"]').input_value() == "saved-board, synthetic"
        assert page.locator("#career-source-leads li").count() == 1
        india.select_option("false")
        page.get_by_role("button", name="Save mission", exact=True).click()
        page.wait_for_function("!document.querySelector('#profile-dialog').open")
        assert profile_writes[-1]["payload"]["eligibility_facts"]["india_authorized_without_sponsorship"] is False
        assert len(profile_writes[-1]["payload"]["source_config"]["discovery_leads"]) == 1

        # New and older profiles must retain Unknown unless the user supplies a fact.
        page.evaluate("openProfileDialog()")
        assert india.input_value() == ""
        page.get_by_label("Mission name", exact=True).fill("Synthetic new mission")
        page.get_by_label("Your name", exact=True).fill("Example Candidate")
        page.locator('[name="desired_titles"]').fill("Software intern")
        page.get_by_role("button", name="Save mission", exact=True).click()
        page.wait_for_function("!document.querySelector('#profile-dialog').open")
        assert profile_writes[-1]["method"] == "POST"
        assert profile_writes[-1]["payload"]["eligibility_facts"]["india_authorized_without_sponsorship"] is None
        assert profile_writes[-1]["payload"]["source_config"]["discovery_leads"] == []
        page.evaluate("showOpportunity('clean')")
        for label, viewport in (("desktop", {"width": 1440, "height": 1080}),
                                ("mobile", {"width": 390, "height": 844})):
            page.set_viewport_size(viewport)
            page.locator("#detail-content .career-eligibility").scroll_into_view_if_needed()
            assert page.locator("#detail-dialog").evaluate("dialog => dialog.scrollWidth <= dialog.clientWidth")
            page.screenshot(path=f"/proof/career-decisions-{label}.png", full_page=True)
        page.locator("#detail-dialog").evaluate("dialog => dialog.close()")
        page.set_viewport_size({"width": 1440, "height": 1080})
        page.evaluate("showApplicationAnswers('clean',[{key:'consent:0',type:'checkbox',label:'Email consent'}])")
        boolean = page.get_by_label("Email consent", exact=True)
        assert boolean.input_value() == ""
        boolean.select_option("false")
        assert boolean.get_attribute("data-boolean-answer") == "true"
        page.locator("#application-answer-dialog").evaluate("dialog => dialog.close()")
        page.evaluate("showApplicationAnswers('clean',[{key:'file:0',type:'file',label:'Proof of identity',reason:'Requires your document'}])")
        assert page.get_by_role("button", name="Prepare exact packet", exact=True).is_disabled()
        assert not errors, errors
        browser.close()
    print("CAREER_UI_OK: outcomes, escaped eligibility, fit/draft evidence, scan exclusions, typed answers, mobile, paired imports, YC manual status, saved-reference preservation, tri-state authorization")


if __name__ == "__main__":
    main()
