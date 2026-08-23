import 'package:flutter_test/flutter_test.dart';
import 'package:xai_compress_authenticator/models/totp_enrollment.dart';

void main() {
  test('parses a standard otpauth URI', () {
    final enrollment = TotpEnrollment.parse(
      'otpauth://totp/XAI-Compress:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=XAI-Compress',
    );
    expect(enrollment.issuer, 'XAI-Compress');
    expect(enrollment.accountName, 'user@example.com');
    expect(enrollment.secret, 'JBSWY3DPEHPK3PXP');
    expect(enrollment.period, 30);
  });

  test('rejects a non-TOTP URI', () {
    expect(() => TotpEnrollment.parse('https://example.com'), throwsFormatException);
  });
}
