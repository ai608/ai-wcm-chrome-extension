"""Full AI visibility report: the job, with an in-memory repository and a fake OpenRouter.

The judge (one LLM call per answer, as in the POC) is faked by `reader`, which behaves like a
language model that reads names loosely ("and" for "&"). The tests check what the app does with
the judge's JSON, not the judge's intelligence."""

import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services import ai_report as ar
from app.services import ai_visibility as av

pytestmark = pytest.mark.anyio

GLOW = "Glow Aesthetics Med Spa"
AUDIT: dict[str, Any] = {
    "domain": "glowmedspa.com",
    "site": {
        "services": {"clusters": [{"service": "Botox (injectables)", "found": 2}]}
    },
    "business": {
        "gbp": {
            "name": GLOW,
            "address": "1 Main St, Austin, TX 78701",
            "category": "Med spa",
        },
        "nap": {"name": None},
    },
    "research": {
        "local_competitors": {
            "state": "ready",
            "data": {
                "items": [
                    {
                        "name": "Revive Medical Spa",
                        "website": "https://revivemedspa.com",
                        "is_this_business": False,
                    },
                    {
                        "name": "Skin Lab Austin",
                        "website": None,
                        "is_this_business": False,
                    },
                ]
            },
        }
    },
}
NO_LOCAL = {**AUDIT, "research": {}}
RANKED = f"Top picks:\n1. Revive Medical Spa - great\n2. {GLOW} - friendly\n3. Skin Lab Austin"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "sk-secret-key")
    monkeypatch.setattr(settings, "SCRIPT_MODEL", "judge/model")
    monkeypatch.setattr(
        settings, "AI_VISIBILITY_JUDGE_MODEL", "judge/model"
    )  # not the real .env value
    monkeypatch.setattr(
        settings, "AI_VISIBILITY_MODELS", "ChatGPT=openai/gpt-x,Gemini=google/gem"
    )
    monkeypatch.setattr(settings, "AI_VISIBILITY_FULL_PROMPTS", 12)
    monkeypatch.setattr(settings, "AI_VISIBILITY_FULL_RUNS", 3)
    monkeypatch.setattr(av, "RETRY_DELAY_S", 0)
    monkeypatch.setattr(ar, "PROGRESS_EVERY_S", 0)


class FakeRepo:
    """Just the repository methods the job uses, in memory."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.run: dict[str, Any] = {
            "id": "r1",
            "audit_id": "a1",
            "requested_by": "u1",
            "status": "running",
            "kind": "full",
            "config": cfg,
            "created_at": datetime.now(UTC),
        }
        self.answers: dict[tuple[int, str, int], dict[str, Any]] = {}
        self.saved: dict[str, Any] = {}

    async def get_ai_run(self, run_id: str) -> dict[str, Any]:
        return self.run

    async def patch_ai_config(self, run_id: str, patch: dict[str, Any]) -> None:
        self.run["config"].update(patch)

    async def save_ai_run(self, run_id: str, **kw: Any) -> None:
        self.saved.update({k: v for k, v in kw.items() if v is not None})
        if kw.get("status"):
            self.run["status"] = kw["status"]

    async def ai_answer_keys(self, run_id: str) -> set[tuple[int, str, int]]:
        return set(self.answers)

    async def save_ai_answer(
        self, run_id: str, p: int, engine: str, r: int, **kw: Any
    ) -> None:
        self.answers.setdefault(
            (p, engine, r),
            {
                "prompt_idx": p,
                "engine": engine,
                "run_no": r,
                "status": "failed" if kw.get("error") else "ok",
                "text": kw.get("text"),
                "urls": kw.get("urls") or [],
                "error": kw.get("error"),
                "tokens": kw.get("tokens", 0),
                "prompt_tokens": kw.get("prompt_tokens", 0),
                "completion_tokens": kw.get("completion_tokens", 0),
                "cost_micro": kw.get("cost_micro", 0),
                "facts": None,
                "judge_tokens": 0,
                "judge_cost_micro": 0,
            },
        )

    async def save_ai_facts(
        self,
        run_id: str,
        p: int,
        engine: str,
        r: int,
        facts: dict[str, Any],
        jt: int = 0,
        jc: int = 0,
    ) -> None:
        self.answers[(p, engine, r)].update(
            facts=facts, judge_tokens=jt, judge_cost_micro=jc
        )

    def _sorted(self) -> list[dict[str, Any]]:
        return sorted(
            self.answers.values(),
            key=lambda a: (a["prompt_idx"], a["engine"], a["run_no"]),
        )

    async def ai_answers_for_log(self, run_id: str) -> list[dict[str, Any]]:
        return [
            {**a, "text": a["text"] or "", "urls": a["urls"] or []}
            for a in self._sorted()
        ]

    async def ai_answers_to_read(self, run_id: str) -> list[dict[str, Any]]:
        # same rule as the SQL: not read yet, or a read that failed (tried again)
        return [
            {**a, "text": a["text"] or ""}
            for a in self._sorted()
            if a["status"] == "ok"
            and (a["facts"] is None or a["facts"].get("judge_failed"))
        ]

    async def ai_answer_texts(
        self, run_id: str, *, limit: int = 0
    ) -> list[dict[str, Any]]:
        return [a for a in self._sorted() if a["status"] == "ok"]

    async def ai_answer_summary(self, run_id: str) -> list[dict[str, Any]]:
        return self._sorted()


def signals(mentioned: bool, **over: Any) -> dict[str, Any]:
    base = {
        "mentioned": mentioned,
        "occurrences": 1 if mentioned else 0,
        "list_rank": 2 if mentioned else None,
        "first_position": 0.2 if mentioned else None,
        "cited": False,
        "sentiment": 0.8 if mentioned else 0.0,
        "is_primary_recommendation": False,
        "note": "named",
    }
    return {**base, **over}


def reader(req: dict[str, Any]) -> dict[str, Any]:
    """A stand-in for the judge model: finds each TARGET_BRAND in the response, reading "&" as
    "and", and also names the one unlisted business it sees ("Lumi Spa")."""
    text = req["response"].lower().replace("&", "and")
    out = {}
    for name in req["brands"]:
        out[name] = signals(name.lower().replace("&", "and") in text)
    if "lumi spa" in text:
        out["Lumi Spa"] = signals(True, list_rank=1)
    return {"brands": out, "response_is_ranked_list": True}


def parse_judge_request(body: dict[str, Any]) -> dict[str, Any]:
    user = body["messages"][1]["content"]
    m = re.match(
        r"PROMPT:\n(.*?)\n\nRESPONSE:\n(.*?)\n\nTARGET_BRANDS: (\[.*?\])(?:\n\nSOURCES:\n(.*))?$",
        user,
        re.DOTALL,
    )
    assert m, user[:200]
    return {
        "prompt": m.group(1),
        "response": m.group(2),
        "brands": json.loads(m.group(3)),
        "sources": (m.group(4) or "").splitlines(),
    }


class Provider:
    """Fake OpenRouter. Answer calls and JSON calls are told apart by `response_format`."""

    def __init__(
        self, answer: Any = RANKED, judge: Any = reader, fail_engine: str | None = None
    ) -> None:
        self.answer, self.judge, self.fail_engine = answer, judge, fail_engine
        self.asks: list[str] = []
        self.json_calls: list[str] = []
        self.judge_requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "response_format" in body:
            system = body["messages"][0]["content"]
            kind = (
                "judge"
                if "strict information-extraction engine" in system
                else "names"
                if "list the names" in system
                else "writer"
            )
            self.json_calls.append(kind)
            if kind == "judge":
                req = parse_judge_request(body)
                self.judge_requests.append(
                    {**req, "system": system, "model": body["model"]}
                )
                out: Any = self.judge(req)
            elif kind == "names":
                out = {"names": {"0": ["Lumi Spa"], "1": ["Lumi Spa", "Bella Skin"]}}
            else:
                out = {
                    "prompts": [
                        "best botox in Austin",
                        f"{GLOW} botox",
                        "top med spa near Austin",
                    ]
                }
            content = out if isinstance(out, str) else json.dumps(out)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": content}}
                    ],
                    "usage": {
                        "total_tokens": 10,
                        "prompt_tokens": 6,
                        "completion_tokens": 4,
                        "cost": 0.0002,
                    },
                },
            )
        self.asks.append(body["model"])
        if self.fail_engine and self.fail_engine in body["model"]:
            return httpx.Response(400, json={"error": "no"})
        text = self.answer(body) if callable(self.answer) else self.answer
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": text}}],
                "usage": {
                    "total_tokens": 100,
                    "prompt_tokens": 40,
                    "completion_tokens": 60,
                    "cost": 0.001,
                },
            },
        )


def config(**over: Any) -> dict[str, Any]:
    base = {
        "n_prompts": 2,
        "runs": 2,
        "calls": 8,
        "engines": [
            {"label": "ChatGPT", "model": "openai/gpt-x"},
            {"label": "Gemini", "model": "google/gem"},
        ],
        "budget_micro": 3_000_000,
        "prompts": ["best botox in Austin", "top med spa near Austin"],
        "prompts_source": "user",
        "prompt_version": 1,
        "scoring_version": 1,
    }
    return {**base, **over}


async def go(repo: FakeRepo, provider: Provider, audit: dict[str, Any] = AUDIT) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        await ar.run_job(repo, http, "r1", audit)  # type: ignore[arg-type]


# ── the judge prompt is the POC's ─────────────────────────────────────────────────────────


def test_the_judge_prompt_is_the_pocs_text_with_only_additions_after_it():
    s = ar.JUDGE_SYSTEM
    # the POC's judge.md, line for line
    assert s.startswith(
        "You are a strict information-extraction engine for AI brand-visibility analysis."
    )
    for line in (
        "(1) the original user PROMPT, (2) an AI assistant's RESPONSE, and (3) a list of TARGET_BRANDS (target + known competitors).",
        "Extract structured facts about EACH brand mentioned in the text, prioritizing TARGET_BRANDS but including any other competing companies or products mentioned. Do not infer beyond the text. Count only explicit mentions.",
        "- mentioned: true/false",
        "- occurrences: integer count of distinct mentions",
        "- list_rank: if the response is an ordered/numbered ranking and the brand appears in it, its 1-based position; otherwise null",
        "- first_position: the position of the brand's FIRST mention as a fraction of total length in [0,1] (0 = very beginning)",
        "- cited: true if the response includes a citation, link, or URL pointing to THIS brand's website/domain; else false",
        "- sentiment: a number in [-1,1] describing how the brand is framed (-1 strongly negative, 0 neutral/factual, +1 strongly positive/recommended)",
        "- is_primary_recommendation: true if this brand is presented as the top / first / main pick",
        "- note: <=15 word justification",
        "- response_is_ranked_list: true/false",
    ):
        assert line in s, line
    assert s.startswith(ar.POC_JUDGE_PROMPT) and s.endswith(ar.JUDGE_RULES)


def test_no_name_matching_is_left_in_the_report_code():
    for gone in ("read_brand", "list_rank", "name_pattern", "judge_sentiment", "Brand"):
        assert not hasattr(ar, gone), gone


# ── pure helpers ──────────────────────────────────────────────────────────────────────────


def test_canon_files_spellings_of_one_name_together_but_keeps_different_businesses_apart():
    same = [
        "Renew Health & Hormones",
        "Renew Health and Hormones",
        "renew health  AND hormones",
        "Renew-Health & Hormones",
    ]
    assert len({ar.canon(n) for n in same}) == 1
    assert ar.canon("Elevè Premier Health") == ar.canon("Eleve Premier Health")
    assert ar.canon("Dr. Smith's Clinic") == ar.canon("Dr Smiths Clinic")
    assert ar.canon("Sonoran Skin Renewal") != ar.canon("Renew Health & Hormones")
    assert ar.canon("Skindale Medspa") == ar.canon(
        "Skindale Med Spa"
    )  # spacing does not matter
    assert ar.canon("Skindale Med Spa") != ar.canon(
        "Skindale Wellness"
    )  # but a different name does


def test_sentiment_uses_the_pocs_thresholds():
    for raw, want in [
        (0.31, 1.0),
        (0.3, 0.0),
        (0.0, 0.0),
        (-0.3, 0.0),
        (-0.31, -1.0),
        (1, 1.0),
        (None, 0.0),
        ("positive", 1.0),
        ("Strongly negative", -1.0),
        ("meh", 0.0),
        (True, 1.0),
    ]:
        assert ar.sentiment_value(raw) == want, raw


def test_clean_signals_keeps_every_number_in_range_and_ignores_loose_booleans():
    f = ar.clean_signals(
        {
            "mentioned": True,
            "occurrences": -4,
            "list_rank": 0,
            "first_position": 1.7,
            "cited": "true",
            "sentiment": -3,
            "is_primary_recommendation": 1,
            "note": "x" * 500,
        }
    )
    assert f["occurrences"] == 1  # mentioned at least once
    assert (
        f["list_rank"] is None and f["first_position"] == 1.0 and f["sentiment"] == -1.0
    )
    assert f["cited"] is False and f["is_primary"] is False and "note" not in f
    gone = ar.clean_signals(
        {
            "mentioned": False,
            "occurrences": 5,
            "list_rank": 2,
            "first_position": 0.1,
            "sentiment": 1,
        }
    )
    assert (
        gone["occurrences"],
        gone["list_rank"],
        gone["first_position"],
        gone["sentiment"],
    ) == (0, None, None, 0.0)
    assert (
        ar.clean_signals({"mentioned": True, "list_rank": "2"})["list_rank"] is None
    )  # text is not a rank


def test_judge_output_is_filed_under_the_tracked_name_and_other_brands_are_capped():
    names = ["Renew Health & Hormones", "Revive Medical Spa"]
    out = {
        "brands": {
            "Renew Health and Hormones": signals(True),
            "Revive Medical Spa": signals(False),
            **{f"Other {i}": signals(True) for i in range(20)},
            "other 3": signals(True),  # the same business again
            "x" * 90: signals(True),
            "Bad": "not an object",
        },
        "response_is_ranked_list": True,
    }
    facts = ar.read_judge_output(out, names)
    assert list(facts["brands"])[:2] == [
        "Renew Health & Hormones",
        "Revive Medical Spa",
    ]
    assert facts["brands"]["Renew Health & Hormones"]["mentioned"] is True
    others = [k for k in facts["brands"] if k not in names]
    assert len(others) == ar.MAX_OTHER_BRANDS and facts["ranked"] is True
    with pytest.raises(TypeError):
        ar.read_judge_output(
            {"nothing": 1}, names
        )  # no brands object: a failed read, not "nobody"


def test_the_tracked_list_is_the_clinic_then_its_competitors_without_repeats():
    t = av.build_target(AUDIT)
    assert ar.brand_names(t, []) == [GLOW, "Revive Medical Spa", "Skin Lab Austin"]
    none = av.build_target(NO_LOCAL)
    assert ar.brand_names(
        none, ["Lumi Spa", "glow aesthetics med spa", "Lumi  Spa"]
    ) == [GLOW, "Lumi Spa"]


async def test_the_judge_is_asked_the_way_the_poc_asks_it():
    prov = Provider()
    async with httpx.AsyncClient(transport=httpx.MockTransport(prov)) as http:
        usage: dict[str, Any] = {}
        facts = await ar.judge_answer(
            http,
            "best botox in Austin",
            RANKED,
            ["https://a.example/x"],
            [GLOW, "Skin Lab Austin"],
            usage,
        )
    req = prov.judge_requests[0]
    assert req["prompt"] == "best botox in Austin" and req["response"] == RANKED
    assert req["brands"] == [GLOW, "Skin Lab Austin"] and req["sources"] == [
        "- https://a.example/x"
    ]
    assert req["model"] == "judge/model" and req["system"] == ar.JUDGE_SYSTEM
    assert facts["brands"][GLOW]["mentioned"] and usage["cost_micro"] == 200


def test_questions_naming_the_clinic_are_dropped_and_templates_fill_the_gap():
    t = av.build_target(AUDIT)
    got = ar.clean_prompts(
        ["best botox in Austin", f"{GLOW} reviews", "x", 7, "best botox in austin"],
        t,
        5,
    )
    assert got == ["best botox in Austin"]
    ctx = ar.context(AUDIT)
    assert ctx["city"] == "Austin, TX" and ctx["services"] == ["botox"]
    fb = ar.fallback_prompts(ctx, 6)
    assert len(fb) == 6 and all("Austin, TX" in p for p in fb) and len(set(fb)) == 6


def test_plan_is_clamped_to_the_env_and_counts_calls():
    p = ar.plan(50, 9)
    assert (p["n_prompts"], p["runs"], p["calls"]) == (12, 3, 12 * 2 * 3)


# ── the job ───────────────────────────────────────────────────────────────────────────────


async def test_full_run_asks_the_judge_once_per_answer_and_scores_it():
    repo, prov = FakeRepo(config()), Provider()
    await go(repo, prov)
    assert repo.run["status"] == "ready" and len(prov.asks) == 8
    assert prov.json_calls.count("judge") == 8  # every answer, as in the POC
    assert all(a["facts"]["brands"] for a in repo.answers.values())
    data = repo.saved["data"]
    rep = data["report"]
    assert (
        rep["mention_rate"]["k"] == 8
        and rep["mention_rate"]["n"] == 8
        and rep["visibility_index"] > 0
    )
    assert data["quality"]["success_rate"] == 1 and data["quality"]["read"] == 8
    assert [e["engine"] for e in data["engines"]] == ["ChatGPT", "Gemini"]
    assert (
        data["usage"]["cost_usd"] == pytest.approx(0.0096)
        and repo.saved["cost_micro"] == 9600
    )  # 8 answers + 8 judge calls
    assert [e["id"] for e in data["log"]][-2:] == ["usage", "final"]


async def test_and_for_ampersand_is_the_same_clinic_end_to_end():
    audit = {
        **AUDIT,
        "business": {
            "gbp": {
                "name": "Renew Health & Hormones",
                "address": "1 A St, Mesa, AZ 85201",
                "category": "clinic",
            },
            "nap": {},
        },
    }
    seen = {}

    def judge(req: dict[str, Any]) -> dict[str, Any]:
        # the model writes the name the way the answer wrote it, not the way it was given
        seen["brands"] = req["brands"]
        return {
            "brands": {"Renew Health and Hormones": signals(True)},
            "response_is_ranked_list": False,
        }

    repo = FakeRepo(config())
    await go(
        repo,
        Provider(answer="Try Renew Health and Hormones for TRT.", judge=judge),
        audit,
    )
    assert seen["brands"][0] == "Renew Health & Hormones"
    rep = repo.saved["data"]["report"]
    assert (rep["mention_rate"]["k"], rep["mention_rate"]["n"]) == (8, 8)
    assert rep["leaderboard"][0] == "Renew Health & Hormones"


async def test_businesses_the_judge_finds_join_the_ranking_the_pocs_dynamic_brands():
    repo = FakeRepo(config())
    await go(repo, Provider(answer=f"Try Lumi Spa first, then {GLOW}."))
    rep = repo.saved["data"]["report"]
    assert "Lumi Spa" in rep["share_of_voice"] and "Lumi Spa" in rep["leaderboard"]
    assert rep["share_of_voice"]["Lumi Spa"] == pytest.approx(
        0.5
    )  # of two named brands, one is Lumi
    assert "Lumi Spa" in repo.saved["data"]["competitors"]["names"]
    # a tracked competitor nobody named stays in the list with no share
    assert rep["share_of_voice"]["Revive Medical Spa"] == 0


async def test_only_the_most_named_other_brands_are_kept():
    def judge(req: dict[str, Any]) -> dict[str, Any]:
        brands = {n: signals(False) for n in req["brands"]}
        for i in range(10):
            brands[f"Hot {i}"] = signals(True)  # named in every answer
        brands["Cold 0"] = signals(
            req["prompt"].startswith("best")
        )  # named in half of them
        brands["Cold 5"] = signals(False)  # never named
        return {"brands": brands, "response_is_ranked_list": False}

    repo = FakeRepo(config())
    await go(repo, Provider(judge=judge))
    names = repo.saved["data"]["competitors"]["names"]
    extra = [n for n in names if n not in ("Revive Medical Spa", "Skin Lab Austin")]
    assert len(extra) == 11 and all(n.startswith("Hot") or n == "Cold 0" for n in extra)
    assert "Cold 5" not in names  # never named: not in the report
    # the cap itself: more named brands than the report keeps
    assert ar.MAX_DYNAMIC_BRANDS == 12


async def test_a_brand_the_judge_leaves_out_counts_as_not_named_not_as_missing_data():
    def judge(req: dict[str, Any]) -> dict[str, Any]:
        return {
            "brands": {"Skin Lab Austin": signals(True)},
            "response_is_ranked_list": False,
        }  # no clinic, no Revive

    repo = FakeRepo(config())
    await go(repo, Provider(judge=judge))
    rep = repo.saved["data"]["report"]
    assert rep["mention_rate"]["k"] == 0 and rep["mention_rate"]["n"] == 8
    assert (
        rep["per_brand"][GLOW]["VI"] == 0
        and rep["share_of_voice"]["Skin Lab Austin"] == 1.0
    )


async def test_sentiment_is_turned_into_positive_neutral_negative_like_the_poc():
    async def vi(sentiment: float) -> float:
        def judge(req: dict[str, Any]) -> dict[str, Any]:
            return {
                "brands": {GLOW: signals(True, sentiment=sentiment)},
                "response_is_ranked_list": False,
            }

        repo = FakeRepo(config())
        await go(repo, Provider(judge=judge))
        return float(repo.saved["data"]["report"]["visibility_index"])

    assert await vi(0.31) == await vi(1.0)  # both are "positive"
    assert await vi(0.3) == await vi(0.0)  # both are "neutral"
    assert await vi(1.0) > await vi(0.0) > await vi(-0.5)


async def test_a_judge_that_cannot_be_read_leaves_the_answer_out_and_the_run_partial():
    def judge(req: dict[str, Any]) -> Any:
        return "this is not json" if "FAILME" in req["response"] else reader(req)

    def answer(body: dict[str, Any]) -> str:
        return "FAILME " + RANKED if "gem" in body["model"] else RANKED

    repo = FakeRepo(config())
    await go(repo, Provider(answer=answer, judge=judge))
    q = repo.saved["data"]["quality"]
    assert repo.run["status"] == "partial" and (
        q["ok"],
        q["read"],
        q["judge_failed"],
    ) == (8, 4, 4)
    assert q["success_rate"] == 0.5 and "50%" in repo.saved["error"]
    assert (
        repo.saved["data"]["report"]["mention_rate"]["n"] == 4
    )  # the unread answers are not "not named"


async def test_when_nothing_can_be_read_the_run_fails_and_says_so():
    repo = FakeRepo(config())
    await go(repo, Provider(judge=lambda _r: {"oops": 1}))
    assert (
        repo.run["status"] == "failed"
        and repo.saved["error"] == "No answer could be read."
    )


async def test_empty_answers_are_not_judged_and_do_not_count_as_good():
    def answer(body: dict[str, Any]) -> str:
        return "" if "gem" in body["model"] else RANKED

    repo, prov = FakeRepo(config()), Provider(answer=answer)
    await go(repo, prov)
    q = repo.saved["data"]["quality"]
    assert prov.json_calls.count("judge") == 4  # nothing to read in the empty ones
    assert (q["empty"], q["read"]) == (4, 4) and repo.run["status"] == "partial"


async def test_a_restart_reads_again_what_the_judge_failed_on_and_only_that():
    repo = FakeRepo(config(started=True))
    for p in (0, 1):
        for e in ("ChatGPT", "Gemini"):
            for r in (1, 2):
                await repo.save_ai_answer("r1", p, e, r, text=RANKED, cost_micro=1000)
    done = ar.read_judge_output(reader({"response": RANKED, "brands": [GLOW]}), [GLOW])
    for key in list(repo.answers):
        repo.answers[key]["facts"] = done  # all read ...
    repo.answers[(0, "ChatGPT", 1)]["facts"] = {
        "judge_failed": True,
        "error": "ValueError",
    }  # ... but one
    prov = Provider()
    await go(repo, prov)
    assert prov.json_calls.count("judge") == 1 and prov.asks == []
    assert repo.run["status"] == "ready" and repo.saved["data"]["quality"]["read"] == 8


async def test_a_restart_asks_only_the_missing_answers():
    repo = FakeRepo(config())
    for key in [(0, "ChatGPT", 1), (0, "ChatGPT", 2), (1, "Gemini", 1)]:
        await repo.save_ai_answer("r1", *key, text=RANKED, cost_micro=1000)
    repo.run["config"]["started"] = True
    prov = Provider()
    await go(repo, prov)
    assert len(prov.asks) == 5 and len(repo.answers) == 8
    assert repo.run["config"]["resumes"] == 1 and repo.run["status"] == "ready"


async def test_a_run_that_keeps_crashing_is_failed_not_retried_forever():
    repo = FakeRepo(config(started=True, resumes=ar.MAX_RESUMES))
    prov = Provider()
    await go(repo, prov)
    assert repo.run["status"] == "failed" and prov.asks == []


async def test_cost_cap_stops_the_run_and_marks_it_partial():
    cfg = config(
        n_prompts=4,
        runs=3,
        calls=24,
        prompts=[f"q{i} med spa Austin" for i in range(4)],
        budget_micro=3000,
    )
    repo, prov = FakeRepo(cfg), Provider()
    await go(repo, prov)
    data = repo.saved["data"]
    assert repo.run["status"] == "partial" and data["quality"]["capped"] is True
    assert 3 <= len(prov.asks) <= 3 + ar.ASK_WAVE < 24
    assert "cost cap" in repo.saved["error"]


async def test_one_dead_engine_is_partial_and_shown_per_engine():
    repo = FakeRepo(config())
    await go(repo, Provider(fail_engine="gem"))
    data = repo.saved["data"]
    assert repo.run["status"] == "partial" and data["quality"]["success_rate"] == 0.5
    gem = next(e for e in data["engines"] if e["engine"] == "Gemini")
    assert gem["prompts_failed"] == 4 and gem["error"] == "HTTP 400"


async def test_every_engine_failing_fails_the_run():
    repo = FakeRepo(config())
    await go(repo, Provider(fail_engine="/"))
    assert repo.run["status"] == "failed" and repo.saved["data"]["quality"]["ok"] == 0


async def test_without_local_competitors_one_batched_call_finds_them_and_the_judge_gets_them():
    repo, prov = FakeRepo(config()), Provider(answer=f"Try Lumi Spa and {GLOW}.")
    await go(repo, prov, NO_LOCAL)
    assert prov.json_calls.count("names") == 1
    assert repo.run["config"]["rivals"][0] == "Lumi Spa"
    assert prov.judge_requests[0]["brands"] == [GLOW, "Lumi Spa", "Bella Skin"]
    assert "Lumi Spa" in repo.saved["data"]["report"]["share_of_voice"]
    assert repo.saved["data"]["competitors"]["source"] == "llm"


async def test_local_competitors_mean_no_discovery_call_and_approved_questions_are_used_as_given():
    repo, prov = FakeRepo(config()), Provider()
    await go(repo, prov)
    assert "names" not in prov.json_calls and "writer" not in prov.json_calls
    assert repo.run["config"]["prompts"] == [
        "best botox in Austin",
        "top med spa near Austin",
    ]
    assert sorted({a["prompt_idx"] for a in repo.answers.values()}) == [0, 1]
    # the judge is shown the question that was asked, for each answer
    assert {r["prompt"] for r in prov.judge_requests} == {
        "best botox in Austin",
        "top med spa near Austin",
    }


async def test_questions_are_written_when_the_caller_gave_none():
    repo, prov = (
        FakeRepo(config(prompts=None, prompts_source=None, n_prompts=3, calls=12)),
        Provider(),
    )
    repo.run["config"].pop("prompts")
    await go(repo, prov)
    got = repo.run["config"]["prompts"]
    assert "writer" in prov.json_calls and len(got) == 3
    assert all(GLOW not in p for p in got)
    assert repo.run["config"]["overhead_micro"] == 200


async def test_a_second_write_for_the_same_answer_is_ignored():
    repo = FakeRepo(config())
    await repo.save_ai_answer("r1", 0, "ChatGPT", 1, text="first", cost_micro=5)
    await repo.save_ai_answer("r1", 0, "ChatGPT", 1, text="second", cost_micro=5)
    assert repo.answers[(0, "ChatGPT", 1)]["text"] == "first"


# ── the step log: one step per engine and question ───────────────────────────────────────


def asks(repo: FakeRepo) -> dict[str, dict[str, Any]]:
    return {e["id"]: e for e in repo.saved["data"]["log"] if e["id"].startswith("ask:")}


async def test_log_has_one_step_per_engine_and_question_summed_over_the_repeats():
    repo = FakeRepo(config())
    await go(repo, Provider())
    steps = asks(repo)
    assert sorted(steps) == [
        "ask:ChatGPT:0",
        "ask:ChatGPT:1",
        "ask:Gemini:0",
        "ask:Gemini:1",
    ]
    one = steps["ask:ChatGPT:0"]
    assert one["status"] == "done" and one["label"] == "ChatGPT · question 1"
    d = one["detail"]
    assert (d["tokens"], d["cost_usd"], d["runs"], d["failed"]) == (200, 0.002, 2, 0)
    # who was named comes from the judge, once it has read the answers
    assert (d["read"], d["mentioned"], d["named"], d["judged"], d["linked"]) == (
        True,
        True,
        2,
        2,
        False,
    )
    assert (
        one["ms"] is not None
    )  # the time of the asking is kept when the result is added
    ids = [e["id"] for e in repo.saved["data"]["log"]]
    assert "ask" not in ids and ids[0] == "prompts" and ids[-2:] == ["usage", "final"]
    assert ids.index("read") > ids.index("ask:Gemini:1")


async def test_log_says_linked_only_when_the_judge_says_cited():
    def judge(req: dict[str, Any]) -> dict[str, Any]:
        return {
            "brands": {GLOW: signals(True, cited=req["prompt"].startswith("best"))},
            "response_is_ranked_list": False,
        }

    repo = FakeRepo(config())
    await go(repo, Provider(judge=judge))
    steps = asks(repo)
    assert (
        steps["ask:ChatGPT:0"]["detail"]["linked"] is True
        and steps["ask:ChatGPT:1"]["detail"]["linked"] is False
    )


async def test_log_counts_how_often_the_clinic_was_named_out_of_the_repeats():
    n = iter(range(100))

    def judge(req: dict[str, Any]) -> dict[str, Any]:
        return {
            "brands": {GLOW: signals(next(n) % 2 == 0)},
            "response_is_ranked_list": False,
        }

    repo = FakeRepo(config())
    await go(repo, Provider(judge=judge))
    assert sum(s["detail"]["named"] for s in asks(repo).values()) == 4  # of 8 answers


async def test_before_the_judge_has_read_a_step_makes_no_claim_about_who_was_named():
    repo = FakeRepo(config())
    async with httpx.AsyncClient(transport=httpx.MockTransport(Provider())) as http:
        job = ar.Job(repo, http, repo.run, AUDIT)  # type: ignore[arg-type]
        job.note("ChatGPT", 0, av.Answer(RANKED, [], 100, 1000), None)
        job.note("ChatGPT", 0, av.Answer(RANKED, [], 100, 1000), None)
    d = {e["id"]: e for e in job.log.events()}["ask:ChatGPT:0"]["detail"]
    assert (
        d["read"] is False
        and "mentioned" not in d
        and "named" not in d
        and d["tokens"] == 200
    )


async def test_log_marks_a_step_failed_only_when_every_repeat_failed():
    repo = FakeRepo(config())
    await go(repo, Provider(fail_engine="gem"))
    steps = asks(repo)
    assert (
        steps["ask:Gemini:0"]["status"] == "failed"
        and steps["ask:Gemini:0"]["detail"]["error"] == "HTTP 400"
    )
    assert steps["ask:ChatGPT:0"]["status"] == "done"


async def test_log_shows_cells_cut_short_by_the_cost_cap_as_skipped():
    cfg = config(
        n_prompts=4,
        runs=3,
        calls=24,
        prompts=[f"q{i} med spa Austin" for i in range(4)],
        budget_micro=1500,
    )
    repo = FakeRepo(cfg)
    await go(repo, Provider())
    steps = asks(repo)
    # the cap lands after 2 of the first cell's 3 repeats, so that cell is cut short
    cut = [s for s in steps.values() if s["status"] == "skipped"]
    assert cut and all(s["detail"]["error"] == "Stopped at the cost cap" for s in cut)
    assert not any(s["status"] == "running" for s in steps.values())


async def test_a_restart_rebuilds_the_log_from_the_saved_answers():
    repo = FakeRepo(config())
    for key in [(0, "ChatGPT", 1), (0, "ChatGPT", 2)]:
        await repo.save_ai_answer(
            "r1",
            *key,
            text=RANKED,
            tokens=100,
            cost_micro=1000,
            urls=["https://glowmedspa.com/x"],
        )
    repo.run["config"]["started"] = True
    await go(repo, Provider())
    d = asks(repo)["ask:ChatGPT:0"]["detail"]
    assert (d["runs"], d["tokens"], d["named"]) == (2, 200, 2)
    assert len(asks(repo)) == 4 and repo.saved["data"]["usage"]["calls"] == 8


async def test_usage_judge_row_says_what_it_is():
    repo = FakeRepo(config())
    await go(repo, Provider())
    judge = repo.saved["data"]["usage"]["judge"]
    assert judge["label"] == "Reading the answers (AI)" and judge[
        "cost_usd"
    ] == pytest.approx(0.0016)
