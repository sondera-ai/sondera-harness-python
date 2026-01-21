"""Life Sciences Clinical Trial Recruitment Agent using LangGraph with Sondera SDK.

Uses rule-based clinical trial eligibility assessment without LLM calls for predictable testing.

Quickstart:
  1. Install: uv pip install -e ../archetypes && uv pip install -e .
  2. Run: uv run python -m langgraph_examples.life_sciences_agent
"""

import argparse
import asyncio
from typing import Any, TypedDict, cast

from archetypes.healthcare import (
    EligibilityResult,
    MockEHRSimulator,
    ParsedPatient,
    PatientRecord,
    TrialProtocol,
    create_sample_patients,
    create_sample_trial,
    rule_based_assessment,
)
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph

from sondera.harness import SonderaRemoteHarness
from sondera.langgraph import SonderaGraph
from sondera.types import Agent, Parameter, Tool


class TrialState(TypedDict, total=False):
    trial_id: str
    hospital_ids: list[str]
    protocol: TrialProtocol
    patient_records: list[PatientRecord]
    parsed_patients: list[ParsedPatient]
    eligibility_results: list[EligibilityResult]
    report: str
    messages: list[BaseMessage]


def build_recruitment_graph(
    protocol_store: dict[str, TrialProtocol], ehr: MockEHRSimulator
) -> StateGraph:
    """Build the recruitment graph as a LangGraph StateGraph."""

    def load_protocol(state: TrialState) -> dict[str, Any]:
        trial_id = state.get("trial_id", "NCT05543210")
        protocol = protocol_store.get(trial_id)
        if not protocol:
            raise ValueError(f"Unknown trial id: {trial_id}")
        messages = list(state.get("messages", []))
        messages.append(AIMessage(content=f"Loaded trial protocol: {protocol.title}"))
        return {"protocol": protocol, "messages": messages}

    def query_ehr(state: TrialState) -> dict[str, Any]:
        hospital_ids = state.get("hospital_ids", [])
        patient_records: list[PatientRecord] = []
        for hospital_id in hospital_ids:
            patient_records.extend(ehr.get_patients(hospital_id))
        messages = list(state.get("messages", []))
        messages.append(
            AIMessage(content=f"Retrieved {len(patient_records)} patient records")
        )
        return {"patient_records": patient_records, "messages": messages}

    def parse_notes(state: TrialState) -> dict[str, Any]:
        parsed = [
            ParsedPatient(
                mrn=record.demographics.mrn,
                patient_name=f"{record.demographics.first_name} {record.demographics.last_name}",
                hospital_id=record.hospital_id,
                note_summary=record.notes[0].content[:100]
                if record.notes
                else "No notes",
            )
            for record in state.get("patient_records", [])
        ]
        messages = list(state.get("messages", []))
        messages.append(AIMessage(content=f"Parsed {len(parsed)} patient notes"))
        return {"parsed_patients": parsed, "messages": messages}

    def check_eligibility(state: TrialState) -> dict[str, Any]:
        protocol = state.get("protocol")
        if protocol is None:
            raise ValueError("Protocol not loaded")
        results = [
            EligibilityResult(
                mrn=record.demographics.mrn,
                patient_name=f"{record.demographics.first_name} {record.demographics.last_name}",
                hospital_id=record.hospital_id,
                assessment=rule_based_assessment(record, protocol),
            )
            for record in state.get("patient_records", [])
        ]
        results.sort(
            key=lambda r: (not r.assessment.eligible, -r.assessment.confidence_score)
        )
        messages = list(state.get("messages", []))
        eligible_count = len([r for r in results if r.assessment.eligible])
        messages.append(
            AIMessage(
                content=f"Assessed {len(results)} patients, found {eligible_count} potentially eligible"
            )
        )
        return {"eligibility_results": results, "messages": messages}

    def generate_report(state: TrialState) -> dict[str, Any]:
        protocol = state.get("protocol")
        if protocol is None:
            raise ValueError("Protocol not loaded")
        results = state.get("eligibility_results", [])
        eligible = [r for r in results if r.assessment.eligible]

        lines = [
            "=== CLINICAL TRIAL RECRUITMENT REPORT ===",
            f"Trial: {protocol.trial_id} - {protocol.title}",
            f"Condition: {protocol.condition} | Phase: {protocol.phase}",
            f"Target Enrollment: {protocol.target_enrollment}",
            "",
            "SCREENING SUMMARY:",
            f"Total Patients Screened: {len(results)}",
            f"Eligible Candidates: {len(eligible)}",
            f"Eligibility Rate: {len(eligible) / len(results) * 100:.1f}%"
            if results
            else "N/A",
            "",
            "PATIENT DETAILS:",
        ]

        for idx, result in enumerate(results, start=1):
            status = "✅ ELIGIBLE" if result.assessment.eligible else "❌ INELIGIBLE"
            lines.append(
                f"\n{idx}. {result.patient_name} (MRN: {result.mrn}, Hospital: {result.hospital_id})"
            )
            lines.append(
                f"   Status: {status} [Confidence: {result.assessment.confidence_score:.2f}]"
            )
            lines.append(f"   Reasoning: {result.assessment.reasoning}")
            if result.assessment.matching_inclusion:
                lines.append(
                    "   ✓ Inclusion: " + ", ".join(result.assessment.matching_inclusion)
                )
            if result.assessment.matching_exclusion:
                lines.append(
                    "   ✗ Exclusion: " + ", ".join(result.assessment.matching_exclusion)
                )

        report = "\n".join(lines)
        messages = list(state.get("messages", []))
        messages.append(AIMessage(content="Generated recruitment report"))
        return {"report": report, "messages": messages}

    graph = StateGraph(TrialState)
    graph.add_node("load_protocol", load_protocol)
    graph.add_node("query_ehr", query_ehr)
    graph.add_node("parse_notes", parse_notes)
    graph.add_node("check_eligibility", check_eligibility)
    graph.add_node("generate_report", generate_report)
    graph.set_entry_point("load_protocol")
    graph.add_edge("load_protocol", "query_ehr")
    graph.add_edge("query_ehr", "parse_notes")
    graph.add_edge("parse_notes", "check_eligibility")
    graph.add_edge("check_eligibility", "generate_report")
    graph.add_edge("generate_report", END)
    return graph


async def main():
    parser = argparse.ArgumentParser(
        description="Run Life Sciences Clinical Trial Recruitment Agent"
    )
    parser.add_argument("--trial-id", default="NCT05543210")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    # Set up mock data using archetypes
    ehr = MockEHRSimulator()
    ehr.add_hospital("hospital_alpha", create_sample_patients("hospital_alpha"))
    ehr.add_hospital("hospital_beta", create_sample_patients("hospital_beta"))
    protocol_store = {"NCT05543210": create_sample_trial()}

    # Create Sondera agent
    sondera_agent = Agent(
        id="life-sciences-recruitment-agent",
        provider_id="langgraph",
        name="life-sciences-recruitment-agent",
        description="AI agent for identifying eligible patients for clinical trials using EHR data",
        instruction="Analyze patient records against clinical trial criteria to identify eligible candidates",
        tools=[
            Tool(
                name="load_protocol",
                description="Load clinical trial protocol by ID",
                parameters=[
                    Parameter(
                        name="trial_id",
                        description="Clinical trial identifier",
                        type="string",
                    )
                ],
                response="TrialProtocol",
            ),
            Tool(
                name="query_ehr",
                description="Query electronic health records for patient data",
                parameters=[
                    Parameter(
                        name="hospital_ids",
                        description="List of hospital identifiers",
                        type="array",
                    )
                ],
                response="list[PatientRecord]",
            ),
            Tool(
                name="check_eligibility",
                description="Check patient eligibility against trial criteria",
                parameters=[],
                response="list[EligibilityResult]",
            ),
            Tool(
                name="generate_report",
                description="Generate recruitment report with eligible patients",
                parameters=[],
                response="string",
            ),
        ],
    )
    harness = SonderaRemoteHarness(agent=sondera_agent)
    graph = build_recruitment_graph(protocol_store, ehr)
    compiled_graph = graph.compile()
    wrapped_graph = SonderaGraph(compiled_graph, harness=harness, enforce=args.enforce)

    initial_state: TrialState = {
        "trial_id": args.trial_id,
        "hospital_ids": ["hospital_alpha", "hospital_beta"],
        "messages": [
            HumanMessage(
                content=f"Analyze clinical trial {args.trial_id} for patient recruitment"
            )
        ],
    }

    print("\n🔬 Starting Clinical Trial Recruitment Analysis")
    print(f"Trial ID: {args.trial_id}")
    print(
        f"Enforcement Mode: {'Enabled' if args.enforce else 'Disabled (Monitor Only)'}"
    )
    print("-" * 60)

    result = await wrapped_graph.ainvoke(cast(dict[str, Any], initial_state))

    print("\n" + result["report"])
    print("\n✨ Analysis complete!")


if __name__ == "__main__":
    asyncio.run(main())
