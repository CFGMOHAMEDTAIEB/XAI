import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:xai_compress_authenticator/core/app_state.dart';
import 'package:xai_compress_authenticator/main.dart';
import 'package:xai_compress_authenticator/models/authenticator_account.dart';
import 'package:xai_compress_authenticator/services/api_service.dart';
import 'package:xai_compress_authenticator/services/biometric_service.dart';
import 'package:xai_compress_authenticator/services/secure_account_store.dart';

class MemoryStore extends SecureAccountStore {
  bool failRead = false;
  bool failWrite = false;
  List<AuthenticatorAccount> stored = [];
  @override
  Future<List<AuthenticatorAccount>> loadAccounts() async {
    if (failRead) throw Exception('private storage details');
    return stored;
  }
  @override
  Future<void> saveAccounts(List<AuthenticatorAccount> accounts) async {
    if (failWrite) throw Exception('private storage details');
    stored = accounts;
  }
}

class FlowApi extends ApiService {
  String stage = 'not_configured';
  bool unavailable = false;
  int disclosures = 0;
  static const eid = '0123456789abcdef0123456789abcdef';
  @override
  Future<void> login({required String email, required String password, String? totpCode}) async {
    if (unavailable) throw const ApiException('Backend unavailable. Retry.');
    accessToken = 'test';
  }
  @override
  Future<void> register({required String email, required String password}) => login(email: email, password: password);
  Map<String, dynamic> status() => {'state': stage, 'email': 'test@example.com', 'enrollment_id': eid};
  @override
  Future<Map<String, dynamic>> mfaStatus() async => status();
  @override
  Future<Map<String, dynamic>> enrollTotp({bool restart = false}) async {
    stage = 'awaiting_email';
    return status();
  }
  @override
  Future<Map<String, dynamic>> resendCode() async => status();
  @override
  Future<Map<String, dynamic>> confirmEmail(String enrollmentId, String code) async {
    if (code != '123456') throw const ApiException('Invalid email code. Retry.');
    disclosures++;
    stage = 'awaiting_totp';
    // Public RFC test material, never a real account secret.
    return {'otpauth_uri': 'otpauth://totp/XAI:test@example.com?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&issuer=XAI'};
  }
  @override
  Future<bool> confirmTotp(String enrollmentId, String code) async {
    if (code != '654321') throw const ApiException('Invalid TOTP. Retry with a fresh code.');
    stage = 'enabled';
    return true;
  }
}

Future<AppState> mount(WidgetTester tester, FlowApi api, MemoryStore store) async {
  final state = AppState(accountStore: store, biometricService: BiometricService(), apiService: api)
    ..loading = false
    ..unlocked = true;
  addTearDown(state.dispose);
  await tester.pumpWidget(ChangeNotifierProvider<AppState>.value(value: state, child: const XaiAuthenticatorApp()));
  return state;
}

Future<void> tap(WidgetTester tester, String text) async {
  await tester.ensureVisible(find.text(text));
  await tester.tap(find.text(text));
  await tester.pumpAndSettle();
}

Future<void> type(WidgetTester tester, String label, String value) async {
  final finder = find.byWidgetPredicate((w) => w is TextField && w.decoration?.labelText == label);
  await tester.ensureVisible(finder);
  await tester.enterText(finder, value);
  await tester.pump();
}

void main() {
  testWidgets('Guided enrollment handles invalid codes and provisions before enabling', (tester) async {
    final api = FlowApi(); final store = MemoryStore();
    await mount(tester, api, store);
    await tap(tester, 'Sign in');
    await tap(tester, 'Setup Authenticator');
    expect(find.text('Email verification code'), findsOneWidget);
    await type(tester, 'Email verification code', '000000');
    await tap(tester, 'Verify email & provision authenticator');
    expect(find.text('Invalid email code. Retry.'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsNothing);
    await type(tester, 'Email verification code', '123456');
    await tap(tester, 'Verify email & provision authenticator');
    expect(store.stored.length, 1);
    expect(store.stored.single.id, 'xai-${FlowApi.eid}');
    await type(tester, 'Generated TOTP code', '000000');
    await tap(tester, 'Verify TOTP & enable MFA');
    expect(find.text('Invalid TOTP. Retry with a fresh code.'), findsOneWidget);
    await type(tester, 'Generated TOTP code', '654321');
    await tap(tester, 'Verify TOTP & enable MFA');
    expect(find.textContaining('MFA ENABLED.'), findsOneWidget);
  });

  testWidgets('Storage retry does not replay consumed email verification', (tester) async {
    final api = FlowApi(); final store = MemoryStore()..failWrite = true;
    await mount(tester, api, store);
    await tap(tester, 'Sign in'); await tap(tester, 'Setup Authenticator');
    await type(tester, 'Email verification code', '123456');
    await tap(tester, 'Verify email & provision authenticator');
    expect(find.text('Retry secure storage'), findsOneWidget);
    expect(store.stored, isEmpty);
    expect(find.text('Verify TOTP & enable MFA'), findsNothing);
    store.failWrite = false;
    await tap(tester, 'Retry secure storage');
    expect(api.disclosures, 1);
    expect(store.stored.length, 1);
    expect(find.text('Verify TOTP & enable MFA'), findsOneWidget);
  });

  testWidgets('Registration and backend outage recover without an infinite spinner', (tester) async {
    final api = FlowApi()..unavailable = true;
    await mount(tester, api, MemoryStore());
    await tap(tester, 'Create a new XAI account');
    await tap(tester, 'Create account');
    expect(find.text('Backend unavailable. Retry.'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsNothing);
    api.unavailable = false;
    await tap(tester, 'Create account');
    expect(find.text('Setup Authenticator'), findsOneWidget);
  });

  testWidgets('Startup secure storage failure clears loading and can retry', (tester) async {
    final store = MemoryStore()..failRead = true;
    final state = AppState(accountStore: store, biometricService: BiometricService(), apiService: FlowApi());
    await state.initialize();
    await tester.pumpWidget(ChangeNotifierProvider<AppState>.value(value: state, child: const XaiAuthenticatorApp()));
    expect(state.loading, isFalse);
    expect(find.text('Retry secure storage'), findsOneWidget);
    store.failRead = false;
    await tap(tester, 'Retry secure storage');
    expect(find.text('Unlock'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    state.dispose();
  });

  testWidgets('Lost disclosure recovers through restart, never an invented secret', (tester) async {
    final api = FlowApi()..stage = 'awaiting_totp';
    await mount(tester, api, MemoryStore());
    await tap(tester, 'Sign in');
    expect(find.textContaining('secret is not on this phone'), findsOneWidget);
    expect(find.text('Verify TOTP & enable MFA'), findsNothing);
    await tap(tester, 'Restart setup with a new secret');
    expect(find.text('Email verification code'), findsOneWidget);
  });

  test('API keeps secrets in authenticated POST bodies, not URLs', () async {
    final requests = <http.Request>[];
    final api = ApiService(client: MockClient((r) async {
      requests.add(r);
      return http.Response(jsonEncode({'enabled': true}), 200);
    }))..accessToken = 'unit-token';
    addTearDown(api.dispose);
    await api.confirmTotp(FlowApi.eid, '123456');
    final request = requests.single;
    expect(request.method, 'POST');
    expect(request.url.host, 'xai-1-be9s.onrender.com');
    expect(request.url.query, isEmpty);
    expect(request.headers['authorization'], 'Bearer unit-token');
    expect(jsonDecode(request.body)['enrollment_id'], FlowApi.eid);
  });

  test('API sanitizes provider bodies', () async {
    final api = ApiService(client: MockClient((_) async => http.Response('private-provider-data', 503)));
    addTearDown(api.dispose);
    await expectLater(api.mfaStatus(), throwsA(isA<ApiException>().having((e) => e.message, 'message', isNot(contains('private-provider-data')))));
  });

  testWidgets('Network timeout has finite wait and recovery message', (tester) async {
    final api = ApiService(client: MockClient((_) => Completer<http.Response>().future));
    addTearDown(api.dispose);
    final result = expectLater(api.mfaStatus(), throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('timed out'))));
    await tester.pump(const Duration(seconds: 41));
    await result;
  });
}
