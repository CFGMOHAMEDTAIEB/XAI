String accountDisplayName(Map<String, dynamic>? account) {
  for (final key in const ['display_name', 'full_name', 'email']) {
    final value = account?[key];
    if (value is String && value.trim().isNotEmpty) return value.trim();
  }
  return 'XAI user';
}

String accountInitials(Map<String, dynamic>? account) {
  final words = accountDisplayName(account)
      .split(RegExp(r'\s+'))
      .where((word) => word.isNotEmpty)
      .toList(growable: false);
  if (words.isEmpty) return 'X';
  if (words.length == 1) return _firstCharacter(words.first).toUpperCase();
  return '${_firstCharacter(words.first)}${_firstCharacter(words.last)}'
      .toUpperCase();
}

String _firstCharacter(String value) =>
    value.isEmpty ? 'X' : String.fromCharCode(value.runes.first);
