import sys
import unittest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure project root and API dirs are in sys.path
_ROOT = Path(__file__).resolve().parent.parent
_API_DIR = _ROOT / "apps" / "api"
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_API_DIR))

from src.main import app
from src.repositories.scheme_repository import SchemeRepository

client = TestClient(app)


class TestFrontendNewChat(unittest.TestCase):
    """Focused tests for the '+ New Chat' button and session isolation."""

    def setUp(self):
        self.repo = SchemeRepository()
        self.html_path = _ROOT / "apps" / "web" / "public" / "assistant.html"
        self.js_path = _ROOT / "apps" / "web" / "public" / "assistant.js"
        self.site_js_path = _ROOT / "apps" / "web" / "public" / "site.js"
        self.css_path = _ROOT / "apps" / "web" / "public" / "styles.css"

    def test_new_chat_button_is_displayed_in_html(self):
        """Verify the '+ New Chat' button exists with the proper ID, class, and label."""
        self.assertTrue(self.html_path.exists(), "assistant.html must exist")
        html_content = self.html_path.read_text(encoding="utf-8")

        self.assertIn('id="newChatBtn"', html_content, "New chat button with id 'newChatBtn' must be present")
        self.assertIn("btn-new-chat", html_content, "New chat button should have class 'btn-new-chat'")
        self.assertIn("+ New Chat", html_content, "Button text should be '+ New Chat'")

    def test_css_styles_defined_for_new_chat_button(self):
        """Verify styling rules for .btn-new-chat and .chat-header are present in styles.css."""
        self.assertTrue(self.css_path.exists(), "styles.css must exist")
        css_content = self.css_path.read_text(encoding="utf-8")

        self.assertIn(".btn-new-chat", css_content, ".btn-new-chat rule must be defined in styles.css")
        self.assertIn(".chat-header", css_content, ".chat-header rule must be defined in styles.css")
        self.assertIn(".chat-status-dot", css_content, ".chat-status-dot rule must be defined in styles.css")

    def test_site_js_provides_session_creation_and_reset_api(self):
        """Verify site.js includes createNewGuestSessionId and API.resetChatSession."""
        self.assertTrue(self.site_js_path.exists(), "site.js must exist")
        site_js = self.site_js_path.read_text(encoding="utf-8")

        self.assertIn("function createNewGuestSessionId()", site_js)
        self.assertIn("resetChatSession:", site_js)
        self.assertIn("/reset", site_js)

    def test_assistant_js_implements_new_chat_reset_flow(self):
        """Verify assistant.js clears messages, restores WELCOME_INTRO_HTML, prevents duplicate clicks, and updates currentSessionId."""
        self.assertTrue(self.js_path.exists(), "assistant.js must exist")
        assistant_js = self.js_path.read_text(encoding="utf-8")

        # Check startNewChat function definition and event listener binding
        self.assertIn("async function startNewChat()", assistant_js)
        self.assertIn('newChatBtn.addEventListener("click", startNewChat)', assistant_js)

        # Check duplicate click protection
        self.assertIn("isResetting", assistant_js)
        self.assertIn("disabled = true", assistant_js)

        # Check message clearing and welcome greeting restore
        self.assertIn("chatLog.innerHTML = WELCOME_INTRO_HTML", assistant_js)

        # Check session_id update
        self.assertIn("currentSessionId = newSessionId", assistant_js)
        self.assertIn("createNewGuestSessionId()", assistant_js)

        # Check error handling try-catch-finally
        self.assertIn("catch (err)", assistant_js)
        self.assertIn("finally {", assistant_js)

    def test_session_isolation_and_backend_context_reset(self):
        """Verify previous session context/profile is NOT carried into a new chat session."""
        old_session_id = f"test_old_{uuid.uuid4().hex[:8]}"
        new_session_id = f"test_new_{uuid.uuid4().hex[:8]}"

        # 1. Establish old session with accumulated profile entities
        self.repo.get_or_create_session(old_session_id)
        self.repo.update_session_profile(old_session_id, {
            "state": "Uttar Pradesh",
            "age": 30,
            "category": "Farmer",
            "caste": "General",
            "annual_income": 200000,
        })
        self.repo.add_message(old_session_id, "user", "I am a 30 year old farmer in Uttar Pradesh")
        self.repo.add_message(old_session_id, "assistant", "Here are schemes for farmers in Uttar Pradesh...")

        old_profile = self.repo.get_session_profile(old_session_id)
        self.assertEqual(old_profile.get("state"), "Uttar Pradesh")
        self.assertEqual(old_profile.get("age"), 30)

        # 2. Trigger reset on backend
        reset_resp = client.post(f"/api/chat/{old_session_id}/reset")
        self.assertEqual(reset_resp.status_code, 200)

        # Verify old session profile is cleared
        cleared_old_profile = self.repo.get_session_profile(old_session_id)
        self.assertIsNone(cleared_old_profile.get("state"))
        self.assertIsNone(cleared_old_profile.get("age"))

        # 3. Verify new session has completely fresh/empty context
        new_profile = self.repo.get_session_profile(new_session_id)
        self.assertEqual(new_profile, {}, "New session profile should start completely empty")

        new_history = self.repo.get_session_messages(new_session_id)
        self.assertEqual(len(new_history), 0, "New session should have 0 messages from previous chat")

        # 4. Confirm vague discovery on new session triggers state clarification gate
        chat_resp = client.post(
            "/api/chat",
            json={"session_id": new_session_id, "message": "tell me schemes"}
        )
        self.assertEqual(chat_resp.status_code, 200)
        data = chat_resp.json()
        self.assertEqual(data["action_taken"], "clarify")
        self.assertIn("Which state or union territory", data["reply"])

    def test_api_reset_failure_graceful_handling(self):
        """Verify resetting a non-existent or empty session does not error out and returns HTTP 200."""
        random_session = f"ghost_session_{uuid.uuid4().hex[:8]}"
        response = client.post(f"/api/chat/{random_session}/reset")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()

