"""Mock EHR simulator."""

from archetypes.healthcare.clinical import PatientRecord


class MockEHRSimulator:
    """Simulates an EHR system with synthetic patient data."""

    def __init__(self):
        self.hospitals: dict[str, list[PatientRecord]] = {}

    def add_hospital(self, hospital_id: str, patients: list[PatientRecord]):
        """Add a hospital with patient records.

        Args:
            hospital_id: Hospital identifier
            patients: List of patient records
        """
        self.hospitals[hospital_id] = patients

    def get_patients(self, hospital_id: str) -> list[PatientRecord]:
        """Get patients for a hospital.

        Args:
            hospital_id: Hospital identifier

        Returns:
            List of patient records for the hospital
        """
        return self.hospitals.get(hospital_id, [])
