class AuthenticatorAccount {
  const AuthenticatorAccount({
    required this.id,
    required this.issuer,
    required this.accountName,
    required this.secret,
    this.algorithm = 'SHA1',
    this.digits = 6,
    this.period = 30,
    this.enrolledAt,
    this.lastUsedAt,
    this.status = 'active',
    this.managed = false,
    this.backendDeviceId,
  });

  final String id;
  final String issuer;
  final String accountName;
  final String secret;
  final String algorithm;
  final int digits;
  final int period;
  final DateTime? enrolledAt;
  final DateTime? lastUsedAt;
  final String status;
  final bool managed;
  final String? backendDeviceId;

  Map<String, dynamic> toJson() => {
        'id': id,
        'issuer': issuer,
        'accountName': accountName,
        'secret': secret,
        'algorithm': algorithm,
        'digits': digits,
        'period': period,
        'enrolledAt': enrolledAt?.toIso8601String(),
        'lastUsedAt': lastUsedAt?.toIso8601String(),
        'status': status,
        'managed': managed,
        'backendDeviceId': backendDeviceId,
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
      enrolledAt: DateTime.tryParse(json['enrolledAt'] as String? ?? ''),
      lastUsedAt: DateTime.tryParse(json['lastUsedAt'] as String? ?? ''),
      status: json['status'] as String? ?? 'active',
      managed: json['managed'] as bool? ?? false,
      backendDeviceId: json['backendDeviceId'] as String?,
    );
  }
}
