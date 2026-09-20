import 'package:flutter_test/flutter_test.dart';
import 'package:xai_compress_desktop/services/api_service.dart';
import 'package:xai_compress_desktop/services/deployment_config.dart';

void main() {
  const enabled = bool.fromEnvironment('XAI_RUNTIME_SMOKE');
  test('configured desktop forgot-password runtime smoke', () async {
    final uri = Uri.parse(configuredApiUrl());
    expect(uri.scheme, 'https');
    expect(uri.host, 'xai-1-be9s.onrender.com');
    final api = ApiService();
    addTearDown(api.dispose);
    await api.forgotPassword('runtime-smoke@example.invalid');
  },
      skip: enabled
          ? false
          : 'Set XAI_RUNTIME_SMOKE=true for the controlled live smoke test.');
}
