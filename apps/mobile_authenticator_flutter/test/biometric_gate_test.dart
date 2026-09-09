import 'package:flutter_test/flutter_test.dart';
import 'package:local_auth/local_auth.dart';
import 'package:xai_compress_authenticator/services/biometric_service.dart';

class UnsupportedAuthentication extends LocalAuthentication {
  @override
  Future<bool> isDeviceSupported() async => false;
}

void main() {
  test('unsupported device authentication never unlocks the factor store', () async {
    final service = BiometricService(authentication: UnsupportedAuthentication());
    expect(await service.authenticate(), isFalse);
  });
}
