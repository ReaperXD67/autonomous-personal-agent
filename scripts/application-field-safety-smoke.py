#!/usr/bin/env python3
"""Exercise actual browser form inspection/submission using synthetic route fixtures.

Run in the existing action-worker image with network=none and the current
control-api source at /source. No account, provider or model is contacted.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlparse

from app.application_browser import (
    BrowserActionError,
    inspect_application_form,
    resolve_application_fields,
    submit_application_form,
)
from playwright.sync_api import Page

IDENTITY = {"first_name": "Synthetic", "last_name": "Applicant", "email": "person@example.test"}
ORIGIN = "http://application-fixture:8081"
FORM = """<!doctype html><html><body><form id="application">
<label>Email<input name="email" type="email" required></label>
<label>Resume<input name="resume" type="file" accept="application/pdf" required></label>
<label>Receive hiring email<input name="marketing" type="checkbox" {checked}></label>
<label>Available yes<input name="availability" type="radio" value="yes" checked required></label>
<label>Available no<input name="availability" type="radio" value="no" required></label>
<button type="submit">Submit application</button></form><script>
document.querySelector('form').addEventListener('submit', async event => {{
 event.preventDefault(); const form = event.currentTarget;
 const resume = form.querySelector('[name=resume]').files[0];
 await fetch('/capture', {{method:'POST', headers:{{'Content-Type':'application/json'}},
  body:JSON.stringify({{email:form.querySelector('[name=email]').value,
   marketing:form.querySelector('[name=marketing]').checked,
   availableYes:form.querySelector('[value=yes]').checked,
   availableNo:form.querySelector('[value=no]').checked,
   resumeName:resume.name,resumeType:resume.type,resumeSize:resume.size}})}});
 document.body.textContent = 'Application received';
}});</script></body></html>"""
DOCUMENT_FORM = """<!doctype html><html><body><form>
<label>Email<input name="email" type="email" required></label>
<label>Proof of work authorization<input name="passport" type="file" required></label>
<button type="submit">Submit application</button></form></body></html>"""


def check(value, message):
    if not value:
        raise AssertionError(message)


def main():
    captured, receipts, requests = [], [], []
    changed_default = [False]
    original_route = Page.route

    def register_route(page, pattern, handler, *args, **kwargs):
        class FixtureRoute:
            def __init__(self, route):
                self._route = route
                self.request = route.request

            def abort(self, *abort_args, **abort_kwargs):
                return self._route.abort(*abort_args, **abort_kwargs)

            def continue_(self, **_overrides):
                # Production's same-host policy chooses whether this method runs.
                # Only its allowed request is answered from an in-memory fixture.
                parsed = urlparse(self.request.url)
                check(parsed.hostname == "application-fixture", "Unexpected fixture host")
                requests.append((self.request.method, parsed.path))
                if parsed.path == "/capture":
                    captured.append(self.request.post_data_json)
                    self._route.fulfill(content_type="application/json", body="{}")
                elif parsed.path == "/unknown-document":
                    self._route.fulfill(content_type="text/html", body=DOCUMENT_FORM)
                else:
                    checked = parsed.path != "/changed-default" or changed_default[0]
                    self._route.fulfill(content_type="text/html", body=FORM.format(
                        checked="checked" if checked else "",
                    ))

        return original_route(page, pattern, lambda route: handler(FixtureRoute(route)),
                              *args, **kwargs)

    def inspect(path):
        preflight = inspect_application_form(ORIGIN + path, "test")
        check(preflight["blocked_reason"] is None, "Fixture inspection unexpectedly blocked")
        return preflight

    def submit(preflight, values):
        with TemporaryDirectory() as temporary:
            return submit_application_form(
                url=preflight["apply_url"], environment="test",
                expected_signature=preflight["form_signature"],
                expected_submit_label=preflight["submit_label"], values=values,
                resume_text="Synthetic Applicant. Python engineering project.",
                candidate_name="Synthetic Applicant", temp_directory=Path(temporary),
                begin_side_effect=lambda: receipts.append("synthetic-receipt"),
            )

    def blocked(preflight, values):
        count = len(receipts)
        try:
            submit(preflight, values)
        except BrowserActionError:
            pass
        else:
            raise AssertionError("Unreviewed fixture reached submission")
        check(len(receipts) == count, "Refused form acquired a side-effect receipt")

    with patch.object(Page, "route", register_route):
        unknown = inspect("/unknown-document")
        values, missing = resolve_application_fields(unknown["fields"], IDENTITY, "Cover", {})
        check(missing and missing[0]["type"] == "file", "Unknown document was auto-resolved")
        forged = {**values, missing[0]["key"]: "__RESUME_PDF__"}
        blocked(unknown, forged)
        check(not captured, "Unknown document caused a form submission")

        reviewed = inspect("/reviewed-controls")
        by_label = {field["label"]: field for field in reviewed["fields"]}
        check(by_label["Receive hiring email"]["checked"], "Default consent was not inspected")
        values, missing = resolve_application_fields(reviewed["fields"], IDENTITY, "Cover", {})
        check(any(field["key"] == by_label["Receive hiring email"]["key"] for field in missing),
              "Default-checked optional consent did not require review")
        blocked(reviewed, values)

        answers = {by_label["Receive hiring email"]["key"]: False,
                   by_label["Available yes"]["key"]: False,
                   by_label["Available no"]["key"]: True}
        values, missing = resolve_application_fields(
            reviewed["fields"], IDENTITY, "Cover", answers,
        )
        check(not missing, "Explicit typed control choices were not accepted")
        result = submit(reviewed, values)
        check(result["confirmation_detected"], "Synthetic form did not confirm receipt")
        check(len(captured) == len(receipts) == 1, "Synthetic submission was duplicated")
        packet = captured[0]
        check(packet["email"] == IDENTITY["email"], "Identity did not reach synthetic form")
        check(packet["marketing"] is False, "Explicit opt-out became consent")
        check(packet["availableYes"] is False and packet["availableNo"] is True,
              "Initially checked radio was not replaced by the exact selected option")
        check(packet["resumeName"] == "resume.pdf" and packet["resumeType"] == "application/pdf"
              and packet["resumeSize"] > 100, "A real synthetic resume PDF was not attached")

        before_change = inspect("/changed-default")
        changed_default[0] = True
        blocked(before_change, values)
        check(len(captured) == len(receipts) == 1, "Changed default consent reached submission")
        check(all(path in {"/capture", "/unknown-document", "/reviewed-controls", "/changed-default"}
                  for _method, path in requests), "Unexpected browser request")

    print("APPLICATION_FIELD_SAFETY_OK: real browser blocks unknown files/default consent, "
          "preserves explicit opt-out/radio choice, attaches synthetic PDF and fences form changes; "
          "network disabled, no real account, provider, model or application")


if __name__ == "__main__":
    main()
