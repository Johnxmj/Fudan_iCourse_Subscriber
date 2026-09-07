import importlib
import os
import unittest


class RuntimeConfigTest(unittest.TestCase):
    def test_deepseek_relay_model_and_base_url(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        os.environ["DEEPSEEK_BASE_URL"] = "https://relay.invalid/v1"

        from src.runtime import config

        importlib.reload(config)
        provider = next(
            provider
            for provider in config.resolve_model_providers()
            if provider["name"] == "deepseek"
        )

        self.assertEqual(provider["base_url"], "https://relay.invalid/v1")
        self.assertEqual(provider["models"], ["DeepSeek-V4-Flash-0731"])


if __name__ == "__main__":
    unittest.main()
