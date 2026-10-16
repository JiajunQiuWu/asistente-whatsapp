import io
import smtplib
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from email.message import EmailMessage
from unittest.mock import patch

from app.email_sender import (
    EmailAuthenticationError,
    EmailConnectionError,
    EmailCredentialStoreError,
    EmailSettings,
    KEYRING_SERVICE,
    build_briefing_email,
    configure_email_account,
    load_email_settings,
    save_app_password,
    send_email,
)
from app.news import DEMO_NEWS
from app.tasks import Task

TEST_SETTINGS = EmailSettings(
    sender="sender@example.com",
    recipient="recipient@example.com",
    password="test-secret",
)


class EmailSenderTests(unittest.TestCase):
    def test_load_settings_prompts_for_missing_password_without_exposing_it(self) -> None:
        class EmptyKeyring:
            def get_password(self, service, username):
                self.last_lookup = (service, username)
                return None

        with patch(
            "app.email_sender.getpass.getpass",
            return_value="prompted-secret",
        ) as getpass, patch(
            "app.email_sender._secure_keyring_backend",
            return_value=EmptyKeyring(),
        ):
            settings = load_email_settings(
                {
                    "GMAIL_ADDRESS": "sender@example.com",
                    "EMAIL_TO": "recipient@example.com",
                }
            )

        self.assertEqual(settings.password, "prompted-secret")
        self.assertNotIn("prompted-secret", repr(settings))
        getpass.assert_called_once()

    def test_environment_password_is_used_before_keyring(self) -> None:
        with patch(
            "app.email_sender._secure_keyring_backend",
            side_effect=AssertionError("no debe consultar keyring"),
        ) as get_backend:
            settings = load_email_settings(
                {
                    "GMAIL_ADDRESS": "sender@example.com",
                    "EMAIL_TO": "recipient@example.com",
                    "GMAIL_APP_PASSWORD": "environment-secret",
                },
                non_interactive=True,
            )

        self.assertEqual(settings.password, "environment-secret")
        get_backend.assert_not_called()

    def test_keyring_password_is_used_before_prompt(self) -> None:
        class StoredKeyring:
            def get_password(self, service, username):
                self.lookup = (service, username)
                return "keyring-secret"

        backend = StoredKeyring()
        with (
            patch(
                "app.email_sender._secure_keyring_backend",
                return_value=backend,
            ),
            patch(
                "app.email_sender.getpass.getpass",
                side_effect=AssertionError("no debe solicitar contraseña"),
            ) as getpass,
        ):
            settings = load_email_settings(
                {
                    "GMAIL_ADDRESS": "sender@example.com",
                    "EMAIL_TO": "recipient@example.com",
                },
                non_interactive=True,
            )

        self.assertEqual(settings.password, "keyring-secret")
        self.assertEqual(backend.lookup, (KEYRING_SERVICE, "sender@example.com"))
        getpass.assert_not_called()

    def test_email_config_saves_prompted_password_to_keyring(self) -> None:
        password = "never-print-this-secret"
        with (
            patch(
                "app.email_sender.getpass.getpass",
                return_value=password,
            ) as getpass,
            patch("app.email_sender._secure_keyring_backend"),
            patch("app.email_sender.save_app_password") as save,
        ):
            sender = configure_email_account(
                {"GMAIL_ADDRESS": "sender@example.com"}
            )

        self.assertEqual(sender, "sender@example.com")
        save.assert_called_once_with(sender, password)
        getpass.assert_called_once()

    def test_email_config_checks_secure_store_before_prompt(self) -> None:
        with (
            patch(
                "app.email_sender._secure_keyring_backend",
                side_effect=EmailCredentialStoreError("almacén no disponible"),
            ),
            patch(
                "app.email_sender.getpass.getpass",
                side_effect=AssertionError("no debe solicitar contraseña"),
            ) as getpass,
        ):
            with self.assertRaises(EmailCredentialStoreError):
                configure_email_account({"GMAIL_ADDRESS": "sender@example.com"})
        getpass.assert_not_called()

    def test_email_config_command_does_not_print_password(self) -> None:
        from app import __main__ as application

        secret = "never-print-this-secret"
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["app", "email-config"]),
            patch(
                "app.email_sender.getpass.getpass",
                return_value=secret,
            ),
            patch("app.email_sender.save_app_password") as save,
            patch.object(
                application,
                "configure_email_account",
                side_effect=lambda: configure_email_account(
                    {"GMAIL_ADDRESS": "sender@example.com"}
                ),
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(application.main(), 0)

        self.assertIn("sender@example.com", output.getvalue())
        self.assertNotIn(secret, output.getvalue())
        save.assert_called_once_with("sender@example.com", secret)

    def test_password_is_saved_using_service_and_sender_account(self) -> None:
        class FakeKeyring:
            def set_password(self, service, username, password):
                self.saved = (service, username, password)

        backend = FakeKeyring()
        with patch(
            "app.email_sender._secure_keyring_backend",
            return_value=backend,
        ):
            save_app_password("sender@example.com", "test-only-secret")

        self.assertEqual(
            backend.saved,
            (KEYRING_SERVICE, "sender@example.com", "test-only-secret"),
        )

    def test_missing_noninteractive_password_does_not_prompt(self) -> None:
        class EmptyKeyring:
            def get_password(self, service, username):
                self.last_lookup = (service, username)
                return None

        backend = EmptyKeyring()
        with (
            patch(
                "app.email_sender._secure_keyring_backend",
                return_value=backend,
            ),
            patch(
                "app.email_sender.getpass.getpass",
                side_effect=AssertionError("no debe solicitar contraseña"),
            ) as getpass,
        ):
            with self.assertRaisesRegex(ValueError, "email-config"):
                load_email_settings(
                    {
                        "GMAIL_ADDRESS": "sender@example.com",
                        "EMAIL_TO": "recipient@example.com",
                    },
                    non_interactive=True,
                )
        self.assertEqual(
            backend.last_lookup,
            (KEYRING_SERVICE, "sender@example.com"),
        )
        getpass.assert_not_called()

    def test_unavailable_secure_store_is_reported_without_prompt_fallback(self) -> None:
        with (
            patch(
                "app.email_sender._secure_keyring_backend",
                side_effect=EmailCredentialStoreError("almacén no disponible"),
            ),
            patch(
                "app.email_sender.getpass.getpass",
                side_effect=AssertionError("no debe usar una alternativa insegura"),
            ) as getpass,
        ):
            with self.assertRaises(EmailCredentialStoreError):
                load_email_settings(
                    {
                        "GMAIL_ADDRESS": "sender@example.com",
                        "EMAIL_TO": "recipient@example.com",
                    }
                )
        getpass.assert_not_called()

    def test_email_config_reports_unavailable_secure_store(self) -> None:
        from app import __main__ as application

        errors = io.StringIO()
        with (
            patch.object(sys, "argv", ["app", "email-config"]),
            patch.object(
                application,
                "configure_email_account",
                side_effect=EmailCredentialStoreError(
                    "No se pudo acceder al almacén seguro."
                ),
            ),
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            exit_code = application.main()

        self.assertEqual(exit_code, 5)
        self.assertIn("almacén seguro", errors.getvalue())

    def test_rejects_invalid_configuration_before_smtp(self) -> None:
        with self.assertRaises(ValueError):
            load_email_settings(
                {
                    "GMAIL_ADDRESS": "invalid",
                    "EMAIL_TO": "recipient@example.com",
                    "GMAIL_APP_PASSWORD": "test-secret",
                }
            )

    def test_sends_using_tls_before_login_and_correct_recipient(self) -> None:
        events: list[tuple] = []
        tls_context = object()
        message = build_briefing_email(
            DEMO_NEWS,
            [Task(id=1, title="[DEMO] Tarea de prueba.")],
            sender=TEST_SETTINGS.sender,
            recipient=TEST_SETTINGS.recipient,
        )

        class FakeSMTP:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                self.exit_args = (exc_type, exc_value, traceback)
                return False

            def starttls(self, context):
                events.append(("starttls", context))

            def login(self, username, password):
                events.append(("login", username, password))

            def send_message(self, outgoing, *, from_addr, to_addrs):
                events.append(("send_message", outgoing, from_addr, to_addrs))

        with (
            patch(
                "app.email_sender.ssl.create_default_context",
                return_value=tls_context,
            ),
            patch("app.email_sender.smtplib.SMTP", return_value=FakeSMTP()) as smtp,
        ):
            send_email(message, TEST_SETTINGS)

        self.assertEqual(
            [event[0] for event in events],
            ["starttls", "login", "send_message"],
        )
        self.assertIs(events[0][1], tls_context)
        self.assertEqual(events[1], ("login", TEST_SETTINGS.sender, "test-secret"))
        self.assertIs(events[2][1], message)
        self.assertEqual(events[2][2], TEST_SETTINGS.sender)
        self.assertEqual(events[2][3], [TEST_SETTINGS.recipient])
        smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=20)

    def test_authentication_failure_is_sanitized(self) -> None:
        class FakeSMTP:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                self.exit_args = (exc_type, exc_value, traceback)
                return False

            def starttls(self, context):
                self.context = context

            def login(self, username, password):
                self.credentials = (username, password)
                raise smtplib.SMTPAuthenticationError(535, b"test-secret rejected")

        message = EmailMessage()
        with (
            patch("app.email_sender.ssl.create_default_context"),
            patch("app.email_sender.smtplib.SMTP", return_value=FakeSMTP()),
        ):
            with self.assertRaises(EmailAuthenticationError) as raised:
                send_email(message, TEST_SETTINGS)

        self.assertNotIn("test-secret", str(raised.exception))

    def test_connection_failure_is_sanitized(self) -> None:
        message = EmailMessage()
        with patch(
            "app.email_sender.smtplib.SMTP",
            side_effect=OSError("failure containing test-secret"),
        ) as smtp:
            with self.assertRaises(EmailConnectionError) as raised:
                send_email(message, TEST_SETTINGS)

        self.assertNotIn("test-secret", str(raised.exception))
        smtp.assert_called_once()

    def test_preview_demo_does_not_connect_to_smtp_or_prompt_for_password(self) -> None:
        from app import __main__ as application

        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["app", "email", "--demo"]),
            patch.object(
                application, "load_email_settings", side_effect=AssertionError
            ) as settings,
            patch.object(
                application, "send_email", side_effect=AssertionError
            ) as send,
            patch("app.email_sender.smtplib.SMTP", side_effect=AssertionError) as smtp,
            redirect_stdout(output),
        ):
            self.assertEqual(application.main(), 0)

        self.assertIn("Vista previa: no se ha enviado ningún correo", output.getvalue())
        settings.assert_not_called()
        send.assert_not_called()
        smtp.assert_not_called()

    def test_real_preview_does_not_fetch_news_or_connect_to_smtp(self) -> None:
        from app import __main__ as application

        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["app", "email"]),
            patch.object(
                application, "load_sources", side_effect=AssertionError
            ) as sources,
            patch.object(
                application, "fetch_news", side_effect=AssertionError
            ) as fetch,
            patch.object(
                application,
                "list_pending_tasks",
                return_value=[Task(1, "Tarea local")],
            ),
            patch.object(
                application, "load_email_settings", side_effect=AssertionError
            ) as settings,
            patch.object(
                application, "send_email", side_effect=AssertionError
            ) as send,
            patch("app.email_sender.smtplib.SMTP", side_effect=AssertionError) as smtp,
            redirect_stdout(output),
        ):
            self.assertEqual(application.main(), 0)

        preview = output.getvalue()
        self.assertIn("Vista previa: no se ha enviado ningún correo", preview)
        self.assertIn("No hay noticias disponibles.", preview)
        self.assertIn("Tarea local", preview)
        sources.assert_not_called()
        fetch.assert_not_called()
        settings.assert_not_called()
        send.assert_not_called()
        smtp.assert_not_called()

    def test_demo_send_uses_fictional_data_and_sanitizes_auth_failure(self) -> None:
        from app import __main__ as application

        output = io.StringIO()
        errors = io.StringIO()
        with (
            patch.object(sys, "argv", ["app", "email", "--demo", "--send"]),
            patch.object(application, "load_email_settings", return_value=TEST_SETTINGS),
            patch.object(
                application, "load_sources", side_effect=AssertionError
            ) as sources,
            patch.object(
                application, "fetch_news", side_effect=AssertionError
            ) as fetch,
            patch.object(
                application, "list_pending_tasks", side_effect=AssertionError
            ) as tasks,
            patch.object(
                application,
                "send_email",
                side_effect=EmailAuthenticationError(
                    "Gmail rechazó la autenticación."
                ),
            ) as send,
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            exit_code = application.main()

        self.assertEqual(exit_code, 3)
        self.assertIn("[FICTICIA]", send.call_args.args[0].get_content())
        self.assertIn("[DEMO] Preparar una lista de compras.", send.call_args.args[0].get_content())
        self.assertIn(TEST_SETTINGS.sender, send.call_args.args[0]["From"])
        self.assertEqual(send.call_args.args[0]["To"], TEST_SETTINGS.recipient)
        self.assertNotIn("test-secret", errors.getvalue())
        self.assertNotIn("test-secret", output.getvalue())
        sources.assert_not_called()
        fetch.assert_not_called()
        tasks.assert_not_called()

    def test_cli_reports_gmail_acceptance_without_claiming_delivery(self) -> None:
        from app import __main__ as application

        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["app", "email", "--demo", "--send"]),
            patch.object(application, "load_email_settings", return_value=TEST_SETTINGS),
            patch.object(application, "send_email") as send,
            redirect_stdout(output),
        ):
            self.assertEqual(application.main(), 0)

        self.assertIn("Gmail aceptó el mensaje para su envío", output.getvalue())
        self.assertIn(
            "no garantiza que llegue a la bandeja de entrada",
            output.getvalue(),
        )
        send.assert_called_once()

    def test_cli_connection_failure_returns_nonzero_without_secret(self) -> None:
        from app import __main__ as application

        errors = io.StringIO()
        with (
            patch.object(sys, "argv", ["app", "email", "--demo", "--send"]),
            patch.object(application, "load_email_settings", return_value=TEST_SETTINGS),
            patch.object(
                application,
                "send_email",
                side_effect=EmailConnectionError("Fallo de conexión."),
            ),
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            exit_code = application.main()

        self.assertEqual(exit_code, 4)
        self.assertIn("Fallo de conexión.", errors.getvalue())
        self.assertNotIn("test-secret", errors.getvalue())

    def test_invalid_cli_configuration_does_not_connect_to_smtp(self) -> None:
        from app import __main__ as application

        errors = io.StringIO()
        with (
            patch.object(sys, "argv", ["app", "email", "--demo", "--send"]),
            patch.dict(
                "os.environ",
                {
                    "GMAIL_ADDRESS": "invalid",
                    "EMAIL_TO": "recipient@example.com",
                    "GMAIL_APP_PASSWORD": "test-secret",
                },
                clear=True,
            ),
            patch("app.email_sender.smtplib.SMTP", side_effect=AssertionError) as smtp,
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            exit_code = application.main()

        self.assertEqual(exit_code, 2)
        self.assertIn("GMAIL_ADDRESS", errors.getvalue())
        smtp.assert_not_called()

    def test_cli_noninteractive_fails_without_password_and_does_not_prompt(self) -> None:
        from app import __main__ as application

        class EmptyKeyring:
            def get_password(self, service, username):
                self.last_lookup = (service, username)
                return None

        backend = EmptyKeyring()
        errors = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                ["app", "email", "--demo", "--send", "--non-interactive"],
            ),
            patch.dict(
                "os.environ",
                {
                    "GMAIL_ADDRESS": "sender@example.com",
                    "EMAIL_TO": "recipient@example.com",
                },
                clear=True,
            ),
            patch(
                "app.email_sender._secure_keyring_backend",
                return_value=backend,
            ),
            patch(
                "app.email_sender.getpass.getpass",
                side_effect=AssertionError("no debe solicitar contraseña"),
            ) as getpass,
            patch.object(
                application, "send_email", side_effect=AssertionError
            ) as send,
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            exit_code = application.main()

        self.assertEqual(exit_code, 2)
        self.assertIn("email-config", errors.getvalue())
        self.assertEqual(
            backend.last_lookup,
            (KEYRING_SERVICE, "sender@example.com"),
        )
        getpass.assert_not_called()
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
