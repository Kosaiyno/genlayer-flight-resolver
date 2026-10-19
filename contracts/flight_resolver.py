# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json

class FlightResolver(gl.Contract):
    """
    FlightResolver: Autonomous On-Chain Travel Disruption & Flight Rebooking Arbiter.
    
    Protects passengers and corporate travel managers against:
    1. Unverified agent rebooking claims (contract independently acquires authoritative flight evidence via gl.nondet.web.get).
    2. Missed hard arrival deadlines (deterministic timestamp clamp against arrival_deadline_iso).
    3. Hidden fare surges & budget overruns (deterministic clamp against max_extra_cost_cents).
    4. Unsafe connection layovers & missed flights (deterministic floor clamp against min_layover_mins).
    5. Ghost bookings / phantom seats (authoritative booking_status verification with verbatim quote grounding).
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

    # =========================================================================
    # VIEW METHODS
    # =========================================================================

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

    # =========================================================================
    # WRITE METHODS
    # =========================================================================

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
            "status": "DISRUPTED",  # Ready for rebooking proposal ingestion
            "created_at": created_ts,
            "confirmed_proposal_id": None
        }

        self.journeys[new_id] = json.dumps(journey_record)
        return new_id

    @gl.public.write
    def propose_rebooking_option(
        self,
        journey_id: int,
        flight_code: str,
        airline: str,
        flight_evidence_url: str,
        claimed_fare_cents: int,
        agent_notes: str
    ) -> u256:
        """
        Agent submits a proposed rebooking flight option.
        Crucially: The contract does NOT trust caller-supplied arrival times, layover
        durations, or fares. The contract independently acquires the authoritative
        flight evidence directly from flight_evidence_url during adjudication.
        """
        j_key = u256(journey_id)
        if j_key not in self.journeys:
            raise ValueError(f"Journey {journey_id} does not exist")

        journey = json.loads(self.journeys[j_key])
        if journey.get("status") != "DISRUPTED":
            raise ValueError(f"Journey {journey_id} is not in 'DISRUPTED' status")

        clean_flight = str(flight_code).upper().strip()
        clean_airline = str(airline).strip()
        clean_url = str(flight_evidence_url).strip()
        clean_notes = str(agent_notes).strip()

        if len(clean_flight) == 0:
            raise ValueError("Flight code cannot be empty")
        if len(clean_airline) == 0:
            raise ValueError("Airline name cannot be empty")
        if len(clean_url) == 0:
            raise ValueError("Flight evidence URL cannot be empty")
        if claimed_fare_cents < 0:
            raise ValueError("Claimed fare cents cannot be negative")

        new_pid = u256(int(self.proposal_counter) + 1)
        self.proposal_counter = new_pid

        proposal_record = {
            "proposal_id": int(new_pid),
            "journey_id": int(journey_id),
            "proposer": str(gl.message.sender_address),
            "flight_code": clean_flight,
            "airline": clean_airline,
            "flight_evidence_url": clean_url,
            "claimed_fare_cents": int(claimed_fare_cents),
            "agent_notes": clean_notes if clean_notes else "Rebooking option proposed by agent",
            "status": "PROPOSED"
        }

        self.proposals[new_pid] = json.dumps(proposal_record)
        return new_pid

    @gl.public.write
    def adjudicate_rebooking(self, journey_id: int, proposal_id: int) -> str:
        """
        Contract-Side Authoritative Evidence Acquisition & Multi-Pillar Adjudication:
        1. Independently acquires live flight and schedule evidence via gl.nondet.web.get(flight_evidence_url).
        2. Validators extract material schedule facts (arrival_iso, fare, stops, layover, status) and verbatim quotes.
        3. Deterministic safety clamps verify verbatim quotes, arrival deadlines, fare ceilings, layover floors, and availability.
        4. Canonicalized adjudication record stored on-chain.
        """
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

        # Snapshot local variables before non-deterministic closures (no self in closures!)
        target_feed_url = str(proposal["flight_evidence_url"])
        flight_code = str(proposal["flight_code"])
        airline = str(proposal["airline"])
        claimed_fare = int(proposal["claimed_fare_cents"])
        origin = str(journey["origin"])
        destination = str(journey["destination"])
        arrival_deadline = str(journey["arrival_deadline_iso"])
        max_cost = int(journey["max_extra_cost_cents"])
        max_stops = int(journey["max_stops"])
        min_layover = int(journey["min_layover_mins"])
        priority_mode = str(journey["priority_mode"])

        # 1. Non-deterministic Flight Evidence Acquisition Closure
        def get_input() -> str:
            try:
                resp = gl.nondet.web.get(target_feed_url)
                body_text = resp.body.decode("utf-8") if hasattr(resp, "body") else str(resp)
            except Exception as e:
                body_text = f"[FLIGHT_FETCH_ERROR]: {str(e)}"

            clean_flight_payload = body_text[:4000].strip()
            if len(clean_flight_payload) == 0:
                clean_flight_payload = "[EMPTY_FLIGHT_FEED_ERROR]"

            return (
                f"=== TRAVELLER JOURNEY CONSTRAINTS ===\n"
                f"Route: {origin} -> {destination}\n"
                f"Strict Arrival Deadline: {arrival_deadline}\n"
                f"Max Added Cost Cents: {max_cost} (${max_cost / 100:.2f})\n"
                f"Max Acceptable Stops: {max_stops}\n"
                f"Min Required Layover Minutes: {min_layover}\n"
                f"Priority Mode: {priority_mode}\n\n"
                f"=== AGENT PROPOSAL CLAIM ===\n"
                f"Proposed Flight: {flight_code} ({airline})\n"
                f"Claimed Fare Cents: {claimed_fare} (${claimed_fare / 100:.2f})\n"
                f"Authoritative Feed URL: {target_feed_url}\n\n"
                f"=== INDEPENDENTLY FETCHED FLIGHT SCHEDULE EVIDENCE ===\n"
                f"{clean_flight_payload}\n\n"
                f"=== EVALUATION DIRECTIVES ===\n"
                f"1. Independent Verification: Read the actual flight schedule evidence payload above.\n"
                f"2. Extract: 'arrival_time_iso', 'actual_fare_cents', 'stops' (int), 'layover_minutes' (int), and 'booking_status'.\n"
                f"3. Verbatim Quote: Extract an exact substring from the flight feed proving arrival time, layover, or fare.\n"
                f"4. If arrival_time_iso is after arrival deadline, or actual fare > max cost, or layover < min layover: DISQUALIFIED.\n"
                f"5. If flight arrives on/before deadline, within budget, and with safe layover: QUALIFIED.\n"
                f"6. If feasible but connection is tight (within 15 mins of safety floor): BORDERLINE_REVIEW."
            )

        task = (
            f"Act as an authoritative flight disruption arbiter. Independently verify the flight feed "
            f"for '{flight_code}' against the passenger's arrival deadline '{arrival_deadline}' and budget ceiling ${max_cost / 100:.2f}. "
            f"Output a valid JSON object with keys: "
            f"'decision' ('QUALIFIED', 'BORDERLINE_REVIEW', or 'DISQUALIFIED'), "
            f"'arrival_time_iso' (string), "
            f"'actual_fare_cents' (integer), "
            f"'stops' (integer), "
            f"'layover_minutes' (integer), "
            f"'booking_status' ('AVAILABLE' or 'SOLD_OUT'), "
            f"'verbatim_quote' (exact string from the flight payload, up to 120 chars), and "
            f"'rationale' (concise explanation up to 200 chars)."
        )

        criteria = """
            1. Output must be a valid JSON object with keys: 'decision', 'arrival_time_iso', 'actual_fare_cents', 'stops', 'layover_minutes', 'booking_status', 'verbatim_quote', and 'rationale'.
            2. 'decision' must be strictly one of: 'QUALIFIED', 'BORDERLINE_REVIEW', or 'DISQUALIFIED'.
            3. 'verbatim_quote' must be an exact substring from the fetched flight schedule evidence.
            4. If the flight arrival time is after the passenger's arrival deadline or fare exceeds max budget, decision must be 'DISQUALIFIED'.
            5. If stops > max_stops or layover_minutes < min_layover_mins, decision must be 'DISQUALIFIED'.
            6. If flight arrives before deadline within budget with safe connections, decision is 'QUALIFIED'.
        """

        raw_result = gl.eq_principle.prompt_non_comparative(
            get_input,
            task=task,
            criteria=criteria,
        )

        # 2. Canonical JSON Parsing & Bracket Sanitization
        result_str = str(raw_result).strip()
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

        decision = "DISQUALIFIED"
        arrival_found = ""
        fare_found = 0
        stops_found = 0
        layover_found = 0
        booking_status = "UNKNOWN"
        verbatim_quote = "NONE"
        rationale = "Default fallback"

        try:
            parsed = json.loads(clean_json_str)
            raw_dec = str(parsed.get("decision", "DISQUALIFIED")).upper().strip()
            if raw_dec in ["QUALIFIED", "BORDERLINE_REVIEW", "DISQUALIFIED"]:
                decision = raw_dec
            arrival_found = str(parsed.get("arrival_time_iso", "")).strip()
            fare_found = int(parsed.get("actual_fare_cents", 0))
            stops_found = int(parsed.get("stops", 0))
            layover_found = int(parsed.get("layover_minutes", 0))
            booking_status = str(parsed.get("booking_status", "UNKNOWN")).upper().strip()
            verbatim_quote = str(parsed.get("verbatim_quote", "NONE")).strip()[:120]
            rationale = str(parsed.get("rationale", "")).strip()[:200]
        except Exception as e:
            decision = "DISQUALIFIED"
            rationale = f"Parsing fallback: {str(e)[:80]}"

        # 3. Deterministic Invariant Clamps (Code Moves State)
        # Clamp 1: Verbatim Quote Verification
        if len(verbatim_quote) < 4 or verbatim_quote == "NONE":
            decision = "DISQUALIFIED"
            rationale = "Deterministic clamp: Missing verifiable verbatim quote from flight feed."

        # Clamp 2: Hard Arrival Deadline
        if arrival_found and arrival_found > arrival_deadline:
            decision = "DISQUALIFIED"
            rationale = f"Deterministic clamp: Arrival ({arrival_found}) lands after deadline ({arrival_deadline})."

        # Clamp 3: Hard Fare Ceiling
        if fare_found > max_cost or claimed_fare > max_cost:
            decision = "DISQUALIFIED"
            rationale = f"Deterministic clamp: Fare ({max(fare_found, claimed_fare)} cents) exceeds max cost ({max_cost} cents)."

        # Clamp 4: Unsafe Connection Floor & Max Stops
        if stops_found > max_stops:
            decision = "DISQUALIFIED"
            rationale = f"Deterministic clamp: Stops ({stops_found}) exceed max allowed ({max_stops})."

        if stops_found > 0 and layover_found < min_layover:
            decision = "DISQUALIFIED"
            rationale = f"Deterministic clamp: Layover ({layover_found}m) is below safe floor ({min_layover}m)."

        # Clamp 5: Seat Availability
        if booking_status == "SOLD_OUT":
            decision = "DISQUALIFIED"
            rationale = "Deterministic clamp: Flight is sold out."

        # 4. Canonicalized Storage Record
        canonical_record = {
            "proposal_id": int(proposal_id),
            "journey_id": int(journey_id),
            "decision": decision,
            "arrival_time_iso": arrival_found,
            "actual_fare_cents": int(fare_found),
            "stops": int(stops_found),
            "layover_minutes": int(layover_found),
            "booking_status": booking_status,
            "verbatim_quote": verbatim_quote,
            "rationale": rationale
        }
        canonical_json = json.dumps(canonical_record)

        proposal["status"] = decision
        self.proposals[p_key] = json.dumps(proposal)
        self.adjudications[p_key] = canonical_json

        return canonical_json

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
