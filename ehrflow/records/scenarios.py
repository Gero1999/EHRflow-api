"""Allowlisted fictional data. Public requests never accept patient free text."""
PATIENTS = {
    "maya": {"name": "Patient Alpha", "record_number": "SYN-1001", "date_of_birth": "1988-04-16", "contact_email": "alpha@example.invalid"},
    "jonah": {"name": "Patient Beta", "record_number": "SYN-1002", "date_of_birth": "1976-09-08", "contact_email": "beta@example.invalid"},
    "avery": {"name": "Patient Gamma", "record_number": "SYN-1003", "date_of_birth": "1994-02-21", "contact_email": "gamma@example.invalid"},
    "theo": {"name": "Patient Delta", "record_number": "SYN-1004", "date_of_birth": "1982-11-03", "contact_email": "delta@example.invalid"},
}
PERSONAS = {
    "registrar": ("Registrar One", "registrar"),
    "nurse": ("Nurse One", "nurse"),
    "clinician": ("Clinician One", "clinician"),
    "other_clinician": ("Clinician Two", "clinician"),
    "reviewer": ("Privacy Reviewer", "reviewer"),
    "access_admin": ("Access Administrator", "access_admin"),
}
REASONS = {"follow_up": "Routine follow-up", "wellness": "Wellness visit", "intake": "New patient intake"}
NOTES = {
    "follow_up": "SYNTHETIC TRAINING RECORD. Routine follow-up reviewed. Demo observations discussed with the fictional patient. No real assessment, diagnosis, or treatment recommendation is provided.",
    "reviewed": "SYNTHETIC TRAINING RECORD. Visit documentation reviewed and the demonstration intake completed. This sample records the workflow only; it is not medical advice.",
    "wellness": "SYNTHETIC TRAINING RECORD. Fictional wellness encounter documented. The sample patient reports no concerns for this scenario. No clinical decision support is performed.",
}
ADDENDA = {"clarification": "SYNTHETIC ADDENDUM. The encounter documentation was reviewed for this demonstration. The original finalized note has been retained unchanged."}
OBSERVATIONS = {
    "pulse": ("72.00", "bpm"), "temperature": ("36.70", "°C"),
    "oxygen_saturation": ("98.00", "%"),
}
