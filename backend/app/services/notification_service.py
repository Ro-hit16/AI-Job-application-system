"""
services/notification_service.py — Email & Webhook Notifications
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class NotificationService:
    async def send_email(self, subject: str, body: str, to_email: Optional[str] = None) -> bool:
        recipient = to_email or settings.NOTIFICATION_EMAIL_TO
        if not recipient or not settings.SMTP_USERNAME:
            logger.warning("Email not configured, skipping")
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.SMTP_USERNAME
            msg["To"] = recipient
            msg.attach(MIMEText(body, "html"))
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_USERNAME, recipient, msg.as_string())
            logger.info("Email sent", extra={"to": recipient, "subject": subject})
            return True
        except Exception as e:
            logger.error("Email send failed", extra={"error": str(e)})
            return False

    async def send_webhook(self, title: str, message: str, color: int = 0x00FF00) -> bool:
        if not settings.WEBHOOK_URL:
            return False
        try:
            payload = {"embeds": [{"title": title, "description": message, "color": color}]}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(settings.WEBHOOK_URL, json=payload)
                resp.raise_for_status()
            logger.info("Webhook sent", extra={"url": settings.WEBHOOK_URL})
            return True
        except Exception as e:
            logger.error("Webhook failed", extra={"error": str(e)})
            return False

    async def notify_new_match(self, job_title: str, company: str, score: float) -> None:
        subject = f"New Job Match: {job_title} at {company} ({score:.0f}%)"
        body = f"""
        <h2>New Job Match Found!</h2>
        <p><strong>Position:</strong> {job_title}</p>
        <p><strong>Company:</strong> {company}</p>
        <p><strong>Match Score:</strong> {score:.1f}%</p>
        <p>Log in to review and approve the application.</p>
        """
        await self.send_email(subject, body)
        await self.send_webhook(subject, f"{job_title} at {company} — {score:.0f}% match", 0x00FF88)

    async def notify_approval_required(self, job_title: str, company: str, app_id: str) -> None:
        subject = f"Approval Required: {job_title} at {company}"
        body = f"""
        <h2>Your Approval is Required</h2>
        <p><strong>Position:</strong> {job_title}</p>
        <p><strong>Company:</strong> {company}</p>
        <p>The resume has been tailored. Please review and approve or reject.</p>
        <p><a href="http://localhost:3000/approvals/{app_id}">Review Application</a></p>
        """
        await self.send_email(subject, body)
        await self.send_webhook(subject, f"Approval needed for {job_title} at {company}", 0xFFAA00)

    async def notify_application_submitted(self, job_title: str, company: str, confirmation: str) -> None:
        subject = f"Application Submitted: {job_title} at {company}"
        body = f"""
        <h2>Application Successfully Submitted!</h2>
        <p><strong>Position:</strong> {job_title}</p>
        <p><strong>Company:</strong> {company}</p>
        <p><strong>Confirmation:</strong> {confirmation}</p>
        """
        await self.send_email(subject, body)
        await self.send_webhook(subject, f"✅ Applied to {job_title} at {company}", 0x00AAFF)

    async def notify_application_failed(self, job_title: str, company: str, error: str) -> None:
        subject = f"Application Failed: {job_title} at {company}"
        body = f"""
        <h2>Application Submission Failed</h2>
        <p><strong>Position:</strong> {job_title}</p>
        <p><strong>Company:</strong> {company}</p>
        <p><strong>Error:</strong> {error}</p>
        """
        await self.send_email(subject, body)
        await self.send_webhook(subject, f"❌ Failed to apply to {job_title} at {company}", 0xFF4444)


_instance: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    global _instance
    if _instance is None:
        _instance = NotificationService()
    return _instance