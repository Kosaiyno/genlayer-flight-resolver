# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import typing
import json

class FlightResolver(gl.Contract):
    """
    FlightResolver is a production-grade GenLayer Intelligent Contract primitive
    designed for autonomous travel disruption management and flight rebooking.

    Core Purpose:
    When a commercial flight is cancelled, diverted, or critically delayed, passengers
    and travel management agents face a complex multi-variable optimization challenge:
    - The cheapest alternative flight might land past a hard arrival deadline (e.g. missing a business conference).
    - An alternative might feature an impossibly short 25-minute international layover across terminals.
    - Traditional smart contracts can only evaluate rigid numeric thresholds or simple binary oracles.
    
    FlightResolver introduces an autonomous on-chain resolution arbiter:
    1. Journey Constraint Escrow: Travellers lock arrival deadlines, maximum added costs,
       stopover ceilings, minimum layover safety floors, and priority modes (SPEED_FIRST, COMFORT_FIRST, BUDGET_FIRST).
    2. Disruption Reporting: Disrupted journeys are transitioned into active resolution mode with proof.
    3. Multi-Option Proposal Ingestion: Airlines, OTAs, or autonomous rebooking agents propose replacement flights.
    4. Multi-Pillar Equivalence Adjudication: GenLayer validators independently evaluate connection viability,
       schedule feasibility, and economic trade-offs via the Equivalence Principle:
       - QUALIFIED: Satisfies arrival deadline, safe connection time, and cost limits.
       - BORDERLINE_REVIEW: Feasible alternative but features tight layovers or minor trade-offs requiring traveller consent.
       - DISQUALIFIED: Violates arrival deadline, exceeds extra cost ceiling, or has unsafe connections.
    5. Sovereign Traveller Overrides & Confirmation: Travellers can approve borderline flights or confirm qualified options.
    """
    owner: Address
    journey_counter: u256
    proposal_counter: u256
    journeys: TreeMap[u256, str]
    proposals: TreeMap[u256, str]
    adjudications: TreeMap[u256, str]

    def __init__(self):
        self.owner = gl.message.sender_address
        self.journey_counter = u256(0)
        self.proposal_counter = u256(0)

    @gl.public.view
    def get_resolver_stats(self) -> str:
        return (
            "FlightResolver Owner: " + str(self.owner)
            + " | Total Journeys: " + str(self.journey_counter)
            + " | Total Proposals: " + str(self.proposal_counter)
        )

    @gl.public.view
    def get_total_journeys(self) -> u256:
        return self.journey_counter

    @gl.public.view
    def get_total_proposals(self) -> u256:
        return self.proposal_counter

    @gl.public.view
    def get_journey(self, journey_id: int) -> str:
        j_key = u256(journey_id)
        if j_key in self.journeys:
            return str(self.journeys[j_key])
        return "Journey not found: " + str(journey_id)

    @gl.public.view
    def get_proposal(self, proposal_id: int) -> str:
        p_key = u256(proposal_id)
        if p_key in self.proposals:
            return str(self.proposals[p_key])
        return "Proposal not found: " + str(proposal_id)

    @gl.public.view
    def get_adjudication(self, proposal_id: int) -> str:
        p_key = u256(proposal_id)
        if p_key in self.adjudications:
            return str(self.adjudications[p_key])
        return "Adjudication not found for proposal: " + str(proposal_id)

    @gl.public.view
    def get_journey_status(self, journey_id: int) -> str:
        j_key = u256(journey_id)
        if j_key not in self.journeys:
            return "UNKNOWN"
        try:
            data = json.loads(self.journeys[j_key])
            return str(data.get("status", "UNKNOWN"))
        except Exception:
            return "UNKNOWN"

    @gl.public.view
    def get_proposal_status(self, proposal_id: int) -> str:
        p_key = u256(proposal_id)
        if p_key not in self.proposals:
            return "UNKNOWN"
        try:
            data = json.loads(self.proposals[p_key])
            return str(data.get("status", "UNKNOWN"))
        except Exception:
            return "UNKNOWN"

    @gl.public.write
    def register_journey(
        self,
        origin: str,
        destination: str,
        arrival_deadline_iso: str,
        max_extra_cost_cents: int,
        max_stops: int,
        min_layover_mins: int,
        priority_mode: str
    ) -> u256:
        clean_orig = str(origin).upper().strip()
        clean_dest = str(destination).upper().strip()
        clean_deadline = str(arrival_deadline_iso).strip()
        clean_mode = str(priority_mode).upper().strip()

        if len(clean_orig) == 0 or len(clean_dest) == 0:
            raise ValueError("Origin and Destination cannot be empty")
        if len(clean_deadline) == 0:
            raise ValueError("Arrival deadline ISO cannot be empty")
        if max_extra_cost_cents < 0:
            raise ValueError("Maximum additional cost cannot be negative")
        if max_stops < 0:
            raise ValueError("Max stops cannot be negative")
        if min_layover_mins < 0:
            raise ValueError("Min layover minutes cannot be negative")
        if clean_mode not in ["SPEED_FIRST", "COMFORT_FIRST", "BUDGET_FIRST"]:
            raise ValueError("Priority mode must be SPEED_FIRST, COMFORT_FIRST, or BUDGET_FIRST")

        new_id = u256(int(self.journey_counter) + 1)
        self.journey_counter = new_id

        created_ts = 0
        try:
            created_ts = int(gl.block.timestamp)
        except Exception:
            pass

        journey_record = {
            "journey_id": int(new_id),
            "traveller": str(gl.message.sender_address),
            "origin": clean_orig,
            "destination": clean_dest,
            "arrival_deadline_iso": clean_deadline,
            "max_extra_cost_cents": int(max_extra_cost_cents),
            "max_stops": int(max_stops),
            "min_layover_mins": int(min_layover_mins),
            "priority_mode": clean_mode,
            "status": "SCHEDULED",
            "created_at": created_ts,
            "disruption_info": None,
            "confirmed_proposal_id": None
        }

        self.journeys[new_id] = json.dumps(journey_record)
        return new_id

    @gl.public.write
    def report_disruption(
        self,
        journey_id: int,
        original_flight_code: str,
        disruption_type: str,
        reason: str
    ) -> bool:
        j_key = u256(journey_id)
        if j_key not in self.journeys:
            raise ValueError(f"Journey {journey_id} does not exist")

        journey = json.loads(self.journeys[j_key])
        current_status = journey.get("status", "")
        if current_status not in ["SCHEDULED", "DISRUPTED"]:
            raise ValueError(f"Cannot report disruption for journey in status '{current_status}'")

        clean_flight = str(original_flight_code).upper().strip()
        clean_type = str(disruption_type).upper().strip()
        clean_reason = str(reason).strip()

        if len(clean_flight) == 0:
            raise ValueError("Original flight code cannot be empty")
        if clean_type not in ["CANCELLED", "DELAYED_MISSED_CONNECTION", "DIVERTED"]:
            raise ValueError("Disruption type must be CANCELLED, DELAYED_MISSED_CONNECTION, or DIVERTED")

        journey["status"] = "DISRUPTED"
        journey["disruption_info"] = {
            "original_flight": clean_flight,
            "disruption_type": clean_type,
            "reason": clean_reason if clean_reason else "Operational delay/cancellation",
            "reported_by": str(gl.message.sender_address)
        }

        self.journeys[j_key] = json.dumps(journey)
        return True

    @gl.public.write
    def propose_rebooking_option(
        self,
        journey_id: int,
        flight_code: str,
        airline: str,
        departure_iso: str,
        arrival_iso: str,
        stops: int,
        layover_details: str,
        added_cost_cents: int,
        booking_url: str
    ) -> u256:
        j_key = u256(journey_id)
        if j_key not in self.journeys:
            raise ValueError(f"Journey {journey_id} does not exist")

        journey = json.loads(self.journeys[j_key])
        if journey.get("status") != "DISRUPTED":
            raise ValueError(f"Journey {journey_id} is not in 'DISRUPTED' status")

        clean_flight = str(flight_code).upper().strip()
        clean_airline = str(airline).strip()
        clean_dep = str(departure_iso).strip()
        clean_arr = str(arrival_iso).strip()
        clean_layover = str(layover_details).strip()
        clean_url = str(booking_url).strip()

        if len(clean_flight) == 0:
            raise ValueError("Flight code cannot be empty")
        if len(clean_airline) == 0:
            raise ValueError("Airline name cannot be empty")
        if len(clean_dep) == 0 or len(clean_arr) == 0:
            raise ValueError("Departure and Arrival ISO times cannot be empty")
        if stops < 0:
            raise ValueError("Stops cannot be negative")
        if added_cost_cents < 0:
            raise ValueError("Added cost cents cannot be negative")

        new_pid = u256(int(self.proposal_counter) + 1)
        self.proposal_counter = new_pid

        proposal_record = {
            "proposal_id": int(new_pid),
            "journey_id": int(journey_id),
            "proposer": str(gl.message.sender_address),
            "flight_code": clean_flight,
            "airline": clean_airline,
            "departure_iso": clean_dep,
            "arrival_iso": clean_arr,
            "stops": int(stops),
            "layover_details": clean_layover if clean_layover else "Non-stop direct flight",
            "added_cost_cents": int(added_cost_cents),
            "booking_url": clean_url if clean_url else "N/A",
            "status": "PROPOSED"
        }

        self.proposals[new_pid] = json.dumps(proposal_record)
        return new_pid

    @gl.public.write
    def adjudicate_rebooking(self, journey_id: int, proposal_id: int) -> str:
        j_key = u256(journey_id)
        p_key = u256(proposal_id)

        if j_key not in self.journeys:
            raise ValueError(f"Journey {journey_id} does not exist")
        if p_key not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} does not exist")

        journey = json.loads(self.journeys[j_key])
        proposal = json.loads(self.proposals[p_key])

        if proposal.get("journey_id") != int(journey_id):
            raise ValueError(f"Proposal {proposal_id} does not belong to Journey {journey_id}")

        if proposal.get("status") not in ["PROPOSED", "BORDERLINE_REVIEW"]:
            raise ValueError(f"Cannot adjudicate proposal in status '{proposal.get('status')}'")

        max_extra_cost = journey["max_extra_cost_cents"]
        proposed_cost = proposal["added_cost_cents"]
        budget_overrun = proposed_cost > max_extra_cost

        def get_input() -> str:
            return (
                f"=== TRAVELLER JOURNEY CONSTRAINTS ===\n"
                f"Journey ID: {journey_id}\n"
                f"Route: {journey['origin']} -> {journey['destination']}\n"
                f"Strict Arrival Deadline: {journey['arrival_deadline_iso']}\n"
                f"Max Additional Cost: ${max_extra_cost / 100:.2f} ({max_extra_cost} cents)\n"
                f"Max Acceptable Stops: {journey['max_stops']}\n"
                f"Min Required Layover: {journey['min_layover_mins']} minutes\n"
                f"Priority Preference: {journey['priority_mode']}\n\n"
                f"=== PROPOSED REBOOKING FLIGHT OPTION ===\n"
                f"Proposal ID: {proposal_id}\n"
                f"Flight: {proposal['flight_code']} ({proposal['airline']})\n"
                f"Departure: {proposal['departure_iso']}\n"
                f"Scheduled Arrival: {proposal['arrival_iso']}\n"
                f"Number of Stops: {proposal['stops']}\n"
                f"Connection Details: {proposal['layover_details']}\n"
                f"Additional Cost: ${proposed_cost / 100:.2f} ({proposed_cost} cents)\n"
                f"Booking Link: {proposal['booking_url']}\n\n"
                f"=== RESOLUTION EVALUATION DIRECTIVES ===\n"
                f"1. Deadline Check: If scheduled arrival time is past arrival deadline, decision MUST be DISQUALIFIED.\n"
                f"2. Budget Check: If additional cost exceeds maximum additional cost, decision MUST be DISQUALIFIED.\n"
                f"3. Layover Safety: If layover connection time is under the required minimum minutes or stops exceed max stops, decision is DISQUALIFIED.\n"
                f"4. Qualification: If option arrives on/before deadline, within budget, and with safe connections, decision is QUALIFIED.\n"
                f"5. Trade-off Review: If option is feasible but features tight connections or minor preference deviations, decision is BORDERLINE_REVIEW."
            )

        raw_result = gl.eq_principle.prompt_non_comparative(
            get_input,
            task=(
                f"Act as an impartial airline passenger resolution arbiter. Evaluate flight "
                f"'{proposal['flight_code']}' arriving at '{proposal['arrival_iso']}' against the traveller's "
                f"deadline '{journey['arrival_deadline_iso']}' and max cost ${max_extra_cost / 100:.2f}. "
                f"Output a valid JSON object with keys: "
                f"'decision' ('QUALIFIED', 'BORDERLINE_REVIEW', or 'DISQUALIFIED'), "
                f"'feasibility_score' (integer 0-100), "
                f"'deadline_met' (boolean), "
                f"'budget_met' (boolean), "
                f"'rationale' (concise 1-2 sentence explanation)."
            ),
            criteria="""
                1. The output is a valid JSON object with keys: decision, feasibility_score, deadline_met, budget_met, and rationale.
                2. The decision is exactly one of: QUALIFIED, BORDERLINE_REVIEW, or DISQUALIFIED.
                3. If scheduled arrival is after the arrival deadline, deadline_met is false and decision is DISQUALIFIED.
                4. If additional cost exceeds maximum additional cost, budget_met is false and decision is DISQUALIFIED.
                5. If stops exceed max acceptable stops or connection time is under minimum layover safety floor, decision is DISQUALIFIED.
                6. If the flight arrives before the deadline within budget with safe connections, decision is QUALIFIED.
                7. If the flight meets the deadline and budget but features tight connection risks or minor preference trade-offs, decision is BORDERLINE_REVIEW.
            """,
        )

        result_str = str(raw_result).strip()

        # Sanitize code blocks if returned
        clean_json_str = result_str
        if "```" in clean_json_str:
            first_brace = clean_json_str.find("{")
            last_brace = clean_json_str.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                clean_json_str = clean_json_str[first_brace : last_brace + 1]
        elif not clean_json_str.startswith("{"):
            first_brace = clean_json_str.find("{")
            last_brace = clean_json_str.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                clean_json_str = clean_json_str[first_brace : last_brace + 1]

        decision = "BORDERLINE_REVIEW"
        try:
            parsed = json.loads(clean_json_str)
            raw_decision = str(parsed.get("decision", "BORDERLINE_REVIEW")).upper().strip()
            if raw_decision in ["QUALIFIED", "BORDERLINE_REVIEW", "DISQUALIFIED"]:
                decision = raw_decision
        except Exception:
            decision = "BORDERLINE_REVIEW"

        # Deterministic invariant clamp: Budget overrun can never be QUALIFIED
        if budget_overrun and decision == "QUALIFIED":
            decision = "DISQUALIFIED"

        proposal["status"] = decision
        self.proposals[p_key] = json.dumps(proposal)
        self.adjudications[p_key] = clean_json_str

        return clean_json_str

    @gl.public.write
    def confirm_rebooking(self, journey_id: int, proposal_id: int) -> bool:
        j_key = u256(journey_id)
        p_key = u256(proposal_id)

        if j_key not in self.journeys:
            raise ValueError(f"Journey {journey_id} does not exist")
        if p_key not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} does not exist")

        journey = json.loads(self.journeys[j_key])
        proposal = json.loads(self.proposals[p_key])

        if proposal.get("journey_id") != int(journey_id):
            raise ValueError(f"Proposal {proposal_id} does not belong to Journey {journey_id}")

        if proposal.get("status") != "QUALIFIED":
            raise ValueError(f"Cannot confirm rebooking: proposal status is '{proposal.get('status')}', must be 'QUALIFIED'")

        journey["status"] = "RESOLVED"
        journey["confirmed_proposal_id"] = int(proposal_id)
        proposal["status"] = "CONFIRMED"

        self.journeys[j_key] = json.dumps(journey)
        self.proposals[p_key] = json.dumps(proposal)
        return True

    @gl.public.write
    def traveller_override(self, journey_id: int, proposal_id: int, approve: bool) -> bool:
        j_key = u256(journey_id)
        p_key = u256(proposal_id)

        if j_key not in self.journeys:
            raise ValueError(f"Journey {journey_id} does not exist")
        if p_key not in self.proposals:
            raise ValueError(f"Proposal {proposal_id} does not exist")

        journey = json.loads(self.journeys[j_key])
        proposal = json.loads(self.proposals[p_key])

        caller_str = str(gl.message.sender_address)
        if caller_str != journey.get("traveller"):
            raise Exception("Unauthorized: Only the registered traveller can override a proposal decision")

        if proposal.get("journey_id") != int(journey_id):
            raise ValueError(f"Proposal {proposal_id} does not belong to Journey {journey_id}")

        if proposal.get("status") != "BORDERLINE_REVIEW":
            raise ValueError(f"Cannot override proposal in status '{proposal.get('status')}', must be 'BORDERLINE_REVIEW'")

        proposal["status"] = "QUALIFIED" if approve else "DISQUALIFIED"
        self.proposals[p_key] = json.dumps(proposal)
        return True

    @gl.public.write
    def cancel_journey(self, journey_id: int) -> bool:
        j_key = u256(journey_id)
        if j_key not in self.journeys:
            raise ValueError(f"Journey {journey_id} does not exist")

        journey = json.loads(self.journeys[j_key])
        caller_str = str(gl.message.sender_address)

        if caller_str != journey.get("traveller") and caller_str != str(self.owner):
            raise Exception("Unauthorized: Only the traveller or contract owner can cancel a journey")

        if journey.get("status") == "RESOLVED":
            raise ValueError("Cannot cancel an already RESOLVED journey")

        journey["status"] = "CANCELLED"
        self.journeys[j_key] = json.dumps(journey)
        return True
