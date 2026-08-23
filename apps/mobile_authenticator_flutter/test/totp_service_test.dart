import 'package:flutter_test/flutter_test.dart';
import 'package:xai_compress_authenticator/models/authenticator_account.dart';
import 'package:xai_compress_authenticator/services/totp_service.dart';

void main() {
  test('generates deterministic code for fixed time', () {
    const account = AuthenticatorAccount(
      id: '1',
      issuer: 'Test',
      accountName: 'user',
      secret: 'JBSWY3DPEHPK3PXP',
    );
    final now = DateTime.fromMillisecondsSinceEpoch(1700000000000);
    final first = TotpService().generate(account, now: now);
    final second = TotpService().generate(account, now: now);
    expect(first.code, second.code);
    expect(first.code.length, 6);
  });
}
