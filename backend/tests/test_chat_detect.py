import pytest

from app.services.site_crawl import detect_chat


def test_ecw_chatbot_inline_loader_is_detected():
    # Real loader snippet from msintegrative.com: widget injected by an inline script.
    html = "}(window, document, 'script', 'api','https://chatbot.ecwcloud.com/cbfrontend/chat-bot.js'));"
    assert detect_chat(html.lower()) == "eClinicalWorks chat"


def test_unknown_vendor_with_chat_script_gets_generic_label():
    assert (
        detect_chat('<script src="https://x.example/acme-chatbot.js">')
        == "Chat widget (unidentified)"
    )


def test_no_chat_returns_none():
    assert detect_chat("<html><body>hello</body></html>") is None


def test_widget_built_by_javascript_is_found_in_rendered_html():
    from app.services.site_crawl import detect_chat_rendered

    rendered = '<body><iframe id="x" title="Chat with us" src="https://a.example/frame"></iframe>'
    assert detect_chat(rendered.lower()) is None  # the raw-HTML check alone misses it
    assert detect_chat_rendered(rendered) == "Chat widget (unidentified)"
    assert (
        detect_chat_rendered('<div id="launcher-frame"></div>')
        == "Chat widget (unidentified)"
    )
    assert detect_chat_rendered("<p>We chat with patients daily</p>") is None


@pytest.mark.anyio
async def test_rendered_check_fills_a_missing_widget_and_skips_when_found(monkeypatch):
    from app.api.v1 import research
    from app.services import site_crawl

    calls = []

    async def fake(_http, url):
        calls.append(url)
        return '<iframe title="chat" src="https://a.example"></iframe>'

    monkeypatch.setattr(site_crawl, "scrape_rendered", fake)
    monkeypatch.setattr(research.settings, "FIRECRAWL_API_KEY", "k")
    missing = {"convert": {"chat_widget": None}}
    await research._rendered_chat(None, missing, "https://x.example")
    assert missing["convert"]["chat_widget"] == "Chat widget (unidentified)"
    found = {"convert": {"chat_widget": "Podium"}}
    await research._rendered_chat(None, found, "https://x.example")
    assert found["convert"]["chat_widget"] == "Podium" and calls == [
        "https://x.example"
    ]


def test_vendor_markers_are_lower_case_and_unique_enough():
    from app.services.constants import CHAT

    # detect_chat matches against lower-cased HTML, so an upper-case marker could never hit.
    assert all(m == m.lower() and len(m) >= 5 for m in CHAT)
    assert len(CHAT) >= 30


def test_a_few_vendors_from_the_expanded_list():
    for html, name in [
        ("<script src='https://client.crisp.chat/l.js'>", "Crisp"),
        ("<script src='https://js.driftt.com/include/x.js'>", "Drift"),
        ("<script src='https://wchat.freshchat.com/js/widget.js'>", "Freshchat"),
        ("<script src='https://cdn.botpress.cloud/webchat/v1/inject.js'>", "Botpress"),
    ]:
        assert detect_chat(html.lower()) == name
