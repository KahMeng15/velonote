import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


def send_email(
    db: Session, recipient_email: str, subject: str, body: str, is_html: bool = False
) -> bool:
    """Send an email using the configured SMTP settings in environment variables"""
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.error("Email configuration is incomplete in environment variables")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = f"{settings.SMTP_SENDER_NAME} <{settings.SMTP_USER}>"
        msg["To"] = recipient_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "html" if is_html else "plain"))

        host = settings.SMTP_HOST
        port = settings.SMTP_PORT

        if settings.SMTP_TLS:
            server = smtplib.SMTP(host, port)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(host, port)

        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()

        logger.info(f"Email sent successfully to {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {e}")
        return False


def send_invitation_email(db: Session, recipient_email: str, invitation_link: str) -> bool:
    """Send an invitation email to a new user"""
    subject = "You're invited to join velonote!"
    body = f"""
    <html>
        <body>
            <h2>Welcome to velonote!</h2>
            <p>You have been invited to join velonote, your AI-powered study companion.</p>
            <p>Click the link below to create your account and get started:</p>
            <p><a href="{invitation_link}">{invitation_link}</a></p>
            <p>If you didn't expect this invitation, you can safely ignore this email.</p>
            <br>
            <p>Best regards,<br>The velonote Team</p>
        </body>
    </html>
    """
    return send_email(db, recipient_email, subject, body, is_html=True)


def send_verification_email(db: Session, recipient_email: str, verification_link: str) -> bool:
    """Send an email verification link to a new user"""
    subject = "Verify Your Email - velonote"
    body = f"""
    <html>
        <body>
            <h2>Verify Your Email</h2>
            <p>Welcome to velonote! Please verify your email address to complete your registration.</p>
            <p>Click the link below to verify your account:</p>
            <p><a href="{verification_link}" style="display: inline-block; padding: 12px 24px; background-color: #10b981; color: white; text-decoration: none; border-radius: 6px; font-weight: 600;">Verify Email</a></p>
            <p>Or copy and paste this link in your browser:</p>
            <p><small>{verification_link}</small></p>
            <p style="color: #666; font-size: 14px; margin-top: 20px;">This link will expire in 24 hours.</p>
            <p style="color: #666; font-size: 14px;">If you didn't create an account, you can safely ignore this email.</p>
            <br>
            <p>Best regards,<br>The velonote Team</p>
        </body>
    </html>
    """
    return send_email(db, recipient_email, subject, body, is_html=True)


def send_password_reset_email(db: Session, recipient_email: str, reset_link: str) -> bool:
    """Send a password reset email to a user"""
    subject = "Password Reset Request - velonote"
    body = f"""
    <html>
        <body>
            <h2>Password Reset Request</h2>
            <p>We received a request to reset the password for your velonote account.</p>
            <p>Click the link below to reset your password:</p>
            <p><a href="{reset_link}" style="display: inline-block; padding: 12px 24px; background-color: #3b82f6; color: white; text-decoration: none; border-radius: 6px; font-weight: 600;">Reset Password</a></p>
            <p>Or copy and paste this link in your browser:</p>
            <p><small>{reset_link}</small></p>
            <p style="color: #666; font-size: 14px; margin-top: 20px;">This link will expire in 24 hours.</p>
            <p style="color: #666; font-size: 14px;">If you didn't request this, you can safely ignore this email. Your password will remain unchanged.</p>
            <br>
            <p>Best regards,<br>The velonote Team</p>
        </body>
    </html>
    """
    return send_email(db, recipient_email, subject, body, is_html=True)


def send_password_change_confirmation_email(
    db: Session, recipient_email: str, confirmation_code: str
) -> bool:
    """Send a password change confirmation email to a user"""
    subject = "Confirm Your Password Change - velonote"
    body = f"""
    <html>
        <body>
            <h2>Confirm Your Password Change</h2>
            <p>A password change has been requested for your velonote account.</p>
            <p>Your confirmation code is:</p>
            <p style="font-size: 24px; font-weight: bold; letter-spacing: 2px; color: #3b82f6; background: #f0f0f0; padding: 15px; border-radius: 6px; text-align: center;">{confirmation_code}</p>
            <p>Enter this code in the settings page to complete your password change.</p>
            <p style="color: #666; font-size: 14px; margin-top: 20px;">This code will expire in 1 hour.</p>
            <p style="color: #666; font-size: 14px;">If you didn't request this, you can safely ignore this email. Your password will remain unchanged.</p>
            <br>
            <p>Best regards,<br>The velonote Team</p>
        </body>
    </html>
    """
    return send_email(db, recipient_email, subject, body, is_html=True)


def send_welcome_email(db: Session, recipient_email: str, full_name: str) -> bool:
    """Send a welcome email to a newly registered/verified user"""
    subject = "Welcome to velonote!"
    body = f"""
    <html>
        <body>
            <h2>Welcome to velonote, {full_name}!</h2>
            <p>We're thrilled to have you join our community of smart learners.</p>
            <p>velonote is designed to help you organize your study materials, generate AI-powered summaries, and practice with smart exercises.</p>
            <p>Here are a few things you can do to get started:</p>
            <ul>
                <li><strong>Upload Notes:</strong> Upload your PDFs or PPTX files to get structured notes.</li>
                <li><strong>Chat with AI:</strong> Ask questions about your materials and get instant clarifications.</li>
                <li><strong>Take Exercises:</strong> Test your knowledge with AI-generated questions from your own notes.</li>
            </ul>
            <p>If you have any questions or need support, feel free to contact us through the app.</p>
            <br>
            <p>Happy studying!<br>The velonote Team</p>
        </body>
    </html>
    """
    return send_email(db, recipient_email, subject, body, is_html=True)


def send_account_approved_email(
    db: Session,
    recipient_email: str,
    full_name: str,
    login_url: str = "http://localhost:8000/login",
) -> bool:
    """Send an email notification when an admin approves a user's account"""
    subject = "Your velonote account has been approved!"
    body = f"""
    <html>
        <body>
            <h2>Welcome to velonote, {full_name}!</h2>
            <p>Good news! Your account has been approved by an administrator.</p>
            <p>You can now log in and start using velonote, your AI-powered study companion.</p>
            <p><a href="{login_url}" style="display: inline-block; padding: 12px 24px; background-color: #10b981; color: white; text-decoration: none; border-radius: 6px; font-weight: 600;">Log In</a></p>
            <p>If you have any questions or need support, feel free to contact us through the app.</p>
            <br>
            <p>Best regards,<br>The velonote Team</p>
        </body>
    </html>
    """
    return send_email(db, recipient_email, subject, body, is_html=True)


def send_password_changed_notification_email(db: Session, recipient_email: str) -> bool:
    """Send a notification email when a user's password has been successfully changed"""
    subject = "Security Alert: Your password was changed - velonote"
    body = """
    <html>
        <body>
            <h2>Your Password was Changed</h2>
            <p>This is a notification to confirm that the password for your velonote account has been successfully updated.</p>
            <p>If you made this change, you can safely ignore this email.</p>
            <p style="color: #ef4444; font-weight: bold;">If you did NOT change your password, please contact our support team immediately or request a password reset to secure your account.</p>
            <br>
            <p>Best regards,<br>The velonote Team</p>
        </body>
    </html>
    """
    return send_email(db, recipient_email, subject, body, is_html=True)
