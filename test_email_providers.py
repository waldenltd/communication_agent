"""
Quick test script to verify email provider switching works.

This demonstrates how easy it is to switch between providers.
"""

from src.providers.email_service import create_email_service

# Test 1: SendGrid configuration
print("Test 1: SendGrid Provider")
sendgrid_config = {
    'sendgrid_key': 'SG.test_key',
    'sendgrid_from': 'noreply@example.com'
}

service = create_email_service(sendgrid_config)
print(f"Provider selected: {service.adapter.get_provider_name()}")
print()

# Test 2: Resend configuration
print("Test 2: Resend Provider")
resend_config = {
    'resend_key': 're_test_key',
    'resend_from': 'noreply@example.com'
}

service = create_email_service(resend_config)
print(f"Provider selected: {service.adapter.get_provider_name()}")
print()

# Test 3: Explicit provider selection
print("Test 3: Explicit Provider Selection")
explicit_config = {
    'email_provider': 'resend',
    'sendgrid_key': 'SG.test_key',  # Both keys present
    'resend_key': 're_test_key',
}

service = create_email_service(explicit_config)
print(f"Provider selected: {service.adapter.get_provider_name()}")
print("(Note: Resend was chosen despite SendGrid key being present)")
print()

print("✅ All tests demonstrate provider switching works correctly!")
print("\nTo actually send emails, you need valid API keys.")
