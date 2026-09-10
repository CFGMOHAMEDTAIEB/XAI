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
    final Uri uri;
    try { uri = Uri.parse(rawUri.trim()); } catch (_) { throw const FormatException('Invalid QR code.'); }
    if (uri.scheme != 'otpauth' || uri.host != 'totp') {
      throw const FormatException('The QR code is not an otpauth TOTP URI.');
    }

    final secret = uri.queryParameters['secret']?.replaceAll(RegExp(r'[\s-]'), '').toUpperCase();
    if (secret == null || secret.trim().isEmpty) {
      throw const FormatException('The TOTP secret is missing.');
    }

    final label = Uri.decodeComponent(uri.pathSegments.join('/'));
    final labelParts = label.split(':');
    final issuer = (uri.queryParameters['issuer'] ??
        (labelParts.length > 1 ? labelParts.first : 'XAI-Compress')).trim();
    final account = labelParts.length > 1 ? labelParts.sublist(1).join(':') : label;
    final labelIssuer=labelParts.length>1?labelParts.first.trim():null;
    if(issuer.isEmpty||account.trim().isEmpty)throw const FormatException('Issuer and account name are required.');
    if(labelIssuer!=null&&uri.queryParameters['issuer']!=null&&labelIssuer!=issuer)throw const FormatException('Issuer does not match the account label.');
    if(!RegExp(r'^[A-Z2-7]+=*$').hasMatch(secret)||secret.length<16)throw const FormatException('The setup key is not valid Base32.');
    final algorithm=(uri.queryParameters['algorithm']??'SHA1').toUpperCase();
    final digits=int.tryParse(uri.queryParameters['digits']??'6');
    final period=int.tryParse(uri.queryParameters['period']??'30');
    if(!{'SHA1','SHA256','SHA512'}.contains(algorithm))throw const FormatException('Unsupported TOTP algorithm.');
    if(digits!=6&&digits!=8)throw const FormatException('TOTP must use 6 or 8 digits.');
    if(period==null||period<15||period>120)throw const FormatException('Unsupported TOTP period.');

    return TotpEnrollment(
      secret: secret,
      issuer: issuer,
      accountName: account.isEmpty ? 'Account' : account,
      algorithm: algorithm,
      digits: digits!,
      period: period!,
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
        enrolledAt: DateTime.now().toUtc(),
        managed: issuer.toUpperCase()=='XAI',
      );
}
