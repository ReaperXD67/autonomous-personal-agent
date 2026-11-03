from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.creator_draft_models import CreatorDraftCreate


@pytest.mark.parametrize("mode", ["remote", "http://example.test", True, None, "LOCAL_ONLY"])
def test_draft_route_cannot_supply_provider_or_endpoint(mode):
    with pytest.raises(ValidationError):
        CreatorDraftCreate(actor="operator", idempotency_key=uuid4(), inference_mode=mode)


def test_legacy_request_retains_automatic_routing():
    assert CreatorDraftCreate(actor="operator", idempotency_key=uuid4()).inference_mode == "auto"
