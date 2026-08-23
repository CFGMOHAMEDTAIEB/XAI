class AuthenticatorAccount {
  const AuthenticatorAccount({
    required this.id,
    required this.issuer,
    required this.accountName,
    required this.secret,
    this.algorithm = 'SHA1',
    this.digits = 6,
    this.period = 30,
  });

  final String id;
  final String issuer;
  final String accountName;
  final String secret;
  final String algorithm;
  final int digits;
  final int period;

  Map<String, dynamic> toJson() => {
        'id': id,
        'issuer': issuer,
        'accountName': accountName,
        'secret': secret,
        'algorithm': algorithm,
        'digits': digits,
        'period': period,
      };

  factory AuthenticatorAccount.fromJson(Map<String, dynamic> json) {
    return AuthenticatorAccount(
      id: json['id'] as String,
      issuer: json['issuer'] as String? ?? 'XAI-Compress',
      accountName: json['accountName'] as String? ?? 'Account',
      secret: json['secret'] as String,
      algorithm: json['algorithm'] as String? ?? 'SHA1',
      digits: json['digits'] as int? ?? 6,
      period: json['period'] as int? ?? 30,
    );
  }
}
