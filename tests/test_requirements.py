from pathlib import Path
import unittest


class RequirementsTest(unittest.TestCase):
    def test_openai_major_version_is_bounded(self):
        requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()

        self.assertIn("openai<3", requirements)


if __name__ == "__main__":
    unittest.main()
