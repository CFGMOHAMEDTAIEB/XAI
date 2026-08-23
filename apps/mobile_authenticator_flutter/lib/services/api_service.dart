import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiService {
  ApiService({this.baseUrl = 'http://10.0.2.2:8000'});

  String baseUrl;
  String? accessToken;

  Future<void> login({
    required String email,
    required String password,
    String? totpCode,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/login'),
      headers: {'content-type': 'application/json'},
      body: jsonEncode({
        'email': email,
        'password': password,
        'totp_code': totpCode,
      }),
    );
    if (response.statusCode >= 400) {
      throw Exception(response.body);
    }
    accessToken = (jsonDecode(response.body) as Map<String, dynamic>)['access_token'] as String;
  }

  Future<Map<String, dynamic>> enrollTotp() async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/totp/enroll'),
      headers: {'authorization': 'Bearer $accessToken'},
    );
    if (response.statusCode >= 400) throw Exception(response.body);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<bool> confirmTotp(String code) async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/totp/confirm?code=$code'),
      headers: {'authorization': 'Bearer $accessToken'},
    );
    if (response.statusCode >= 400) throw Exception(response.body);
    return true;
  }
}
