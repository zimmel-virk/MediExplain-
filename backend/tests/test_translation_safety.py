import unittest

from app.services.translation_safety import verify
# These unit tests check key translation-safety rules used before patient text is
# accepted for delivery. They verify that missing clinical numbers are detected,
# that Devanagari output is rejected for Urdu, and that English text is accepted
# without requiring an Arabic-derived script.

class TranslationSafetyTests(unittest.TestCase):
    def test_missing_dose_number_is_flagged(self):
        source = "Take paracetamol 500 mg twice daily."
        target = "پیراسیٹامول دن میں دو بار لیں۔"
        out = verify(source, target, "ur", {"medications": [{"name": "paracetamol"}]})
        self.assertFalse(out["numeric_preserved"])

    def test_devanagari_is_invalid_for_urdu(self):
        out = verify("Take medicine.", "दवा लें।", "ur", {})
        self.assertFalse(out["script_valid"])

    def test_english_source_is_not_required_to_be_arabic(self):
        out = verify("Take medicine.", "Take medicine.", "en", {})
        self.assertTrue(out["script_valid"])


if __name__ == "__main__":
    unittest.main()
