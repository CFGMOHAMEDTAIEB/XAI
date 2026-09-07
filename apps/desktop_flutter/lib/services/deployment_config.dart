import 'package:flutter/foundation.dart';
String configuredApiUrl() {
  const defined = String.fromEnvironment('XAI_API_URL');
  if (kReleaseMode) {
    final uri = Uri.tryParse(defined);
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty || uri.userInfo.isNotEmpty ||
        ['localhost','127.0.0.1','10.0.2.2','backend','::1'].contains(uri.host) || defined.contains('REPLACE_')) {
      throw StateError('Production build requires a deployed HTTPS XAI_API_URL.');
    }
  }
  return defined.isEmpty ? 'http://localhost:8000' : defined;
}
