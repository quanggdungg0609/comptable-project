import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.infrastructure.rules.rustfs_rules_manager import RustfsRulesManager

BUCKET = "excel-cr"
RULES_KEY = "config/rules.json"

DEFAULT_RULES ={
    "llm_confirmed": [],
    "keyword": [],
    "direct":[]
}

@pytest.mark.asyncio
async def test_load_returns_default_rules_when_not_found():
    storage = MagicMock()
    storage.download_file = AsyncMock(side_effect=Exception("NoSuchKey"))
    mgr = RustfsRulesManager(storage, BUCKET)
    rules = await mgr.load()
    assert rules == DEFAULT_RULES

@pytest.mark.asyncio
async def test_load_returns_stored_rules():
    stored = {"llm_confirmed": [{"dien_giai": "foo", "chi_tieu": "bar"}], "keyword": [], "direct": []}
    storage = MagicMock()
    storage.download_file = AsyncMock(return_value=json.dumps(stored).encode())
    mgr = RustfsRulesManager(storage, BUCKET)
    rules = await mgr.load()
    assert rules["llm_confirmed"][0]["dien_giai"] == "foo"

@pytest.mark.asyncio
async def test_save_uploads_json():
    storage = MagicMock()
    storage.upload_file = AsyncMock(return_value=RULES_KEY)
    mgr = RustfsRulesManager(storage, BUCKET)
    rules = {"llm_confirmed": [], "keyword": [], "direct": []}
    await mgr.save(rules)
    storage.upload_file.assert_called_once()
    call_args = storage.upload_file.call_args
    assert call_args[0][0] == BUCKET
    assert call_args[0][1] == RULES_KEY
    saved = json.loads(call_args[0][2])
    assert saved == rules