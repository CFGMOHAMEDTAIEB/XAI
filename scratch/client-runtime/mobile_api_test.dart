import 'dart:convert';
import 'dart:math';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:xai_compress_authenticator/services/api_service.dart';
void main() {
  test('Production API configuration and mobile authentication', () async {
    final api = ApiService();
    expect(api.baseUrl, 'https://xai-1-be9s.onrender.com');
    final health = await http.get(Uri.parse('https://xai-1-be9s.onrender.com/health'));
    expect(health.statusCode, 200);
    final email = 'mobile-release-${DateTime.now().microsecondsSinceEpoch}@example.com';
    final password = List.generate(32, (_) => Random.secure().nextInt(10)).join();
    final registration = await http.post(Uri.parse('${api.baseUrl}/auth/register'), headers: {'content-type':'application/json'}, body: jsonEncode({'email':email,'password':password}));
    expect(registration.statusCode, 200);
    await api.login(email:email, password:password);
    expect(api.accessToken, isNotEmpty);
    final history = await http.get(Uri.parse('${api.baseUrl}/history'), headers: {'authorization':'Bearer ${api.accessToken}'});
    expect(history.statusCode, 200);
  }, timeout: const Timeout(Duration(minutes: 2)));
}

