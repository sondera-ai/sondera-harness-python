"""Life Sciences Clinical Trial Recruitment Agent using Pydantic AI with Sondera SDK.

Uses rule-based clinical trial eligibility assessment. No LLM calls — the agent
runs a deterministic pipeline to screen patients against trial criteria, with
Sondera governance tracking the trajectory.

Quickstart:
  1. Install: uv sync
  2. Set keys: sondera auth login
  3. Run: uv run python -m pydantic_ai_examples.life_sciences_agent

Suggested prompts:
- Analyze clinical trial NCT05543210 for patient recruitment.
- Screen patients from hospital_alpha for the diabetes trial.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import uuid

from archetypes.healthcare import (
    EligibilityResult,
    MockEHRSimulator,
    ParsedPatient,
    create_sample_patients,
    create_sample_trial,
    rule_based_assessment,
)

from sondera import Agent as SonderaAgent
from sondera import AgentCard, Parameter, ReActAgentCard, Tool
from sondera.harness import SonderaRemoteHarness

logger = logging.getLogger(__name__)


def build_sondera_agent() -> SonderaAgent:
    """Build the Sondera agent card for the life sciences pipeline."""
    return SonderaAgent(
        id="pydantic-lifesci-demo",
        provider="pydantic-ai",
        card=AgentCard.react(
            ReActAgentCard(
                system_instruction="Analyze patient records against clinical trial criteria to identify eligible candidates",
                tools=[
                    Tool(
                        name="load_protocol",
                        description="Load clinical trial protocol by ID",
                        parameters=[
                            Parameter(
                                name="trial_id",
                                description="Clinical trial identifier",
                                param_type="string",
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
                                param_type="array",
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
        ),
    )


async def run_recruitment_pipeline(
    trial_id: str,
    hospital_ids: list[str],
    harness: SonderaRemoteHarness,
) -> str:
    """Run the clinical trial recruitment pipeline with trajectory tracking."""
    from sondera.types import Event, ToolCall, ToolOutput

    # Set up mock data
    ehr = MockEHRSimulator()
    for hid in hospital_ids:
        ehr.add_hospital(hid, create_sample_patients(hid))
    protocol_store = {"NCT05543210": create_sample_trial()}

    sondera_agent = harness.agent
    assert sondera_agent is not None
    trajectory_id = harness.trajectory_id
    assert trajectory_id is not None

    # Step 1: Load protocol
    protocol = protocol_store.get(trial_id)
    if not protocol:
        raise ValueError(f"Unknown trial id: {trial_id}")

    await harness.adjudicate(
        Event(
            agent=sondera_agent,
            trajectory_id=trajectory_id,
            event=ToolCall(
                tool="load_protocol",
                arguments=f'{{"trial_id": "{trial_id}"}}',
                call_id="load-1",
            ),
        )
    )
    await harness.adjudicate(
        Event(
            agent=sondera_agent,
            trajectory_id=trajectory_id,
            event=ToolOutput.from_success("load-1", f"Loaded: {protocol.title}"),
        )
    )
    print(f"  Loaded trial protocol: {protocol.title}")

    # Step 2: Query EHR
    patient_records = []
    for hid in hospital_ids:
        patient_records.extend(ehr.get_patients(hid))

    await harness.adjudicate(
        Event(
            agent=sondera_agent,
            trajectory_id=trajectory_id,
            event=ToolCall(
                tool="query_ehr",
                arguments=f'{{"hospital_ids": {hospital_ids}}}',
                call_id="ehr-1",
            ),
        )
    )
    await harness.adjudicate(
        Event(
            agent=sondera_agent,
            trajectory_id=trajectory_id,
            event=ToolOutput.from_success(
                "ehr-1", f"Retrieved {len(patient_records)} patient records"
            ),
        )
    )
    print(f"  Retrieved {len(patient_records)} patient records")

    # Step 3: Parse notes
    parsed = [
        ParsedPatient(
            mrn=r.demographics.mrn,
            patient_name=f"{r.demographics.first_name} {r.demographics.last_name}",
            hospital_id=r.hospital_id,
            note_summary=r.notes[0].content[:100] if r.notes else "No notes",
        )
        for r in patient_records
    ]
    print(f"  Parsed {len(parsed)} patient notes")

    # Step 4: Check eligibility
    results = [
        EligibilityResult(
            mrn=r.demographics.mrn,
            patient_name=f"{r.demographics.first_name} {r.demographics.last_name}",
            hospital_id=r.hospital_id,
            assessment=rule_based_assessment(r, protocol),
        )
        for r in patient_records
    ]
    results.sort(
        key=lambda r: (not r.assessment.eligible, -r.assessment.confidence_score)
    )

    await harness.adjudicate(
        Event(
            agent=sondera_agent,
            trajectory_id=trajectory_id,
            event=ToolCall(tool="check_eligibility", arguments="{}", call_id="elig-1"),
        )
    )
    eligible_count = len([r for r in results if r.assessment.eligible])
    await harness.adjudicate(
        Event(
            agent=sondera_agent,
            trajectory_id=trajectory_id,
            event=ToolOutput.from_success(
                "elig-1", f"Assessed {len(results)} patients, {eligible_count} eligible"
            ),
        )
    )
    print(
        f"  Assessed {len(results)} patients, found {eligible_count} potentially eligible"
    )

    # Step 5: Generate report
    lines = [
        "=== CLINICAL TRIAL RECRUITMENT REPORT ===",
        f"Trial: {protocol.trial_id} - {protocol.title}",
        f"Condition: {protocol.condition} | Phase: {protocol.phase}",
        f"Target Enrollment: {protocol.target_enrollment}",
        "",
        "SCREENING SUMMARY:",
        f"Total Patients Screened: {len(results)}",
        f"Eligible Candidates: {eligible_count}",
        f"Eligibility Rate: {eligible_count / len(results) * 100:.1f}%"
        if results
        else "N/A",
        "",
        "PATIENT DETAILS:",
    ]
    for idx, result in enumerate(results, start=1):
        status = "ELIGIBLE" if result.assessment.eligible else "INELIGIBLE"
        lines.append(
            f"\n{idx}. {result.patient_name} (MRN: {result.mrn}, Hospital: {result.hospital_id})"
        )
        lines.append(
            f"   Status: {status} [Confidence: {result.assessment.confidence_score:.2f}]"
        )
        lines.append(f"   Reasoning: {result.assessment.reasoning}")
        if result.assessment.matching_inclusion:
            lines.append(
                "   Inclusion: " + ", ".join(result.assessment.matching_inclusion)
            )
        if result.assessment.matching_exclusion:
            lines.append(
                "   Exclusion: " + ", ".join(result.assessment.matching_exclusion)
            )

    report = "\n".join(lines)

    await harness.adjudicate(
        Event(
            agent=sondera_agent,
            trajectory_id=trajectory_id,
            event=ToolCall(tool="generate_report", arguments="{}", call_id="report-1"),
        )
    )
    await harness.adjudicate(
        Event(
            agent=sondera_agent,
            trajectory_id=trajectory_id,
            event=ToolOutput.from_success("report-1", "Generated recruitment report"),
        )
    )

    return report


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Life Sciences Clinical Trial Recruitment Agent"
    )
    parser.add_argument("--trial-id", default="NCT05543210")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(
            logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO
        )
    )

    sondera_agent = build_sondera_agent()
    harness = SonderaRemoteHarness()
    session_id = f"session-{uuid.uuid4()}"
    await harness.initialize(agent=sondera_agent, session_id=session_id)

    print("\nLife Sciences Clinical Trial Recruitment Agent")
    print(f"Trial ID: {args.trial_id}")
    print("-" * 60)

    try:
        report = await run_recruitment_pipeline(
            trial_id=args.trial_id,
            hospital_ids=["hospital_alpha", "hospital_beta"],
            harness=harness,
        )
        print("\n" + report)
        await harness.finalize()
        print("\nAnalysis complete!")
    except Exception as exc:
        await harness.fail(reason=str(exc))
        logger.error("Pipeline error: %s", exc)
        raise


if __name__ == "__main__":
    asyncio.run(main())
