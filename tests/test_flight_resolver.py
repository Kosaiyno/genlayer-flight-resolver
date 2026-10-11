"""
Unit tests for FlightResolver Intelligent Contract.
Mocks the GenLayer runtime environment (gl, TreeMap, u256, Address) to verify
all contract state transitions, disruption flows, equivalence adjudications,
budget clamps, borderline overrides, and error handling.
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


class MockEqPrinciple:
    def __init__(self):
        self.mock_response = None

    def prompt_non_comparative(self, get_input_fn, task="", criteria=""):
        if self.mock_response is not None:
            return self.mock_response

        user_input = get_input_fn()
        # Simulated responses based on test scenarios
        if "Additional Cost: $350.00 (35000 cents)" in user_input and "Max Additional Cost: $200.00" in user_input:
            return json.dumps({
                "decision": "DISQUALIFIED",
                "feasibility_score": 45,
                "deadline_met": True,
                "budget_met": False,
                "rationale": "Flight arrives in time but exceeds traveller's additional cost ceiling."
            })
        elif "BA177" in user_input:
            return json.dumps({
                "decision": "QUALIFIED",
                "feasibility_score": 96,
                "deadline_met": True,
                "budget_met": True,
                "rationale": "Direct flight arriving 2 hours before deadline within budget."
            })
        elif "EI105" in user_input:
            return json.dumps({
                "decision": "BORDERLINE_REVIEW",
                "feasibility_score": 78,
                "deadline_met": True,
                "budget_met": True,
                "rationale": "Arrives before deadline under budget, but has a 45-minute tight connection in Dublin."
            })
        elif "DL402" in user_input:
            return json.dumps({
                "decision": "DISQUALIFIED",
                "feasibility_score": 30,
                "deadline_met": False,
                "budget_met": True,
                "rationale": "Scheduled arrival lands 3 hours after traveller's strict arrival deadline."
            })
        else:
            return json.dumps({
                "decision": "QUALIFIED",
                "feasibility_score": 90,
                "deadline_met": True,
                "budget_met": True,
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
        self.agent = "0xAgent22222222222222222222222222222222222"
        self.intruder = "0xIntruder9999999999999999999999999999999"

    def test_initialization(self):
        self.assertEqual(int(self.resolver.get_total_journeys()), 0)
        self.assertEqual(int(self.resolver.get_total_proposals()), 0)
        stats = self.resolver.get_resolver_stats()
        self.assertIn("Total Journeys: 0", stats)

    def test_register_journey_success(self):
        jid = self.resolver.register_journey(
            origin="LHR",
            destination="JFK",
            arrival_deadline_iso="2026-10-15T18:00:00Z",
            max_extra_cost_cents=20000,
            max_stops=1,
            min_layover_mins=60,
            priority_mode="SPEED_FIRST"
        )
        self.assertEqual(int(jid), 1)
        self.assertEqual(int(self.resolver.get_total_journeys()), 1)
        self.assertEqual(self.resolver.get_journey_status(1), "SCHEDULED")

        journey = json.loads(self.resolver.get_journey(1))
        self.assertEqual(journey["origin"], "LHR")
        self.assertEqual(journey["destination"], "JFK")
        self.assertEqual(journey["max_extra_cost_cents"], 20000)

    def test_register_journey_validations(self):
        # Empty origin/destination
        with self.assertRaises(ValueError):
            self.resolver.register_journey("", "JFK", "2026-10-15T18:00:00Z", 20000, 1, 60, "SPEED_FIRST")

        # Negative cost
        with self.assertRaises(ValueError):
            self.resolver.register_journey("LHR", "JFK", "2026-10-15T18:00:00Z", -100, 1, 60, "SPEED_FIRST")

        # Invalid priority mode
        with self.assertRaises(ValueError):
            self.resolver.register_journey("LHR", "JFK", "2026-10-15T18:00:00Z", 20000, 1, 60, "INVALID_MODE")

    def test_report_disruption(self):
        self.resolver.register_journey("LHR", "JFK", "2026-10-15T18:00:00Z", 20000, 1, 60, "SPEED_FIRST")
        res = self.resolver.report_disruption(
            journey_id=1,
            original_flight_code="VS003",
            disruption_type="CANCELLED",
            reason="Mechanical engine issue grounded aircraft"
        )
        self.assertTrue(res)
        self.assertEqual(self.resolver.get_journey_status(1), "DISRUPTED")

        journey = json.loads(self.resolver.get_journey(1))
        self.assertEqual(journey["disruption_info"]["disruption_type"], "CANCELLED")

    def test_propose_and_adjudicate_qualified_and_confirm(self):
        self.resolver.register_journey("LHR", "JFK", "2026-10-15T18:00:00Z", 20000, 1, 60, "SPEED_FIRST")
        self.resolver.report_disruption(1, "VS003", "CANCELLED", "Flight cancelled")

        # Agent proposes BA177
        mock_gl.message.sender_address = Address(self.agent)
        pid = self.resolver.propose_rebooking_option(
            journey_id=1,
            flight_code="BA177",
            airline="British Airways",
            departure_iso="2026-10-15T13:00:00Z",
            arrival_iso="2026-10-15T16:00:00Z",
            stops=0,
            layover_details="Direct flight",
            added_cost_cents=15000,
            booking_url="https://ba.com/booking/177"
        )
        self.assertEqual(int(pid), 1)
        self.assertEqual(self.resolver.get_proposal_status(1), "PROPOSED")

        # Adjudicate rebooking
        adj_result = self.resolver.adjudicate_rebooking(journey_id=1, proposal_id=1)
        parsed = json.loads(adj_result)
        self.assertEqual(parsed["decision"], "QUALIFIED")
        self.assertEqual(self.resolver.get_proposal_status(1), "QUALIFIED")

        # Confirm rebooking
        mock_gl.message.sender_address = Address(self.traveller)
        confirm_res = self.resolver.confirm_rebooking(journey_id=1, proposal_id=1)
        self.assertTrue(confirm_res)
        self.assertEqual(self.resolver.get_journey_status(1), "RESOLVED")
        self.assertEqual(self.resolver.get_proposal_status(1), "CONFIRMED")

    def test_adjudicate_deadline_breach_disqualified(self):
        self.resolver.register_journey("LHR", "JFK", "2026-10-15T18:00:00Z", 20000, 1, 60, "SPEED_FIRST")
        self.resolver.report_disruption(1, "VS003", "CANCELLED", "Cancelled")

        # Flight lands at 21:00 (past 18:00 deadline)
        mock_gl.message.sender_address = Address(self.agent)
        self.resolver.propose_rebooking_option(
            journey_id=1,
            flight_code="DL402",
            airline="Delta Air Lines",
            departure_iso="2026-10-15T17:00:00Z",
            arrival_iso="2026-10-15T21:00:00Z",
            stops=0,
            layover_details="Direct flight",
            added_cost_cents=10000,
            booking_url="https://delta.com"
        )
        self.resolver.adjudicate_rebooking(1, 1)
        self.assertEqual(self.resolver.get_proposal_status(1), "DISQUALIFIED")

        # Cannot confirm a disqualified flight
        with self.assertRaises(ValueError):
            self.resolver.confirm_rebooking(1, 1)

    def test_adjudicate_budget_clamp_disqualified(self):
        self.resolver.register_journey("LHR", "JFK", "2026-10-15T18:00:00Z", 20000, 1, 60, "SPEED_FIRST")
        self.resolver.report_disruption(1, "VS003", "CANCELLED", "Cancelled")

        # Flight costs $350 (exceeds $200 max)
        mock_gl.message.sender_address = Address(self.agent)
        self.resolver.propose_rebooking_option(
            journey_id=1,
            flight_code="AF022",
            airline="Air France",
            departure_iso="2026-10-15T12:00:00Z",
            arrival_iso="2026-10-15T16:00:00Z",
            stops=1,
            layover_details="CDG 120 mins",
            added_cost_cents=35000,
            booking_url="https://airfrance.com"
        )

        # Even if LLM erroneously returns QUALIFIED, deterministic clamp enforces DISQUALIFIED
        mock_gl.eq_principle.mock_response = json.dumps({
            "decision": "QUALIFIED",
            "feasibility_score": 95,
            "deadline_met": True,
            "budget_met": False,
            "rationale": "Arrives early."
        })

        self.resolver.adjudicate_rebooking(1, 1)
        self.assertEqual(self.resolver.get_proposal_status(1), "DISQUALIFIED")

    def test_adjudicate_borderline_and_traveller_override(self):
        self.resolver.register_journey("LHR", "JFK", "2026-10-15T18:00:00Z", 20000, 1, 60, "SPEED_FIRST")
        self.resolver.report_disruption(1, "VS003", "CANCELLED", "Cancelled")

        # EI105 with tight 45 min connection
        mock_gl.message.sender_address = Address(self.agent)
        self.resolver.propose_rebooking_option(
            journey_id=1,
            flight_code="EI105",
            airline="Aer Lingus",
            departure_iso="2026-10-15T11:00:00Z",
            arrival_iso="2026-10-15T16:30:00Z",
            stops=1,
            layover_details="DUB 45 mins",
            added_cost_cents=12000,
            booking_url="https://aerlingus.com"
        )

        self.resolver.adjudicate_rebooking(1, 1)
        self.assertEqual(self.resolver.get_proposal_status(1), "BORDERLINE_REVIEW")

        # Intruder cannot override
        mock_gl.message.sender_address = Address(self.intruder)
        with self.assertRaises(Exception):
            self.resolver.traveller_override(1, 1, approve=True)

        # Traveller approves override
        mock_gl.message.sender_address = Address(self.traveller)
        self.resolver.traveller_override(1, 1, approve=True)
        self.assertEqual(self.resolver.get_proposal_status(1), "QUALIFIED")

        # Now traveller can confirm
        self.resolver.confirm_rebooking(1, 1)
        self.assertEqual(self.resolver.get_journey_status(1), "RESOLVED")

    def test_cancel_journey_access_control(self):
        self.resolver.register_journey("LHR", "JFK", "2026-10-15T18:00:00Z", 20000, 1, 60, "SPEED_FIRST")

        mock_gl.message.sender_address = Address(self.intruder)
        with self.assertRaises(Exception):
            self.resolver.cancel_journey(1)

        mock_gl.message.sender_address = Address(self.traveller)
        self.resolver.cancel_journey(1)
        self.assertEqual(self.resolver.get_journey_status(1), "CANCELLED")

    def test_markdown_wrapped_response_sanitization(self):
        self.resolver.register_journey("LHR", "JFK", "2026-10-15T18:00:00Z", 20000, 1, 60, "SPEED_FIRST")
        self.resolver.report_disruption(1, "VS003", "CANCELLED", "Cancelled")
        mock_gl.message.sender_address = Address(self.agent)
        self.resolver.propose_rebooking_option(1, "BA177", "BA", "13:00", "16:00", 0, "Direct", 10000, "http")

        mock_gl.eq_principle.mock_response = """```json
{
  "decision": "QUALIFIED",
  "feasibility_score": 94,
  "deadline_met": true,
  "budget_met": true,
  "rationale": "Direct flight satisfies all timing constraints."
}
```"""
        result = self.resolver.adjudicate_rebooking(1, 1)
        parsed = json.loads(result)
        self.assertEqual(parsed["decision"], "QUALIFIED")
        self.assertEqual(self.resolver.get_proposal_status(1), "QUALIFIED")

    def test_nonexistent_ids(self):
        with self.assertRaises(ValueError):
            self.resolver.report_disruption(999, "BA", "CANCELLED", "X")
        with self.assertRaises(ValueError):
            self.resolver.propose_rebooking_option(999, "BA", "BA", "12", "14", 0, "", 10, "")
        with self.assertRaises(ValueError):
            self.resolver.adjudicate_rebooking(999, 1)
        with self.assertRaises(ValueError):
            self.resolver.confirm_rebooking(999, 1)
        with self.assertRaises(ValueError):
            self.resolver.cancel_journey(999)

        self.assertIn("Journey not found: 999", self.resolver.get_journey(999))
        self.assertIn("Proposal not found: 999", self.resolver.get_proposal(999))
        self.assertEqual(self.resolver.get_journey_status(999), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
