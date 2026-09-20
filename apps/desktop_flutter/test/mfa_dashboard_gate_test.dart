import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';
import 'package:xai_compress_desktop/core/app_state.dart';
import 'package:xai_compress_desktop/screens/app_shell.dart';
import 'package:xai_compress_desktop/services/api_service.dart';
import 'package:xai_compress_desktop/services/history_service.dart';
import 'package:xai_compress_desktop/services/local_engine_service.dart';
import 'package:xai_compress_desktop/services/secure_session_store.dart';
import 'package:xai_compress_desktop/services/settings_service.dart';

class MemorySessionStore implements SessionStore {
  String? value;
  @override
  Future<void> clear() async => value = null;
  @override
  Future<String?> readRefreshToken() async => value;
  @override
  Future<void> writeRefreshToken(String token) async => value = token;
}

class TestSettings extends SettingsService {
  @override
  Future<DesktopSettings> load() async => DesktopSettings();
}

AppState stateFor(ApiService api, {SessionStore? store}) => AppState(
    engine: LocalEngineService(),
    api: api,
    history: HistoryService(),
    settings: TestSettings(),
    sessionStore: store)
  ..config = DesktopSettings();

void main() {
  testWidgets(
      'password accepted with MFA required shows locked dashboard and calls no protected APIs',
      (tester) async {
    var protectedCalls = 0;
    final api = ApiService(client: MockClient((request) async {
      if (request.url.path == '/auth/login') {
        return http.Response(
            jsonEncode({'detail': 'Valid TOTP code required'}), 401);
      }
      protectedCalls++;
      return http.Response('[]', 200);
    }));
    final store = MemorySessionStore();
    final state = stateFor(api, store: store);
    addTearDown(state.dispose);
    try {
      await state.login('person@example.com', 'valid-password');
    } on ApiException catch (_) {}
    expect(state.mfaPending, isTrue);
    expect(state.page, 0);
    expect(api.token, isNull);
    expect(store.value, isNull);
    await tester.binding.setSurfaceSize(const Size(1220, 780));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(ChangeNotifierProvider.value(
        value: state, child: const MaterialApp(home: AppShell())));
    expect(find.text('Mobile Authenticator verification'), findsOneWidget);
    state.setPage(1);
    state.setPage(4);
    state.setPage(5);
    state.setPage(6);
    await tester.pump();
    expect(state.page, 0);
    expect(protectedCalls, 0);
    await expectLater(api.history(), throwsA(isA<ApiException>()));
    expect(protectedCalls, 0);
    expect(find.byIcon(Icons.lock_outline), findsWidgets);
  });

  test('invalid input makes no request and incorrect TOTP remains locked',
      () async {
    var calls = 0;
    final api = ApiService(client: MockClient((request) async {
      calls++;
      return http.Response(
          jsonEncode({'detail': 'Valid TOTP code required'}), 401);
    }));
    final state = stateFor(api);
    addTearDown(state.dispose);
    try {
      await state.login('person@example.com', 'valid-password');
    } catch (_) {}
    expect(calls, 1);
    await expectLater(state.verifyMfa('12x'), throwsA(isA<ApiException>()));
    expect(calls, 1);
    await expectLater(
        state.verifyMfa('123456'),
        throwsA(
            isA<ApiException>().having((e) => e.kind, 'kind', 'invalid_mfa')));
    expect(calls, 2);
    expect(state.mfaPending, isTrue);
    expect(state.workspaceUnlocked, isFalse);
  });

  test('correct mobile TOTP unlocks and logout clears session state', () async {
    var loginCalls = 0;
    final store = MemorySessionStore();
    final api = ApiService(client: MockClient((request) async {
      if (request.url.path == '/auth/login') {
        loginCalls++;
        final body = jsonDecode(request.body);
        if (body['totp_code'] == null) {
          return http.Response(
              jsonEncode({'detail': 'Valid TOTP code required'}), 401);
        }
        expect(body['totp_code'], '428731');
        return http.Response('{"access_token":"a","refresh_token":"r"}', 200);
      }
      if (request.url.path == '/auth/me') {
        return http.Response(
            '{"email":"person@example.com","mfa_enabled":true,"email_verified":true,"account_status":"ACTIVE"}',
            200);
      }
      return http.Response('{}', 200);
    }));
    final state = stateFor(api, store: store);
    addTearDown(state.dispose);
    try {
      await state.login('person@example.com', 'valid-password');
    } catch (_) {}
    await state.verifyMfa('428731');
    expect(loginCalls, 2);
    expect(state.workspaceUnlocked, isTrue);
    expect(store.value, 'r');
    await state.logout();
    expect(state.authStage, AuthStage.login);
    expect(store.value, isNull);
  });

  test(
      'restored server-issued session unlocks; failed restore returns to login',
      () async {
    final validStore = MemorySessionStore()..value = 'refresh';
    final validApi = ApiService(client: MockClient((request) async {
      if (request.url.path == '/auth/refresh') {
        return http.Response(
            '{"access_token":"a","refresh_token":"rotated"}', 200);
      }
      return http.Response(
          '{"email":"person@example.com","mfa_enabled":true,"email_verified":true,"account_status":"ACTIVE"}',
          200);
    }));
    final valid = stateFor(validApi, store: validStore);
    addTearDown(valid.dispose);
    await valid.initialize();
    expect(valid.workspaceUnlocked, isTrue);
    final badStore = MemorySessionStore()..value = 'invalid';
    final invalid = stateFor(
        ApiService(client: MockClient((_) async => http.Response('{}', 401))),
        store: badStore);
    addTearDown(invalid.dispose);
    await invalid.initialize();
    expect(invalid.authStage, AuthStage.login);
    expect(badStore.value, isNull);
  });

  test('returning to login erases the volatile MFA password', () async {
    var calls = 0;
    final api = ApiService(client: MockClient((_) async {
      calls++;
      return http.Response(
          jsonEncode({'detail': 'Valid TOTP code required'}), 401);
    }));
    final state = stateFor(api);
    addTearDown(state.dispose);
    try {
      await state.login('person@example.com', 'valid-password');
    } catch (_) {}
    state.backToLogin();
    await expectLater(state.verifyMfa('123456'), throwsA(isA<ApiException>()));
    expect(calls, 1);
  });

  test('logout while MFA is pending erases volatile challenge state', () async {
    var calls = 0;
    final api = ApiService(client: MockClient((_) async {
      calls++;
      return http.Response(
          jsonEncode({'detail': 'Valid TOTP code required'}), 401);
    }));
    final state = stateFor(api, store: MemorySessionStore());
    addTearDown(state.dispose);
    try {
      await state.login('person@example.com', 'valid-password');
    } catch (_) {}
    await state.logout();
    await expectLater(state.verifyMfa('123456'), throwsA(isA<ApiException>()));
    expect(calls, 1);
    expect(state.authStage, AuthStage.login);
  });
}
