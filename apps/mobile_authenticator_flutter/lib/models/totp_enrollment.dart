import 'authenticator_account.dart';

class TotpEnrollment {
  const TotpEnrollment({
    required this.secret,
    required this.issuer,
    required this.accountName,
    this.algorithm = 'SHA1',
    this.digits = 6,
    this.period = 30,
  });

  final String secret;
  final String issuer;
  final String accountName;
  final String algorithm;
  final int digits;
  final int period;

  factory TotpEnrollment.parse(String rawUri) {
    final uri = Uri.parse(rawUri.trim());
    if (uri.scheme != 'otpauth' || uri.host != 'totp') {
      throw const FormatException('The QR code is not an otpauth TOTP URI.');
    }

    final secret = uri.queryParameters['secret'];
    if (secret == null || secret.trim().isEmpty) {
      throw const FormatException('The TOTP secret is missing.');
    }

    final label = Uri.decodeComponent(uri.pathSegments.join('/'));
    final labelParts = label.split(':');
    final issuer = uri.queryParameters['issuer'] ??
        (labelParts.length > 1 ? labelParts.first : 'XAI-Compress');
    final account = labelParts.length > 1 ? labelParts.sublist(1).join(':') : label;

    return TotpEnrollment(
      secret: secret.replaceAll(' ', '').toUpperCase(),
      issuer: issuer,
      accountName: account.isEmpty ? 'Account' : account,
      algorithm: (uri.queryParameters['algorithm'] ?? 'SHA1').toUpperCase(),
      digits: int.tryParse(uri.queryParameters['digits'] ?? '') ?? 6,
      period: int.tryParse(uri.queryParameters['period'] ?? '') ?? 30,
    );
  }

  AuthenticatorAccount toAccount(String id) => AuthenticatorAccount(
        id: id,
        issuer: issuer,
        accountName: accountName,
        secret: secret,
        algorithm: algorithm,
        digits: digits,
        period: period,
      );
}
