import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:xai_compress_desktop/services/api_service.dart';

void main() {
  const inputMessage = 'Please check the information you entered.';
  const networkMessage = 'Could not connect securely. Please retry.';

  Future<ApiException> forgotWithStatus(int status,
      {String body = '{}'}) async {
    final api = ApiService(
        client: MockClient((_) async => http.Response(body, status)));
    try {
      await api.forgotPassword('person@example.com');
      fail('Expected HTTP $status to fail');
    } on ApiException catch (error) {
      return error;
    }
  }

  test('200 forgot-password response succeeds generically', () async {
    var calls = 0;
    final api = ApiService(client: MockClient((_) async {
      calls++;
      return http.Response('{"accepted":true,"message":"generic"}', 200);
    }));
    await api.forgotPassword('person@example.com');
    expect(calls, 1);
  });

  test('400 maps to safe input UX',
      () async => expect((await forgotWithStatus(400)).message, inputMessage));
  test(
      '422 maps to safe input UX even with backend detail',
      () async => expect(
          (await forgotWithStatus(422,
                  body: '{"detail":"Invalid authentication request"}'))
              .message,
          inputMessage));
  test(
      '401 maps to authentication UX',
      () async => expect((await forgotWithStatus(401)).message,
          'Email, password, or authentication code is incorrect.'));
  test(
      '403 maps to forbidden UX',
      () async => expect((await forgotWithStatus(403)).message,
          'This action is not allowed.'));
  test(
      '409 maps to safe conflict UX',
      () async => expect((await forgotWithStatus(409)).message,
          'This request conflicts with the current account or resource state.'));
  test(
      '429 maps to rate-limit UX',
      () async => expect((await forgotWithStatus(429)).message,
          'Too many attempts. Please try again later.'));
  test(
      '500 maps to temporary service UX',
      () async => expect(
          (await forgotWithStatus(500, body: 'internal provider details'))
              .message,
          'Service is temporarily unavailable. Please try again.'));

  test('timeout has dedicated UX', () async {
    final api = ApiService(
        requestTimeout: const Duration(milliseconds: 1),
        client: MockClient((_) async {
          await Future<void>.delayed(const Duration(milliseconds: 30));
          return http.Response('{}', 200);
        }));
    expect(
        api.forgotPassword('person@example.com'),
        throwsA(isA<ApiException>().having(
            (e) => e.message, 'message', 'Request timed out. Please retry.')));
  });

  test('socket and DNS failures map only to network UX', () async {
    final api = ApiService(
        client: MockClient(
            (_) async => throw const SocketException('host lookup failed')));
    expect(
        api.forgotPassword('person@example.com'),
        throwsA(isA<ApiException>()
            .having((e) => e.message, 'message', networkMessage)));
  });

  test('TLS handshake failures map only to network UX', () async {
    final api = ApiService(
        client: MockClient((_) async =>
            throw const HandshakeException('certificate failure')));
    expect(
        api.forgotPassword('person@example.com'),
        throwsA(isA<ApiException>()
            .having((e) => e.message, 'message', networkMessage)));
  });

  test('invalid email is rejected before network request', () async {
    var contacted = false;
    final api = ApiService(client: MockClient((_) async {
      contacted = true;
      return http.Response('{}', 200);
    }));
    expect(
        () => api.forgotPassword('invalid-email'),
        throwsA(isA<ApiException>()
            .having((e) => e.message, 'message', inputMessage)));
    expect(contacted, isFalse);
  });

  test('protected 401 reports expired session', () async {
    final api =
        ApiService(client: MockClient((_) async => http.Response('{}', 401)));
    api.token = 'expired-access-token';
    expect(
        api.history(),
        throwsA(isA<ApiException>().having((e) => e.message, 'message',
            'Your session has expired. Please sign in again.')));
  });
}
