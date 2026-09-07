FROM clamav/clamav:stable
# Preserve the official entrypoint, signature updates, and health probe.
# Treat exceeded engine limits as a rejection rather than a silently partial scan.
RUN printf '\nAlertExceedsMax yes\n' >> /etc/clamav/clamd.conf
