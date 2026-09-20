import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:xai_compress_desktop/services/api_service.dart';
import 'package:xai_compress_desktop/services/deployment_config.dart';

void main() {
  test('desktop default resolves to the deployed HTTPS API origin', () {
    final uri = Uri.parse(configuredApiUrl());
    expect(uri.scheme, 'https');
    expect(uri.host, 'xai-1-be9s.onrender.com');
    expect(uri.path, isEmpty);
    expect(uri.userInfo, isEmpty);
  });

  test('release validation rejects local, credentialed, and path URLs', () {
    for (final value in [
      'http://localhost:8000',
      'https://user:password@example.com',
      'https://example.com/api',
    ]) {
      expect(() => validateDesktopApiUrl(value, allowLocal: false),
          throwsStateError);
    }
  });

  test('actual config path constructs exact forgot-password request', () async {
    late http.Request captured;
    final api = ApiService(client: MockClient((request) async {
      captured = request;
      return http.Response('{"accepted":true}', 200);
    }));
    await api.forgotPassword('runtime-smoke@example.invalid');
    expect(api.baseUrl, configuredApiUrl());
    expect(captured.url.scheme, 'https');
    expect(captured.url.host, 'xai-1-be9s.onrender.com');
    expect(captured.url.path, '/auth/password/forgot');
    expect(captured.headers['content-type'], 'application/json');
    expect(jsonDecode(captured.body).keys, ['identifier']);
  });
}
