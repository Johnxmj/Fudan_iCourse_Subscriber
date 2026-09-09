import unittest

from src.api.emailer import _md_to_html


class EmailMathRenderingTest(unittest.TestCase):
    def test_unmatched_dollar_is_escaped(self):
        html = _md_to_html(r"结果为 $P_n(\sin^2\frac{k\pi}{2n+1}")
        self.assertNotIn("$P_n", html)
        self.assertIn("&#36;P_n", html)

    def test_unbalanced_latex_is_readable_fallback(self):
        html = _md_to_html(r"公式：$\\frac{a}{b$")
        self.assertNotIn("<img", html)
        self.assertIn("frac", html)


if __name__ == "__main__":
    unittest.main()
