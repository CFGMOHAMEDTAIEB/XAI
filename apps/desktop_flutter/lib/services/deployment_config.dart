import 'package:flutter/foundation.dart';

const desktopDefaultApiUrl = 'https://xai-1-be9s.onrender.com';

String configuredApiUrl() {
  const compiled = String.fromEnvironment(
    'XAI_API_URL',
    defaultValue: desktopDefaultApiUrl,
  );
  return validateDesktopApiUrl(compiled, allowLocal: !kReleaseMode);
}

@visibleForTesting
String validateDesktopApiUrl(String value, {required bool allowLocal}) {
  final normalized = value.trim().replaceFirst(RegExp(r'/+$'), '');
  final uri = Uri.tryParse(normalized);
  final localHosts = {'localhost', '127.0.0.1', '::1'};
  if (uri == null ||
      !uri.hasScheme ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.path.isNotEmpty && uri.path != '/') ||
      !{'http', 'https'}.contains(uri.scheme) ||
      (!allowLocal && uri.scheme != 'https') ||
      (!allowLocal && localHosts.contains(uri.host)) ||
      normalized.contains('REPLACE_')) {
    throw StateError('Desktop API URL is not a valid service origin.');
  }
  return normalized;
}
