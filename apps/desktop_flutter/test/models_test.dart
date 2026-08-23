import 'package:flutter_test/flutter_test.dart';import 'package:xai_compress_desktop/models/app_models.dart';
void main(){test('calculates compression metrics',(){final r=EngineResult(originalSize:1000,outputSize:400,mode:'static');expect(r.saving,60);expect(r.ratio,2.5);expect(r.bitsPerByte,3.2);});}
