import unittest
from app.services.anonymise import anonymise

# This unit test checks that the anonymisation helper removes common identifying
# information from consultation text, including email addresses, phone numbers
# and Pakistani CNIC numbers, before the text is used elsewhere in the system.

class AnonymiseTests(unittest.TestCase):
    def test_obvious_identifiers_removed(self):
        text = "Email ali@example.com, call 0300-1234567, CNIC 35202-1234567-1."
        out = anonymise(text)
        self.assertNotIn("ali@example.com", out)
        self.assertNotIn("0300-1234567", out)
        self.assertNotIn("35202-1234567-1", out)


if __name__ == "__main__":
    unittest.main()
