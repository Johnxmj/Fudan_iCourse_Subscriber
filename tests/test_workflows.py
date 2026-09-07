from pathlib import Path
import unittest


class WorkflowSecurityTest(unittest.TestCase):
    def test_runtime_workflows_pass_only_required_provider_secrets(self):
        for workflow_name in ("check.yml", "single_run.yml"):
            workflow = Path(".github/workflows", workflow_name).read_text(
                encoding="utf-8"
            )

            self.assertNotIn("toJSON(secrets)", workflow)
            self.assertNotIn('eval "$(python scripts/provider_env.py)"', workflow)
            self.assertIn(
                "DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}", workflow
            )
            self.assertIn(
                "DEEPSEEK_BASE_URL: ${{ secrets.DEEPSEEK_BASE_URL }}", workflow
            )


if __name__ == "__main__":
    unittest.main()
