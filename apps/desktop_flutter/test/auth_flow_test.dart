import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:xai_compress_desktop/services/api_service.dart';

void main() {
  test('password login recognizes MFA requirement without exposing response',
      () async {
    final api = ApiService(
        client: MockClient((request) async => http.Response(
            jsonEncode({'detail': 'Valid TOTP code required'}), 401)));
    expect(
        () => api.login('person@example.com', 'valid-password'),
        throwsA(
            isA<ApiException>().having((e) => e.kind, 'kind', 'mfa_required')));
  });

  test('desktop submits mobile TOTP through existing login contract', () async {
    String? sentCode;
    final api = ApiService(client: MockClient((request) async {
      if (request.url.path == '/auth/login') {
        sentCode = jsonDecode(request.body)['totp_code'];
        return http.Response('{"access_token":"a","refresh_token":"r"}', 200);
      }
      return http.Response(
          '{"email":"person@example.com","email_verified":true,"account_status":"ACTIVE","mfa_enabled":true}',
          200);
    }));
    await api.login('person@example.com', 'valid-password', totp: '428731');
    expect(sentCode, '428731');
  });

  test('password reset codes and authorization remain in POST bodies',
      () async {
    final paths = <String>[];
    final api = ApiService(client: MockClient((request) async {
      paths.add(request.url.toString());
      expect(request.url.query, isEmpty);
      if (request.url.path.endsWith('verify-code')) {
        expect(jsonDecode(request.body)['code'], '123456');
        return http.Response('{"reset_token":"temporary"}', 200);
      }
      expect(jsonDecode(request.body)['reset_token'], 'temporary');
      return http.Response('{}', 200);
    }));
    final token = await api.verifyResetCode('person@example.com', '123456');
    await api.resetPassword(token, 'new-password-123');
    expect(paths, hasLength(2));
  });
}
