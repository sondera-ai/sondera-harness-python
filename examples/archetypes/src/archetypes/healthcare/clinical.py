"""Clinical trial and patient data models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Demographics:
    """Patient demographics."""

    mrn: str
    first_name: str
    last_name: str
    date_of_birth: str
    age: int
    gender: str


@dataclass
class ClinicalNote:
    """Clinical note from EHR."""

    note_id: str
    note_type: str
    authored_on: datetime
    content: str


@dataclass
class PatientRecord:
    """Complete patient record."""

    demographics: Demographics
    hospital_id: str
    notes: list[ClinicalNote]


@dataclass
class TrialProtocol:
    """Clinical trial protocol."""

    trial_id: str
    title: str
    phase: str
    condition: str
    inclusion_criteria: list[str]
    exclusion_criteria: list[str]
    target_enrollment: int


@dataclass
class EligibilityAssessment:
    """Patient eligibility assessment result."""

    eligible: bool
    confidence_score: float
    reasoning: str
    matching_inclusion: list[str]
    matching_exclusion: list[str]


@dataclass
class ParsedPatient:
    """Parsed patient with clinical note summary."""

    mrn: str
    patient_name: str
    hospital_id: str
    note_summary: str


@dataclass
class EligibilityResult:
    """Final eligibility result for a patient."""

    mrn: str
    patient_name: str
    hospital_id: str
    assessment: EligibilityAssessment


def create_sample_patients(hospital_id: str) -> list[PatientRecord]:
    """Create sample patient records for testing.

    Args:
        hospital_id: Hospital identifier

    Returns:
        List of sample patient records
    """
    return [
        PatientRecord(
            demographics=Demographics(
                mrn="MRN001",
                first_name="John",
                last_name="Doe",
                date_of_birth="1965-03-15",
                age=58,
                gender="M",
            ),
            hospital_id=hospital_id,
            notes=[
                ClinicalNote(
                    note_id="N001",
                    note_type="Progress Note",
                    authored_on=datetime(2024, 1, 15),
                    content="Patient diagnosed with Type 2 Diabetes. HbA1c 8.5%. Starting metformin.",
                )
            ],
        ),
        PatientRecord(
            demographics=Demographics(
                mrn="MRN002",
                first_name="Jane",
                last_name="Smith",
                date_of_birth="1970-07-22",
                age=53,
                gender="F",
            ),
            hospital_id=hospital_id,
            notes=[
                ClinicalNote(
                    note_id="N002",
                    note_type="Progress Note",
                    authored_on=datetime(2024, 1, 10),
                    content="Type 2 Diabetes well controlled. HbA1c 6.2%. History of severe kidney disease.",
                )
            ],
        ),
    ]


def create_sample_trial() -> TrialProtocol:
    """Create a sample clinical trial protocol.

    Returns:
        Sample trial protocol for diabetes study
    """
    return TrialProtocol(
        trial_id="NCT05543210",
        title="Study of Novel Diabetes Treatment",
        phase="Phase 3",
        condition="Type 2 Diabetes",
        inclusion_criteria=[
            "Age 18-75 years",
            "Diagnosed with Type 2 Diabetes",
            "HbA1c between 7.0% and 10.0%",
        ],
        exclusion_criteria=[
            "Severe kidney disease",
            "Active cancer treatment",
            "Pregnancy or nursing",
        ],
        target_enrollment=500,
    )


def rule_based_assessment(
    patient: PatientRecord, protocol: TrialProtocol
) -> EligibilityAssessment:
    """Rule-based eligibility assessment (no LLM required).

    Args:
        patient: Patient record to assess
        protocol: Trial protocol with criteria

    Returns:
        Eligibility assessment result
    """
    notes_text = " ".join(note.content.lower() for note in patient.notes)

    matching_inclusion = []
    matching_exclusion = []

    # Check inclusion criteria
    if 18 <= patient.demographics.age <= 75:
        matching_inclusion.append("Age 18-75 years")

    if "type 2 diabetes" in notes_text or "t2d" in notes_text:
        matching_inclusion.append("Diagnosed with Type 2 Diabetes")

    if "hba1c" in notes_text:
        matching_inclusion.append("HbA1c documented")

    # Check exclusion criteria
    if "kidney disease" in notes_text or "renal failure" in notes_text:
        matching_exclusion.append("Severe kidney disease")

    if "cancer" in notes_text and "treatment" in notes_text:
        matching_exclusion.append("Active cancer treatment")

    # Determine eligibility
    eligible = len(matching_inclusion) >= 2 and len(matching_exclusion) == 0
    confidence = 0.8 if eligible else 0.9

    reasoning = f"Patient matches {len(matching_inclusion)} inclusion criteria"
    if matching_exclusion:
        reasoning += f" but has {len(matching_exclusion)} exclusion factors"

    return EligibilityAssessment(
        eligible=eligible,
        confidence_score=confidence,
        reasoning=reasoning,
        matching_inclusion=matching_inclusion,
        matching_exclusion=matching_exclusion,
    )
