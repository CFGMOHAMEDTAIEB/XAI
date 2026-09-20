import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:xai_compress_authenticator/core/app_state.dart';
import 'package:xai_compress_authenticator/models/authenticator_account.dart';
import 'package:xai_compress_authenticator/services/api_service.dart';
import 'package:xai_compress_authenticator/services/biometric_service.dart';
import 'package:xai_compress_authenticator/services/secure_account_store.dart';

class MemoryStore extends SecureAccountStore {
  bool failWrite = false;
  List<AuthenticatorAccount> stored = [];
  @override
  Future<List<AuthenticatorAccount>> loadAccounts() async => stored;
  @override
  Future<void> saveAccounts(List<AuthenticatorAccount> accounts) async {
    if (failWrite) throw Exception('private storage details');
    stored = accounts;
  }
}

void main() {
  test('backend provisioning writes only secure account storage', () async {
    final store = MemoryStore();
    final state = AppState(
        accountStore: store,
        biometricService: BiometricService(),
        apiService: ApiService());
    addTearDown(state.dispose);
    await state.provision(
        'otpauth://totp/XAI:test@example.com?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&issuer=XAI',
        '0123456789abcdef0123456789abcdef',
        displayName: 'Test User');
    expect(store.stored, hasLength(1));
    expect(store.stored.single.displayName, 'Test User');
  });

  test('secure storage failure does not retain account in state', () async {
    final store = MemoryStore()..failWrite = true;
    final state = AppState(
        accountStore: store,
        biometricService: BiometricService(),
        apiService: ApiService());
    addTearDown(state.dispose);
    await expectLater(
        state.provision(
            'otpauth://totp/XAI:test@example.com?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&issuer=XAI',
            '0123456789abcdef0123456789abcdef'),
        throwsException);
    expect(state.accounts, isEmpty);
  });

  test('codes and reset authorization use POST bodies, never URLs', () async {
    final requests = <http.Request>[];
    final api = ApiService(client: MockClient((request) async {
      requests.add(request);
      return http.Response(
          jsonEncode(request.url.path.contains('verify-code')
              ? {'reset_token': 'memory-only-reset-token-123456789012345'}
              : {'enabled': true}),
          200);
    }))
      ..accessToken = 'unit-token';
    addTearDown(api.dispose);
    await api.confirmAuthenticatorEnrollment(
        '0123456789abcdef0123456789abcdef', '123456');
    await api.verifyPasswordResetCode('test@example.com', '654321');
    for (final request in requests) {
      expect(request.method, 'POST');
      expect(request.url.query, isEmpty);
      expect(request.url.toString(), isNot(contains('123456')));
      expect(request.url.toString(), isNot(contains('654321')));
    }
  });

  test('API sanitizes backend bodies', () async {
    final api = ApiService(
        client: MockClient(
            (_) async => http.Response('private-provider-data', 503)));
    addTearDown(api.dispose);
    await expectLater(
        api.mfaStatus(),
        throwsA(isA<ApiException>().having((e) => e.message, 'message',
            isNot(contains('private-provider-data')))));
  });

  testWidgets('network timeout is finite and sanitized', (tester) async {
    final api = ApiService(
        client: MockClient((_) => Completer<http.Response>().future));
    addTearDown(api.dispose);
    final result = expectLater(
        api.mfaStatus(),
        throwsA(isA<ApiException>()
            .having((e) => e.message, 'message', contains('timed out'))));
    await tester.pump(const Duration(seconds: 41));
    await result;
  });
}
