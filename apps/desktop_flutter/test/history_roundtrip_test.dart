import 'package:flutter_test/flutter_test.dart';
import 'package:xai_compress_desktop/models/app_models.dart';

void main() {
  test('persisted history preserves measured sizes and savings', () {
    final original = HistoryItem(id: '1', action: 'compress', inputPath: 'input',
      outputPath: 'output', mode: 'static', createdAt: DateTime(2026), success: true,
      result: EngineResult(originalSize: 1000, outputSize: 400, mode: 'static'));
    final restored = HistoryItem.fromJson(original.toJson());
    expect(restored.result!.originalSize, 1000);
    expect(restored.result!.outputSize, 400);
    expect(restored.result!.saving, 60);
  });
}
