"""The agent is only as good as the leash. These tests are the leash."""
import json

import pytest

from sdoc.agents import (
    AgentStats, AgentUnavailable, FieldResolver, NullClient, TriageAgent,
    _gemini_text, _parse_json_object, make_client,
)
from sdoc.compare import compare_documents
from sdoc.documents import DocType, Document
from sdoc.fields import extract_fields

DOC = """SHIPPING INSTRUCTION
========================================

Shipper: APRIL FAR EAST (M) SDN BHD
CONSIGNEE:
Notify: EAST BRIGHT FZ-LLC
Port of Loading: PORT KLANG, MALAYSIA (MYPKG)
Discharge Port: CALLAO, PERU (PECLL)
Total Containers: 6 x 40'HC
Gross Wt (kgs): 131,058 KG

Remarks: consignee is MOORIM SP CO., LTD per the booking note.
"""


class FakeClient:
    """Returns whatever the test tells it to, and records what it was asked."""

    def __init__(self, reply=""):
        self.reply = reply
        self.calls = []

    def complete(self, system, user, max_tokens=1024):
        self.calls.append((system, user))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class ExplodingClient:
    def complete(self, system, user, max_tokens=1024):
        raise RuntimeError("bedrock unavailable")


def resolve_with(reply):
    stats = AgentStats()
    resolver = FieldResolver(FakeClient(reply), stats)
    fields = extract_fields(DOC)
    accepted = resolver.resolve(DOC, fields, "shipping instruction")
    return fields, stats, accepted


class TestGrounding:
    def test_a_value_present_in_the_document_is_accepted(self):
        reply = json.dumps({"consignee": {
            "value": "MOORIM SP CO., LTD",
            "quote": "Remarks: consignee is MOORIM SP CO., LTD per the booking note.",
        }})
        fields, stats, accepted = resolve_with(reply)
        assert accepted == 1
        assert fields.get("consignee").value == "MOORIM SP CO., LTD"
        assert stats.fields_accepted == 1 and stats.rejected_ungrounded == 0

    def test_an_invented_value_is_rejected(self):
        # The company never appears in the document. This is the failure mode
        # that would put the wrong party on a bill of lading.
        reply = json.dumps({"consignee": {
            "value": "TOTALLY MADE UP TRADING LLC",
            "quote": "CONSIGNEE: TOTALLY MADE UP TRADING LLC",
        }})
        fields, stats, accepted = resolve_with(reply)
        assert accepted == 0
        assert "consignee" in fields.missing
        assert stats.rejected_ungrounded == 1

    def test_a_real_quote_with_a_smuggled_value_is_rejected(self):
        # Quote is genuine, value is not inside it.
        reply = json.dumps({"consignee": {
            "value": "SOME OTHER COMPANY",
            "quote": "Shipper: APRIL FAR EAST (M) SDN BHD",
        }})
        _, stats, accepted = resolve_with(reply)
        assert accepted == 0 and stats.rejected_ungrounded == 1

    def test_grounding_survives_line_wrapping(self):
        wrapped = DOC.replace(
            "Remarks: consignee is MOORIM SP CO., LTD per the booking note.",
            "Remarks: consignee is\n  MOORIM SP CO., LTD per the\n  booking note.",
        )
        stats = AgentStats()
        resolver = FieldResolver(FakeClient(json.dumps({"consignee": {
            "value": "MOORIM SP CO., LTD",
            "quote": "consignee is MOORIM SP CO., LTD per the booking note.",
        }})), stats)
        fields = extract_fields(wrapped)
        assert resolver.resolve(wrapped, fields, "si") == 1

    def test_implausible_value_for_a_typed_field_is_rejected(self):
        doc = "SHIPPING INSTRUCTION\n\nGross Wt (kgs):\nNote: the vessel is SOLID 16\n"
        stats = AgentStats()
        resolver = FieldResolver(FakeClient(json.dumps({"gross_weight_kg": {
            "value": "the vessel is SOLID 16",
            "quote": "Note: the vessel is SOLID 16",
        }})), stats)
        fields = extract_fields(doc)
        assert resolver.resolve(doc, fields, "si") == 0
        assert stats.rejected_implausible == 1

    def test_an_unfilled_blank_is_rejected_though_it_is_grounded(self):
        """The blank really is printed there, so grounding alone accepts it.

        Found on a live run against email_517, where the agent resolved
        `Port of Loading (POL): ____MT` to "____MT" and the comparison then
        reported the carrier's SINGAPORE as a serious discrepancy against it.
        The reading pass already refuses these; the agent must too.
        """
        doc = ("SHIPPING INSTRUCTION\n\n"
               "Port of Loading (POL): ____MT\n"
               "Port of Discharge (POD): TBA\n")
        stats = AgentStats()
        resolver = FieldResolver(FakeClient(json.dumps({
            "port_of_loading": {"value": "____MT",
                                "quote": "Port of Loading (POL): ____MT"},
            "port_of_discharge": {"value": "TBA",
                                  "quote": "Port of Discharge (POD): TBA"},
        })), stats)
        fields = extract_fields(doc)
        assert resolver.resolve(doc, fields, "si") == 0
        assert stats.rejected_placeholder == 2
        assert stats.rejected_ungrounded == 0    # they were grounded
        assert "port_of_loading" not in fields.values


class TestRefusalToOverreach:
    def test_it_never_overwrites_a_field_the_parser_already_found(self):
        reply = json.dumps({"shipper": {
            "value": "APRIL FAR EAST (M) SDN BHD",
            "quote": "Shipper: APRIL FAR EAST (M) SDN BHD",
        }})
        fields, _, accepted = resolve_with(reply)
        assert accepted == 0
        assert fields.get("shipper").label == "Shipper"

    def test_unknown_field_names_are_ignored(self):
        reply = json.dumps({"vessel_name": {"value": "SOLID 16", "quote": "x"}})
        _, _, accepted = resolve_with(reply)
        assert accepted == 0

    def test_it_is_not_called_when_nothing_is_missing(self):
        client = FakeClient("{}")
        resolver = FieldResolver(client, AgentStats())
        complete_doc = DOC.replace("CONSIGNEE:", "CONSIGNEE: EAST BRIGHT FZ-LLC")
        fields = extract_fields(complete_doc)
        assert not fields.missing
        assert resolver.resolve(complete_doc, fields) == 0
        assert client.calls == []

    def test_only_the_missing_fields_are_asked_for(self):
        client = FakeClient("{}")
        FieldResolver(client, AgentStats()).resolve(DOC, extract_fields(DOC), "si")
        _, user = client.calls[0]
        assert "consignee" in user and "not found by the parser" in user
        assert "shipper," not in user.split("not found by the parser")[1]


class TestFailureModes:
    @pytest.mark.parametrize("reply", ["", "   ", "I could not find it.", "{", "null", "[]"])
    def test_unusable_replies_are_treated_as_abstention(self, reply):
        _, _, accepted = resolve_with(reply)
        assert accepted == 0

    def test_a_transport_failure_does_not_break_the_run(self):
        stats = AgentStats()
        resolver = FieldResolver(ExplodingClient(), stats)
        fields = extract_fields(DOC)
        assert resolver.resolve(DOC, fields, "si") == 0
        assert any("resolver call failed" in n for n in stats.notes)

    def test_null_client_never_calls_out(self):
        resolver = FieldResolver(NullClient(), AgentStats())
        assert resolver.resolve(DOC, extract_fields(DOC)) == 0
        assert resolver.stats.resolver_calls == 0

    def test_json_wrapped_in_a_code_fence_is_read(self):
        reply = '```json\n{"consignee": {"value": "MOORIM SP CO., LTD", ' \
                '"quote": "Remarks: consignee is MOORIM SP CO., LTD per the booking note."}}\n```'
        _, _, accepted = resolve_with(reply)
        assert accepted == 1

    def test_parse_helper_handles_prose_around_the_object(self):
        assert _parse_json_object('Sure! {"a": 1} hope that helps') == {"a": 1}


class TestCascadePlacement:
    """The agent runs before escalation, and never instead of the comparator."""

    def _docs(self, si_text):
        si = Document(path="si.txt", role="SI", fmt=".txt", text=si_text,
                      doc_type=DocType.SHIPPING_INSTRUCTION, ok=True)
        bl = Document(path="bl.txt", role="BL", fmt=".txt", text=(
            "BILL OF LADING (DRAFT)\n\n"
            "SHIPPER: APRIL FAR EAST (M) SDN BHD\n"
            "CONSIGNEE: MOORIM SP CO., LTD\n"
            "Notify Party: EAST BRIGHT FZ-LLC\n"
            "POL: PORT KLANG, MALAYSIA (MYPKG)\n"
            "POD: CALLAO, PERU (PECLL)\n"
            "Container Count: 6 x 40'HC\n"
            "Gross Weight(KG): 131,058 KG\n"
        ), doc_type=DocType.BILL_OF_LADING, ok=True)
        return si, bl

    def test_a_recovered_field_turns_an_escalation_into_a_decision(self):
        si, bl = self._docs(DOC)
        assert compare_documents(si, bl).review_reason == "missing_value"

        resolver = FieldResolver(FakeClient(json.dumps({"consignee": {
            "value": "MOORIM SP CO., LTD",
            "quote": "Remarks: consignee is MOORIM SP CO., LTD per the booking note.",
        }})), AgentStats())
        assert compare_documents(si, bl, resolver).status == "OK"

    def test_a_recovered_field_can_also_reveal_a_defect(self):
        si, bl = self._docs(DOC.replace(
            "Remarks: consignee is MOORIM SP CO., LTD per the booking note.",
            "Remarks: consignee is CLIFFORD PAPER INC per the booking note.",
        ))
        resolver = FieldResolver(FakeClient(json.dumps({"consignee": {
            "value": "CLIFFORD PAPER INC",
            "quote": "Remarks: consignee is CLIFFORD PAPER INC per the booking note.",
        }})), AgentStats())
        verdict = compare_documents(si, bl, resolver)
        assert verdict.status == "MISMATCH" and verdict.defect_fields == ["consignee"]

    def test_a_hallucinating_agent_still_escalates(self):
        si, bl = self._docs(DOC)
        resolver = FieldResolver(FakeClient(json.dumps({"consignee": {
            "value": "MOORIM SP CO., LTD",
            "quote": "CONSIGNEE: MOORIM SP CO., LTD",
        }})), AgentStats())
        verdict = compare_documents(si, bl, resolver)
        assert verdict.status == "NEEDS_REVIEW" and verdict.review_reason == "missing_value"

    def test_the_agent_is_never_consulted_for_a_blocked_comparison(self):
        client = FakeClient("{}")
        resolver = FieldResolver(client, AgentStats())
        si, _ = self._docs(DOC)
        assert compare_documents(si, None, resolver).review_reason == "missing_attachment"
        assert client.calls == []


class TestTriageAgent:
    def test_a_valid_category_is_taken(self):
        agent = TriageAgent(FakeClient('{"category": "INVOICE_QUERY"}'), AgentStats())
        assert agent.classify("RAK BILLING MISSING GR", "...") == "INVOICE_QUERY"

    def test_an_invented_category_is_refused(self):
        agent = TriageAgent(FakeClient('{"category": "URGENT_ESCALATION"}'), AgentStats())
        assert agent.classify("x", "y") is None

    def test_failure_returns_none_so_the_rule_verdict_stands(self):
        agent = TriageAgent(ExplodingClient(), AgentStats())
        assert agent.classify("x", "y") is None

    def test_null_client_abstains(self):
        assert TriageAgent(NullClient(), AgentStats()).classify("x", "y") is None


class TestProviders:
    """Provider choice is a swap behind one method, and must fail loudly."""

    def test_off_never_calls_out(self):
        assert isinstance(make_client("off"), NullClient)

    def test_an_unknown_provider_is_refused(self):
        with pytest.raises(AgentUnavailable, match="unknown agent provider"):
            make_client("gpt5")

    def test_gemini_without_a_key_explains_itself(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        with pytest.raises(AgentUnavailable, match="GEMINI_API_KEY"):
            make_client("gemini")

    def test_gemini_client_is_built_when_a_key_exists(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
        client = make_client("gemini")
        assert client.model and hasattr(client, "complete")


class TestGeminiResponseShape:
    def test_reads_the_reply_text(self):
        payload = {"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}]}
        assert _gemini_text(payload) == '{"a": 1}'

    def test_joins_several_parts(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "{"}, {"text": "}"}]}}]}
        assert _gemini_text(payload) == "{}"

    @pytest.mark.parametrize("payload", [
        {},
        {"candidates": []},
        {"candidates": [{"finishReason": "SAFETY"}]},
        {"candidates": [{"content": {}}]},
        {"candidates": [{"content": {"parts": []}}]},
    ])
    def test_a_blocked_or_empty_reply_is_an_abstention(self, payload):
        # Empty string reaches the resolver, which treats it as "found nothing".
        assert _gemini_text(payload) == ""

    def test_an_empty_reply_makes_the_resolver_abstain(self):
        stats = AgentStats()
        resolver = FieldResolver(FakeClient(_gemini_text({"candidates": []})), stats)
        from sdoc.fields import extract_fields
        fields = extract_fields(DOC)
        assert resolver.resolve(DOC, fields, "si") == 0
