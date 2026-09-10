import 'package:flutter_test/flutter_test.dart';
import 'package:local_auth/local_auth.dart';
import 'package:xai_compress_authenticator/services/biometric_service.dart';

class UnsupportedAuthentication extends LocalAuthentication {
  @override
  Future<bool> isDeviceSupported() async => false;
}

void main() {
  test('supported authentication unlocks only on success', () async {
    expect(await BiometricService(authentication: SupportedAuthentication(true)).authenticate(), isTrue);
    expect(await BiometricService(authentication: SupportedAuthentication(false)).authenticate(), isFalse);
  });
  test('authentication exceptions deny access', () async {
    expect(await BiometricService(authentication: SupportedAuthentication(true, throws: true)).authenticate(), isFalse);
  });
  test('unsupported device authentication never unlocks the factor store', () async {
    final service = BiometricService(authentication: UnsupportedAuthentication());
    expect(await service.authenticate(), isFalse);
  });
}

class SupportedAuthentication extends LocalAuthentication {
  SupportedAuthentication(this.result, {this.throws = false});
  final bool result;
  final bool throws;
  @override
  Future<bool> isDeviceSupported() async => true;
  @override
  Future<bool> authenticate({
    required String localizedReason,
    Iterable<dynamic> authMessages = const [],
    bool biometricOnly = false,
    bool sensitiveTransaction = true,
    bool persistAcrossBackgrounding = false,
  }) async {
    if (throws) throw StateError('test authentication failure');
    return result;
  }
}
