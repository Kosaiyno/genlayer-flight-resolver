"""
Unit tests for FlightResolver Intelligent Contract.
Mocks the GenLayer runtime environment (gl, TreeMap, u256, Address, gl.nondet.web.get)
to verify all contract state transitions, authoritative flight feed acquisition,
verbatim quote validation, and deterministic safety clamps.
"""

import sys
import os
import json
import unittest

# --- Mock GenLayer Runtime for Local Unit Testing ---
class Address(str):
    def __repr__(self):
        return f"Address('{self}')"


class u256(int):
    def __new__(cls, val):
        return super().__new__(cls, val)


class TreeMap(dict):
    pass


class DynArray(list):
    pass


class MockMessage:
    def __init__(self):
        self.sender_address = Address("0xTraveller11111111111111111111111111111111")
        self.origin_address = Address("0xTraveller11111111111111111111111111111111")


class MockBlock:
    def __init__(self):
        self.timestamp = 1791500000


class MockWebResponse:
    def __init__(self, text: str):
        self.body = text.encode("utf-8")

    def __str__(self):
        return self.body.decode("utf-8")


class MockNondetWeb:
    def __init__(self):
        self.responses = {}

    def get(self, url: str):
        if url in self.responses:
            return MockWebResponse(self.responses[url])
        return MockWebResponse(json.dumps({
            "flight_number": "DEFAULT123",
            "arrival_time_iso": "2026-11-05T15:00:00Z",
            "fare_cents": 10000,
            "stops": 0,
            "layover_minutes": 0,
            "booking_status": "AVAILABLE"
        }))


class MockNondet:
    def __init__(self):
        self.web = MockNondetWeb()


class MockEqPrinciple:
    def __init__(self):
        self.mock_response = None

    def prompt_non_comparative(self, get_input_fn, task="", criteria=""):
        if self.mock_response is not None:
            return self.mock_response

        user_input = get_input_fn()
        if "DL402" in user_input or "2026-11-05T21:45:00Z" in user_input:
            return json.dumps({
                "decision": "DISQUALIFIED",
                "arrival_time_iso": "2026-11-05T21:45:00Z",
                "actual_fare_cents": 12000,
                "stops": 0,
                "layover_minutes": 0,
                "booking_status": "AVAILABLE",
                "verbatim_quote": "\"arrival_time_iso\": \"2026-11-05T21:45:00Z\"",
                "rationale": "Flight arrives over 3 hours after passenger strict deadline."
            })
        elif "AF1128" in user_input or "layover_minutes\": 25" in user_input:
            return json.dumps({
                "decision": "DISQUALIFIED",
                "arrival_time_iso": "2026-11-05T17:45:00Z",
                "actual_fare_cents": 18000,
                "stops": 1,
                "layover_minutes": 25,
                "booking_status": "AVAILABLE",
                "verbatim_quote": "\"layover_minutes\": 25",
                "rationale": "25-minute connection violates minimum 60-minute layover safety floor."
            })
        elif "BA177" in user_input:
            return json.dumps({
                "decision": "QUALIFIED",
                "arrival_time_iso": "2026-11-05T16:15:00Z",
                "actual_fare_cents": 15000,
                "stops": 0,
                "layover_minutes": 0,
                "booking_status": "AVAILABLE",
                "verbatim_quote": "\"flight_number\": \"BA177\", \"arrival_time_iso\": \"2026-11-05T16:15:00Z\"",
                "rationale": "Direct non-stop flight arrives 2 hours before deadline within budget."
            })
        else:
            return json.dumps({
                "decision": "QUALIFIED",
                "arrival_time_iso": "2026-11-05T15:00:00Z",
                "actual_fare_cents": 10000,
                "stops": 0,
                "layover_minutes": 0,
                "booking_status": "AVAILABLE",
                "verbatim_quote": "\"booking_status\": \"AVAILABLE\"",
                "rationale": "Feasible alternative within constraints."
            })


class MockContract:
    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls)
        obj.journeys = TreeMap()
        obj.proposals = TreeMap()
        obj.adjudications = TreeMap()
        obj.journey_counter = u256(0)
        obj.proposal_counter = u256(0)
        return obj


class MockPublic:
    @staticmethod
    def view(f):
        return f

    @staticmethod
    def write(f):
        return f


class MockGLModule:
    def __init__(self):
        self.Contract = MockContract
        self.message = MockMessage()
        self.block = MockBlock()
        self.nondet = MockNondet()
        self.eq_principle = MockEqPrinciple()
        self.public = MockPublic()


# Register mocks in sys.modules
mock_gl = MockGLModule()
genlayer_mock = type(sys)("genlayer")
genlayer_mock.gl = mock_gl
genlayer_mock.Address = Address
genlayer_mock.u256 = u256
genlayer_mock.TreeMap = TreeMap
genlayer_mock.DynArray = DynArray
sys.modules["genlayer"] = genlayer_mock

# Add contracts path to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "contracts")))
from flight_resolver import FlightResolver


class TestFlightResolver(unittest.TestCase):
    def setUp(self):
        mock_gl.message.sender_address = Address("0xTraveller11111111111111111111111111111111")
        mock_gl.eq_principle.mock_response = None
        self.resolver = FlightResolver()
        self.traveller = "0xTraveller11111111111111111111111111111111"
        self.agent = "0xAgent222222222222222222222222222222222222"
        self.intruder = "0xIntruder99999999999999999999999999999999"

        # Mock URLs
        self.url_honest = "https://raw.githubusercontent.com/kosaiyno/genlayer-flight-resolver/main/evidence/honest_rebooking_flight.json"
        self.url_delayed = "https://raw.githubusercontent.com/kosaiyno/genlayer-flight-resolver/main/evidence/delayed_missed_deadline_flight.json"
        self.url_unsafe = "https://raw.githubusercontent.com/kosaiyno/genlayer-flight-resolver/main/evidence/phantom_unsafe_connection_flight.json"

        mock_gl.nondet.web.responses[self.url_honest] = json.dumps({
            "flight_number": "BA177",
            "arrival_time_iso": "2026-11-05T16:15:00Z",
            "fare_cents": 15000,
            "stops": 0,
            "layover_minutes": 0,
            "booking_status": "AVAILABLE"
        })
        mock_gl.nondet.web.responses[self.url_delayed] = json.dumps({
            "flight_number": "DL402",
            "arrival_time_iso": "2026-11-05T21:45:00Z",
            "fare_cents": 12000,
            "stops": 0,
            "layover_minutes": 0,
            "booking_status": "AVAILABLE"
        })
        mock_gl.nondet.web.responses[self.url_unsafe] = json.dumps({
            "flight_number": "AF1128",
            "arrival_time_iso": "2026-11-05T17:45:00Z",
            "fare_cents": 18000,
            "stops": 1,
            "layover_minutes": 25,
            "booking_status": "AVAILABLE"
        })

    def test_initialization(self):
        self.assertEqual(int(self.resolver.get_total_journeys()), 0)
        self.assertEqual(int(self.resolver.get_total_proposals()), 0)
        stats = self.resolver.get_resolver_stats()
        self.assertIn("Total Journeys: 0", stats)

    def test_register_journey_and_propose(self):
        jid = self.resolver.register_journey(
            origin="LHR",
            destination="JFK",
            arrival_deadline_iso="2026-11-05T18:30:00Z",
            max_extra_cost_cents=20000,
            max_stops=1,
            min_layover_mins=60,
            priority_mode="SPEED_FIRST"
        )
        self.assertEqual(int(jid), 1)
        self.assertEqual(self.resolver.get_journey_status(1), "DISRUPTED")

        mock_gl.message.sender_address = Address(self.agent)
        pid = self.resolver.propose_rebooking_option(
            journey_id=1,
            flight_code="BA177",
            airline="British Airways",
            flight_evidence_url=self.url_honest,
            claimed_fare_cents=15000,
            agent_notes="Direct replacement flight"
        )
        self.assertEqual(int(pid), 1)
        self.assertEqual(self.resolver.get_proposal_status(1), "PROPOSED")

    def test_adjudicate_honest_qualified_and_confirmed(self):
        self.resolver.register_journey(
            origin="LHR",
            destination="JFK",
            arrival_deadline_iso="2026-11-05T18:30:00Z",
            max_extra_cost_cents=20000,
            max_stops=1,
            min_layover_mins=60,
            priority_mode="SPEED_FIRST"
        )
        mock_gl.message.sender_address = Address(self.agent)
        self.resolver.propose_rebooking_option(1, "BA177", "British Airways", self.url_honest, 15000, "Direct")

        res = self.resolver.adjudicate_rebooking(1, 1)
        parsed = json.loads(res)
        self.assertEqual(parsed["decision"], "QUALIFIED")
        self.assertEqual(self.resolver.get_proposal_status(1), "QUALIFIED")

        # Confirm rebooking
        confirm_res = self.resolver.confirm_rebooking(1, 1)
        self.assertTrue(confirm_res)
        self.assertEqual(self.resolver.get_journey_status(1), "RESOLVED")
        self.assertEqual(self.resolver.get_proposal_status(1), "CONFIRMED")

    def test_adjudicate_catches_delayed_deadline_miss(self):
        self.resolver.register_journey(
            origin="LHR",
            destination="JFK",
            arrival_deadline_iso="2026-11-05T18:30:00Z",
            max_extra_cost_cents=20000,
            max_stops=1,
            min_layover_mins=60,
            priority_mode="SPEED_FIRST"
        )
        mock_gl.message.sender_address = Address(self.agent)
        # Agent proposes flight DL402 that lands at 21:45:00Z (past 18:30:00Z deadline)
        self.resolver.propose_rebooking_option(1, "DL402", "Delta", self.url_delayed, 12000, "Alternative")

        res = self.resolver.adjudicate_rebooking(1, 1)
        parsed = json.loads(res)
        self.assertEqual(parsed["decision"], "DISQUALIFIED")
        self.assertEqual(self.resolver.get_proposal_status(1), "DISQUALIFIED")

    def test_adjudicate_catches_unsafe_connection_layover(self):
        self.resolver.register_journey(
            origin="LHR",
            destination="JFK",
            arrival_deadline_iso="2026-11-05T18:30:00Z",
            max_extra_cost_cents=20000,
            max_stops=1,
            min_layover_mins=60,  # Requires at least 60m layover
            priority_mode="SPEED_FIRST"
        )
        mock_gl.message.sender_address = Address(self.agent)
        # Agent claims viable flight, but feed shows 25-minute layover
        self.resolver.propose_rebooking_option(1, "AF1128", "Air France", self.url_unsafe, 18000, "Via CDG")

        res = self.resolver.adjudicate_rebooking(1, 1)
        parsed = json.loads(res)
        self.assertEqual(parsed["decision"], "DISQUALIFIED")
        self.assertEqual(self.resolver.get_proposal_status(1), "DISQUALIFIED")
        self.assertIn("Deterministic clamp", parsed["rationale"])

    def test_verbatim_quote_enforcement(self):
        self.resolver.register_journey(
            origin="LHR",
            destination="JFK",
            arrival_deadline_iso="2026-11-05T18:30:00Z",
            max_extra_cost_cents=20000,
            max_stops=1,
            min_layover_mins=60,
            priority_mode="SPEED_FIRST"
        )
        mock_gl.message.sender_address = Address(self.agent)
        self.resolver.propose_rebooking_option(1, "BA177", "British Airways", self.url_honest, 15000, "Direct")

        # Mock LLM returning missing verbatim quote
        mock_gl.eq_principle.mock_response = json.dumps({
            "decision": "QUALIFIED",
            "arrival_time_iso": "2026-11-05T16:15:00Z",
            "actual_fare_cents": 15000,
            "stops": 0,
            "layover_minutes": 0,
            "booking_status": "AVAILABLE",
            "verbatim_quote": "",  # Missing quote
            "rationale": "Looks ok"
        })

        res = self.resolver.adjudicate_rebooking(1, 1)
        parsed = json.loads(res)
        self.assertEqual(parsed["decision"], "DISQUALIFIED")
        self.assertIn("Missing verifiable verbatim quote", parsed["rationale"])

    def test_traveller_override_flow(self):
        self.resolver.register_journey("LHR", "JFK", "2026-11-05T18:30:00Z", 20000, 1, 45, "SPEED_FIRST")
        mock_gl.message.sender_address = Address(self.agent)
        self.resolver.propose_rebooking_option(1, "EI105", "Aer Lingus", self.url_honest, 14000, "Tight layover")

        mock_gl.eq_principle.mock_response = json.dumps({
            "decision": "BORDERLINE_REVIEW",
            "arrival_time_iso": "2026-11-05T17:00:00Z",
            "actual_fare_cents": 14000,
            "stops": 1,
            "layover_minutes": 50,
            "booking_status": "AVAILABLE",
            "verbatim_quote": "\"flight_number\": \"BA177\"",
            "rationale": "Tight 50-minute connection"
        })

        self.resolver.adjudicate_rebooking(1, 1)
        self.assertEqual(self.resolver.get_proposal_status(1), "BORDERLINE_REVIEW")

        # Unauthorized override fails
        mock_gl.message.sender_address = Address(self.intruder)
        with self.assertRaises(Exception):
            self.resolver.traveller_override(1, 1, approve=True)

        # Traveller approves
        mock_gl.message.sender_address = Address(self.traveller)
        self.resolver.traveller_override(1, 1, approve=True)
        self.assertEqual(self.resolver.get_proposal_status(1), "QUALIFIED")

    def test_cancellation_access_control(self):
        self.resolver.register_journey("LHR", "JFK", "2026-11-05T18:30:00Z", 20000, 1, 60, "SPEED_FIRST")
        mock_gl.message.sender_address = Address(self.intruder)
        with self.assertRaises(Exception):
            self.resolver.cancel_journey(1)

        mock_gl.message.sender_address = Address(self.traveller)
        self.resolver.cancel_journey(1)
        self.assertEqual(self.resolver.get_journey_status(1), "CANCELLED")


if __name__ == "__main__":
    unittest.main()
