import 'dart:convert';
import 'dart:math';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:xai_compress_desktop/services/api_service.dart';
void main() {
  test('Production API configuration and desktop authentication', () async {
    final api = ApiService();
    expect(api.baseUrl, 'https://xai-1-be9s.onrender.com');
    final email = 'desktop-release-${DateTime.now().microsecondsSinceEpoch}@example.com';
    final password = List.generate(32, (_) => Random.secure().nextInt(10)).join();
    final registration = await http.post(Uri.parse('${api.baseUrl}/auth/register'), headers: {'content-type':'application/json'}, body: jsonEncode({'email':email,'password':password}));
    expect(registration.statusCode, 200);
    await api.login(email, password);
    expect(api.token, isNotEmpty);
    expect(await api.history(), isA<List<dynamic>>());
  }, timeout: const Timeout(Duration(minutes: 2)));
}
