"""Offline checks for the practical local OpenCode/C# profile."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


def render_template():
    template = (ROOT / "assistant" / "opencode.template.jsonc").read_text(encoding="utf-8")
    replacements = {
        "{{INSTRUCTIONS_PATH_JSON}}": json.dumps(str(ROOT / "assistant" / "csharp.md")),
        "{{PROJECT_PATH_JSON}}": json.dumps(str(ROOT / "workspaces" / "CleanArchitecture")),
        "{{DISPLAY_NAME_JSON}}": json.dumps("Local C# (qwen3:8b)"),
        "{{CONTEXT_TOKENS}}": "8192",
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    return "\n".join(line for line in template.splitlines()
                     if not line.lstrip().startswith("//"))


class LocalAssistantProfileTests(unittest.TestCase):
    def setUp(self):
        self.config_text = render_template()

    def test_template_renders_valid_local_only_json(self):
        config = json.loads(self.config_text)
        self.assertNotIn("{{", self.config_text)
        self.assertEqual(config["model"], "ollama/csharp-local")
        model = config["providers"]["ollama"]["models"]["csharp-local"]
        self.assertEqual(model["limit"], {"context": 8192, "output": 4096})
        self.assertEqual(config["policies"], [
            {"action": "provider.use", "resource": "*", "effect": "deny"},
            {"action": "provider.use", "resource": "ollama", "effect": "allow"},
        ])

    def test_roslyn_is_direct_and_unrelated_azure_is_disabled(self):
        servers = json.loads(self.config_text)["mcp"]["servers"]
        self.assertFalse(servers["roslyn"]["codemode"])
        self.assertTrue(servers["azure"]["disabled"])
        self.assertEqual(servers["roslyn"]["command"],
                         ["dnx", "RoslynCodeLens.Mcp", "--yes"])

    def test_roslyn_surface_is_limited_to_core_tool_names(self):
        rules = json.loads(self.config_text)["permissions"]
        roslyn_rules = [rule for rule in rules if rule["action"].startswith("roslyn_")]
        self.assertEqual(roslyn_rules[0],
                         {"action": "roslyn_*", "resource": "*", "effect": "deny"})
        allowed = {rule["action"] for rule in roslyn_rules if rule["effect"] == "allow"}
        self.assertEqual(len(roslyn_rules), 16)
        self.assertEqual(len(allowed), 15)
        for required in ("roslyn_load_solution", "roslyn_go_to_definition",
                         "roslyn_find_references", "roslyn_get_diagnostics"):
            self.assertIn(required, allowed)

    def test_build_does_not_delegate_and_helpers_stay_local(self):
        agents = json.loads(self.config_text)["agents"]
        self.assertIn({"action": "subagent", "resource": "*", "effect": "deny"},
                      agents["build"]["permissions"])
        for name in ("build", "title", "summary", "compaction", "general", "explore"):
            self.assertEqual(agents[name]["model"], "ollama/csharp-local", name)

    def test_benchmark_probe_is_read_only(self):
        config_text = (ROOT / "opencode.jsonc").read_text(encoding="utf-8")
        probe = json.loads(config_text)["agents"]["probe"]
        self.assertEqual(probe["steps"], 8)
        denied = {rule["action"] for rule in probe["permissions"] if rule["effect"] == "deny"}
        for action in ("edit", "shell", "execute", "subagent", "webfetch", "websearch"):
            self.assertIn(action, denied)

    def test_powershell_launcher_parses(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            self.skipTest("PowerShell is not installed")
        launcher = str(ROOT / "local.ps1").replace("'", "''")
        command = (
            "$errors = $null; $tokens = $null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{launcher}', "
            "[ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
        )
        result = subprocess.run([shell, "-NoProfile", "-Command", command],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
